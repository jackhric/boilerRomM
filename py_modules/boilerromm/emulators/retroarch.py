"""RetroArch (the consoles before the PlayStation 2), run from libretro's own AppImage with libretro's own cores."""
import asyncio
import io
import os
import shutil
import tempfile
import zipfile
import zlib
from typing import Any

from . import releases
from .base import Command, Emulator, Firmware, Layout, md5_of
from .progress import Session
from .sevenzip import ArchiveError, extract_7z

# libretro publishes no checksum for its builds, so the pinned one carries the size and checksum it had when it was
# tested. Cores exist only as nightly builds, the same ones RetroArch's own updater fetches: they cannot be pinned.
BUILDBOT = "https://buildbot.libretro.com"
TAG = "1.22.2"
PUBLISHED = "2025-11-20"
ARCHIVE_SIZE = 179361448
ARCHIVE_SHA256 = "7d62da9a21397d6e1b9490785cedbeafd262781b50115076736fbe8a77ef30e9"
CORES_URL = f"{BUILDBOT}/nightly/linux/x86_64/latest"

CORES = {
    "psx": "swanstation",
    "nes": "mesen",
    "famicom": "mesen",
    "snes": "snes9x",
    "sfam": "snes9x",
    "n64": "mupen64plus_next",
    "gb": "gambatte",
    "gbc": "gambatte",
    "gba": "mgba",
    "virtualboy": "mednafen_vb",
    "genesis": "genesis_plus_gx",
    "sms": "genesis_plus_gx",
    "segacd": "genesis_plus_gx",
    "sega32": "picodrive",
    "saturn": "mednafen_saturn",
    "atari2600": "stella",
    "atari5200": "a5200",
    "atari7800": "prosystem",
    "lynx": "handy",
    "jaguar": "virtualjaguar",
    "ngp": "mednafen_ngp",
    "ngpc": "mednafen_ngp",
    "wonderswan": "mednafen_wswan",
    "3do": "opera",
}

# The platforms whose games do not start without a BIOS. Elsewhere a BIOS is optional: SwanStation falls back to
# the OpenBIOS built into it.
NEEDS_BIOS = ("saturn", "segacd", "3do")

# Names and checksums from each core's .info file; the PlayStation ones are the named entries of SwanStation's own
# table (src/core/bios.cpp). Every core but SwanStation finds its BIOS by these exact names.
BIOS = {
    "psx": (
        ("scph1000.bin", "239665b1a3dade1b5a52c06338011044"),
        ("scph1001.bin", "924e392ed05558ffdb115408c263dccf"),
        ("scph1002.bin", "54847e693405ffeb0359c6287434cbef"),
        ("scph3000.bin", "849515939161e62f6b866f6853006780"),
        ("scph3500.bin", "cba733ceeff5aef5c32254f1d617fa62"),
        ("scph5500.bin", "8dd7d5296a650fac7319bce665a6a53c"),
        ("scph5501.bin", "490f666e1afb15b7362b406ed1cea246"),
        ("scph5502.bin", "32736f17079d0b2b7024407c39bd3050"),
        ("scph7001.bin", "1e68c231d0896b7eadcad1d7d8e76129"),
        ("scph7002.bin", "b9d9a0286c33dc6b7237bb13cd46fdee"),
        ("scph100.bin", "8abc1b549a4a80954addc48ef02c4521"),
        ("scph101.bin", "6e3735ff4c7dc899ee98981385f6f3d0"),
        ("scph102A.bin", "b10f5e0e3d9eb60e5159690680b1e774"),
        ("scph102B.bin", "de93caec13d1a141a40a79f5c86168d6"),
        ("psxonpsp660.bin", "c53ca5908936d412331790f4426c6c33"),
        ("ps1_rom.bin", "81bbe60ba7a3d1cea1d48c14cbcc647b"),
    ),
    "saturn": (
        ("sega_101.bin", "85ec9ca47d8f6807718151cbcca8b964"),
        ("mpr-17933.bin", "3240872c70984b6cbfda1586cab68dbe"),
    ),
    "segacd": (
        ("bios_CD_U.bin", "2efd74e3232ff260e371b99f84024f7f"),
        ("bios_CD_U.bin", "854b9150240a198070150e4566ae1290"),
        ("bios_CD_E.bin", "e66fa1dc5820d254611fdcdba0662372"),
        ("bios_CD_J.bin", "278a9397d192149e84e820ac621a8edd"),
    ),
    "3do": (
        ("panafz1.bin", "f47264dd47fe30f73ab3c010015c155b"),
        ("panafz10.bin", "51f2f43ae2f3508a14d9f56597e2d3ce"),
        ("panafz10-norsa.bin", "1477bda80dc33731a65468c1f5bcbee9"),
        ("panafz10e-anvil.bin", "a48e6746bd7edec0f40cff078f0bb19f"),
        ("panafz10e-anvil-norsa.bin", "cf11bbb5a16d7af9875cca9de9a15e09"),
        ("panafz1j.bin", "a496cfdded3da562759be3561317b605"),
        ("panafz1j-norsa.bin", "f6c71de7470d16abe4f71b1444883dc8"),
        ("goldstar.bin", "8639fd5e549bd6238cfee79e3e749114"),
        ("sanyotry.bin", "35fa1a1ebaaeea286dc5cd15487c13ea"),
        ("3do_arcade_saot.bin", "8970fc987ab89a7f64da9f8a8c4333ff"),
    ),
    "famicom": (("disksys.rom", "ca30b50f880eb660a320674ed365ef7a"),),
    "gba": (("gba_bios.bin", "a860e8c0b6d573d191e4ec7db1b1e4f6"),),
    "lynx": (("lynxboot.img", "fcd403db69f54290b51035d82f835e7b"),),
}

