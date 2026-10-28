#!/usr/bin/env python3
"""Run: python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v"""
from __future__ import annotations

import hashlib
import math
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from modules import injection as injector
from modules import pipeline
from modules.version import VERSION


class ConfigTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.txt"
            path.write_text(text, encoding="utf-8")
            return injector.parse_config(path)

    def test_legacy_and_fifth_field(self):
        entries = self.parse(
            '1 "a b.wav" auto\n2 a.wav 0x50 off\n'
            '3 a.wav 1 auto 12.2 # intro\n4 a.wav 30 0.25 0\n'
            '5 a.wav 1 auto 12.4 0.05\n6 a.wav 1 off 0 0\n'
        )
        self.assertEqual(entries, [
            (1, Path("a b.wav"), None, None, 0.0, 0.0),
            (2, Path("a.wav"), 80, 0.0, 0.0, 0.0),
            (3, Path("a.wav"), 1, None, 12.2, 0.0),
            (4, Path("a.wav"), 30, 0.25, 0.0, 0.0),
            (5, Path("a.wav"), 1, None, 12.4, 0.05),
            (6, Path("a.wav"), 1, 0.0, 0.0, 0.0),
        ])

    def test_version_comes_from_repository_file(self):
        version_file = SCRIPT_DIR.parent / "VERSION"
        self.assertEqual(VERSION, version_file.read_text(encoding="ascii").strip())

    def test_invalid_offsets(self):
        for value in ("-1", "nan", "inf", "-inf", "bad"):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                self.parse(f"1 a.wav auto auto {value}")

    def test_duplicate_song_and_extra_field(self):
        for text in ("1 a.wav auto\n1 a.wav auto auto 1", "1 a.wav auto auto 1 0.05 extra"):
            with self.subTest(text=text), self.assertRaises(SystemExit):
                self.parse(text)

    def test_invalid_crossfades(self):
        for value in ("-1", "nan", "inf", "-inf", "bad"):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                self.parse(f"1 a.wav auto auto 0.25 {value}")
        with self.assertRaisesRegex(SystemExit, "positive loop start"):
            self.parse("1 a.wav auto auto 0 0.05")


class CrossfadeTests(unittest.TestCase):
    def test_zero_leaves_audio_and_offset_unchanged(self):
        samples = [0.1, 0.2, -0.3, -0.4]
        result, offset = injector.apply_loop_crossfade(samples, 100, 0.01, 0)
        self.assertIs(result, samples)
        self.assertEqual(offset, 0.01)

    def test_linear_blend_and_native_jump(self):
        samples = [i / 100 for i in range(100)]
        original = samples.copy()
        mixed, offset = injector.apply_loop_crossfade(samples, 100, 0.2, 0.1)
        self.assertEqual(samples, original)  # The caller's source is untouched.
        self.assertEqual(mixed[:90], samples[:90])
        self.assertEqual(len(mixed), len(samples))
        self.assertEqual(offset, 0.3)  # Continue after the head already mixed.
        self.assertEqual(mixed[90], samples[90])
        self.assertEqual(mixed[-1], samples[29])
        for i in range(10):
            self.assertAlmostEqual(mixed[90 + i],
                                   (1 - i / 9) * samples[90 + i] + i / 9 * samples[20 + i])
        blob, off = injector.build_song_blob(
            pcm=injector.base.to_pcm8(mixed), sample_rate=100,
            base_note=60, volume=127, tempo=1, num_holds=1, loop_start_s=offset,
        )
        self.assertEqual(struct.unpack_from("<I", blob, off["wave_off"] + 8)[0], 30)

    def test_correlated_audio_is_not_boosted(self):
        mixed, _ = injector.apply_loop_crossfade([0.75] * 100, 100, 0.2, 0.1)
        for sample in mixed:
            self.assertAlmostEqual(sample, 0.75)

    def test_invalid_crossfade_boundaries(self):
        for start, fade in ((0, 0.1), (1, 0.1), (math.nan, 0.1),
                            (0.2, -1), (0.2, math.nan), (0.2, math.inf),
                            (0.2, 0.001), (0.2, 0.41)):
            with self.subTest(start=start, fade=fade), self.assertRaises(ValueError):
                injector.apply_loop_crossfade([0.1] * 100, 100, start, fade)


