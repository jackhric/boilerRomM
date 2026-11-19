import os

import pytest
from boilerromm.emulators import Layout, inifile
from boilerromm.emulators.lichii import SEEDED, TAG, Lichii

KEYS = b"# dumped keys\nheader_key = " + b"0f" * 32 + b"\nmaster_key_00 = " + b"1e" * 16 + b"\n"


@pytest.fixture
def lichii(tmp_path):
    return Lichii(Layout(str(tmp_path)))


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return str(path)


def test_the_build_is_the_plain_x86_64_appimage_of_a_pinned_release():
    import re
    names = ["lichii-linux-aarch64.AppImage", "lichii-linux-x86_64-pgo.AppImage", "lichii-linux-x86_64.tar.gz",
             "lichii-linux-x86_64.AppImage", "lichii-windows-x86_64.zip"]
    assert [n for n in names if re.search(Lichii.source.asset, n)] == ["lichii-linux-x86_64.AppImage"]
    assert Lichii.source.repo == "zortos293/Lichii" and Lichii.source.tag == TAG


def test_prepare_writes_a_config_that_starts_without_questions(lichii, tmp_path):
    lichii.prepare()
    assert lichii.ini == str(tmp_path / "emulators" / "lichii" / "config" / "lichii" / "qt-config.ini")
    for key, value in {"check_for_updates": "false", "confirmStop": "2", "show_whats_new": "false", "gui_hide_backend_warning": "true"}.items():
        assert inifile.read(lichii.ini, "UI", key) == value
        assert inifile.read(lichii.ini, "UI", key + "\\default") == "false"
    for key, value in SEEDED.items():
        assert inifile.read(lichii.ini, "Renderer", key) == value
        assert inifile.read(lichii.ini, "Renderer", key + "\\default") == "false"
    assert inifile.read(lichii.ini, "Data Storage", "save_directory") == str(tmp_path / "saves" / "switch" / "lichii")
    assert (tmp_path / "saves" / "switch" / "lichii").is_dir()


def test_prepare_again_keeps_the_users_settings_and_repoints_the_saves(lichii, tmp_path):
    lichii.prepare()
    inifile.update(lichii.ini, {"UI": {"confirmStop": "0"}, "Renderer": {"scaling_filter": "1", "resolution_setup": "4"},
                                "Data Storage": {"save_directory": "/somewhere/else"}})
    lichii.prepare()
    assert inifile.read(lichii.ini, "UI", "confirmStop") == "0"
    assert inifile.read(lichii.ini, "Renderer", "scaling_filter") == "1"
    assert inifile.read(lichii.ini, "Renderer", "resolution_setup") == "4"
    assert inifile.read(lichii.ini, "Data Storage", "save_directory") == str(tmp_path / "saves" / "switch" / "lichii")


def test_the_keys_folder_is_the_shared_one(lichii, tmp_path):
    lichii.prepare()
    assert os.path.realpath(lichii.keys_dir) == str(tmp_path / "bios" / "switch")
    assert lichii.keys_dir.startswith(lichii.env()["XDG_DATA_HOME"])
    lichii.prepare()
    assert os.path.islink(lichii.keys_dir)


def test_a_keys_folder_the_user_filled_is_left_alone(lichii):
    own = write(os.path.join(lichii.keys_dir, "prod.keys"), KEYS)
    lichii.prepare()
    assert not os.path.islink(lichii.keys_dir) and os.path.exists(own)
    assert lichii.firmware_ready()


def test_reset_config_leaves_keys_and_saves(lichii, tmp_path):
    lichii.prepare()
    keys = write(lichii.keys, KEYS)
    save = write(tmp_path / "saves" / "switch" / "lichii" / "user" / "save" / "0", b"save")
    inifile.update(lichii.ini, {"UI": {"confirmStop": "0"}})
    lichii.reset_config()
    assert inifile.read(lichii.ini, "UI", "confirmStop") == "2"
    assert os.path.exists(keys) and os.path.exists(save)


def test_command_starts_the_game_fullscreen_with_its_own_folders(lichii):
    c = lichii.command("/roms/switch/-odd name.nsp")
    assert c.argv == [lichii.executable, "-f", "-g", "/roms/switch/-odd name.nsp"]
    assert c.env == {"XDG_CONFIG_HOME": lichii.config_dir, "XDG_DATA_HOME": lichii.data_dir, "XDG_CACHE_HOME": lichii.cache_dir}
    assert lichii.ini.startswith(c.env["XDG_CONFIG_HOME"])


def test_ready_needs_keys_that_hold_the_header_key(lichii):
    status = lichii.status()
    assert not status["firmware"] and not status["ready"] and status["requires"] == "keys"
    write(lichii.keys, b"master_key_00 = " + b"1e" * 16 + b"\n")
    assert not lichii.firmware_ready()
    write(lichii.keys, KEYS)
    assert [f.name for f in lichii.firmware_found()] == ["prod.keys"]
    assert lichii.status()["firmware"] and not lichii.status()["ready"]
    write(lichii.executable, b"\x7fELF")
    write(lichii.version_file, TAG.encode())
    assert lichii.status()["ready"]


def test_add_firmware_takes_only_a_keys_file_whatever_it_is_called(lichii, tmp_path):
    assert lichii.add_firmware(write(tmp_path / "in" / "prod.keys", b"not keys")) is None
    assert lichii.add_firmware(str(tmp_path / "in" / "missing.keys")) is None
    assert lichii.add_firmware(write(tmp_path / "in" / "my switch.keys", KEYS)).name == "prod.keys"
    assert (tmp_path / "bios" / "switch" / "prod.keys").read_bytes() == KEYS
    assert lichii.firmware_ready()


def test_title_keys_are_kept_beside_the_keys_but_are_not_enough_alone(lichii, tmp_path):
    title = tmp_path / "anything.txt"
    title.write_text("0100000000010000000000000000000" + "5 = " + "ab" * 16 + "\n")
    assert lichii.add_firmware(str(title)).name == "title.keys"
    assert os.listdir(lichii.layout.bios("switch")) == ["title.keys"]
    assert not lichii.firmware_ready()
    assert lichii.bios_status()[0]["expects"] == "prod.keys, title.keys"
