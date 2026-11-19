"""The one object main.py builds: settings, the RomM client, pairing, the library and downloads.

Every change ends in `emit(STATE_EVENT, state)`, so the panel and the library page only render the latest snapshot;
download progress goes out separately as `PROGRESS_EVENT` a couple of times a second.
"""
import asyncio
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from . import emulators
from .emulators.commands import EmulatorCommands
from .games.commands import GameCommands
from .games.downloads import Downloader, Job
from .games.install import ROMS_FOLDER, InstallLocation
from .games.ledger import Ledger
from .games.shortcuts import ShortcutMap
from .games.video import VideoResolver
from .romm.client import RommClient, ssl_context
from .romm.commands import ServerCommands, device_identity
from .romm.library import Library
from .romm.pairing import DevicePairing
from .settings import Settings, SettingsStore
from .sgdb.artwork import ArtCache, ArtPrefetch
from .sgdb.client import SgdbClient
from .sgdb.commands import ArtworkCommands
from .sgdb.signin import SgdbSignin

STATE_EVENT = "boilerromm_state"
PROGRESS_EVENT = "boilerromm_progress"

class App(ServerCommands, GameCommands, EmulatorCommands, ArtworkCommands):
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

    async def finish_setup(self) -> dict:
        self.settings.setup_done = True
        self.store.save(self.settings)
        self._changed()
        return self.state()

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
