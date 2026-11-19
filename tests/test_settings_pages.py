import asyncio
import logging
import os

import pytest

from boilerromm.app import App
from boilerromm.emulators.rpcs3 import PUP_MAGIC
from boilerromm.romm import RommError

PUP = PUP_MAGIC + b"firmware"


async def _noop(*a):
    pass


class FakeRomm:
    def __init__(self, files=None, me=None, heartbeat=None):
        self.base_url = "https://romm"
        self.files = files or {}
        self._me = me
        self._heartbeat = heartbeat

    async def heartbeat(self):
        if isinstance(self._heartbeat, Exception):
            raise self._heartbeat
        return self._heartbeat or {"SYSTEM": {"VERSION": "5.4.1"}}

    async def me(self):
        if isinstance(self._me, Exception):
            raise self._me
        return self._me or {"username": "ana"}

    async def platforms(self):
        return [{"id": 7, "fs_slug": "ps3"}, {"id": 9, "fs_slug": "ps2"}]

    async def firmware(self, platform_id):
        return [{"id": i, "file_name": name} for i, (name, (pid, _)) in enumerate(self.files.items(), 1) if pid == platform_id]

    async def fetch_firmware(self, firmware_id, file_name, dest):
        with open(dest, "wb") as f:
            f.write(self.files[file_name][1])

    async def close(self):
        pass


@pytest.fixture
def app(tmp_path):
    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), _noop, logging.getLogger("t"), data_dir=str(tmp_path / "data"))
    app.settings.server_url, app.settings.token, app.settings.device_id = "https://romm", "t", "d"
    return app


async def test_checking_the_connection_reports_what_the_server_said(app):
    app.client = FakeRomm()
    result = await app.check_connection()
    assert result | {"ms": 0} == {"reachable": True, "version": "5.4.1", "supported": True, "signed_in": True, "username": "ana", "ms": 0, "error": ""}
    assert app.state()["server"]["version"] == "5.4.1"


async def test_a_refused_token_and_an_old_or_absent_server_are_told_apart(app):
    app.client = FakeRomm(me=RommError(401, "no"))
    result = await app.check_connection()
    assert result["reachable"] and not result["signed_in"] and "no longer accepts" in result["error"]

    app.client = FakeRomm(heartbeat={"SYSTEM": {"VERSION": "4.0.0"}})
    result = await app.check_connection()
    assert result["reachable"] and not result["supported"] and "or newer" in result["error"]

    app.client = FakeRomm(heartbeat=OSError("down"))
    result = await app.check_connection()
    assert not result["reachable"] and not result["signed_in"] and "down" in result["error"]

    app.client = None
    assert (await app.check_connection())["error"] == "No server is set"


