#!/usr/bin/env python3
"""
Harmony of Dissonance - REharmonized boot credits screen (Visual Improvement variant)

Same as add_credits_screen.py, but for the alternative patch that applies
REharmonized's music changes on top of Pemburu Vampir's "Visual Improvement"
patch. Only the credits image changes (adds a Visual Improvement / Pemburu
Vampir line); everything else (bitmap conversion, ARM stub, ROM patching) is
reused as-is from add_credits_screen.py - do not duplicate that logic here.

The version number shown on screen is NOT duplicated here: it's imported
from add_credits_screen.VERSION, so it only ever needs to be bumped in one
place.

Usage:
    python3 add_credits_screen_visual_improvement.py rom-reharmonized-testN.gba rom-final.gba
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

import add_credits_screen as base

# Version of Pemburu Vampir's Visual Improvement patch, independent of base.VERSION
VISUAL_IMPROVEMENT_VERSION = "1.2.7"


def render_credits_image() -> Image.Image:
    img = Image.new("RGB", (base.SCREEN_W, base.SCREEN_H), (8, 8, 24))
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(base.FONT_PATH, 16)
    header_font = ImageFont.truetype(base.FONT_PATH, 12)
    body_font = ImageFont.truetype(base.FONT_PATH, 8)

    y = 6
    title_text = "REharmonized"
    version_text = base.VERSION
    title_w = draw.textlength(title_text, font=title_font)
    version_w = draw.textlength(version_text, font=body_font)
    gap = 4
    start_x = (base.SCREEN_W - (title_w + gap + version_w)) / 2
    draw.text((start_x, y), title_text, font=title_font, fill=(255, 210, 60), anchor="la")
    draw.text((start_x + title_w + gap, y + 9), version_text, font=body_font, fill=(255, 210, 60), anchor="la")
    y += 20
    draw.text((base.SCREEN_W // 2, y), "AlexArroyoDuque", font=header_font, fill=(255, 255, 255), anchor="ma")
    y += 16

    vi_text = "Visual Improvement"
    vi_version_text = VISUAL_IMPROVEMENT_VERSION
    vi_w = draw.textlength(vi_text, font=header_font)
    vi_version_w = draw.textlength(vi_version_text, font=body_font)
    vi_start_x = (base.SCREEN_W - (vi_w + gap + vi_version_w)) / 2
    draw.text((vi_start_x, y), vi_text, font=header_font, fill=(120, 220, 120), anchor="la")
    draw.text((vi_start_x + vi_w + gap, y + 4), vi_version_text, font=body_font, fill=(120, 220, 120), anchor="la")
    y += 13
    draw.text((base.SCREEN_W // 2, y), "Pemburu Vampir", font=body_font, fill=(220, 220, 220), anchor="ma")
    y += 13

    for line in base.wrap_text(draw, "Aria of Sorrow Streamed Audio", header_font, base.SCREEN_W - 12):
        draw.text((base.SCREEN_W // 2, y), line, font=header_font, fill=(120, 200, 255), anchor="ma")
        y += 13
    draw.text((base.SCREEN_W // 2, y), "Rexius55", font=body_font, fill=(220, 220, 220), anchor="ma")
    y += 13

    draw.text((base.SCREEN_W // 2, y), "Music", font=header_font, fill=(120, 200, 255), anchor="ma")
    y += 13

    for line in base.wrap_text(draw, base.MUSIC_CREDITS, body_font, base.SCREEN_W - 12):
        draw.text((base.SCREEN_W // 2, y), line, font=body_font, fill=(220, 220, 220), anchor="ma")
        y += 9

    y = base.SCREEN_H - 12
    draw.text((base.SCREEN_W // 2, y), "PRESS START", font=body_font, fill=(160, 160, 160), anchor="ma")

    return img


if __name__ == "__main__":
    base.main(render_credits_image)
