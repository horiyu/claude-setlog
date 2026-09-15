#!/usr/bin/env python3
"""Overwrite just the thought line, keeping the rest of the card. Usage: say.py "..." """
import json, os, subprocess, sys, datetime
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(HOME, "state")
p = os.path.join(STATE, "thought.json")
t = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
t["summary"] = " ".join(sys.argv[1:])[:120]
t["time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
json.dump(t, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
subprocess.run([sys.executable, os.path.join(HOME, "bin", "render.py")], check=True)
