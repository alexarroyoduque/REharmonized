#!/usr/bin/env python3
"""
Harmony of Dissonance - WAV Song Injector

Turns a .wav file into a custom "streamed" MP2K song and injects it into a
chosen Harmony of Dissonance song slot, producing a new ROM. This follows the
same technique documented in:

    ariastreamed-ver2.0.1/AoS Streamed Audio.txt

...but automates it: instead of hand-editing a ROM in HxD/FEBuilderGBA, this
script builds the song data, instrument (ToneData), and sample header (WaveData)
directly from your .wav and appends them after Harmony's own 8 MiB.

The song is a single instrument holding one long tied note (CF) for the whole
duration of the sample, looping by jumping back to the BD/voice command, which
restarts sample playback from the beginning - exactly the "streamed audio"
trick from the doc, just generated programmatically.

Usage:
    python3 wav_to_harmony.py harmony.gba config.txt output.gba

Config syntax (one replacement per line):
    # HARMONY_SONG   WAV_PATH            TEMPO
    1                librarian.wav       auto
    15               "castle theme.wav"  0x4B

HARMONY_SONG may be decimal or hexadecimal (0x..). WAV_PATH is resolved
relative to the current directory; quote it if it contains spaces. TEMPO is
either the literal "auto" (auto-pick the closest loop-timing match) or a BB
tempo byte (1-255, decimal or hex) forced for that song only - use a forced
value if that specific song's loop point clicks/pops or has a silence gap.

Requirements for the .wav: PCM, 8-bit or 16-bit, any sample rate/channel count
(it will be downmixed to mono and resampled).

Caveats:
- The loop-timing math (tempo byte -> real seconds) follows MP2K's actual
  tick rate of 24 ticks/beat and BPM = 2 * tempo byte (verified against
  agbplay's own player timing, see SequenceReader.cpp). This is a best-effort
  estimate, not a guaranteed-exact figure: test the result in agbplay/mGBA and
  force a TEMPO to fine-tune the loop point if needed.
- Only Harmony of Dissonance (Europe, game code ACHP) is supported, matching
  inject_music.py.
- Input ROM is never modified.
"""

from __future__ import annotations

import argparse
import math
import shlex
import struct
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# ROM / GAME CONSTANTS (same values as inject_music.py)
# ---------------------------------------------------------------------------

GBA_ROM_BASE = 0x08000000
SOURCE_ROM_SIZE = 0x00800000  # 8 MiB
MAX_GBA_ROM_SIZE = 0x02000000  # 32 MiB

HOD_GAME_CODE = b"ACHP"
HOD_SONG_TABLE = 0x001A6B5C

DEFAULT_SAMPLE_RATE = 11025
DEFAULT_BASE_NOTE = 0x3C
DEFAULT_VOLUME = 0x7F  # BE command's valid range is 0-127; >127 overflows the
                       # engine's internal vol<<1 scaling and clips the mixer

# MP2K timing assumptions (see module docstring caveat above).
PPQN = 24            # ticks per beat
MAX_WAIT_TICKS = 96  # ticks represented by the 0xB0 hold/wait opcode

# Default target gaps (seconds) for the printed tempo suggestions: empirically,
# a small negative gap (hold ends slightly before the sample would loop
# again) tends to click/pop less than chasing an exact 0.000s match.
DEFAULT_SUGGEST_GAPS = (-0.3, -0.6, -0.9, -1.2, -1.5, -1.8, -2.0)


