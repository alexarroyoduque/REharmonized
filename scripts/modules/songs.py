"""MP2K sequences, instrument/sample headers and native intro loops."""
from __future__ import annotations

import math
import struct

DEFAULT_BASE_NOTE = 0x3C


DEFAULT_VOLUME = 0x7F  # BE command's valid range is 0-127; >127 overflows the


def build_legacy_song_blob(
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

    blob, offsets = build_legacy_song_blob(
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
