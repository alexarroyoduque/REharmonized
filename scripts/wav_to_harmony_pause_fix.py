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

Config format (fields 4-6 optional; old configurations still work):
    HARMONY_SONG_ID WAV_PATH auto|TEMPO [auto|off|TARGET_RMS] [LOOP_START_SECONDS] [CROSSFADE_SECONDS]

    LOOP_START_SECONDS defaults to 0 (the existing whole-song loop).
    A positive value plays the intro once, then loops from that point to
    the end using MP2K's native PCM loop. No audio is duplicated and tempo
    does not control this loop boundary. Use 'auto' in field 4 to keep the
    default normalization while specifying field 5.

    CROSSFADE_SECONDS defaults to 0 (disabled), and requires a positive
    LOOP_START_SECONDS. Mix the loop's head into its tail, then jump past
    the mixed head. The loop period is shortened by the crossfade duration;
    the initial intro is unchanged. The source WAV is never modified.

    (missing) / auto  -> RMS-normalize to 0.40 (default)
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
import math
import shlex
import struct
from pathlib import Path

GBA_ROM_BASE = 0x08000000

PATCH_ADDR = 0x080BC458
CAVE_ADDR = 0x080C6D34

# Original bytes expected at PATCH_ADDR (ldr r0,[r5,#0]; bl m4aMPlayStop),
# checked before patching so we never blindly overwrite unexpected content.
ORIGINAL_PATCH_BYTES = bytes.fromhex("286800f043fb")

PATCH_BYTES = bytes.fromhex("0af06cfc0000")
CAVE_BYTES = bytes.fromhex("042c04d000b52868f5f7d2fe00bd7047")

# Overrides base.normalize_loudness's own default target_rms (0.45).
DEFAULT_TARGET_RMS = 0.4

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


def build_song_blob(
    pcm: bytes,
    sample_rate: int,
    base_note: int,
    volume: int,
    tempo: int,
    num_holds: int,
    loop_start_s: float = 0.0,
) -> tuple[bytes, dict[str, int]]:
    """Keep legacy blobs unchanged; positive offsets use a native PCM loop."""
    if not math.isfinite(loop_start_s) or not (0 <= loop_start_s < len(pcm) / sample_rate):
        raise ValueError("loop start must be finite, non-negative and before the end of the audio")
    loop_start_sample = round(loop_start_s * sample_rate)
    if loop_start_s > 0 and not (0 < loop_start_sample < len(pcm)):
        raise ValueError("loop start rounds outside the valid sample range")

    blob, offsets = base.build_song_blob(
        pcm, sample_rate, base_note, volume, tempo,
        1 if loop_start_sample else num_holds,
    )
    if not loop_start_sample:
        return blob, offsets

    blob = bytearray(blob)
    # WaveData: type/status (loop flag in byte 3), rate, loop start, length.
    struct.pack_into("<I", blob, offsets["wave_off"], 0x40000000)
    struct.pack_into("<I", blob, offsets["wave_off"] + 8, loop_start_sample)
    # After the initial keyshift/voice/volume/TIE, wait forever. Jumping back
    # to the TIE or alternating voices would restart the intro. Segment B
    # stays unreachable; retain the base layout and relocation information.
    offsets["loop_wait_off"] = offsets["seg_a_off"] + 9
    return bytes(blob), offsets


def apply_loop_crossfade(
    samples: list[float], sample_rate: int, loop_start_s: float, crossfade_s: float,
) -> tuple[list[float], float]:
    """Blend tail/head before PCM quantization; return the native jump offset.

    Linear complementary weights avoid boosting correlated signals. The last
    mixed sample is the last head sample; playback resumes at the next one.
    Keep the prefix intact, including the intro and the first loop entry.
    """
    if not math.isfinite(crossfade_s) or crossfade_s < 0:
        raise ValueError("crossfade must be finite and non-negative (seconds)")
    if crossfade_s == 0:
        return samples, loop_start_s
    if not math.isfinite(loop_start_s) or loop_start_s <= 0:
        raise ValueError("crossfade requires a positive loop start")
    start = round(loop_start_s * sample_rate)
    count = round(crossfade_s * sample_rate)
    if not 0 < start < len(samples):
        raise ValueError("loop start must be before the end of the audio")
    if count < 2:
        raise ValueError("crossfade must span at least two resampled samples")
    if 2 * count > len(samples) - start:
        raise ValueError("crossfade must not exceed half the loop duration")

    mixed = samples.copy()
    tail = len(samples) - count
    for i in range(count):
        weight = i / (count - 1)
        mixed[tail + i] = (1 - weight) * samples[tail + i] + weight * samples[start + i]
    return mixed, (start + count) / sample_rate


