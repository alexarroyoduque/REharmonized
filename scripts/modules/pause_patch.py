"""Verified pause/resume engine patch."""
from __future__ import annotations

from .rom import GBA_ROM_BASE

PATCH_ADDR = 0x080BC458


CAVE_ADDR = 0x080C6D34


ORIGINAL_PATCH_BYTES = bytes.fromhex("286800f043fb")


PATCH_BYTES = bytes.fromhex("0af06cfc0000")


CAVE_BYTES = bytes.fromhex("042c04d000b52868f5f7d2fe00bd7047")


def apply_pause_patch(rom: bytearray) -> None:
    patch_off = PATCH_ADDR - GBA_ROM_BASE
    cave_off = CAVE_ADDR - GBA_ROM_BASE

    current = bytes(rom[patch_off : patch_off + len(ORIGINAL_PATCH_BYTES)])
    if current != ORIGINAL_PATCH_BYTES:
        raise SystemExit(
            f"Pause-patch site at 0x{PATCH_ADDR:08X} has unexpected bytes "
            f"({current.hex()}, expected {ORIGINAL_PATCH_BYTES.hex()}) - "
            "refusing to patch (engine code may have shifted)."
        )

    cave_region = bytes(rom[cave_off : cave_off + len(CAVE_BYTES)])
    if any(cave_region):
        raise SystemExit(
            f"Cave region at 0x{CAVE_ADDR:08X} is not free (found "
            f"{cave_region.hex()}) - refusing to patch."
        )

    rom[cave_off : cave_off + len(CAVE_BYTES)] = CAVE_BYTES
    rom[patch_off : patch_off + len(PATCH_BYTES)] = PATCH_BYTES
