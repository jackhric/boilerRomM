"""Emulator builds published as GitHub release assets: finding one and downloading it."""
import hashlib
import os
import re
from dataclasses import dataclass

API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "boilerRomM/1.0"}
CHUNK = 1 << 20


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class Source:
    repo: str        # "owner/name"
    asset: str       # regular expression searched in the asset's file name
    tag: str = ""    # "" for the latest release


@dataclass(frozen=True)
class Release:
    tag: str
    name: str
    url: str
    size: int
    sha256: str      # "" when the release does not publish one
    title: str = ""  # the release's own name, where the tag is not what people call the version


@dataclass(frozen=True)
class Version:
    tag: str
    prerelease: bool
    published: str   # ISO date
    title: str = ""


async def _json(session, source: Source, path: str):
    async with session.get(f"{API}/repos/{source.repo}/{path}", headers=HEADERS) as r:
        if r.status != 200:
            raise ReleaseError(f"{source.repo} {path}: HTTP {r.status}")
        return await r.json()


async def versions(session, source: Source, recent: int = 20) -> list[Version]:
    """The builds worth offering: the latest stable release, then the `recent` newest releases of any kind."""
    found = []
    try:
        found.append(await _json(session, source, "releases/latest"))
    except ReleaseError:
        pass  # a project that only publishes prereleases has no "latest"
    if recent:
        found += await _json(session, source, f"releases?per_page={recent}")
    out: dict[str, Version] = {}
    for release in found:
        has_build = any(re.search(source.asset, a["name"]) for a in release.get("assets", []))
        if has_build and not release.get("draft"):
            out.setdefault(release["tag_name"], Version(release["tag_name"], bool(release.get("prerelease")), (release.get("published_at") or "")[:10],
                                                           release.get("name") or ""))
    return list(out.values())


async def find(session, source: Source, tag: str = "") -> Release:
    """The source's build in the release `tag`, or in the release the source names when no tag is given."""
    tag = tag or source.tag
    data = await _json(session, source, f"releases/tags/{tag}" if tag else "releases/latest")
    for a in data.get("assets", []):
        if re.search(source.asset, a["name"]):
            digest = a.get("digest") or ""
            return Release(data["tag_name"], a["name"], a["browser_download_url"], a["size"],
                           digest.removeprefix("sha256:") if digest.startswith("sha256:") else "", data.get("name") or "")
    raise ReleaseError(f"{source.repo} {data.get('tag_name', '')}: no asset matches {source.asset}")


async def download(session, release: Release, dest: str) -> None:
    """Writes the asset to `dest` as an executable; a download that does not match the release leaves nothing behind."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    digest, size = hashlib.sha256(), 0
    try:
        async with session.get(release.url, headers={"User-Agent": HEADERS["User-Agent"]}) as r:
            if r.status != 200:
                raise ReleaseError(f"{release.name}: HTTP {r.status}")
            with open(part, "wb") as f:
                async for chunk in r.content.iter_chunked(CHUNK):
                    f.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
        if size != release.size:
            raise ReleaseError(f"{release.name}: got {size} bytes, expected {release.size}")
        if release.sha256 and digest.hexdigest() != release.sha256:
            raise ReleaseError(f"{release.name}: checksum does not match the release")
        os.chmod(part, 0o755)
        os.replace(part, dest)
    except BaseException:
        try:
            os.unlink(part)
        except OSError:
            pass
        raise
