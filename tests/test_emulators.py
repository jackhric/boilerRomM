import hashlib
import os

import pytest
from boilerromm.emulators import Layout, Pcsx2, for_platform, inifile, releases
from boilerromm.emulators.pcsx2 import BIOS, TAG

BUILD = b"\x7fELF" + b"b" * 5000
NIGHTLY = "v2.9.183"
ASSET = "pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage"
ASSET_URL = "https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/" + ASSET


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
    def __init__(self, build=BUILD, digest=None, assets=None):
        sha = digest if digest is not None else "sha256:" + hashlib.sha256(BUILD).hexdigest()
        self.build = build
        self.release = {"tag_name": TAG, "assets": assets if assets is not None else [
            {"name": "pcsx2-v2.8.2-windows-x64-Qt.7z", "size": 1, "digest": None, "browser_download_url": "https://x/win"},
            {"name": ASSET, "size": len(BUILD), "digest": sha, "browser_download_url": ASSET_URL},
        ]}
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append(url)
        base = f"{releases.API}/repos/PCSX2/pcsx2/releases"
        if url == f"{base}/tags/{TAG}":
            return FakeResponse(200, self.release)
        if url == f"{base}/tags/{NIGHTLY}":
            return FakeResponse(200, {**self.release, "tag_name": NIGHTLY})
        if url == f"{base}/latest":
            return FakeResponse(200, {**self.release, "published_at": "2026-09-04T23:04:48Z"})
        if url.startswith(f"{base}?per_page="):
            asset = self.release["assets"][-1:]
            return FakeResponse(200, [
                {"tag_name": NIGHTLY, "prerelease": True, "published_at": "2026-11-18T01:00:00Z", "assets": asset},
                {"tag_name": "v2.9.182", "prerelease": True, "published_at": "2026-11-18T00:00:00Z", "assets": []},
                {"tag_name": "v2.9.181", "prerelease": True, "draft": True, "published_at": None, "assets": asset},
            ])
        if url == ASSET_URL:
            return FakeResponse(200, self.build)
        return FakeResponse(404, {})


@pytest.fixture
def pcsx2(tmp_path):
    return Pcsx2(Layout(str(tmp_path)))


def bios_file(folder, content=b"a ps2 bios"):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "whatever-the-user-called-it.bin")
    with open(path, "wb") as f:
        f.write(content)
    return path


def test_layout_and_registry(tmp_path):
    layout = Layout(str(tmp_path))
    assert layout.bios("ps2") == str(tmp_path / "bios" / "ps2")
    assert layout.saves("ps2", "pcsx2") == str(tmp_path / "saves" / "ps2" / "pcsx2")
    assert layout.states("ps2", "pcsx2") == str(tmp_path / "states" / "ps2" / "pcsx2")
    assert isinstance(for_platform("ps2", layout), Pcsx2)
    assert for_platform("dreamcast", layout) is None


async def test_install_fetches_the_pinned_build_and_makes_it_executable(pcsx2):
    github = FakeGitHub()
    assert pcsx2.version == "" and not pcsx2.status()["installed"]
    assert await pcsx2.install(github) == TAG
    with open(pcsx2.executable, "rb") as f:
        assert f.read() == BUILD
    assert os.access(pcsx2.executable, os.X_OK)
    assert pcsx2.version == TAG
    assert github.calls == [f"{releases.API}/repos/PCSX2/pcsx2/releases/tags/{TAG}", ASSET_URL]


@pytest.mark.parametrize("github, message", [
    (FakeGitHub(digest="sha256:" + "0" * 64), "checksum"),
    (FakeGitHub(build=BUILD[:100]), "expected"),
    (FakeGitHub(assets=[]), "no asset"),
])
async def test_a_build_that_does_not_match_its_release_is_not_installed(pcsx2, github, message):
    with pytest.raises(releases.ReleaseError, match=message):
        await pcsx2.install(github)
    assert pcsx2.version == ""
    assert not os.path.exists(pcsx2.executable) and not os.path.exists(pcsx2.executable + ".part")


async def test_versions_offer_the_tested_build_first_then_what_the_project_publishes(pcsx2):
    assert await pcsx2.versions(FakeGitHub()) == [
        {"tag": TAG, "name": TAG, "prerelease": False, "published": "2026-09-04", "tested": True},
        {"tag": NIGHTLY, "name": NIGHTLY, "prerelease": True, "published": "2026-11-18", "tested": False},
    ]


