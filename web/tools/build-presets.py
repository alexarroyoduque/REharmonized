import json
import shlex
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    config = root / "scripts/config_wav_reharmonized.txt"
    music = (root / "music").resolve()
    files = {}
    paths = {}
    presets = {}
    for line in config.read_text().splitlines():
        fields = shlex.split(line, comments=True)
        if not fields:
            continue
        if len(fields) not in (3, 4):
            raise ValueError(f"Invalid preset: {line}")
        song_id = str(int(fields[0], 0))
        source = (config.parent / fields[1]).resolve()
        if not source.is_relative_to(music) or not source.is_file():
            raise ValueError(f"Missing or invalid preset WAV: {source}")
        if source not in paths:
            paths[source] = f"presets/song-{song_id}.wav"
            files[paths[source]] = str(source)
        if song_id in presets:
            raise ValueError(f"Duplicate preset song ID: {song_id}")
        presets[song_id] = {
            "wavPath": paths[source],
            "tempo": fields[2],
            "volume": fields[3] if len(fields) == 4 else "auto",
        }
    if not presets:
        raise ValueError("Preset configuration is empty")
    print(json.dumps({"files": files, "presets": presets}))


if __name__ == "__main__":
    main()