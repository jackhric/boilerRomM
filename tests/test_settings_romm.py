import os

from boilerromm.romm.client import RommError, normalize_url, parse_version
from boilerromm.settings import Settings, SettingsStore


def test_settings_round_trip_is_private(tmp_path):
    store = SettingsStore(str(tmp_path / "settings.json"))
    assert store.load() == Settings()
    store.save(Settings(server_url="https://r", token="t", device_id="d", roms_dir="~/roms"))
    assert oct(os.stat(store.path).st_mode & 0o777) == "0o600"
    loaded = store.load()
    assert loaded.paired and loaded.roms_dir == "~/roms"


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"server_url": "https://r", "future": 1}')
    assert SettingsStore(str(path)).load().server_url == "https://r"


def test_url_and_version_helpers():
    assert normalize_url(" romm.example.com/ ") == "https://romm.example.com"
    assert normalize_url("http://10.0.0.5:8080/") == "http://10.0.0.5:8080"
    assert parse_version("5.4.1") == (5, 4, 1)
    assert parse_version("5.4.1-rc1") == (5, 4, 1)
    assert RommError(400, "slow_down").code == "slow_down"
    assert RommError(422, [{"msg": "x"}]).code == ""


def test_signing_out_keeps_every_setting_that_is_about_the_device(tmp_path):
    from dataclasses import fields

    from boilerromm.settings import Settings, SettingsStore

    account = {"server_url", "token", "device_id", "username", "scopes", "setup_done"}
    full = Settings(**{f.name: (["x"] if f.name == "scopes" else f"{f.name}-value") for f in fields(Settings)})
    out = full.signed_out()
    assert not out.paired
    for f in fields(Settings):
        assert getattr(out, f.name) == (type(getattr(Settings(), f.name))() if f.name in account else getattr(full, f.name)), f.name
    moved = full.for_server("https://other")
    assert moved.server_url == "https://other" and moved.token == "" and moved.sgdb_key == "sgdb_key-value"

    store = SettingsStore(str(tmp_path / "s" / "settings.json"))
    store.save(full)
    assert store.load() == full
    assert oct((tmp_path / "s" / "settings.json").stat().st_mode & 0o777) == "0o600"
    assert [n for n in (tmp_path / "s").iterdir() if n.name.startswith(".")] == []
