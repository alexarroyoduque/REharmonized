#!/usr/bin/env python3
"""
Harmony of Dissonance - tempo suggestion only (no injection, no ROM writes)

Same inputs as wav_to_harmony.py (a Harmony of Dissonance ROM + a config file
in the config_wav_reharmonized.txt format: HARMONY_SONG WAV_PATH auto|TEMPO
[auto|off|TARGET_RMS] per line), but only computes and prints the tempo/holds
suggestions for each song's .wav duration - it never builds song data, never
touches the ROM bytes, and never writes an output .gba. Meant as the engine
for a future web tool that needs the same suggestions without running the
full injection pipeline.

Reuses wav_to_harmony_pause-not-resume-music.py's helper functions via
dynamic import (never modified, same approach as wav_to_harmony_pause_fix.py).

Usage:
    python3 suggest_tempos.py harmony.gba config.txt [--suggest-gaps -0.3,-0.6]

Output: a single JSON object on stdout, e.g.
    {
      "songs": [
        {
          "song_id": 1,
          "wav_path": "librarian.wav",
          "source_sample_rate": 44100,
          "resampled_rate": 11025,
          "duration_s": 3.217,
          "best": {"tempo": 91, "holds": 10, "hold_s": 3.199, "gap_s": -0.018},
          "suggestions": [
            {"target_gap_s": -0.3, "tempo": 77, "holds": 9, "actual_s": 2.922, "gap_s": -0.295},
            ...
          ]
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
from pathlib import Path

_BASE_PATH = Path(__file__).parent / "wav_to_harmony_pause-not-resume-music.py"
_spec = importlib.util.spec_from_file_location("wav_to_harmony_base", _BASE_PATH)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


def parse_config(path: Path) -> list[tuple[int, Path]]:
    """Same HARMONY_SONG WAV_PATH ... line format as the injector scripts;
    only the first two fields matter here (tempo/normalization fields, if
    present, are accepted but ignored - suggestions are always computed from
    scratch for every song)."""
    replacements: list[tuple[int, Path]] = []

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
            song_id = int(parts[0], 10)
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: invalid song id {parts[0]!r}: {exc}") from exc
        if not (0 < song_id <= 0xFFFF):
            raise SystemExit(f"{path}:{lineno}: song id must be between 1 and 0xFFFF")

        replacements.append((song_id, Path(parts[1])))

    if not replacements:
        raise SystemExit(f"{path}: no replacements found")

    return replacements


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Suggest Harmony of Dissonance tempo/holds for each song in a config, without injecting anything"
    )
    parser.add_argument("rom", type=Path, help="Original Harmony of Dissonance ROM (.gba), used only for validation")
    parser.add_argument("config", type=Path, help="Text file: HARMONY_SONG WAV_PATH auto|TEMPO [NORM] per line")
    parser.add_argument(
        "--suggest-gaps",
        default=None,
        help="Comma-separated target loop gaps (seconds) to suggest a tempo for, one each, "
        f"e.g. -0.3,-0.6,-0.9 (default: {','.join(str(g) for g in base.DEFAULT_SUGGEST_GAPS)})",
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

    harmony = base.validate_harmony(rom_path)
    replacements = parse_config(args.config)

    songs_out = []
    for song_id, wav_path in replacements:
        if not wav_path.exists():
            raise SystemExit(f"Missing .wav file: {wav_path}")

        entry_off = base.HOD_SONG_TABLE + song_id * 8
        if entry_off + 8 > len(harmony):
            raise SystemExit(f"Song {song_id} is outside Harmony's song table")

        mono, src_rate = base.read_wav_mono_float(wav_path)
        resampled = base.resample_linear(mono, src_rate, base.DEFAULT_SAMPLE_RATE)
        if not resampled:
            raise SystemExit(f"{wav_path} contains no audio data")

        duration_s = len(resampled) / base.DEFAULT_SAMPLE_RATE
        tempo, holds, hold_s = base.pick_tempo_and_holds(duration_s, None)

        suggestions = [
            {
                "target_gap_s": sug_target,
                "tempo": sug_tempo,
                "holds": sug_holds,
                "actual_s": round(sug_actual, 6),
                "gap_s": round(sug_gap, 6),
            }
            for sug_target, sug_tempo, sug_holds, sug_actual, sug_gap in base.suggest_tempos(
                duration_s, suggest_gaps
            )
        ]

        songs_out.append(
            {
                "song_id": song_id,
                "wav_path": str(wav_path),
                "source_sample_rate": src_rate,
                "resampled_rate": base.DEFAULT_SAMPLE_RATE,
                "duration_s": round(duration_s, 6),
                "best": {
                    "tempo": tempo,
                    "holds": holds,
                    "hold_s": round(hold_s, 6),
                    "gap_s": round(hold_s - duration_s, 6),
                },
                "suggestions": suggestions,
            }
        )

    print(json.dumps({"songs": songs_out}, indent=2))


if __name__ == "__main__":
    main()
