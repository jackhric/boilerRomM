import base64
import hashlib
import io
import os
import zipfile
import zlib

import pytest

from boilerromm import releases
from boilerromm.emulators import Layout
from boilerromm.emulators import retroarch as module
from boilerromm.emulators.retroarch import BIOS, CORES, CORES_URL, NEEDS_BIOS, TAG, ArchiveError, RetroArch, extract_7z, read_cfg, write_cfg

# A solid LZMA archive laid out like libretro's RetroArch.7z, made with `7z a -m0=lzma -ms=on`: the AppImage, one
# file each under assets, autoconfig, cores (a core's .info) and shaders, and an empty system folder.
ARCHIVE = base64.b64decode(
    "N3q8ryccAAR2H4nCvQEAAAAAAAAiAAAAAAAAAOqLeIsAP5FFhGlNX2Q/SetmLcXqJRZAuGL9yy2g4Ky3fAXjpvMPDoI9nd8a5ynGACuUdg2/K9+jc+V2Qako"
    "+g6xaFwbZRFBRsNDJAh8sems0RjgAAAAgTMHrg/SwW/9QMCQ00PE4fnorqGMNJVLzT3cgWEJ3is9p3Ts7D86NPOa+XRhw/zCtWFME0mAZdM5pU7XsZ+78eiI"
    "5VitLvgRnAlNsn9wx/c0GHO97b+dm//VHzBC6X2CLhQ/r7gJWvGIkV6X2A1PmoDlJcYeh5IB3J/uQzi1xv4NX71P8Jn2g9LPcZEI8UF+J5DqxTc5Qwqmq4b4"
    "LFTmHW7cGZnpBjYwoYcaV2U9Ywgs6jr9FQehIjy7ebbHhctea7FlsAHcqKDGQ59mHr435lHgoPY4dUQaK4y5oRSjvnIFeDeYPY5MuJI0YYJOcn/iBPHPIamW"
    "nchxAHwSGSnWVWrB/N+CmggtSjb0XuPTyadXvDezw5YfZTyX2QauZXWPIGno8ZPynKmW1d7Suwnu3AXGVU2/FhRIe48l3BOlJa4acEPvecHBfBEXpShz61Ee"
    "z1+665bCABOShf8TWsayiRljAvxtRfGKAAAAFwZQAQmBbQAHCwEAASMDAQEFXQAQAAAMjFIKAcFCdIYAAA==")
APPIMAGE = b"\x7fELF an AppImage"
ARCHIVE_URL = f"https://buildbot.libretro.com/stable/{TAG}/linux/x86_64/RetroArch.7z"
ALL_CORES = sorted(set(CORES.values()))


def core_build(core):
    return b"\x7fELF " + core.encode()


def core_zip(core, content=None):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{core}_libretro.so", core_build(core) if content is None else content)
    return data.getvalue()