async def test_install_takes_a_chosen_version_over_the_tested_one(pcsx2):
    assert await pcsx2.install(FakeGitHub(), NIGHTLY) == NIGHTLY
    assert pcsx2.version == NIGHTLY
    assert await pcsx2.install(FakeGitHub()) == TAG
    assert pcsx2.version == TAG


async def test_a_release_without_a_checksum_is_checked_by_size(pcsx2):
    assert await pcsx2.install(FakeGitHub(digest="")) == TAG


def test_prepare_writes_a_config_that_skips_the_setup_wizard(pcsx2, tmp_path):
    pcsx2.prepare()
    assert inifile.read(pcsx2.ini, "UI", "SettingsVersion") == "1"
    assert inifile.read(pcsx2.ini, "UI", "SetupWizardIncomplete") == ""
    assert inifile.read(pcsx2.ini, "UI", "StartFullscreen") == "true"
    assert inifile.read(pcsx2.ini, "Folders", "Bios") == str(tmp_path / "bios" / "ps2")
    assert inifile.read(pcsx2.ini, "Folders", "MemoryCards") == str(tmp_path / "saves" / "ps2" / "pcsx2")
    assert inifile.read(pcsx2.ini, "Folders", "SaveStates") == str(tmp_path / "states" / "ps2" / "pcsx2")
    for folder in ("bios/ps2", "saves/ps2/pcsx2", "states/ps2/pcsx2", "emulators/pcsx2/config", "emulators/pcsx2/cache"):
        assert (tmp_path / folder).is_dir()


def test_prepare_again_keeps_the_users_settings_and_repoints_the_folders(pcsx2, tmp_path):
    pcsx2.prepare()
    inifile.update(pcsx2.ini, {"UI": {"StartFullscreen": "false"}, "EmuCore/GS": {"upscale_multiplier": "3"},
                               "Folders": {"Bios": "/somewhere/else"}})
    pcsx2.prepare()
    assert inifile.read(pcsx2.ini, "UI", "StartFullscreen") == "false"
    assert inifile.read(pcsx2.ini, "EmuCore/GS", "upscale_multiplier") == "3"
    assert inifile.read(pcsx2.ini, "Folders", "Bios") == str(tmp_path / "bios" / "ps2")


def test_reset_config_restores_defaults_and_leaves_saves_and_firmware(pcsx2, tmp_path):
    pcsx2.prepare()
    inifile.update(pcsx2.ini, {"UI": {"StartFullscreen": "false"}})
    card = tmp_path / "saves" / "ps2" / "pcsx2" / "Mcd001.ps2"
    card.write_bytes(b"save")
    bios = bios_file(pcsx2.layout.bios("ps2"))
    pcsx2.reset_config()
    assert inifile.read(pcsx2.ini, "UI", "StartFullscreen") == "true"
    assert card.read_bytes() == b"save" and os.path.exists(bios)


def test_command_runs_the_build_with_its_own_folders(pcsx2):
    c = pcsx2.command("/roms/ps2/-odd name.chd")
    assert c.argv == [pcsx2.executable, "-batch", "-fullscreen", "--", "/roms/ps2/-odd name.chd"]
    assert c.env == {"XDG_CONFIG_HOME": pcsx2.config_dir, "XDG_DATA_HOME": pcsx2.data_dir, "XDG_CACHE_HOME": pcsx2.cache_dir}
    assert pcsx2.ini.startswith(c.env["XDG_CONFIG_HOME"])


async def test_ready_needs_the_build_and_one_known_bios(pcsx2, monkeypatch):
    content = b"a ps2 bios"
    monkeypatch.setattr(Pcsx2, "firmware", (*Pcsx2.firmware[:1], type(Pcsx2.firmware[0])("ps2", "known.bin", hashlib.md5(content).hexdigest())))
    assert pcsx2.status() == {"id": "pcsx2", "name": "PCSX2", "system": "PlayStation 2", "platforms": ["ps2"], "installed": False, "version": "", "version_name": "",
                              "firmware": False, "requires": "a BIOS", "ready": False, "configured": False,
                              "bios": [{"platform": "ps2", "folder": pcsx2.layout.bios("ps2"), "found": [], "ready": False, "expects": "scph39001.bin, ps2-0230a-20080220.bin, …"}],
                              "firmware_installed": False, "year": 2000, "accepts": ".bin", "firmware_set": False, "firmware_label": ""}
    bios_file(pcsx2.layout.bios("ps2"), b"not a bios")
    assert not pcsx2.firmware_ready()
    bios_file(pcsx2.layout.bios("ps2"), content)
    assert [f.name for f in pcsx2.firmware_found()] == ["known.bin"]
    assert pcsx2.status()["firmware"] and not pcsx2.status()["ready"]
    await pcsx2.install(FakeGitHub())
    assert pcsx2.status()["ready"]


