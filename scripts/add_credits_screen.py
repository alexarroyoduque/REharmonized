#!/usr/bin/env python3
"""
Harmony of Dissonance - REharmonized boot credits screen

Standalone, independent patch: takes an already-built REharmonized ROM
(output of wav_to_harmony_pause_fix.py) and prepends a simple splash screen
that shows the patch/music credits before the game boots, requiring a
START press to continue into the normal game.

Does NOT touch any existing script/patch - purely additive, applied last.

How it works:
  1. Renders a 240x160 credits image (Pillow) and converts it to GBA Mode 3
     bitmap format (RGB555, 2 bytes/pixel).
  2. Assembles a tiny ARM stub (arm-none-eabi-as/objcopy) that sets video
     Mode 3 + BG2, copies the bitmap into VRAM, waits for START, then jumps
     to the ORIGINAL game entry point (decoded from the ROM's own first
     instruction) - fully position-independent code (no absolute branches),
     so it can be appended anywhere in the ROM without relinking.
  3. Appends bitmap + stub after the existing ROM content, and rewrites the
     4-byte entry-point branch (offset 0x0, NOT part of the hardware-checked
     Nintendo logo at 0x04-0x9F) to jump to the new stub instead.

Usage:
    python3 add_credits_screen.py rom-reharmonized-testN.gba [rom-final.gba]

If the output path is omitted, it defaults to the input filename with
"-credits" appended before the extension (e.g. rom-testN.gba -> rom-testN-credits.gba).
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GBA_ROM_BASE = 0x08000000
SCREEN_W, SCREEN_H = 240, 160
MAX_GBA_ROM_SIZE = 32 * 1024 * 1024

# Single source of truth for the version shown on the credits screen - bump
# this here only, variant scripts (e.g. add_credits_screen_visual_improvement.py)
# import and reuse it.
VERSION = "1.2.0"

FONT_PATH = "/System/Library/Fonts/Menlo.ttc"

MUSIC_CREDITS = (
    "Jorge Fuentes, The Noble Demon, Tobbeh99 Music, Erik Hose, "
    "Dracula9AntiChapel, Francisco Relano, TheWanderingNight, "
    "Nostalgames_XP, WSPursuer, TristanMachinima, Good Knight Productions"
)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_credits_image() -> Image.Image:
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (8, 8, 24))
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(FONT_PATH, 16)
    header_font = ImageFont.truetype(FONT_PATH, 12)
    body_font = ImageFont.truetype(FONT_PATH, 8)

    y = 6
    title_text = "REharmonized"
    version_text = VERSION
    title_w = draw.textlength(title_text, font=title_font)
    version_w = draw.textlength(version_text, font=body_font)
    gap = 4
    start_x = (SCREEN_W - (title_w + gap + version_w)) / 2
    draw.text((start_x, y), title_text, font=title_font, fill=(255, 210, 60), anchor="la")
    draw.text((start_x + title_w + gap, y + 9), version_text, font=body_font, fill=(255, 210, 60), anchor="la")
    y += 20
    draw.text((SCREEN_W // 2, y), "AlexArroyoDuque", font=header_font, fill=(255, 255, 255), anchor="ma")
    y += 18

    for line in wrap_text(draw, "Aria of Sorrow Streamed Audio", header_font, SCREEN_W - 12):
        draw.text((SCREEN_W // 2, y), line, font=header_font, fill=(120, 200, 255), anchor="ma")
        y += 14
    draw.text((SCREEN_W // 2, y), "Rexius55", font=body_font, fill=(220, 220, 220), anchor="ma")
    y += 14

    draw.text((SCREEN_W // 2, y), "Music", font=header_font, fill=(120, 200, 255), anchor="ma")
    y += 14

    for line in wrap_text(draw, MUSIC_CREDITS, body_font, SCREEN_W - 12):
        draw.text((SCREEN_W // 2, y), line, font=body_font, fill=(220, 220, 220), anchor="ma")
        y += 10

    y = SCREEN_H - 12
    draw.text((SCREEN_W // 2, y), "PRESS START", font=body_font, fill=(160, 160, 160), anchor="ma")

    return img


def image_to_mode3_bitmap(img: Image.Image) -> bytes:
    assert img.size == (SCREEN_W, SCREEN_H)
    out = bytearray(SCREEN_W * SCREEN_H * 2)
    pixels = img.load()
    i = 0
    for yy in range(SCREEN_H):
        for xx in range(SCREEN_W):
            r, g, b = pixels[xx, yy]
            r5, g5, b5 = r >> 3, g >> 3, b >> 3
            gba_color = r5 | (g5 << 5) | (b5 << 10)
            struct.pack_into("<H", out, i, gba_color)
            i += 2
    return bytes(out)


def decode_entry_branch(rom: bytes) -> int:
    (instr,) = struct.unpack_from("<I", rom, 0)
    cond = instr >> 28
    opcode = (instr >> 24) & 0xF
    if cond != 0xE or opcode not in (0xA, 0xB):  # AL condition, B/BL
        raise SystemExit(
            f"ROM entry point at 0x{GBA_ROM_BASE:08X} is not a plain ARM B/BL "
            f"instruction (raw=0x{instr:08X}) - refusing to patch."
        )
    offset24 = instr & 0xFFFFFF
    if offset24 & 0x800000:
        offset24 -= 0x1000000
    target = GBA_ROM_BASE + 8 + (offset24 << 2)
    return target


def assemble_stub(bitmap_addr: int, original_target: int, tmpdir: Path) -> bytes:
    asm_src = f"""
    .arm
    .equ REG_DISPCNT, 0x04000000
    .equ REG_KEYINPUT, 0x04000130
    .equ VRAM, 0x06000000
    .equ BITMAP_SRC, 0x{bitmap_addr:08X}
    .equ ORIGINAL_TARGET, 0x{original_target:08X}
    .equ WORD_COUNT, {(SCREEN_W * SCREEN_H * 2) // 4}

    .global _start
_start:
    ldr r0, =REG_DISPCNT
    ldr r1, =0x0403
    str r1, [r0]

    ldr r0, =BITMAP_SRC
    ldr r1, =VRAM
    ldr r2, =WORD_COUNT
copy_loop:
    ldr r3, [r0], #4
    str r3, [r1], #4
    subs r2, r2, #1
    bne copy_loop

wait_press:
    ldr r0, =REG_KEYINPUT
    ldrh r1, [r0]
    mov r2, #0x0008
    tst r1, r2
    bne wait_press

    ldr r0, =ORIGINAL_TARGET
    bx r0

    .ltorg
"""
    src_path = tmpdir / "stub.s"
    obj_path = tmpdir / "stub.o"
    bin_path = tmpdir / "stub.bin"
    src_path.write_text(asm_src)

    subprocess.run(
        ["arm-none-eabi-as", "-mcpu=arm7tdmi", "-o", str(obj_path), str(src_path)],
        check=True,
    )
    subprocess.run(
        ["arm-none-eabi-objcopy", "-O", "binary", str(obj_path), str(bin_path)],
        check=True,
    )
    return bin_path.read_bytes()


def main(render_fn=render_credits_image) -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(f"Usage: {sys.argv[0]} input.gba [output.gba]")

    if shutil.which("arm-none-eabi-as") is None or shutil.which("arm-none-eabi-objcopy") is None:
        raise SystemExit(
            "arm-none-eabi-as / arm-none-eabi-objcopy not found in PATH.\n"
            "Install with: brew install arm-none-eabi-binutils"
        )

    input_path = Path(sys.argv[1])
    if len(sys.argv) == 3:
        output_path = Path(sys.argv[2])
    else:
        output_path = input_path.with_name(f"{input_path.stem}-credits{input_path.suffix}")
    rom = bytearray(input_path.read_bytes())

    original_target = decode_entry_branch(bytes(rom))
    print(f"Original entry target: 0x{original_target:08X}")

    img = render_fn()
    bitmap = image_to_mode3_bitmap(img)

    # Append offset must be 4-byte aligned for the ARM stub.
    append_off = len(rom)
    if append_off % 4:
        rom += b"\x00" * (4 - append_off % 4)
        append_off = len(rom)

    bitmap_addr = GBA_ROM_BASE + append_off
    rom += bitmap

    stub_off = len(rom)
    if stub_off % 4:
        rom += b"\x00" * (4 - stub_off % 4)
        stub_off = len(rom)
    stub_addr = GBA_ROM_BASE + stub_off

    with tempfile.TemporaryDirectory() as tmp:
        stub_code = assemble_stub(bitmap_addr, original_target, Path(tmp))
    rom += stub_code

    # Redirect the ROM's own entry point to our stub (ARM B instruction).
    branch_offset = (stub_addr - (GBA_ROM_BASE + 8)) >> 2
    new_entry_instr = 0xEA000000 | (branch_offset & 0xFFFFFF)
    struct.pack_into("<I", rom, 0, new_entry_instr)

    if len(rom) > MAX_GBA_ROM_SIZE:
        raise SystemExit("Result would exceed the GBA 32 MiB ROM limit")

    output_path.write_bytes(rom)
    print(f"Bitmap @0x{bitmap_addr:08X} ({len(bitmap)} bytes)")
    print(f"Stub   @0x{stub_addr:08X} ({len(stub_code)} bytes)")
    print(f"Created: {output_path} ({len(rom) / 1024 / 1024:.2f} MiB)")


if __name__ == "__main__":
    main()
