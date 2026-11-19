"""RPCS3 (PlayStation 3), run from the project's own AppImage."""
import json
import os
import re
import shutil
from typing import Any

from ..games.install import Target, launch_file
from . import inifile
from .base import Command, Emulator, Firmware
from .releases import Source

# RPCS3 publishes one release per commit, tagged with the commit. This one is 0.0.43-20623.
TAG = "build-0ebb63697666a54b44a4de69ef222c4ecee0001a"

# Every device is given its own path: on start RPCS3 resolves some of them before it has read $(EmulatorDir)
# from vfs.yml, so that key alone leaves dev_hdd0 in the config folder. It also refuses a device whose folder
# is missing, firmware install included.
DEVICES = ("dev_hdd0", "dev_hdd1", "dev_flash", "dev_flash2", "dev_flash3", "dev_bdvd", "games")
USER = "00000001"
FIRMWARE_TIMEOUT_S = 20 * 60
PUP_NAME = "PS3UPDAT.PUP"
PUP_MAGIC = b"SCEUF\0\0\0"
# Where RPCS3 looks for the executable of a game folder (Emulator::GetElfPathFromDir).
BOOT_FILES = ("EBOOT.BIN", "USRDIR/EBOOT.BIN", "USRDIR/ISO.BIN.EDAT", "PS3_GAME/USRDIR/EBOOT.BIN")

# The exit status of a headless install is not zero even when it works, so the game is started either way.
INSTALL_THEN_RUN = '[ -e "$1" ] || [ ! -e "$2" ] || "$0" --headless --installfw "$2"; exec "$0" --no-gui --fullscreen "$3"'


def _is_pup(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(len(PUP_MAGIC)) == PUP_MAGIC
    except OSError:
        return False


def _is_game_folder(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, name)) for name in BOOT_FILES)


def _set_top_level(path: str, values: dict[str, str]) -> None:
    """Sets `key: value` lines of a YAML file whose top level is a plain map, keeping its other lines."""
    try:
        with open(path, encoding="utf-8") as f:
            kept = [line for line in f.read().splitlines() if line.split(":", 1)[0] not in values]
    except OSError:
        kept = []
    # A JSON string is a YAML double-quoted scalar.
    lines = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in values.items()]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines + kept) + "\n")
    os.replace(tmp, path)


def _link(link: str, target: str) -> None:
    """Makes `link` a symlink to `target`, moving in whatever the emulator had already put in a folder there."""
    if os.path.islink(link):
        if os.readlink(link) == target:
            return
        os.unlink(link)
    elif os.path.isdir(link):
        for name in os.listdir(link):
            if not os.path.lexists(os.path.join(target, name)):
                shutil.move(os.path.join(link, name), os.path.join(target, name))
        try:
            os.rmdir(link)
        except OSError:
            os.replace(link, link + ".old")
    os.makedirs(os.path.dirname(link), exist_ok=True)
    os.symlink(target, link)


