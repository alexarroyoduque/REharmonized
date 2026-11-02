"""M2 USA caller-side pause patch and power-of-two output sizing."""
from __future__ import annotations

import struct

from .rom import GBA_ROM_BASE, MAX_GBA_ROM_SIZE, is_advance_collection

PAUSE_CALL_ADDR = 0x080BB40C
PAUSE_STUB_ADDR = 0x080BD600
RESUME_CALL_ADDR = 0x080BB424
RESUME_STUB_ADDR = 0x080BD61E
VOLUME_CONTROL_ADDR = 0x080BD274
CONTINUE_ALL_ADDR = 0x080BC480
ORIGINAL_PAUSE_CALL = bytes.fromhex("01f01cf8")
ORIGINAL_RESUME_CALL = bytes.fromhex("01f02cf8")
PAUSE_CALL_BYTES = bytes.fromhex("02f0f8f8")
PAUSE_RESUME_STUB_BYTES = bytes.fromhex(
    "30b50c4d03242868fff76cfa0c35013cf9d109487f210022fff72cfe30bd"
    "13b505487f2101221202fff724fe03bcfef727ff10bd386b1a08c04f0003"
)
PAUSE_STUB_BYTES = PAUSE_RESUME_STUB_BYTES
RESUME_STUB_OFFSET = RESUME_STUB_ADDR - PAUSE_STUB_ADDR
VOLUME_CONTROL_SIGNATURE = bytes.fromhex("93df7047")
CONTINUE_ALL_SIGNATURE = bytes.fromhex("0420014991df70472c6b1a08")
BG_PLAYER_SIGNATURE = bytes.fromhex("c04f0003d021000307000000")


def _thumb_bl(source: int, target: int) -> bytes:
    displacement = target - (source + 4)
    if displacement % 2 or not -(1 << 22) <= displacement < (1 << 22):
        raise ValueError("Thumb BL target is unaligned or out of range")
    return struct.pack("<HH", 0xF000 | ((displacement >> 12) & 0x7FF),
                       0xF800 | ((displacement >> 1) & 0x7FF))


def apply_pause_patch(rom: bytearray) -> None:
    """Mute M2's BGM while paused and restore it before continuing playback."""
    if not is_advance_collection(rom):
        raise SystemExit("Unsupported Advance Collection sound engine; refusing to patch")
    signatures = (
        (PAUSE_CALL_ADDR, ORIGINAL_PAUSE_CALL),
        (RESUME_CALL_ADDR, ORIGINAL_RESUME_CALL),
        (VOLUME_CONTROL_ADDR, VOLUME_CONTROL_SIGNATURE),
        (CONTINUE_ALL_ADDR, CONTINUE_ALL_SIGNATURE),
        (PAUSE_STUB_ADDR, bytes(len(PAUSE_RESUME_STUB_BYTES))),
        (0x081A6B2C, BG_PLAYER_SIGNATURE),
        (0x081A6B38, bytes.fromhex("00500003002400030200000040500003a024000302000000905000034025000301000000")),
    )
    for address, expected in signatures:
        offset = address - GBA_ROM_BASE
        current = bytes(rom[offset:offset + len(expected)])
        if current != expected:
            raise SystemExit(f"Advance Collection patch site at 0x{address:08X} has unexpected bytes; refusing to patch")
    call = PAUSE_CALL_ADDR - GBA_ROM_BASE
    stub = PAUSE_STUB_ADDR - GBA_ROM_BASE
    resume_call = RESUME_CALL_ADDR - GBA_ROM_BASE
    rom[call:call + 4] = _thumb_bl(PAUSE_CALL_ADDR, PAUSE_STUB_ADDR)
    rom[resume_call:resume_call + 4] = _thumb_bl(RESUME_CALL_ADDR, RESUME_STUB_ADDR)
    rom[stub:stub + len(PAUSE_RESUME_STUB_BYTES)] = PAUSE_RESUME_STUB_BYTES


def pad_output(rom: bytes | bytearray) -> bytes:
    """The Collection GBA core requires a power-of-two size, capped at 32 MiB."""
    if len(rom) > MAX_GBA_ROM_SIZE:
        raise SystemExit("Advance Collection output would exceed the GBA 32 MiB ROM limit")
    return bytes(rom) + b"\xFF" * (MAX_GBA_ROM_SIZE - len(rom))