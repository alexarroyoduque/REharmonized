"""Coordinate song injection, the pause fix and boot credits atomically."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from . import credits
from .injection import inject_songs
from .rom import is_advance_collection
from .advance_collection import pad_output


def build_rom(rom_path: Path, config_path: Path, output_path: Path) -> None:
    """Publish a completed ROM only after every stage succeeds."""
    if output_path.resolve() == rom_path.resolve():
        raise SystemExit("Output must differ from the original ROM; refusing to overwrite it")

    collection = is_advance_collection(rom_path.read_bytes())

    with tempfile.TemporaryDirectory(dir=output_path.resolve().parent) as tmp:
        injected_path = Path(tmp) / f"injected{rom_path.suffix}"
        final_path = Path(tmp) / f"final{rom_path.suffix}"
        print(f"[1/2] Injecting songs + pause patch -> {injected_path.name}")
        inject_songs(rom_path, config_path, injected_path)
        print()
        if collection:
            print("[2/2] Advance Collection USA (M2): skip Mode 3 credits; pad to exactly 32 MiB (0xFF)")
            print("M2 pause keeps BGM advancing and audible; the standard GBA mute hook is not applied.")
            final_path.write_bytes(pad_output(injected_path.read_bytes()))
        else:
            print(f"[2/2] Adding credits screen -> {output_path}")
            credits.add_credits(injected_path, final_path)
        final_path.replace(output_path)

    print()
    print(f"Created: {output_path}")


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(f"Usage: {sys.argv[0]} harmony.gba config.txt [output.gba]")
    rom_path = Path(sys.argv[1])
    config_path = Path(sys.argv[2])
    output_path = (Path(sys.argv[3]) if len(sys.argv) == 4 else
                   Path(f"{rom_path.stem}-{credits.VERSION}{rom_path.suffix}"))
    build_rom(rom_path, config_path, output_path)
