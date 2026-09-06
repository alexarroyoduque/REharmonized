#!/usr/bin/env python3
"""
Experimental MP2K/M4A song transplant for:
  Castlevania: Circle of the Moon (USA) song 0004
      -> Castlevania: Harmony of Dissonance (Europe) song 0001

Strategy:
- Keep Harmony as the first 8 MiB of the ROM.
- Append the user's Circle ROM as the second 8 MiB (16 MiB total).
- Point Harmony song 0001 at Circle song 0004's relocated header.
- Relocate the selected song's header pointers, track branch/pattern pointers,
  and voicegroup/sample pointers by +8 MiB.

This is deliberately a first prototype. It never modifies the input ROMs.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

GBA_ROM_BASE = 0x08000000
EXPECTED_ROM_SIZE = 0x00800000  # 8 MiB

HOD_GAME_CODE = b"ACHP"
CIRCLE_GAME_CODE = b"AAME"

HOD_SONG_TABLE = 0x001A6B5C
CIRCLE_SONG_TABLE = 0x00106E38

HOD_DEST_SONG_ID = 1
CIRCLE_SOURCE_SONG_ID = 4


def u32(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def p32(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", buf, off, value)


def gba_to_off(ptr: int) -> int:
    if not (GBA_ROM_BASE <= ptr < GBA_ROM_BASE + EXPECTED_ROM_SIZE):
        raise ValueError(f"Not an 8 MiB source-ROM pointer: 0x{ptr:08X}")
    return ptr - GBA_ROM_BASE


def is_source_rom_ptr(value: int) -> bool:
    return GBA_ROM_BASE <= value < GBA_ROM_BASE + EXPECTED_ROM_SIZE


def game_code(rom: bytes) -> bytes:
    return rom[0xAC:0xB0]


def read_song_header(rom: bytes, song_table_off: int, song_id: int):
    entry = song_table_off + song_id * 8
    ptr = u32(rom, entry)
    off = gba_to_off(ptr)
    track_count = rom[off]
    block_count = rom[off + 1]
    priority = rom[off + 2]
    reverb = rom[off + 3]
    voicegroup = u32(rom, off + 4)
    tracks = [u32(rom, off + 8 + 4 * i) for i in range(track_count)]
    return {
        "entry_off": entry,
        "ptr": ptr,
        "off": off,
        "track_count": track_count,
        "block_count": block_count,
        "priority": priority,
        "reverb": reverb,
        "voicegroup": voicegroup,
        "tracks": tracks,
    }


def relocate_track_pointers(out: bytearray, source_start: int, source_end: int, append_delta: int) -> int:
    """Patch GOTO/PATT/REPT pointers inside the copied Circle song data.

    We only patch operands that currently look like valid pointers back into this
    song's own track/pattern block. That keeps the scan conservative.
    """
    final_start = append_delta + source_start
    final_end = append_delta + source_end
    source_gba_start = GBA_ROM_BASE + source_start
    source_gba_end = GBA_ROM_BASE + source_end
    patched = 0

    i = final_start
    while i < final_end:
        op = out[i]

        # GOTO and PATT: opcode + 4-byte pointer
        if op in (0xB2, 0xB3) and i + 5 <= final_end:
            ptr = u32(out, i + 1)
            if source_gba_start <= ptr < source_gba_end:
                p32(out, i + 1, ptr + append_delta)
                patched += 1
                i += 5
                continue

        # REPT: opcode + repeat-count byte + 4-byte pointer
        if op == 0xB5 and i + 6 <= final_end:
            ptr = u32(out, i + 2)
            if source_gba_start <= ptr < source_gba_end:
                p32(out, i + 2, ptr + append_delta)
                patched += 1
                i += 6
                continue

        i += 1

    return patched


def relocate_voice_table(
    out: bytearray,
    source_table_off: int,
    append_delta: int,
    visited: set[int],
    entries: int = 128,
) -> int:
    """Relocate pointer-bearing ToneData entries in an Circle voice table.

    ToneData entries are 12 bytes. The primary data pointer is at +4. For
    split/drum entries (high type bits), +8 may also be a ROM pointer.
    Drum/split tables are followed recursively.
    """
    if source_table_off in visited:
        return 0
    visited.add(source_table_off)

    final_table_off = append_delta + source_table_off
    patched = 0
    recurse_targets: list[int] = []

    for idx in range(entries):
        eoff = final_table_off + idx * 12
        if eoff + 12 > len(out):
            break

        tone_type = out[eoff]
        primary = u32(out, eoff + 4)

        if is_source_rom_ptr(primary):
            p32(out, eoff + 4, primary + append_delta)
            patched += 1

            # 0x40/0x80 families point at another tone table.
            if tone_type & 0xC0:
                recurse_targets.append(primary - GBA_ROM_BASE)

        if tone_type & 0xC0:
            secondary = u32(out, eoff + 8)
            if is_source_rom_ptr(secondary):
                p32(out, eoff + 8, secondary + append_delta)
                patched += 1

    for target in recurse_targets:
        patched += relocate_voice_table(out, target, append_delta, visited, entries=128)

    return patched


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("harmony", type=Path, help="Harmony of Dissonance (Europe) .gba")
    ap.add_argument("circle", type=Path, help="Circle of the Moon (USA) .gba")
    ap.add_argument("output", type=Path, help="Output test ROM .gba")
    args = ap.parse_args()

    hod = args.harmony.read_bytes()
    circle = args.circle.read_bytes()

    if len(hod) != EXPECTED_ROM_SIZE:
        raise SystemExit(f"Harmony ROM must be exactly 8 MiB; got 0x{len(hod):X} bytes")
    if len(circle) != EXPECTED_ROM_SIZE:
        raise SystemExit(f"Circle ROM must be exactly 8 MiB; got 0x{len(circle):X} bytes")

    if game_code(hod) != HOD_GAME_CODE:
        raise SystemExit(f"Unexpected Harmony game code: {game_code(hod)!r}; expected {HOD_GAME_CODE!r}")
    if game_code(circle) != CIRCLE_GAME_CODE:
        raise SystemExit(f"Unexpected Circle game code: {game_code(circle)!r}; expected {CIRCLE_GAME_CODE!r}")

    hod_song = read_song_header(hod, HOD_SONG_TABLE, HOD_DEST_SONG_ID)
    circle_song = read_song_header(circle, CIRCLE_SONG_TABLE, CIRCLE_SOURCE_SONG_ID)

    if circle_song["track_count"] == 0:
        raise SystemExit("Circle source song has zero tracks")

    append_delta = len(hod)
    out = bytearray(hod + circle)

    # 1) Harmony song 0001 now points to the appended Circle song 0004 header.
    relocated_header_ptr = circle_song["ptr"] + append_delta
    p32(out, hod_song["entry_off"], relocated_header_ptr)

    # 2) Relocate pointers stored in Circle's copied song header.
    copied_header = append_delta + circle_song["off"]
    voice_ptr = u32(out, copied_header + 4)
    if not is_source_rom_ptr(voice_ptr):
        raise SystemExit(f"Unexpected source voicegroup pointer 0x{voice_ptr:08X}")
    p32(out, copied_header + 4, voice_ptr + append_delta)

    for i in range(circle_song["track_count"]):
        poff = copied_header + 8 + i * 4
        ptr = u32(out, poff)
        if not is_source_rom_ptr(ptr):
            raise SystemExit(f"Unexpected track pointer 0x{ptr:08X}")
        p32(out, poff, ptr + append_delta)

    # 3) The Circle tracks/patterns are contiguous immediately before the header.
    track_offsets = [gba_to_off(p) for p in circle_song["tracks"]]
    track_block_start = min(track_offsets)
    track_block_end = circle_song["off"]
    track_ptrs_patched = relocate_track_pointers(out, track_block_start, track_block_end, append_delta)

    # 4) Relocate sample/tone pointers in the song's voicegroup and nested drum/split tables.
    voicegroup_off = gba_to_off(circle_song["voicegroup"])
    voice_ptrs_patched = relocate_voice_table(out, voicegroup_off, append_delta, set())

    args.output.write_bytes(out)

    print("Created experimental 16 MiB ROM:")
    print(f"  {args.output}")
    print()
    print("Destination:")
    print(f"  Harmony song {HOD_DEST_SONG_ID:04d}: 0x{hod_song['ptr']:08X}")
    print("Source:")
    print(f"  Circle song {CIRCLE_SOURCE_SONG_ID:04d}:    0x{circle_song['ptr']:08X}")
    print(f"  tracks: {circle_song['track_count']}")
    print(f"  voicegroup: 0x{circle_song['voicegroup']:08X}")
    print("Relocated:")
    print(f"  new song pointer: 0x{relocated_header_ptr:08X}")
    print(f"  track GOTO/PATT/REPT pointers patched: {track_ptrs_patched}")
    print(f"  voice/sample pointers patched: {voice_ptrs_patched}")
    print()
    print("First test this output in agbplay. If song 0001 plays correctly there, test the intro in mGBA.")


if __name__ == "__main__":
    main()
