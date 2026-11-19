import json
from dataclasses import asdict, dataclass, field, fields, replace

from . import jsonfile


@dataclass
class Settings:
    server_url: str = ""
    token: str = ""
    device_id: str = ""
    username: str = ""
    scopes: list[str] = field(default_factory=list)
    roms_dir: str = ""
    sgdb_key: str = ""
    setup_done: bool = False

    def for_server(self, url: str) -> "Settings":
        """These settings pointed at another RomM server: signed out, so setup runs again; everything about the
        device is kept."""
        return replace(self, server_url=url, token="", device_id="", username="", scopes=[], setup_done=False)

    def signed_out(self) -> "Settings":
        return self.for_server("")

    @property
    def paired(self) -> bool:
        return bool(self.server_url and self.token and self.device_id)


class SettingsStore:
    """One JSON file, written atomically and readable only by the owner (it holds the RomM token)."""

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> Settings:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, ValueError):
            return Settings()
        known = {f.name for f in fields(Settings)}
        return Settings(**{k: v for k, v in data.items() if k in known})

    def save(self, settings: Settings) -> None:
        jsonfile.write(self.path, asdict(settings), private=True)
