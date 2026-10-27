"""Legacy and current positional TXT configuration parsing."""
from __future__ import annotations

import math
import shlex
from pathlib import Path
from .rom import parse_int

DEFAULT_TARGET_RMS = 0.4


def parse_legacy_config(path: Path) -> list[tuple[int, Path, int | None]]:
    replacements: list[tuple[int, Path, int | None]] = []

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            raise SystemExit(f"{path}:{lineno}: {exc}") from exc

        if len(parts) != 3:
            raise SystemExit(
                f"{path}:{lineno}: expected 3 fields: "
                "HARMONY_SONG WAV_PATH auto|TEMPO"
            )

        try:
            song_id = parse_int(parts[0])
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
                tempo = parse_int(tempo_field)
            except ValueError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid tempo {tempo_field!r}: {exc}") from exc
            if not (1 <= tempo <= 255):
                raise SystemExit(f"{path}:{lineno}: tempo must be between 1 and 255")

        replacements.append((song_id, Path(parts[1]), tempo))

    if not replacements:
        raise SystemExit(f"{path}: no replacements found")

    # Prevent accidental duplicate Harmony targets.
    seen: dict[int, int] = {}
    for idx, (song_id, _, _) in enumerate(replacements, 1):
        if song_id in seen:
            raise SystemExit(
                f"{path}: Harmony song {song_id} is replaced more than once "
                f"(entries {seen[song_id]} and {idx})"
            )
        seen[song_id] = idx

    return replacements


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
            song_id = parse_int(parts[0])
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
                tempo = parse_int(tempo_field)
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
