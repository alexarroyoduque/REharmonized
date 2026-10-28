"""Pause/mute regression tests; Unicorn enables execution of the actual Thumb code."""
from __future__ import annotations

import importlib.util
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
from modules import pause_patch as patch


def original_fixture():
    rom = bytearray(8 * 1024 * 1024)
    signatures = (
        (patch.PATCH_ADDR, patch.ORIGINAL_PATCH_BYTES),
        (patch.RESUME_ADDR, patch.ORIGINAL_RESUME_BYTES),
        (patch.VOLUME_ADDR, patch.ORIGINAL_VOLUME_BYTES),
        (0x081A6B2C, bytes.fromhex("c04f0003d021000307000000005000030024000302000000")),
        (0x080BB414, struct.pack("<I", patch.PAUSED_FLAG)),
        (0x080BB42C, struct.pack("<I", patch.PAUSED_FLAG)),
    )
    for address, data in signatures:
        offset = address - patch.GBA_ROM_BASE
        rom[offset:offset + len(data)] = data
    return rom


class PausePatchTests(unittest.TestCase):
    def test_payload_and_veneer_destinations(self):
        rom = original_fixture()
        original_size = len(rom)
        patch.apply_pause_patch(rom)
        self.assertEqual(len(rom), original_size + len(patch.STUB_BYTES))
        self.assertEqual(rom[original_size:], patch.STUB_BYTES)
        for address, destination in (
            (patch.CAVE_ADDR, patch.GBA_ROM_BASE + original_size),
            (patch.CAVE_ADDR + 8, patch.GBA_ROM_BASE + original_size + patch.RESUME_STUB_OFFSET),
            (patch.VOLUME_ADDR, patch.GBA_ROM_BASE + original_size + patch.VOLUME_STUB_OFFSET),
        ):
            offset = address - patch.GBA_ROM_BASE
            self.assertEqual(rom[offset:offset + 4], patch.VENEER_PREFIX)
            self.assertEqual(struct.unpack_from("<I", rom, offset + 4)[0], destination | 1)

    def test_invalid_engine_or_cave_does_not_modify_rom(self):
        for address in (patch.PATCH_ADDR, patch.RESUME_ADDR, patch.VOLUME_ADDR,
                        patch.CAVE_ADDR, 0x081A6B2C, 0x080BB414, 0x080BB42C):
            with self.subTest(address=hex(address)):
                rom = original_fixture()
                rom[address - patch.GBA_ROM_BASE] ^= 1
                before = bytes(rom)
                with self.assertRaisesRegex(SystemExit, "unexpected bytes"):
                    patch.apply_pause_patch(rom)
                self.assertEqual(rom, before)

    def test_size_limit_does_not_modify_rom(self):
        rom = original_fixture()
        rom.extend(bytes(patch.MAX_GBA_ROM_SIZE - len(rom)))
        before = bytes(rom)
        with self.assertRaisesRegex(SystemExit, "32 MiB"):
            patch.apply_pause_patch(rom)
        self.assertEqual(rom, before)

    def test_payload_alignment(self):
        rom = original_fixture()
        rom.append(0x5A)
        patch.apply_pause_patch(rom)
        self.assertEqual(rom[8 * 1024 * 1024:8 * 1024 * 1024 + 4], b"\x5a\0\0\0")
        self.assertEqual(rom[-len(patch.STUB_BYTES):], patch.STUB_BYTES)

    @unittest.skipUnless(all(shutil.which(f"arm-none-eabi-{tool}") for tool in ("as", "ld", "objcopy", "nm")),
                         "ARM binutils unavailable")
    def test_embedded_payload_matches_assembly_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            obj, elf, binary = root / "stub.o", root / "stub.elf", root / "stub.bin"
            subprocess.run(["arm-none-eabi-as", "-mcpu=arm7tdmi", "-o", str(obj),
                            str(SCRIPT_DIR / "modules/pause_mute.s")], check=True)
            subprocess.run(["arm-none-eabi-ld", "-Ttext=0", "-e", "pause_stub", "-o", str(elf), str(obj)], check=True)
            subprocess.run(["arm-none-eabi-objcopy", "-O", "binary", str(elf), str(binary)], check=True)
            self.assertEqual(binary.read_bytes(), patch.STUB_BYTES)
            symbols = subprocess.check_output(["arm-none-eabi-nm", "-n", str(elf)], text=True)
            for name, offset in (("pause_stub", patch.PAUSE_STUB_OFFSET),
                                 ("resume_stub", patch.RESUME_STUB_OFFSET),
                                 ("volume_stub", patch.VOLUME_STUB_OFFSET)):
                self.assertIn(f"{offset:08x} T {name}", symbols)


@unittest.skipUnless(importlib.util.find_spec("unicorn") and (SCRIPT_DIR / "rom-harmony-usa.gba").is_file(),
                     "Unicorn and original USA ROM required for ARM execution")
