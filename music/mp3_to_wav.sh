#!/usr/bin/env bash
# Converts every .mp3 in this folder to .wav (mono, 16-bit PCM, 11025 Hz) for wav_to_harmony.py.
# Skips a file if the matching .wav already exists.
set -euo pipefail
cd "$(dirname "$0")"

for mp3 in *.mp3; do
    [ -e "$mp3" ] || continue
    wav="${mp3%.mp3}.wav"
    if [ -e "$wav" ]; then
        echo "Skipping (already exists): $wav"
        continue
    fi
    echo "Converting: $mp3 -> $wav"
    ffmpeg -y -i "$mp3" -ar 11025 -ac 1 -sample_fmt s16 "$wav"
done
