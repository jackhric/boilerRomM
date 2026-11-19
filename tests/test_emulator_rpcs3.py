import json
import os
import re
import subprocess

import pytest

from boilerromm import inifile
from boilerromm.emulators import Layout
from boilerromm.emulators.rpcs3 import INSTALL_THEN_RUN, PUP_MAGIC, TAG, Rpcs3
from boilerromm.install import Target

PUP = PUP_MAGIC + b"the rest of a firmware update"


@pytest.fixture
def rpcs3(tmp_path):
    return Rpcs3(Layout(str(tmp_path)))


def write(path, content=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return str(path)


def vfs(rpcs3):
    with open(rpcs3.vfs, encoding="utf-8") as f:
        return f.read().splitlines()


def install_firmware(rpcs3):
    write(rpcs3.firmware_version_file, b"release:04.9300:\n")


def test_the_build_is_the_pinned_linux_appimage():
    assert Rpcs3.source.repo == "RPCS3/rpcs3-binaries-linux" and Rpcs3.source.tag == TAG
    assert re.fullmatch(r"build-[0-9a-f]{40}", TAG)
    assert re.search(Rpcs3.source.asset, "rpcs3-v0.0.43-20623-0ebb6369_linux64.AppImage")
    assert not re.search(Rpcs3.source.asset, "rpcs3-v0.0.43-20623-0ebb6369_linux64.AppImage.zsync")


def test_prepare_points_every_device_at_the_data_folder_and_skips_the_welcome_dialog(rpcs3, tmp_path):
    rpcs3.prepare()
    data = tmp_path / "emulators" / "rpcs3" / "data"
    lines = vfs(rpcs3)
    for device in ("dev_hdd0", "dev_hdd1", "dev_flash", "dev_flash2", "dev_flash3", "dev_bdvd", "games"):
        assert f"/{device}/: {json.dumps(str(data / device) + '/')}" in lines
        assert (data / device).is_dir()
    assert rpcs3.vfs == str(tmp_path / "emulators" / "rpcs3" / "config" / "rpcs3" / "vfs.yml")
    assert inifile.read(rpcs3.gui_ini, "main_window", "infoBoxEnabledWelcome") == "false"
    assert inifile.read(rpcs3.gui_ini, "main_window", "confirmationBoxExitGame") == "false"
    assert inifile.read(rpcs3.gui_ini, "Meta", "checkUpdateStart") == "false"


def test_saves_and_states_land_in_the_shared_folders(rpcs3, tmp_path):
    rpcs3.prepare()
    savedata = tmp_path / "emulators" / "rpcs3" / "data" / "dev_hdd0" / "home" / "00000001" / "savedata"
    savestates = tmp_path / "emulators" / "rpcs3" / "config" / "rpcs3" / "savestates"
    assert os.readlink(savedata) == str(tmp_path / "saves" / "ps3" / "rpcs3")
    assert os.readlink(savestates) == str(tmp_path / "states" / "ps3" / "rpcs3")
    (savedata / "BLUS30001-SAVE").mkdir()
    assert (tmp_path / "saves" / "ps3" / "rpcs3" / "BLUS30001-SAVE").is_dir()


def test_saves_the_emulator_already_wrote_are_moved_not_lost(rpcs3, tmp_path):
    savedata = tmp_path / "emulators" / "rpcs3" / "data" / "dev_hdd0" / "home" / "00000001" / "savedata"
    write(savedata / "BLUS30001-SAVE" / "PARAM.SFO", b"mine")
    rpcs3.prepare()
    assert savedata.is_symlink()
    assert (tmp_path / "saves" / "ps3" / "rpcs3" / "BLUS30001-SAVE" / "PARAM.SFO").read_bytes() == b"mine"


def test_prepare_again_keeps_the_users_settings_and_repoints_the_folders(rpcs3, tmp_path):
    rpcs3.prepare()
    inifile.update(rpcs3.gui_ini, {"main_window": {"confirmationBoxExitGame": "true", "infoBoxEnabledWelcome": "true"},
                                   "GameList": {"sortCol": "1"}})
    with open(rpcs3.vfs, "w", encoding="utf-8") as f:
        f.write("$(EmulatorDir): \"\"\n/dev_hdd0/: /somewhere/else/\n/app_home/: \"\"\n/dev_usb***/:\n  /dev_usb000:\n    Path: /media/stick/\n")
    moved = Rpcs3(Layout(str(tmp_path / "moved")))
    new_home = tmp_path / "moved" / "emulators" / "rpcs3"
    os.makedirs(new_home.parent)
    os.rename(rpcs3.home, new_home)
    moved.prepare()
    assert inifile.read(moved.gui_ini, "main_window", "confirmationBoxExitGame") == "true"
    assert inifile.read(moved.gui_ini, "main_window", "infoBoxEnabledWelcome") == "false"
    assert inifile.read(moved.gui_ini, "GameList", "sortCol") == "1"
    lines = vfs(moved)
    assert f"/dev_hdd0/: {json.dumps(moved.device('dev_hdd0') + '/')}" in lines
    assert len([line for line in lines if line.startswith("/dev_hdd0/:")]) == 1
    assert lines[-5:] == ['$(EmulatorDir): ""', '/app_home/: ""', "/dev_usb***/:", "  /dev_usb000:", "    Path: /media/stick/"]
    assert os.readlink(os.path.join(moved.settings_dir, "savestates")) == str(tmp_path / "moved" / "states" / "ps3" / "rpcs3")


def test_reset_config_leaves_saves_states_and_installed_firmware(rpcs3, tmp_path):
    rpcs3.prepare()
    install_firmware(rpcs3)
    inifile.update(rpcs3.gui_ini, {"main_window": {"confirmationBoxExitGame": "true"}})
    save = write(tmp_path / "saves" / "ps3" / "rpcs3" / "BLUS30001-SAVE" / "PARAM.SFO", b"save")
    state = write(tmp_path / "states" / "ps3" / "rpcs3" / "BLUS30001" / "a.SAVESTAT", b"state")
    rpcs3.reset_config()
    assert inifile.read(rpcs3.gui_ini, "main_window", "confirmationBoxExitGame") == "false"
    assert os.path.exists(save) and os.path.exists(state) and rpcs3.firmware_installed
    assert os.path.exists(os.path.join(rpcs3.settings_dir, "savestates", "BLUS30001", "a.SAVESTAT"))


def test_firmware_is_a_pup_in_the_bios_folder_or_one_already_installed(rpcs3):
    assert not rpcs3.firmware_ready() and not rpcs3.status()["firmware"]
    write(os.path.join(rpcs3.layout.bios("ps3"), "readme.txt"), b"not a firmware")
    assert rpcs3.firmware_found() == [] and not rpcs3.firmware_ready()
    write(os.path.join(rpcs3.layout.bios("ps3"), "whatever.pup"), PUP)
    assert [f.name for f in rpcs3.firmware_found()] == ["whatever.pup"]
    assert rpcs3.firmware_ready() and not rpcs3.firmware_installed
    os.unlink(os.path.join(rpcs3.layout.bios("ps3"), "whatever.pup"))
    install_firmware(rpcs3)
    assert rpcs3.firmware_ready() and rpcs3.firmware_installed and rpcs3.status()["firmware"]


def test_add_firmware_takes_only_a_pup(rpcs3, tmp_path):
    assert rpcs3.add_firmware(write(tmp_path / "in" / "bios.bin", b"something else")) is None
    assert rpcs3.add_firmware(str(tmp_path / "in" / "missing.pup")) is None
    assert rpcs3.add_firmware(write(tmp_path / "in" / "update.pup", PUP)).name == "PS3UPDAT.PUP"
    assert (tmp_path / "bios" / "ps3" / "PS3UPDAT.PUP").read_bytes() == PUP
    assert rpcs3.firmware_ready()


def test_command_runs_the_game_without_the_gui_once_firmware_is_installed(rpcs3):
    install_firmware(rpcs3)
    c = rpcs3.command("/roms/ps3/Game [BLUS30001]")
    assert c.argv == [rpcs3.executable, "--no-gui", "--fullscreen", "/roms/ps3/Game [BLUS30001]"]
    assert c.env == {"XDG_CONFIG_HOME": rpcs3.config_dir, "XDG_DATA_HOME": rpcs3.data_dir, "XDG_CACHE_HOME": rpcs3.cache_dir}
    assert rpcs3.vfs.startswith(c.env["XDG_CONFIG_HOME"])


def test_command_installs_the_firmware_first_when_it_is_not_yet(rpcs3, tmp_path):
    pup = write(os.path.join(rpcs3.layout.bios("ps3"), "my firmware.PUP"), PUP)
    c = rpcs3.command("/roms/ps3/game.iso")
    assert c.argv == ["/bin/sh", "-c", INSTALL_THEN_RUN, rpcs3.executable, rpcs3.firmware_version_file, pup, "/roms/ps3/game.iso"]

    # A stand-in emulator that records how it was called and "installs" on --installfw, failing as the real one does.
    log = tmp_path / "calls"
    os.makedirs(rpcs3.home)
    with open(rpcs3.executable, "w") as f:
        f.write(f'#!/bin/sh\necho "$@" >> "{log}"\n[ "$1" = --headless ] && mkdir -p "{os.path.dirname(rpcs3.firmware_version_file)}" '
                f'&& touch "{rpcs3.firmware_version_file}" && exit 143\nexit 0\n')
    os.chmod(rpcs3.executable, 0o755)
    subprocess.run(c.argv, check=True)
    subprocess.run(c.argv, check=True)
    assert log.read_text().splitlines() == [f"--headless --installfw {pup}", "--no-gui --fullscreen /roms/ps3/game.iso",
                                            "--no-gui --fullscreen /roms/ps3/game.iso"]


def test_command_without_any_firmware_still_starts_the_emulator(rpcs3, tmp_path):
    c = rpcs3.command("/roms/ps3/game.iso")
    assert c.argv[4:] == [rpcs3.firmware_version_file, str(tmp_path / "bios" / "ps3" / "PS3UPDAT.PUP"), "/roms/ps3/game.iso"]


def test_launch_file_is_the_game_folder_an_iso_or_the_file_itself(rpcs3, tmp_path):
    assert rpcs3.launch_file(Target(str(tmp_path / "game.iso"), False)) == str(tmp_path / "game.iso")

    disc = tmp_path / "Disc Game"
    write(disc / "PS3_DISC.SFB", b"x" * 100)
    write(disc / "PS3_GAME" / "USRDIR" / "EBOOT.BIN", b"x")
    assert rpcs3.launch_file(Target(str(disc), True)) == str(disc)

    nested = tmp_path / "Nested Game"
    write(nested / "notes.txt", b"x" * 100)
    write(nested / "NPUB30001" / "USRDIR" / "EBOOT.BIN", b"x")
    assert rpcs3.launch_file(Target(str(nested), True)) == str(nested / "NPUB30001")

    image = tmp_path / "Image Game"
    write(image / "game.dkey", b"k")
    write(image / "game.iso", b"x" * 100)
    assert rpcs3.launch_file(Target(str(image), True)) == str(image / "game.iso")
