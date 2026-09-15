#!/usr/bin/env python3
"""state/thought.json -> state/caption.png, a translucent strip for the screencast."""
import json, os
from PIL import Image, ImageDraw, ImageFont

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(HOME, "state")
W = 720
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-{}.ttc"


def wrap(draw, text, f, width):
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=f) > width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def main():
    with open(os.path.join(STATE, "thought.json"), encoding="utf-8") as fh:
        t = json.load(fh)
    f_body = ImageFont.truetype(FONT.format("Medium"), 26)
    f_meta = ImageFont.truetype(FONT.format("Regular"), 20)

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = wrap(probe, t.get("summary", ""), f_body, W - 72)[:3]
    h = 40 + 36 * len(lines) + 34

    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([16, 0, W - 16, h - 16], radius=14, fill=(12, 12, 14, 205))
    y = 18
    for ln in lines:
        d.text((40, y), ln, font=f_body, fill=(238, 238, 234, 255))
        y += 36
    d.text((40, y + 2), f"{t.get('time','')}   {t.get('model','')}", font=f_meta,
           fill=(150, 150, 156, 255))
    tmp = os.path.join(STATE, ".caption.next.png")
    img.save(tmp)
    os.replace(tmp, os.path.join(STATE, "caption.png"))


if __name__ == "__main__":
    main()
