#!/usr/bin/env python3
"""Draw the live Claude Code session as a terminal, and feed it to the emulator camera.

Not a screen grab. The session may have been started from a phone, from the web, or
from a terminal that is not on this display at all — so the screen is reconstructed
from the transcript instead of captured from a window.
"""
import glob, json, os, subprocess, sys, time, unicodedata
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTCollection, TTFont

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(HOME, "state")
PROJECTS = os.path.expanduser("~/.claude/projects")

# setlog captures in landscape ("rotate to capture"). Re-measured 2026-09-15 with the
# device tilted via the accelerometer: the Log comes out upright and keeps the TOP
# 16:9 band of the source (1710x962). So the terminal is drawn landscape and scaled
# up into that band. Portrait mode keeps the original upright layout.
LANDSCAPE = os.environ.get("SETLOG_ORIENT", "landscape") == "landscape"
W, H = (1280, 720) if LANDSCAPE else (720, 1280)   # content area, before scaling
# desktop = editor + terminal + mouse, drawn like a screen recording (bin/desktop.py);
# terminal = the Claude Code terminal alone, filling the frame.
SCENE = os.environ.get("SETLOG_SCENE", "desktop")
SRC_W = 1710              # full source frame (4:3 sensor the emulator expects)
SRC_H = 1280
CELL, LINE = 13, 30
PAD_X, TOP = 24, 64
COLS = (W - 2 * PAD_X) // CELL

BG, FG = (14, 14, 16), (232, 230, 227)
DIM, ACCENT, GREEN, BLUE = (122, 122, 128), (217, 119, 87), (126, 186, 124), (122, 162, 208)

DEJA = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
# JetBrains Mono wherever it is installed (SETLOG_MONO_FONT picks another), else DejaVu.
MONO = os.environ.get("SETLOG_MONO_FONT") or next(
    (p for pat in ("~/.local/share/fonts/**/JetBrainsMono*-Regular.ttf",
                   "/usr/share/fonts/**/JetBrainsMono*-Regular.ttf")
     for p in sorted(glob.glob(os.path.expanduser(pat), recursive=True))), DEJA)
CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-{}.ttc"
SPINNER = "✻✢✳✶✻✽"
# No single face here covers the box-drawing and marker glyphs, so each character
# is routed to the first font whose cmap actually contains it. U+23FA (Claude
# Code's ⏺) is in none of them; ● stands in for it.
DOT = "●"


def _cmap(path):
    f = TTCollection(path).fonts[0] if path.endswith(".ttc") else TTFont(path, fontNumber=0)
    return set(f.getBestCmap())


def fonts():
    return {
        "mono": ImageFont.truetype(MONO, 21),
        "deja": ImageFont.truetype(DEJA, 21),
        "cjk": ImageFont.truetype(CJK.format("Regular"), 25),
        "cjk_s": ImageFont.truetype(CJK.format("Regular"), 20),
        "_mono": _cmap(MONO),
        "_deja": _cmap(DEJA),
    }


def wide(ch):
    return unicodedata.east_asian_width(ch) in ("W", "F")


# ---------------------------------------------------------------- transcript

MOOD_SENTINEL = "SETLOG_MOOD_CALL"


