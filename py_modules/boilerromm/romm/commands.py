"""What `App` does with the RomM server: the address, pairing, the connection check and the library."""
import asyncio
import hashlib
import socket
import time

from ..romm.client import MIN_VERSION, RommClient, RommError, normalize_url, parse_version
from ..romm.library import Library
from ..romm.pairing import DevicePairing

LIBRARY_REFRESH_S = 600
# Waits between tries while the library cannot be loaded, so a server that comes back is noticed in seconds, not minutes.
LIBRARY_RETRY_S = (15, 30, 60, 120, 300)
CLIENT = "boilerromm"


def device_identity(version: str) -> dict:
    try:
        with open("/etc/machine-id") as f:
            machine = f.read().strip()
    except OSError:
        machine = socket.gethostname()
    return {
        "client_device_identifier": hashlib.sha256(machine.encode()).hexdigest()[:32],
        "name": socket.gethostname() or "Steam device",
        "client": CLIENT,
        "platform": "steamos",
        "client_version": version,
    }


class ServerCommands:
    async def set_server(self, url: str) -> dict:
        typed = url.strip().rstrip("/")
        if not typed:
            raise ValueError("Enter the RomM server address")
        if self.pairing:
            await self.pairing.cancel()
            self.pairing = None
        # An address typed without a protocol is tried over https, then over http if nothing there is RomM.
        candidates = [typed] if "://" in typed else [f"https://{typed}", f"http://{typed}"]
        for url in candidates:
            if self.client:
                await self.client.close()
            self.client = RommClient(url)
            await self._probe_server(emit=False)
            if self.server["version"]:
                break
        if not self.server["version"]:
            url = normalize_url(typed)
            if len(candidates) > 1:
                self.server["error"] = f"Nothing answered at {typed}"
        if self.settings.server_url != url:
            await self.prefetch.stop()
            self.settings = self.settings.for_server(url)
            self.store.save(self.settings)
            self.library = Library()
        self._changed()
        return self.state()

    async def _probe_server(self, emit: bool = True) -> None:
        assert self.client
        self.server = {"version": "", "error": ""}
        try:
            hb = await self.client.heartbeat()
            version = str(hb.get("SYSTEM", {}).get("VERSION", ""))
            self.server["version"] = version
            if parse_version(version) < MIN_VERSION:
                self.server["error"] = f"RomM {'.'.join(map(str, MIN_VERSION))} or newer is needed (this one is {version})"
        except RommError as e:
            self.server["error"] = f"Not a RomM server ({e.status})"
        except Exception as e:
            self.server["error"] = f"Cannot reach {self.client.base_url}: {e}"
        if emit:
            self._changed()

    async def check_connection(self) -> dict:
        """Asks the server now: does it answer, which version, and does it still accept this device's token."""
        result = {"reachable": False, "version": "", "supported": False, "signed_in": False, "username": "", "ms": 0, "error": ""}
        if not self.client:
            result["error"] = "No server is set"
            return result
        started = time.monotonic()
        await self._probe_server(emit=False)
        result["ms"] = round((time.monotonic() - started) * 1000)
        version = self.server["version"]
        result.update(reachable=bool(version), version=version, supported=bool(version) and not self.server["error"], error=self.server["error"])
        if version and self.settings.paired:
            try:
                me = await self.client.me()
                result.update(signed_in=True, username=(me or {}).get("username", ""))
            except RommError as e:
                result["error"] = "RomM no longer accepts this device; disconnect and pair again" if e.status in (401, 403) else f"RomM answered {e.status}"
            except Exception as e:
                result["error"] = str(e) or type(e).__name__
        self._changed()
        return result

    async def start_pairing(self) -> dict:
        if not self.client or self.server.get("error"):
            raise ValueError("Connect to a RomM server first")
        if not self.pairing:
            self.pairing = DevicePairing(self.client, self.identity, self._changed, self._approved)
        await self.pairing.start()
        return self.state()

    async def _approved(self, token: dict) -> None:
        assert self.client
        self.client.token = token["access_token"]
        self.settings.token = token["access_token"]
        self.settings.device_id = token["device_id"]
        self.settings.scopes = list(token.get("scopes", []))
        try:
            me = await self.client.me()
            self.settings.username = me.get("username", "") if me else ""
        except Exception as e:
            self.log.warning("users/me failed after pairing: %s", e)
        self.store.save(self.settings)
        await self._describe_device()
        self.pairing = None
        self._start_paired()

    async def _describe_device(self) -> None:
        assert self.client
        try:
            await self.client.update_device(self.settings.device_id, {
                "client": CLIENT, "client_version": self.version, "platform": "steamos",
                "hostname": self.identity["name"], "capabilities": {},
            })
        except Exception as e:
            self.log.warning("device update failed: %s", e)

    async def disconnect(self) -> dict:
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None
        await self.prefetch.stop()
        if self.downloader:
            await self.downloader.stop()
            self.downloader = None
        if self.pairing:
            await self.pairing.cancel()
            self.pairing = None
        if self.client:
            await self.client.close()
            self.client = None
        self.settings = self.settings.signed_out()
        self.store.save(self.settings)
        self.server = {"version": "", "error": ""}
        self.library = Library()
        self._changed()
        return self.state()

    async def refresh_library(self) -> dict:
        if self.settings.paired and self.client and not self.library.loading:
            self.library.loading = True
            self._changed()
            await self.library.refresh(self.client)
            if self.library.error and "401" in self.library.error:
                self.library.error = "RomM no longer accepts this device; disconnect and pair again"
            elif not self.library.error and self.sgdb and not self.sgdb_error and not self.prefetch.running:
                self.prefetch.start(self.sgdb, self.library.games.values())
            if not self.library.error and not self.server.get("version"):
                await self._probe_server(emit=False)
            self._changed()
            if not self.library.error:
                await self.adopt()
        return self.state()

    async def _refresh_loop(self) -> None:
        if not self.server.get("version"):
            await self._probe_server(emit=False)
        await self._describe_device()
        failures = 0
        while True:
            await self.refresh_library()
            failures = failures + 1 if self.library.error else 0
            await asyncio.sleep(LIBRARY_RETRY_S[min(failures, len(LIBRARY_RETRY_S)) - 1] if failures else LIBRARY_REFRESH_S)

    async def game_details(self, rom_id: int) -> dict:
        game = self.library.games.get(int(rom_id))
        if not game or not self.client:
            raise ValueError("Unknown game")
        return game.details(self.client)

    async def similar_games(self, rom_id: int) -> list[dict]:
        """Games in the library that resemble this one, from RomM's similarity graph."""
        if not self.client:
            return []
        out = []
        for r in await self.client.similar(int(rom_id)):
            sid = (r.get("rom") or {}).get("id")
            if sid in self.library.games:
                out.append({"rom_id": sid, "score": r.get("score", 0),
                            "reasons": [f"{x.get('facet', '')}: {x.get('value', '')}".strip(": ") for x in (r.get("reasons") or [])[:3]]})
        return out