class BlobTests(unittest.TestCase):
    def setUp(self):
        self.kwargs = dict(
            pcm=bytes(range(256)) * 8, sample_rate=1000,
            base_note=60, volume=127, tempo=80, num_holds=3,
        )

    def test_zero_offset_is_byte_identical_to_legacy(self):
        self.assertEqual(injector.build_song_blob(**self.kwargs),
                         injector.base.build_song_blob(**self.kwargs))

    def test_native_header_and_wait_target(self):
        blob, off = injector.build_song_blob(**self.kwargs, loop_start_s=0.25)
        flags, rate, loop_start, length = struct.unpack_from("<IIII", blob, off["wave_off"])
        self.assertEqual((flags, rate, loop_start, length), (0x40000000, 1024000, 250, 2048))
        self.assertEqual(blob[off["sample_off"]:off["sample_off"] + length], self.kwargs["pcm"])
        self.assertEqual(blob[off["loop_wait_off"]:off["seg_a_goto_ptr_off"]], b"\xb0\xb2")
        self.assertEqual(blob[off["loop_wait_off"] - 3:off["loop_wait_off"]], b"\xcf\x3c\x7f")
        self.assertLess(len(blob) - length, 160)  # No duplicate intro or loop PCM.

    def test_nearest_resampled_sample(self):
        blob, off = injector.build_song_blob(**self.kwargs, loop_start_s=0.2506)
        self.assertEqual(struct.unpack_from("<I", blob, off["wave_off"] + 8)[0], 251)

    def test_invalid_audio_boundaries(self):
        for offset in (-1, math.nan, math.inf, 2.048, 3, 0.00001, 2.0479):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                injector.build_song_blob(**self.kwargs, loop_start_s=offset)


class PipelineTests(unittest.TestCase):
    def test_failed_credits_preserve_existing_output_and_clean_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.gba"
            output = root / "output.gba"
            source.write_bytes(b"original")
            output.write_bytes(b"previous valid output")

            def inject(rom_path, config_path, target):
                target.write_bytes(b"injected")

            def failed_credits(injected, target):
                target.write_bytes(b"partial output")
                raise RuntimeError("Credits failed")

            with patch.object(pipeline, "inject_songs", side_effect=inject), \
                    patch.object(pipeline.credits, "add_credits", side_effect=failed_credits):
                with self.assertRaisesRegex(RuntimeError, "Credits failed"):
                    pipeline.build_rom(source, root / "config.txt", output)

            self.assertEqual(source.read_bytes(), b"original")
            self.assertEqual(output.read_bytes(), b"previous valid output")
            self.assertEqual(sorted(path.name for path in root.iterdir()),
                             ["original.gba", "output.gba"])

    def test_success_publishes_only_completed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.gba"
            output = root / "output.gba"
            source.write_bytes(b"original")
            output.write_bytes(b"previous valid output")

            def inject(rom_path, config_path, target):
                target.write_bytes(b"injected")

            def credits(injected, target):
                self.assertEqual(injected.read_bytes(), b"injected")
                self.assertEqual(output.read_bytes(), b"previous valid output")
                target.write_bytes(b"complete output")

            with patch.object(pipeline, "inject_songs", side_effect=inject), \
                    patch.object(pipeline.credits, "add_credits", side_effect=credits):
                pipeline.build_rom(source, root / "config.txt", output)
            self.assertEqual(output.read_bytes(), b"complete output")
            self.assertEqual(source.read_bytes(), b"original")
            self.assertEqual(len(list(root.iterdir())), 2)


