import logging
import os

import pytest
from boilerromm.app import App
from boilerromm.emulators.rpcs3 import PUP_MAGIC
from boilerromm.romm.client import RommError

PUP = PUP_MAGIC + b"firmware"


async def _noop(*a):
    pass


class FakeRomm:
    def __init__(self, files=None, me=None, heartbeat=None, md5=None):
        self.base_url = "https://romm"
        self.files = files or {}
        self.md5 = md5 or {}
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
        return [{"id": i, "file_name": name, "md5_hash": self.md5.get(name), "file_size_bytes": len(data)}
                for i, (name, (pid, data)) in enumerate(self.files.items(), 1) if pid == platform_id]

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
    from boilerromm.games.ledger import INSTALLED, QUEUED, Install

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


async def test_bios_from_romm_keeps_only_files_the_emulator_recognises(app):
    app.client = FakeRomm({"PS3UPDAT.PUP": (7, PUP), "readme.txt": (7, b"nothing"), "ps2.bin": (9, b"other platform")})
    state = await app.emulator_bios_install("rpcs3")
    rpcs3 = next(e for e in state["emulators"] if e["id"] == "rpcs3")
    assert rpcs3["error"] == "" and rpcs3["busy"] == ""
    assert rpcs3["bios"][0]["ready"] and rpcs3["bios"][0]["found"] == ["PS3UPDAT.PUP"]
    assert sorted(os.listdir(app.emulators["rpcs3"].layout.bios("ps3"))) == ["PS3UPDAT.PUP"]


async def test_bios_from_romm_says_why_nothing_was_kept(app):
    app.client = FakeRomm({"readme.txt": (7, b"nothing")})
    state = await app.emulator_bios_install("rpcs3")
    assert next(e for e in state["emulators"] if e["id"] == "rpcs3")["error"] == "None of RomM's files are ones it can use"

    app.client = FakeRomm({})
    state = await app.emulator_bios_install("rpcs3")
    assert next(e for e in state["emulators"] if e["id"] == "rpcs3")["error"] == "RomM has no firmware for this emulator"


async def test_bios_from_romm_needs_a_signed_in_device(app):
    app.settings.token = ""
    state = await app.emulator_bios_install("rpcs3")
    assert next(e for e in state["emulators"] if e["id"] == "rpcs3")["error"] == "Connect to RomM first"


def test_the_bios_folder_of_each_emulator_that_needs_one(app):
    needing = {e.id: [b["platform"] for b in e.status()["bios"]] for e in app.emulators.values()}
    assert needing == {"retroarch": ["saturn", "segacd", "3do"], "pcsx2": ["ps2"], "dolphin": [], "cemu": ["wiiu"], "rpcs3": ["ps3"], "shadps4": ["ps4"],
                       "kyty": [], "xenia": [], "lichii": ["switch"]}


def _game(rom_id, slug, platform):
    from boilerromm.romm.library import Game

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

    assert (await app.play_target(5))["blocked"] == "RPCS3 could not install its firmware. Try again in Settings, under BIOS Files."
    assert os.listdir(rpcs3.layout.bios("ps3")) == ["PS3UPDAT.PUP"]

    async def run(*args, timeout):
        os.makedirs(os.path.dirname(rpcs3.firmware_version_file))
        open(rpcs3.firmware_version_file, "w").close()
        return 0

    rpcs3.run = run
    assert (await app.play_target(5))["blocked"] == ""


async def test_a_game_stays_blocked_with_the_reason_when_romm_has_no_firmware(app):
    app.client = FakeRomm({})
    app.library.games[5] = _game(5, "ps2", "PlayStation 2")
    app.library.games[6] = _game(6, "vectrex9", "Odd")
    _installed(app.emulators["pcsx2"])
    target = await app.play_target(5)
    assert target["blocked"] == "PCSX2 needs a BIOS, and RomM did not have one. Add it in Settings, under BIOS Files."
    assert app.state()["emulators"][1]["error"] == ""
    assert app.launch_target(6)["blocked"] == "boilerRomM has no emulator for Odd."


