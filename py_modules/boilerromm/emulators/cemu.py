"""Cemu (Wii U), run from the project's own AppImage."""
import os
import re
import shutil

from ..games.install import Target
from . import xmlfile
from .base import Command, Emulator, Firmware, link_dir
from .releases import Source

# Cemu starts its Getting Started dialog while there is no settings.xml, and only reads the keys below from it.
# The tag and the settings are pinned together: check CemuConfig::Load in src/config/CemuConfig.cpp when moving the tag.
TAG = "v2.6"

# Where a key is missing from settings.xml, Cemu reads another value than the one it saves for a new install.
DEFAULTS = {
    "fullscreen": "true",
    "check_update": "false",
    "use_discord_presence": "false",
    "vk_warning": "true",
    "gp_download": "true",
    "Graphic/api": "1",  # Vulkan; OpenGL when absent
    "Graphic/device": "0" * 32,
    "Audio/api": "3",  # Cubeb, the only one on Linux
    "Audio/TVVolume": "100",
    "Audio/TVDevice": "default",
}

# The Steam Virtual Gamepad, which Steam Input presents in place of the real controller: its SDL GUID, as RetroDECK has it.
PAD_UUID = "0_030079f6de280000ff11000001000000"
PAD_NAME = "Steam Virtual Gamepad"
# Wii U GamePad input to SDL button or axis number. A and B, X and Y sit where they are on the GamePad, not
# where the letters are on an Xbox pad; the microphone blows into R3.
PAD_MAPPINGS = {1: 1, 2: 0, 3: 3, 4: 2, 5: 9, 6: 10, 7: 42, 8: 43, 9: 6, 10: 4, 11: 11, 12: 12, 13: 13, 14: 14, 15: 7, 16: 8,
                17: 45, 18: 39, 19: 44, 20: 38, 21: 47, 22: 41, 23: 46, 24: 40, 25: 8}

# keys.txt holds one 128-bit disc key per line, as 32 hex digits; Cemu writes this one into the file it makes itself.
EXAMPLE_KEY = "541b9889519b27d363cd21604b97c67a"
KEYS = "keys.txt"


def is_keys_file(path: str) -> bool:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.read(1 << 20).splitlines()
    except OSError:
        return False
    for line in lines:
        key = re.sub(r"[ \t_-]", "", re.split(r"[#;]", line, maxsplit=1)[0]).lower()
        if re.fullmatch(r"[0-9a-f]{32}", key) and key != EXAMPLE_KEY:
            return True
    return False


def _profile() -> str:
    entries = "".join(f"<entry><mapping>{m}</mapping><button>{b}</button></entry>" for m, b in PAD_MAPPINGS.items())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<emulated_controller><type>Wii U GamePad</type><profile>boilerRomM</profile>'
        f"<controller><api>SDLController</api><uuid>{PAD_UUID}</uuid><display_name>{PAD_NAME}</display_name><rumble>0</rumble>"
        "<axis><deadzone>0.25</deadzone><range>1</range></axis><rotation><deadzone>0.25</deadzone><range>1</range></rotation>"
        f"<trigger><deadzone>0.25</deadzone><range>1</range></trigger><mappings>{entries}</mappings></controller></emulated_controller>\n"
    )


class Cemu(Emulator):
    id = "cemu"
    name = "Cemu"
    system = "Wii U"
    platforms = ("wiiu",)
    requires = "a keys.txt for WUD and WUX disc images"
    source = Source("cemu-project/Cemu", r"-x86_64\.AppImage$", TAG)

    @property
    def settings(self) -> str:
        return os.path.join(self.config_dir, "Cemu", "settings.xml")

    @property
    def profile(self) -> str:
        return os.path.join(self.config_dir, "Cemu", "controllerProfiles", "controller0.xml")

    @property
    def mlc(self) -> str:
        return os.path.join(self.data_dir, "mlc01")

    @property
    def keys(self) -> str:
        return os.path.join(self.layout.bios("wiiu"), KEYS)

    @property
    def keys_in_use(self) -> str:
        return os.path.join(self.data_dir, "Cemu", KEYS)

    def configure(self) -> None:
        # Cemu keeps its save data, and the accounts and Miis in it, in the mlc folder, which is a setting of its own.
        link_dir(os.path.join(self.mlc, "usr", "save"), self.layout.saves("wiiu", self.id))
        xmlfile.update(self.settings, "content", values={"mlc_path": self.mlc}, defaults=DEFAULTS)
        if not os.path.exists(self.profile):
            os.makedirs(os.path.dirname(self.profile), exist_ok=True)
            with open(self.profile, "w", encoding="utf-8") as f:
                f.write(_profile())
        if is_keys_file(self.keys):
            os.makedirs(os.path.dirname(self.keys_in_use), exist_ok=True)
            shutil.copyfile(self.keys, self.keys_in_use)

    def launch_file(self, target: Target) -> str:
        # A game folder is launched as it is, when it is one Cemu recognises; elsewhere Cemu wants the file.
        if target.is_dir and all(os.path.isdir(os.path.join(target.path, name)) for name in ("code", "content", "meta")):
            return target.path
        tmd = os.path.join(target.path, "title.tmd")
        return tmd if target.is_dir and os.path.isfile(tmd) else super().launch_file(target)

    # Keys
    # Only WUD and WUX images need them: WUA archives, game folders and installed titles do not, so this never blocks a launch.
    def firmware_found(self) -> list[Firmware]:
        return [Firmware("wiiu", KEYS, "")] if is_keys_file(self.keys) or is_keys_file(self.keys_in_use) else []

    def bios_platforms(self) -> tuple[str, ...]:
        return ("wiiu",)

    def platform_ready(self, platform: str) -> bool:
        return True

    def firmware_ready(self) -> bool:
        return True

    def bios_status(self) -> list[dict]:
        found = self.firmware_found()
        return [{"platform": "wiiu", "folder": self.layout.bios("wiiu"), "found": [f.name for f in found], "ready": bool(found)}]

    def add_firmware(self, path: str) -> Firmware | None:
        if not is_keys_file(path):
            return None
        os.makedirs(os.path.dirname(self.keys), exist_ok=True)
        shutil.copyfile(path, self.keys)
        return Firmware("wiiu", KEYS, "")

    def command(self, rom: str, platform: str = "") -> Command:
        return Command([self.executable, "-f", "-g", rom], self.env())
