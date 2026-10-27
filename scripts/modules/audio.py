"""WAV decoding, mono conversion, resampling and signed PCM encoding."""
from __future__ import annotations

import struct
import wave
from pathlib import Path

DEFAULT_SAMPLE_RATE = 11025


def read_wav_mono_float(path: Path) -> tuple[list[float], int]:
    """Read a PCM .wav as a list of mono samples in the range [-1, 1]."""
    try:
        with wave.open(str(path), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
    except wave.Error as exc:
        raise SystemExit(
            f"Could not read {path} as PCM .wav: {exc}. "
            "Export it as uncompressed 8-bit or 16-bit PCM WAV."
        ) from exc

    total = nframes * nchannels

    if sampwidth == 1:
        ints = struct.unpack(f"<{total}B", raw)
        floats = [(v - 128) / 128.0 for v in ints]
    elif sampwidth == 2:
        ints = struct.unpack(f"<{total}h", raw)
        floats = [v / 32768.0 for v in ints]
    else:
        raise SystemExit(
            f"Unsupported WAV bit depth: {sampwidth * 8}-bit. "
            "Export the .wav as 8-bit or 16-bit PCM."
        )

    if nchannels == 1:
        mono = floats
    else:
        mono = [
            sum(floats[i * nchannels:(i + 1) * nchannels]) / nchannels
            for i in range(nframes)
        ]

    return mono, framerate


def resample_linear(samples: list[float], src_rate: int, dst_rate: int) -> list[float]:
    if src_rate == dst_rate or not samples:
        return list(samples)

    src_len = len(samples)
    duration = (src_len - 1) / src_rate
    dst_len = max(1, round(duration * dst_rate) + 1)
    ratio = (src_len - 1) / (dst_len - 1) if dst_len > 1 else 0.0

    out = [0.0] * dst_len
    for i in range(dst_len):
        pos = i * ratio
        idx = int(pos)
        frac = pos - idx
        if idx + 1 < src_len:
            out[i] = samples[idx] * (1 - frac) + samples[idx + 1] * frac
        else:
            out[i] = samples[idx]
    return out


def to_pcm8(samples: list[float]) -> bytes:
    """Quantize to signed 8-bit PCM."""
    out = bytearray(len(samples))
    for i, s in enumerate(samples):
        v = int(round(s * 127))
        if v > 127:
            v = 127
        elif v < -128:
            v = -128
        out[i] = v & 0xFF
    return bytes(out)
