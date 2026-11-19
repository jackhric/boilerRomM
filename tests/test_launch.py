import logging
import os
import subprocess

from boilerromm.app import App

LAUNCHER = os.path.join(os.path.dirname(__file__), "..", "bin", "boilerromm-launch")


async def _noop(*a):
    pass


def make_app(tmp_path) -> App:
    app = App(str(tmp_path / "settings" / "settings.json"), "1", str(tmp_path), _noop, logging.getLogger("t"),
              data_dir=str(tmp_path / "data"))
    app.install_launcher(LAUNCHER, str(tmp_path / "data"))
    return app


def fake_build(emulator) -> None:
    """Stands in for an installed emulator: prints what it was started with."""
    os.makedirs(emulator.home, exist_ok=True)
    with open(emulator.executable, "w") as f:
        f.write('#!/bin/bash\necho "config=$XDG_CONFIG_HOME"\nprintf "arg=%s\\n" "$@"\n')
    os.chmod(emulator.executable, 0o755)
    with open(emulator.version_file, "w") as f:
        f.write("v1")


def run(app: App, rom_id) -> subprocess.CompletedProcess:
    return subprocess.run([app.launcher, str(rom_id)], capture_output=True, text=True)


def test_roms_live_under_the_data_folder_by_default(tmp_path):
    app = make_app(tmp_path)
    assert app.location.roms_dir == str(tmp_path / "data" / "roms")
    assert app.location.platform_dir("ngc") == str(tmp_path / "data" / "roms" / "ngc")
    assert "retrodeck" not in app.state()


def test_the_launcher_runs_a_game_through_its_platforms_emulator(tmp_path):
    app = make_app(tmp_path)
    pcsx2 = app.emulators["pcsx2"]
    fake_build(pcsx2)
    target = app.location.target("ps2", "It's a Game (USA).chd", single_file=True)
    os.makedirs(os.path.dirname(target.path))
    open(target.path, "wb").close()
    app.write_launch_script("ps2", 32, target)

    out = run(app, 32)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == [f"config={pcsx2.config_dir}", "arg=-batch", "arg=-fullscreen", "arg=--", f"arg={target.path}"]
    assert os.path.exists(pcsx2.ini)


def test_the_launcher_refuses_a_game_that_is_still_downloading_or_gone(tmp_path):
    app = make_app(tmp_path)
    fake_build(app.emulators["pcsx2"])
    target = app.location.target("ps2", "Game.chd", single_file=True)
    os.makedirs(os.path.dirname(target.path))
    app.write_launch_script("ps2", 7, target)
    assert run(app, 7).returncode == 1 and "not on this device" in run(app, 7).stderr
    open(target.path + ".part", "wb").close()
    assert "still downloading" in run(app, 7).stderr


def test_the_launcher_says_why_when_there_is_no_emulator_to_run_a_game(tmp_path):
    app = make_app(tmp_path)
    target = app.location.target("ps2", "Game.chd", single_file=True)
    app.write_launch_script("ps2", 1, target)
    assert run(app, 1).returncode == 1 and "PCSX2 is not installed" in run(app, 1).stderr
    app.write_launch_script("dreamcast", 2, app.location.target("dreamcast", "Game.chd", single_file=True))
    assert "no emulator for dreamcast" in run(app, 2).stderr
    assert run(app, 99).returncode == 1 and "nothing to launch" in run(app, 99).stderr
    assert run(app, "x; rm -rf /").returncode == 2


def test_each_platform_goes_to_the_emulator_that_runs_it(tmp_path):
    app = make_app(tmp_path)
    picks = {slug: app.emulator_for(slug).id for slug in ("psx", "snes", "ps2", "ngc", "wii", "wiiu", "ps3", "ps4", "ps5", "xbox360", "switch", "switch2")}
    assert picks == {"psx": "retroarch", "snes": "retroarch", "ps2": "pcsx2", "ngc": "dolphin", "wii": "dolphin", "wiiu": "cemu", "ps3": "rpcs3",
                     "ps4": "shadps4", "ps5": "kyty", "xbox360": "xenia", "switch": "lichii", "switch2": "lichii"}
    assert app.emulator_for("dreamcast") is None


async def test_the_first_download_makes_our_own_rom_folder_but_not_a_chosen_one(tmp_path):
    import logging
    from types import SimpleNamespace

    import pytest
    from boilerromm.app import App

    async def emit(*a):
        pass

    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"), data_dir=str(tmp_path / "data"))
    added = []
    app.downloader = SimpleNamespace(add=lambda game, appid: added.append(game.rom_id), snapshot=lambda *a, **k: {"active": None, "queue": [], "items": []})
    app.library.games[53] = SimpleNamespace(rom_id=53, name="Halo 3", slug="xbox360")
    app.state = lambda: {}
    await app.download(53)
    assert added == [53] and (tmp_path / "data" / "roms").is_dir()

    await app.set_roms_dir(str(tmp_path / "sdcard" / "roms"))
    with pytest.raises(ValueError, match="does not exist"):
        await app.download(53)
    assert added == [53] and not (tmp_path / "sdcard").exists()
