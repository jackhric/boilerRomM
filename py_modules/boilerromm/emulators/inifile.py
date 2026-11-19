"""Changing some keys of an emulator's INI file and leaving the rest as the emulator or the user wrote them."""
import configparser
import os
import tempfile

Sections = dict[str, dict[str, str]]


def update(path: str, values: Sections | None = None, defaults: Sections | None = None) -> None:
    """`values` are always written; `defaults` only where the key is not there yet."""
    ini = configparser.RawConfigParser(strict=False)
    ini.optionxform = str  # emulators read their keys case-sensitively
    ini.read(path, encoding="utf-8")
    for sections, overwrite in ((defaults, False), (values, True)):
        for section, items in (sections or {}).items():
            if not ini.has_section(section):
                ini.add_section(section)
            for key, value in items.items():
                if overwrite or not ini.has_option(section, key):
                    ini.set(section, key, value)
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{os.path.basename(path)}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            ini.write(f)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read(path: str, section: str, key: str, fallback: str = "") -> str:
    ini = configparser.RawConfigParser(strict=False)
    ini.optionxform = str
    ini.read(path, encoding="utf-8")
    return ini.get(section, key, fallback=fallback)
