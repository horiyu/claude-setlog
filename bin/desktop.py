#!/usr/bin/env python3
"""Draw a whole desktop so the Log reads as a screen recording of the PC: the Claude
Code terminal in front, and behind it the windows the conversation called for (an
editor, a browser, an image viewer, a system monitor, a file manager). A mouse
cursor wanders between them along a different random path every time.

Nothing is captured and no desktop is started: it is all drawn from the transcript.
Sessions with no visible window (phone, web) render the same way, and nothing else
on the real desktop can leak in. The only real-world readings are the system
monitor's CPU / memory / GPU figures, taken from this PC at render time.
"""
import datetime, getpass, json, math, os, random, re, subprocess, time
from urllib.parse import quote, urlparse

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound

from feed import (ACCENT, BG, CELL, CJK, DIM, FG, SPINNER, SRC_W,
                  fonts, layout, put, read_session, session_model, wide)

USER = os.environ.get("SETLOG_USER") or getpass.getuser()   # the name the apps greet

DW, DH = SRC_W, 962            # the band setlog keeps in landscape; drawn 1:1
BAR, TITLE, STATUS = 34, 38, 26
EL, TL = 26, 27                # line heights: editor, terminal

WALL = ((38, 10, 52), (119, 33, 111), (233, 84, 32))
ED_BG, SIDE_BG, ACT_BG = (30, 30, 30), (37, 37, 38), (51, 51, 55)
ED_FG = (212, 212, 212)
PALETTE = {                    # roughly VS Code Dark+
    Token.Comment: (106, 153, 85),
    Token.Keyword: (197, 134, 192),
    Token.Keyword.Constant: (86, 156, 214),
    Token.Operator.Word: (197, 134, 192),
    Token.Name.Builtin: (86, 156, 214),
    Token.Name.Function: (220, 220, 170),
    Token.Name.Class: (78, 201, 176),
    Token.Name.Decorator: (220, 220, 170),
    Token.Name: (156, 220, 254),
    Token.Literal.String: (206, 145, 120),
    Token.Literal.Number: (181, 206, 168),
    Token.Generic.Heading: (86, 156, 214),
    Token.Generic.Subheading: (86, 156, 214),
}

# Never put these on screen: the windows show real file contents.
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".mp4", ".mov", ".zip",
            ".ttf", ".ttc", ".pyc", ".bin", ".so"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SECRET = (".env", "secret", "token", "credential", "id_rsa", ".pem", ".key", "password")

# Which conversation calls for which window.
SYS_CMD = re.compile(r"\b(lscpu|nproc|free|nvidia-smi|top|htop|ps|df|du|sensors|uptime|"
                     r"vmstat|lsblk|lspci|inxi|neofetch|fastfetch)\b")
LS_CMD = re.compile(r"^\s*(?:cd \S+ *(?:&&|;) *)?(ls|tree|find)\b")
# MCP tools, by a substring of their name -> the app window drawn for them. The apps
# are pictures only: their look is imitated, their content comes from the transcript.
APPS = ("slack", "notion", "gmail", "google_calendar", "google_drive", "figma")

ARROW = [(0, 0), (0, 27), (7, 21), (12, 32), (17, 30), (12, 19), (21, 19)]


# ---------------------------------------------------------------- what to show

def _safe_name(fp):
    base = os.path.basename(fp).lower()
    if any(h in base for h in SECRET):
        return False
    # Claude's own memory and settings are notes about the user, not the work.
    return not os.path.abspath(fp).startswith(os.path.expanduser("~/.claude") + os.sep)


# Set by build() for a transcript sent from another machine (bin/on-remote.sh): the
# files Claude touched there arrive unpacked under REMOTE_ROOT + their original path.
REMOTE_ROOT = None


def _local(fp):
    if REMOTE_ROOT and fp and not os.path.exists(fp):
        cand = REMOTE_ROOT + fp
        if os.path.exists(cand):
            return cand
    return fp


def showable(fp):
    if os.path.splitext(fp)[1].lower() in SKIP_EXT or not _safe_name(fp):
        return False
    try:
        lf = _local(fp)
        return os.path.isfile(lf) and os.path.getsize(lf) < 2_000_000
    except OSError:
        return False


def viewable_image(fp):
    try:
        lf = _local(fp)
        return _safe_name(fp) and os.path.isfile(lf) and os.path.getsize(lf) < 30_000_000
    except OSError:
        return False


def _listed_dir(cmd, cwd):
    for tok in cmd.replace("&&", " ").replace(";", " ").split()[1:]:
        if tok.startswith("-") or tok in ("ls", "tree", "find", "cd"):
            continue
        p = os.path.expanduser(tok.strip("'\""))
        p = p if os.path.isabs(p) else os.path.join(cwd or "~", p)
        if os.path.isdir(p):
            return p
    return cwd


def scan(path):
    """Walk the transcript once -> (cwd, {window kind: (recency, data)})."""
    cwd, results, uses = None, {}, []
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            try:
                e = json.loads(raw)
            except ValueError:
                continue
            cwd = e.get("cwd") or cwd
            c = (e.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    uses.append(b)
                elif b.get("type") == "tool_result":
                    r = b.get("content")
                    if isinstance(r, list):
                        r = " ".join(x.get("text", "") for x in r if isinstance(x, dict))
                    results[b.get("tool_use_id")] = str(r or "")

    found = {}
    for i, b in enumerate(uses):
        name, inp = b.get("name", ""), b.get("input") or {}
        res = results.get(b.get("id"), "")
        kind = data = None
        fp = inp.get("file_path")
        if name in ("Edit", "MultiEdit", "Write", "Read") and fp:
            if os.path.splitext(fp)[1].lower() in IMAGE_EXT:
                if viewable_image(fp):
                    kind, data = "image", {"path": fp}
            elif showable(fp):
                needle = inp.get("new_string") if name == "Edit" else None
                if name == "MultiEdit" and inp.get("edits"):
                    needle = inp["edits"][-1].get("new_string")
                kind, data = "editor", {"path": fp, "needle": needle,
                                        "hint": inp.get("offset") if name == "Read" else None}
        elif name == "WebFetch" and inp.get("url"):
            u = urlparse(inp["url"])
            kind, data = "browser", {"url": inp["url"], "site": u.netloc,
                                     "title": (u.netloc + u.path)[:60], "body": res}
        elif name == "WebSearch" and inp.get("query"):
            kind, data = "search", {"query": inp["query"], "result": res}
        elif name.startswith("mcp__"):
            app = next((k for k in APPS if k in name.lower()), None)
            if app:                                 # keep a little history per app
                hist = found.get(app, (0, {"history": []}))[1]["history"]
                kind, data = app, {"history": (hist + [(name.lower(), inp, res)])[-8:]}
        elif name == "Bash":
            cmd = inp.get("command", "")
            if SYS_CMD.search(cmd):
                kind, data = "monitor", {"cmd": cmd}
            elif LS_CMD.search(cmd):
                kind, data = "files", {"dir": _listed_dir(cmd, cwd)}
        elif name in ("Glob", "LS"):
            kind, data = "files", {"dir": inp.get("path") or cwd}
        if kind and data:
            found[kind] = (i, data)
    return cwd, found


# ---------------------------------------------------------------- drawing helpers

def ui_font(size):
    return ImageFont.truetype(CJK.format("Regular"), size)


def text_w(font, s):
    return int(font.getlength(s))


def wrap_px(text, font, width, max_lines):
    lines, cur, w = [], "", 0.0
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur, w = "", 0.0
        else:
            cw = font.getlength(ch)
            if w + cw > width:
                lines.append(cur)
                cur, w = "", 0.0
            cur += ch
            w += cw
        if len(lines) >= max_lines:
            return lines
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def plain(md):
    """Markdown / tool output -> readable page text. Only markup is removed, so
    identifiers such as #prj_setlog or snake_case survive."""
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"(?m)^\s*#{1,6}\s+", "", md)            # headings
    md = re.sub(r"(?m)^\s*>\s?", "", md)                 # quotes
    md = re.sub(r"\*\*|`+", "", md)                      # bold, code
    md = re.sub(r"(?m)^[\s|:\-]+$", "", md)              # table rules
    md = re.sub(r"\s*\|\s*", "  ", md)                   # table cells
    md = re.sub(r"[ \t]+", " ", md)
    return re.sub(r"\n\s*\n+", "\n", md).strip()


