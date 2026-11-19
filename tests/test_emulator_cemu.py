import os
import re

import pytest
from boilerromm.emulators import Layout, releases, xmlfile
from boilerromm.emulators.cemu import DEFAULTS, EXAMPLE_KEY, PAD_UUID, TAG, Cemu
from boilerromm.games.install import Target

BUILD = b"\x7fELF" + b"c" * 5000
ASSET = "Cemu-2.6-x86_64.AppImage"
ASSET_URL = f"https://github.com/cemu-project/Cemu/releases/download/{TAG}/{ASSET}"
KEY = "0123456789abcdef0123456789abcdef"


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

    def get(self, url, headers=None):
        self.calls.append(url)
        base = f"{releases.API}/repos/cemu-project/Cemu/releases"
        if url in (f"{base}/tags/{TAG}", f"{base}/latest"):
            names = ("cemu-2.6-macos-12-x64.dmg", "cemu-2.6-ubuntu-22.04-x64.zip", "cemu-2.6-windows-x64.zip", ASSET)
            return FakeResponse(200, {"tag_name": TAG, "name": "Cemu 2.6", "prerelease": False, "draft": False, "published_at": "2025-02-06T13:18:18Z",
                                      "assets": [{"name": n, "size": len(BUILD), "digest": "", "browser_download_url": ASSET_URL if n == ASSET else "x"}
                                                 for n in names]})
        if url == ASSET_URL:
            return FakeResponse(200, BUILD)
        return FakeResponse(404, {})


@pytest.fixture
def cemu(tmp_path):
    return Cemu(Layout(str(tmp_path)))


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    return str(path)


async def test_install_takes_the_appimage_of_the_pinned_release(cemu):
    github = FakeGitHub()
    assert await cemu.install(github) == TAG
    assert github.calls[-1] == ASSET_URL
    assert os.access(cemu.executable, os.X_OK) and cemu.version == TAG


def test_it_runs_wii_u_games(cemu):
    assert cemu.platforms == ("wiiu",)


def test_prepare_writes_a_config_that_starts_a_game_without_dialogs(cemu, tmp_path):
    cemu.prepare()
    assert cemu.settings == str(tmp_path / "emulators" / "cemu" / "config" / "Cemu" / "settings.xml")
    for key, value in DEFAULTS.items():
        assert xmlfile.read(cemu.settings, key) == value
    assert xmlfile.read(cemu.settings, "check_update") == "false" and xmlfile.read(cemu.settings, "fullscreen") == "true"
    assert cemu.status()["configured"]


def test_the_mlc_folder_is_ours_and_its_saves_are_the_shared_ones(cemu, tmp_path):
    cemu.prepare()
    mlc = tmp_path / "emulators" / "cemu" / "data" / "mlc01"
    assert xmlfile.read(cemu.settings, "mlc_path") == str(mlc)
    assert os.path.realpath(mlc / "usr" / "save") == str(tmp_path / "saves" / "wiiu" / "cemu")
    cemu.prepare()
    assert os.path.islink(mlc / "usr" / "save")


def test_prepare_again_keeps_the_users_settings_and_repoints_the_mlc(cemu, tmp_path):
    cemu.prepare()
    xmlfile.update(cemu.settings, "content", values={"Graphic/api": "0", "mlc_path": "/old", "Graphic/VSync": "1"})
    cemu.prepare()
    assert xmlfile.read(cemu.settings, "Graphic/api") == "0" and xmlfile.read(cemu.settings, "Graphic/VSync") == "1"
    assert xmlfile.read(cemu.settings, "mlc_path") == str(tmp_path / "emulators" / "cemu" / "data" / "mlc01")


def test_prepare_leaves_what_cemu_wrote_to_its_settings_alone(cemu):
    write(cemu.settings, "<?xml version=\"1.0\"?><content><GamePaths><Entry>/games</Entry></GamePaths><check_update>true</check_update></content>")
    cemu.prepare()
    assert xmlfile.read(cemu.settings, "GamePaths/Entry") == "/games" and xmlfile.read(cemu.settings, "check_update") == "true"
    assert xmlfile.read(cemu.settings, "fullscreen") == "true"


def test_a_settings_file_that_does_not_parse_is_replaced(cemu):
    write(cemu.settings, "<content><fullscr")
    cemu.prepare()
    assert xmlfile.read(cemu.settings, "fullscreen") == "true"


def test_the_controller_is_the_steam_pad_as_a_gamepad_and_the_profile_is_kept(cemu):
    cemu.prepare()
    with open(cemu.profile) as f:
        profile = f.read()
    assert "<type>Wii U GamePad</type>" in profile and f"<uuid>{PAD_UUID}</uuid>" in profile and "<api>SDLController</api>" in profile
    assert profile.count("<entry>") == 25
    write(cemu.profile, "mine")
    cemu.prepare()
    assert open(cemu.profile).read() == "mine"


def test_command_starts_the_game_fullscreen_with_its_own_folders(cemu):
    c = cemu.command("/roms/wiiu/-odd name.wua")
    assert c.argv == [cemu.executable, "-f", "-g", "/roms/wiiu/-odd name.wua"]
    assert c.env == {"XDG_CONFIG_HOME": cemu.config_dir, "XDG_DATA_HOME": cemu.data_dir, "XDG_CACHE_HOME": cemu.cache_dir}
    assert cemu.settings.startswith(c.env["XDG_CONFIG_HOME"])
    assert not os.path.exists(os.path.join(cemu.home, "portable"))


