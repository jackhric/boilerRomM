import os
import tomllib

import pytest

from boilerromm.emulators import Layout
from boilerromm.emulators.xenia import GAMERTAG, TAG, XUID, Xenia, account_file, read_account


@pytest.fixture
def xenia(tmp_path):
    return Xenia(Layout(str(tmp_path)))


def config(xenia):
    with open(xenia.toml, "rb") as f:
        return tomllib.load(f)


def test_the_build_is_the_projects_linux_appimage_at_a_pinned_commit(xenia):
    assert xenia.source.repo == "xenia-canary/xenia-canary" and xenia.source.tag == TAG
    assert xenia.executable.endswith("emulators/xenia/xenia.AppImage")
    assert Xenia.platforms == ("xbox360",) and not Xenia.firmware


def test_account_file_is_one_xenia_can_decrypt():
    data = account_file(GAMERTAG)
    assert len(data) == 0x18 + 0x17C
    assert read_account(data) == GAMERTAG
    assert read_account(data[:-1] + bytes([data[-1] ^ 1])) == ""
    assert read_account(b"") == ""


def test_prepare_points_xenia_at_the_shared_folders_and_signs_a_profile_in(xenia, tmp_path):
    xenia.prepare()
    saves = tmp_path / "saves" / "xbox360" / "xenia"
    assert config(xenia) == {
        "Storage": {"content_root": str(saves), "cache_root": str(tmp_path / "emulators" / "xenia" / "cache")},
        "Display": {"fullscreen": True},
        "Profiles": {"logged_profile_slot_0_xuid": XUID},
    }
    account = saves / XUID / "FFFE07D1" / "00010000" / XUID / "Account"
    assert read_account(account.read_bytes()) == GAMERTAG
    assert xenia.status()["configured"]


def test_prepare_again_keeps_the_users_settings_and_repoints_the_folders(xenia, tmp_path):
    xenia.prepare()
    with open(xenia.toml, "w", encoding="utf-8") as f:
        # The shape Xenia itself writes: every option, each with its description.
        f.write('[Display]\nfullscreen = false                \t# Whether to launch the emulator in fullscreen.\n\n'
                '[GPU]\ndraw_resolution_scale_x = 2           \t# Integer pixel width scale.\n'
                '                                             \t# 1, 2 and 3 are supported.\n'
                'gpu = "vulkan"\n\n'
                '[Profiles]\nlogged_profile_slot_0_xuid = "E030000000001234"\n\n'
                '[Storage]\ncontent_root = "/somewhere/else"\ncache_root = ""\n')
    xenia.prepare()
    after = config(xenia)
    assert after["Display"]["fullscreen"] is False
    assert after["GPU"] == {"draw_resolution_scale_x": 2, "gpu": "vulkan"}
    assert after["Profiles"]["logged_profile_slot_0_xuid"] == "E030000000001234"
    assert after["Storage"]["content_root"] == str(tmp_path / "saves" / "xbox360" / "xenia")
    assert after["Storage"]["cache_root"] == xenia.cache_dir


def test_a_profile_the_user_made_is_used_instead_of_making_one(xenia, tmp_path):
    theirs = "E0300000000ABCDE"
    package = tmp_path / "saves" / "xbox360" / "xenia" / theirs / "FFFE07D1" / "00010000" / theirs
    package.mkdir(parents=True)
    xenia.prepare()
    assert xenia.profiles() == [theirs]
    assert config(xenia)["Profiles"]["logged_profile_slot_0_xuid"] == theirs


def test_a_config_xenia_cannot_read_is_replaced(xenia):
    os.makedirs(xenia.config_dir)
    with open(xenia.toml, "w", encoding="utf-8") as f:
        f.write("[Display\nfullscreen = ")
    xenia.prepare()
    assert config(xenia)["Display"]["fullscreen"] is True


def test_reset_config_restores_defaults_and_leaves_the_profile_and_saves(xenia, tmp_path):
    xenia.prepare()
    xenia.write_config({"Display": {"fullscreen": False}})
    save = tmp_path / "saves" / "xbox360" / "xenia" / XUID / "4D5307E6" / "00000001" / "save" / "data.bin"
    save.parent.mkdir(parents=True)
    save.write_bytes(b"save")
    xenia.reset_config()
    assert config(xenia)["Display"]["fullscreen"] is True
    assert save.read_bytes() == b"save" and xenia.profiles() == [XUID]


def test_command_starts_the_game_fullscreen_with_its_own_config(xenia):
    c = xenia.command("/roms/xbox360/Some Game (USA).iso")
    assert c.argv == [xenia.executable, f"--config={xenia.toml}", "--fullscreen=true", "/roms/xbox360/Some Game (USA).iso"]
    assert c.env == {"XDG_CONFIG_HOME": xenia.config_dir, "XDG_DATA_HOME": xenia.data_dir, "XDG_CACHE_HOME": xenia.cache_dir}
    assert xenia.toml.startswith(xenia.config_dir)