class FakeResponse:
    def __init__(self, status, body=b""):
        self.status = status
        self._body = body
        self.content = self

    async def read(self):
        return self._body

    async def iter_chunked(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeBuildbot:
    def __init__(self, archive=ARCHIVE, cores=ALL_CORES, zips=None):
        self.archive = archive
        self.zips = {core: core_zip(core) for core in cores} | (zips or {})
        self.index = "".join(f"2026-11-18 {zlib.crc32(core_build(core)):08x} {core}_libretro.so.zip\n" for core in cores)
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append(url)
        if url == ARCHIVE_URL:
            return FakeResponse(200, self.archive)
        if url == f"{CORES_URL}/.index-extended":
            return FakeResponse(200, self.index.encode())
        core = url.removeprefix(f"{CORES_URL}/").removesuffix("_libretro.so.zip")
        if core in self.zips:
            return FakeResponse(200, self.zips[core])
        return FakeResponse(404)


@pytest.fixture
def retroarch(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ARCHIVE_SIZE", len(ARCHIVE))
    monkeypatch.setattr(module, "ARCHIVE_SHA256", hashlib.sha256(ARCHIVE).hexdigest())
    return RetroArch(Layout(str(tmp_path)))


def bios_file(folder, name, content):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(content)
    return path


def known(monkeypatch, platform, name, content):
    """Makes `content` the checksum boilerRomM knows the platform's BIOS `name` by."""
    files = tuple((n, hashlib.md5(content).hexdigest() if n == name else md5) for n, md5 in BIOS[platform])
    monkeypatch.setitem(BIOS, platform, files)
    monkeypatch.setattr(RetroArch, "firmware", tuple(module.Firmware(p, n, md5) for p, fs in BIOS.items() for n, md5 in fs))


def test_every_platform_has_a_core_and_playstation_runs_on_swanstation():
    assert CORES["psx"] == "swanstation"
    assert RetroArch.platforms == tuple(CORES)
    assert not {"ps2", "ngc", "dc", "xbox"} & set(RetroArch.platforms)
    assert set(BIOS) <= set(CORES) and set(NEEDS_BIOS) <= set(BIOS)


# Archive
def test_extract_takes_the_wanted_files_out_of_a_solid_archive(tmp_path):
    archive = tmp_path / "a.7z"
    archive.write_bytes(ARCHIVE)
    count = extract_7z(str(archive), lambda name: str(tmp_path / "out" / os.path.basename(name)) if name.endswith((".AppImage", ".slang")) else None)
    assert count == 2
    assert (tmp_path / "out" / "RetroArch-Linux-x86_64.AppImage").read_bytes() == APPIMAGE
    assert (tmp_path / "out" / "crt.slang").read_bytes() == b"shader\n"
    assert sorted(os.listdir(tmp_path / "out")) == ["RetroArch-Linux-x86_64.AppImage", "crt.slang"]


@pytest.mark.parametrize("damaged, message", [
    (b"PK\x03\x04" + ARCHIVE[4:], "not a 7z"),
    (ARCHIVE[:-10], "cut short or damaged"),
    (ARCHIVE[:40] + bytes([ARCHIVE[40] ^ 0xFF]) + ARCHIVE[41:], "checksum|cut short|damaged"),
])
def test_extract_refuses_a_damaged_archive(tmp_path, damaged, message):
    archive = tmp_path / "a.7z"
    archive.write_bytes(damaged)
    with pytest.raises(ArchiveError, match=message):
        extract_7z(str(archive), lambda name: str(tmp_path / "out" / os.path.basename(name)))
    assert not (tmp_path / "out").exists() or os.listdir(tmp_path / "out") == []


# Build
async def test_install_unpacks_the_build_and_fetches_every_core(retroarch, tmp_path):
    buildbot = FakeBuildbot()
    assert retroarch.version == "" and not retroarch.status()["installed"]
    assert await retroarch.install(buildbot) == TAG
    home = tmp_path / "emulators" / "retroarch"
    assert (home / "retroarch.AppImage").read_bytes() == APPIMAGE
    assert os.access(retroarch.executable, os.X_OK)
    assert (home / "assets" / "ozone" / "font.ttf").is_file()
    assert (home / "autoconfig" / "sdl2" / "Steam Virtual Gamepad.cfg").is_file()
    assert (home / "info" / "swanstation_libretro.info").is_file()
    assert not (home / "shaders").exists() and not (home / "cache" / "RetroArch.7z").exists()
    assert sorted(os.listdir(home / "cores")) == [f"{core}_libretro.so" for core in ALL_CORES]
    assert (home / "cores" / "swanstation_libretro.so").read_bytes() == core_build("swanstation")
    assert retroarch.version == TAG and retroarch.status()["installed"]
    assert buildbot.calls[:2] == [ARCHIVE_URL, f"{CORES_URL}/.index-extended"]


@pytest.mark.parametrize("buildbot, message", [
    (FakeBuildbot(archive=ARCHIVE[:-1]), "expected"),
    (FakeBuildbot(archive=ARCHIVE[:-1] + b"\x01"), "checksum"),
    (FakeBuildbot(cores=[c for c in ALL_CORES if c != "swanstation"]), "swanstation_libretro.so: libretro does not publish"),
    (FakeBuildbot(zips={"snes9x": core_zip("snes9x", b"another build")}), "snes9x_libretro.so: checksum"),
    (FakeBuildbot(zips={"snes9x": b"not a zip"}), "snes9x_libretro.so: the download is damaged"),
])
async def test_an_install_that_does_not_match_what_libretro_publishes_is_not_installed(retroarch, buildbot, message):
    with pytest.raises(releases.ReleaseError, match=message):
        await retroarch.install(buildbot)
    assert retroarch.version == "" and not retroarch.status()["installed"]


async def test_only_the_tested_build_is_offered(retroarch):
    assert await retroarch.versions(FakeBuildbot()) == [
        {"tag": TAG, "name": TAG, "prerelease": False, "published": "2025-11-20", "tested": True}]
    with pytest.raises(releases.ReleaseError, match="only"):
        await retroarch.install(FakeBuildbot(), "1.21.0")


async def test_uninstall_removes_the_build_and_its_cores_and_keeps_settings_and_saves(retroarch, tmp_path):
    await retroarch.install(FakeBuildbot())
    retroarch.prepare()
    save = bios_file(str(tmp_path / "saves" / "psx" / "retroarch"), "game.srm", b"save")
    retroarch.uninstall()
    home = tmp_path / "emulators" / "retroarch"
    assert sorted(os.listdir(home)) == ["config", "data"]
    assert os.path.isfile(retroarch.cfg) and os.path.isfile(save)
    assert retroarch.version == ""


# Config
def test_cfg_files_keep_the_lines_they_are_not_asked_to_change(tmp_path):
    path = str(tmp_path / "retroarch.cfg")
    with open(path, "w") as f:
        f.write('# mine\nvideo_fullscreen = "false"\nsystem_directory = "/old"\nvideo_shader = "/a=b.slangp"\n')
    write_cfg(path, values={"system_directory": "/new", "libretro_directory": "/cores"}, defaults={"video_fullscreen": "true", "fps_show": "true"})
    with open(path) as f:
        assert f.read().splitlines() == ['# mine', 'video_fullscreen = "false"', 'system_directory = "/new"', 'video_shader = "/a=b.slangp"',
                                         'fps_show = "true"', 'libretro_directory = "/cores"']
    assert read_cfg(path, "video_shader") == "/a=b.slangp"
    assert read_cfg(path, "missing", "fallback") == "fallback"


def test_prepare_points_retroarch_at_its_own_folders_and_each_platform_at_the_shared_ones(retroarch, tmp_path):
    retroarch.prepare()
    home = tmp_path / "emulators" / "retroarch"
    assert retroarch.cfg == str(home / "config" / "retroarch" / "retroarch.cfg")
    assert read_cfg(retroarch.cfg, "libretro_directory") == str(home / "cores")
    assert read_cfg(retroarch.cfg, "libretro_info_path") == str(home / "info")
    assert read_cfg(retroarch.cfg, "assets_directory") == str(home / "assets")
    assert read_cfg(retroarch.cfg, "joypad_autoconfig_dir") == str(home / "autoconfig")
    assert read_cfg(retroarch.cfg, "video_fullscreen") == "true"
    assert read_cfg(retroarch.cfg, "quit_on_close_content") == "1"
    assert read_cfg(retroarch.cfg, "rgui_show_start_screen") == "false"
    assert read_cfg(retroarch.cfg, "input_joypad_driver") == "sdl2"
    for platform in ("psx", "snes", "saturn"):
        cfg = retroarch.platform_cfg(platform)
        assert read_cfg(cfg, "system_directory") == str(tmp_path / "bios" / platform)
        assert read_cfg(cfg, "savefile_directory") == str(tmp_path / "saves" / platform / "retroarch")
        assert read_cfg(cfg, "savestate_directory") == str(tmp_path / "states" / platform / "retroarch")
        for folder in (f"bios/{platform}", f"saves/{platform}/retroarch", f"states/{platform}/retroarch"):
            assert (tmp_path / folder).is_dir()
    assert sorted(os.listdir(home / "config" / "retroarch" / "platforms")) == sorted(f"{p}.cfg" for p in CORES)


def test_prepare_again_keeps_the_users_settings_and_repoints_the_folders(retroarch, tmp_path):
    retroarch.prepare()
    write_cfg(retroarch.cfg, {"video_fullscreen": "false", "video_shader_enable": "true", "libretro_directory": "/somewhere/else"})
    write_cfg(retroarch.platform_cfg("psx"), {"system_directory": "/somewhere/else"})
    retroarch.prepare()
    assert read_cfg(retroarch.cfg, "video_fullscreen") == "false"
    assert read_cfg(retroarch.cfg, "video_shader_enable") == "true"
    assert read_cfg(retroarch.cfg, "libretro_directory") == str(tmp_path / "emulators" / "retroarch" / "cores")
    assert read_cfg(retroarch.platform_cfg("psx"), "system_directory") == str(tmp_path / "bios" / "psx")


def test_reset_config_restores_defaults_and_leaves_saves_and_firmware(retroarch, tmp_path):
    retroarch.prepare()
    write_cfg(retroarch.cfg, {"video_fullscreen": "false"})
    save = bios_file(str(tmp_path / "saves" / "psx" / "retroarch"), "game.srm", b"save")
    bios = bios_file(str(tmp_path / "bios" / "psx"), "scph5501.bin", b"bios")
    retroarch.reset_config()
    assert read_cfg(retroarch.cfg, "video_fullscreen") == "true"
    assert os.path.isfile(save) and os.path.isfile(bios)


# Launch
@pytest.mark.parametrize("platform, core", [("psx", "swanstation"), ("snes", "snes9x"), ("sfam", "snes9x"), ("segacd", "genesis_plus_gx"),
                                            ("n64", "mupen64plus_next"), ("saturn", "mednafen_saturn"), ("gbc", "gambatte")])
def test_command_starts_the_game_fullscreen_on_its_platforms_core(retroarch, tmp_path, platform, core):
    home = tmp_path / "emulators" / "retroarch"
    command = retroarch.command("/roms/A Game (USA).chd", platform)
    assert command.argv == [
        str(home / "retroarch.AppImage"),
        "--config", str(home / "config" / "retroarch" / "retroarch.cfg"),
        "--appendconfig", str(home / "config" / "retroarch" / "platforms" / f"{platform}.cfg"),
        "-L", str(home / "cores" / f"{core}_libretro.so"),
        "-f", "/roms/A Game (USA).chd",
    ]
    assert command.env["XDG_CONFIG_HOME"] == str(home / "config")


@pytest.mark.parametrize("platform", ["", "ps2", "dc", "nonsense"])
def test_command_refuses_a_platform_it_has_no_core_for(retroarch, platform):
    with pytest.raises(ValueError, match="no core"):
        retroarch.command("/roms/game.iso", platform)
    with pytest.raises(ValueError, match="no core"):
        retroarch.command("/roms/game.iso")


# Firmware
def test_most_platforms_start_without_a_bios_and_three_do_not(retroarch):
    assert retroarch.firmware_ready() and retroarch.status()["firmware"]
    assert retroarch.firmware_ready("psx") and retroarch.firmware_ready("snes")
    assert not retroarch.firmware_ready("saturn") and not retroarch.firmware_ready("segacd") and not retroarch.firmware_ready("3do")
    assert retroarch.firmware_missing() == ["saturn", "segacd", "3do"]


def test_a_bios_is_known_by_content_whatever_it_is_called(retroarch, tmp_path, monkeypatch):
    known(monkeypatch, "saturn", "mpr-17933.bin", b"a saturn bios")
    known(monkeypatch, "psx", "scph5501.bin", b"a playstation bios")
    bios_file(str(tmp_path / "bios" / "saturn"), "Sega Saturn BIOS (USA).bin", b"a saturn bios")
    bios_file(str(tmp_path / "bios" / "saturn"), "notes.txt", b"not a bios")
    bios_file(str(tmp_path / "bios" / "psx"), "scph5501.bin", b"a playstation bios")
    assert [(f.platform, f.name) for f in retroarch.firmware_found()] == [("psx", "scph5501.bin"), ("saturn", "mpr-17933.bin")]
    assert retroarch.firmware_ready("saturn")
    assert retroarch.firmware_missing() == ["segacd", "3do"]


def test_prepare_gives_a_known_bios_the_name_its_core_looks_for(retroarch, tmp_path, monkeypatch):
    known(monkeypatch, "saturn", "mpr-17933.bin", b"a saturn bios")
    bios_file(str(tmp_path / "bios" / "saturn"), "Sega Saturn BIOS (USA).bin", b"a saturn bios")
    retroarch.prepare()
    retroarch.prepare()
    link = tmp_path / "bios" / "saturn" / "mpr-17933.bin"
    assert link.is_symlink() and link.read_bytes() == b"a saturn bios"
    assert sorted(os.listdir(tmp_path / "bios" / "saturn")) == ["Sega Saturn BIOS (USA).bin", "mpr-17933.bin"]


def test_a_bios_of_another_revision_counts_when_it_has_the_name_the_core_looks_for(retroarch, tmp_path):
    bios_file(str(tmp_path / "bios" / "segacd"), "bios_CD_U.bin", b"a revision boilerRomM has no checksum of")
    assert retroarch.firmware_found() == []
    assert retroarch.firmware_ready("segacd")


def test_add_firmware_files_a_bios_under_its_platform_and_name(retroarch, tmp_path, monkeypatch):
    known(monkeypatch, "segacd", "bios_CD_E.bin", b"a sega cd bios")
    source = bios_file(str(tmp_path / "downloads"), "MegaCD.bin", b"a sega cd bios")
    added = retroarch.add_firmware(source)
    assert (added.platform, added.name) == ("segacd", "bios_CD_E.bin")
    assert (tmp_path / "bios" / "segacd" / "bios_CD_E.bin").read_bytes() == b"a sega cd bios"
    assert retroarch.add_firmware(bios_file(str(tmp_path / "downloads"), "other.bin", b"something else")) is None
    assert retroarch.firmware_ready("segacd")
