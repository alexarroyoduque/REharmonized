#!/usr/bin/env python3
"""Build REharmonized through the stages in modules/pipeline.py.

Usage:
    python3 wav_to_harmony.py rom-harmony-usa.gba config_wav_reharmonized.txt [output.gba]

Without output.gba, the name uses the version defined in modules/credits.py.
The original ROM is never overwritten.
"""
from modules.pipeline import main


if __name__ == "__main__":
    main()