def test_storage_counts_installed_games_and_the_drive_of_the_rom_folder(app, tmp_path):
    from boilerromm.ledger import INSTALLED, QUEUED, Install

    # The folder does not exist yet: the drive of its nearest existing parent is reported.
    app.location.roms_dir = str(tmp_path / "later" / "roms")
    done = Install(rom_id=1, name="A", slug="ps2", fs_name="a.iso", single_file=True, state=INSTALLED, files=[{"path": "", "size": 5}])
    other = Install(rom_id=2, name="B", slug="ps2", fs_name="b.iso", single_file=True, state=QUEUED, files=[{"path": "", "size": 9}])
    for i in (done, other):
        app.ledger.put(i)
    path = app.location.target("ps2", "a.iso", True).path
    os.makedirs(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(b"12345")
    storage = app.state()["storage"]
    assert storage["used_bytes"] == 5
    assert storage["total_bytes"] >= storage["free_bytes"] > 0


async def test_rescanning_sends_the_state_again(tmp_path):
    sent = []

    async def emit(event, payload):
        sent.append(event)

    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"), data_dir=str(tmp_path / "data"))
    await app.rescan_bios()
    await asyncio.sleep(0)
    assert sent == ["boilerromm_state"]


async def test_bios_from_romm_keeps_only_files_the_emulator_recognises(app):
    app.client = FakeRomm({"PS3UPDAT.PUP": (7, PUP), "readme.txt": (7, b"nothing"), "ps2.bin": (9, b"other platform")})
    state = await app.emulator_bios_from_romm("rpcs3")
    rpcs3 = next(e for e in state["emulators"] if e["id"] == "rpcs3")
    assert rpcs3["error"] == "" and rpcs3["busy"] == ""
    assert rpcs3["bios"][0]["ready"] and rpcs3["bios"][0]["found"] == ["PS3UPDAT.PUP"]
    assert sorted(os.listdir(app.emulators["rpcs3"].layout.bios("ps3"))) == ["PS3UPDAT.PUP"]


async def test_bios_from_romm_says_why_nothing_was_kept(app):
    app.client = FakeRomm({"readme.txt": (7, b"nothing")})
    state = await app.emulator_bios_from_romm("rpcs3")
    assert next(e for e in state["emulators"] if e["id"] == "rpcs3")["error"] == "None of RomM's files are ones it can use"

    app.client = FakeRomm({})
    state = await app.emulator_bios_from_romm("rpcs3")
    assert next(e for e in state["emulators"] if e["id"] == "rpcs3")["error"] == "RomM has no firmware for this emulator"


async def test_bios_from_romm_needs_a_signed_in_device(app):
    app.settings.token = ""
    state = await app.emulator_bios_from_romm("rpcs3")
    assert next(e for e in state["emulators"] if e["id"] == "rpcs3")["error"] == "Connect to RomM first"


def test_the_bios_folder_of_each_emulator_that_needs_one(app):
    needing = {e.id: [b["platform"] for b in e.status()["bios"]] for e in app.emulators.values()}
    assert needing == {"retroarch": ["saturn", "segacd", "3do"], "pcsx2": ["ps2"], "dolphin": [], "rpcs3": ["ps3"], "shadps4": ["ps4"],
                       "kyty": [], "xenia": [], "lichii": ["switch"]}


def _game(rom_id, slug, platform):
    from boilerromm.library import Game

    return Game(rom_id=rom_id, name="G", platform_id=1, platform=platform, slug=slug, fs_name="g.iso", single_file=True, size_bytes=1, cover="")


def _installed(emulator):
    os.makedirs(emulator.home, exist_ok=True)
    for path in (emulator.executable, emulator.version_file):
        with open(path, "w") as f:
            f.write("1")


async def test_a_game_whose_emulator_lacks_firmware_gets_it_from_romm_before_it_starts(app):
    app.client = FakeRomm({"PS3UPDAT.PUP": (7, PUP)})
    app.library.games[5] = _game(5, "ps3", "PlayStation 3")
    rpcs3 = app.emulators["rpcs3"]
    assert app.launch_target(5)["blocked"] == "RPCS3 is not installed. Install it in Settings, under Emulators."
    _installed(rpcs3)
    assert "needs" in app.launch_target(5)["blocked"]

    assert (await app.play_target(5))["blocked"] == ""
    assert os.listdir(rpcs3.layout.bios("ps3")) == ["PS3UPDAT.PUP"]


async def test_a_game_stays_blocked_with_the_reason_when_romm_has_no_firmware(app):
    app.client = FakeRomm({})
    app.library.games[5] = _game(5, "ps2", "PlayStation 2")
    app.library.games[6] = _game(6, "vectrex9", "Odd")
    _installed(app.emulators["pcsx2"])
    target = await app.play_target(5)
    assert target["blocked"] == "PCSX2 needs a BIOS, and RomM did not have one. Add it in Settings, under BIOS."
    assert app.state()["emulators"][1]["error"] == ""
    assert app.launch_target(6)["blocked"] == "boilerRomM has no emulator for Odd."
