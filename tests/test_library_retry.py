import asyncio
import logging

import pytest
from boilerromm.app import App
from boilerromm.romm import commands as appmod
from boilerromm.settings import Settings


class FlakyClient:
    base_url = "https://romm.test"

    def __init__(self):
        self.down = True
        self.calls = 0

    async def platforms(self):
        self.calls += 1
        if self.down:
            raise ConnectionError("Cannot connect to host romm.test:443 ssl:default [Temporary failure in name resolution]")
        return [{"id": 1, "name": "P", "fs_slug": "psx", "rom_count": 1}]

    async def roms(self):
        return [{"id": 1, "name": "G", "platform_id": 1, "platform_display_name": "P", "platform_slug": "psx", "fs_name": "G.bin"}]

    async def recommendations(self):
        return []

    async def heartbeat(self):
        return {"SYSTEM": {"VERSION": "4.9.0"}}


class SilentFailure(FlakyClient):
    async def platforms(self):
        raise asyncio.TimeoutError()


async def _noop(*a):
    pass


def make(tmp_path, client) -> App:
    app = App(str(tmp_path / "settings.json"), "1", str(tmp_path), _noop, logging.getLogger("t"))
    app.settings = Settings(server_url="https://romm.test", token="t", device_id="d", username="u")
    app.client = client
    return app


@pytest.mark.asyncio
async def test_a_manual_refresh_after_a_failure_clears_the_error(tmp_path):
    client = FlakyClient()
    app = make(tmp_path, client)
    out = await app.refresh_library()
    assert "name resolution" in out["library"]["error"] and not out["library"]["loading"]
    client.down = False
    out = await app.refresh_library()
    assert out["library"]["error"] == "" and len(out["library"]["games"]) == 1
    assert app.server["version"] == "4.9.0"


@pytest.mark.asyncio
async def test_a_failed_refresh_keeps_the_games_already_loaded(tmp_path):
    client = FlakyClient()
    client.down = False
    app = make(tmp_path, client)
    await app.refresh_library()
    client.down = True
    out = await app.refresh_library()
    assert out["library"]["error"] and len(out["library"]["games"]) == 1


@pytest.mark.asyncio
async def test_an_error_with_no_message_still_says_something(tmp_path):
    app = make(tmp_path, SilentFailure())
    assert (await app.refresh_library())["library"]["error"] == "TimeoutError"


@pytest.mark.asyncio
async def test_loading_is_announced_before_the_request_goes_out(tmp_path):
    seen = []
    app = make(tmp_path, FlakyClient())
    app._changed = lambda: seen.append(app.library.loading)
    await app.refresh_library()
    assert seen[0] is True and seen[-1] is False


@pytest.mark.asyncio
async def test_the_loop_retries_soon_after_a_failure_and_backs_off(tmp_path, monkeypatch):
    waits = []

    async def fake_sleep(s):
        waits.append(s)
        if len(waits) == 8:
            raise asyncio.CancelledError

    client = FlakyClient()
    app = make(tmp_path, client)
    app.server = {"version": "4.9.0", "error": ""}
    monkeypatch.setattr(appmod.asyncio, "sleep", fake_sleep)
    app._describe_device = _noop
    with pytest.raises(asyncio.CancelledError):
        await app._refresh_loop()
    assert waits == [15, 30, 60, 120, 300, 300, 300, 300]
    assert client.calls == 8

    waits.clear()
    client.down = False
    with pytest.raises(asyncio.CancelledError):
        await app._refresh_loop()
    assert waits[0] == appmod.LIBRARY_REFRESH_S
