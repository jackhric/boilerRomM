"""Xenia Canary (Xbox 360), run from the project's own AppImage."""
import hashlib
import hmac
import json
import os
import re
import tempfile
import tomllib
from typing import Any

from .base import Command, Emulator
from .releases import Source

# Canary publishes a release per commit, tagged with the short commit hash; there are no version numbers.
TAG = "79aee12"

# Xenia only saves games for a signed-in profile, and making one in its window needs a keyboard. The profile gets
# the same id on every device so that a save synced from one is found on another.
XUID = "E03000000000B01E"
GAMERTAG = "boilerRomM"
PROFILE = os.path.join("FFFE07D1", "00010000")

# The console key Xenia decrypts a profile's Account file with: key19 in src/xenia/kernel/xboxkrnl/xboxkrnl_crypt.cc.
ACCOUNT_KEY = bytes.fromhex("e1bc159c73b1eae9ab3170f3ad47ebf3")
ACCOUNT_SIZE = 0x17C


def _hmac(data: bytes) -> bytes:
    return hmac.new(ACCOUNT_KEY, data, hashlib.sha1).digest()[:16]


def _rc4(key: bytes, data: bytes) -> bytes:
    s, j = list(range(256)), 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out, i, j = bytearray(), 0, 0
    for byte in data:
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) & 0xFF])
    return bytes(out)


def account_file(gamertag: str) -> bytes:
    """An Account file as ProfileManager::EncryptAccountFile writes it, for an offline profile with this name."""
    account = (bytes(8) + gamertag.encode("utf-16-be")).ljust(ACCOUNT_SIZE, b"\0")
    plain = b"\xfd" * 8 + account
    digest = _hmac(plain)
    return digest + _rc4(_hmac(digest), plain)


def read_account(data: bytes) -> str:
    """The gamertag in an Account file; "" when Xenia would not accept the file."""
    plain = _rc4(_hmac(data[:16]), data[16:16 + 8 + ACCOUNT_SIZE])
    if len(plain) != 8 + ACCOUNT_SIZE or _hmac(plain) != data[:16]:
        return ""
    return plain[16:48].decode("utf-16-be").rstrip("\0")


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)


class Xenia(Emulator):
    year = 2005

    id = "xenia"
    name = "Xenia Canary"
    system = "Xbox 360"
    platforms = ("xbox360",)
    source = Source("xenia-canary/xenia-canary", r"^xenia_canary_linux\.AppImage$", TAG)

    @property
    def toml(self) -> str:
        return os.path.join(self.config_dir, "xenia-canary.config.toml")

    @property
    def content(self) -> str:
        """Xenia's content folder: the profiles, and under each profile its saves."""
        return self.layout.saves("xbox360", self.id)

    def profiles(self) -> list[str]:
        try:
            names = sorted(os.listdir(self.content))
        except OSError:
            return []
        return [n for n in names if re.fullmatch("[0-9A-F]{16}", n) and os.path.isdir(os.path.join(self.content, n, PROFILE, n))]

    def configure(self) -> None:
        profiles = self.profiles()
        if not profiles:
            folder = os.path.join(self.content, XUID, PROFILE, XUID)
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "Account"), "wb") as f:
                f.write(account_file(GAMERTAG))
            profiles = [XUID]
        config = self.read_config()
        config.setdefault("Storage", {}).update(content_root=self.content, cache_root=self.cache_dir)
        config.setdefault("Display", {}).setdefault("fullscreen", True)
        if not config.setdefault("Profiles", {}).get("logged_profile_slot_0_xuid"):
            config["Profiles"]["logged_profile_slot_0_xuid"] = profiles[0]
        self.write_config(config)

    def read_config(self) -> dict[str, dict[str, Any]]:
        try:
            with open(self.toml, "rb") as f:
                config = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        return {section: dict(items) for section, items in config.items() if isinstance(items, dict)}

    def write_config(self, config: dict[str, dict[str, Any]]) -> None:
        # Xenia writes the whole file again when it closes, with every option and its description, so the comments
        # lost here come back.
        text = "\n".join(f"[{section}]\n" + "".join(f"{key} = {_toml(value)}\n" for key, value in items.items())
                         for section, items in config.items())
        os.makedirs(self.config_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.config_dir, prefix=".config-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.toml)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def command(self, rom: str, platform: str = "") -> Command:
        # Xenia looks for its config under XDG_DATA_HOME, with its logs and patches; --config keeps the config in
        # the folder a reset clears.
        return Command([self.executable, f"--config={self.toml}", "--fullscreen=true", rom], self.env())
