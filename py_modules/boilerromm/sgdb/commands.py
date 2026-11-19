"""What `App` does with SteamGridDB: the key, signing in for it, and a game's art and icon."""
import base64
import os
from typing import Any

from ..core import Core
from ..romm.library import Game
from ..sgdb.client import KINDS as ART_KINDS
from ..sgdb.client import SgdbClient, SgdbError


class ArtworkCommands(Core):
    def _sgdb_client(self, key: str) -> SgdbClient:
        return SgdbClient(key, self._sgdb_session, f"boilerRomM/{self.version}")

    def _art_failed(self, e: SgdbError) -> None:
        self.sgdb_error = e.message
        self.log.warning("SteamGridDB prefetch stopped: %s", e.message)

    async def set_sgdb_key(self, key: str) -> dict[str, Any]:
        """Saves the key only once SteamGridDB accepts it; a refused key shows up as `sgdb.error`, never raises."""
        key = (key or "").strip()
        if not key:
            self.sgdb_error = "Enter a SteamGridDB API key"
            return self.state()
        client = self._sgdb_client(key)
        try:
            await client.verify()
        except SgdbError as e:
            await client.close()
            self.sgdb_error = "Invalid SteamGridDB key" if e.status in (401, 403) else e.message
            self._changed()
            return self.state()
        await self.prefetch.stop()
        if self.sgdb:
            await self.sgdb.close()
        self.sgdb, self.sgdb_error = client, ""
        self.settings.sgdb_key = key
        self.store.save(self.settings)
        if self.library.games:
            self.prefetch.start(client, self.library.games.values())
        self._changed()
        return self.state()

    async def _signin_key(self, key: str) -> str:
        await self.set_sgdb_key(key)
        return "" if self.sgdb is not None and not self.sgdb_error else (self.sgdb_error or "SteamGridDB did not accept the key")

    async def start_sgdb_signin(self) -> dict[str, Any]:
        self.signin.start()
        return self.state()

    async def cancel_sgdb_signin(self) -> dict[str, Any]:
        await self.signin.cancel()
        return self.state()

    async def clear_sgdb_key(self) -> dict[str, Any]:
        await self.prefetch.stop()
        if self.sgdb:
            await self.sgdb.close()
        self.sgdb, self.sgdb_error = None, ""
        self.settings.sgdb_key = ""
        self.store.save(self.settings)
        self._changed()
        return self.state()

    async def _art_entry(self, game: Game) -> dict[str, Any] | None:
        """The game's cache entry, looked up now when missing; None without a key or when the lookup failed."""
        entry = self.art.get(game.rom_id, game.sgdb_id, game.name)
        if entry or not self.sgdb:
            return entry
        try:
            entry, fetched = await self.art.ensure(self.sgdb, game.rom_id, game.sgdb_id, game.name)
        except SgdbError as e:
            if e.status == 401:
                self.sgdb_error = "Invalid SteamGridDB key"
                self._changed()
            self.log.warning("SteamGridDB art for %s: %s", game.name, e.message)
            return None
        if fetched:
            self._changed()
        return entry

    async def game_art(self, rom_id: int) -> dict[str, Any]:
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        entry = await self._art_entry(game)
        urls = {k: (entry or {}).get(k, "") for k in ART_KINDS}
        sgdb_id = (entry or {}).get("sgdb_id") or game.sgdb_id
        return {"rom_id": game.rom_id, "sgdb_id": sgdb_id, **urls, "ready": self.sgdb is not None}

    async def art_base64(self, rom_id: int, kind: str) -> dict[str, Any]:
        if kind not in ART_KINDS:
            raise ValueError(f"Unknown art kind {kind!r}")
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        entry = await self._art_entry(game)
        if not entry or not entry.get(kind) or not entry.get("sgdb_id"):
            return {"base64": "", "format": ""}
        cached = self.art.image(entry["sgdb_id"], kind)
        if cached:
            data, fmt = cached
        else:
            client = self.sgdb or self._cdn
            if client is None:
                client = self._cdn = self._sgdb_client("")
            try:
                data, fmt = await client.fetch_image(entry[kind])
            except SgdbError as e:
                self.log.warning("SteamGridDB %s of %s: %s", kind, game.name, e.message)
                return {"base64": "", "format": ""}
            try:
                self.art.write_image(entry["sgdb_id"], kind, data, fmt)
            except OSError as e:
                self.log.warning("art cache not written: %s", e)
        return {"base64": base64.b64encode(data).decode(), "format": fmt}

    def _icon_path(self, rom_id: int) -> str:
        return os.path.join(self.runtime_dir, "icons", f"{int(rom_id)}.png") if self.runtime_dir else ""

    def save_icon(self, rom_id: int, data_base64: str) -> str:
        """Writes a shortcut icon drawn by the frontend; Steam takes a shortcut's icon only as a file path."""
        path = self._icon_path(rom_id)
        data = base64.b64decode(data_base64 or "", validate=True)
        if not path or not data.startswith(b"\x89PNG") or len(data) > 4 * 1024 * 1024:
            raise ValueError("Not a PNG icon")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        return path
