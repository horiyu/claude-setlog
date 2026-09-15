#!/usr/bin/env python3
"""Own the X CLIPBOARD so the emulator can share it into Android.

There is no xclip/xsel here and installing one needs root, so this serves the
selection itself. It must keep running: whoever owns a selection has to answer
every request for it. Usage: clip.py "text"   (or no args -> state/mood.txt)
"""
import os, sys

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HOME, "vendor"))

from Xlib import X, display, Xatom  # noqa: E402


def main():
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        with open(os.path.join(HOME, "state", "mood.txt"), encoding="utf-8") as fh:
            text = fh.read().strip()
    data = text.encode("utf-8")

    d = display.Display(os.environ.get("DISPLAY", ":0"))
    win = d.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    CLIPBOARD = d.intern_atom("CLIPBOARD")
    UTF8 = d.intern_atom("UTF8_STRING")
    TARGETS = d.intern_atom("TARGETS")

    for sel in (CLIPBOARD, Xatom.PRIMARY):
        win.set_selection_owner(sel, X.CurrentTime)
    d.sync()
    print(f"owning clipboard: {text}", flush=True)

    while True:
        e = d.next_event()
        if e.type == X.SelectionClear:
            return 0
        if e.type != X.SelectionRequest:
            continue
        prop = e.property if e.property != X.NONE else e.target
        if e.target == TARGETS:
            e.requestor.change_property(prop, Xatom.ATOM, 32, [TARGETS, UTF8, Xatom.STRING])
        elif e.target in (UTF8, Xatom.STRING):
            e.requestor.change_property(prop, e.target, 8, data)
        else:
            prop = X.NONE
        e.requestor.send_event(
            display.event.SelectionNotify(
                time=e.time, requestor=e.requestor, selection=e.selection,
                target=e.target, property=prop))
        d.flush()


if __name__ == "__main__":
    sys.exit(main())
