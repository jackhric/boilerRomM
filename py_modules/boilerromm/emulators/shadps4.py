"""shadPS4 (PlayStation 4), run from the project's own AppImage: the build without a window of its own."""
import asyncio
import json
import os
import shutil
import tempfile
import zipfile

from ..games.install import Target, launch_file
from . import releases
from .base import Command, Emulator, Firmware
from .releases import Source

TAG = "v.0.21.0"
NIGHTLY = "Pre-release-shadPS4-"

# The first of shadPS4's four users, the one a controller is given. Unless its folder is there, shadPS4 stops at
# a desktop dialog asking whether to move the saves of an older version (UserManager::CreateDefaultUsers).
USER = "1000"
USER_FOLDERS = ("savedata", "trophy", "inputs")

# What a reset clears from the folder shadPS4 keeps everything in; the rest of it is the user's or a cache.
SETTINGS = ("config.json", "users.json", "input_config", "custom_configs")

# The first bytes of a system module as dumped from a console (a SELF file), or of one already decrypted (an ELF).
MODULE_MAGICS = (b"\x4f\x15\x3d\x1d", b"\x7fELF")

# A folder beside a game that shadPS4 lays over it (FileSys::BaseGameFromOverlay): never the game itself.
OVERLAYS = ("-UPDATE", "-patch", "-mods")

# shadPS4 takes a folder called "user" in the folder it is started from as its own, before it looks anywhere
# else, and a Steam shortcut starts in the ROM folder.
RUN_FROM = 'cd "$1" && shift && exec "$@"'


def _is_game_folder(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "eboot.bin"))


def _is_module(path: str) -> bool:
    if not path.lower().endswith(".sprx"):
        return False
    try:
        with open(path, "rb") as f:
            return f.read(4) in MODULE_MAGICS
    except OSError:
        return False


def _is_overlay(path: str) -> bool:
    return os.path.splitext(path)[0].endswith(OVERLAYS)


def _update_json(path: str, values: dict[str, dict]) -> None:
    """Sets keys in the sections of a JSON file, keeping everything else in it."""
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    for section, items in values.items():
        if not isinstance(config.get(section), dict):
            config[section] = {}
        config[section].update(items)
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".config-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class ShadPs4(Emulator):
    id = "shadps4"
    name = "shadPS4"
    system = "PlayStation 4"
    platforms = ("ps4",)
    requires = "PS4 system modules"
    source = Source("shadps4-emu/shadPS4", r"^shadps4-linux-sdl-.*\.zip$", TAG)

    def __init__(self, layout):
        super().__init__(layout)
        # shadPS4 has one folder for everything, under XDG_DATA_HOME, and no way to move its config out of it.
        self.config_dir = os.path.join(self.data_dir, "shadPS4")
        self.cache_dir = os.path.join(self.config_dir, "cache")

    @property
    def config(self) -> str:
        return os.path.join(self.config_dir, "config.json")

    def version_label(self, tag: str, title: str) -> str:
        if tag.startswith(NIGHTLY):
            return tag.removeprefix(NIGHTLY)[:len("2026-01-01-0000000")]
        return tag.removeprefix("v.")

    # Build
    async def install(self, session, tag: str = "") -> str:
        release = await releases.find(session, self.source, tag)
        archive = self.executable + ".zip"
        await releases.download(session, release, archive)
        try:
            await asyncio.to_thread(self._unpack, archive)
        finally:
            os.unlink(archive)
        with open(self.version_file, "w", encoding="utf-8") as f:
            f.write(f"{release.tag}\n{self.version_label(release.tag, release.title)}")
        return release.tag

    def _unpack(self, archive: str) -> None:
        part = self.executable + ".part"
        try:
            with zipfile.ZipFile(archive) as z:
                name = next((n for n in z.namelist() if n.endswith(".AppImage")), None)
                if name is None:
                    raise releases.ReleaseError(f"{os.path.basename(archive)}: the archive holds no AppImage")
                with z.open(name) as src, open(part, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            os.chmod(part, 0o755)
            os.replace(part, self.executable)
        except zipfile.BadZipFile as e:
            raise releases.ReleaseError(f"{os.path.basename(archive)}: the download is damaged") from e
        finally:
            try:
                os.unlink(part)
            except OSError:
                pass

    # Firmware
    # shadPS4 has no checksums to go by: it loads any of the *.sprx it knows by name, so a file is recognised by its header.
    # No module is needed to boot (it falls back to its own versions), but its README calls them required to run games properly.
    def firmware_found(self) -> list[Firmware]:
        folder = self.layout.bios("ps4")
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return []
        return [Firmware("ps4", name, "") for name in names if _is_module(os.path.join(folder, name))]

    def bios_platforms(self) -> tuple[str, ...]:
        return ("ps4",)

    def firmware_ready(self) -> bool:
        return bool(self.firmware_found())

    def add_firmware(self, path: str) -> Firmware | None:
        if not _is_module(path):
            return None
        name = os.path.basename(path)
        folder = self.layout.bios("ps4")
        os.makedirs(folder, exist_ok=True)
        shutil.copyfile(path, os.path.join(folder, name))
        return Firmware("ps4", name, "")

    # Config
    def configure(self) -> None:
        home = self.layout.saves("ps4", self.id)
        for name in USER_FOLDERS:
            os.makedirs(os.path.join(home, USER, name), exist_ok=True)
        # System modules (*.sprx) and the font and font2 folders dumped from a console are all looked for here.
        firmware = self.layout.bios("ps4")
        _update_json(self.config, {"General": {"home_dir": home, "sys_modules_dir": firmware, "font_dir": firmware}})

    def reset_config(self) -> None:
        for name in SETTINGS:
            path = os.path.join(self.config_dir, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        self.prepare()

    # Launch
    def launch_file(self, target: Target) -> str:
        """An unpacked game is launched as the folder holding its eboot.bin, wherever below the download that is."""
        if target.is_dir:
            try:
                inner = sorted(os.path.join(target.path, n) for n in os.listdir(target.path))
            except OSError:
                inner = []
            inner.sort(key=_is_overlay)
            for folder in (target.path, *inner):
                if _is_game_folder(folder):
                    return folder
            for path in inner:
                if path.endswith(".zar") and os.path.isfile(path):
                    return path
        return launch_file(target)

    def command(self, rom: str, platform: str = "") -> Command:
        return Command(["/bin/sh", "-c", RUN_FROM, "sh", self.home, self.executable, "--fullscreen", "true", "--game", rom], self.env())
