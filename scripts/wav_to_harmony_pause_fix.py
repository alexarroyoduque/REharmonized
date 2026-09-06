#!/usr/bin/env python3
"""
Harmony of Dissonance - WAV Song Injector + pause/resume engine patch

Runs the exact same song injection as wav_to_harmony_pause-not-resume-music.py
(unmodified, called as a subprocess) and then patches the resulting ROM's
sound engine so pausing no longer kills the BGM (player0) channel - fixing
the "silent until the whole song loops" bug for injected streamed songs,
without touching SE/sound-effect channels (which still stop normally).

Usage:
    python3 wav_to_harmony_pause_fix.py harmony.gba config.txt output.gba

Any extra arguments (--sample-rate, --base-note, --volume, --tempo,
--suggest-gaps) are forwarded as-is to wav_to_harmony_pause-not-resume-music.py.

The patch (validated live with gdb + mGBA before being baked in here):
  - At 0x080BC458 (inside the pause routine's per-player stop loop), the
    original `ldr r0,[r5,#0]` + `bl m4aMPlayStop` (6 bytes) is replaced by
    `bl <cave>` + a 2-byte filler.
  - The cave (16 bytes, written into a verified-free padding gap at
    0x080C6D34) does: `cmp r4,#4` (r4 is the loop's remaining-player
    counter, counting down from 4; ==4 only on the very first iteration,
    which is always player0/BGM) `beq skip; push {lr}; ldr r0,[r5,#0]; bl
    m4aMPlayStop; pop {pc}; skip: bx lr` - i.e. skip the stop call only for
    player0, run it normally for the other 3 (SE) players. The push/pop of
    lr around the nested `bl m4aMPlayStop` is required: without it, that
    inner call clobbers lr, so the loop's own return address is lost and
    the game eventually corrupts its stack and soft-resets on pause.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from pathlib import Path

BASE_SCRIPT = Path(__file__).parent / "wav_to_harmony_pause-not-resume-music.py"

GBA_ROM_BASE = 0x08000000

PATCH_ADDR = 0x080BC458
CAVE_ADDR = 0x080C6D34

# Original bytes expected at PATCH_ADDR (ldr r0,[r5,#0]; bl m4aMPlayStop),
# checked before patching so we never blindly overwrite unexpected content.
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inject .wav songs into Harmony of Dissonance and apply the pause/resume fix"
    )
    parser.add_argument("rom", type=Path, help="Original Harmony of Dissonance ROM (.gba)")
    parser.add_argument("config", type=Path, help="Text file: HARMONY_SONG WAV_PATH per line")
    parser.add_argument("output", type=Path, help="Output .gba file")
    parser.add_argument(
        "--skip-pause-patch",
        action="store_true",
        help="Only run the song injection, do not apply the pause/resume engine patch",
    )
    args, passthrough = parser.parse_known_args()

    rom_path = args.rom
    if not rom_path.is_file():
        raise SystemExit(f"ROM not found: {rom_path}")
    output_path = args.output

    print("Step 1/2: song injection (wav_to_harmony_pause-not-resume-music.py)")
    print("=" * 60)
    cmd = [sys.executable, str(BASE_SCRIPT), str(rom_path), str(args.config), str(output_path), *passthrough]
    subprocess.run(cmd, check=True)

    if args.skip_pause_patch:
        print()
        print("--skip-pause-patch given, done.")
        return

    print()
    print("Step 2/2: pause/resume engine patch")
    print("=" * 60)
    rom = bytearray(output_path.read_bytes())
    apply_pause_patch(rom)
    output_path.write_bytes(rom)
    print(f"OK  patched pause routine (cave @0x{CAVE_ADDR:08X}, call site @0x{PATCH_ADDR:08X})")
    print(f"Created: {output_path}")


if __name__ == "__main__":
    main()
