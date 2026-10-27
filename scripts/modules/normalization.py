"""Loudness normalization and soft limiting."""
from __future__ import annotations

import math

def soft_limit(x: float, threshold: float = 0.85) -> float:
    """Leave |x| <= threshold untouched; smoothly saturate anything above it
    towards +-1.0 (tanh knee) instead of flat-top clipping."""
    a = abs(x)
    if a <= threshold:
        return x
    sign = 1.0 if x > 0 else -1.0
    span = 1.0 - threshold
    return sign * (threshold + span * math.tanh((a - threshold) / span))


def normalize_loudness(
    samples: list[float], target_rms: float = 0.45, max_gain: float = 8.0
) -> tuple[list[float], float, float]:
    """Scale so the average (RMS) level reaches target_rms, not just the peak.

    Source .wav files are used at their own recorded amplitude with no other
    gain applied anywhere in the pipeline. Peak-only normalization isn't
    enough for tracks with a high crest factor (a few loud transients, quiet
    body): their peak already sits near full scale so no gain gets applied,
    yet the track still sounds quiet overall. Targeting RMS instead raises
    the perceived loudness; samples pushed past the soft_limit threshold are
    smoothly saturated (not hard-clipped), trading a little coloration on
    rare peaks for a much louder average level.
    """
    if not samples:
        return samples, 1.0, 0.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    if rms <= 0.0:
        return samples, 1.0, 0.0
    gain = min(target_rms / rms, max_gain)
    if gain == 1.0:
        return samples, 1.0, 0.0
    boosted = [s * gain for s in samples]
    limited_pct = 100.0 * sum(1 for s in boosted if abs(s) > 0.85) / len(boosted)
    limited = [soft_limit(s) for s in boosted]
    return limited, gain, limited_pct
