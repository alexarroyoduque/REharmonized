"""Song injection, pointer relocation, deduplication and CLI."""
from __future__ import annotations

import argparse
from pathlib import Path
from . import base
from .config import DEFAULT_TARGET_RMS, parse_config
from .loops import apply_loop_crossfade
from .songs import build_song_blob
from .pause_patch import *

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

    inject_songs(args.rom, args.config, args.output,
                 skip_pause_patch=args.skip_pause_patch, suggest_gaps=suggest_gaps)


def inject_songs(
    rom_path: Path, config_path: Path, output_path: Path, *,
    skip_pause_patch: bool = False, suggest_gaps: list[float] | None = None,
) -> None:
    """Build and relocate songs, then optionally apply the pause engine patch."""
    if suggest_gaps is None:
        suggest_gaps = list(base.DEFAULT_SUGGEST_GAPS)
    if not rom_path.is_file():
        raise SystemExit(f"ROM not found: {rom_path}")
    if output_path.resolve() == rom_path.resolve():
        raise SystemExit("Output must differ from the original ROM; refusing to overwrite it")

    replacements = parse_config(config_path)
    harmony = base.validate_harmony(rom_path)

    print("Harmony of Dissonance - WAV Song Injector (per-track loudness control)")
    print("=" * 70)
    print(f"Harmony: {rom_path}")
    print(f"Config:  {config_path}")
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

    if skip_pause_patch:
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