def wallpaper():
    g = Image.linear_gradient("L").resize((DW, DH))
    return ImageOps.colorize(g, WALL[0], WALL[2], mid=WALL[1]).convert("RGB")


def topbar(img, ui):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, DW, BAR], fill=(12, 12, 14))
    fg = (230, 230, 230)
    # setlog trims a few percent off each side of the Log, so keep clear of the edges.
    d.text((64, 6), "Activities", font=ui, fill=fg)
    now = datetime.datetime.now()
    s = f"{now.month}月{now.day}日  {now:%H:%M}"
    d.text(((DW - text_w(ui, s)) // 2, 6), s, font=ui, fill=fg)
    x = DW - 200
    d.text((x, 6), "ja", font=ui, fill=fg)
    d.polygon([(x + 40, 13), (x + 46, 13), (x + 53, 7), (x + 53, 27), (x + 46, 21), (x + 40, 21)],
              fill=fg)
    d.rounded_rectangle([x + 75, 10, x + 105, 24], 3, outline=fg, width=2)
    d.rectangle([x + 78, 13, x + 98, 21], fill=fg)
    d.rectangle([x + 106, 14, x + 109, 20], fill=fg)
    d.arc([x + 120, 9, x + 136, 25], 300, 240, fill=fg, width=2)
    d.line([(x + 128, 6), (x + 128, 15)], fill=fg, width=2)


def window(img, box, title, ui, focused, body):
    x0, y0, x1, y1 = box
    sh = Image.new("L", img.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 4, y0 + 10, x1 + 4, y1 + 16], 14,
                                         fill=170 if focused else 120)
    img.paste((0, 0, 0), (0, 0, DW, DH), sh.filter(ImageFilter.GaussianBlur(16)))
    d = ImageDraw.Draw(img)
    bar = (46, 46, 50) if focused else (36, 36, 38)
    d.rounded_rectangle(box, 10, fill=body)
    d.rounded_rectangle([x0, y0, x1, y0 + TITLE], 10, fill=bar)
    d.rectangle([x0, y0 + TITLE - 10, x1, y0 + TITLE], fill=bar)
    tc = (230, 230, 230) if focused else (140, 140, 146)
    title = title if text_w(ui, title) < (x1 - x0 - 200) else title[:40] + "…"
    d.text(((x0 + x1 - text_w(ui, title)) // 2, y0 + 8), title, font=ui, fill=tc)
    cx, cy = x1 - 24, y0 + TITLE // 2          # close, maximise, minimise (GNOME order)
    d.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=(70, 70, 74) if focused else (52, 52, 56))
    d.line([(cx - 4, cy - 4), (cx + 4, cy + 4)], fill=tc, width=2)
    d.line([(cx - 4, cy + 4), (cx + 4, cy - 4)], fill=tc, width=2)
    d.rectangle([cx - 41, cy - 5, cx - 31, cy + 5], outline=tc, width=2)
    d.line([(cx - 76, cy + 4), (cx - 66, cy + 4)], fill=tc, width=2)
    d.rounded_rectangle(box, 10, outline=(80, 80, 86) if focused else (58, 58, 62), width=1)
    return d


# ---------------------------------------------------------------- editor

def code_view(fp, needle, hint, rows):
    """-> (lines, first visible index, lines to mark as just written, focus line)."""
    try:
        with open(_local(fp), encoding="utf-8", errors="replace") as fh:
            text = fh.read().expandtabs(4)
    except OSError:
        return [], 0, set(), 0
    lines = text.split("\n")
    focus, marked = 0, set()
    if needle:
        i = text.find(needle.expandtabs(4))
        if i >= 0:
            focus = text.count("\n", 0, i)
            marked = set(range(focus, focus + needle.count("\n") + 1))
    elif hint:
        focus = max(0, int(hint) - 1)
    # Keep the focus near the top: the lower part of a window tends to sit behind others.
    start = max(0, min(focus - 3, len(lines) - rows))
    return lines, start, marked, focus


def colour_of(ttype):
    while ttype is not Token:
        if ttype in PALETTE:
            return PALETTE[ttype]
        ttype = ttype.parent
    return ED_FG


def lex_lines(fp, lines):
    try:
        lexer = get_lexer_for_filename(fp, stripnl=False, ensurenl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False, ensurenl=False)
    out = [[]]
    for ttype, val in lexer.get_tokens("\n".join(lines)):
        col = colour_of(ttype)
        for k, part in enumerate(val.split("\n")):
            if k:
                out.append([])
            if part:
                out[-1].append((part, col))
    return out, lexer.name


def clip(segs, maxcells):
    out, used = [], 0
    for text, col in segs:
        keep = ""
        for ch in text:
            w = 2 if wide(ch) else 1
            if used + w > maxcells:
                break
            keep += ch
            used += w
        if keep:
            out.append((keep, col))
        if keep != text:
            break
    return out


def explorer_rows(root, fp, maxrows):
    """Real listing of the project, with the folders down to the open file expanded."""
    rows = []
    parts = os.path.relpath(fp, root).split(os.sep) if fp else []
    if parts and parts[0] == "..":
        parts = []

    def walk(d, depth, parts):
        try:
            ld = _local(d)
            names = sorted(os.listdir(ld),
                           key=lambda n: (not os.path.isdir(os.path.join(ld, n)), n.lower()))
        except OSError:
            return
        for n in names:
            if len(rows) >= maxrows:
                return
            if n.startswith(".") or n == "__pycache__":
                continue
            p = os.path.join(d, n)
            isdir = os.path.isdir(_local(p))
            is_open = isdir and bool(parts) and n == parts[0]
            active = bool(fp) and os.path.abspath(p) == os.path.abspath(fp)
            rows.append((depth, n, isdir, is_open, active))
            if is_open:
                walk(p, depth + 1, parts[1:])

    walk(root, 0, parts)
    return rows


def editor(img, box, f, ui, data, cwd, focused=False):
    """-> points of interest for the mouse."""
    x0, y0, x1, y1 = box
    fp = (data or {}).get("path")
    name = os.path.basename(fp) if fp else "Welcome"
    under_cwd = cwd and fp and os.path.abspath(fp).startswith(os.path.abspath(cwd) + os.sep)
    root = cwd if under_cwd else (os.path.dirname(fp) if fp else cwd)
    proj = os.path.basename(root) if root else ""
    d = window(img, box, f"{name} — {proj} — Code" if proj else f"{name} — Code", ui, focused, ED_BG)
    top, bottom = y0 + TITLE, y1 - STATUS
    small = ui_font(14)
    pois = []

    d.rectangle([x0, top, x0 + 48, bottom], fill=ACT_BG)             # activity bar
    for k in range(4):
        yy = top + 16 + k * 52
        d.rounded_rectangle([x0 + 13, yy, x0 + 35, yy + 22], 4,
                            outline=(200, 200, 200) if k == 0 else (120, 120, 124), width=2)
    d.rectangle([x0, top + 10, x0 + 2, top + 44], fill=(230, 230, 230))

    sx0 = sx1 = x0 + 48
    if x1 - x0 >= 900 and root:                                      # explorer
        sx1 = x0 + 288
        d.rectangle([sx0, top, sx1, bottom], fill=SIDE_BG)
        d.text((sx0 + 16, top + 10), "EXPLORER", font=small, fill=(170, 170, 170))
        d.text((sx0 + 16, top + 38), proj.upper(), font=small, fill=(225, 225, 225))
        ry = top + 64
        for depth, n, isdir, is_open, active in explorer_rows(root, fp, (bottom - ry) // 24):
            if active:
                d.rectangle([sx0, ry - 2, sx1, ry + 21], fill=(55, 55, 61))
            ix = sx0 + 16 + depth * 14
            if isdir:
                tri = [(ix, ry + 6), (ix + 8, ry + 6), (ix + 4, ry + 12)] if is_open else \
                      [(ix + 2, ry + 4), (ix + 7, ry + 9), (ix + 2, ry + 14)]
                d.polygon(tri, fill=(190, 190, 190))
            d.text((ix + 16, ry), n[:24], font=small,
                   fill=(235, 235, 235) if active else (200, 200, 200))
            pois.append((ix + 40, ry + 10))
            ry += 24

    cx0 = sx1                                                        # tab
    d.rectangle([cx0, top, x1, top + 36], fill=SIDE_BG)
    tw = text_w(ui, name) + 56
    d.rectangle([cx0, top, cx0 + tw, top + 36], fill=ED_BG)
    d.line([(cx0, top), (cx0 + tw, top)], fill=(0, 122, 204), width=2)
    d.text((cx0 + 16, top + 7), name, font=ui, fill=(235, 235, 235))
    d.text((cx0 + tw - 26, top + 7), "×", font=ui, fill=(170, 170, 170))
    pois.append((cx0 + tw // 2, top + 18))

    gut, cy = cx0 + 64, top + 46                                     # code
    rows = (bottom - cy - 6) // EL
    focus, lang = 0, "Plain Text"
    if fp:
        lines, start, marked, focus = code_view(fp, data.get("needle"), data.get("hint"), rows)
        segs, lang = lex_lines(fp, lines[start:start + rows])
        maxc = (x1 - gut - 24) // CELL
        for k, line in enumerate(segs[:rows]):
            n, y = start + k, cy + k * EL
            if n in marked:
                d.rectangle([cx0, y - 3, x1 - 16, y + EL - 4], fill=(38, 58, 42))
            elif n == focus:
                d.rectangle([cx0, y - 3, x1 - 16, y + EL - 4], outline=(62, 62, 66))
            num = str(n + 1)
            put(d, f, gut - 18 - len(num) * CELL, y, num,
                (200, 200, 200) if n == focus else (110, 110, 116))
            x = gut
            for text, col in clip(line, maxc):
                x = put(d, f, x, y, text, col)
            if n == focus or n in marked:
                pois.append((min(x, gut + 380) + 16, y + 10))
        if len(lines) > rows:                                        # scrollbar
            th = max(30, (bottom - cy) * rows // len(lines))
            ty = cy + (bottom - cy - th) * start // (len(lines) - rows)
            d.rectangle([x1 - 12, ty, x1 - 4, ty + th], fill=(66, 66, 70))
            pois.append((x1 - 8, ty + th // 2))
    else:
        d.text((gut + 120, cy + 200), "ファイルを開いていません", font=ui, fill=(110, 110, 116))
        pois.append((gut + 200, cy + 210))

    d.rounded_rectangle([x0, bottom, x1, y1], 10, fill=(0, 122, 204))  # status bar
    d.rectangle([x0, bottom, x1, bottom + 12], fill=(0, 122, 204))
    status = f"Ln {focus + 1}, Col 1    Spaces: 4    UTF-8    LF    {lang}"
    d.text((sx0 + 16, bottom + 4), status, font=small, fill=(255, 255, 255))
    return pois, None


# ---------------------------------------------------------------- browser

def chrome(img, box, ui, title, url, focused):
    """A Chromium window with its toolbar -> (draw, top of the page, a point on the URL bar)."""
    x0, y0, x1, y1 = box
    d = window(img, box, f"{title} — Chromium", ui, focused, (255, 255, 255))
    top = y0 + TITLE
    small = ui_font(14)
    d.rectangle([x0, top, x1, top + 48], fill=(242, 242, 245))       # toolbar
    for k, glyph in enumerate("‹›"):
        d.text((x0 + 20 + k * 34, top + 11), glyph, font=ui, fill=(90, 90, 96))
    rx, ry = x0 + 94, top + 24                   # reload, drawn: no font here has ↻
    d.arc([rx - 8, ry - 8, rx + 8, ry + 8], 40, 330, fill=(90, 90, 96), width=2)
    d.polygon([(rx + 4, ry - 11), (rx + 10, ry - 5), (rx + 2, ry - 3)], fill=(90, 90, 96))
    ux0 = x0 + 128
    d.rounded_rectangle([ux0, top + 9, x1 - 60, top + 39], 15, fill=(255, 255, 255),
                        outline=(210, 210, 216))
    url = url if len(url) < 90 else url[:88] + "…"
    d.text((ux0 + 36, top + 14), url, font=small, fill=(60, 60, 66))
    d.ellipse([ux0 + 12, top + 18, ux0 + 24, top + 30], outline=(120, 120, 126), width=2)
    return d, top + 48, (ux0 + 180, top + 24)


def browser(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d, py, bar = chrome(img, box, ui, data["title"], data["url"], focused)
    small, body_f, head_f = ui_font(14), ui_font(16), ui_font(24)
    pois = [bar]
    body = plain(data.get("body") or "")
    head = data["title"]
    y = py + 22
    if head:
        for ln in wrap_px(head, head_f, x1 - x0 - 80, 2):
            d.text((x0 + 40, y), ln, font=head_f, fill=(26, 26, 30))
            y += 34
        d.text((x0 + 40, y), data["site"], font=small, fill=(24, 128, 56))
        y += 34
    lines = wrap_px(body, body_f, x1 - x0 - 90, max(1, (y1 - y - 20) // 26))
    for ln in lines:
        d.text((x0 + 40, y), ln, font=body_f, fill=(60, 60, 66))
        if ln.strip():
            pois.append((x0 + 40 + min(text_w(body_f, ln), 300) // 2, y + 10))
        y += 26
    return pois, None


# ---------------------------------------------------------------- apps (pictures only)

def bold_font(size):
    try:
        return ImageFont.truetype(CJK.format("Bold"), size)
    except OSError:
        return ui_font(size)


AVATAR = [(224, 30, 90), (46, 182, 125), (236, 178, 46), (54, 197, 240), (120, 90, 200),
          (230, 110, 60)]


def avatar(d, x, y, s, name, round_=False):
    col = AVATAR[sum(map(ord, name or "?")) % len(AVATAR)]
    if round_:
        d.ellipse([x, y, x + s, y + s], fill=col)
    else:
        d.rounded_rectangle([x, y, x + s, y + s], max(3, s // 5), fill=col)
    ch = (name or "?")[:1].upper()
    bf = bold_font(max(8, int(s * 0.5)))
    d.text((x + (s - text_w(bf, ch)) // 2, y + int(s * 0.12)), ch, font=bf, fill=(255, 255, 255))


def caret(d, x, y, col):
    d.polygon([(x, y + 5), (x + 8, y + 5), (x + 4, y + 11)], fill=col)


def doc_icon(d, x, y, w, h, col, width=1):
    """A page with lines on it (a bare rectangle reads as a missing glyph)."""
    d.rectangle([x, y, x + w, y + h], outline=col, width=width)
    for k in range(1, 4):
        yy = y + k * h // 4
        d.line([(x + w // 5, yy), (x + w - w // 5, yy)], fill=col, width=width)


def _fit(d, xy, text, font, width, fill):
    if width <= 10:
        return
    if text_w(font, text) > width:
        while text and text_w(font, text + "…") > width:
            text = text[:-1]
        text += "…"
    d.text(xy, text, font=font, fill=fill)


def _items(res, keys=("title", "name", "subject", "summary", "text", "message", "snippet",
                      "content")):
    """Readable strings out of a tool result: its fields if it is JSON, else its lines."""
    try:
        obj = json.loads(res)
    except (ValueError, TypeError):
        return [l.strip()[:160] for l in plain(res or "").split("\n") if l.strip()][:20]
    out = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in keys and isinstance(v, str) and v.strip():
                    out.append(" ".join(v.split())[:160])
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return out[:20]


def _said(inp, keys=("message", "text", "title", "summary", "subject", "query", "content",
                     "name")):
    for k in keys:
        v = inp.get(k)
        if isinstance(v, str) and v.strip():
            return " ".join(v.split())
    return ""


def _gathered(hist, inputs=True):
    """What an app window can show: what Claude wrote into it and what it read back.
    inputs=False keeps only what came back (a search query is not a mail or a file)."""
    out = []
    for tool, inp, res in hist:
        s = _said(inp) if inputs else ""
        if s:
            out.append(s[:160])
        out += _items(res)
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[-12:]


def _clock(minutes_ago):
    return (datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago)).strftime("%H:%M")


def _panel(d, box, x1, fill):
    """A side panel down the left of a window, with the window's rounded corner."""
    x0, top, y1 = box
    d.rectangle([x0, top, x1, y1 - 10], fill=fill)
    d.rounded_rectangle([x0, y1 - 20, x1, y1], 10, fill=fill)
    d.rectangle([x0 + 10, y1 - 20, x1, y1], fill=fill)


def slack(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d = window(img, box, "Slack", ui, focused, (255, 255, 255))
    top = y0 + TITLE
    small, body_f, name_f, head_f = ui_font(14), ui_font(15), bold_font(15), bold_font(18)
    msgs, chan = [], None
    for tool, inp, res in data["history"]:
        c = inp.get("channel_name") or inp.get("channel") or inp.get("channel_id")
        if isinstance(c, str) and c:
            chan = c.lstrip("#")
        if any(w in tool for w in ("send", "schedule", "draft")):
            t = _said(inp)
            if t:
                msgs.append(("Claude", t))
        else:
            for it in _items(res):
                m = re.match(r"^([^:：]{1,24})[:：]\s*(.+)", it)
                msgs.append((m.group(1).strip(), m.group(2)) if m else ("Slack", it))
    if not chan or re.fullmatch(r"[CDG][A-Z0-9]{6,}", chan):
        chan = "general"
    msgs = msgs[-6:] or [("Claude", "…")]

    d.rectangle([x0, top, x1, top + 40], fill=(53, 13, 54))                  # search bar
    mid = (x0 + x1) // 2
    d.rounded_rectangle([mid - 200, top + 7, mid + 200, top + 33], 6, fill=(96, 62, 97))
    d.text((mid - 180, top + 10), f"{USER} を検索", font=small, fill=(220, 205, 220))
    sx1 = x0 + min(250, (x1 - x0) // 3)                                    # sidebar
    _panel(d, (x0, top + 40, y1), sx1, (63, 14, 64))
    d.text((x0 + 18, top + 52), USER, font=head_f, fill=(255, 255, 255))
    y = top + 92
    for label in ("スレッド", "アクティビティ"):
        d.text((x0 + 22, y), label, font=small, fill=(207, 195, 207))
        y += 28
    y += 8
    caret(d, x0 + 18, y, (207, 195, 207))
    d.text((x0 + 32, y), "チャンネル", font=small, fill=(207, 195, 207))
    y += 30
    pois = []
    for c in dict.fromkeys(["general", "random", chan]):
        if c == chan:
            d.rounded_rectangle([x0 + 8, y - 4, sx1 - 8, y + 22], 6, fill=(18, 100, 163))
        _fit(d, (x0 + 22, y), f"# {c}", small, sx1 - x0 - 34,
             (255, 255, 255) if c == chan else (207, 195, 207))
        pois.append((x0 + 80, y + 9))
        y += 30
    y += 8
    caret(d, x0 + 18, y, (207, 195, 207))
    d.text((x0 + 32, y), "ダイレクトメッセージ", font=small, fill=(207, 195, 207))
    y += 30
    for who in ("Claude", USER):
        avatar(d, x0 + 22, y, 18, who)
        d.text((x0 + 48, y), who, font=small, fill=(207, 195, 207))
        y += 30

    mx0 = sx1 + 20                                                          # channel
    d.text((mx0, top + 52), f"# {chan}", font=head_f, fill=(29, 28, 29))
    d.line([(sx1, top + 90), (x1, top + 90)], fill=(221, 221, 221))
    pois.append((mx0 + 60, top + 62))
    comp_y = y1 - 90
    y = ytop = comp_y - 14                            # newest at the bottom, as in Slack
    for k, (who, text) in reversed(list(enumerate(msgs))):
        lines = wrap_px(text, body_f, x1 - mx0 - 80, 4)
        y -= 34 + 22 * len(lines)
        if y < top + 100:
            break
        ytop = y
        avatar(d, mx0, y + 2, 36, who)
        d.text((mx0 + 48, y), who, font=name_f, fill=(29, 28, 29))
        d.text((mx0 + 56 + text_w(name_f, who), y + 2), _clock(3 * (len(msgs) - k)),
               font=small, fill=(97, 96, 97))
        for j, ln in enumerate(lines):
            d.text((mx0 + 48, y + 24 + 22 * j), ln, font=body_f, fill=(29, 28, 29))
        pois.append((mx0 + 60 + min(200, text_w(body_f, lines[0]) // 2), y + 34))
    if ytop - top > 150:                              # date divider above the history
        dy, cx = ytop - 22, (mx0 + x1 - 20) // 2
        pw = text_w(small, "今日") + 24
        d.line([(mx0, dy), (x1 - 20, dy)], fill=(221, 221, 221))
        d.rounded_rectangle([cx - pw // 2, dy - 12, cx + pw // 2, dy + 12], 12,
                            fill=(255, 255, 255), outline=(221, 221, 221))
        d.text((cx - pw // 2 + 12, dy - 10), "今日", font=small, fill=(29, 28, 29))
    if ytop - top > 280:                              # short history: the channel's opening
        d.text((mx0, top + 112), f"# {chan}", font=bold_font(26), fill=(29, 28, 29))
        _fit(d, (mx0, top + 154), f"これは #{chan} チャンネルのいちばん最初です。", body_f,
             x1 - mx0 - 40, (97, 96, 97))
    d.rounded_rectangle([mx0, comp_y, x1 - 20, y1 - 22], 8, outline=(190, 190, 190), width=1)
    d.text((mx0 + 14, comp_y + 12), f"#{chan} へのメッセージ", font=body_f, fill=(150, 150, 150))
    for k in range(5):
        d.rounded_rectangle([mx0 + 14 + k * 30, y1 - 52, mx0 + 32 + k * 30, y1 - 34], 4,
                            outline=(170, 170, 170))
    pois.append((mx0 + 120, comp_y + 20))
    return pois, None


def notion(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d = window(img, box, "Notion", ui, focused, (255, 255, 255))
    top = y0 + TITLE
    small, body_f, title_f = ui_font(14), ui_font(16), bold_font(32)
    items = _gathered(data["history"])
    title = (items[0] if items else "無題")[:28]
    sx1 = x0 + min(240, (x1 - x0) // 3)
    _panel(d, (x0, top, y1), sx1, (247, 247, 245))
    avatar(d, x0 + 16, top + 14, 22, USER)
    _fit(d, (x0 + 46, top + 15), f"{USER} のワークスペース", small, sx1 - x0 - 56, (55, 53, 47))
    y = top + 52
    for label in ("検索", "ホーム", "受信トレイ"):
        d.text((x0 + 22, y), label, font=small, fill=(95, 94, 91))
        y += 28
    y += 12
    d.text((x0 + 18, y), "プライベート", font=ui_font(12), fill=(145, 145, 140))
    y += 26
    pois = []
    for k, p in enumerate([title] + [s[:24] for s in items[1:6]]):
        if k == 0:
            d.rounded_rectangle([x0 + 8, y - 4, sx1 - 8, y + 22], 4, fill=(234, 234, 232))
        doc_icon(d, x0 + 20, y + 3, 11, 14, (145, 145, 140))
        _fit(d, (x0 + 40, y), p, small, sx1 - x0 - 52, (55, 53, 47))
        pois.append((x0 + 90, y + 9))
        y += 28

    _fit(d, (sx1 + 16, top + 12), f"プライベート / {title}", small, x1 - sx1 - 140, (95, 94, 91))
    d.text((x1 - 80, top + 12), "共有", font=small, fill=(95, 94, 91))
    mx0 = sx1 + 60
    y = top + 70
    d.rounded_rectangle([mx0, y, mx0 + 56, y + 56], 10, fill=(235, 235, 232))
    doc_icon(d, mx0 + 16, y + 11, 24, 34, (140, 140, 135), width=2)
    y += 72
    for ln in wrap_px(title, title_f, x1 - mx0 - 60, 2):
        d.text((mx0, y), ln, font=title_f, fill=(55, 53, 47))
        y += 46
    pois.append((mx0 + 120, y - 24))
    y += 10
    for s in items[1:]:
        for j, ln in enumerate(wrap_px(s, body_f, x1 - mx0 - 80, 3)):
            if y > y1 - 40:
                break
            if j == 0:
                d.ellipse([mx0 + 4, y + 9, mx0 + 10, y + 15], fill=(55, 53, 47))
            d.text((mx0 + 22, y), ln, font=body_f, fill=(55, 53, 47))
            y += 26
        pois.append((mx0 + 100, y - 14))
        y += 6
    return pois, None


def gmail(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d, top, bar = chrome(img, box, ui, "受信トレイ - Gmail",
                         "https://mail.google.com/mail/u/0/#inbox", focused)
    small, row_f, bold = ui_font(14), ui_font(15), bold_font(15)
    _panel(d, (x0, top, y1), x1, (246, 248, 252))
    d.text((x0 + 24, top + 10), "M", font=bold_font(28), fill=(234, 67, 53))
    d.text((x0 + 58, top + 14), "Gmail", font=ui_font(21), fill=(95, 99, 104))
    sx1 = x0 + 230
    d.rounded_rectangle([x0 + 16, top + 62, x0 + 150, top + 112], 16, fill=(194, 231, 255))
    d.text((x0 + 58, top + 76), "作成", font=bold, fill=(0, 29, 53))
    pois = [bar, (x0 + 83, top + 87)]
    hist = data["history"]
    items = _gathered(hist, inputs=False) or _gathered(hist)
    q = next((i["query"] for _, i, _ in reversed(hist) if isinstance(i.get("query"), str)), "")
    y = top + 132
    for k, label in enumerate(("受信トレイ", "スター付き", "スヌーズ中", "送信済み", "下書き")):
        if k == 0:
            d.rounded_rectangle([x0 + 8, y - 5, sx1 - 10, y + 25], 15, fill=(211, 227, 253))
            d.text((sx1 - 44, y), str(max(1, len(items))), font=bold, fill=(32, 33, 36))
        d.text((x0 + 30, y), label, font=bold if k == 0 else row_f, fill=(32, 33, 36))
        y += 36
    mx0 = sx1
    d.rounded_rectangle([mx0 + 10, top + 10, x1 - 30, top + 50], 20, fill=(233, 238, 246))
    d.text((mx0 + 50, top + 19), q or "メールを検索", font=row_f,
           fill=(32, 33, 36) if q else (95, 99, 104))
    d.rounded_rectangle([mx0 + 10, top + 62, x1 - 16, y1 - 18], 14, fill=(255, 255, 255))
    y = top + 84
    senders = ["Google", "GitHub", "Slack", "Notion", "Amazon", "Tailscale"]
    for k, s in enumerate(items or ["（メールはありません）"]):
        if y > y1 - 60:
            break
        m = re.match(r"^([^:：]{1,24})[:：]\s*(.+)", s)
        sender, subj = (m.group(1), m.group(2)) if m else (senders[k % len(senders)], s)
        unread = k < 2
        d.rectangle([mx0 + 24, y + 4, mx0 + 38, y + 18], outline=(160, 160, 160))
        d.ellipse([mx0 + 50, y + 4, mx0 + 64, y + 18], outline=(160, 160, 160))
        _fit(d, (mx0 + 80, y), sender, bold if unread else row_f, 150, (32, 33, 36))
        _fit(d, (mx0 + 244, y), subj, bold if unread else row_f, x1 - mx0 - 350, (32, 33, 36))
        d.text((x1 - 80, y), _clock(20 * (k + 1)), font=bold if unread else small, fill=(32, 33, 36))
        d.line([(mx0 + 20, y + 30), (x1 - 26, y + 30)], fill=(238, 238, 238))
        pois.append((mx0 + 300, y + 10))
        y += 40
    return pois, None


def gcal(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d, top, bar = chrome(img, box, ui, "Google カレンダー",
                         "https://calendar.google.com/calendar/u/0/r/week", focused)
    small, bold, head = ui_font(13), bold_font(14), ui_font(22)
    now = datetime.datetime.now()
    d.text((x0 + 24, top + 12), "カレンダー", font=head, fill=(60, 64, 67))
    d.rounded_rectangle([x0 + 170, top + 14, x0 + 240, top + 44], 15, outline=(200, 200, 200))
    d.text((x0 + 190, top + 19), "今日", font=bold, fill=(60, 64, 67))
    d.text((x0 + 270, top + 12), f"{now.year}年 {now.month}月", font=head, fill=(60, 64, 67))
    pois = [bar, (x0 + 205, top + 29)]
    gx0, gy0 = x0 + 64, top + 124
    cw = (x1 - 20 - gx0) // 7
    monday = now - datetime.timedelta(days=now.weekday())
    for k in range(7):
        day, cx = monday + datetime.timedelta(days=k), gx0 + k * cw
        d.text((cx + cw // 2 - 7, top + 60), "月火水木金土日"[k], font=small, fill=(112, 117, 122))
        num = str(day.day)
        if day.date() == now.date():
            d.ellipse([cx + cw // 2 - 17, top + 80, cx + cw // 2 + 17, top + 114], fill=(26, 115, 232))
        d.text((cx + cw // 2 - text_w(head, num) // 2, top + 82), num, font=head,
               fill=(255, 255, 255) if day.date() == now.date() else (60, 64, 67))
    hours = list(range(8, 20))
    rh = max(30, (y1 - 20 - gy0) // len(hours))
    for j, h in enumerate(hours):
        yy = gy0 + j * rh
        if yy > y1 - 20:
            break
        d.line([(gx0, yy), (x1 - 20, yy)], fill=(230, 230, 230))
        d.text((x0 + 14, yy - 8), f"{h}:00", font=small, fill=(112, 117, 122))
    for k in range(8):
        d.line([(gx0 + k * cw, gy0), (gx0 + k * cw, y1 - 20)], fill=(230, 230, 230))
    palette = [(3, 155, 229), (51, 182, 121), (244, 81, 30), (142, 36, 170)]
    for k, s in enumerate((_gathered(data["history"]) or ["予定"])[:8]):
        h = sum(map(ord, s))
        ex0, ey0 = gx0 + (h % 5) * cw + 3, gy0 + (h % 9) * rh + 2
        ey1 = ey0 + rh * (1 + h % 2) - 4
        if ey1 > y1 - 22:
            continue
        d.rounded_rectangle([ex0, ey0, ex0 + cw - 8, ey1], 5, fill=palette[k % 4])
        _fit(d, (ex0 + 6, ey0 + 3), s, bold, cw - 20, (255, 255, 255))
        pois.append((ex0 + cw // 2, (ey0 + ey1) // 2))
    if 8 <= now.hour < 20:                                                  # "now" line
        ny, dx = gy0 + int((now.hour - 8 + now.minute / 60) * rh), gx0 + now.weekday() * cw
        if ny < y1 - 20:
            d.line([(dx, ny), (dx + cw, ny)], fill=(234, 67, 53), width=2)
            d.ellipse([dx - 5, ny - 5, dx + 5, ny + 5], fill=(234, 67, 53))
    return pois, None


def gdrive(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d, top, bar = chrome(img, box, ui, "マイドライブ - Google ドライブ",
                         "https://drive.google.com/drive/my-drive", focused)
    small, bold, head = ui_font(14), bold_font(15), ui_font(22)
    _panel(d, (x0, top, y1), x1, (248, 250, 253))
    d.polygon([(x0 + 22, top + 40), (x0 + 33, top + 20), (x0 + 44, top + 40)], fill=(15, 157, 88))
    d.polygon([(x0 + 33, top + 20), (x0 + 44, top + 40), (x0 + 50, top + 30)], fill=(244, 180, 0))
    d.text((x0 + 60, top + 14), "ドライブ", font=head, fill=(68, 71, 70))
    d.rounded_rectangle([x0 + 16, top + 62, x0 + 130, top + 110], 16, fill=(255, 255, 255),
                        outline=(220, 220, 220))
    d.text((x0 + 54, top + 75), "新規", font=bold, fill=(31, 31, 31))
    y = top + 130
    for k, label in enumerate(("ホーム", "マイドライブ", "共有アイテム", "最近使用したアイテム",
                               "スター付き", "ゴミ箱")):
        if k == 1:
            d.rounded_rectangle([x0 + 8, y - 5, x0 + 220, y + 25], 15, fill=(194, 231, 255))
        d.text((x0 + 30, y), label, font=bold if k == 1 else small, fill=(31, 31, 31))
        y += 34
    mx0 = x0 + 236
    d.rounded_rectangle([mx0, top + 10, x1 - 30, top + 50], 20, fill=(233, 238, 246))
    hist = data["history"]
    q = next((i["query"] for _, i, _ in reversed(hist) if isinstance(i.get("query"), str)), "")
    d.text((mx0 + 40, top + 19), q or "ドライブで検索", font=small,
           fill=(31, 31, 31) if q else (95, 99, 104))
    d.text((mx0 + 10, top + 66), "マイドライブ", font=head, fill=(31, 31, 31))
    kinds = [(66, 133, 244), (15, 157, 88), (244, 180, 0), (234, 67, 53)]
    cw, ch = 200, 180
    cols = max(1, (x1 - mx0 - 20) // (cw + 16))
    pois = [bar, (x0 + 73, top + 86)]
    names = _gathered(hist, inputs=False) or _gathered(hist) or ["無題のドキュメント"]
    for k, n in enumerate(names[:12]):
        cx, cy = mx0 + (k % cols) * (cw + 16), top + 112 + (k // cols) * (ch + 16)
        if cy + ch > y1 - 14:
            break
        d.rounded_rectangle([cx, cy, cx + cw, cy + ch], 12, fill=(255, 255, 255), outline=(225, 227, 230))
        d.rounded_rectangle([cx + 10, cy + 42, cx + cw - 10, cy + ch - 12], 6, fill=(241, 243, 244))
        for j in range(5):
            d.rectangle([cx + 24, cy + 56 + j * 16, cx + 24 + (cw - 48) * (1 - 0.12 * j), cy + 62 + j * 16],
                        fill=(214, 218, 222))
        d.rounded_rectangle([cx + 12, cy + 12, cx + 30, cy + 30], 4, fill=kinds[sum(map(ord, n)) % 4])
        _fit(d, (cx + 38, cy + 11), n, small, cw - 50, (31, 31, 31))
        pois.append((cx + cw // 2, cy + ch // 2))
    return pois, None


def figma(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d = window(img, box, "Figma", ui, focused, (44, 44, 44))
    top = y0 + TITLE
    small, bold = ui_font(13), bold_font(13)
    names = _gathered(data["history"]) or ["Frame 1"]
    for k in range(6):                                                     # toolbar
        d.rounded_rectangle([x0 + 14 + k * 38, top + 10, x0 + 38 + k * 38, top + 34], 5,
                            fill=(12, 140, 233) if k == 0 else (70, 70, 70))
    title = names[0][:30]
    d.text(((x0 + x1) // 2 - text_w(small, title) // 2, top + 13), title, font=small, fill=(230, 230, 230))
    d.rounded_rectangle([x1 - 90, top + 8, x1 - 20, top + 36], 6, fill=(12, 140, 233))
    d.text((x1 - 72, top + 12), "共有", font=bold, fill=(255, 255, 255))
    lx1, rx0 = x0 + 220, x1 - 220
    d.rectangle([lx1, top + 44, rx0, y1 - 10], fill=(229, 229, 229))          # canvas
    d.text((x0 + 14, top + 56), "レイヤー", font=bold, fill=(230, 230, 230))
    y, pois = top + 86, []
    frames = names[1:6] or names[:1]                # names[0] is the file's own name
    for k, n in enumerate(frames):
        if k == 1:
            d.rectangle([x0 + 1, y - 4, lx1, y + 20], fill=(12, 60, 110))
        d.rectangle([x0 + 16, y + 3, x0 + 26, y + 13], outline=(180, 180, 180))
        _fit(d, (x0 + 34, y), n, small, lx1 - x0 - 44, (230, 230, 230))
        pois.append((x0 + 90, y + 8))
        y += 26
    span = rx0 - lx1
    for k, n in enumerate(frames[:3]):
        fw = (span - 60) // 3 - 20
        fx0, fy0 = lx1 + 30 + k * (fw + 20), top + 110
        fh = min(y1 - 60 - fy0, int(fw * 1.7))
        _fit(d, (fx0, fy0 - 22), n, small, fw, (110, 110, 110))
        d.rectangle([fx0, fy0, fx0 + fw, fy0 + fh], fill=(255, 255, 255))
        d.rounded_rectangle([fx0 + 12, fy0 + 14, fx0 + fw - 12, fy0 + 60], 6, fill=AVATAR[k % 6])
        for j in range(4):
            d.rounded_rectangle([fx0 + 12, fy0 + 76 + j * 22,
                                 fx0 + 12 + int((fw - 24) * (0.9 - 0.15 * j)), fy0 + 88 + j * 22],
                                4, fill=(225, 225, 225))
        if k == 1:
            d.rectangle([fx0 - 2, fy0 - 2, fx0 + fw + 2, fy0 + fh + 2], outline=(12, 140, 233), width=2)
        pois.append((fx0 + fw // 2, fy0 + fh // 2))
    d.text((rx0 + 14, top + 56), "デザイン", font=bold, fill=(230, 230, 230))
    yy = top + 90
    for lab in ("X  120", "Y  64", "W  390", "H  844", "塗り  #FFFFFF", "角の半径  16"):
        d.text((rx0 + 16, yy), lab, font=small, fill=(200, 200, 200))
        yy += 30
    return pois, None


def search(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    q = data["query"]
    d, top, bar = chrome(img, box, ui, f"{q} - Google 検索",
                         "https://www.google.com/search?q=" + quote(q), focused)
    small, title_f, snip_f = ui_font(13), ui_font(20), ui_font(14)
    logo, x = bold_font(30), x0 + 30
    for ch, col in zip("Google", [(66, 133, 244), (234, 67, 53), (251, 188, 5), (66, 133, 244),
                                  (52, 168, 83), (234, 67, 53)]):
        d.text((x, top + 18), ch, font=logo, fill=col)
        x += text_w(logo, ch)
    sx0, sx1 = x + 30, min(x1 - 40, x + 650)
    d.rounded_rectangle([sx0, top + 18, sx1, top + 62], 22, fill=(255, 255, 255), outline=(223, 225, 229))
    _fit(d, (sx0 + 22, top + 29), q, snip_f, sx1 - sx0 - 60, (32, 33, 36))
    tx = sx0
    for k, t in enumerate(["すべて", "画像", "ニュース", "動画", "ショッピング"]):
        d.text((tx, top + 76), t, font=small, fill=(26, 115, 232) if k == 0 else (95, 99, 104))
        if k == 0:
            d.line([(tx, top + 101), (tx + text_w(small, t), top + 101)], fill=(26, 115, 232), width=3)
        tx += text_w(small, t) + 28
    d.line([(x0, top + 103), (x1, top + 103)], fill=(235, 235, 235))
    result, links = data.get("result") or "", []
    m = re.search(r"Links:\s*(\[.*?\])\s*(?:\n|$)", result, re.S)
    if m:
        try:
            links = [l for l in json.loads(m.group(1)) if isinstance(l, dict)]
        except ValueError:
            pass
    rest = re.sub(r"Links:\s*\[.*?\]\s*(?:\n|$)", "", result, flags=re.S)
    rest = re.sub(r"(?m)^(Web search results for query:.*|REMINDER:.*)$", "", rest)
    snippets = [s for s in plain(rest).split("\n") if len(s) > 20]
    pois, y = [bar, (sx0 + 120, top + 40)], top + 122
    for k, l in enumerate(links[:6] or [{"title": q, "url": "https://www.google.com/"}]):
        if y > y1 - 70:
            break
        host = urlparse(l.get("url", "")).netloc
        avatar(d, sx0, y + 2, 26, host or "g", round_=True)
        d.text((sx0 + 36, y - 1), host[:50], font=small, fill=(32, 33, 36))
        _fit(d, (sx0 + 36, y + 15), l.get("url", ""), small, 520, (77, 81, 86))
        _fit(d, (sx0, y + 38), l.get("title", ""), title_f, x1 - sx0 - 60, (26, 13, 171))
        yy = y + 68
        if k < len(snippets):
            for ln in wrap_px(snippets[k], snip_f, min(620, x1 - sx0 - 60), 2):
                d.text((sx0, yy), ln, font=snip_f, fill=(71, 71, 71))
                yy += 21
        pois.append((sx0 + 150, y + 50))
        y = yy + 18
    return pois, None


# ---------------------------------------------------------------- image viewer

def image_viewer(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    fp = data["path"]
    d = window(img, box, os.path.basename(fp), ui, focused, (36, 36, 38))
    top = y0 + TITLE
    area = (x0 + 16, top + 16, x1 - 16, y1 - 44)
    pois = []
    try:
        pic = Image.open(_local(fp)).convert("RGB")
        ow = pic.width
        pic.thumbnail((area[2] - area[0], area[3] - area[1]))
        px = (area[0] + area[2] - pic.width) // 2
        py = (area[1] + area[3] - pic.height) // 2
        img.paste(pic, (px, py))
        zoom = f"{round(100 * pic.width / max(1, ow))}%"
        pois += [(px + pic.width // 3, py + pic.height // 3),
                 (px + 2 * pic.width // 3, py + 2 * pic.height // 3)]
    except Exception:
        zoom = "—"
    d = ImageDraw.Draw(img)
    small = ui_font(14)
    d.text((x0 + 20, y1 - 32), f"{os.path.basename(fp)}    {zoom}", font=small, fill=(190, 190, 196))
    return pois, None


# ---------------------------------------------------------------- system monitor

def _cpu_usage():
    def snap():
        out = []
        with open("/proc/stat") as fh:
            for l in fh:
                if l.startswith("cpu") and l[3].isdigit():
                    v = list(map(int, l.split()[1:]))
                    out.append((sum(v), v[3] + v[4]))
        return out
    try:
        a = snap()
        time.sleep(0.25)
        b = snap()
        return [max(0.02, min(1.0, 1 - (bi[1] - ai[1]) / max(1, bi[0] - ai[0])))
                for ai, bi in zip(a, b)]
    except OSError:
        return [random.random() * 0.5 for _ in range(8)]


def _memory():
    try:
        m = {}
        with open("/proc/meminfo") as fh:
            for l in fh:
                k, v = l.split(":")
                m[k] = int(v.split()[0]) / 1048576
        return m["MemTotal"] - m["MemAvailable"], m["MemTotal"]
    except (OSError, KeyError, ValueError):
        return 0.0, 0.0


def _gpu():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                              "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=3).stdout.strip()
        name, util, used, total = [s.strip() for s in out.splitlines()[0].split(",")]
        return name, int(util) / 100, float(used) / 1024, float(total) / 1024
    except Exception:
        return None


def monitor(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    d = window(img, box, "システムモニター", ui, focused, (32, 32, 34))
    top = y0 + TITLE
    small = ui_font(14)
    d.rectangle([x0, top, x1, top + 40], fill=(40, 40, 43))
    tabs = ["プロセス", "リソース", "ファイルシステム"]
    tx = x0 + 24
    for k, t in enumerate(tabs):
        if k == 1:
            d.rounded_rectangle([tx - 10, top + 6, tx + text_w(small, t) + 10, top + 34], 6,
                                fill=(62, 62, 66))
        d.text((tx, top + 11), t, font=small, fill=(230, 230, 230))
        tx += text_w(small, t) + 40
    pois = [(x0 + 70, top + 20)]

    cores = _cpu_usage()
    avg = sum(cores) / len(cores)
    y = top + 56
    d.text((x0 + 24, y), f"CPU   {round(avg * 100)}%   {len(cores)} スレッド", font=small,
           fill=(230, 230, 230))
    y += 28
    n = len(cores)
    per_row = min(n, 16)
    bw = max(8, (x1 - x0 - 48 - (per_row - 1) * 6) // per_row)
    bh = 70
    bars = []
    for i, u in enumerate(cores):
        bx = x0 + 24 + (i % per_row) * (bw + 6)
        by = y + (i // per_row) * (bh + 12)
        bars.append((bx, by, u))
    rows = (n + per_row - 1) // per_row
    y += rows * (bh + 12) + 10
    pois += [(bars[0][0] + bw // 2, bars[0][1] + bh // 2),
             (bars[-1][0] + bw // 2, bars[-1][1] + bh // 2)]

    used, total = _memory()
    if total:
        d.text((x0 + 24, y), f"メモリ   {used:.1f} GiB / {total:.1f} GiB", font=small,
               fill=(230, 230, 230))
        y += 26
        w = x1 - x0 - 48
        d.rounded_rectangle([x0 + 24, y, x0 + 24 + w, y + 14], 7, fill=(58, 58, 62))
        d.rounded_rectangle([x0 + 24, y, x0 + 24 + int(w * used / total), y + 14], 7,
                            fill=(120, 170, 255))
        pois.append((x0 + 24 + int(w * used / total), y + 7))
        y += 34
    g = _gpu()
    if g and y + 40 < y1:
        name, util, gu, gt = g
        d.text((x0 + 24, y), f"GPU   {name}   {round(util * 100)}%   VRAM {gu:.1f} / {gt:.0f} GiB",
               font=small, fill=(230, 230, 230))
        y += 26
        w = x1 - x0 - 48
        d.rounded_rectangle([x0 + 24, y, x0 + 24 + w, y + 14], 7, fill=(58, 58, 62))
        d.rounded_rectangle([x0 + 24, y, x0 + 24 + max(14, int(w * util)), y + 14], 7,
                            fill=(118, 185, 0))

    def animate(draw, i, rnd):
        # Real readings, nudged a little each frame so the meters look alive.
        for bx, by, u in bars:
            if by + bh > y1 - 8:
                continue
            v = max(0.02, min(1.0, u + rnd.uniform(-0.08, 0.08)))
            draw.rectangle([bx, by, bx + bw, by + bh], fill=(52, 52, 56))
            draw.rectangle([bx, by + int(bh * (1 - v)), bx + bw, by + bh],
                           fill=(255, 140, 90) if v > 0.7 else (98, 160, 234))
    return pois, animate


# ---------------------------------------------------------------- file manager

def files(img, box, f, ui, data, cwd, focused=False):
    x0, y0, x1, y1 = box
    folder = data.get("dir") or cwd or os.path.expanduser("~")
    d = window(img, box, os.path.basename(folder.rstrip("/")) or "/", ui, focused, (250, 250, 250))
    top = y0 + TITLE
    small = ui_font(14)
    side = x0 + 190 if x1 - x0 > 600 else x0
    if side > x0:
        d.rectangle([x0, top, side, y1 - 10], fill=(240, 240, 242))
        for k, place in enumerate(["ホーム", "デスクトップ", "ドキュメント", "ダウンロード", "画像", "ゴミ箱"]):
            d.text((x0 + 22, top + 18 + k * 34), place, font=small, fill=(70, 70, 76))
    d.rounded_rectangle([side + 16, top + 12, x1 - 16, top + 42], 8, fill=(236, 236, 240))
    shown = folder.replace(os.path.expanduser("~"), "~", 1)
    d.text((side + 30, top + 17), shown[-70:], font=small, fill=(60, 60, 66))
    pois = [(side + 140, top + 27)]

    lf = _local(folder)
    try:
        names = sorted((n for n in os.listdir(lf) if not n.startswith(".")),
                       key=lambda n: (not os.path.isdir(os.path.join(lf, n)), n.lower()))
    except OSError:
        names = []
    cw, ch = 120, 118
    cols = max(1, (x1 - side - 32) // cw)
    gx, gy = side + 24, top + 62
    for k, n in enumerate(names):
        cx, cy = gx + (k % cols) * cw, gy + (k // cols) * ch
        if cy + ch > y1 - 10:
            break
        if os.path.isdir(os.path.join(lf, n)):
            d.rounded_rectangle([cx + 26, cy + 8, cx + 58, cy + 18], 3, fill=(214, 160, 60))
            d.rounded_rectangle([cx + 26, cy + 14, cx + 94, cy + 64], 6, fill=(240, 186, 80))
        else:
            d.polygon([(cx + 38, cy + 6), (cx + 74, cy + 6), (cx + 86, cy + 18), (cx + 86, cy + 66),
                       (cx + 38, cy + 66)], fill=(255, 255, 255), outline=(190, 190, 196))
            ext = os.path.splitext(n)[1][1:5].upper()
            if ext:
                d.text((cx + 62 - text_w(small, ext) // 2, cy + 40), ext, font=small,
                       fill=(90, 120, 200))
        label = n if text_w(small, n) < cw - 8 else n[:11] + "…"
        d.text((cx + 60 - text_w(small, label) // 2, cy + 74), label, font=small, fill=(40, 40, 46))
        pois.append((cx + 60, cy + 36))
    return pois, None


# ---------------------------------------------------------------- terminal

def terminal(img, box, f, ui, events, cwd, model="claude"):
    """Draw the Claude Code terminal; -> geometry for the per-frame overlays."""
    x0, y0, x1, y1 = box
    short = re.sub(r"^(/Users|/home)/[^/]+", "~", cwd) if cwd else "~"   # this PC or the Mac
    d = window(img, box, f"claude — {short}", ui, True, BG)
    pad, top = 18, y0 + TITLE
    put(d, f, x0 + pad, top + 10, f"{short}  ·  {model}", DIM)
    d.line([(x0 + pad, top + 40), (x1 - pad, top + 40)], fill=(38, 38, 42), width=1)
    yb = y1 - 84
    ys = yb - 40
    y = top + 50
    pois = []
    for head, hcol, body, bcol in layout(events, (ys - y - 6) // TL, (x1 - x0 - 2 * pad) // CELL):
        x = put(d, f, x0 + pad, y, head, hcol)
        put(d, f, x, y, body, bcol)
        if body.strip():
            pois.append((x0 + pad + 120, y + 10))
        y += TL
    d.rounded_rectangle([x0 + pad, yb, x1 - pad, yb + 58], 8, outline=(58, 58, 64), width=1)
    put(d, f, x0 + pad + 16, yb + 16, "> ", ACCENT)
    pois.append((x0 + pad + 150, yb + 30))
    return {"px": x0 + pad, "ys": ys, "yb": yb, "pois": pois[-6:]}


# ---------------------------------------------------------------- mouse

def mouse_path(rnd, pois, frames):
    """A different wander every time: 3-5 stops picked from what is on screen, curved
    moves at varying speed, pauses of varying length, and clicks now and then."""
    stops = rnd.sample(pois, min(len(pois), rnd.randint(3, 5))) if pois else [(DW / 2, DH / 2)]
    stops = [(min(DW - 30, max(40, x + rnd.uniform(-24, 24))),
              min(DH - 40, max(BAR + 6, y + rnd.uniform(-12, 12)))) for x, y in stops]
    x, y = stops[0]
    pos, clicks = [(x, y)] * rnd.randint(1, 6), []
    for nx, ny in stops[1:]:
        n = rnd.randint(5, 11)
        dx, dy = nx - x, ny - y
        b1, b2 = rnd.uniform(-0.35, 0.35), rnd.uniform(-0.35, 0.35)
        c1 = (x + dx * 0.3 - dy * b1, y + dy * 0.3 + dx * b1)
        c2 = (x + dx * 0.7 - dy * b2, y + dy * 0.7 + dx * b2)
        for k in range(1, n + 1):
            t = k / n
            s = t * t * (3 - 2 * t)
            u = 1 - s
            pos.append((u ** 3 * x + 3 * u * u * s * c1[0] + 3 * u * s * s * c2[0] + s ** 3 * nx,
                        u ** 3 * y + 3 * u * u * s * c1[1] + 3 * u * s * s * c2[1] + s ** 3 * ny))
        if rnd.random() < 0.45:
            clicks.append(len(pos) - 1)
        pos += [(nx, ny)] * rnd.randint(2, 9)
        x, y = nx, ny
    pos += [(x, y)] * max(0, frames - len(pos))
    return pos[:frames], clicks


# ---------------------------------------------------------------- scene

DRAW = {"editor": editor, "browser": browser, "image": image_viewer,
        "monitor": monitor, "files": files, "search": search,
        "slack": slack, "notion": notion, "gmail": gmail, "google_calendar": gcal,
        "google_drive": gdrive, "figma": figma}


def arrange(rnd):
    """Where the windows go this time -> (big, side, terminal, side drawn over big?).
    The terminal takes the left or the right; the big window takes the other side and
    the small one the top corner above the terminal. Sizes and offsets vary widely."""
    tw, th = rnd.randint(760, 860), rnd.randint(590, 650)
    bw, bh = rnd.randint(980, 1140), rnd.randint(760, 880)
    sw, sh = rnd.randint(600, 740), rnd.randint(340, 460)
    ty = rnd.randint(290, DH - 14 - th)
    by = rnd.randint(BAR + 14, max(BAR + 15, DH - 14 - bh))
    sy = rnd.randint(BAR + 14, BAR + 60)
    if rnd.random() < 0.5:                          # terminal on the right
        tx, bx, sx = DW - tw - rnd.randint(30, 110), rnd.randint(30, 110), DW - sw - rnd.randint(30, 90)
    else:                                           # terminal on the left
        tx, bx, sx = rnd.randint(30, 110), DW - bw - rnd.randint(30, 110), rnd.randint(30, 90)

    def box(x, y, w, h):
        return (x, y, min(DW - 24, x + w), min(DH - 14, y + h))
    return box(bx, by, bw, bh), box(sx, sy, sw, sh), box(tx, ty, tw, th), rnd.random() < 0.35


def _inside(pt, b):
    return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]


def build(path, frames, fps):
    rnd = random.Random()
    f, ui = fonts(), ui_font(17)
    global REMOTE_ROOT
    root = os.path.join(os.path.dirname(path), "root")
    REMOTE_ROOT = root if os.path.basename(path) == "transcript.jsonl" and os.path.isdir(root) else None
    events, running = read_session(path)
    cwd, found = scan(path)
    if REMOTE_ROOT:
        # Another machine's session: this PC's CPU and GPU would be the wrong machine's,
        # and folders there are only visible if their files came along.
        found.pop("monitor", None)
        if "files" in found and not os.path.isdir(_local(found["files"][1].get("dir") or "")):
            found.pop("files")
    # The windows the conversation used most recently: the newest gets the big slot.
    kinds = [k for k, _ in sorted(found.items(), key=lambda kv: kv[1][0], reverse=True)][:2]
    if not kinds:
        kinds = ["editor"]

    base = wallpaper()
    topbar(base, ui)
    big, side, term, side_front = arrange(rnd)
    jobs = [(kinds[0], big)]                        # back to front; the terminal goes last
    if len(kinds) > 1:
        jobs.insert(1 if side_front else 0, (kinds[1], side))
    drawn, anims = [], []
    for kind, b in jobs:
        p, a = DRAW[kind](base, b, f, ui, found[kind][1] if kind in found else None, cwd)
        drawn.append((b, p))
        if a:
            anims.append((a, len(drawn) - 1))
    t = terminal(base, term, f, ui, events, cwd, session_model(path))
    drawn.append((term, t["pois"]))

    # Only what can be seen counts: the mouse skips points under a later window, and
    # animated parts are masked to the uncovered area of their own window.
    pois = [pt for i, (b, p) in enumerate(drawn) for pt in p
            if not any(_inside(pt, later) for later, _ in drawn[i + 1:])]
    masks = []
    for a, i in anims:
        m = Image.new("L", base.size, 0)
        md = ImageDraw.Draw(m)
        md.rectangle(drawn[i][0], fill=255)
        for later, _ in drawn[i + 1:]:
            md.rectangle(later, fill=0)
        masks.append((a, m))

    xy, clicks = mouse_path(rnd, pois, frames)
    out = []
    for i in range(frames):
        img = base.copy()
        for a, m in masks:        # every frame: the base copy has no meters of its own
            layer = img.copy()
            a(ImageDraw.Draw(layer), i, rnd)
            img.paste(layer, (0, 0), m)
        d = ImageDraw.Draw(img)
        if running:
            x = put(d, f, t["px"], t["ys"], SPINNER[(i // 2) % len(SPINNER)] + " ", ACCENT)
            put(d, f, x, t["ys"], f"Working… ({int(i / fps)}s)", DIM)
        if i % 8 < 5:
            bx = t["px"] + 16 + CELL * 2
            d.rectangle([bx, t["yb"] + 18, bx + CELL - 2, t["yb"] + 40], fill=FG)
        mx, my = xy[i]
        for c in clicks:
            if 0 <= i - c < 3:
                r = 8 + 6 * (i - c)
                d.ellipse([mx - r, my - r, mx + r, my + r], outline=(255, 255, 255), width=2)
        d.polygon([(mx + px, my + py) for px, py in ARROW],
                  fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        out.append(img)
    return out