class PauseArmTests(unittest.TestCase):
    def setUp(self):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
        from unicorn import arm_const
        self.reg = arm_const
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.uc.mem_map(0x08000000, 32 * 1024 * 1024)
        self.uc.mem_map(0x03000000, 0x8000)
        rom = bytearray((SCRIPT_DIR / "rom-harmony-usa.gba").read_bytes())
        patch.apply_pause_patch(rom)
        self.uc.mem_write(0x08000000, bytes(rom))
        self.players = (patch.BGM_PLAYER, 0x03005000, 0x03005040, 0x03005090)
        self.tracks = (patch.BGM_TRACKS, 0x03002400, 0x030024A0, 0x03002540)
        for player, tracks, count in zip(self.players, self.tracks, (7, 2, 2, 1)):
            self.write32(player + 4, 1)
            self.uc.mem_write(player + 8, bytes([count]))
            self.write32(player + 44, tracks)
            self.write32(player + 52, 0x68736D53)
            for index in range(count):
                self.uc.mem_write(tracks + index * 80, b"\x80")
        self.calls = []

        def trace(uc, address, size, data):
            if address in (0x080BCAE4, 0x080BC254):
                self.calls.append((address, uc.reg_read(arm_const.UC_ARM_REG_R0)))

        self.uc.hook_add(UC_HOOK_CODE, trace)

    def write32(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value))

    def call(self, address):
        self.uc.reg_write(self.reg.UC_ARM_REG_SP, 0x03007F00)
        self.uc.reg_write(self.reg.UC_ARM_REG_LR, 0x08000101)
        self.uc.emu_start(address | 1, 0x08000100, count=20000)
        self.assertEqual(self.uc.reg_read(self.reg.UC_ARM_REG_PC), 0x08000100)
        self.assertEqual(self.uc.reg_read(self.reg.UC_ARM_REG_SP), 0x03007F00)

    def test_pause_resume_calls_and_register_preservation(self):
        bgm_before = bytes(self.uc.mem_read(patch.BGM_PLAYER, 64))
        channel = 0x03006000
        self.write32(patch.BGM_TRACKS + 32, channel)
        self.uc.mem_write(channel, b"\x80" + bytes(range(1, 64)))
        channel_before = bytes(self.uc.mem_read(channel, 64))
        self.uc.mem_write(patch.PAUSED_FLAG, b"\x01\0")
        self.uc.reg_write(self.reg.UC_ARM_REG_R4, 0x1234)
        self.uc.reg_write(self.reg.UC_ARM_REG_R5, 0x5678)
        self.call(0x080BC448)
        self.assertEqual(self.calls, [(0x080BCAE4, player) for player in self.players[1:]])
        self.assertEqual(self.uc.reg_read(self.reg.UC_ARM_REG_R4), 0x1234)
        self.assertEqual(self.uc.reg_read(self.reg.UC_ARM_REG_R5), 0x5678)
        self.assertEqual(struct.unpack("<I", self.uc.mem_read(patch.BGM_PLAYER + 4, 4))[0], 1)
        self.assertEqual(bytes(self.uc.mem_read(patch.BGM_PLAYER, 64)), bgm_before)
        self.assertEqual(bytes(self.uc.mem_read(channel, 64)), channel_before)
        self.assertEqual([self.uc.mem_read(patch.BGM_TRACKS + index * 80, 1)[0] for index in range(7)], [0x83] * 7)
        for index in range(7):
            self.uc.mem_write(patch.BGM_TRACKS + index * 80, b"\x80")
        self.calls.clear()
        self.uc.mem_write(patch.PAUSED_FLAG, b"\0\0")
        self.call(0x080BC480)
        self.assertEqual(self.calls, [(0x080BC254, player) for player in self.players])
        self.assertEqual(bytes(self.uc.mem_read(patch.BGM_PLAYER, 64)), bgm_before)
        self.assertEqual(bytes(self.uc.mem_read(channel, 64)), channel_before)
        self.assertEqual([self.uc.mem_read(patch.BGM_TRACKS + index * 80, 1)[0] for index in range(7)], [0x83] * 7)

    def gain(self, track, paused, velocity=100, pan=0):
        channel = 0x03006000
        self.uc.mem_write(channel, bytes(64))
        self.uc.mem_write(channel + 18, bytes([velocity]))
        self.uc.mem_write(channel + 20, bytes([pan & 255]))
        self.uc.mem_write(track + 16, bytes([91, 73]))
        self.uc.mem_write(patch.PAUSED_FLAG, struct.pack("<H", paused))
        before_track = bytes(self.uc.mem_read(track, 80))
        self.uc.reg_write(self.reg.UC_ARM_REG_R4, channel)
        self.uc.reg_write(self.reg.UC_ARM_REG_R5, track)
        self.call(patch.VOLUME_ADDR)
        self.assertEqual(bytes(self.uc.mem_read(track, 80)), before_track)
        self.assertEqual(bytes(self.uc.mem_read(channel + 18, 1)), bytes([velocity]))
        return tuple(self.uc.mem_read(channel + 2, 2))

    def test_only_bgm_muted_and_exact_gain_restored(self):
        for track in (patch.BGM_TRACKS, patch.BGM_TRACKS_END - 80):
            for velocity, pan in ((127, -64), (99, 0), (40, 63)):
                with self.subTest(track=hex(track), velocity=velocity, pan=pan):
                    normal = self.gain(track, 0, velocity, pan)
                    self.assertEqual(normal, (min(255, ((128 + pan) * velocity * 91) >> 14),
                                              min(255, ((127 - pan) * velocity * 73) >> 14)))
                    self.assertTrue(any(normal))
                    self.assertEqual(self.gain(track, 1, velocity, pan), (0, 0))
                    self.assertEqual(self.gain(track, 0, velocity, pan), normal)
        for track in self.tracks[1:]:
            self.assertEqual(self.gain(track, 1), self.gain(track, 0))


if __name__ == "__main__":
    unittest.main()