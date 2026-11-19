"""KytyPS5 (PlayStation 5), run from the project's own Linux build."""
import asyncio
import gzip
import os
import shutil
import tarfile
import zlib

from ..games.install import Target, launch_file
from . import releases
from .base import Command, Emulator
from .releases import Source
from .rpcs3 import _link

# KytyPS5 publishes a release per commit to main, several a day, tagged with the day and the commit; not every one
# has a Linux build. Its options exist only on the command line, and an unknown one aborts the start: check
# PrintUsage and ParseArgs in src/main.cpp when moving the tag.
TAG = "KytyPS5-2026-11-18-a90be8d"

# The archive also holds the project's Qt launcher and its updater. Only the emulator is taken out, with the
# fonts, sounds and cursors it looks for beside itself.
BINARY = "kyty_emulator"
ASSETS = "assets/"
BOOT_FILE = "eboot.bin"
DUMP = ".zar"
SEARCH_DEPTH = 3

# KytyPS5 has no data folder: _SaveData, _PipelineCache, _DownloadData and _TempData go under whatever folder it is
# started in.
RUN = 'cd "$1" && shift && exec "$0" "$@"'


def _game_in(folder: str) -> str:
    """The game a folder holds itself: the folder when it has an eboot.bin, or a ZArchive dump in it."""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return ""
    if any(n.lower() == BOOT_FILE and os.path.isfile(os.path.join(folder, n)) for n in names):
        return folder
    return next((os.path.join(folder, n) for n in names if n.lower().endswith(DUMP)), "")


class Kyty(Emulator):
    year = 2020

    id = "kyty"
    name = "KytyPS5"
    system = "PlayStation 5"
    platforms = ("ps5",)
    source = Source("KytyPS5/KytyPS5", r"-Linux-x86_64\.tar\.gz$", TAG)

    def __init__(self, layout):
        super().__init__(layout)
        self.build_dir = os.path.join(self.home, "build")
        self.executable = os.path.join(self.build_dir, BINARY)

    def version_label(self, tag: str, title: str) -> str:
        return tag.removeprefix("KytyPS5-")

    # Build
    async def install(self, session, tag: str = "") -> str:
        release = await releases.find(session, self.source, tag)
        archive = os.path.join(self.cache_dir, "kyty.tar.gz")
        await releases.download(session, release, archive)
        try:
            await asyncio.to_thread(self._unpack, archive)
        finally:
            os.unlink(archive)
        with open(self.version_file, "w", encoding="utf-8") as f:
            f.write(f"{release.tag}\n{self.version_label(release.tag, release.title)}")
        return release.tag

    def _unpack(self, archive: str) -> None:
        part = self.build_dir + ".part"
        shutil.rmtree(part, ignore_errors=True)
        try:
            with tarfile.open(archive, "r:gz") as tar:
                for member in tar:
                    name = os.path.normpath(member.name)
                    if not member.isfile() or not (name == BINARY or name.startswith(ASSETS)):
                        continue
                    path = os.path.join(part, name)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with tar.extractfile(member) as source, open(path, "wb") as f:
                        shutil.copyfileobj(source, f)
            if not os.path.isfile(os.path.join(part, BINARY)):
                raise releases.ReleaseError(f"KytyPS5: the archive holds no {BINARY}")
            os.chmod(os.path.join(part, BINARY), 0o755)
            shutil.rmtree(self.build_dir, ignore_errors=True)
            os.replace(part, self.build_dir)
        except (tarfile.TarError, EOFError, zlib.error, gzip.BadGzipFile) as e:
            raise releases.ReleaseError("KytyPS5: the download is damaged") from e
        finally:
            shutil.rmtree(part, ignore_errors=True)

    def uninstall(self, keep_settings: bool = True) -> None:
        super().uninstall(keep_settings)
        shutil.rmtree(self.build_dir, ignore_errors=True)

    # Config
    def configure(self) -> None:
        # There is no config file and no setting for either folder.
        pipelines = os.path.join(self.cache_dir, "pipelines")
        os.makedirs(pipelines, exist_ok=True)
        _link(os.path.join(self.data_dir, "_SaveData"), self.layout.saves("ps5", self.id))
        _link(os.path.join(self.data_dir, "_PipelineCache"), pipelines)

    # Launch
    def launch_file(self, target: Target) -> str:
        """A game is a folder with an eboot.bin or a ZArchive dump of one, wherever below the download it is."""
        if not target.is_dir:
            return target.path
        level = [target.path]
        for _ in range(SEARCH_DEPTH):
            below = []
            for folder in level:
                game = _game_in(folder)
                if game:
                    return game
                try:
                    below += sorted(e.path for e in os.scandir(folder) if e.is_dir())
                except OSError:
                    pass
            level = below
        return launch_file(target)

    def command(self, rom: str, platform: str = "") -> Command:
        return Command(["/bin/sh", "-c", RUN, self.executable, self.data_dir,
                        "--game", rom, "--fullscreen", "--hide-cursor", "--shader-cache"], self.env())
