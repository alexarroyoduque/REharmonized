"""Keep BGM advancing while paused, but mute its output until resume.

The original pause flag at 0x030021A8 gates final channel gains, not track
volume or PCM position. Mark BGM tracks dirty on both transitions so their
existing channels update immediately. Other players keep their original
stop/continue behavior, including menu effects.

pause_mute.s is the source of STUB_BYTES (ARM7TDMI Thumb, linked at zero).
Local branches are position independent; ROM/RAM literals match the verified
USA/Europe engine. Two 8-byte veneers occupy the original padding cave.
The 144-byte payload is appended after the injected audio; no RAM is reserved
and no assembler is needed at runtime or in Pyodide.
"""
from __future__ import annotations

import struct

from .rom import GBA_ROM_BASE, MAX_GBA_ROM_SIZE

PATCH_ADDR = 0x080BC458


CAVE_ADDR = 0x080C6D34


ORIGINAL_PATCH_BYTES = bytes.fromhex("286800f043fb")


PATCH_BYTES = bytes.fromhex("0af06cfc0000")


RESUME_ADDR = 0x080BC490
VOLUME_ADDR = 0x080BBF2C
PAUSED_FLAG = 0x030021A8
BGM_PLAYER = 0x03004FC0
BGM_TRACKS = 0x030021D0
BGM_TRACKS_END = 0x03002400
ORIGINAL_RESUME_BYTES = bytes.fromhex("2868fff7dffe")
ORIGINAL_VOLUME_BYTES = bytes.fromhex("a17c142022568023")
VENEER_PREFIX = bytes.fromhex("004b1847")
CAVE_SIZE = 16
PAUSE_STUB_OFFSET = 0
RESUME_STUB_OFFSET = 0x16
VOLUME_STUB_OFFSET = 0x48
STUB_BYTES = bytes.fromhex(
    "00b5042c03d1286800f00ff800bd286800f02ef800bd00b5042c02d12868"
    "00f004f8286800f026f800bd017ac26a002909d013788020034202d00320"
    "0343137050320139f5d170470b480088002809d00a48854206d30a488542"
    "03d20020a070e0707047a17c14202256802305480047054b1847054b1847"
    "a8210003d02100030024000335bf0b08e5ca0b0855c20b08"
)


def _thumb_bl(source: int, target: int) -> bytes:
    displacement = target - (source + 4)
    if displacement % 2 or not -(1 << 22) <= displacement < (1 << 22):
        raise ValueError("Thumb BL target is unaligned or out of range")
    return struct.pack("<HH", 0xF000 | ((displacement >> 12) & 0x7FF),
                       0xF800 | ((displacement >> 1) & 0x7FF))


def _veneer(target: int) -> bytes:
    return VENEER_PREFIX + struct.pack("<I", target | 1)


def apply_pause_patch(rom: bytearray) -> None:
    """Verify every assumption before modifying any byte of the ROM."""
    signatures = (
        (PATCH_ADDR, ORIGINAL_PATCH_BYTES),
        (RESUME_ADDR, ORIGINAL_RESUME_BYTES),
        (VOLUME_ADDR, ORIGINAL_VOLUME_BYTES),
        (0x081A6B2C, bytes.fromhex("c04f0003d021000307000000005000030024000302000000")),
        (0x080BB414, struct.pack("<I", PAUSED_FLAG)),
        (0x080BB42C, struct.pack("<I", PAUSED_FLAG)),
        (CAVE_ADDR, bytes(CAVE_SIZE)),
    )
    for address, expected in signatures:
        offset = address - GBA_ROM_BASE
        current = bytes(rom[offset:offset + len(expected)])
        if current != expected:
            raise SystemExit(
                f"Pause-patch site at 0x{address:08X} has unexpected bytes "
                f"({current.hex()}, expected {expected.hex()}) - refusing to patch."
            )

    payload_off = (len(rom) + 3) & ~3
    if payload_off + len(STUB_BYTES) > MAX_GBA_ROM_SIZE:
        raise SystemExit("Pause/mute payload would exceed the GBA 32 MiB ROM limit")
    payload_addr = GBA_ROM_BASE + payload_off
    patches = (
        (PATCH_ADDR, PATCH_BYTES),
        (RESUME_ADDR, _thumb_bl(RESUME_ADDR, CAVE_ADDR + 8) + b"\x00\x00"),
        (VOLUME_ADDR, _veneer(payload_addr + VOLUME_STUB_OFFSET)),
        (CAVE_ADDR, _veneer(payload_addr + PAUSE_STUB_OFFSET)
         + _veneer(payload_addr + RESUME_STUB_OFFSET)),
    )
    rom.extend(bytes(payload_off - len(rom)) + STUB_BYTES)
    for address, data in patches:
        offset = address - GBA_ROM_BASE
        rom[offset:offset + len(data)] = data