# What is taken out of the build's archive: the rest of it is shaders, overlays and a game database.
_ARCHIVE_ROOT = "RetroArch-Linux-x86_64/"
_ARCHIVE_CONFIG = _ARCHIVE_ROOT + "RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/"
_ARCHIVE_FOLDERS = {"assets/": "assets/", "autoconfig/": "autoconfig/", "cores/": "info/"}

def write_cfg(path: str, values: dict[str, str] | None = None, defaults: dict[str, str] | None = None) -> None:
    """retroarch.cfg is flat `key = "value"` lines. `values` are always written; `defaults` only where the key is
    not there yet, so what the user changes in RetroArch's own menu stays."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    at = {line.split("=", 1)[0].strip(): i for i, line in enumerate(lines) if "=" in line}
    for items, overwrite in ((defaults, False), (values, True)):
        for key, value in (items or {}).items():
            line = f'{key} = "{value}"'
            if key not in at:
                at[key] = len(lines)
                lines.append(line)
            elif overwrite:
                lines[at[key]] = line
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{os.path.basename(path)}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_cfg(path: str, key: str, fallback: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                name, sep, value = line.partition("=")
                if sep and name.strip() == key:
                    return value.strip().strip('"')
    except OSError:
        pass
    return fallback


async def _fetch(session: Session, url: str) -> bytes:
    async with session.get(url, headers={"User-Agent": releases.HEADERS["User-Agent"]}) as r:
        if r.status != 200:
            raise releases.ReleaseError(f"{url.rsplit('/', 1)[-1]}: HTTP {r.status}")
        return bytes(await r.read())


class RetroArch(Emulator):
    year = 1977
    firmware_set = True

    id = "retroarch"
    name = "RetroArch"
    system = "Classic consoles"
    platforms = tuple(CORES)
    firmware = tuple(Firmware(platform, name, md5) for platform, files in BIOS.items() for name, md5 in files)

    def __init__(self, layout: Layout) -> None:
        super().__init__(layout)
        self.cores_dir = os.path.join(self.home, "cores")
        self.info_dir = os.path.join(self.home, "info")
        self.assets_dir = os.path.join(self.home, "assets")
        self.autoconfig_dir = os.path.join(self.home, "autoconfig")

    @property
    def cfg(self) -> str:
        return os.path.join(self.config_dir, "retroarch", "retroarch.cfg")

    def platform_cfg(self, platform: str) -> str:
        return os.path.join(self.config_dir, "retroarch", "platforms", f"{platform}.cfg")

    def core(self, platform: str) -> str:
        if platform not in CORES:
            raise ValueError(f"RetroArch has no core for {platform or 'a game without a platform'}")
        return os.path.join(self.cores_dir, f"{CORES[platform]}_libretro.so")

    # Build
    async def versions(self, session: Session) -> list[dict[str, Any]]:
        return [{"tag": TAG, "name": TAG, "prerelease": False, "published": PUBLISHED, "tested": True}]

    async def install(self, session: Session, tag: str = "") -> str:
        if tag and tag != TAG:
            raise releases.ReleaseError(f"RetroArch {tag}: only {TAG} can be installed")
        archive = os.path.join(self.cache_dir, "RetroArch.7z")
        url = f"{BUILDBOT}/stable/{TAG}/linux/x86_64/RetroArch.7z"
        await releases.download(session, releases.Release(TAG, "RetroArch.7z", url, ARCHIVE_SIZE, ARCHIVE_SHA256), archive)
        try:
            await asyncio.to_thread(self._unpack, archive)
        finally:
            os.unlink(archive)
        await self._install_cores(session)
        with open(self.version_file, "w", encoding="utf-8") as f:
            f.write(TAG)
        return TAG

    def _unpack(self, archive: str) -> None:
        def wanted(name: str) -> str | None:
            if name == _ARCHIVE_ROOT + "RetroArch-Linux-x86_64.AppImage":
                return self.executable
            for source, folder in _ARCHIVE_FOLDERS.items():
                if name.startswith(_ARCHIVE_CONFIG + source):
                    path = os.path.normpath(os.path.join(self.home, folder, name[len(_ARCHIVE_CONFIG + source):]))
                    return path if path.startswith(os.path.join(self.home, folder)) else None
            return None

        extract_7z(archive, wanted)
        if not os.path.isfile(self.executable):
            raise ArchiveError("RetroArch.7z: the archive holds no AppImage")
        os.chmod(self.executable, 0o755)

    async def _install_cores(self, session: Session) -> None:
        # One line per core: the day it was built, the checksum of the core inside the zip, the zip's name.
        index = (await _fetch(session, f"{CORES_URL}/.index-extended")).decode()
        checksums = {fields[2]: fields[1] for fields in (line.split() for line in index.splitlines()) if len(fields) == 3}
        os.makedirs(self.cores_dir, exist_ok=True)
        for core in sorted(set(CORES.values())):
            name = f"{core}_libretro.so"
            if f"{name}.zip" not in checksums:
                raise releases.ReleaseError(f"{name}: libretro does not publish this core")
            data = await _fetch(session, f"{CORES_URL}/{name}.zip")
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    built = z.read(name)
            except (zipfile.BadZipFile, KeyError) as e:
                raise releases.ReleaseError(f"{name}: the download is damaged") from e
            if f"{zlib.crc32(built):08x}" != checksums[f"{name}.zip"].lower():
                raise releases.ReleaseError(f"{name}: checksum does not match libretro's list")
            path = os.path.join(self.cores_dir, name)
            with open(path + ".part", "wb") as f:
                f.write(built)
            os.replace(path + ".part", path)

    def uninstall(self, keep_settings: bool = True) -> None:
        super().uninstall(keep_settings)
        for folder in (self.cores_dir, self.info_dir, self.assets_dir, self.autoconfig_dir):
            shutil.rmtree(folder, ignore_errors=True)

    # Firmware
    def firmware_ready(self, platform: str = "") -> bool:
        """Whether a platform's games can start. Most cores need no BIOS, so RetroArch as a whole is always ready."""
        if platform not in NEEDS_BIOS:
            return True
        folder = self.layout.bios(platform)
        return any(os.path.isfile(os.path.join(folder, name)) for name, _ in BIOS[platform]) or \
            any(f.platform == platform for f in self.firmware_found())

    def bios_platforms(self) -> tuple[str, ...]:
        return NEEDS_BIOS

    def platform_ready(self, platform: str) -> bool:
        return self.firmware_ready(platform)

    def firmware_missing(self) -> list[str]:
        """The platforms whose games cannot start until the user adds a BIOS."""
        return [platform for platform in NEEDS_BIOS if not self.firmware_ready(platform)]

    def _name_firmware(self) -> None:
        """Cores look for a BIOS by name, where boilerRomM knows one by content: a known file under another name
        gets a link with the name the core wants."""
        for platform, files in BIOS.items():
            folder = self.layout.bios(platform)
            wanted = {md5: name for name, md5 in files}
            try:
                present = sorted(os.listdir(folder))
            except OSError:
                continue
            for name in present:
                path = os.path.join(folder, name)
                known = wanted.get(md5_of(path)) if os.path.isfile(path) else None
                if known and not os.path.lexists(os.path.join(folder, known)):
                    os.symlink(name, os.path.join(folder, known))

    # Config
    def configure(self) -> None:
        self._name_firmware()
        write_cfg(
            self.cfg,
            values={
                "libretro_directory": self.cores_dir,
                "libretro_info_path": self.info_dir,
                "assets_directory": self.assets_dir,
                "joypad_autoconfig_dir": self.autoconfig_dir,
            },
            defaults={
                "video_fullscreen": "true",
                "quit_on_close_content": "1",
                "rgui_show_start_screen": "false",
                "input_menu_toggle_gamepad_combo": "2",  # L3 + R3: without a keyboard nothing else opens the menu
                # The only joypad driver RetroArch has a profile of Steam's virtual gamepad for.
                "input_joypad_driver": "sdl2",
                "menu_swap_ok_cancel_buttons": "true",
                "sort_savefiles_enable": "false",
                "sort_savestates_enable": "false",
            },
        )
        # RetroArch has one BIOS, one save and one state folder; boilerRomM has them per platform. Each platform's
        # folders are in a file of its own, which command() adds on top of the main config.
        for platform in self.platforms:
            write_cfg(self.platform_cfg(platform), values={
                "system_directory": self.layout.bios(platform),
                "savefile_directory": self.layout.saves(platform, self.id),
                "savestate_directory": self.layout.states(platform, self.id),
            })

    # Launch
    def command(self, rom: str, platform: str = "") -> Command:
        core = self.core(platform)
        return Command([self.executable, "--config", self.cfg, "--appendconfig", self.platform_cfg(platform),
                        "-L", core, "-f", rom], self.env())
