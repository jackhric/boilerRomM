import os

import pytest
from boilerromm.emulators import Layout, inifile, releases
from boilerromm.emulators.dolphin import TAG, Dolphin

BUILD = b"\x7fELF" + b"d" * 5000
ASSET = "Dolphin_Emulator-2609a-anylinux-x86_64.AppImage"
ASSET_URL = f"https://github.com/pkgforge-dev/Dolphin-emu-AppImage/releases/download/{TAG}/{ASSET}"


class FakeResponse:
    def __init__(self, status, body=None):
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
    def __init__(self):
        self.calls = []

    def release(self, tag):
        names = ("Dolphin_Emulator-2609a-anylinux-aarch64.AppImage", ASSET + ".zsync", ASSET)
        return {"tag_name": tag, "name": "Dolphin_Emulator: 2609a", "prerelease": False, "draft": False,
                "published_at": "2026-11-01T18:29:58Z",
                "assets": [{"name": name, "size": len(BUILD), "digest": "", "browser_download_url": ASSET_URL if name == ASSET else "x"}
                           for name in names]}

    def get(self, url, headers=None):
        self.calls.append(url)
        base = f"{releases.API}/repos/pkgforge-dev/Dolphin-emu-AppImage/releases"
        if url in (f"{base}/tags/{TAG}", f"{base}/latest"):
            return FakeResponse(200, self.release(TAG))
        if url == ASSET_URL:
            return FakeResponse(200, BUILD)
        return FakeResponse(404, {})


@pytest.fixture
def dolphin(tmp_path):
    return Dolphin(Layout(str(tmp_path)))


async def test_install_takes_the_x86_build_and_names_it_by_its_dolphin_version(dolphin):
    github = FakeGitHub()
    assert await dolphin.install(github) == TAG
    assert github.calls[-1] == ASSET_URL
    assert os.access(dolphin.executable, os.X_OK)
    assert dolphin.version == TAG and dolphin.version_name == "2609a"
    assert await dolphin.versions(github) == [
        {"tag": TAG, "name": "2609a", "prerelease": False, "published": "2026-11-01", "tested": True}]


def test_it_runs_both_consoles_and_needs_no_firmware(dolphin):
    assert dolphin.platforms == ("ngc", "wii")
    assert dolphin.firmware_ready()


def test_prepare_writes_a_config_that_starts_and_stops_without_dialogs(dolphin, tmp_path):
    dolphin.prepare()
    assert dolphin.ini == str(tmp_path / "emulators" / "dolphin" / "data" / "Config" / "Dolphin.ini")
    assert inifile.read(dolphin.ini, "Analytics", "PermissionAsked") == "True"
    assert inifile.read(dolphin.ini, "Interface", "ConfirmStop") == "False"
    assert dolphin.status()["configured"]


def test_prepare_keeps_saves_and_states_in_the_shared_folders(dolphin, tmp_path):
    dolphin.prepare()
    memory_cards = tmp_path / "saves" / "ngc" / "dolphin"
    assert inifile.read(dolphin.ini, "Core", "GCIFolderAPath") == str(memory_cards)
    assert inifile.read(dolphin.ini, "Core", "MemcardAPath") == str(memory_cards / "MemoryCardA.raw")
    assert inifile.read(dolphin.ini, "General", "NANDRootPath") == str(tmp_path / "saves" / "wii" / "dolphin")
    states = tmp_path / "emulators" / "dolphin" / "data" / "StateSaves"
    assert os.path.realpath(states) == str(tmp_path / "states" / "ngc" / "dolphin") and os.path.isdir(states)


def test_prepare_again_keeps_the_users_settings_and_repoints_the_folders(dolphin, tmp_path):
    dolphin.prepare()
    inifile.update(dolphin.ini, {"Interface": {"ConfirmStop": "True"}, "Core": {"GFXBackend": "Vulkan", "GCIFolderAPath": "/old"}})
    states = str(tmp_path / "emulators" / "dolphin" / "data" / "StateSaves")
    os.unlink(states)
    os.symlink("/somewhere/else", states)
    dolphin.prepare()
    assert inifile.read(dolphin.ini, "Interface", "ConfirmStop") == "True"
    assert inifile.read(dolphin.ini, "Core", "GFXBackend") == "Vulkan"
    assert inifile.read(dolphin.ini, "Core", "GCIFolderAPath") == str(tmp_path / "saves" / "ngc" / "dolphin")
    assert os.readlink(states) == str(tmp_path / "states" / "ngc" / "dolphin")


def test_a_state_folder_dolphin_already_filled_is_left_as_it_is(dolphin, tmp_path):
    states = tmp_path / "emulators" / "dolphin" / "data" / "StateSaves"
    states.mkdir(parents=True)
    (states / "GALE01.s01").write_bytes(b"state")
    dolphin.prepare()
    assert not states.is_symlink() and (states / "GALE01.s01").is_file()


def test_command_starts_the_game_fullscreen_in_its_own_user_folder(dolphin, tmp_path):
    c = dolphin.command("/roms/gc/-odd name.rvz")
    user = str(tmp_path / "emulators" / "dolphin" / "data")
    assert c.argv == [dolphin.executable, "-u", user, "-b", "-C", "Dolphin.Display.Fullscreen=True", "-e", "/roms/gc/-odd name.rvz"]
    assert c.env == {"XDG_CONFIG_HOME": dolphin.config_dir, "XDG_DATA_HOME": dolphin.data_dir, "XDG_CACHE_HOME": dolphin.cache_dir,
                     "DISABLE_AUTO_UPDATES": "1"}
    assert dolphin.ini.startswith(user)


def test_reset_and_uninstall_never_touch_saves_or_states(dolphin, tmp_path):
    dolphin.prepare()
    inifile.update(dolphin.ini, {"Core": {"GFXBackend": "Vulkan"}})
    (tmp_path / "saves" / "ngc" / "dolphin" / "USA").mkdir()
    (tmp_path / "saves" / "ngc" / "dolphin" / "USA" / "game.gci").write_bytes(b"save")
    (tmp_path / "saves" / "wii" / "dolphin" / "title.bin").write_bytes(b"nand")
    (tmp_path / "emulators" / "dolphin" / "data" / "StateSaves" / "GALE01.s01").write_bytes(b"state")
    (tmp_path / "emulators" / "dolphin" / "data" / "Cache" / "shader").write_bytes(b"cache")
    dolphin.reset_config()
    assert inifile.read(dolphin.ini, "Core", "GFXBackend") == ""
    dolphin.uninstall()
    assert os.path.isfile(dolphin.ini) and not os.path.exists(dolphin.cache_dir)
    dolphin.uninstall(keep_settings=False)
    assert not os.path.exists(dolphin.home)
    assert (tmp_path / "saves" / "ngc" / "dolphin" / "USA" / "game.gci").read_bytes() == b"save"
    assert (tmp_path / "saves" / "wii" / "dolphin" / "title.bin").read_bytes() == b"nand"
    assert (tmp_path / "states" / "ngc" / "dolphin" / "GALE01.s01").read_bytes() == b"state"
