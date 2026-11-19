import io
import json
import os
import re
import subprocess
import zipfile

import pytest
from boilerromm.emulators import Layout, releases
from boilerromm.emulators.shadps4 import RUN_FROM, TAG, ShadPs4
from boilerromm.games.install import Target

SELF = b"\x4f\x15\x3d\x1d" + b"module"
APPIMAGE = b"\x7fELF" + b"a" * 5000
ASSET = "shadps4-linux-sdl-0.21.0.zip"
ASSET_URL = "https://github.com/shadps4-emu/shadPS4/releases/download/v.0.21.0/" + ASSET


def zipped(*members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members:
            z.writestr(name, data)
    return buf.getvalue()


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body
        self.content = self

    async def json(self):
        return self._body

    async def iter_chunked(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeGitHub:
    def __init__(self, archive):
        self.archive = archive
        self.release = {"tag_name": TAG, "name": "shadPS4 0.21.0", "assets": [
            {"name": "shadps4-win64-sdl-0.21.0.zip", "size": 1, "digest": None, "browser_download_url": "https://x/win"},
            {"name": ASSET, "size": len(archive), "digest": None, "browser_download_url": ASSET_URL},
        ]}

    def get(self, url, headers=None):
        if url == f"{releases.API}/repos/shadps4-emu/shadPS4/releases/tags/{TAG}":
            return FakeResponse(200, self.release)
        if url == ASSET_URL:
            return FakeResponse(200, self.archive)
        return FakeResponse(404, {})


@pytest.fixture
def shadps4(tmp_path):
    return ShadPs4(Layout(str(tmp_path)))


def write(path, content=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return str(path)


def config(shadps4):
    with open(shadps4.config, encoding="utf-8") as f:
        return json.load(f)


def test_the_build_is_the_pinned_linux_sdl_zip():
    assert ShadPs4.source.repo == "shadps4-emu/shadPS4" and ShadPs4.source.tag == TAG == "v.0.21.0"
    assert re.search(ShadPs4.source.asset, ASSET)
    assert re.search(ShadPs4.source.asset, "shadps4-linux-sdl-2026-11-18-741d9b7.zip")
    assert not re.search(ShadPs4.source.asset, "shadps4-win64-sdl-0.21.0.zip")
    assert not re.search(ShadPs4.source.asset, "shadps4-ubuntu64-2026-11-18-741d9b7.zip")


def test_versions_are_named_by_release_or_nightly_date(shadps4):
    assert shadps4.version_label(TAG, "") == "0.21.0"
    assert shadps4.version_label("Pre-release-shadPS4-2026-11-18-741d9b75fd87104ae2f81e4443ffc5433828eebf", "") == "2026-11-18-741d9b7"


def test_prepare_keeps_everything_in_the_plugins_folders(shadps4, tmp_path):
    shadps4.prepare()
    home = tmp_path / "saves" / "ps4" / "shadps4"
    assert shadps4.config == str(tmp_path / "emulators" / "shadps4" / "data" / "shadPS4" / "config.json")
    assert config(shadps4) == {"General": {"home_dir": str(home), "sys_modules_dir": str(tmp_path / "bios" / "ps4"),
                                           "font_dir": str(tmp_path / "bios" / "ps4")}}
    for name in ("savedata", "trophy", "inputs"):
        assert (home / "1000" / name).is_dir()
    assert shadps4.env()["XDG_DATA_HOME"] == str(tmp_path / "emulators" / "shadps4" / "data")
    assert shadps4.config.startswith(os.path.join(shadps4.env()["XDG_DATA_HOME"], "shadPS4"))


def test_prepare_keeps_the_users_settings_and_repoints_the_folders(shadps4, tmp_path):
    shadps4.prepare()
    with open(shadps4.config, "w", encoding="utf-8") as f:
        json.dump({"General": {"home_dir": "/old", "volume_slider": 40}, "GPU": {"window_width": 1280}}, f)
    moved = ShadPs4(Layout(str(tmp_path / "moved")))
    os.makedirs(os.path.dirname(moved.config))
    os.replace(shadps4.config, moved.config)
    moved.prepare()
    c = config(moved)
    assert c["General"]["home_dir"] == str(tmp_path / "moved" / "saves" / "ps4" / "shadps4")
    assert c["General"]["volume_slider"] == 40 and c["GPU"] == {"window_width": 1280}


@pytest.mark.parametrize("content", [b"", b"{not json", b"[1, 2]"])
def test_a_damaged_config_is_replaced(shadps4, content):
    write(shadps4.config, content)
    shadps4.prepare()
    assert set(config(shadps4)["General"]) == {"home_dir", "sys_modules_dir", "font_dir"}


def test_reset_config_clears_settings_but_not_saves_firmware_or_cache(shadps4, tmp_path):
    shadps4.prepare()
    write(os.path.join(shadps4.config_dir, "users.json"), b"{}")
    write(os.path.join(shadps4.config_dir, "input_config", "default.ini"), b"x")
    write(os.path.join(shadps4.config_dir, "custom_configs", "CUSA00001.json"), b"{}")
    write(os.path.join(shadps4.config_dir, "cache", "kept"), b"x")
    save = write(tmp_path / "saves" / "ps4" / "shadps4" / "1000" / "savedata" / "CUSA00001" / "sce_sys" / "param.sfo", b"s")
    module = write(os.path.join(shadps4.layout.bios("ps4"), "libSceLibcInternal.sprx"), SELF)
    with open(shadps4.config, "w", encoding="utf-8") as f:
        json.dump({"General": {"volume_slider": 1}}, f)
    shadps4.reset_config()
    assert "volume_slider" not in config(shadps4)["General"] and config(shadps4)["General"]["home_dir"]
    for gone in ("users.json", "input_config", "custom_configs"):
        assert not os.path.exists(os.path.join(shadps4.config_dir, gone))
    assert all(os.path.exists(p) for p in (save, module, os.path.join(shadps4.config_dir, "cache", "kept")))


def test_firmware_is_any_system_module_in_the_bios_folder(shadps4, tmp_path):
    folder = shadps4.layout.bios("ps4")
    assert shadps4.requires == "PS4 system modules"
    assert not shadps4.firmware_ready() and not shadps4.status()["firmware"] and not shadps4.status()["ready"]
    write(os.path.join(folder, "readme.txt"), b"no")
    write(os.path.join(folder, "libSceFake.sprx"), b"not a module")
    write(os.path.join(folder, "font", "a.ttf"), SELF)
    assert shadps4.firmware_found() == [] and not shadps4.firmware_ready()
    write(os.path.join(folder, "libSceJson.sprx"), SELF)
    write(os.path.join(folder, "libSceXml.SPRX"), b"\x7fELF" + b"x")
    assert [f.name for f in shadps4.firmware_found()] == ["libSceJson.sprx", "libSceXml.SPRX"]
    assert shadps4.firmware_ready() and shadps4.status()["firmware"]


def test_add_firmware_takes_only_system_modules(shadps4, tmp_path):
    assert shadps4.add_firmware(write(tmp_path / "in" / "libSceJson.sprx", b"junk")) is None
    assert shadps4.add_firmware(write(tmp_path / "in" / "firmware.bin", SELF)) is None
    assert shadps4.add_firmware(str(tmp_path / "in" / "missing.sprx")) is None
    added = shadps4.add_firmware(write(tmp_path / "in" / "libSceJson.sprx", SELF))
    assert added.name == "libSceJson.sprx" and added.platform == "ps4"
    assert (tmp_path / "bios" / "ps4" / "libSceJson.sprx").read_bytes() == SELF
    assert shadps4.firmware_ready()


def test_command_runs_the_game_fullscreen_from_the_emulators_own_folder(shadps4):
    c = shadps4.command("/roms/ps4/Game [CUSA00001]")
    assert c.argv == ["/bin/sh", "-c", RUN_FROM, "sh", shadps4.home, shadps4.executable, "--fullscreen", "true", "--game", "/roms/ps4/Game [CUSA00001]"]
    assert c.env == {"XDG_CONFIG_HOME": shadps4.config_dir, "XDG_DATA_HOME": shadps4.data_dir, "XDG_CACHE_HOME": shadps4.cache_dir}


def test_command_leaves_a_user_folder_in_the_roms_folder_alone(shadps4, tmp_path):
    roms = tmp_path / "roms"
    os.makedirs(roms / "user")
    os.makedirs(shadps4.home)
    log = tmp_path / "calls"
    write(shadps4.executable, f'#!/bin/sh\necho "$(pwd) $*" >> "{log}"\n'.encode())
    os.chmod(shadps4.executable, 0o755)
    c = shadps4.command(str(roms / "Game"))
    subprocess.run(c.argv, check=True, cwd=roms)
    assert log.read_text() == f"{shadps4.home} --fullscreen true --game {roms / 'Game'}\n"


def test_launch_file_is_the_folder_holding_the_eboot(shadps4, tmp_path):
    assert shadps4.launch_file(Target(str(tmp_path / "game.zar"), False)) == str(tmp_path / "game.zar")

    plain = tmp_path / "Plain"
    write(plain / "eboot.bin", b"x")
    write(plain / "sce_sys" / "param.sfo", b"x" * 100)
    assert shadps4.launch_file(Target(str(plain), True)) == str(plain)

    nested = tmp_path / "Nested"
    write(nested / "readme.txt", b"x" * 100)
    write(nested / "CUSA00002" / "eboot.bin", b"x")
    assert shadps4.launch_file(Target(str(nested), True)) == str(nested / "CUSA00002")


def test_launch_file_prefers_the_base_game_to_its_update_or_mods(shadps4, tmp_path):
    pack = tmp_path / "Pack"
    for name in ("CUSA00003-UPDATE", "CUSA00003-mods", "CUSA00003-patch", "CUSA00003"):
        write(pack / name / "eboot.bin", b"x")
    assert shadps4.launch_file(Target(str(pack), True)) == str(pack / "CUSA00003")
    only_update = tmp_path / "OnlyUpdate"
    write(only_update / "CUSA00004-UPDATE" / "eboot.bin", b"x")
    assert shadps4.launch_file(Target(str(only_update), True)) == str(only_update / "CUSA00004-UPDATE")


def test_launch_file_takes_a_zar_archive_when_there_is_no_folder(shadps4, tmp_path):
    archive = tmp_path / "Archive"
    write(archive / "readme.txt", b"x" * 500)
    write(archive / "CUSA00005.zar", b"x" * 10)
    write(archive / "CUSA00005-UPDATE.zar", b"x")
    assert shadps4.launch_file(Target(str(archive), True)) == str(archive / "CUSA00005.zar")


def test_launch_file_cannot_make_a_pkg_launchable(shadps4, tmp_path):
    pkg = tmp_path / "Game.pkg"
    assert shadps4.launch_file(Target(str(pkg), False)) == str(pkg)
    folder = tmp_path / "Pkgs"
    write(folder / "Game.pkg", b"x" * 100)
    assert shadps4.launch_file(Target(str(folder), True)) == str(folder / "Game.pkg")


async def test_install_unpacks_the_appimage_from_the_zip(shadps4):
    github = FakeGitHub(zipped(("Shadps4-sdl.AppImage", APPIMAGE)))
    assert await shadps4.install(github) == TAG
    assert open(shadps4.executable, "rb").read() == APPIMAGE
    assert os.access(shadps4.executable, os.X_OK)
    assert shadps4.version == TAG and shadps4.version_name == "0.21.0"
    assert sorted(os.listdir(shadps4.home)) == ["shadps4.AppImage", "version"]


@pytest.mark.parametrize("archive, message", [(zipped(("readme.txt", b"x")), "no AppImage"), (b"not a zip file at all", "damaged")])
async def test_a_zip_without_the_build_installs_nothing(shadps4, archive, message):
    with pytest.raises(releases.ReleaseError, match=message):
        await shadps4.install(FakeGitHub(archive))
    assert not os.path.exists(shadps4.executable) and shadps4.version == ""
    assert os.listdir(shadps4.home) == []


async def test_installing_again_replaces_the_build_and_uninstall_keeps_saves(shadps4, tmp_path):
    await shadps4.install(FakeGitHub(zipped(("Shadps4-sdl.AppImage", b"\x7fELFold"))))
    await shadps4.install(FakeGitHub(zipped(("Shadps4-sdl.AppImage", APPIMAGE))))
    assert open(shadps4.executable, "rb").read() == APPIMAGE
    shadps4.prepare()
    save = write(tmp_path / "saves" / "ps4" / "shadps4" / "1000" / "savedata" / "x", b"s")
    shadps4.uninstall()
    assert not os.path.exists(shadps4.executable) and os.path.exists(save) and os.path.exists(shadps4.config)