def test_add_firmware_takes_only_files_it_knows(pcsx2, tmp_path, monkeypatch):
    content = b"a ps2 bios"
    monkeypatch.setattr(Pcsx2, "firmware", (type(Pcsx2.firmware[0])("ps2", "known.bin", hashlib.md5(content).hexdigest()),))
    assert pcsx2.add_firmware(bios_file(str(tmp_path / "in"), b"something else")) is None
    assert pcsx2.add_firmware(bios_file(str(tmp_path / "in"), content)).name == "known.bin"
    assert (tmp_path / "bios" / "ps2" / "known.bin").read_bytes() == content


async def test_uninstall_keeps_settings_unless_told_and_never_touches_saves(pcsx2, tmp_path):
    await pcsx2.install(FakeGitHub())
    pcsx2.prepare()
    card = tmp_path / "saves" / "ps2" / "pcsx2" / "Mcd001.ps2"
    card.write_bytes(b"save")
    pcsx2.uninstall()
    assert pcsx2.version == "" and not os.path.exists(pcsx2.executable) and os.path.exists(pcsx2.ini)
    pcsx2.uninstall(keep_settings=False)
    assert not os.path.exists(pcsx2.home) and card.read_bytes() == b"save"


def test_the_bios_list_is_well_formed():
    assert len(BIOS) > 30
    assert all(len(md5) == 32 and name.endswith(".bin") for name, md5 in BIOS)


def pcsx2_of(state: dict) -> dict:
    return next(e for e in state["emulators"] if e["id"] == "pcsx2")


async def test_the_app_installs_uninstalls_and_resets_an_emulator_and_reports_failures(tmp_path):
    import logging

    from boilerromm.app import App

    states = []

    async def emit(name, state):
        states.append(pcsx2_of(state))

    class Session(FakeGitHub):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    sessions = [Session(assets=[]), Session(), Session(), Session()]
    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"),
              data_dir=str(tmp_path / "data"), release_session_factory=lambda: sessions.pop(0))
    assert pcsx2_of(app.state()) == {"id": "pcsx2", "name": "PCSX2", "system": "PlayStation 2", "platforms": ["ps2"], "installed": False, "version": "", "version_name": "",
                                           "firmware": False, "requires": "a BIOS", "ready": False, "configured": False,
                                     "bios": [{"platform": "ps2", "folder": app.emulators["pcsx2"].layout.bios("ps2"), "found": [], "ready": False, "expects": "scph39001.bin, ps2-0230a-20080220.bin, …"}],
                                     "firmware_installed": False, "year": 2000, "accepts": ".bin", "firmware_set": False, "firmware_label": "",
                                     "busy": "", "error": "", "progress": None}

    failed = pcsx2_of(await app.emulator_install("pcsx2"))
    assert not failed["installed"] and "no asset" in failed["error"] and failed["busy"] == ""

    done = pcsx2_of(await app.emulator_install("pcsx2"))
    assert done["installed"] and done["version"] == TAG and done["configured"] and done["error"] == ""
    assert str(tmp_path / "data" / "emulators" / "pcsx2") == app.emulators["pcsx2"].home

    assert [v["tag"] for v in await app.emulator_versions("pcsx2")] == [TAG, NIGHTLY]
    assert [v["tag"] for v in await app.emulator_versions("pcsx2")] == [TAG, NIGHTLY] and len(sessions) == 1
    assert pcsx2_of(await app.emulator_install("pcsx2", NIGHTLY))["version"] == NIGHTLY

    inifile.update(app.emulators["pcsx2"].ini, {"UI": {"StartFullscreen": "false"}})
    await app.emulator_reset("pcsx2")
    assert inifile.read(app.emulators["pcsx2"].ini, "UI", "StartFullscreen") == "true"

    gone = pcsx2_of(await app.emulator_uninstall("pcsx2"))
    assert not gone["installed"] and gone["configured"]
    with pytest.raises(ValueError):
        await app.emulator_install("nope")

    import asyncio
    await asyncio.sleep(0)
    assert "installing" in [s["busy"] for s in states]


def test_lichii_runs_both_switch_generations(tmp_path):
    from boilerromm.emulators import Lichii

    layout = Layout(str(tmp_path))
    assert isinstance(for_platform("switch", layout), Lichii)
    assert isinstance(for_platform("switch2", layout), Lichii)


