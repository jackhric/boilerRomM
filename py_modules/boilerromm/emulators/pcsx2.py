"""PCSX2 (PlayStation 2), run from the project's own AppImage."""
import os

from .. import inifile
from ..releases import Source
from .base import Command, Emulator, Firmware

# PCSX2 shows its setup wizard, or asks to reset everything, unless the config carries the settings version this
# build expects. The two are pinned together: check SETTINGS_VERSION in pcsx2/VMManager.cpp when moving the tag.
TAG = "v2.8.2"
SETTINGS_VERSION = "1"

# File names and checksums as listed by RetroDECK's PCSX2 component.
BIOS = (
    ("ps2-0100j-20000117.bin", "acf4730ceb38ac9d8c7d8e21f2614600"),
    ("ps2-0101j-20000217.bin", "b1459d7446c69e3e97e6ace3ae23dd1c"),
    ("ps2-0120j-20001027-185015.bin", "f63bc530bd7ad7c026fcd6f7bd0d9525"),
    ("ps2-0120j-20001027-191435.bin", "cee06bd68c333fc5768244eae77e4495"),
    ("ps2-0150j-20010118.bin", "815ac991d8bc3b364696bead3457de7d"),
    ("ps2-0160j-20010427.bin", "ab55cceea548303c22c72570cfd4dd71"),
    ("ps2-0170j-20030206.bin", "312ad4816c232a9606e56f946bc0678a"),
    ("ps2-0200j-20040614.bin", "0eee5d1c779aa50e94edd168b4ebf42e"),
    ("ps2-0210j-20040917.bin", "1ad977bb539fc9448a08ab276a836bbc"),
    ("ps2-0210j-20040917.bin", "1ad977bb539fc9448a08ab276a836bbc"),
    ("ps2-0110a-20000727.bin", "a20c97c02210f16678ca3010127caf36"),
    ("ps2-0120a-20000902.bin", "8db2fbbac7413bf3e7154c1e0715e565"),
    ("ps2-0150a-20001228.bin", "8accc3c49ac45f5ae2c5db0adc854633"),
    ("ps2-0160a-20010427.bin", "b107b5710042abe887c0f6175f6e94bb"),
    ("ps2-0160a-20011004.bin", "7200a03d51cacc4c14fcdfdbc4898431"),
    ("ps2-0160a-20020207.bin", "d5ce2c7d119f563ce04bc04dbc3a323e"),
    ("ps2-0170a-20030325.bin", "8aa12ce243210128c5074552d3b86251"),
    ("ps2-0190a-20030623.bin", "35461cecaa51712b300b2d6798825048"),
    ("ps2-0200a-20040614.bin", "d333558cc14561c1fdc334c75d5f37b7"),
    ("ps2-0220a-20050620.bin", "929a14baca1776b00869f983aa6e14d2"),
    ("ps2-0220a-20060210.bin", "cb801b7920a7d536ba07b6534d2433ca"),
    ("ps2-0220a-20060905.bin", "40c11c063b3b9409aa5e4058e984e30c"),
    ("ps2-0230a-20080220.bin", "21038400dc633070a78ad53090c53017"),
    ("ps2-0120e-20000902.bin", "b7fa11e87d51752a98b38e3e691cbf17"),
    ("ps2-0150e-20001228.bin", "838544f12de9b0abc90811279ee223c8"),
    ("ps2-0160e-20010704.bin", "491209dd815ceee9de02dbbc408c06d6"),
    ("ps2-0160e-20011004.bin", "8359638e857c8bc18c3c18ac17d9cc3c"),
    ("ps2-0160e-20020319.bin", "0d2228e6fd4fb639c9c39d077a9ec10c"),
    ("ps2-0170e-20030227.bin", "6e69920fa6eef8522a1d688a11e41bc6"),
    ("ps2-0190e-20030623.bin", "bd6415094e1ce9e05daabe85de807666"),
    ("ps2-0200e-20040614.bin", "dc752f160044f2ed5fc1f4964db2a095"),
    ("ps2-0220e-20050620.bin", "573f7d4a430c32b3cc0fd0c41e104bbd"),
    ("ps2-0220e-20060210.bin", "af60e6d1a939019d55e5b330d24b1c25"),
    ("ps2-0220e-20060905.bin", "80bbb237a6af9c611df43b16b930b683"),
    ("ps2-0230e-20080220.bin", "dc69f0643a3030aaa4797501b483d6c4"),
    ("ps2-0160h-20010730.bin", "352d2ff9b3f68be7e6fa7e6dd8389346"),
    ("ps2-0160h-20020426.bin", "315a4003535dfda689752cb25f24785c"),
    ("ps2-0190h-20030623.bin", "07b562a3f0c4b9a55834df9bbc9bd0c3"),
    ("ps2-0200h-20040614.bin", "3e3e030c0f600442fa05b94f87a1e238"),
    ("ps2-0220h-20060905.bin", "c37bce95d32b2be480f87dd32704e664"),
    ("ps2-0220h-20060210.bin", "549a66d0c698635ca9fa3ab012da7129"),
    ("ps2-0190c-20030623.bin", "1b6e631b536247756287b916f9396872"),
    ("ps2-0190r-20030623.bin", "0c13357c01a25a886db2356bbe73d9f0"),
)


class Pcsx2(Emulator):
    id = "pcsx2"
    name = "PCSX2"
    system = "PlayStation 2"
    platforms = ("ps2",)
    source = Source("PCSX2/pcsx2", r"linux-appimage-x64-Qt\.AppImage$", TAG)
    firmware = tuple(Firmware("ps2", name, md5) for name, md5 in BIOS)

    @property
    def ini(self) -> str:
        return os.path.join(self.config_dir, "PCSX2", "inis", "PCSX2.ini")

    def configure(self) -> None:
        inifile.update(
            self.ini,
            values={"Folders": {
                "Bios": self.layout.bios("ps2"),
                "MemoryCards": self.layout.saves("ps2", self.id),
                "SaveStates": self.layout.states("ps2", self.id),
            }},
            defaults={"UI": {
                "SettingsVersion": SETTINGS_VERSION,
                "StartFullscreen": "true",
                "ConfirmShutdown": "false",
                "HideMouseCursor": "true",
            }},
        )

    def command(self, rom: str, platform: str = "") -> Command:
        return Command([self.executable, "-batch", "-fullscreen", "--", rom], self.env())
