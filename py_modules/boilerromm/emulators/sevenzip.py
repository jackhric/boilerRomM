"""Reading a .7z archive with what Python ships: the single-coder LZMA and LZMA2 archives that 7-Zip writes by
default. Every file taken out is checked against the archive's own CRC."""
import io
import lzma
import os
import struct
import zlib
from collections.abc import Callable, Iterator
from typing import BinaryIO

from . import releases

_CHUNK = 1 << 20


class ArchiveError(releases.ReleaseError):
    pass


class _Reader:
    """The fields of a 7z header."""

    def __init__(self, data: bytes) -> None:
        self.data = io.BytesIO(data)

    def read(self, size: int) -> bytes:
        data = self.data.read(size)
        if len(data) != size:
            raise ArchiveError("the archive's header is cut short")
        return data

    def byte(self) -> int:
        return self.read(1)[0]

    def number(self) -> int:
        first, value = self.byte(), 0
        for i in range(8):
            mask = 0x80 >> i
            if not first & mask:
                return value | ((first & (mask - 1)) << (8 * i))
            value |= self.byte() << (8 * i)
        return value

    def bits(self, count: int) -> list[bool]:
        data = self.read((count + 7) // 8)
        return [bool(data[i // 8] & (0x80 >> (i % 8))) for i in range(count)]

    def checksums(self, count: int) -> list[int | None]:
        defined = [True] * count if self.byte() else self.bits(count)
        return [struct.unpack("<I", self.read(4))[0] if d else None for d in defined]

    def expect(self, value: int) -> None:
        if self.byte() != value:
            raise ArchiveError("the archive is laid out in a way this reader does not know")


class _Folder:
    """One compressed stream and the files packed into it one after another."""

    def __init__(self, method: bytes, properties: bytes) -> None:
        self.method = method
        self.properties = properties
        self.offset = 0
        self.packed = 0
        self.size = 0
        self.checksum: int | None = None
        self.sizes: list[int] = []
        self.checksums: list[int | None] = []

    def decoder(self) -> lzma.LZMADecompressor:
        if self.method == b"\x03\x01\x01":
            d = self.properties[0]
            return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{
                "id": lzma.FILTER_LZMA1, "lc": d % 9, "lp": d // 9 % 5, "pb": d // 45,
                "dict_size": struct.unpack("<I", self.properties[1:5])[0]}])
        if self.method == b"\x21":
            bits = self.properties[0]
            size = 0xFFFFFFFF if bits >= 40 else (2 | (bits & 1)) << (bits // 2 + 11)
            return lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{"id": lzma.FILTER_LZMA2, "dict_size": size}])
        raise ArchiveError(f"the archive is compressed with a method this reader does not know ({self.method.hex()})")

    def unpack(self, f: BinaryIO) -> Iterator[bytes]:
        """The stream's content, in pieces."""
        decoder = self.decoder()
        f.seek(self.offset)
        packed, left = self.packed, self.size
        while left:
            if decoder.needs_input:
                data = f.read(min(_CHUNK, packed))
                if not data:
                    raise ArchiveError("the archive is cut short")
                packed -= len(data)
            else:
                data = b""
            try:
                piece = decoder.decompress(data, min(_CHUNK, left))
            except (lzma.LZMAError, EOFError) as e:
                raise ArchiveError("the archive is damaged") from e
            left -= len(piece)
            yield piece


def _read_folder(r: _Reader) -> _Folder:
    if r.number() != 1:
        raise ArchiveError("the archive chains compression methods, which this reader does not know")
    flags = r.byte()
    method = r.read(flags & 0x0F)
    if flags & 0x10:
        raise ArchiveError("the archive is laid out in a way this reader does not know")
    return _Folder(method, r.read(r.number()) if flags & 0x20 else b"")


def _read_streams(r: _Reader) -> list[_Folder]:
    start = 0
    packed: list[int] = []
    folders: list[_Folder] = []
    while kind := r.byte():
        if kind == 0x06:
            start, count = r.number(), r.number()
            while kind := r.byte():
                if kind == 0x09:
                    packed = [r.number() for _ in range(count)]
                elif kind == 0x0A:
                    r.checksums(count)
        elif kind == 0x07:
            r.expect(0x0B)
            count = r.number()
            r.expect(0)
            folders = [_read_folder(r) for _ in range(count)]
            r.expect(0x0C)
            for folder in folders:
                folder.size = r.number()
                folder.sizes = [folder.size]
            kind = r.byte()
            if kind == 0x0A:
                for folder, checksum in zip(folders, r.checksums(count), strict=True):
                    folder.checksum = checksum
                kind = r.byte()
            if kind:
                raise ArchiveError("the archive is laid out in a way this reader does not know")
        elif kind == 0x08:
            counts = [1] * len(folders)
            kind = r.byte()
            if kind == 0x0D:
                counts = [r.number() for _ in folders]
                kind = r.byte()
            for folder, count in zip(folders, counts, strict=True):
                sizes = [r.number() for _ in range(count - 1)] if kind == 0x09 else []
                folder.sizes = sizes + [folder.size - sum(sizes)] if count else []
            if kind == 0x09:
                kind = r.byte()
            for folder in folders:
                known = len(folder.sizes) == 1 and folder.checksum is not None
                folder.checksums = [folder.checksum] if known else [None] * len(folder.sizes)
            if kind == 0x0A:
                unknown = [(folder, i) for folder in folders for i, c in enumerate(folder.checksums) if c is None]
                for (folder, i), checksum in zip(unknown, r.checksums(len(unknown)), strict=True):
                    folder.checksums[i] = checksum
                kind = r.byte()
            if kind:
                raise ArchiveError("the archive is laid out in a way this reader does not know")
        else:
            raise ArchiveError("the archive is laid out in a way this reader does not know")
    if len(packed) != len(folders):
        raise ArchiveError("the archive is laid out in a way this reader does not know")
    offset = 32 + start
    for folder, size in zip(folders, packed, strict=True):
        folder.offset, folder.packed = offset, size
        if not folder.checksums:
            folder.checksums = [folder.checksum]
        offset += size
    return folders


def _read_files(r: _Reader) -> list[tuple[str, bool]]:
    """Every entry's name and whether it has content: folders and empty files have none."""
    count = r.number()
    names, empty = [], [False] * count
    while kind := r.byte():
        field = _Reader(r.read(r.number()))
        if kind == 0x0E:
            empty = field.bits(count)
        elif kind == 0x11:
            field.expect(0)
            names = field.data.read().decode("utf-16-le").split("\0")[:count]
    if len(names) != count:
        raise ArchiveError("the archive does not name its files")
    return [(name, not e) for name, e in zip(names, empty, strict=True)]


def _read_archive(f: BinaryIO) -> tuple[list[_Folder], list[str]]:
    """The archive's streams, and the names of the files in them in the order they are packed."""
    start = f.read(32)
    if len(start) != 32 or start[:6] != b"7z\xbc\xaf\x27\x1c":
        raise ArchiveError("not a 7z archive")
    offset, size, checksum = struct.unpack("<QQI", start[12:])
    f.seek(32 + offset)
    header = f.read(size)
    if len(header) != size or zlib.crc32(header) != checksum:
        raise ArchiveError("the archive is cut short or damaged")
    r = _Reader(header)
    kind = r.byte()
    if kind == 0x17:
        packed = _read_streams(r)[0]
        header = b"".join(packed.unpack(f))
        if packed.checksum is not None and zlib.crc32(header) != packed.checksum:
            raise ArchiveError("the archive is damaged")
        r = _Reader(header)
        kind = r.byte()
    if kind != 0x01:
        raise ArchiveError("the archive is laid out in a way this reader does not know")
    folders: list[_Folder] = []
    files: list[tuple[str, bool]] = []
    while kind := r.byte():
        if kind == 0x04:
            folders = _read_streams(r)
        elif kind == 0x05:
            files = _read_files(r)
        elif kind == 0x02:
            while r.byte():
                r.read(r.number())
        else:
            raise ArchiveError("the archive is laid out in a way this reader does not know")
    names = [name for name, has_content in files if has_content]
    if len(names) != sum(len(folder.sizes) for folder in folders):
        raise ArchiveError("the archive is laid out in a way this reader does not know")
    return folders, names


def extract_7z(archive: str, wanted: Callable[[str], str | None]) -> int:
    """Unpacks the files of a 7z archive that `wanted` gives a path for, each checked against the archive's own
    checksum; returns how many. Python reads no 7z itself, and a handheld's system need not have a tool that does:
    this reads the plain LZMA archives libretro publishes."""
    done = 0
    with open(archive, "rb") as f:
        folders, names = _read_archive(f)
        targets = [wanted(name) for name in names]
        index = 0
        for folder in folders:
            mine = targets[index:index + len(folder.sizes)]
            index += len(folder.sizes)
            if not any(mine):
                continue
            last = max(i for i, target in enumerate(mine) if target)
            pieces = folder.unpack(f)
            buffer = b""
            for target, size, checksum in list(zip(mine, folder.sizes, folder.checksums, strict=True))[:last + 1]:
                out = None
                if target:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    out = open(target + ".part", "wb")
                try:
                    crc, left = 0, size
                    while left:
                        buffer = buffer or next(pieces, b"")
                        if not buffer:
                            raise ArchiveError("the archive is cut short")
                        piece, buffer = buffer[:left], buffer[left:]
                        left -= len(piece)
                        if out:
                            out.write(piece)
                            crc = zlib.crc32(piece, crc)
                    if out and target and checksum is not None and crc != checksum:
                        raise ArchiveError(f"{os.path.basename(target)}: checksum does not match the archive")
                except BaseException:
                    if out and target:
                        out.close()
                        os.unlink(target + ".part")
                    raise
                if out and target:
                    out.close()
                    os.replace(target + ".part", target)
                    done += 1
    return done
