"""M2 USA caller-side pause patch and power-of-two output sizing."""
from __future__ import annotations

from .rom import GBA_ROM_BASE, MAX_GBA_ROM_SIZE, is_advance_collection

PAUSE_CALL_ADDR = 0x080BB40C
PAUSE_STUB_ADDR = 0x080BD600
ORIGINAL_PAUSE_CALL = bytes.fromhex("01f01cf8")
PAUSE_CALL_BYTES = bytes.fromhex("02f0f8f8")
PAUSE_STUB_BYTES = bytes.fromhex("30b5054d03242868fff76cfa0c35013cf9d130bc01bc0047386b1a08")


def apply_pause_patch(rom: bytearray) -> None:
    """Stop only players 1-3; leave M2's BGM and all SVC entries intact."""
    if not is_advance_collection(rom):
        raise SystemExit("Unsupported Advance Collection sound engine; refusing to patch")
    signatures = (
        (PAUSE_CALL_ADDR, ORIGINAL_PAUSE_CALL),
        (PAUSE_STUB_ADDR, bytes(len(PAUSE_STUB_BYTES))),
        (0x081A6B38, bytes.fromhex("00500003002400030200000040500003a024000302000000905000034025000301000000")),
    )
    for address, expected in signatures:
        offset = address - GBA_ROM_BASE
        current = bytes(rom[offset:offset + len(expected)])
        if current != expected:
            raise SystemExit(f"Advance Collection patch site at 0x{address:08X} has unexpected bytes; refusing to patch")
    call = PAUSE_CALL_ADDR - GBA_ROM_BASE
    stub = PAUSE_STUB_ADDR - GBA_ROM_BASE
    rom[call:call + len(PAUSE_CALL_BYTES)] = PAUSE_CALL_BYTES
    rom[stub:stub + len(PAUSE_STUB_BYTES)] = PAUSE_STUB_BYTES


def pad_output(rom: bytes | bytearray) -> bytes:
    """The Collection GBA core requires a power-of-two size, capped at 32 MiB."""
    if len(rom) > MAX_GBA_ROM_SIZE:
        raise SystemExit("Advance Collection output would exceed the GBA 32 MiB ROM limit")
    return bytes(rom) + b"\xFF" * (MAX_GBA_ROM_SIZE - len(rom))