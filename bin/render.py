#!/usr/bin/env python3
"""state/thought.json -> state/card.png / card.mp4 (emulator camera feed)."""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(HOME, "state")
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-{}.ttc"
W, H = 960, 1280   # content canvas (what must survive the crop)
BG, FG, DIM, ACCENT = (14, 14, 16), (240, 240, 238), (120, 120, 126), (208, 122, 74)


def font(weight, size, index=0):
    return ImageFont.truetype(FONT.format(weight), size, index=index)


def wrap(draw, text, f, width):
    """Character-wise wrap; CJK has no spaces to break on."""
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=f) > width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def render(t):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    pad = 84

    f_meta, f_body, f_step = font("Medium", 30), font("Bold", 66), font("Regular", 27)

    d.text((pad, pad), t.get("time", ""), font=f_meta, fill=DIM)
    label = t.get("model", "claude")
    d.text((W - pad - d.textlength(label, font=f_meta), pad), label, font=f_meta, fill=DIM)
    d.line([(pad, pad + 54), (W - pad, pad + 54)], fill=(40, 40, 44), width=2)

    # instruction being worked on
    y = pad + 112
    if t.get("instruction"):
        d.text((pad, y), "指令", font=f_step, fill=ACCENT)
        y += 40
        for ln in wrap(d, t["instruction"], f_step, W - 2 * pad)[:3]:
            d.text((pad, y), ln, font=f_step, fill=DIM)
            y += 38
        y += 48

    # the thought itself
    body = t.get("summary") or "…"
    lines = wrap(d, body, f_body, W - 2 * pad)[:8]
    for ln in lines:
        d.text((pad, y), ln, font=f_body, fill=FG)
        y += 92

    # trail of what it actually did
    steps = t.get("steps", [])[-6:]
    if steps:
        y = H - pad - 46 * len(steps) - 40
        d.line([(pad, y - 44), (W - pad, y - 44)], fill=(40, 40, 44), width=2)
        for s in steps:
            d.text((pad, y), "· " + wrap(d, s, f_step, W - 2 * pad - 40)[0], font=f_step, fill=DIM)
            y += 46
    return img


def compose(card):
    """The emulator's camera only shows a left-anchored, vertically-centred window
    of the source frame. Pad the card out so that window lands exactly on it."""
    with open(os.path.join(STATE, "geometry.json"), encoding="utf-8") as fh:
        g = json.load(fh)
    frac = g["visible_fraction"]
    src_w = int(round(card.width / frac)) // 2 * 2   # x264 needs even dimensions
    src_h = card.height
    frame = Image.new("RGB", (src_w, src_h), BG)
    frame.paste(card, (0, (src_h - card.height) // 2))
    return frame


def main():
    with open(os.path.join(STATE, "thought.json"), encoding="utf-8") as fh:
        t = json.load(fh)
    card = render(t)
    card.save(os.path.join(STATE, "card.png"))
    src = os.path.join(STATE, "frame.png")
    compose(card).save(src)
    mp4 = os.path.join(STATE, "card.mp4")
    tmp = mp4 + ".tmp.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", src, "-t", "12",
         "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "libx264", tmp],
        check=True,
    )
    os.replace(tmp, mp4)   # atomic: the emulator may open this file at any moment
    print(mp4)


if __name__ == "__main__":
    main()