class Rpcs3(Emulator):
    year = 2006
    accepts = ".PUP"

    id = "rpcs3"
    name = "RPCS3"
    system = "PlayStation 3"
    platforms = ("ps3",)
    requires = "PS3 firmware"
    # Each build is its own release, tagged with the commit, and the list does not come newest first: only the
    # latest can be offered, and it is known by the release's title ("0.0.43-20623").
    recent_versions = 0
    source = Source("RPCS3/rpcs3-binaries-linux", r"_linux64\.AppImage$", TAG)

    def version_label(self, tag: str, title: str) -> str:
        return title or tag.removeprefix("build-")[:8]

    @property
    def settings_dir(self) -> str:
        return os.path.join(self.config_dir, "rpcs3")

    @property
    def gui_ini(self) -> str:
        return os.path.join(self.settings_dir, "GuiConfigs", "CurrentSettings.ini")

    @property
    def vfs(self) -> str:
        return os.path.join(self.settings_dir, "vfs.yml")

    def device(self, name: str) -> str:
        return os.path.join(self.data_dir, name)

    @property
    def firmware_version_file(self) -> str:
        return os.path.join(self.device("dev_flash"), "vsh", "etc", "version.txt")

    # Firmware
    # Any PS3UPDAT.PUP will do and Sony replaces it now and then, so it is recognised by its header, not a checksum.
    # RPCS3 does not read the file when it runs a game: it unpacks it into dev_flash once.
    def firmware_found(self) -> list[Firmware]:
        folder = self.layout.bios("ps3")
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return []
        return [Firmware("ps3", name, "") for name in names if _is_pup(os.path.join(folder, name))]

    def expected_files(self, platform: str) -> str:
        return PUP_NAME

    def compatible(self, entry: dict[str, Any]) -> bool:
        return str(entry.get("file_name", "")).lower().endswith(".pup")

    def firmware_label(self) -> str:
        version = self.firmware_version
        return f"{PUP_NAME} ({version})" if version else PUP_NAME if self.firmware_found() else ""

    def remove_firmware(self) -> None:
        for f in self.firmware_found():
            os.unlink(os.path.join(self.layout.bios("ps3"), f.name))
        shutil.rmtree(self.device("dev_flash"), ignore_errors=True)
        os.makedirs(self.device("dev_flash"), exist_ok=True)

    @property
    def firmware_installed(self) -> bool:
        return os.path.isfile(self.firmware_version_file)

    def bios_platforms(self) -> tuple[str, ...]:
        return ("ps3",)

    def platform_ready(self, platform: str) -> bool:
        return self.firmware_ready()

    def firmware_ready(self) -> bool:
        return self.firmware_installed or bool(self.firmware_found())

    def add_firmware(self, path: str) -> Firmware | None:
        if not _is_pup(path):
            return None
        folder = self.layout.bios("ps3")
        os.makedirs(folder, exist_ok=True)
        shutil.copyfile(path, os.path.join(folder, PUP_NAME))
        return Firmware("ps3", PUP_NAME, "")

    async def install_firmware(self) -> None:
        """Unpacks the PUP into dev_flash with RPCS3 itself, which needs no window for it."""
        found = self.firmware_found()
        if self.firmware_installed or not found or not self.version:
            return
        self.prepare()
        await self.run("--headless", "--installfw", os.path.join(self.layout.bios("ps3"), found[0].name), timeout=FIRMWARE_TIMEOUT_S)
        # RPCS3 ends with the same status whether it worked or not.
        if not self.firmware_installed:
            raise RuntimeError("RPCS3 could not install the PS3 firmware")

    @property
    def firmware_version(self) -> str:
        """The installed firmware, e.g. "4.93"; "" when none is."""
        try:
            with open(self.firmware_version_file, encoding="utf-8") as f:
                release = re.search(r"release:(\d+)\.(\d\d)", f.read())
        except OSError:
            return ""
        return f"{int(release.group(1))}.{release.group(2)}" if release else ""

    # Config
    def configure(self) -> None:
        for name in DEVICES:
            os.makedirs(self.device(name), exist_ok=True)
        _set_top_level(self.vfs, {f"/{name}/": self.device(name) + "/" for name in DEVICES})
        # RPCS3 has no setting for either folder.
        _link(os.path.join(self.device("dev_hdd0"), "home", USER, "savedata"), self.layout.saves("ps3", self.id))
        _link(os.path.join(self.settings_dir, "savestates"), self.layout.states("ps3", self.id))
        inifile.update(
            self.gui_ini,
            values={"main_window": {"infoBoxEnabledWelcome": "false"}},
            defaults={"main_window": {"confirmationBoxExitGame": "false"}, "Meta": {"checkUpdateStart": "false"}},
        )

    # Launch
    def launch_file(self, target: Target) -> str:
        """A disc or PSN game folder is launched as the folder, wherever below the download it starts."""
        if target.is_dir:
            inner: list[str] = []
            try:
                inner = sorted(os.path.join(target.path, n) for n in os.listdir(target.path))
            except OSError:
                pass
            for folder in (target.path, *inner):
                if _is_game_folder(folder):
                    return folder
        return launch_file(target)

    def command(self, rom: str, platform: str = "") -> Command:
        if self.firmware_installed:
            return Command([self.executable, "--no-gui", "--fullscreen", rom], self.env())
        found = self.firmware_found()
        pup = os.path.join(self.layout.bios("ps3"), found[0].name if found else PUP_NAME)
        return Command(["/bin/sh", "-c", INSTALL_THEN_RUN, self.executable, self.firmware_version_file, pup, rom], self.env())