def _is_own_subsession(path):
    """Skip transcripts produced by bin/mood.py, or the feed films itself."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for _ in range(4):
                line = fh.readline()
                if not line:
                    break
                if MOOD_SENTINEL in line:
                    return True
    except OSError:
        pass
    return False


def latest_transcript(pattern, wait=30):
    # Set by bin/on-prompt.sh: film the session the user just spoke to, not merely
    # whichever one was written last. On a session's first prompt the hook fires
    # before the file exists, so give it a moment; but never fall back to another
    # session's file, which would put someone else's conversation in the Log.
    pinned = os.environ.get("SETLOG_TRANSCRIPT")
    if pinned:
        deadline = time.time() + wait
        while not os.path.isfile(pinned):
            if time.time() > deadline:
                return None
            time.sleep(1)
        return pinned
    files = glob.glob(os.path.join(PROJECTS, pattern, "*.jsonl"))
    for path in sorted(files, key=os.path.getmtime, reverse=True):
        if not _is_own_subsession(path):
            return path
    return None


def session_model(path):
    """The model the session last answered with, for the terminal header."""
    import re
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            tail = fh.readlines()[-200:]
    except OSError:
        return "claude"
    for line in reversed(tail):
        m = re.search(r'"model"\s*:\s*"(claude-[^"]+)"', line)
        if m:
            return m.group(1)
    return "claude"


def blocks(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def strip(text, limit=400):
    text = " ".join(text.split())
    return text[:limit]


def tool_line(b):
    name = b.get("name", "?")
    inp = b.get("input") or {}
    if name == "Bash":
        return f"{name}({strip(inp.get('command', ''), 90)})"
    for key in ("file_path", "path", "pattern", "query", "url", "prompt"):
        if inp.get(key):
            return f"{name}({os.path.basename(str(inp[key]))[:70]})"
    return f"{name}()"


def read_session(path, keep=60):
    """-> (list of (kind, text), running) where kind styles the line."""
    entries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

    out, pending = [], set()
    for e in entries[-keep:]:
        msg = e.get("message") or {}
        role = msg.get("role")
        bs = blocks(msg)
        if role == "user":
            results = [b for b in bs if b.get("type") == "tool_result"]
            for b in results:
                pending.discard(b.get("tool_use_id"))
                c = b.get("content")
                if isinstance(c, list):
                    c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                out.append(("result", strip(str(c or ""), 160)))
            if not results:
                for b in bs:
                    if b.get("type") == "text" and b.get("text", "").strip():
                        out.append(("user", strip(b["text"], 300)))
        elif role == "assistant":
            for b in bs:
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append(("say", strip(b["text"], 300)))
                elif b.get("type") == "tool_use":
                    out.append(("tool", tool_line(b)))
                    pending.add(b.get("id"))
    return out, bool(pending)


# ---------------------------------------------------------------- layout

def wrap_cells(text, width):
    lines, cur, used = [], "", 0
    for ch in text:
        w = 2 if wide(ch) else 1
        if used + w > width:
            lines.append(cur)
            cur, used = "", 0
        cur += ch
        used += w
    if cur:
        lines.append(cur)
    return lines or [""]


PREFIX = {"user": ("> ", DIM), "say": (DOT + " ", FG), "tool": (DOT + " ", GREEN),
          "result": ("  ⎿  ", DIM)}
COLOR = {"user": FG, "say": FG, "tool": BLUE, "result": DIM}


def layout(events, rows, cols=COLS):
    """-> list of (cells, colour) ready to draw, cropped to the last `rows` lines."""
    out = []
    for kind, text in events:
        mark, mark_col = PREFIX[kind]
        body_w = cols - len(mark)
        for i, part in enumerate(wrap_cells(text, body_w)):
            head = mark if i == 0 else " " * len(mark)
            out.append((head, mark_col, part, COLOR[kind]))
        if kind in ("say", "result"):
            out.append(("", FG, "", FG))
    return out[-rows:]


# ---------------------------------------------------------------- drawing

def pick(f, ch, w):
    o = ord(ch)
    if o in f["_mono"]:
        return f["mono"], 0
    if o in f["_deja"]:
        return f["deja"], 0
    return (f["cjk"], -4) if w == 2 else (f["cjk_s"], -1)


def put(draw, f, x, y, text, colour):
    for ch in text:
        w = 2 if wide(ch) else 1
        if ch != " ":
            font, dy = pick(f, ch, w)
            off = max(0, (w * CELL - int(font.getlength(ch))) // 2)
            draw.text((x + off, y + dy), ch, font=font, fill=colour)
        x += CELL * w
    return x


def base_frame(f, lines, header):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    put(d, f, PAD_X, 22, header, DIM)
    d.line([(PAD_X, 52), (W - PAD_X, 52)], fill=(38, 38, 42), width=1)
    y = TOP
    for head, hcol, body, bcol in lines:
        x = put(d, f, PAD_X, y, head, hcol)
        put(d, f, x, y, body, bcol)
        y += LINE
    return img, y


def prompt_box(d, f, y):
    d.rounded_rectangle([PAD_X, y, W - PAD_X, y + 62], radius=8,
                        outline=(58, 58, 64), width=1)
    put(d, f, PAD_X + 16, y + 18, "> ", ACCENT)


# ---------------------------------------------------------------- main

def build(path, frames, fps):
    if LANDSCAPE and SCENE == "desktop":
        import desktop
        return desktop.build(path, frames, fps)
    f = fonts()
    events, running = read_session(path)
    project = os.path.basename(os.path.dirname(path)).lstrip("-").replace("-", "/")
    header = f"{project}  ·  {session_model(path)}"

    rows = (H - TOP - 190) // LINE
    lines = layout(events, rows)
    base, _ = base_frame(f, lines, header)
    y_box = H - 96          # prompt box is pinned to the bottom, like the real thing
    y_spin = y_box - 46

    out = []
    for i in range(frames):
        img = base.copy()
        d = ImageDraw.Draw(img)
        if running:
            spin = SPINNER[(i // 2) % len(SPINNER)]
            secs = int(i / fps)
            x = put(d, f, PAD_X, y_spin, spin + " ", ACCENT)
            put(d, f, x, y_spin, f"Working… ({secs}s)", DIM)
        prompt_box(d, f, y_box)
        if i % 8 < 5:
            d.rectangle([PAD_X + 16 + CELL * 2, y_box + 18,
                         PAD_X + 16 + CELL * 3 - 2, y_box + 18 + 22], fill=FG)
        out.append(img.resize((SRC_W, 962), Image.LANCZOS) if LANDSCAPE else img)
    return out


def encode(images, fps, dest):
    tmp = os.path.join(STATE, f".card.next.{os.getpid()}.mp4")
    w, h = images[0].size
    p = subprocess.Popen(   # raw frames: PNG-encoding 64 full frames was the slow part
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-framerate", str(fps),
         "-i", "-", "-vf", f"pad={SRC_W}:{SRC_H}:0:0:color=0x0e0e10", "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-g", "12", tmp],
        stdin=subprocess.PIPE)
    for im in images:
        p.stdin.write(im.convert("RGB").tobytes())
    p.stdin.close()
    if p.wait() != 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    os.replace(tmp, dest)
    # Selfie apps mirror the front camera, which makes text unreadable. Keep a
    # pre-flipped copy so the front feed still reads correctly once mirrored.
    mtmp = os.path.join(STATE, f".front.next.{os.getpid()}.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", dest, "-vf", "hflip",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast", mtmp])
    if r.returncode == 0:
        os.replace(mtmp, os.path.join(STATE, "card_front.mp4"))
    return True


def main():
    pattern = os.environ.get("SETLOG_PROJECT", "*")   # "*" = whichever session is
    # most recently active, so it follows you whether you gave the instruction from
    # a phone, the web, or a terminal on another machine.
    fps, seconds = 8, 8
    once = "--once" in sys.argv
    while True:
        path = latest_transcript(pattern)
        ok = bool(path) and encode(build(path, fps * seconds, fps), fps,
                                   os.path.join(STATE, "card.mp4"))
        if once:
            # A failed encode leaves the previous card.mp4 in place; say so, or the
            # caller would film last time's screen under this time's caption.
            if not ok:
                print("no transcript to draw" if not path else "ffmpeg failed; card.mp4 not updated",
                      file=sys.stderr)
            sys.exit(0 if ok else 1)
        time.sleep(2)


if __name__ == "__main__":
    main()
