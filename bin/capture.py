#!/usr/bin/env python3
"""Stop hook: turn the finished turn into state/thought.json, then re-render the card.

Claude Code stores thinking blocks encrypted (`thinking` is always ""), so the
card is built from what the transcript does keep: the instruction, the text
Claude wrote, and the trail of tools it reached for.
"""
import json, os, re, subprocess, sys, datetime

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(HOME, "state")
MAX_SUMMARY = 120
MAX_INSTRUCTION = 70


def blocks(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def is_human(entry):
    msg = entry.get("message") or {}
    if msg.get("role") != "user" or entry.get("isMeta"):
        return False
    bs = blocks(msg)
    if any(b.get("type") == "tool_result" for b in bs):
        return False
    return any(b.get("type") == "text" and b.get("text", "").strip() for b in bs)


def clean(text):
    text = re.sub(r"<[^>]+>", "", text)              # system-reminder & friends
    text = re.sub(r"```.*?```", "", text, flags=re.S)  # code fences
    text = re.sub(r"[*_`#>|-]", "", text)
    return " ".join(text.split())


def describe(block):
    name = block.get("name", "")
    inp = block.get("input") or {}
    if name == "Bash" and inp.get("description"):
        return inp["description"]
    for key in ("file_path", "path", "pattern", "query", "url"):
        if inp.get(key):
            return f"{name} {os.path.basename(str(inp[key]))}"
    return name


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return

    entries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

    start = max((i for i, e in enumerate(entries) if is_human(e)), default=None)
    if start is None:
        return

    instruction, texts, steps = "", [], []
    for b in blocks(entries[start]["message"]):
        if b.get("type") == "text":
            instruction = clean(b["text"])
            break
    for e in entries[start + 1:]:
        msg = e.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        for b in blocks(msg):
            if b.get("type") == "text" and b.get("text", "").strip():
                texts.append(clean(b["text"]))
            elif b.get("type") == "tool_use":
                steps.append(describe(b))

    summary = next((t for t in texts if len(t) > 12), texts[0] if texts else "")
    thought = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "model": payload.get("model") or os.environ.get("SETLOG_MODEL", "claude"),
        "instruction": instruction[:MAX_INSTRUCTION],
        "summary": summary[:MAX_SUMMARY],
        "steps": steps,
        "session": payload.get("session_id", ""),
    }

    os.makedirs(STATE, exist_ok=True)
    tmp = os.path.join(STATE, "thought.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(thought, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(STATE, "thought.json"))

    with open(os.path.join(STATE, "thoughts.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(thought, ensure_ascii=False) + "\n")

    # The camera feed is live terminal footage (bin/screencast.sh), so do NOT
    # rewrite card.mp4 here. Emit a caption strip the screencast can overlay.
    subprocess.run([sys.executable, os.path.join(HOME, "bin", "caption.py")],
                   capture_output=True, timeout=60)


if __name__ == "__main__":
    main()
