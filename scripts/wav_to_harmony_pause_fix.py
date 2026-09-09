#!/usr/bin/env python3
"""
Harmony of Dissonance - WAV Song Injector + pause/resume engine patch + per-track loudness control

All-in-one script: builds and injects each replacement song directly (reusing
wav_to_harmony_pause-not-resume-music.py's helper functions via dynamic
import, since that script's filename contains hyphens and can't be
`import`-ed normally - and is never modified), then applies the pause/resume
engine patch to the result.

Usage:
    python3 wav_to_harmony_pause_fix.py harmony.gba config.txt output.gba

Config format (4th field optional, fully backward compatible with 3-field lines):
    HARMONY_SONG_ID   WAV_PATH   auto|TEMPO   [auto|off|TARGET_RMS]

    (missing) / auto  -> RMS-normalize to 0.45 (default)
    off               -> no gain applied at all, use the .wav at its own
                         recorded amplitude (still passed through soft_limit
                         as a safety net against genuine >0dB peaks, so it
                         can't hard-clip, but nothing gets boosted/saturated)
    TARGET_RMS        -> a number in (0, 1], e.g. 0.30, overrides the RMS
                         target for this song only. Lower = less gain = less
                         soft-limiter saturation (quieter); higher = more gain
                         = more saturation (louder, more coloration on peaks).

The pause/resume patch (validated live with gdb + mGBA before being baked in
here):
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
import importlib.util
import shlex
from pathlib import Path

GBA_ROM_BASE = 0x08000000

PATCH_ADDR = 0x080BC458
CAVE_ADDR = 0x080C6D34

# Original bytes expected at PATCH_ADDR (ldr r0,[r5,#0]; bl m4aMPlayStop),
# checked before patching so we never blindly overwrite unexpected content.
ORIGINAL_PATCH_BYTES = bytes.fromhex("286800f043fb")

PATCH_BYTES = bytes.fromhex("0af06cfc0000")
CAVE_BYTES = bytes.fromhex("042c04d000b52868f5f7d2fe00bd7047")

# Matches base.normalize_loudness's own default target_rms.
DEFAULT_TARGET_RMS = 0.45

_BASE_PATH = Path(__file__).parent / "wav_to_harmony_pause-not-resume-music.py"
_spec = importlib.util.spec_from_file_location("wav_to_harmony_base", _BASE_PATH)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


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


def parse_config(path: Path) -> list[tuple[int, Path, int | None, float | None]]:
    """Same as base.parse_config, plus an optional 4th normalization field."""
    replacements: list[tuple[int, Path, int | None, float | None]] = []

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: {exc}") from exc

        if len(parts) not in (3, 4):
            raise SystemExit(
                f"{path}:{lineno}: expected 3 or 4 fields: "
                "HARMONY_SONG WAV_PATH auto|TEMPO [auto|off|TARGET_RMS]"
            )

        try:
            song_id = base.parse_int(parts[0])
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: invalid song id {parts[0]!r}: {exc}") from exc
        if not (0 < song_id <= 0xFFFF):
            raise SystemExit(f"{path}:{lineno}: song id must be between 1 and 0xFFFF")

        tempo_field = parts[2]
        tempo: int | None
        if tempo_field.lower() == "auto":
            tempo = None
        else:
            try:
                tempo = base.parse_int(tempo_field)
            except ValueError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid tempo {tempo_field!r}: {exc}") from exc
            if not (1 <= tempo <= 255):
                raise SystemExit(f"{path}:{lineno}: tempo must be between 1 and 255")

        norm_field = parts[3] if len(parts) == 4 else "auto"
        target_rms: float | None
        if norm_field.lower() == "auto":
            target_rms = None  # -> DEFAULT_TARGET_RMS at use site
        elif norm_field.lower() == "off":
            target_rms = 0.0  # sentinel: no gain at all
        else:
            try:
                target_rms = float(norm_field)
            except ValueError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid normalization {norm_field!r}: {exc}") from exc
            if not (0.0 < target_rms <= 1.0):
                raise SystemExit(f"{path}:{lineno}: normalization target RMS must be between 0 and 1")

        replacements.append((song_id, Path(parts[1]), tempo, target_rms))

    if not replacements:
        raise SystemExit(f"{path}: no replacements found")

    seen: dict[int, int] = {}
    for idx, (song_id, _, _, _) in enumerate(replacements, 1):
        if song_id in seen:
            raise SystemExit(
                f"{path}: Harmony song {song_id} is replaced more than once "
                f"(entries {seen[song_id]} and {idx})"
            )
        seen[song_id] = idx

    return replacements


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inject .wav songs into Harmony of Dissonance and apply the pause/resume fix"
    )
    parser.add_argument("rom", type=Path, help="Original Harmony of Dissonance ROM (.gba)")
    parser.add_argument("config", type=Path, help="Text file: HARMONY_SONG WAV_PATH auto|TEMPO [NORM] per line")
    parser.add_argument("output", type=Path, help="Output .gba file")
    parser.add_argument(
        "--skip-pause-patch",
        action="store_true",
        help="Only run the song injection, do not apply the pause/resume engine patch",
    )
    args = parser.parse_args()

    rom_path = args.rom
    if not rom_path.is_file():
        raise SystemExit(f"ROM not found: {rom_path}")
    output_path = args.output

    replacements = parse_config(args.config)
    harmony = base.validate_harmony(rom_path)

    print("Harmony of Dissonance - WAV Song Injector (per-track loudness control)")
    print("=" * 70)
    print(f"Harmony: {rom_path}")
    print(f"Config:  {args.config}")
    print(f"Output:  {output_path}")
    print()

    out = bytearray(harmony)
    blob_cache: dict[tuple, int] = {}

    for song_id, wav_path, tempo_override, target_rms_override in replacements:
        if not wav_path.exists():
            raise SystemExit(f"Missing .wav file: {wav_path}")

        entry_off = base.HOD_SONG_TABLE + song_id * 8
        if entry_off + 8 > len(harmony):
            raise SystemExit(f"Song {song_id} is outside Harmony's song table")

        target_rms = DEFAULT_TARGET_RMS if target_rms_override is None else target_rms_override

        cache_key = (
            wav_path.resolve(),
            tempo_override,
            target_rms,
            base.DEFAULT_SAMPLE_RATE,
            base.DEFAULT_BASE_NOTE,
            base.DEFAULT_VOLUME,
        )
        cached_header_addr = blob_cache.get(cache_key)
        if cached_header_addr is not None:
            base.p32(out, entry_off, cached_header_addr)
            print(f"OK  Harmony {song_id:04d} <- {wav_path} (reused sample, no extra ROM space)")
            continue

        mono, src_rate = base.read_wav_mono_float(wav_path)
        resampled = base.resample_linear(mono, src_rate, base.DEFAULT_SAMPLE_RATE)
        if target_rms > 0.0:
            resampled, gain, limited_pct = base.normalize_loudness(resampled, target_rms=target_rms)
        else:
            gain, limited_pct = 1.0, 0.0
        pcm = base.to_pcm8(resampled)

        if not pcm:
            raise SystemExit(f"{wav_path} contains no audio data")

        duration_s = len(pcm) / base.DEFAULT_SAMPLE_RATE
        tempo, num_holds, hold_s = base.pick_tempo_and_holds(duration_s, tempo_override)

        blob, off = base.build_song_blob(
            pcm=pcm,
            sample_rate=base.DEFAULT_SAMPLE_RATE,
            base_note=base.DEFAULT_BASE_NOTE,
            volume=base.DEFAULT_VOLUME,
            tempo=tempo,
            num_holds=num_holds,
        )

        append_delta = len(out)
        out += blob
        rom_base = base.GBA_ROM_BASE + append_delta

        base.p32(out, append_delta + off["seg_a_goto_ptr_off"], rom_base + off["seg_b_off"])
        base.p32(out, append_delta + off["seg_b_goto_ptr_off"], rom_base + off["seg_a_off"])
        base.p32(out, append_delta + off["voicegroup_ptr_off"], rom_base + off["tone_off"])
        base.p32(out, append_delta + off["track_ptr_off"], rom_base + off["song_data_off"])
        base.p32(out, append_delta + off["tone_wav_ptr_off_0"], rom_base + off["wave_off"])
        base.p32(out, append_delta + off["tone_wav_ptr_off_1"], rom_base + off["wave_off"])

        header_addr = rom_base + off["header_off"]
        base.p32(out, entry_off, header_addr)
        blob_cache[cache_key] = header_addr

        norm_desc = "off" if target_rms == 0.0 else f"target_rms={target_rms:.2f}"
        print(f"OK  Harmony {song_id:04d} <- {wav_path}  ({norm_desc})")
        print(
            f"    {src_rate} Hz -> {base.DEFAULT_SAMPLE_RATE} Hz  duration={duration_s:.3f}s  "
            f"tempo=0x{tempo:02X}  holds={num_holds} ({hold_s:.3f}s, gap {hold_s - duration_s:+.3f}s)"
        )
        if gain != 1.0:
            print(f"    normalized: RMS gain x{gain:.2f}", end="")
            print(f", {limited_pct:.1f}% samples soft-limited" if limited_pct > 0 else "")

    if len(out) > base.MAX_GBA_ROM_SIZE:
        raise SystemExit(f"Output ROM would exceed {base.MAX_GBA_ROM_SIZE} bytes ({len(out)} bytes)")

    output_path.write_bytes(out)
    print()
    print(f"Created: {output_path}")

    if args.skip_pause_patch:
        print()
        print("--skip-pause-patch given, done.")
        return

    print()
    print("Applying pause/resume engine patch...")
    rom = bytearray(output_path.read_bytes())
    apply_pause_patch(rom)
    output_path.write_bytes(rom)
    print(f"OK  patched pause routine (cave @0x{CAVE_ADDR:08X}, call site @0x{PATCH_ADDR:08X})")


if __name__ == "__main__":
    main()
