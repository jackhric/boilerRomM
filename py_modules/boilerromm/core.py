"""What the command groups share: the objects `App` builds, declared once so each group is checked against them."""
import asyncio
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

from .emulators import Emulator
from .games.downloads import Downloader
from .games.install import ROMS_FOLDER, InstallLocation
from .games.ledger import Ledger
from .games.shortcuts import ShortcutMap
from .games.video import VideoResolver
from .romm.client import RommClient
from .romm.library import Library
from .romm.pairing import DevicePairing
from .settings import Settings, SettingsStore
from .sgdb.artwork import ArtCache, ArtPrefetch
from .sgdb.client import SgdbClient
from .sgdb.signin import SgdbSignin

STATE_EVENT = "boilerromm_state"
PROGRESS_EVENT = "boilerromm_progress"


class Core(ABC):
    store: SettingsStore
    settings: Settings
    version: str
    home: str
    identity: dict[str, str]
    log: logging.Logger
    client: RommClient | None
    pairing: DevicePairing | None
    server: dict[str, Any]
    library: Library
    videos: VideoResolver
    shortcuts: ShortcutMap
    ledger: Ledger
    launcher: str
    runtime_dir: str
    data_dir: str
    location: InstallLocation
    emulators: dict[str, Emulator]
    downloader: Downloader | None
    art: ArtCache
    sgdb: SgdbClient | None
    sgdb_error: str
    prefetch: ArtPrefetch
    signin: SgdbSignin
    _emit: Callable[..., Coroutine[Any, Any, None]]
    _emulator_busy: dict[str, str]
    _emulator_error: dict[str, str]
    _emulator_versions: dict[str, tuple[float, list[dict[str, Any]]]]
    _emulator_progress: dict[str, tuple[int, int]]
    _bios_fetching: set[str]
    _progress_sent: float
    _install_all: asyncio.Task[None] | None
    _refresh_task: asyncio.Task[None] | None
    _release_session: Callable[[], Any]
    _sgdb_session: Callable[[], Any]
    _cdn: SgdbClient | None

    @abstractmethod
    def state(self) -> dict[str, Any]: ...

    @abstractmethod
    def _start_paired(self) -> None: ...

    def _changed(self) -> None:
        asyncio.get_event_loop().create_task(self._emit(STATE_EVENT, self.state()))

    def _progress(self, progress: dict[str, Any]) -> None:
        asyncio.get_event_loop().create_task(self._emit(PROGRESS_EVENT, progress))

    @property
    def default_roms_dir(self) -> str:
        return os.path.join(self.data_dir, ROMS_FOLDER)