async def test_install_all_reports_progress_and_one_failure_does_not_stop_the_rest(tmp_path, monkeypatch):
    import asyncio
    import logging

    from boilerromm import emulators as registry
    from boilerromm.app import App
    from boilerromm.emulators.base import Emulator

    installed = []

    class Fine(Emulator):
        id, name, platforms = "fine", "Fine", ("a",)

        async def install(self, session, tag=""):
            async with session.get("https://example/build") as r:
                async for _ in r.content.iter_chunked(4):
                    pass
            os.makedirs(self.home, exist_ok=True)
            for path in (self.executable, self.version_file):
                with open(path, "w") as f:
                    f.write("v1")
            installed.append(self.id)
            return "v1"

        def configure(self):
            pass

    class Broken(Fine):
        id, name = "broken", "Broken"

        async def install(self, session, tag=""):
            raise RuntimeError("the build host is down")

    class Later(Fine):
        id, name = "later", "Later"

    class Response:
        content_length = 12

        def __init__(self):
            self.content = self

        async def iter_chunked(self, n):
            for _ in range(0, 12, n):
                yield b"x" * n

    class Request:
        async def __aenter__(self):
            return Response()

        async def __aexit__(self, *a):
            return False

    class Session(Request):
        async def __aenter__(self):
            return self

        def get(self, url, **kw):
            return Request()

    monkeypatch.setattr(registry, "ALL", (Fine, Broken, Later))
    states = []

    async def emit(name, state):
        states.append({e["id"]: (e["busy"], e["progress"]) for e in state["emulators"]})

    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"),
              data_dir=str(tmp_path / "data"), release_session_factory=Session)
    app._progress_sent = -1.0
    monkeypatch.setattr("time.monotonic", lambda: 10.0 + len(states))

    first = await app.emulators_install_all()
    assert {e["id"]: e["busy"] for e in first["emulators"]} == {"fine": "queued", "broken": "queued", "later": "queued"}
    await app._install_all
    await asyncio.sleep(0)

    final = {e["id"]: e for e in app.state()["emulators"]}
    assert installed == ["fine", "later"]
    assert final["fine"]["installed"] and final["later"]["installed"] and not final["broken"]["installed"]
    assert "build host is down" in final["broken"]["error"] and final["fine"]["error"] == ""
    assert all(e["busy"] == "" and e["progress"] is None for e in final.values())
    assert any(s["fine"] == ("installing", (4, 12)) or s["fine"][1] in ((8, 12), (12, 12)) for s in states)
    assert (await app.emulators_install_all())["emulators"][1]["busy"] == "queued"
    await app._install_all


async def test_setup_is_done_once_finished_and_starts_over_after_signing_out(tmp_path):
    import logging

    from boilerromm.app import App

    async def emit(*a):
        pass

    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"), data_dir=str(tmp_path / "data"))
    assert app.state()["setup_done"] is False
    assert (await app.finish_setup())["setup_done"] is True
    again = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"), data_dir=str(tmp_path / "data"))
    assert again.state()["setup_done"] is True
    assert again.settings.signed_out().setup_done is False


async def test_reset_goes_back_to_a_fresh_install_but_keeps_the_games(tmp_path):
    import logging

    from boilerromm.app import App

    async def emit(*a):
        pass

    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"), data_dir=str(tmp_path / "data"))
    app.settings.server_url, app.settings.token, app.settings.device_id = "https://romm.test", "t", "d"
    app.settings.sgdb_key, app.settings.roms_dir = "k" * 32, str(tmp_path / "roms")
    await app.finish_setup()
    pcsx2 = app.emulators["pcsx2"]
    os.makedirs(pcsx2.home)
    for path in (pcsx2.executable, pcsx2.version_file):
        with open(path, "w") as f:
            f.write("1")
    os.makedirs(app.art.root)
    game = tmp_path / "roms" / "ps2" / "game.iso"
    game.parent.mkdir(parents=True)
    game.write_text("rom")

    state = await app.reset()

    assert state["setup_done"] is False and state["account"]["paired"] is False and state["sgdb"]["configured"] is False
    assert not any(e["installed"] for e in state["emulators"])
    assert not os.path.exists(pcsx2.home) and not os.path.exists(app.art.root)
    assert game.exists() and app.settings.roms_dir == str(tmp_path / "roms")
    fresh = App(str(tmp_path / "settings.json"), "1", str(tmp_path), emit, logging.getLogger("t"), data_dir=str(tmp_path / "data"))
    assert (fresh.settings.server_url, fresh.settings.token, fresh.settings.sgdb_key) == ("", "", "")
