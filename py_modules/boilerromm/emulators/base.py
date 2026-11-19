"""An emulator boilerRomM installs and runs itself: where its build comes from, where its files live, how it starts a game.

Each emulator's files are split by how replaceable they are. The build and its cache can be fetched again, the
config is rewritten by prepare(), and saves, states and firmware are the user's: nothing here deletes those.
"""
import hashlib
import asyncio
import os
import shutil
from dataclasses import dataclass

from ..games.install import Target, launch_file
from . import releases


@dataclass(frozen=True)
class Layout:
    """The folders under the plugin's data folder. ROMs are not among them: their folder is a setting of its own."""
    root: str

    def bios(self, platform: str) -> str:
        return os.path.join(self.root, "bios", platform)

    def saves(self, platform: str, emulator: str) -> str:
        return os.path.join(self.root, "saves", platform, emulator)

    def states(self, platform: str, emulator: str) -> str:
        return os.path.join(self.root, "states", platform, emulator)

    def emulator(self, emulator: str) -> str:
        return os.path.join(self.root, "emulators", emulator)


@dataclass(frozen=True)
class Firmware:
    platform: str
    name: str
    md5: str


@dataclass(frozen=True)
class Command:
    """What a Steam shortcut runs to start a game."""
    argv: list[str]
    env: dict[str, str]


def link_dir(link: str, target: str) -> None:
    """Makes `link` a link to the folder `target`; a folder the emulator already filled there is left where it works."""
    os.makedirs(target, exist_ok=True)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.islink(link):
        if os.readlink(link) == target:
            return
        os.unlink(link)
    elif os.path.isdir(link):
        try:
            os.rmdir(link)
        except OSError:
            return
    os.symlink(target, link)


_md5: dict[tuple[str, int, int], str] = {}


def md5_of(path: str) -> str:
    """A file's checksum, remembered until the file changes: status() asks on every state the backend sends."""
    stat = os.stat(path)
    key = (path, stat.st_size, stat.st_mtime_ns)
    if key not in _md5:
        _md5[key] = _digest(path)
    return _md5[key]


