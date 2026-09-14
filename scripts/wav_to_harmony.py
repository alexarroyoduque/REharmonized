#!/usr/bin/env python3
"""
Harmony of Dissonance - REharmonized all-in-one builder

Convenience wrapper around the two standalone tools already in this folder:
runs wav_to_harmony_pause_fix.py (song injection + pause/resume patch) then
add_credits_screen.py (boot credits screen) as subprocesses, chaining their
output/input through a temp file. Neither script is modified or duplicated -
this just saves you from running them one after another by hand.

Usage:
  python3 wav_to_harmony.py harmony.gba config_wav_reharmonized.txt [output.gba]

If output.gba is omitted, it defaults to "<harmony-stem>-<VERSION><suffix>"
in the current directory (VERSION comes from add_credits_screen.VERSION),
e.g. harmony.gba -> harmony-1.2.2.gba.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import add_credits_screen

SCRIPT_DIR = Path(__file__).parent
INJECTOR = SCRIPT_DIR / "wav_to_harmony_pause_fix.py"
CREDITS = SCRIPT_DIR / "add_credits_screen.py"


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(f"Usage: {sys.argv[0]} harmony.gba config.txt [output.gba]")

    rom_path = Path(sys.argv[1])
    config_path = Path(sys.argv[2])
    if len(sys.argv) == 4:
        output_path = Path(sys.argv[3])
    else:
        output_path = Path(f"{rom_path.stem}-{add_credits_screen.VERSION}{rom_path.suffix}")

    with tempfile.TemporaryDirectory() as tmp:
        injected_path = Path(tmp) / f"injected{rom_path.suffix}"

        print(f"[1/2] Injecting songs + pause patch -> {injected_path.name}")
        subprocess.run(
            [sys.executable, str(INJECTOR), str(rom_path), str(config_path), str(injected_path)],
            check=True,
        )

        print()
        print(f"[2/2] Adding credits screen -> {output_path}")
        subprocess.run(
            [sys.executable, str(CREDITS), str(injected_path), str(output_path)],
            check=True,
        )

    print()
    print(f"Created: {output_path}")


if __name__ == "__main__":
    main()