def u32(buf: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def p32(buf: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", buf, off, value)


def game_code(rom: bytes) -> bytes:
    return rom[0xAC:0xB0]


def parse_int(value: str) -> int:
    return int(value, 0)


def validate_harmony(path: Path) -> bytes:
    if not path.exists():
        raise SystemExit(f"Missing Harmony ROM: {path}")

    rom = path.read_bytes()

    if len(rom) != SOURCE_ROM_SIZE:
        raise SystemExit(
            f"Harmony ROM must be exactly 8 MiB; got {len(rom)} bytes (0x{len(rom):X})"
        )

    code = game_code(rom)
    if code != HOD_GAME_CODE:
        raise SystemExit(
            f"Unexpected Harmony game code: {code!r}; expected {HOD_GAME_CODE!r}"
        )

    return rom


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


def pick_tempo_and_holds(
    duration_s: float, tempo_override: int | None
) -> tuple[int, int, float]:
    """
    Choose a BB tempo byte and a count of 0xB0 hold bytes so the song holds
    its single tied note for approximately `duration_s` seconds before
    looping.

    seconds_per_tick   = 60 / (2 * tempo * PPQN) == 1.25 / tempo
    seconds_per_hold   = MAX_WAIT_TICKS * seconds_per_tick == 120 / tempo
    (BPM = 2 * tempo, 24 ticks/beat; see module docstring caveat. A previous
    version of this script assumed 48 ticks/beat, doubling every hold's real
    duration - the sample would finish, then wait through a second full
    silent copy of its own length before the loop pointer ever fired.)
    """
    if tempo_override is not None:
        tempo = tempo_override
        holds = max(1, round(duration_s * tempo / 120.0))
        return tempo, holds, holds * 120.0 / tempo

    best: tuple[float, int, int, float] | None = None
    for tempo in range(1, 256):
        holds = max(1, round(duration_s * tempo / 120.0))
        actual = holds * 120.0 / tempo
        error = abs(actual - duration_s)
        if best is None or error < best[0]:
            best = (error, tempo, holds, actual)

    assert best is not None
    _, tempo, holds, actual = best
    return tempo, holds, actual


def suggest_tempos(
    duration_s: float, target_gaps: list[float]
) -> list[tuple[float, int, int, float, float]]:
    """
    For each requested target gap (seconds), find the (tempo, holds)
    combination whose resulting gap (actual - duration_s) is closest to it.
    Returns one suggestion per target gap, in the same order.
    """
    results: list[tuple[float, int, int, float, float]] = []
    for target in target_gaps:
        best: tuple[float, int, int, float, float] | None = None
        for tempo in range(1, 256):
            holds = max(1, round(duration_s * tempo / 120.0))
            actual = holds * 120.0 / tempo
            gap = actual - duration_s
            error = abs(gap - target)
            if best is None or error < best[0]:
                best = (error, tempo, holds, actual, gap)
        assert best is not None
        _, tempo, holds, actual, gap = best
        results.append((target, tempo, holds, actual, gap))
    return results


def build_song_blob(
    pcm: bytes,
    sample_rate: int,
    base_note: int,
    volume: int,
    tempo: int,
    num_holds: int,
) -> tuple[bytes, dict[str, int]]:
    """
    Build the song data + instrument + sample blob.

    Alternating the voice slot alone (0/1) did not make real hardware
    re-trigger the sample on loop, so the "same note continues" check the
    engine applies must key off the raw note value itself, not the voice
    slot. Each pass now also uses a different raw key (base_note vs
    base_note+1) paired with a compensating track keyshift (0 vs -1) so the
    audible pitch stays identical but the key byte sent to CF genuinely
    changes every loop, forcing a fresh note-on instead of a tied
    continuation.
    """
    if base_note < 127:
        alt_key, alt_shift = base_note + 1, 0xFF  # +1 semitone note, -1 semitone shift
    else:
        alt_key, alt_shift = base_note - 1, 0x01  # -1 semitone note, +1 semitone shift

    blob = bytearray()

    song_data_off = len(blob)
    blob += bytes([0xBB, tempo & 0xFF])               # tempo

    seg_a_off = len(blob)
    blob += bytes([0xBC, 0x00])                       # keyshift +0
    blob += bytes([0xBD, 0x00])                       # select voice 0
    blob += bytes([0xBE, volume & 0xFF])              # volume
    blob += bytes([0xCF, base_note & 0xFF, 0x7F])     # tie: hold the sample's note
    blob += bytes([0xB0]) * num_holds                 # extend hold across the sample
    blob += bytes([0xB2])                             # jump to the other voice slot
    seg_a_goto_ptr_off = len(blob)
    blob += b"\x00\x00\x00\x00"                       # placeholder: -> seg_b_off

    seg_b_off = len(blob)
    blob += bytes([0xBC, alt_shift])                  # compensating keyshift
    blob += bytes([0xBD, 0x01])                       # select voice 1 (same sample)
    blob += bytes([0xBE, volume & 0xFF])              # volume
    blob += bytes([0xCF, alt_key & 0xFF, 0x7F])       # tie: different raw key, same audible pitch
    blob += bytes([0xB0]) * num_holds                 # extend hold across the sample
    blob += bytes([0xB2])                             # jump back to voice 0
    seg_b_goto_ptr_off = len(blob)
    blob += b"\x00\x00\x00\x00"                       # placeholder: -> seg_a_off

    while len(blob) % 4 != 0:                          # header must be 4-byte aligned
        blob.append(0xB0)                              # unreachable filler

    header_off = len(blob)
    # track_count=1, block=0, priority=50 (vanilla's common BGM/SFX value;
    # original value of 0 always lost hardware-channel contention against SFX
    # like the save-room heartbeat, dropping the song's single note-on
    # permanently). Matching 50 exactly (rather than 51) keeps contention
    # against same-priority SFX resolved the same way as in the original game.
    blob += bytes([1, 0, 50, 0])
    voicegroup_ptr_off = len(blob)
    blob += b"\x00\x00\x00\x00"                        # placeholder: -> ToneData
    track_ptr_off = len(blob)
    blob += b"\x00\x00\x00\x00"                        # placeholder: -> song data start

    # Two instrument slots (indices 0 and 1), both pointing at the same sample.
    tone_off = len(blob)
    blob += bytes([0x00, base_note & 0xFF, 0x00, 0x00])  # type, key, pan/unused
    tone_wav_ptr_off_0 = len(blob)
    blob += b"\x00\x00\x00\x00"                        # placeholder: -> WaveData
    blob += bytes([0xFF, 0xFF, 0xFF, 0x00])             # attack, decay, sustain, release

    tone_off_1 = len(blob)
    blob += bytes([0x00, base_note & 0xFF, 0x00, 0x00])  # type, key, pan/unused
    tone_wav_ptr_off_1 = len(blob)
    blob += b"\x00\x00\x00\x00"                        # placeholder: -> WaveData (same sample)
    blob += bytes([0xFF, 0xFF, 0xFF, 0x00])             # attack, decay, sustain, release

    wave_off = len(blob)
    blob += struct.pack("<IIII", 0, round(sample_rate * 1024), 0, len(pcm))

    sample_off = len(blob)
    blob += pcm
    blob += b"\x00" * 4  # trailing pad: some players' range checks are pos+len >= size (off-by-one)

    while len(blob) % 4 != 0:  # keep the next song's blob (appended right after) 4-byte aligned
        blob.append(0x00)

    offsets = {
        "song_data_off": song_data_off,
        "seg_a_off": seg_a_off,
        "seg_a_goto_ptr_off": seg_a_goto_ptr_off,
        "seg_b_off": seg_b_off,
        "seg_b_goto_ptr_off": seg_b_goto_ptr_off,
        "header_off": header_off,
        "voicegroup_ptr_off": voicegroup_ptr_off,
        "track_ptr_off": track_ptr_off,
        "tone_off": tone_off,
        "tone_wav_ptr_off_0": tone_wav_ptr_off_0,
        "tone_off_1": tone_off_1,
        "tone_wav_ptr_off_1": tone_wav_ptr_off_1,
        "wave_off": wave_off,
        "sample_off": sample_off,
    }
    return bytes(blob), offsets


def parse_config(path: Path) -> list[tuple[int, Path, int | None]]:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inject .wav files as new songs into Harmony of Dissonance"
    )
    parser.add_argument("rom", type=Path, help="Path to the Harmony of Dissonance ROM (Europe, ACHP)")
    parser.add_argument("config", type=Path, help="Text file: HARMONY_SONG WAV_PATH per line")
    parser.add_argument("output", type=Path, help="Output .gba file")
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help=f"Playback sample rate in Hz, applied to every song (default: {DEFAULT_SAMPLE_RATE})",
    )
    parser.add_argument(
        "--base-note",
        type=parse_int,
        default=DEFAULT_BASE_NOTE,
        help="Reference note byte, applied to every song (default 0x3C)",
    )
    parser.add_argument(
        "--volume",
        type=parse_int,
        default=DEFAULT_VOLUME,
        help="Song volume byte, BE command, applied to every song (0-127, default 0x7F)",
    )
    parser.add_argument(
        "--tempo",
        type=parse_int,
        default=None,
        help="Force a specific BB tempo byte (1-255) for every song whose config "
        "line uses 'auto', instead of auto-picking the closest loop-timing match "
        "per song",
    )
    parser.add_argument(
        "--suggest-gaps",
        type=str,
        default=None,
        help="Comma-separated target loop gaps (seconds) to print a tempo suggestion "
        f"for, one each, e.g. -0.3,-0.6,-0.9 (default: {','.join(str(g) for g in DEFAULT_SUGGEST_GAPS)}; "
        "pass an empty string to disable)",
    )
    args = parser.parse_args()

    if args.tempo is not None and not (1 <= args.tempo <= 255):
        raise SystemExit("--tempo must be between 1 and 255")
    if not (0 <= args.volume <= 127):
        raise SystemExit("--volume must be between 0 and 127 (BE command's valid range)")
    if args.suggest_gaps is None:
        suggest_gaps = list(DEFAULT_SUGGEST_GAPS)
    elif args.suggest_gaps.strip() == "":
        suggest_gaps = []
    else:
        try:
            suggest_gaps = [float(g) for g in args.suggest_gaps.split(",")]
        except ValueError as exc:
            raise SystemExit(f"--suggest-gaps: invalid value {args.suggest_gaps!r}: {exc}") from exc

    replacements = parse_config(args.config)
    harmony = validate_harmony(args.rom)

    print("Harmony of Dissonance - WAV Song Injector")
    print("=" * 48)
    print(f"Harmony: {args.rom}")
    print(f"Config:  {args.config}")
    print(f"Output:  {args.output}")
    print()

    out = bytearray(harmony)

    # Reuse an already-built blob when a later entry has the same source .wav
    # and encoding/tempo settings, instead of duplicating identical sample
    # data in the ROM (e.g. songs 15/16/17 share one recording).
    blob_cache: dict[tuple, int] = {}

    for song_id, wav_path, tempo_override in replacements:
        if not wav_path.exists():
            raise SystemExit(f"Missing .wav file: {wav_path}")

        entry_off = HOD_SONG_TABLE + song_id * 8
        if entry_off + 8 > len(harmony):
            raise SystemExit(f"Song {song_id} is outside Harmony's song table")

        cache_key = (
            wav_path.resolve(),
            tempo_override,
            args.tempo,
            args.sample_rate,
            args.base_note,
            args.volume,
        )
        cached_header_addr = blob_cache.get(cache_key)
        if cached_header_addr is not None:
            p32(out, entry_off, cached_header_addr)
            print(f"OK  Harmony {song_id:04d} <- {wav_path} (reused sample, no extra ROM space)")
            continue

        mono, src_rate = read_wav_mono_float(wav_path)
        resampled = resample_linear(mono, src_rate, args.sample_rate)
        resampled, gain, limited_pct = normalize_loudness(resampled)
        pcm = to_pcm8(resampled)

        if not pcm:
            raise SystemExit(f"{wav_path} contains no audio data")

        duration_s = len(pcm) / args.sample_rate
        tempo, num_holds, hold_s = pick_tempo_and_holds(
            duration_s, tempo_override if tempo_override is not None else args.tempo
        )

        blob, off = build_song_blob(
            pcm=pcm,
            sample_rate=args.sample_rate,
            base_note=args.base_note,
            volume=args.volume,
            tempo=tempo,
            num_holds=num_holds,
        )

        append_delta = len(out)
        out += blob
        base = GBA_ROM_BASE + append_delta

        p32(out, append_delta + off["seg_a_goto_ptr_off"], base + off["seg_b_off"])
        p32(out, append_delta + off["seg_b_goto_ptr_off"], base + off["seg_a_off"])
        p32(out, append_delta + off["voicegroup_ptr_off"], base + off["tone_off"])
        p32(out, append_delta + off["track_ptr_off"], base + off["song_data_off"])
        p32(out, append_delta + off["tone_wav_ptr_off_0"], base + off["wave_off"])
        p32(out, append_delta + off["tone_wav_ptr_off_1"], base + off["wave_off"])

        # Point Harmony's song table entry at the new song header.
        header_addr = base + off["header_off"]
        p32(out, entry_off, header_addr)
        blob_cache[cache_key] = header_addr

        print(f"OK  Harmony {song_id:04d} <- {wav_path}")
        print(
            f"    {src_rate} Hz -> {args.sample_rate} Hz  duration={duration_s:.3f}s  "
            f"tempo=0x{tempo:02X}  holds={num_holds} ({hold_s:.3f}s, gap {hold_s - duration_s:+.3f}s)"
        )
        if gain != 1.0:
            print(f"    normalized: RMS gain x{gain:.2f} (source recording was quiet)", end="")
            print(f", {limited_pct:.1f}% samples soft-limited" if limited_pct > 0 else "")
        if suggest_gaps:
            print("    Suggestions (one closest match per target gap):")
            for sug_target, sug_tempo, sug_holds, sug_actual, sug_gap in suggest_tempos(duration_s, suggest_gaps):
                print(
                    f"      target={sug_target:+.2f}s  tempo=0x{sug_tempo:02X} ({sug_tempo:3d})  "
                    f"holds={sug_holds}  gap={sug_gap:+.3f}s"
                )

    # Plain-text credits, appended after all song data. Not referenced by any
    # pointer - purely informational (readable via `strings`/a hex editor),
    # no effect on gameplay or the game's own text/font system.
    credits_text = (
        "\n"
        "================================================\n"
        "REHARMONIZED AlexArroyoDuque\n"
        "================================================\n"
    )
    out += credits_text.encode("ascii")
    out += b"\x00"  # trailing pad byte (agbplay rejects data ending exactly at ROM end)

    if len(out) > MAX_GBA_ROM_SIZE:
        raise SystemExit("Result would exceed the GBA 32 MiB ROM limit")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)

    print()
    print("=" * 48)
    print(f"Created: {args.output}")
    print(f"Size:    {len(out) / (1024 * 1024):.2f} MiB")
    print(f"Songs:   {len(replacements)} replacement(s)")
    print()
    print("Test the resulting ROM in agbplay first, then in mGBA. If a loop")
    print("point clicks/pops or has a silence gap, re-run with --tempo tuned")
    print("up (shorter gap, more precision) or down, or trim that .wav so it")
    print("loops seamlessly on its own.")


if __name__ == "__main__":
    main()
