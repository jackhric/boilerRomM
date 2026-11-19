"""Lichii (Nintendo Switch and Switch 2), run from the project's own AppImage."""
import os
import re
import shutil

from . import inifile
from .base import Command, Emulator, Firmware
from .releases import Source

# Lichii seeds a few renderer settings only when it creates qt-config.ini itself (Config::SetUpIni in
# src/frontend_common/config.cpp). configure() writes the file first, so SEEDED repeats them: check both when
# moving the tag.
TAG = "build-341"
SEEDED = {"scaling_filter": "15", "gpu_accuracy": "0", "nvdec_emulation": "2", "async_presentation": "true"}

KEYS = "prod.keys"
# The one key every encrypted game needs (KeyManager::BaseDeriveNecessary). Key files differ from console to
# console and firmware to firmware, so there is no checksum to know them by.
HEADER_KEY = re.compile(rb"^\s*header_key\s*=\s*[0-9a-fA-F]{64}\s*$", re.MULTILINE)


def is_keys_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return bool(HEADER_KEY.search(f.read(1 << 20)))
    except OSError:
        return False


def _set(items: dict[str, str]) -> dict[str, str]:
    # A value is only read when its "\default" twin says it is not the default.
    return {k: v for key, value in items.items() for k, v in ((f"{key}\\default", "false"), (key, value))}


class Lichii(Emulator):
    id = "lichii"
    name = "Lichii"
    system = "Nintendo Switch and Switch 2"
    platforms = ("switch2", "switch")
    requires = "keys"
    source = Source("zortos293/Lichii", r"linux-x86_64\.AppImage$", TAG)

    @property
    def ini(self) -> str:
        return os.path.join(self.config_dir, "lichii", "qt-config.ini")

    @property
    def keys_dir(self) -> str:
        return os.path.join(self.data_dir, "lichii", "keys")

    @property
    def keys(self) -> str:
        return os.path.join(self.layout.bios("switch"), KEYS)

    def configure(self) -> None:
        self._link_keys()
        inifile.update(
            self.ini,
            values={"Data Storage": _set({"save_directory": self.layout.saves("switch", self.id)})},
            defaults={
                "UI": _set({
                    "check_for_updates": "false",  # a build older than the latest asks to update at every start
                    "confirmStop": "2",  # never ask: the question would block Steam closing the game
                    "show_whats_new": "false",
                    "gui_hide_backend_warning": "true",
                }),
                "Renderer": _set(SEEDED),
            },
        )

    def _link_keys(self) -> None:
        # Lichii has no setting for its keys folder, so the folder becomes a link to the shared one. A folder
        # the user already filled is left alone.
        target = self.layout.bios("switch")
        os.makedirs(target, exist_ok=True)
        link = self.keys_dir
        if os.path.islink(link):
            if os.readlink(link) == target:
                return
            os.unlink(link)
        elif os.path.isdir(link):
            try:
                os.rmdir(link)
            except OSError:
                return
        os.makedirs(os.path.dirname(link), exist_ok=True)
        os.symlink(target, link)

    def firmware_found(self) -> list[Firmware]:
        paths = (self.keys, os.path.join(self.keys_dir, KEYS))
        return [Firmware("switch", KEYS, "")] if any(is_keys_file(p) for p in paths) else []

    def bios_platforms(self) -> tuple[str, ...]:
        return ("switch",)

    def firmware_ready(self) -> bool:
        return bool(self.firmware_found())

    def add_firmware(self, path: str) -> Firmware | None:
        if not is_keys_file(path):
            return None
        os.makedirs(os.path.dirname(self.keys), exist_ok=True)
        shutil.copyfile(path, self.keys)
        return Firmware("switch", KEYS, "")

    def command(self, rom: str, platform: str = "") -> Command:
        return Command([self.executable, "-f", "-g", rom], self.env())