def parse_config(path: Path) -> list[tuple[int, Path, int | None, float | None, float, float]]:
    """Parse optional normalization, loop-start and crossfade fields."""
    replacements: list[tuple[int, Path, int | None, float | None, float, float]] = []

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: {exc}") from exc

        if len(parts) not in (3, 4, 5, 6):
            raise SystemExit(
            f"{path}:{lineno}: expected 3 to 6 fields: "
            "HARMONY_SONG WAV_PATH auto|TEMPO [auto|off|TARGET_RMS] [LOOP_START_SECONDS] [CROSSFADE_SECONDS]"
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

        norm_field = parts[3] if len(parts) >= 4 else "auto"
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

        try:
            loop_start_s = float(parts[4]) if len(parts) >= 5 else 0.0
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: invalid loop start {parts[4]!r}: {exc}") from exc
        if not math.isfinite(loop_start_s) or loop_start_s < 0:
            raise SystemExit(f"{path}:{lineno}: loop start must be finite and non-negative (seconds)")

        try:
            crossfade_s = float(parts[5]) if len(parts) == 6 else 0.0
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: invalid crossfade {parts[5]!r}: {exc}") from exc
        if not math.isfinite(crossfade_s) or crossfade_s < 0:
            raise SystemExit(f"{path}:{lineno}: crossfade must be finite and non-negative (seconds)")
        if crossfade_s > 0 and loop_start_s == 0:
            raise SystemExit(f"{path}:{lineno}: crossfade requires a positive loop start")

        replacements.append((song_id, Path(parts[1]), tempo, target_rms, loop_start_s, crossfade_s))

    if not replacements:
        raise SystemExit(f"{path}: no replacements found")

    seen: dict[int, int] = {}
    for idx, (song_id, _, _, _, _, _) in enumerate(replacements, 1):
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
    parser.add_argument("config", type=Path, help="Text file: HARMONY_SONG WAV_PATH auto|TEMPO [NORM] [LOOP_START_SECONDS] [CROSSFADE_SECONDS] per line")
    parser.add_argument("output", type=Path, help="Output .gba file")
    parser.add_argument(
        "--skip-pause-patch",
        action="store_true",
        help="Only run the song injection, do not apply the pause/resume engine patch",
    )
    parser.add_argument(
        "--suggest-gaps",
        default=None,
        help="Comma-separated target loop gaps (seconds) to print a tempo suggestion "
        "for each song, one each, e.g. -0.3,-0.6,-0.9 (default: "
        f"{','.join(str(g) for g in base.DEFAULT_SUGGEST_GAPS)}; pass '' to disable)",
    )
    args = parser.parse_args()

    if args.suggest_gaps is None:
        suggest_gaps = list(base.DEFAULT_SUGGEST_GAPS)
    elif args.suggest_gaps.strip() == "":
        suggest_gaps = []
    else:
        try:
            suggest_gaps = [float(g) for g in args.suggest_gaps.split(",")]
        except ValueError as exc:
            raise SystemExit(f"--suggest-gaps: invalid value {args.suggest_gaps!r}: {exc}") from exc

    rom_path = args.rom
    if not rom_path.is_file():
        raise SystemExit(f"ROM not found: {rom_path}")
    output_path = args.output
    if output_path.resolve() == rom_path.resolve():
        raise SystemExit("Output must differ from the original ROM; refusing to overwrite it")

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

    for song_id, wav_path, tempo_override, target_rms_override, loop_start_s, crossfade_s in replacements:
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
            loop_start_s,
            crossfade_s,
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
        try:
            resampled, native_loop_start_s = apply_loop_crossfade(
                resampled, base.DEFAULT_SAMPLE_RATE, loop_start_s, crossfade_s,
            )
        except ValueError as exc:
            raise SystemExit(f"Song {song_id} ({wav_path}): {exc}") from exc
        pcm = base.to_pcm8(resampled)

        if not pcm:
            raise SystemExit(f"{wav_path} contains no audio data")

        duration_s = len(pcm) / base.DEFAULT_SAMPLE_RATE
        tempo, num_holds, hold_s = base.pick_tempo_and_holds(duration_s, tempo_override)

        try:
            blob, off = build_song_blob(
                pcm=pcm,
                sample_rate=base.DEFAULT_SAMPLE_RATE,
                base_note=base.DEFAULT_BASE_NOTE,
                volume=base.DEFAULT_VOLUME,
                tempo=tempo,
                num_holds=num_holds,
                loop_start_s=native_loop_start_s,
            )
        except ValueError as exc:
            raise SystemExit(f"Song {song_id} ({wav_path}): {exc} (duration={duration_s:.6f}s)") from exc

        append_delta = len(out)
        out += blob
        rom_base = base.GBA_ROM_BASE + append_delta

        base.p32(out, append_delta + off["seg_a_goto_ptr_off"], rom_base + off.get("loop_wait_off", off["seg_b_off"]))
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
        print(f"    {src_rate} Hz -> {base.DEFAULT_SAMPLE_RATE} Hz  duration={duration_s:.3f}s", end="  ")
        if loop_start_s > 0:
            actual_start = round(native_loop_start_s * base.DEFAULT_SAMPLE_RATE) / base.DEFAULT_SAMPLE_RATE
            print(f"native loop={actual_start:.6f}s -> {duration_s:.6f}s (intro once; tempo-independent)")
            if crossfade_s > 0:
                actual_fade = round(crossfade_s * base.DEFAULT_SAMPLE_RATE) / base.DEFAULT_SAMPLE_RATE
                print(f"    loop start={loop_start_s:.6f}s, crossfade={actual_fade:.6f}s "
                      f"(loop period shortened by {actual_fade:.6f}s; intro unchanged)")
        else:
            print(f"tempo=0x{tempo:02X}  holds={num_holds} ({hold_s:.3f}s, gap {hold_s - duration_s:+.3f}s)")
        if gain != 1.0:
            print(f"    normalized: RMS gain x{gain:.2f}", end="")
            print(f", {limited_pct:.1f}% samples soft-limited" if limited_pct > 0 else "")
        if suggest_gaps and loop_start_s == 0:
            print("    Suggestions (one closest match per target gap):")
            for sug_target, sug_tempo, sug_holds, sug_actual, sug_gap in base.suggest_tempos(duration_s, suggest_gaps):
                print(
                    f"      target={sug_target:+.2f}s  tempo=0x{sug_tempo:02X} ({sug_tempo:3d})  "
                    f"holds={sug_holds}  gap={sug_gap:+.3f}s"
                )

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