@unittest.skipUnless((SCRIPT_DIR / "rom-harmony-usa.gba").is_file(), "Original USA ROM unavailable")
class RomTests(unittest.TestCase):
    def setUp(self):
        self.rom = SCRIPT_DIR / "rom-harmony-usa.gba"
        self.original = self.rom.read_bytes()
        self.original_hash = hashlib.sha256(self.original).digest()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.wav = self.directory / "test.wav"
        with wave.open(str(self.wav), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(11025)
            audio.writeframes(b"".join(struct.pack("<h", round(10000 * math.sin(i / 10))) for i in range(11025)))
        self.config = self.directory / "config.txt"

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.rom.read_bytes()).digest(), self.original_hash)

    def run_injector(self, text, output=None):
        self.config.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "modules.injection",
             str(self.rom), str(self.config), str(output or self.directory / "out.gba"),
             "--suggest-gaps", ""], capture_output=True, text=True, cwd=SCRIPT_DIR,
        )

    def test_rom_pointers_cache_and_pause_patch(self):
        result = self.run_injector(
            f'1 "{self.wav}" auto off\n2 "{self.wav}" auto off 0.25\n'
            f'3 "{self.wav}" auto off 0.25\n4 "{self.wav}" auto off\n'
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rom = (self.directory / "out.gba").read_bytes()
        base = injector.base
        headers = [base.u32(rom, base.HOD_SONG_TABLE + song * 8) - base.GBA_ROM_BASE for song in range(1, 5)]
        self.assertEqual(headers[0], headers[3])
        self.assertEqual(headers[1], headers[2])
        self.assertNotEqual(headers[0], headers[1])
        header = headers[1]
        tone = base.u32(rom, header + 4) - base.GBA_ROM_BASE
        track = base.u32(rom, header + 8) - base.GBA_ROM_BASE
        wave_off = base.u32(rom, tone + 4) - base.GBA_ROM_BASE
        self.assertEqual(struct.unpack_from("<IIII", rom, wave_off),
                         (0x40000000, 11025 * 1024, round(0.25 * 11025), 11025))
        wait_off = track + 2 + 9  # TEMPO then keyshift, voice, volume, TIE.
        self.assertEqual(rom[wait_off:wait_off + 2], b"\xb0\xb2")
        self.assertEqual(base.u32(rom, wait_off + 2), base.GBA_ROM_BASE + wait_off)
        mono, _ = base.read_wav_mono_float(self.wav)
        self.assertEqual(rom[wave_off + 16:wave_off + 16 + 11025], base.to_pcm8(mono))
        patch_off = injector.PATCH_ADDR - base.GBA_ROM_BASE
        cave_off = injector.CAVE_ADDR - base.GBA_ROM_BASE
        self.assertEqual(rom[patch_off:patch_off + len(injector.PATCH_BYTES)], injector.PATCH_BYTES)
        self.assertEqual(rom[cave_off:cave_off + 4], injector.VENEER_PREFIX)
        payload_addr = base.u32(rom, cave_off + 4) & ~1
        payload_off = payload_addr - base.GBA_ROM_BASE
        self.assertEqual(rom[payload_off:payload_off + len(injector.STUB_BYTES)], injector.STUB_BYTES)
        self.assertEqual(base.u32(rom, cave_off + 12),
                 (payload_addr + injector.RESUME_STUB_OFFSET) | 1)

    def test_end_offset_rejected_without_output(self):
        result = self.run_injector(f'1 "{self.wav}" auto auto 1\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("before the end", result.stderr)
        self.assertFalse((self.directory / "out.gba").exists())

    def test_crossfade_pcm_jump_and_cache(self):
        result = self.run_injector(
            f'1 "{self.wav}" 1 off 0.25 0.05\n'
            f'2 "{self.wav}" 1 off 0.25 0.05\n'
            f'3 "{self.wav}" 1 off 0.25 0\n'
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rom = (self.directory / "out.gba").read_bytes()
        base = injector.base
        headers = [base.u32(rom, base.HOD_SONG_TABLE + song * 8) - base.GBA_ROM_BASE
                   for song in (1, 2, 3)]
        self.assertEqual(headers[0], headers[1])
        self.assertNotEqual(headers[0], headers[2])
        tone = base.u32(rom, headers[0] + 4) - base.GBA_ROM_BASE
        wave_off = base.u32(rom, tone + 4) - base.GBA_ROM_BASE
        mono, _ = base.read_wav_mono_float(self.wav)
        mixed, offset = injector.apply_loop_crossfade(mono, 11025, 0.25, 0.05)
        self.assertEqual(struct.unpack_from("<IIII", rom, wave_off),
                         (0x40000000, 11025 * 1024, round(offset * 11025), 11025))
        self.assertEqual(rom[wave_off + 16:wave_off + 16 + 11025], base.to_pcm8(mixed))
        self.assertIn("crossfade=", result.stdout)

    def test_excessive_crossfade_rejected_without_output(self):
        result = self.run_injector(f'1 "{self.wav}" auto auto 0.25 0.4\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("half the loop", result.stderr)
        self.assertFalse((self.directory / "out.gba").exists())

    def test_original_cannot_be_output(self):
        result = self.run_injector(f'1 "{self.wav}" auto\n', self.rom)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite", result.stderr)

    def test_wrapper_also_protects_original(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "wav_to_harmony.py"),
             str(self.rom), str(self.config), str(self.rom)], capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite", result.stderr)


if __name__ == "__main__":
    unittest.main()