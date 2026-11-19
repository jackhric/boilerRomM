"""The one object main.py builds: settings, the RomM client, pairing, the library and downloads.

Every change ends in `emit(STATE_EVENT, state)`, so the panel and the library page only render the latest snapshot;
download progress goes out separately as `PROGRESS_EVENT` a couple of times a second.
"""
import asyncio
import base64
import hashlib
import logging
import os
import shlex
import socket
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

from .artwork import ArtCache, ArtPrefetch
from . import ledger as L
from .downloads import Downloader, Job, as_game, manifest
from .install import ROMS_FOLDER, InstallLocation, Target
from .ledger import Install, Ledger
from .library import Library
from .pairing import DevicePairing
from . import emulators
from .progress import Counted
from .shortcuts import ShortcutMap
import shutil
from .romm import MIN_VERSION, RommClient, RommError, normalize_url, parse_version, ssl_context
from .sgdb import KINDS as ART_KINDS, SgdbClient, SgdbError
from .settings import Settings, SettingsStore
from .video import VideoResolver
from .signin import SgdbSignin

STATE_EVENT = "boilerromm_state"
PROGRESS_EVENT = "boilerromm_progress"
LIBRARY_REFRESH_S = 600
CLIENT = "boilerromm"


def device_identity(version: str) -> dict:
    try:
        with open("/etc/machine-id") as f:
            machine = f.read().strip()
    except OSError:
        machine = socket.gethostname()
    return {
        "client_device_identifier": hashlib.sha256(machine.encode()).hexdigest()[:32],
        "name": socket.gethostname() or "Steam device",
        "client": CLIENT,
        "platform": "steamos",
        "client_version": version,
    }


@dataclass(frozen=True)
class Held:
    """A ledger record with what the disk says about it."""
    install: Install
    target: Target
    seen: L.Check
    state: str