def _digest(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Emulator:
    id = ""
    name = ""
    system = ""                       # what it emulates, as a person would say it
    platforms: tuple[str, ...] = ()   # RomM filesystem slugs
    source: releases.Source
    firmware: tuple[Firmware, ...] = ()
    requires = "a BIOS"               # what the user must supply, as it reads after "needs"
    year = 0                          # when its oldest system came out: emulators are listed and installed in this order
    accepts = ".bin"                  # the kind of firmware file it takes, as shown to the user
    firmware_set = False              # it takes a set of files, not one
    recent_versions = 20              # how many of the project's newest releases to offer besides the latest

    def __init__(self, layout: Layout):
        self.layout = layout
        self.home = layout.emulator(self.id)
        self.executable = os.path.join(self.home, f"{self.id}.AppImage")
        self.version_file = os.path.join(self.home, "version")
        self.config_dir = os.path.join(self.home, "config")
        self.data_dir = os.path.join(self.home, "data")
        self.cache_dir = os.path.join(self.home, "cache")

    # Build
    def _installed(self) -> list[str]:
        if not os.path.isfile(self.executable):
            return []
        try:
            with open(self.version_file, encoding="utf-8") as f:
                return f.read().split("\n")
        except OSError:
            return []

    @property
    def version(self) -> str:
        """The installed build's release tag; "" when not installed."""
        return (self._installed() or [""])[0].strip()

    @property
    def version_name(self) -> str:
        """What to call the installed build: the tag, unless the emulator names its builds some other way."""
        lines = self._installed()
        return (lines[1].strip() if len(lines) > 1 else "") or self.version

    def version_label(self, tag: str, title: str) -> str:
        """The name of a build as a person would say it; the release's title where the tag is only a commit."""
        return tag

    async def versions(self, session) -> list[dict]:
        """The builds that can be installed, the one boilerRomM is tested with first."""
        listed = await releases.versions(session, self.source, self.recent_versions)
        tested = self.source.tag
        if tested and all(v.tag != tested for v in listed):
            listed.insert(0, releases.Version(tested, False, ""))
        listed.sort(key=lambda v: v.tag != tested)
        return [{"tag": v.tag, "name": self.version_label(v.tag, v.title), "prerelease": v.prerelease, "published": v.published,
                 "tested": v.tag == tested} for v in listed]

    async def install(self, session, tag: str = "") -> str:
        """Installs the tested build, or the build of another release when a tag is given."""
        release = await releases.find(session, self.source, tag)
        await releases.download(session, release, self.executable)
        with open(self.version_file, "w", encoding="utf-8") as f:
            f.write(f"{release.tag}\n{self.version_label(release.tag, release.title)}")
        return release.tag

    def uninstall(self, keep_settings: bool = True) -> None:
        """Removes the build and its cache, and the config and data too unless they are kept."""
        if keep_settings:
            for path in (self.executable, self.version_file):
                try:
                    os.unlink(path)
                except OSError:
                    pass
            shutil.rmtree(self.cache_dir, ignore_errors=True)
        else:
            shutil.rmtree(self.home, ignore_errors=True)

    # Firmware
    def firmware_found(self) -> list[Firmware]:
        """The known firmware files present, recognised by content: emulators do not care what they are called."""
        known = {f.md5: f for f in self.firmware}
        found = []
        for platform in sorted({f.platform for f in self.firmware}):
            folder = self.layout.bios(platform)
            try:
                names = sorted(os.listdir(folder))
            except OSError:
                continue
            for name in names:
                path = os.path.join(folder, name)
                match = known.get(md5_of(path)) if os.path.isfile(path) else None
                if match and match.platform == platform:
                    found.append(match)
        return found

    def firmware_ready(self) -> bool:
        """Whether the emulator has the firmware it needs. By default any one known file is enough."""
        return not self.firmware or bool(self.firmware_found())

    def bios_platforms(self) -> tuple[str, ...]:
        """The platforms whose folders the user fills; none for an emulator that needs nothing."""
        return tuple(sorted({f.platform for f in self.firmware}))

    def platform_ready(self, platform: str) -> bool:
        return any(f.platform == platform for f in self.firmware_found())

    def expected_files(self, platform: str) -> str:
        """The files to put on the RomM server for this platform, as they are usually named."""
        names = list(dict.fromkeys(f.name for f in self.firmware if f.platform == platform))
        return ", ".join(names[:3]) + (", …" if len(names) > 3 else "")

    def compatible(self, entry: dict) -> bool:
        """Whether a firmware file RomM lists ({file_name, md5_hash, ...}) is one this emulator can use, judged
        before it is downloaded. Without a checksum from RomM the name has to do; the download is checked again."""
        md5 = (entry.get("md5_hash") or "").lower()
        if md5:
            return any(f.md5 == md5 for f in self.firmware)
        return str(entry.get("file_name", "")).lower().endswith(self.accepts.lower())

    def recommended(self, entries: list[dict]) -> dict | None:
        """The one of RomM's compatible files to install when nobody chooses."""
        return entries[0] if entries else None

    def firmware_label(self) -> str:
        """What is installed, in a few words; "" when nothing is."""
        names = list(dict.fromkeys(f.name for f in self.firmware_found()))
        return ", ".join(names) if len(names) <= 2 else f"{len(names)} files"

    def remove_firmware(self) -> None:
        """Deletes the firmware files this emulator recognises; other files in the folders are left."""
        known = {f.md5 for f in self.firmware}
        for platform in self.bios_platforms():
            folder = self.layout.bios(platform)
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for name in names:
                path = os.path.join(folder, name)
                if os.path.isfile(path) and md5_of(path) in known:
                    os.unlink(path)

    def bios_status(self) -> list[dict]:
        found = self.firmware_found()
        return [{"platform": p, "folder": self.layout.bios(p), "found": [f.name for f in found if f.platform == p], "ready": self.platform_ready(p),
                 "expects": self.expected_files(p)}
                for p in self.bios_platforms()]

    def add_firmware(self, path: str) -> Firmware | None:
        """Copies a firmware file into place if it is one this emulator knows; None when it is not."""
        digest = md5_of(path)
        match = next((f for f in self.firmware if f.md5 == digest), None)
        if match:
            folder = self.layout.bios(match.platform)
            os.makedirs(folder, exist_ok=True)
            shutil.copyfile(path, os.path.join(folder, match.name))
        return match

    # Config
    def prepare(self) -> None:
        """Makes the emulator ready to start a game. Safe before every launch: it keeps the user's settings and
        only re-points the folders, so a moved data folder is picked up."""
        for folder in (self.config_dir, self.data_dir, self.cache_dir):
            os.makedirs(folder, exist_ok=True)
        for platform in self.platforms:
            for folder in (self.layout.bios(platform), self.layout.saves(platform, self.id), self.layout.states(platform, self.id)):
                os.makedirs(folder, exist_ok=True)
        self.configure()

    def configure(self) -> None:
        """Writes the emulator's own config files."""
        raise NotImplementedError

    def reset_config(self) -> None:
        """Throws away the emulator's settings and writes fresh ones. Saves, states and firmware are untouched."""
        shutil.rmtree(self.config_dir, ignore_errors=True)
        self.prepare()

    # Launch
    @property
    def firmware_installed(self) -> bool:
        """Whether the firmware is where the emulator uses it; for most, having the files is all there is to it."""
        return self.firmware_ready()

    async def install_firmware(self) -> None:
        """Whatever the emulator must do with its firmware files before a game can start; most only need the files."""

    async def run(self, *args: str, timeout: float) -> int:
        """Runs the emulator itself with `args`, without a window, and waits for it to end."""
        # Decky Loader's own Python points these at its bundle, which an AppImage must not load from.
        env = {k: v for k, v in os.environ.items() if k not in ("LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH")}
        process = await asyncio.create_subprocess_exec(
            self.executable, *args, env={**env, **self.env()}, cwd=self.home,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            return await asyncio.wait_for(process.wait(), timeout)
        except BaseException:
            if process.returncode is None:
                process.kill()
            raise

    def env(self) -> dict[str, str]:
        # Most emulators follow the XDG folders, which keeps their files out of the user's own ~/.config.
        return {"XDG_CONFIG_HOME": self.config_dir, "XDG_DATA_HOME": self.data_dir, "XDG_CACHE_HOME": self.cache_dir}

    def launch_file(self, target: Target) -> str:
        return launch_file(target)

    def command(self, rom: str, platform: str = "") -> Command:
        """What to run for a game; `platform` is its RomM slug, for an emulator that runs several."""
        raise NotImplementedError

    def status(self) -> dict:
        version, firmware = self.version, self.firmware_ready()
        return {"id": self.id, "name": self.name, "system": self.system, "platforms": list(self.platforms), "installed": bool(version),
                "version": version, "version_name": self.version_name, "firmware": firmware, "requires": self.requires, "ready": bool(version) and firmware,
                "configured": os.path.isdir(self.config_dir) and bool(os.listdir(self.config_dir)), "bios": self.bios_status(),
                "firmware_installed": self.firmware_installed, "year": self.year, "accepts": self.accepts,
                "firmware_set": self.firmware_set, "firmware_label": self.firmware_label()}
