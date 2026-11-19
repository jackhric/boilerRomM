"""Writing a JSON file so that a crash or power loss leaves the old file or the new one, never a torn one."""
import json
import os
import tempfile


def write(path: str, data: object, *, indent: int | None = 2, private: bool = False, durable: bool = False) -> None:
    """`private` makes the file readable by its owner only; `durable` waits until the bytes are on the disk."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{os.path.basename(path)}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
            if durable:
                f.flush()
                os.fsync(f.fileno())
        if private:
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
