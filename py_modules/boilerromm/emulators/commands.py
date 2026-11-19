"""What `App` does with emulators: installing them, their firmware, and the command that starts a game."""
import asyncio
import os
import shlex
import tempfile
import time
from collections.abc import Awaitable, Callable

from .. import emulators
from ..emulators.progress import Counted
from ..games.install import Target


class EmulatorCommands:
    async def _emulator_task(self, emulator_id: str, doing: str, work: Callable[[emulators.Emulator], Awaitable[None]]) -> dict:
        emulator = self.emulators.get(emulator_id)
        if not emulator:
            raise ValueError("Unknown emulator")
        if self._emulator_busy.get(emulator_id):
            return self.state()
        self._emulator_busy[emulator_id] = doing
        self._emulator_error.pop(emulator_id, None)
        self._changed()
        try:
            await work(emulator)
        except Exception as e:
            self.log.warning("%s %s failed: %s", doing, emulator_id, e)
            self._emulator_error[emulator_id] = str(e) or type(e).__name__
        finally:
            self._emulator_busy.pop(emulator_id, None)
        self._changed()
        return self.state()

    async def emulator_versions(self, emulator_id: str) -> list[dict]:
        """The builds on offer, asked from the project at most every ten minutes (GitHub limits anonymous requests)."""
        emulator = self.emulators.get(emulator_id)
        if not emulator:
            raise ValueError("Unknown emulator")
        cached = self._emulator_versions.get(emulator_id)
        if cached and time.monotonic() - cached[0] < 600:
            return cached[1]
        async with self._release_session() as session:
            listed = await emulator.versions(session)
        self._emulator_versions[emulator_id] = (time.monotonic(), listed)
        return listed

    def _downloaded(self, emulator_id: str, done: int, total: int) -> None:
        self._emulator_progress[emulator_id] = (done, total)
        # A download reports every chunk; the screen needs a few updates a second.
        if time.monotonic() - self._progress_sent > 0.3:
            self._progress_sent = time.monotonic()
            self._changed()

    async def emulator_install(self, emulator_id: str, tag: str = "") -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            try:
                async with self._release_session() as session:
                    await emulator.install(Counted(session, lambda done, total: self._downloaded(emulator.id, done, total)), tag)
                emulator.prepare()
            finally:
                self._emulator_progress.pop(emulator.id, None)
            if emulator.bios_platforms():
                # A step of its own on screen: it can take minutes, and is not the emulator downloading.
                self._emulator_busy[emulator.id] = "firmware"
                self._changed()
                await self._auto_bios(emulator)
        return await self._emulator_task(emulator_id, "installing", work)

    async def emulators_install_all(self) -> dict:
        """Installs every emulator that is not installed, one after another, in the background. Each stands alone:
        one that fails is reported on its own row and the rest carry on."""
        waiting = [e.id for e in self.emulators.values() if not e.version and not self._emulator_busy.get(e.id)]
        for emulator_id in waiting:
            self._emulator_busy[emulator_id] = "queued"
            self._emulator_error.pop(emulator_id, None)
        if waiting:
            previous = self._install_all
            self._install_all = asyncio.create_task(self._install_queued(waiting, previous))
        self._changed()
        return self.state()

    async def _install_queued(self, waiting: list[str], previous: asyncio.Task | None) -> None:
        try:
            if previous:
                await asyncio.gather(previous, return_exceptions=True)
            for emulator_id in waiting:
                self._emulator_busy.pop(emulator_id, None)
                await self.emulator_install(emulator_id)
        finally:
            for emulator_id in waiting:
                if self._emulator_busy.get(emulator_id) == "queued":
                    self._emulator_busy.pop(emulator_id, None)

    async def emulator_uninstall(self, emulator_id: str) -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            emulator.uninstall()
        return await self._emulator_task(emulator_id, "uninstalling", work)

    async def emulator_reset(self, emulator_id: str) -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            emulator.reset_config()
        return await self._emulator_task(emulator_id, "resetting", work)

    async def _romm_firmware(self, wanted: list[emulators.Emulator]) -> dict[str, tuple[list[dict], int]]:
        """What RomM holds for each emulator: (the files it can use, how many RomM listed for its platforms)."""
        if not self.client or not self.settings.paired:
            raise RuntimeError("Connect to RomM first")
        ids = {p["fs_slug"]: p["id"] for p in await self.client.platforms()}
        listed: dict[str, list[dict]] = {}
        out = {}
        for emulator in wanted:
            usable, count = [], 0
            for platform in emulator.bios_platforms():
                if platform not in ids:
                    continue
                if platform not in listed:
                    listed[platform] = await self.client.firmware(ids[platform])
                count += len(listed[platform])
                usable += [{**e, "platform": platform} for e in listed[platform] if not e.get("missing_from_fs") and emulator.compatible(e)]
            out[emulator.id] = (usable, count)
        return out

    async def bios_available(self) -> dict:
        """The firmware files on the RomM server each emulator could install, for the BIOS page's menus."""
        wanted = [e for e in self.emulators.values() if e.bios_platforms()]
        try:
            found = await self._romm_firmware(wanted)
        except Exception as e:
            self.log.warning("firmware on RomM was not listed: %s", e)
            return {e.id: [] for e in wanted}
        out = {}
        for emulator in wanted:
            usable = found[emulator.id][0]
            pick = emulator.recommended(usable)
            out[emulator.id] = [{"id": e["id"], "name": e["file_name"], "size": e.get("file_size_bytes") or 0, "platform": e["platform"],
                                 "recommended": not emulator.firmware_set and pick is not None and e["id"] == pick["id"]} for e in usable]
            # The suggestion leads the menu; a long list of BIOS versions would otherwise bury it.
            out[emulator.id].sort(key=lambda f: not f["recommended"])
        return out

    async def _fetch_bios(self, emulator: emulators.Emulator, only: list[int] | None = None) -> tuple[int, int]:
        """Downloads firmware from RomM for the emulator: (kept, listed). `only` names the files by RomM's id; without
        it, a set is fetched whole and otherwise the one recommended file. Each download goes through the emulator's
        own check, so a file that turns out not to be what it looked like is not kept."""
        usable, listed = (await self._romm_firmware([emulator]))[emulator.id]
        if only:
            chosen = [e for e in usable if e["id"] in only]
        elif emulator.firmware_set:
            chosen = usable
        else:
            chosen = [e for e in [emulator.recommended(usable)] if e]
        kept = 0
        with tempfile.TemporaryDirectory(dir=self.data_dir if os.path.isdir(self.data_dir) else None) as scratch:
            for entry in chosen:
                path = os.path.join(scratch, os.path.basename(entry["file_name"]))
                await self.client.fetch_firmware(entry["id"], entry["file_name"], path)
                if emulator.add_firmware(path):
                    kept += 1
                os.unlink(path)
        return kept, listed

    async def emulator_bios_install(self, emulator_id: str, firmware_ids: list[int] | None = None) -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            kept, listed = await self._fetch_bios(emulator, [int(i) for i in firmware_ids or []])
            if not kept:
                raise RuntimeError("RomM has no firmware for this emulator" if not listed else "None of RomM's files are ones it can use")
            emulator.prepare()
            await emulator.install_firmware()
        return await self._emulator_task(emulator_id, "fetching", work)

    async def emulator_bios_uninstall(self, emulator_id: str) -> dict:
        async def work(emulator: emulators.Emulator) -> None:
            emulator.remove_firmware()
        return await self._emulator_task(emulator_id, "removing", work)

    def _bios_missing(self, emulator: emulators.Emulator, slug: str = "") -> bool:
        """Whether the emulator lacks firmware it cannot run without: for `slug`'s games, or for any of its platforms."""
        needed = [p for p in emulator.bios_platforms() if not slug or p == slug]
        return any(not emulator.platform_ready(p) for p in needed)

    async def _auto_bios(self, emulator: emulators.Emulator, slug: str = "") -> None:
        """Gets missing firmware from RomM without being asked. Quiet: RomM not having it is not an error here, the
        BIOS page and the launch check say what is missing."""
        if emulator.id in self._bios_fetching:
            return
        self._bios_fetching.add(emulator.id)
        try:
            if self.settings.paired and self._bios_missing(emulator, slug):
                kept, _ = await self._fetch_bios(emulator)
                if kept:
                    self.log.info("%s: %d firmware files from RomM", emulator.name, kept)
            await emulator.install_firmware()
        except Exception as e:
            self.log.warning("firmware for %s was not set up: %s", emulator.name, e)
        finally:
            self._bios_fetching.discard(emulator.id)
        self._changed()

    def emulator_for(self, slug: str) -> emulators.Emulator | None:
        """The emulator that runs a platform's games; None when boilerRomM has none for it."""
        return next((e for e in self.emulators.values() if slug in e.platforms), None)

    def launch_script(self, rom_id: int) -> str:
        return os.path.join(self.runtime_dir, "launch", f"{int(rom_id)}.sh") if self.runtime_dir else ""

    def write_launch_script(self, slug: str, rom_id: int, target: Target) -> None:
        """Writes what the launcher runs for a game. A Steam shortcut carries only the game's id, so the emulator,
        its version and the ROM folder can all change without the shortcut going stale."""
        path = self.launch_script(rom_id)
        if not path:
            return
        emulator = self.emulator_for(slug)
        if not emulator:
            lines = [f"echo {shlex.quote(f'boilerRomM has no emulator for {slug} games')} >&2", "exit 1"]
        elif not emulator.version:
            lines = [f"echo {shlex.quote(f'{emulator.name} is not installed: install it in boilerRomM settings')} >&2", "exit 1"]
        else:
            emulator.prepare()
            command = emulator.command(emulator.launch_file(target), slug)
            # Steam lists a game while it downloads, so Play can be pressed before the files are whole.
            lines = [f"rom={shlex.quote(target.path)}",
                     'if [[ -e "$rom.part" ]] || { [[ -d "$rom" ]] && compgen -G "$rom/*.part" >/dev/null; }; then',
                     '  echo "boilerRomM: $rom is still downloading" >&2; exit 1',
                     "fi",
                     'if [[ ! -e "$rom" ]]; then echo "boilerRomM: $rom is not on this device" >&2; exit 1; fi']
            lines += [f"export {key}={shlex.quote(value)}" for key, value in command.env.items()]
            lines.append("exec " + " ".join(shlex.quote(arg) for arg in command.argv))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/bin/bash\n" + "\n".join(lines) + "\n")
        os.chmod(path, 0o755)

    def launch_target(self, rom_id: int) -> dict:
        """What a Steam shortcut for this game runs: the launcher with the game's id."""
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        target = self.location.target(game.slug, game.fs_name, game.single_file)
        self.write_launch_script(game.slug, game.rom_id, target)
        return {
            "rom_id": game.rom_id, "name": game.name, "appid": self.shortcuts.appid(game.rom_id),
            "exe": self.launcher or "/usr/bin/false", "start_dir": os.path.dirname(target.path),
            "launch_options": str(game.rom_id), "cover": game.cover_large or game.cover,
            "installed": target.installed, "blocked": self._blocked(game.slug, game.platform),
        }

    def _blocked(self, slug: str, platform: str) -> str:
        """Why a game of this platform cannot start; "" when it can."""
        emulator = self.emulator_for(slug)
        if not emulator:
            return f"boilerRomM has no emulator for {platform}."
        if not emulator.version:
            return f"{emulator.name} is not installed. Install it in Settings, under Emulators."
        if self._bios_missing(emulator, slug):
            return f"{emulator.name} needs {emulator.requires}, and RomM did not have one. Add it in Settings, under BIOS."
        if slug in emulator.bios_platforms() and not emulator.firmware_installed:
            return f"{emulator.name} could not install its firmware. Try again in Settings, under BIOS."
        return ""

    async def play_target(self, rom_id: int) -> dict:
        """`launch_target` for a game about to be started, after one more try at getting missing firmware."""
        game = self.library.games.get(int(rom_id))
        if not game:
            raise ValueError("Unknown game")
        emulator = self.emulator_for(game.slug)
        if emulator and emulator.version:
            await self._auto_bios(emulator, game.slug)
        return self.launch_target(rom_id)
