import json
import os
from typing import Any

from boilerromm.app import App

import decky


def _version() -> str:
    try:
        with open(os.path.join(decky.DECKY_PLUGIN_DIR, "package.json")) as f:
            return str(json.load(f).get("version", "0"))
    except Exception:
        return "0"


class Plugin:
    app: App

    async def _main(self) -> None:
        self.app = App(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"), _version(),
                       decky.DECKY_USER_HOME, decky.emit, decky.logger, data_dir=decky.DECKY_PLUGIN_RUNTIME_DIR)
        self.app.install_launcher(os.path.join(decky.DECKY_PLUGIN_DIR, "bin", "boilerromm-launch"), decky.DECKY_PLUGIN_RUNTIME_DIR)
        await self.app.start()
        decky.logger.info("boilerRomM %s started", self.app.version)

    async def _unload(self) -> None:
        await self.app.stop()

    async def get_state(self) -> dict[str, Any]:
        return self.app.state()

    async def set_server(self, url: str) -> dict[str, Any]:
        return await self.app.set_server(url)

    async def check_connection(self) -> dict[str, Any]:
        return await self.app.check_connection()

    async def start_pairing(self) -> dict[str, Any]:
        return await self.app.start_pairing()

    async def disconnect(self) -> dict[str, Any]:
        return await self.app.disconnect()

    async def reset(self) -> dict[str, Any]:
        return await self.app.reset()

    async def refresh_library(self) -> dict[str, Any]:
        return await self.app.refresh_library()

    async def similar_games(self, rom_id: int) -> list[dict[str, Any]]:
        return await self.app.similar_games(rom_id)

    async def game_details(self, rom_id: int) -> dict[str, Any]:
        return await self.app.game_details(rom_id)

    async def download(self, rom_id: int, appid: int = 0) -> dict[str, Any]:
        return await self.app.download(rom_id, appid)

    async def cover_base64(self, rom_id: int) -> dict[str, Any]:
        return await self.app.cover_base64(rom_id)

    async def save_icon(self, rom_id: int, data_base64: str) -> str:
        return self.app.save_icon(rom_id, data_base64)

    async def launch_target(self, rom_id: int) -> dict[str, Any]:
        return self.app.launch_target(rom_id)

    async def play_target(self, rom_id: int) -> dict[str, Any]:
        return await self.app.play_target(rom_id)

    async def set_shortcut(self, rom_id: int, appid: int) -> dict[str, Any]:
        return await self.app.set_shortcut(rom_id, appid)

    async def remove(self, rom_id: int) -> dict[str, Any]:
        return await self.app.remove(rom_id)

    async def download_control(self, action: str, appid: int = 0, value: int = 0) -> dict[str, Any]:
        return await self.app.download_control(action, appid, value)

    async def emulator_versions(self, emulator_id: str) -> list[dict[str, Any]]:
        return await self.app.emulator_versions(emulator_id)

    async def emulator_install(self, emulator_id: str, tag: str = "") -> dict[str, Any]:
        return await self.app.emulator_install(emulator_id, tag)

    async def emulators_install_all(self) -> dict[str, Any]:
        return await self.app.emulators_install_all()

    async def finish_setup(self) -> dict[str, Any]:
        return await self.app.finish_setup()

    async def bios_available(self) -> dict[str, Any]:
        return await self.app.bios_available()

    async def emulator_bios_install(self, emulator_id: str, firmware_ids: list[int] | None = None) -> dict[str, Any]:
        return await self.app.emulator_bios_install(emulator_id, firmware_ids)

    async def emulator_bios_uninstall(self, emulator_id: str) -> dict[str, Any]:
        return await self.app.emulator_bios_uninstall(emulator_id)

    async def emulator_uninstall(self, emulator_id: str) -> dict[str, Any]:
        return await self.app.emulator_uninstall(emulator_id)

    async def emulator_reset(self, emulator_id: str) -> dict[str, Any]:
        return await self.app.emulator_reset(emulator_id)

    async def cancel_download(self, rom_id: int) -> dict[str, Any]:
        return await self.app.cancel_download(rom_id)

    async def set_sgdb_key(self, key: str) -> dict[str, Any]:
        return await self.app.set_sgdb_key(key)

    async def start_sgdb_signin(self) -> dict[str, Any]:
        return await self.app.start_sgdb_signin()

    async def cancel_sgdb_signin(self) -> dict[str, Any]:
        return await self.app.cancel_sgdb_signin()

    async def game_art(self, rom_id: int) -> dict[str, Any]:
        return await self.app.game_art(rom_id)

    async def art_base64(self, rom_id: int, kind: str) -> dict[str, Any]:
        return await self.app.art_base64(rom_id, kind)

    async def game_video(self, rom_id: int) -> dict[str, Any]:
        return await self.app.game_video(rom_id)

    async def set_roms_dir(self, path: str) -> dict[str, Any]:
        return await self.app.set_roms_dir(path)
