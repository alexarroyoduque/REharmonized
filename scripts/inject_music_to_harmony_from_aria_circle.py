#!/usr/bin/env python3
"""
Harmony of Dissonance - GBA Music Injector

Builds a new Harmony of Dissonance ROM using songs from:
  - Castlevania: Aria of Sorrow (Europe)
  - Castlevania: Circle of the Moon (USA)

Usage:
    python3 inject_music.py harmony.gba config.txt output.gba \
        [--aria aria.gba] [--circle circle.gba]

harmony.gba does not have to be the pristine original: it may already be a
ROM produced by this script or by wav_to_harmony.py (it just needs to
contain a valid, unmodified Harmony ROM in its first 8 MiB).

Config syntax:
    # source   harmony_song   source_song
    aria       1              2
    circle     15             4
    aria       32             18

Song IDs may be decimal or hexadecimal:
    aria 0x01 0x02

Strategy:
- Only the bytes actually needed for each replacement are copied: the
  song's track/pattern data, its voicegroup (instrument) table, and the
  WaveData + PCM samples referenced from that table. Everything else in
  Aria/Circle's 8 MiB is left out, instead of appending the whole ROM.
- Identical chunks (e.g. a voicegroup or sample shared by two songs) are
  copied only once.
- Input ROMs are never modified.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# ROM / GAME CONSTANTS
# ---------------------------------------------------------------------------

GBA_ROM_BASE = 0x08000000
SOURCE_ROM_SIZE = 0x00800000  # 8 MiB
MAX_GBA_ROM_SIZE = 0x02000000 # 32 MiB

HOD_GAME_CODE = b"ACHP"
ARIA_GAME_CODE = b"A2CP"
CIRCLE_GAME_CODE = b"AAME"

HOD_SONG_TABLE = 0x001A6B5C
ARIA_SONG_TABLE = 0x0027CD4C
CIRCLE_SONG_TABLE = 0x00106E38

SOURCE_INFO = {
    "aria": {
        "game_code": ARIA_GAME_CODE,
        "song_table": ARIA_SONG_TABLE,
        "display": "Aria of Sorrow",
    },
    "circle": {
        "game_code": CIRCLE_GAME_CODE,
        "song_table": CIRCLE_SONG_TABLE,
        "display": "Circle of the Moon",
    },
}


@dataclass(frozen=True)
class Replacement:
    source: str
    harmony_song: int
    source_song: int


def u32(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def p32(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", buf, off, value)


def game_code(rom: bytes) -> bytes:
    return rom[0xAC:0xB0]


def parse_song_id(value: str) -> int:
    try:
        song_id = int(value, 0)
    except ValueError:
        # Friendly fallback: plain values such as "0004" are decimal.
        try:
            song_id = int(value, 10)
        except ValueError as exc:
            raise ValueError(f"Invalid song ID: {value!r}") from exc

    if not (0 <= song_id <= 0xFFFF):
        raise ValueError(f"Song ID out of range: {value!r}")
    return song_id


def source_ptr_to_off(ptr: int) -> int:
    if not (GBA_ROM_BASE <= ptr < GBA_ROM_BASE + SOURCE_ROM_SIZE):
        raise ValueError(f"Not an 8 MiB source-ROM pointer: 0x{ptr:08X}")
    return ptr - GBA_ROM_BASE


def is_source_rom_ptr(value: int) -> bool:
    return GBA_ROM_BASE <= value < GBA_ROM_BASE + SOURCE_ROM_SIZE


def read_song_header(rom: bytes | bytearray, song_table_off: int, song_id: int):
    entry = song_table_off + song_id * 8

    if entry + 8 > len(rom):
        raise ValueError(f"Song {song_id} entry is outside the ROM")

    ptr = u32(rom, entry)
    off = source_ptr_to_off(ptr)

    if off + 8 > len(rom):
        raise ValueError(f"Song {song_id} header is outside the ROM")

    track_count = rom[off]
    block_count = rom[off + 1]
    priority = rom[off + 2]
    reverb = rom[off + 3]
    voicegroup = u32(rom, off + 4)

    if track_count > 32:
        raise ValueError(
            f"Song {song_id} has suspicious track count {track_count}; "
            "check the song table/version"
        )

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


def parse_config(path: Path) -> list[Replacement]:
    replacements: list[Replacement] = []

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        parts = line.replace(",", " ").split()
        if len(parts) != 3:
            raise SystemExit(
                f"{path}:{lineno}: expected 3 fields: "
                "aria|circle HARMONY_SONG SOURCE_SONG"
            )

        source = parts[0].lower()
        if source not in SOURCE_INFO:
            raise SystemExit(
                f"{path}:{lineno}: invalid source {parts[0]!r}; "
                "use 'aria' or 'circle'"
            )

        try:
            harmony_song = parse_song_id(parts[1])
            source_song = parse_song_id(parts[2])
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: {exc}") from exc

        replacements.append(Replacement(source, harmony_song, source_song))

    if not replacements:
        raise SystemExit(f"{path}: no replacements found")

    # Prevent accidental duplicate Harmony targets.
    seen: dict[int, int] = {}
    for idx, repl in enumerate(replacements, 1):
        if repl.harmony_song in seen:
            raise SystemExit(
                f"{path}: Harmony song {repl.harmony_song} is replaced more than once "
                f"(entries {seen[repl.harmony_song]} and {idx})"
            )
        seen[repl.harmony_song] = idx

    return replacements


def validate_harmony(path: Path) -> bytes:
    if not path.exists():
        raise SystemExit(f"Missing Harmony ROM: {path}")

    rom = path.read_bytes()

    if len(rom) < SOURCE_ROM_SIZE:
        raise SystemExit(
            f"Harmony ROM must be at least 8 MiB; got {len(rom)} bytes (0x{len(rom):X})"
        )

    code = game_code(rom)
    if code != HOD_GAME_CODE:
        raise SystemExit(
            f"Unexpected Harmony game code: {code!r}; expected {HOD_GAME_CODE!r}"
        )

    return rom


def validate_source(path: Path, expected_code: bytes, display_name: str) -> bytes:
    if not path.exists():
        raise SystemExit(f"Missing {display_name} ROM: {path}")

    rom = path.read_bytes()

    if len(rom) != SOURCE_ROM_SIZE:
        raise SystemExit(
            f"{display_name} ROM must be exactly 8 MiB; "
            f"got {len(rom)} bytes (0x{len(rom):X})"
        )

    code = game_code(rom)
    if code != expected_code:
        raise SystemExit(
            f"Unexpected {display_name} game code: {code!r}; "
            f"expected {expected_code!r}"
        )

    return rom


# ---------------------------------------------------------------------------
# Compact extraction: copy only the bytes a replacement needs, deduplicated
# by (source, original_offset) so shared voicegroups/samples aren't repeated.
# ---------------------------------------------------------------------------

ChunkKey = tuple[str, int]


def copy_track_data(
    out: bytearray,
    source_rom: bytes,
    source_id: str,
    start: int,
    end: int,
    copied: dict[ChunkKey, int],
) -> int:
    """Copy a song's track/pattern byte range and patch internal GOTO/PATT/REPT
    pointers that pointed within that same range. Returns the new offset."""
    key = (source_id, start)
    if key in copied:
        return copied[key]

    dest_start = len(out)
    out += source_rom[start:end]
    copied[key] = dest_start

    delta = dest_start - start
    source_gba_start = GBA_ROM_BASE + start
    source_gba_end = GBA_ROM_BASE + end
    dest_end = dest_start + (end - start)

    i = dest_start
    while i < dest_end:
        op = out[i]

        # GOTO / PATT: opcode + 4-byte pointer
        if op in (0xB2, 0xB3) and i + 5 <= dest_end:
            ptr = u32(out, i + 1)
            if source_gba_start <= ptr < source_gba_end:
                p32(out, i + 1, ptr + delta)
                i += 5
                continue

        # REPT: opcode + repeat byte + 4-byte pointer
        if op == 0xB5 and i + 6 <= dest_end:
            ptr = u32(out, i + 2)
            if source_gba_start <= ptr < source_gba_end:
                p32(out, i + 2, ptr + delta)
                i += 6
                continue

        i += 1

    return dest_start


def copy_wave_data(
    out: bytearray,
    source_rom: bytes,
    source_id: str,
    wave_off: int,
    copied: dict[ChunkKey, int],
) -> int:
    """Copy a WaveData header + its sample data. Returns the new offset.

    Handles the three MP2K sample encodings actually used by these games'
    engine (matching agbplay's Rom parsing): raw PCM, GameFreak-style DPCM
    (predictor byte + 4-bit deltas, 64 samples per 33-byte block), and
    Camelot ADPCM (negative sample count, 2 samples/byte).
    """
    key = (source_id, wave_off)
    if key in copied:
        return copied[key]

    if wave_off + 16 > len(source_rom):
        raise ValueError(f"WaveData at 0x{wave_off:X} is outside the ROM")

    mode = source_rom[wave_off]
    size = u32(source_rom, wave_off + 12)

    if mode == 1:
        data_len = (size + 63) // 64 * 0x21
    elif mode == 0 and size >= 0x80000000:
        data_len = ((0x100000000 - size) // 2)
    elif mode == 0:
        data_len = size
    else:
        raise ValueError(f"WaveData at 0x{wave_off:X} uses an unsupported sample mode {mode}")

    total = 16 + data_len
    if wave_off + total > len(source_rom):
        raise ValueError(f"WaveData at 0x{wave_off:X} + size exceeds ROM bounds")

    while len(out) % 4 != 0:  # WaveData's u32 fields must stay word-aligned
        out.append(0)

    dest_off = len(out)
    out += source_rom[wave_off:wave_off + total]
    copied[key] = dest_off
    return dest_off


BANKDATA_TYPE_SPLIT = 0x40   # bit: primary=ToneData sub-table, secondary=128-byte key->index map
BANKDATA_TYPE_RHYTHM = 0x80  # exact value: primary=ToneData sub-table indexed directly by key


def copy_key_map(
    out: bytearray,
    source_rom: bytes,
    source_id: str,
    map_off: int,
    copied: dict[ChunkKey, int],
) -> int:
    """Copy a 128-byte keysplit map (one sub-instrument index per MIDI key).
    This is plain data (no pointers), unlike a ToneData table."""
    key = (source_id, map_off)
    if key in copied:
        return copied[key]

    length = min(128, len(source_rom) - map_off)
    if length <= 0:
        raise ValueError(f"Key map at 0x{map_off:X} is outside the ROM")

    dest_off = len(out)
    out += source_rom[map_off:map_off + length]
    copied[key] = dest_off
    return dest_off


def copy_voice_table(
    out: bytearray,
    source_rom: bytes,
    source_id: str,
    table_off: int,
    copied: dict[ChunkKey, int],
    entries: int = 128,
) -> int:
    """Copy a 128-entry ToneData table and every WaveData/sub-table it
    references, deduplicated. Returns the new table offset."""
    key = (source_id, table_off)
    if key in copied:
        return copied[key]

    length = entries * 12
    if table_off + length > len(source_rom):
        length = len(source_rom) - table_off
        entries = length // 12

    while len(out) % 4 != 0:  # ToneData's pointer fields must stay word-aligned
        out.append(0)

    dest_off = len(out)
    out += source_rom[table_off:table_off + length]
    copied[key] = dest_off

    for idx in range(entries):
        dest_eoff = dest_off + idx * 12

        tone_type = out[dest_eoff]
        primary = u32(out, dest_eoff + 4)
        is_split = bool(tone_type & BANKDATA_TYPE_SPLIT)
        is_rhythm = tone_type == BANKDATA_TYPE_RHYTHM
        has_sub_table = is_split or is_rhythm

        # Not every one of the 128 slots is actually used by a real song; the
        # unused tail can contain stale/garbage pointer-shaped bytes. If an
        # entry doesn't parse as a valid WaveData/sub-table, leave it as-is
        # instead of aborting the whole injection.
        if is_source_rom_ptr(primary):
            primary_off = source_ptr_to_off(primary)
            try:
                if has_sub_table:
                    # Split/rhythm instruments point at another ToneData table.
                    new_off = copy_voice_table(
                        out, source_rom, source_id, primary_off, copied, entries=entries
                    )
                else:
                    new_off = copy_wave_data(out, source_rom, source_id, primary_off, copied)
            except ValueError:
                new_off = None
            if new_off is not None:
                p32(out, dest_eoff + 4, GBA_ROM_BASE + new_off)

        # Only split (0x40) instruments dereference +8 as a pointer (to a
        # 128-byte key->sub-instrument map). Rhythm (0x80) instruments index
        # their sub-table directly by note key and don't use +8 as a pointer.
        if is_split:
            secondary = u32(out, dest_eoff + 8)
            if is_source_rom_ptr(secondary):
                secondary_off = source_ptr_to_off(secondary)
                try:
                    new_off = copy_key_map(out, source_rom, source_id, secondary_off, copied)
                except ValueError:
                    new_off = None
                if new_off is not None:
                    p32(out, dest_eoff + 8, GBA_ROM_BASE + new_off)

    return dest_off

    return dest_off


def inject_one(
    out: bytearray,
    source_rom: bytes,
    repl: Replacement,
    source_song_table: int,
    copied: dict[ChunkKey, int],
):
    src_song = read_song_header(source_rom, source_song_table, repl.source_song)

    if src_song["track_count"] == 0:
        raise ValueError(f"{repl.source} song {repl.source_song} has zero tracks")

    # 1) Copy + relocate this song's track/pattern data.
    track_offsets = [source_ptr_to_off(p) for p in src_song["tracks"]]
    track_block_start = min(track_offsets)
    track_block_end = src_song["off"]  # header sits right after track data

    dest_track_off = copy_track_data(
        out, source_rom, repl.source, track_block_start, track_block_end, copied
    )
    track_delta = dest_track_off - track_block_start

    # 2) Copy + relocate the referenced voicegroup (and its samples).
    voicegroup_off = source_ptr_to_off(src_song["voicegroup"])
    dest_voicegroup_off = copy_voice_table(
        out, source_rom, repl.source, voicegroup_off, copied
    )

    # 3) Copy this song's own header, patched to point at the new locations.
    while len(out) % 4 != 0:  # header must land on a 4-byte boundary
        out.append(0)

    dest_header_off = len(out)
    header_len = 8 + 4 * src_song["track_count"]
    header_bytes = bytearray(source_rom[src_song["off"]: src_song["off"] + header_len])
    p32(header_bytes, 4, GBA_ROM_BASE + dest_voicegroup_off)
    for i, orig_ptr in enumerate(src_song["tracks"]):
        orig_off = source_ptr_to_off(orig_ptr)
        p32(header_bytes, 8 + 4 * i, GBA_ROM_BASE + orig_off + track_delta)
    out += header_bytes

    return {
        "source_original": src_song["ptr"],
        "new_pointer": GBA_ROM_BASE + dest_header_off,
        "tracks": src_song["track_count"],
        "voicegroup": src_song["voicegroup"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inject Aria/Circle MP2K songs into Harmony of Dissonance"
    )
    parser.add_argument(
        "harmony",
        type=Path,
        help="Harmony ROM to start from (may already be edited by this script "
        "or by wav_to_harmony.py)",
    )
    parser.add_argument(
        "config",
        type=Path,
        help="Text file containing: aria|circle HARMONY_SONG SOURCE_SONG",
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Output .gba file (input ROMs are never modified)",
    )
    parser.add_argument(
        "--aria",
        type=Path,
        default=Path("aria.gba"),
        help="Aria of Sorrow (Europe) .gba, needed if config references 'aria' (default: aria.gba)",
    )
    parser.add_argument(
        "--circle",
        type=Path,
        default=Path("circle.gba"),
        help="Circle of the Moon (USA) .gba, needed if config references 'circle' (default: circle.gba)",
    )
    args = parser.parse_args()

    replacements = parse_config(args.config)

    harmony = validate_harmony(args.harmony)

    needed_sources = {repl.source for repl in replacements}
    source_roms: dict[str, bytes] = {}
    if "aria" in needed_sources:
        source_roms["aria"] = validate_source(args.aria, ARIA_GAME_CODE, "Aria")
    if "circle" in needed_sources:
        source_roms["circle"] = validate_source(args.circle, CIRCLE_GAME_CODE, "Circle")

    out = bytearray(harmony)
    copied: dict[ChunkKey, int] = {}
    results = []

    print("Harmony of Dissonance - GBA Music Injector")
    print("=" * 48)
    print(f"Harmony: {args.harmony} ({len(harmony) / (1024 * 1024):.2f} MiB)")
    if "aria" in source_roms:
        print(f"Aria:    {args.aria}")
    if "circle" in source_roms:
        print(f"Circle:  {args.circle}")
    print(f"Config:  {args.config}")
    print(f"Output:  {args.output}")
    print()

    for repl in replacements:
        info = SOURCE_INFO[repl.source]
        entry_off = HOD_SONG_TABLE + repl.harmony_song * 8
        if entry_off + 8 > len(harmony):
            raise SystemExit(f"Harmony song {repl.harmony_song} is outside the song table")

        before = len(out)
        try:
            result = inject_one(
                out=out,
                source_rom=source_roms[repl.source],
                repl=repl,
                source_song_table=info["song_table"],
                copied=copied,
            )
        except (ValueError, struct.error, IndexError) as exc:
            raise SystemExit(
                f"Failed replacing Harmony song {repl.harmony_song} "
                f"with {info['display']} song {repl.source_song}: {exc}"
            ) from exc

        p32(out, entry_off, result["new_pointer"])
        added = len(out) - before
        results.append((repl, info, result))

        print(
            f"OK  Harmony {repl.harmony_song:04d} "
            f"<- {info['display']} {repl.source_song:04d}"
        )
        print(
            f"    tracks={result['tracks']}  "
            f"new=0x{result['new_pointer']:08X}  "
            f"added={added} bytes"
        )

    if len(out) > MAX_GBA_ROM_SIZE:
        raise SystemExit("Result would exceed the GBA 32 MiB ROM limit")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)

    print()
    print("=" * 48)
    print(f"Created: {args.output}")
    print(f"Size:    {len(out) / (1024 * 1024):.2f} MiB (was {len(harmony) / (1024 * 1024):.2f} MiB)")
    print(f"Songs:   {len(results)} replacement(s)")


if __name__ == "__main__":
    main()
