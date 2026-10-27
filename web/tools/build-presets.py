import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from modules.config import parse_config


def main():
    root = Path(__file__).resolve().parents[2]
    config = root / "scripts/config_wav_reharmonized.txt"
    music = (root / "music").resolve()
    files = {}
    paths = {}
    presets = {}
    for identifier, wav_path, tempo, volume, loop_start, crossfade in parse_config(config):
        song_id = str(identifier)
        source = (config.parent / wav_path).resolve()
        if not source.is_relative_to(music) or not source.is_file():
            raise ValueError(f"Missing or invalid preset WAV: {source}")
        if source not in paths:
            paths[source] = f"presets/song-{song_id}.wav"
            files[paths[source]] = str(source)
        if song_id in presets:
            raise ValueError(f"Duplicate preset song ID: {song_id}")
        presets[song_id] = {
            "wavPath": paths[source],
            "tempo": "auto" if tempo is None else str(tempo),
            "volume": "auto" if volume is None else "off" if volume == 0 else str(volume),
            "loopStart": loop_start,
            "crossfade": crossfade,
        }
    if not presets:
        raise ValueError("Preset configuration is empty")
    print(json.dumps({"files": files, "presets": presets}))


if __name__ == "__main__":
    main()