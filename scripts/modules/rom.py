"""ROM constants, binary access and original-ROM validation."""
from __future__ import annotations

import struct
from pathlib import Path

GBA_ROM_BASE = 0x08000000


SOURCE_ROM_SIZE = 0x00800000  # 8 MiB


MAX_GBA_ROM_SIZE = 0x02000000  # 32 MiB


HOD_GAME_CODES = (b"ACHP", b"ACHE")  # Europe, USA - verified byte-identical


HOD_SONG_TABLE = 0x001A6B5C


def u32(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def p32(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", buf, off, value)


def game_code(rom: bytes) -> bytes:
    return rom[0xAC:0xB0]


def parse_int(value: str) -> int:
    return int(value, 0)


def validate_harmony(path: Path) -> bytes:
    if not path.exists():
        raise SystemExit(f"Missing Harmony ROM: {path}")

    rom = path.read_bytes()

    if len(rom) != SOURCE_ROM_SIZE:
        raise SystemExit(
            f"Harmony ROM must be exactly 8 MiB; got {len(rom)} bytes (0x{len(rom):X})"
        )

    code = game_code(rom)
    if code not in HOD_GAME_CODES:
        raise SystemExit(
            f"Unexpected Harmony game code: {code!r}; expected one of {HOD_GAME_CODES!r}"
        )

    return rom