async def test_installing_an_emulator_that_needs_firmware_shows_a_step_for_it(app, monkeypatch):
    app.client = FakeRomm({"PS3UPDAT.PUP": (7, PUP)})
    rpcs3 = app.emulators["rpcs3"]
    seen, installed = [], []

    async def install(session, tag=""):
        _installed(rpcs3)

    async def install_firmware():
        seen.append((app._emulator_busy.get("rpcs3"), os.listdir(rpcs3.layout.bios("ps3"))))
        installed.append(True)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    monkeypatch.setattr(rpcs3, "install", install)
    monkeypatch.setattr(rpcs3, "install_firmware", install_firmware)
    app._release_session = Session
    state = await app.emulator_install("rpcs3")
    assert seen == [("firmware", ["PS3UPDAT.PUP"])]
    assert next(e for e in state["emulators"] if e["id"] == "rpcs3")["busy"] == ""


def test_every_firmware_folder_says_which_files_it_expects(app):
    for emulator in app.emulators.values():
        for entry in emulator.bios_status():
            assert entry["expects"], (emulator.id, entry["platform"])


async def test_the_bios_page_is_told_which_of_romms_files_each_emulator_can_install(app):
    newest_usa, old_japan = "21038400dc633070a78ad53090c53017", "acf4730ceb38ac9d8c7d8e21f2614600"
    app.client = FakeRomm({"PS3UPDAT.PUP": (7, PUP), "notes.txt": (7, b"x"), "a.bin": (9, b"x"), "b.bin": (9, b"y"), "c.bin": (9, b"z")},
                          md5={"a.bin": old_japan, "b.bin": newest_usa, "c.bin": "0" * 32})
    available = await app.bios_available()
    assert [f["name"] for f in available["rpcs3"]] == ["PS3UPDAT.PUP"]
    assert [(f["name"], f["recommended"]) for f in available["pcsx2"]] == [("b.bin", True), ("a.bin", False)]
    assert available["lichii"] == [] and "dolphin" not in available

    app.settings.token = ""
    assert (await app.bios_available())["rpcs3"] == []


async def test_pcsx2_installs_one_bios_names_it_in_its_settings_and_can_remove_it(app):
    import hashlib

    from boilerromm.emulators import Firmware, inifile

    # Stand-ins for two real images: the names are what matter, so they are known by the checksum of made-up bytes.
    images = {name: name.encode() for name in ("ps2-0100j-20000117.bin", "ps2-0230a-20080220.bin")}
    md5 = {name: hashlib.md5(data).hexdigest() for name, data in images.items()}
    pcsx2 = app.emulators["pcsx2"]
    pcsx2.firmware = tuple(Firmware("ps2", name, md5[name]) for name in images)
    app.client = FakeRomm({name: (9, data) for name, data in images.items()}, md5=md5)

    state = await app.emulator_bios_install("pcsx2")
    status = next(e for e in state["emulators"] if e["id"] == "pcsx2")
    assert status["firmware_label"] == "ps2-0230a-20080220.bin" and os.listdir(pcsx2.layout.bios("ps2")) == ["ps2-0230a-20080220.bin"]
    assert inifile.read(pcsx2.ini, "Filenames", "BIOS") == "ps2-0230a-20080220.bin"

    japan = next(f["id"] for f in (await app.bios_available())["pcsx2"] if f["name"].startswith("ps2-0100j"))
    await app.emulator_bios_install("pcsx2", [japan])
    assert pcsx2.firmware_label() == "ps2-0100j-20000117.bin" and len(os.listdir(pcsx2.layout.bios("ps2"))) == 2

    state = await app.emulator_bios_uninstall("pcsx2")
    status = next(e for e in state["emulators"] if e["id"] == "pcsx2")
    assert os.listdir(pcsx2.layout.bios("ps2")) == [] and status["firmware_label"] == "" and not status["firmware"]


def test_emulators_are_listed_oldest_system_first(app):
    assert list(app.emulators) == ["retroarch", "pcsx2", "dolphin", "xenia", "rpcs3", "cemu", "shadps4", "lichii", "kyty"]
