"""What `App` does with games on the device: what is installed, downloads, shortcuts, trailers and covers."""
import asyncio
import base64
import os
import shutil
from dataclasses import dataclass

from ..games import ledger as L
from ..games.downloads import as_game, manifest
from ..games.install import InstallLocation, Target
from ..games.ledger import Install


@dataclass(frozen=True)
class Held:
    """A ledger record with what the disk says about it."""
    install: Install
    target: Target
    seen: L.Check
    state: str


class GameCommands:
    def _target(self, install: Install) -> Target:
        return self.location.target(install.slug, install.fs_name, install.single_file)

    def held(self) -> dict[int, "Held"]:
        """Every record held against the disk once; a snapshot shares one of these between its parts."""
        out = {}
        for i in self.ledger.all():
            target = self._target(i)
            seen = L.check(i, target.path)
            # An installed game with files gone reads as incomplete.
            state = L.INCOMPLETE if i.state == L.INSTALLED and not seen.complete else i.state
            out[i.rom_id] = Held(i, target, seen, state)
        return out

    def status(self, rom_id: int, held: dict[int, "Held"] | None = None) -> str:
        h = (self.held() if held is None else held).get(rom_id)
        return h.state if h else "available"

    def installs(self, held: dict[int, "Held"] | None = None) -> list[dict]:
        """Every game the ledger knows, held against the disk."""
        return [{"rom_id": h.install.rom_id, "name": h.install.name, "state": h.state, "appid": self.shortcuts.appid(h.install.rom_id),
                 "bytes_done": h.seen.done_bytes, "bytes_total": h.seen.total_bytes, "missing": list(h.seen.missing),
                 "error": h.install.error, "queued_at": h.install.queued_at, "updated_at": h.install.updated_at,
                 "completed_at": h.install.completed_at}
                for h in (self.held() if held is None else held).values()]

    def storage(self, held: dict[int, "Held"] | None = None) -> dict:
        """What the ROM folder's drive has: bytes taken by installed games, and the drive's free and total bytes."""
        used = sum(h.seen.done_bytes for h in (self.held() if held is None else held).values() if h.state == L.INSTALLED)
        # The folder is only made when the first game downloads; its drive is the nearest folder that exists.
        path = self.location.roms_dir
        while path and not os.path.exists(path) and os.path.dirname(path) != path:
            path = os.path.dirname(path)
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return {"used_bytes": used, "free_bytes": 0, "total_bytes": 0}
        return {"used_bytes": used, "free_bytes": usage.free, "total_bytes": usage.total}

    def installed(self, held: dict[int, "Held"] | None = None) -> list[dict]:
        """Complete games that have a Steam shortcut, with what Steam's storage pages show for an installed app."""
        out = []
        for h in (self.held() if held is None else held).values():
            appid = self.shortcuts.appid(h.install.rom_id)
            if not appid or h.state != L.INSTALLED:
                continue
            try:
                device = os.stat(h.target.path).st_dev
            except OSError:
                continue
            out.append({"rom_id": h.install.rom_id, "appid": appid, "name": h.install.name, "path": h.target.path,
                        "folder": h.target.path if h.target.is_dir else os.path.dirname(h.target.path),
                        "bytes": h.seen.done_bytes, "device": device})
        return out

    async def adopt(self) -> None:
        """Games found on disk that the ledger does not know (from before it existed, or after it was lost) get a
        record: RomM's file list decides whether each is installed or incomplete."""
        if not self.client:
            return
        changed = False
        for game in list(self.library.games.values()):
            if self.ledger.get(game.rom_id):
                continue
            target = self.location.target(game.slug, game.fs_name, game.single_file)
            if not (target.installed or target.partial):
                continue
            try:
                files = manifest(await self.client.rom(game.rom_id), target)
            except Exception as e:
                self.log.warning("could not check %s found on disk: %s", game.name, e)
                continue
            install = Install(rom_id=game.rom_id, name=game.name, slug=game.slug, fs_name=game.fs_name, single_file=game.single_file,
                              size_bytes=game.size_bytes, files=files, state=L.INCOMPLETE)
            if L.check(install, target.path).complete:
                install.state = L.INSTALLED
            self.ledger.put(install)
            changed = True
        if changed:
            self._changed()

    async def verify(self, rom_id: int) -> dict:
        """Asks RomM for the game's files again and holds the disk against them."""
        install = self.ledger.get(int(rom_id))
        if not install or not self.client:
            raise ValueError("Unknown game")
        if install.state not in L.IN_QUEUE:
            files = manifest(await self.client.rom(install.rom_id), self._target(install))
            install = self.ledger.update(install.rom_id, files=files)
            complete = L.check(install, self._target(install).path).complete
            if complete != (install.state == L.INSTALLED):
                self.ledger.update(install.rom_id, state=L.INSTALLED if complete else L.INCOMPLETE)
        self._changed()
        return self.state()

    async def game_video(self, rom_id: int) -> dict:
        """Direct stream addresses for the game's trailer ("" each when it has none or it cannot be resolved)."""
        game = self.library.games.get(int(rom_id))
        video_id = (game.raw.get("youtube_video_id") or "") if game else ""
        return {"rom_id": int(rom_id), **(await self.videos.resolve(video_id))}

    async def cover_base64(self, rom_id: int) -> dict:
        """The game's cover for Steam's custom artwork call (the Steam webview cannot fetch it cross-origin itself)."""
        game = self.library.games.get(int(rom_id))
        if not game or not self.client or not (game.cover_large or game.cover):
            return {"base64": "", "format": ""}
        data, _ctype = await self.client.fetch_bytes(game.cover_large or game.cover)
        # RomM labels every cover image/png whatever it holds; Steam needs the real format.
        fmt = "png" if data.startswith(b"\x89PNG") else "jpg" if data.startswith(b"\xff\xd8") else ""
        if not fmt:
            self.log.warning("cover of %s is neither PNG nor JPEG (%d bytes)", game.name, len(data))
            return {"base64": "", "format": ""}
        return {"base64": base64.b64encode(data).decode(), "format": fmt}

    async def download(self, rom_id: int, appid: int = 0) -> dict:
        game = self.library.games.get(int(rom_id))
        if not game or not self.downloader:
            raise ValueError("Unknown game")
        if not self.location.exists:
            # Only our own folder is made: a chosen one that is missing is likely a drive that is not there.
            if self.location.roms_dir != self.default_roms_dir:
                raise ValueError(f"The ROM folder {self.location.roms_dir} does not exist")
            os.makedirs(self.location.roms_dir, exist_ok=True)
        if appid:
            self.shortcuts.set(game.rom_id, int(appid), game.name)
        self.downloader.add(game, self.shortcuts.appid(game.rom_id))
        emulator = self.emulator_for(game.slug)
        if emulator:
            # In the background: by the time the game is on the device, so is what its emulator needs.
            self._bios_task = asyncio.create_task(self._auto_bios(emulator, game.slug))
        self._changed()
        return self.state()

    async def set_shortcut(self, rom_id: int, appid: int) -> dict:
        """Records the game's Steam shortcut; appid 0 forgets one Steam no longer has."""
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        self.shortcuts.set(game.rom_id, int(appid), game.name)
        if self.downloader:
            self.downloader.add_appid(game.rom_id, int(appid))
        self._changed()
        return self.state()

    async def remove(self, rom_id: int) -> dict:
        """Deletes the game's files and its record, whatever state it is in; the frontend removes the Steam shortcut
        with the appid returned in `removed`."""
        rom_id = int(rom_id)
        install, game = self.ledger.get(rom_id), self.library.games.get(rom_id)
        if not install and not game:
            raise ValueError("Unknown game")
        if self.downloader:
            await self.downloader.drop(rom_id)
        target = self._target(install) if install else self.location.target(game.slug, game.fs_name, game.single_file)
        for path in (target.path, target.path + ".part"):
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)
        icon = self._icon_path(rom_id)
        if icon and os.path.exists(icon):
            os.unlink(icon)
        self.ledger.remove(rom_id)
        appid = self.shortcuts.forget(rom_id)
        self._changed()
        return {"removed": appid, **self.state()}

    def _rom_id_for(self, appid: int) -> int | None:
        return self.shortcuts.rom_id(int(appid))

    async def download_control(self, action: str, appid: int = 0, value: int = 0) -> dict:
        """Steam's Downloads page buttons: pause/resume/cancel one of ours, pause_all/resume_all, move/move_to, clear."""
        d = self.downloader
        if not d:
            return self.state()
        rom_id = self._rom_id_for(appid) if appid else None
        if action == "pause_all":
            await d.pause_all()
        elif action == "resume_all":
            await d.resume_all()
        elif action == "clear":
            d.clear()
        elif rom_id is not None:
            if action == "pause":
                await d.pause(rom_id)
            elif action == "resume":
                install = self.ledger.get(rom_id)
                if install and install.state in (L.INCOMPLETE, L.FAILED):
                    d.add(as_game(install), int(appid))  # Steam's Resume on a download that had stopped
                else:
                    await d.resume(rom_id)
            elif action == "cancel":
                await d.cancel(rom_id)
            elif action == "move":
                d.move(rom_id, int(value))
            elif action == "move_to":
                d.move_to(rom_id, int(value))
        self._changed()
        return self.state()

    async def cancel_download(self, rom_id: int) -> dict:
        if self.downloader:
            await self.downloader.cancel(int(rom_id))
        return self.state()

    async def set_roms_dir(self, path: str) -> dict:
        path = path.strip() or self.default_roms_dir
        self.location = InstallLocation(path, self.home)
        if self.downloader:
            self.downloader.location = self.location
        self.settings.roms_dir = path
        self.store.save(self.settings)
        self._changed()
        return self.state()