class App:
    def __init__(self, settings_path: str, version: str, home: str,
                 emit: Callable[..., Awaitable[None]], logger: logging.Logger, data_dir: str = "",
                 sgdb_session_factory: Callable[[], Any] | None = None, browser: dict | None = None,
                 release_session_factory: Callable[[], Any] | None = None):
        self.store = SettingsStore(settings_path)
        self.settings: Settings = self.store.load()
        self.version = version
        self.home = home
        self.identity = device_identity(version)
        self._emit = emit
        self.log = logger
        self.client: RommClient | None = None
        self.pairing: DevicePairing | None = None
        self.server: dict[str, Any] = {"version": "", "error": ""}
        self.library = Library()
        self.videos = VideoResolver(log=logger)
        self.shortcuts = ShortcutMap(os.path.join(os.path.dirname(settings_path), "shortcuts.json"))
        self.ledger = Ledger(os.path.join(os.path.dirname(settings_path), "installs.json"), logger)
        self.launcher = ""
        self.runtime_dir = ""
        self.data_dir = data_dir or os.path.dirname(settings_path)
        self.location = InstallLocation(self.settings.roms_dir or self.default_roms_dir, home)
        self.emulators = {cls.id: cls(emulators.Layout(self.data_dir)) for cls in emulators.ALL}
        self._emulator_busy: dict[str, str] = {}
        self._emulator_error: dict[str, str] = {}
        self._emulator_versions: dict[str, tuple[float, list[dict]]] = {}
        self._emulator_progress: dict[str, tuple[int, int]] = {}
        self._bios_fetching: set[str] = set()
        self._progress_sent = 0.0
        self._install_all: asyncio.Task | None = None
        # No total timeout: a build is tens of megabytes on whatever connection the device has.
        self._release_session = release_session_factory or (lambda: aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=60), connector=aiohttp.TCPConnector(ssl=ssl_context())))
        self.downloader: Downloader | None = None
        self._refresh_task: asyncio.Task | None = None
        if self.settings.server_url:
            self.client = RommClient(self.settings.server_url, self.settings.token)
        self.art = ArtCache(data_dir or os.path.dirname(settings_path))
        self._sgdb_session = sgdb_session_factory or (lambda: aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30), connector=aiohttp.TCPConnector(ssl=ssl_context())))
        self.sgdb: SgdbClient | None = self._sgdb_client(self.settings.sgdb_key) if self.settings.sgdb_key else None
        self._cdn: SgdbClient | None = None
        self.sgdb_error = ""
        self.prefetch = ArtPrefetch(self.art, self._changed, self._art_failed, logger)
        self.signin = SgdbSignin(self._signin_key, self._changed, logger, **(browser or {}))

    # Lifecycle
    def install_launcher(self, source: str, runtime_dir: str) -> None:
        """Copies the shortcut launcher where the user can run it (the plugin dir is root-owned)."""
        self.runtime_dir = runtime_dir
        try:
            os.makedirs(runtime_dir, exist_ok=True)
            dest = os.path.join(runtime_dir, "boilerromm-launch")
            shutil.copyfile(source, dest)
            os.chmod(dest, 0o755)
            self.launcher = dest
        except OSError as e:
            self.log.warning("launcher not installed: %s", e)

    async def start(self) -> None:
        if self.settings.paired:
            self._start_paired()
        elif self.client:
            asyncio.create_task(self._probe_server())

    async def stop(self) -> None:
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._install_all:
            self._install_all.cancel()
        if self.signin.active:
            await self.signin.cancel()
        await self.prefetch.stop()
        for c in (self.sgdb, self._cdn):
            if c:
                await c.close()
        if self.downloader:
            await self.downloader.stop()
        if self.pairing:
            await self.pairing.cancel()
        if self.client:
            await self.client.close()

    def _start_paired(self) -> None:
        assert self.client
        self.downloader = Downloader(self.client, self.location, self._progress, self._finished, self.ledger)
        self.downloader.restore(self.shortcuts.appid)
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    # Snapshot
    def state(self) -> dict:
        s = self.settings
        held = self.held()
        return {
            "server": {"url": s.server_url, **self.server},
            "pairing": self.pairing.state.as_dict() if self.pairing else {"status": "idle"},
            "account": {"paired": s.paired, "username": s.username, "device_id": s.device_id,
                        "device_name": self.identity["name"]},
            "library": self.library.snapshot(lambda rom_id: self.status(rom_id, held), lambda g: self.art.urls(g.rom_id, g.sgdb_id, g.name)),
            "downloads": self.downloader.snapshot() if self.downloader else {"active": None, "queue": [], "roms_dir": self.location.roms_dir},
            "installs": self.installs(held),
            "installed": self.installed(held),
            "roms_dir_exists": self.location.exists,
            "storage": self.storage(held),
            "emulators": [{**e.status(), "busy": self._emulator_busy.get(e.id, ""), "error": self._emulator_error.get(e.id, ""),
                           "progress": self._emulator_progress.get(e.id)}
                          for e in self.emulators.values()],
            "setup_done": self.settings.setup_done,
            "sgdb": {"configured": self.sgdb is not None, "error": self.sgdb_error,
                     "art_ready": self.art.count(self.library.games.values()), "art_total": len(self.library.games),
                     "signin": self.signin.as_dict()},
            "version": self.version,
        }

    def _target(self, install: Install) -> Target:
        return self.location.target(install.slug, install.fs_name, install.single_file)

    def held(self) -> dict[int, "Held"]:
        """Every record held against the disk once; a snapshot shares one of these between its parts."""
        out = {}
        for i in self.ledger.all():
            target = self._target(i)
            seen = L.check(i, target.path)
            # An installed game with files gone reads as incomplete.
            state = L.INCOMPLETE if i.state == L.INSTALLED and not seen.complete else i.state
            out[i.rom_id] = Held(i, target, seen, state)
        return out

    def status(self, rom_id: int, held: dict[int, "Held"] | None = None) -> str:
        h = (self.held() if held is None else held).get(rom_id)
        return h.state if h else "available"

    def installs(self, held: dict[int, "Held"] | None = None) -> list[dict]:
        """Every game the ledger knows, held against the disk."""
        return [{"rom_id": h.install.rom_id, "name": h.install.name, "state": h.state, "appid": self.shortcuts.appid(h.install.rom_id),
                 "bytes_done": h.seen.done_bytes, "bytes_total": h.seen.total_bytes, "missing": list(h.seen.missing),
                 "error": h.install.error, "queued_at": h.install.queued_at, "updated_at": h.install.updated_at,
                 "completed_at": h.install.completed_at}
                for h in (self.held() if held is None else held).values()]

    def storage(self, held: dict[int, "Held"] | None = None) -> dict:
        """What the ROM folder's drive has: bytes taken by installed games, and the drive's free and total bytes."""
        used = sum(h.seen.done_bytes for h in (self.held() if held is None else held).values() if h.state == L.INSTALLED)
        # The folder is only made when the first game downloads; its drive is the nearest folder that exists.
        path = self.location.roms_dir
        while path and not os.path.exists(path) and os.path.dirname(path) != path:
            path = os.path.dirname(path)
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return {"used_bytes": used, "free_bytes": 0, "total_bytes": 0}
        return {"used_bytes": used, "free_bytes": usage.free, "total_bytes": usage.total}

    def installed(self, held: dict[int, "Held"] | None = None) -> list[dict]:
        """Complete games that have a Steam shortcut, with what Steam's storage pages show for an installed app."""
        out = []
        for h in (self.held() if held is None else held).values():
            appid = self.shortcuts.appid(h.install.rom_id)
            if not appid or h.state != L.INSTALLED:
                continue
            try:
                device = os.stat(h.target.path).st_dev
            except OSError:
                continue
            out.append({"rom_id": h.install.rom_id, "appid": appid, "name": h.install.name, "path": h.target.path,
                        "folder": h.target.path if h.target.is_dir else os.path.dirname(h.target.path),
                        "bytes": h.seen.done_bytes, "device": device})
        return out

    async def adopt(self) -> None:
        """Games found on disk that the ledger does not know (from before it existed, or after it was lost) get a
        record: RomM's file list decides whether each is installed or incomplete."""
        if not self.client:
            return
        changed = False
        for game in list(self.library.games.values()):
            if self.ledger.get(game.rom_id):
                continue
            target = self.location.target(game.slug, game.fs_name, game.single_file)
            if not (target.installed or target.partial):
                continue
            try:
                files = manifest(await self.client.rom(game.rom_id), target)
            except Exception as e:
                self.log.warning("could not check %s found on disk: %s", game.name, e)
                continue
            install = Install(rom_id=game.rom_id, name=game.name, slug=game.slug, fs_name=game.fs_name, single_file=game.single_file,
                              size_bytes=game.size_bytes, files=files, state=L.INCOMPLETE)
            if L.check(install, target.path).complete:
                install.state = L.INSTALLED
            self.ledger.put(install)
            changed = True
        if changed:
            self._changed()

    async def verify(self, rom_id: int) -> dict:
        """Asks RomM for the game's files again and holds the disk against them."""
        install = self.ledger.get(int(rom_id))
        if not install or not self.client:
            raise ValueError("Unknown game")
        if install.state not in L.IN_QUEUE:
            files = manifest(await self.client.rom(install.rom_id), self._target(install))
            install = self.ledger.update(install.rom_id, files=files)
            complete = L.check(install, self._target(install).path).complete
            if complete != (install.state == L.INSTALLED):
                self.ledger.update(install.rom_id, state=L.INSTALLED if complete else L.INCOMPLETE)
        self._changed()
        return self.state()

    # Emulators
    async def _emulator_task(self, emulator_id: str, doing: str, work: Callable[[emulators.Emulator], Awaitable[None]]) -> dict:
        emulator = self.emulators.get(emulator_id)
        if not emulator:
            raise ValueError("Unknown emulator")
        if self._emulator_busy.get(emulator_id):
            return self.state()
        self._emulator_busy[emulator_id] = doing
        self._emulator_error.pop(emulator_id, None)
        self._changed()
        try:
            await work(emulator)
        except Exception as e:
            self.log.warning("%s %s failed: %s", doing, emulator_id, e)
            self._emulator_error[emulator_id] = str(e) or type(e).__name__
        finally:
            self._emulator_busy.pop(emulator_id, None)
        self._changed()
        return self.state()

    async def emulator_versions(self, emulator_id: str) -> list[dict]:
        """The builds on offer, asked from the project at most every ten minutes (GitHub limits anonymous requests)."""
        emulator = self.emulators.get(emulator_id)
        if not emulator:
            raise ValueError("Unknown emulator")
        cached = self._emulator_versions.get(emulator_id)
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
        async with self._release_session() as session:
            listed = await emulator.versions(session)
        self._emulator_versions[emulator_id] = (time.monotonic(), listed)
        return listed

    def _downloaded(self, emulator_id: str, done: int, total: int) -> None:
        self._emulator_progress[emulator_id] = (done, total)
        # A download reports every chunk; the screen needs a few updates a second.
        if time.monotonic() - self._progress_sent > 0.3:
            self._progress_sent = time.monotonic()
            self._changed()

    async def emulator_install(self, emulator_id: str, tag: str = "") -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            try:
                async with self._release_session() as session:
                    await emulator.install(Counted(session, lambda done, total: self._downloaded(emulator.id, done, total)), tag)
                emulator.prepare()
            finally:
                self._emulator_progress.pop(emulator.id, None)
            await self._auto_bios(emulator)
        return await self._emulator_task(emulator_id, "installing", work)

    async def emulators_install_all(self) -> dict:
        """Installs every emulator that is not installed, one after another, in the background. Each stands alone:
        one that fails is reported on its own row and the rest carry on."""
        waiting = [e.id for e in self.emulators.values() if not e.version and not self._emulator_busy.get(e.id)]
        for emulator_id in waiting:
            self._emulator_busy[emulator_id] = "queued"
            self._emulator_error.pop(emulator_id, None)
        if waiting:
            previous = self._install_all
            self._install_all = asyncio.create_task(self._install_queued(waiting, previous))
        self._changed()
        return self.state()

    async def _install_queued(self, waiting: list[str], previous: asyncio.Task | None) -> None:
        try:
            if previous:
                await asyncio.gather(previous, return_exceptions=True)
            for emulator_id in waiting:
                self._emulator_busy.pop(emulator_id, None)
                await self.emulator_install(emulator_id)
        finally:
            for emulator_id in waiting:
                if self._emulator_busy.get(emulator_id) == "queued":
                    self._emulator_busy.pop(emulator_id, None)

    async def finish_setup(self) -> dict:
        self.settings.setup_done = True
        self.store.save(self.settings)
        self._changed()
        return self.state()

    async def emulator_uninstall(self, emulator_id: str) -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            emulator.uninstall()
        return await self._emulator_task(emulator_id, "uninstalling", work)

    async def emulator_reset(self, emulator_id: str) -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            emulator.reset_config()
        return await self._emulator_task(emulator_id, "resetting", work)

    async def rescan_bios(self) -> dict:
        self._changed()
        return self.state()

    async def _fetch_bios(self, emulator: emulators.Emulator) -> tuple[int, int]:
        """Downloads the firmware RomM holds for the emulator's platforms: (kept, listed). Each file goes through the
        emulator's own check, so only what it recognises is kept, and a file that fails the check is not."""
        if not self.client or not self.settings.paired:
            raise RuntimeError("Connect to RomM first")
        ids = {p["fs_slug"]: p["id"] for p in await self.client.platforms()}
        kept, listed = 0, 0
        with tempfile.TemporaryDirectory(dir=self.data_dir if os.path.isdir(self.data_dir) else None) as scratch:
            for platform in emulator.bios_platforms():
                if platform not in ids:
                    continue
                for entry in await self.client.firmware(ids[platform]):
                    listed += 1
                    path = os.path.join(scratch, os.path.basename(entry["file_name"]))
                    await self.client.fetch_firmware(entry["id"], entry["file_name"], path)
                    if emulator.add_firmware(path):
                        kept += 1
                    os.unlink(path)
        return kept, listed

    async def emulator_bios_from_romm(self, emulator_id: str) -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            kept, listed = await self._fetch_bios(emulator)
            if not kept:
                raise RuntimeError("RomM has no firmware for this emulator" if not listed else "None of RomM's files are ones it can use")
        return await self._emulator_task(emulator_id, "fetching", work)

    def _bios_missing(self, emulator: emulators.Emulator, slug: str = "") -> bool:
        """Whether the emulator lacks firmware it cannot run without: for `slug`'s games, or for any of its platforms."""
        needed = [p for p in emulator.bios_platforms() if not slug or p == slug]
        return any(not emulator.platform_ready(p) for p in needed)

    async def _auto_bios(self, emulator: emulators.Emulator, slug: str = "") -> None:
        """Gets missing firmware from RomM without being asked. Quiet: RomM not having it is not an error here, the
        BIOS page and the launch check say what is missing."""
        if emulator.id in self._bios_fetching or not self.settings.paired or not self._bios_missing(emulator, slug):
            return
        self._bios_fetching.add(emulator.id)
        try:
            kept, _ = await self._fetch_bios(emulator)
            if kept:
                self.log.info("%s: %d firmware files from RomM", emulator.name, kept)
        except Exception as e:
            self.log.warning("firmware for %s was not fetched: %s", emulator.name, e)
        finally:
            self._bios_fetching.discard(emulator.id)
        self._changed()

    def _changed(self) -> None:
        asyncio.get_event_loop().create_task(self._emit(STATE_EVENT, self.state()))

    def _progress(self, progress: dict) -> None:
        asyncio.get_event_loop().create_task(self._emit(PROGRESS_EVENT, progress))

    async def _finished(self, job: Job) -> None:
        if job.status == "failed":
            self.log.warning("download of %s failed: %s", job.game.name, job.error)
        self._changed()

    @property
    def default_roms_dir(self) -> str:
        return os.path.join(self.data_dir, ROMS_FOLDER)

    def emulator_for(self, slug: str) -> emulators.Emulator | None:
        """The emulator that runs a platform's games; None when boilerRomM has none for it."""
        return next((e for e in self.emulators.values() if slug in e.platforms), None)

    def launch_script(self, rom_id: int) -> str:
        return os.path.join(self.runtime_dir, "launch", f"{int(rom_id)}.sh") if self.runtime_dir else ""

    def write_launch_script(self, slug: str, rom_id: int, target: Target) -> None:
        """Writes what the launcher runs for a game. A Steam shortcut carries only the game's id, so the emulator,
        its version and the ROM folder can all change without the shortcut going stale."""
        path = self.launch_script(rom_id)
        if not path:
            return
        emulator = self.emulator_for(slug)
        if not emulator:
            lines = [f"echo {shlex.quote(f'boilerRomM has no emulator for {slug} games')} >&2", "exit 1"]
        elif not emulator.version:
            lines = [f"echo {shlex.quote(f'{emulator.name} is not installed: install it in boilerRomM settings')} >&2", "exit 1"]
        else:
            emulator.prepare()
            command = emulator.command(emulator.launch_file(target), slug)
            # Steam lists a game while it downloads, so Play can be pressed before the files are whole.
            lines = [f"rom={shlex.quote(target.path)}",
                     'if [[ -e "$rom.part" ]] || { [[ -d "$rom" ]] && compgen -G "$rom/*.part" >/dev/null; }; then',
                     '  echo "boilerRomM: $rom is still downloading" >&2; exit 1',
                     "fi",
                     'if [[ ! -e "$rom" ]]; then echo "boilerRomM: $rom is not on this device" >&2; exit 1; fi']
            lines += [f"export {key}={shlex.quote(value)}" for key, value in command.env.items()]
            lines.append("exec " + " ".join(shlex.quote(arg) for arg in command.argv))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\n" + "\n".join(lines) + "\n")
        os.chmod(path, 0o755)

    def launch_target(self, rom_id: int) -> dict:
        """What a Steam shortcut for this game runs: the launcher with the game's id."""
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        target = self.location.target(game.slug, game.fs_name, game.single_file)
        self.write_launch_script(game.slug, game.rom_id, target)
        return {
            "rom_id": game.rom_id, "name": game.name, "appid": self.shortcuts.appid(game.rom_id),
            "exe": self.launcher or "/usr/bin/false", "start_dir": os.path.dirname(target.path),
            "launch_options": str(game.rom_id), "cover": game.cover_large or game.cover,
            "installed": target.installed, "blocked": self._blocked(game.slug, game.platform),
        }

    def _blocked(self, slug: str, platform: str) -> str:
        """Why a game of this platform cannot start; "" when it can."""
        emulator = self.emulator_for(slug)
        if not emulator:
            return f"boilerRomM has no emulator for {platform}."
        if not emulator.version:
            return f"{emulator.name} is not installed. Install it in Settings, under Emulators."
        if self._bios_missing(emulator, slug):
            return f"{emulator.name} needs {emulator.requires}, and RomM did not have one. Add it in Settings, under BIOS."
        return ""

    async def play_target(self, rom_id: int) -> dict:
        """`launch_target` for a game about to be started, after one more try at getting missing firmware."""
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        emulator = self.emulator_for(game.slug)
        if emulator and emulator.version:
            await self._auto_bios(emulator, game.slug)
        return self.launch_target(rom_id)

    # Server and pairing
    async def set_server(self, url: str) -> dict:
        typed = url.strip().rstrip("/")
        if not typed:
            raise ValueError("Enter the RomM server address")
        if self.pairing:
            await self.pairing.cancel()
            self.pairing = None
        # An address typed without a protocol is tried over https, then over http if nothing there is RomM.
        candidates = [typed] if "://" in typed else [f"https://{typed}", f"http://{typed}"]
        for url in candidates:
            if self.client:
                await self.client.close()
            self.client = RommClient(url)
            await self._probe_server(emit=False)
            if self.server["version"]:
                break
        if not self.server["version"]:
            url = normalize_url(typed)
            if len(candidates) > 1:
                self.server["error"] = f"Nothing answered at {typed}"
        if self.settings.server_url != url:
            await self.prefetch.stop()
            self.settings = self.settings.for_server(url)
            self.store.save(self.settings)
            self.library = Library()
        self._changed()
        return self.state()

    async def _probe_server(self, emit: bool = True) -> None:
        assert self.client
        self.server = {"version": "", "error": ""}
        try:
            hb = await self.client.heartbeat()
            version = str(hb.get("SYSTEM", {}).get("VERSION", ""))
            self.server["version"] = version
            if parse_version(version) < MIN_VERSION:
                self.server["error"] = f"RomM {'.'.join(map(str, MIN_VERSION))} or newer is needed (this one is {version})"
        except RommError as e:
            self.server["error"] = f"Not a RomM server ({e.status})"
        except Exception as e:
            self.server["error"] = f"Cannot reach {self.client.base_url}: {e}"
        if emit:
            self._changed()

    async def check_connection(self) -> dict:
        """Asks the server now: does it answer, which version, and does it still accept this device's token."""
        result = {"reachable": False, "version": "", "supported": False, "signed_in": False, "username": "", "ms": 0, "error": ""}
        if not self.client:
            result["error"] = "No server is set"
            return result
        started = time.monotonic()
        await self._probe_server(emit=False)
        result["ms"] = round((time.monotonic() - started) * 1000)
        version = self.server["version"]
        result.update(reachable=bool(version), version=version, supported=bool(version) and not self.server["error"], error=self.server["error"])
        if version and self.settings.paired:
            try:
                me = await self.client.me()
                result.update(signed_in=True, username=(me or {}).get("username", ""))
            except RommError as e:
                result["error"] = "RomM no longer accepts this device; disconnect and pair again" if e.status in (401, 403) else f"RomM answered {e.status}"
            except Exception as e:
                result["error"] = str(e) or type(e).__name__
        self._changed()
        return result

    async def start_pairing(self) -> dict:
        if not self.client or self.server.get("error"):
            raise ValueError("Connect to a RomM server first")
        if not self.pairing:
            self.pairing = DevicePairing(self.client, self.identity, self._changed, self._approved)
        await self.pairing.start()
        return self.state()

    async def cancel_pairing(self) -> dict:
        if self.pairing:
            await self.pairing.cancel()
        return self.state()

    async def _approved(self, token: dict) -> None:
        assert self.client
        self.client.token = token["access_token"]
        self.settings.token = token["access_token"]
        self.settings.device_id = token["device_id"]
        self.settings.scopes = list(token.get("scopes", []))
        try:
            me = await self.client.me()
            self.settings.username = me.get("username", "") if me else ""
        except Exception as e:
            self.log.warning("users/me failed after pairing: %s", e)
        self.store.save(self.settings)
        await self._describe_device()
        self.pairing = None
        self._start_paired()

    async def _describe_device(self) -> None:
        assert self.client
        try:
            await self.client.update_device(self.settings.device_id, {
                "client": CLIENT, "client_version": self.version, "platform": "steamos",
                "hostname": self.identity["name"], "capabilities": {},
            })
        except Exception as e:
            self.log.warning("device update failed: %s", e)

    async def disconnect(self) -> dict:
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None
        await self.prefetch.stop()
        if self.downloader:
            await self.downloader.stop()
            self.downloader = None
        if self.pairing:
            await self.pairing.cancel()
            self.pairing = None
        if self.client:
            await self.client.close()
            self.client = None
        self.settings = self.settings.signed_out()
        self.store.save(self.settings)
        self.server = {"version": "", "error": ""}
        self.library = Library()
        self._changed()
        return self.state()

    async def reset(self) -> dict:
        """Back to a fresh install, so setup runs again. Downloaded games and their saves stay on the device."""
        if self._install_all:
            self._install_all.cancel()
            self._install_all = None
        if self.signin.active:
            await self.signin.cancel()
        await self.clear_sgdb_key()
        self.art.clear()
        for emulator in self.emulators.values():
            try:
                emulator.uninstall(keep_settings=False)
            except OSError as e:
                self.log.warning("%s was not removed: %s", emulator.name, e)
        self._emulator_busy.clear()
        self._emulator_error.clear()
        self._emulator_progress.clear()
        return await self.disconnect()

    # Library and downloads
    async def refresh_library(self) -> dict:
        if self.settings.paired and self.client and not self.library.loading:
            await self.library.refresh(self.client)
            if self.library.error and "401" in self.library.error:
                self.library.error = "RomM no longer accepts this device; disconnect and pair again"
            elif not self.library.error and self.sgdb and not self.sgdb_error and not self.prefetch.running:
                self.prefetch.start(self.sgdb, self.library.games.values())
            self._changed()
            if not self.library.error:
                await self.adopt()
        return self.state()

    async def _refresh_loop(self) -> None:
        if not self.server.get("version"):
            await self._probe_server(emit=False)
        await self._describe_device()
        while True:
            await self.refresh_library()
            await asyncio.sleep(LIBRARY_REFRESH_S)

    async def game_details(self, rom_id: int) -> dict:
        game = self.library.games.get(int(rom_id))
        if not game or not self.client:
            raise ValueError("Unknown game")
        return game.details(self.client)

    async def game_video(self, rom_id: int) -> dict:
        """Direct stream addresses for the game's trailer ("" each when it has none or it cannot be resolved)."""
        game = self.library.games.get(int(rom_id))
        video_id = (game.raw.get("youtube_video_id") or "") if game else ""
        return {"rom_id": int(rom_id), **(await self.videos.resolve(video_id))}

    async def cover_base64(self, rom_id: int) -> dict:
        """The game's cover for Steam's custom artwork call (the Steam webview cannot fetch it cross-origin itself)."""
        game = self.library.games.get(int(rom_id))
        if not game or not self.client or not (game.cover_large or game.cover):
            return {"base64": "", "format": ""}
        data, _ctype = await self.client.fetch_bytes(game.cover_large or game.cover)
        # RomM labels every cover image/png whatever it holds; Steam needs the real format.
        fmt = "png" if data.startswith(b"\x89PNG") else "jpg" if data.startswith(b"\xff\xd8") else ""
        if not fmt:
            self.log.warning("cover of %s is neither PNG nor JPEG (%d bytes)", game.name, len(data))
            return {"base64": "", "format": ""}
        return {"base64": base64.b64encode(data).decode(), "format": fmt}

    # SteamGridDB artwork
    def _sgdb_client(self, key: str) -> SgdbClient:
        return SgdbClient(key, self._sgdb_session, f"boilerRomM/{self.version}")

    def _art_failed(self, e: SgdbError) -> None:
        self.sgdb_error = e.message
        self.log.warning("SteamGridDB prefetch stopped: %s", e.message)

    async def set_sgdb_key(self, key: str) -> dict:
        """Saves the key only once SteamGridDB accepts it; a refused key shows up as `sgdb.error`, never raises."""
        key = (key or "").strip()
        if not key:
            self.sgdb_error = "Enter a SteamGridDB API key"
            return self.state()
        client = self._sgdb_client(key)
        try:
            await client.verify()
        except SgdbError as e:
            await client.close()
            self.sgdb_error = "Invalid SteamGridDB key" if e.status in (401, 403) else e.message
            self._changed()
            return self.state()
        await self.prefetch.stop()
        if self.sgdb:
            await self.sgdb.close()
        self.sgdb, self.sgdb_error = client, ""
        self.settings.sgdb_key = key
        self.store.save(self.settings)
        if self.library.games:
            self.prefetch.start(client, self.library.games.values())
        self._changed()
        return self.state()

    async def _signin_key(self, key: str) -> str:
        await self.set_sgdb_key(key)
        return "" if self.sgdb is not None and not self.sgdb_error else (self.sgdb_error or "SteamGridDB did not accept the key")

    async def start_sgdb_signin(self) -> dict:
        self.signin.start()
        return self.state()

    async def cancel_sgdb_signin(self) -> dict:
        await self.signin.cancel()
        return self.state()

    async def clear_sgdb_key(self) -> dict:
        await self.prefetch.stop()
        if self.sgdb:
            await self.sgdb.close()
        self.sgdb, self.sgdb_error = None, ""
        self.settings.sgdb_key = ""
        self.store.save(self.settings)
        self._changed()
        return self.state()

    async def _art_entry(self, game) -> dict | None:
        """The game's cache entry, looked up now when missing; None without a key or when the lookup failed."""
        entry = self.art.get(game.rom_id, game.sgdb_id, game.name)
        if entry or not self.sgdb:
            return entry
        try:
            entry, fetched = await self.art.ensure(self.sgdb, game.rom_id, game.sgdb_id, game.name)
        except SgdbError as e:
            if e.status == 401:
                self.sgdb_error = "Invalid SteamGridDB key"
                self._changed()
            self.log.warning("SteamGridDB art for %s: %s", game.name, e.message)
            return None
        if fetched:
            self._changed()
        return entry

    async def game_art(self, rom_id: int) -> dict:
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        entry = await self._art_entry(game)
        urls = {k: (entry or {}).get(k, "") for k in ART_KINDS}
        sgdb_id = (entry or {}).get("sgdb_id") or game.sgdb_id
        return {"rom_id": game.rom_id, "sgdb_id": sgdb_id, **urls, "ready": self.sgdb is not None}

    async def art_base64(self, rom_id: int, kind: str) -> dict:
        if kind not in ART_KINDS:
            raise ValueError(f"Unknown art kind {kind!r}")
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        entry = await self._art_entry(game)
        if not entry or not entry.get(kind) or not entry.get("sgdb_id"):
            return {"base64": "", "format": ""}
        cached = self.art.image(entry["sgdb_id"], kind)
        if cached:
            data, fmt = cached
        else:
            client = self.sgdb or self._cdn
            if client is None:
                client = self._cdn = self._sgdb_client("")
            try:
                data, fmt = await client.fetch_image(entry[kind])
            except SgdbError as e:
                self.log.warning("SteamGridDB %s of %s: %s", kind, game.name, e.message)
                return {"base64": "", "format": ""}
            try:
                self.art.write_image(entry["sgdb_id"], kind, data, fmt)
            except OSError as e:
                self.log.warning("art cache not written: %s", e)
        return {"base64": base64.b64encode(data).decode(), "format": fmt}

    def _icon_path(self, rom_id: int) -> str:
        return os.path.join(self.runtime_dir, "icons", f"{int(rom_id)}.png") if self.runtime_dir else ""

    def save_icon(self, rom_id: int, data_base64: str) -> str:
        """Writes a shortcut icon drawn by the frontend; Steam takes a shortcut's icon only as a file path."""
        path = self._icon_path(rom_id)
        data = base64.b64decode(data_base64 or "", validate=True)
        if not path or not data.startswith(b"\x89PNG") or len(data) > 4 * 1024 * 1024:
            raise ValueError("Not a PNG icon")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        return path

    async def similar_games(self, rom_id: int) -> list[dict]:
        """Games in the library that resemble this one, from RomM's similarity graph."""
        if not self.client:
            return []
        out = []
        for r in await self.client.similar(int(rom_id)):
            sid = (r.get("rom") or {}).get("id")
            if sid in self.library.games:
                out.append({"rom_id": sid, "score": r.get("score", 0),
                            "reasons": [f"{x.get('facet', '')}: {x.get('value', '')}".strip(": ") for x in (r.get("reasons") or [])[:3]]})
        return out

    async def download(self, rom_id: int, appid: int = 0) -> dict:
        game = self.library.games.get(int(rom_id))
        if not game or not self.downloader:
            raise ValueError("Unknown game")
        if not self.location.exists:
            # Only our own folder is made: a chosen one that is missing is likely a drive that is not there.
            if self.location.roms_dir != self.default_roms_dir:
                raise ValueError(f"The ROM folder {self.location.roms_dir} does not exist")
            os.makedirs(self.location.roms_dir, exist_ok=True)
        if appid:
            self.shortcuts.set(game.rom_id, int(appid), game.name)
        self.downloader.add(game, self.shortcuts.appid(game.rom_id))
        emulator = self.emulator_for(game.slug)
        if emulator:
            # In the background: by the time the game is on the device, so is what its emulator needs.
            self._bios_task = asyncio.create_task(self._auto_bios(emulator, game.slug))
        self._changed()
        return self.state()

    async def set_shortcut(self, rom_id: int, appid: int) -> dict:
        """Records the game's Steam shortcut; appid 0 forgets one Steam no longer has."""
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        self.shortcuts.set(game.rom_id, int(appid), game.name)
        if self.downloader:
            self.downloader.add_appid(game.rom_id, int(appid))
        self._changed()
        return self.state()

    async def remove(self, rom_id: int) -> dict:
        """Deletes the game's files and its record, whatever state it is in; the frontend removes the Steam shortcut
        with the appid returned in `removed`."""
        rom_id = int(rom_id)
        install, game = self.ledger.get(rom_id), self.library.games.get(rom_id)
        if not install and not game:
            raise ValueError("Unknown game")
        if self.downloader:
            await self.downloader.drop(rom_id)
        target = self._target(install) if install else self.location.target(game.slug, game.fs_name, game.single_file)
        for path in (target.path, target.path + ".part"):
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)
        icon = self._icon_path(rom_id)
        if icon and os.path.exists(icon):
            os.unlink(icon)
        self.ledger.remove(rom_id)
        appid = self.shortcuts.forget(rom_id)
        self._changed()
        return {"removed": appid, **self.state()}

    def _rom_id_for(self, appid: int) -> int | None:
        return self.shortcuts.rom_id(int(appid))

    async def download_control(self, action: str, appid: int = 0, value: int = 0) -> dict:
        """Steam's Downloads page buttons: pause/resume/cancel one of ours, pause_all/resume_all, move/move_to, clear."""
        d = self.downloader
        if not d:
            return self.state()
        rom_id = self._rom_id_for(appid) if appid else None
        if action == "pause_all":
            await d.pause_all()
        elif action == "resume_all":
            await d.resume_all()
        elif action == "clear":
            d.clear()
        elif rom_id is not None:
            if action == "pause":
                await d.pause(rom_id)
            elif action == "resume":
                install = self.ledger.get(rom_id)
                if install and install.state in (L.INCOMPLETE, L.FAILED):
                    d.add(as_game(install), int(appid))  # Steam's Resume on a download that had stopped
                else:
                    await d.resume(rom_id)
            elif action == "cancel":
                await d.cancel(rom_id)
            elif action == "move":
                d.move(rom_id, int(value))
            elif action == "move_to":
                d.move_to(rom_id, int(value))
        self._changed()
        return self.state()

    async def cancel_download(self, rom_id: int) -> dict:
        if self.downloader:
            await self.downloader.cancel(int(rom_id))
        return self.state()

    async def set_roms_dir(self, path: str) -> dict:
        path = path.strip() or self.default_roms_dir
        self.location = InstallLocation(path, self.home)
        if self.downloader:
            self.downloader.location = self.location
        self.settings.roms_dir = path
        self.store.save(self.settings)
        self._changed()
        return self.state()