def test_a_game_folder_is_launched_as_a_whole_and_an_archive_as_the_file(cemu, tmp_path):
    folder = tmp_path / "roms" / "wiiu" / "Game"
    for name in ("code", "content", "meta"):
        (folder / name).mkdir(parents=True)
    assert cemu.launch_file(Target(str(folder), True)) == str(folder)
    nus = tmp_path / "roms" / "wiiu" / "Nus"
    write(nus / "title.tmd", "x")
    write(nus / "00000001.app", "x" * 100)
    assert cemu.launch_file(Target(str(nus), True)) == str(nus / "title.tmd")
    pack = tmp_path / "roms" / "wiiu" / "Pack"
    write(pack / "game.wua", "x")
    assert cemu.launch_file(Target(str(pack), True)) == str(pack / "game.wua")
    assert cemu.launch_file(Target(str(tmp_path / "Game.wux"), False)) == str(tmp_path / "Game.wux")


def test_keys_are_optional_and_never_block_a_game(cemu):
    status = cemu.status()
    assert status["firmware"] and cemu.platform_ready("wiiu")
    assert status["bios"][0]["platform"] == "wiiu" and not status["bios"][0]["ready"] and status["bios"][0]["found"] == []


def test_add_firmware_takes_only_a_keys_file_whatever_it_is_called(cemu, tmp_path):
    assert cemu.add_firmware(write(tmp_path / "in" / "a.txt", "not keys")) is None
    assert cemu.add_firmware(write(tmp_path / "in" / "example.txt", f"# example\n{EXAMPLE_KEY} # example key\n")) is None
    assert cemu.add_firmware(str(tmp_path / "in" / "missing.txt")) is None
    assert cemu.add_firmware(write(tmp_path / "in" / "my wii u.txt", f"# disc keys\n{KEY[:16]}-{KEY[16:]} ; Game\n")).name == "keys.txt"
    assert cemu.bios_status()[0]["ready"] and cemu.bios_status()[0]["found"] == ["keys.txt"]


def test_prepare_gives_cemu_the_keys_from_the_bios_folder(cemu, tmp_path):
    write(cemu.keys, KEY + "\n")
    cemu.prepare()
    assert open(cemu.keys_in_use).read() == KEY + "\n"
    assert cemu.keys_in_use.startswith(cemu.env()["XDG_DATA_HOME"])


def test_keys_the_user_put_in_cemus_own_folder_count_too(cemu):
    write(cemu.keys_in_use, f"# keys\n{KEY}\n")
    cemu.prepare()
    assert cemu.bios_status()[0]["ready"] and open(cemu.keys_in_use).read() == f"# keys\n{KEY}\n"


def test_reset_and_uninstall_never_touch_saves_or_keys(cemu, tmp_path):
    write(cemu.keys, KEY)
    cemu.prepare()
    save = write(tmp_path / "saves" / "wiiu" / "cemu" / "00050000" / "10101c00" / "user" / "80000001" / "save", "save")
    xmlfile.update(cemu.settings, "content", values={"fullscreen": "false"})
    cemu.reset_config()
    assert xmlfile.read(cemu.settings, "fullscreen") == "true"
    cemu.uninstall(keep_settings=False)
    assert not os.path.exists(cemu.home)
    assert open(save).read() == "save" and open(cemu.keys).read() == KEY


def test_the_xml_reader_keeps_what_it_does_not_change(tmp_path):
    path = str(tmp_path / "settings.xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!-- cemu -->\n<content>\n    <mlc_path>/a &amp; b</mlc_path>\n'
                '    <Graphic><api>0</api><Overlay enabled="true"/></Graphic>\n    <GamePaths>\n        <Entry>/games</Entry>\n'
                "        <Entry>/more</Entry>\n    </GamePaths>\n    <empty></empty>\n</content>\n")
    xmlfile.update(path, "content", values={"Graphic/api": "1"}, defaults={"mlc_path": "/x", "Audio/api": "3"})
    assert xmlfile.read(path, "mlc_path") == "/a & b" and xmlfile.read(path, "Graphic/api") == "1" and xmlfile.read(path, "Audio/api") == "3"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "/a &amp; b" in text and '<Overlay enabled="true"/>' in text and text.count("<Entry>") == 2
    xmlfile.update(path, "content")
    with open(path, encoding="utf-8") as f:
        assert f.read() == text

    with open(path, "w", encoding="utf-8") as f:
        f.write("<content><broken></content>")
    xmlfile.update(path, "content", values={"fullscreen": "true"})
    assert xmlfile.read(path, "fullscreen") == "true" and xmlfile.read(path, "broken", "gone") == "gone"


def test_the_backend_uses_no_module_decky_does_not_ship():
    import pathlib

    root = pathlib.Path(__file__).parent.parent / "py_modules" / "boilerromm"
    using = [str(p.relative_to(root)) for p in root.rglob("*.py") if re.search(r"^\s*(import|from) xml\b", p.read_text(), re.M)]
    assert using == []
