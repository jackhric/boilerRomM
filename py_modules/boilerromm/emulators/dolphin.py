"""Dolphin (GameCube and Wii), run from pkgforge-dev's AppImage: the Dolphin project publishes none of its own."""
import os

from .. import inifile
from ..releases import Source
from .base import Command, Emulator

# pkgforge-dev builds each Dolphin release again every three weeks, with newer libraries, and tags every build
# "<Dolphin version>@<build date>_<build time>".
TAG = "2609a@2026-11-01_1793557796"


def _link(link: str, target: str) -> None:
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
            return  # Dolphin already keeps files here: they stay where they work
    os.symlink(target, link)


class Dolphin(Emulator):
    id = "dolphin"
    name = "Dolphin"
    system = "GameCube and Wii"
    platforms = ("ngc", "wii")
    source = Source("pkgforge-dev/Dolphin-emu-AppImage", r"-anylinux-x86_64\.AppImage$", TAG)
    recent_versions = 0  # they would mostly be older builds of the same Dolphin version

    def __init__(self, layout):
        super().__init__(layout)
        # Dolphin follows the XDG folders only while there is no ~/.dolphin-emu and no ./user, so it is given one
        # user folder with -u instead, and keeps its config and cache inside it.
        self.config_dir = os.path.join(self.data_dir, "Config")
        self.cache_dir = os.path.join(self.data_dir, "Cache")

    @property
    def ini(self) -> str:
        return os.path.join(self.config_dir, "Dolphin.ini")

    def version_label(self, tag: str, title: str) -> str:
        return tag.split("@")[0]

    def configure(self) -> None:
        # Dolphin has no setting for its save state folder, and keeps the states of both consoles in it.
        _link(os.path.join(self.data_dir, "StateSaves"), self.layout.states("ngc", self.id))
        memory_cards = self.layout.saves("ngc", self.id)
        inifile.update(
            self.ini,
            values={
                # Dolphin adds the game's region to both: a USA folder, a MemoryCardA.USA.raw file.
                "Core": {"GCIFolderAPath": memory_cards, "MemcardAPath": os.path.join(memory_cards, "MemoryCardA.raw")},
                "General": {"NANDRootPath": self.layout.saves("wii", self.id)},
            },
            defaults={
                "Analytics": {"PermissionAsked": "True"},
                "Interface": {"ConfirmStop": "False"},
            },
        )

    def env(self) -> dict[str, str]:
        # The AppImage's own launcher asks to check for updates, in a desktop dialog, from its second start on.
        return {**super().env(), "DISABLE_AUTO_UPDATES": "1"}

    def command(self, rom: str, platform: str = "") -> Command:
        return Command([self.executable, "-u", self.data_dir, "-b", "-C", "Dolphin.Display.Fullscreen=True", "-e", rom], self.env())
