"""Intro-preserving crossfade and native PCM loop offsets."""
from __future__ import annotations

import math

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
