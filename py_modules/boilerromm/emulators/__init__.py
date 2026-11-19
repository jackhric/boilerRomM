from .base import Command, Emulator, Firmware, Layout
from .cemu import Cemu
from .dolphin import Dolphin
from .kyty import Kyty
from .lichii import Lichii
from .pcsx2 import Pcsx2
from .retroarch import RetroArch
from .rpcs3 import Rpcs3
from .shadps4 import ShadPs4
from .xenia import Xenia

# In the order the settings page lists them.
ALL: tuple[type[Emulator], ...] = (RetroArch, Pcsx2, Dolphin, Cemu, Rpcs3, ShadPs4, Kyty, Xenia, Lichii)


def for_platform(platform: str, layout: Layout) -> Emulator | None:
    """The emulator that runs a RomM platform's games; None when boilerRomM has none for it."""
    for cls in ALL:
        if platform in cls.platforms:
            return cls(layout)
    return None


__all__ = ["ALL", "Cemu", "Command", "Dolphin", "Emulator", "Firmware", "Kyty", "Layout", "Lichii", "Pcsx2", "RetroArch", "Rpcs3", "ShadPs4", "Xenia", "for_platform"]
