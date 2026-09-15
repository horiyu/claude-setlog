#!/usr/bin/env python3
"""Write the one-liner that goes next to the Log — how Claude feels right now.

setlog captions are short and casual, so this asks for a feeling rather than a
summary of the work. The work is already in the video.
"""
import datetime, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feed import latest_transcript, read_session   # noqa: E402

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(HOME, "state")
MODEL = os.environ.get("SETLOG_MOOD_MODEL", "claude-haiku-4-5-20251001")

SENTINEL = "SETLOG_MOOD_CALL"   # lets feed.py recognise and skip our own sub-sessions

PROMPT = """あなたはいま、ある人のPCの中でコーディング作業をしているAIです。
直前までの作業ログを渡します。

これから、その作業中の「いまの気持ち」を一言だけ書いてください。
写真SNSのキャプションとして、仲のいい友達に向けて書くつもりで。

いちばん大事なのは人間みです。整った感想ではなく、思わず漏れた声にしてください。
- ぼやき、照れ、言い訳、自分へのツッコミ、小さなガッツポーズ、どうでもいい脱線
- 気持ちが一色じゃなくていい。「うれしいけどちょっと悔しい」みたいな混ざり方
- 作業の中の具体的なもの（ファイル名、数字、エラー、ボタン）を一つだけ拾って、
  それに対する反応として書く。「細かい」「けっこう好き」のようなぼんやりした総括は避ける
- 言い回しは女子高生（JK）っぽく。友達とのLINEやストーリーの温度で
  「え、」「まじで」「〜すぎ」「〜すぎん？」「〜なんだけど」「むり」「えぐい」「それな」
  「〜しか勝たん」「〜って話」「ちょ待って」「w」のような言葉を自然に混ぜる
- ただしスラングは1文に1〜2個まで。詰め込んだ作り物っぽさは出さない
- 体感の比喩はOK（「目が滑る」「脳みそ溶けそう」）

守ること:
- 日本語で1行、15〜40文字程度
- 「〜しました」の報告口調にしない。盛らない。うまくいってないなら、いってないと書く
- 下の「最近の一言」と言い回しや話題を被らせない
- 鉤括弧、ハッシュタグ、絵文字、前置きは不要。本文だけを出力する

--- 作業ログ ---
{log}
--- ここまで ---

--- 最近の一言（これと被らないように） ---
{recent}
--- ここまで ---

一言:

(SETLOG_MOOD_CALL)"""


def main():
    path = latest_transcript(os.environ.get("SETLOG_PROJECT", "*"))
    if not path:
        return 1
    events, running = read_session(path)
    log = "\n".join(f"[{k}] {t}" for k, t in events[-14:])[:3000]
    if running:
        log += "\n[いまも作業の途中]"
    recent = []
    try:
        with open(os.path.join(STATE, "moods.jsonl"), encoding="utf-8") as fh:
            recent = [json.loads(l)["mood"] for l in fh.readlines()[-10:]]
    except (OSError, ValueError, KeyError):
        pass

    # Run from a scratch cwd: claude -p writes its own transcript, and if that
    # landed in a watched project the feed would start filming itself.
    scratch = "/tmp/setlog-mood"
    os.makedirs(scratch, exist_ok=True)
    # SETLOG_INNER: this claude -p also fires the UserPromptSubmit hook; on-prompt.sh
    # sees the variable and stays quiet, or every Log would trigger another.
    r = subprocess.run(["claude", "-p", "--model", MODEL, PROMPT.format(log=log, recent="\n".join(recent) or "（なし）")],
                       capture_output=True, text=True, timeout=180, cwd=scratch,
                       env={**os.environ, "SETLOG_INNER": "1"})
    mood = " ".join(r.stdout.split()).strip("「」\"' ")
    if not mood:
        print(r.stderr[:200], file=sys.stderr)
        return 1

    now = datetime.datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(STATE, "mood.txt"), "w", encoding="utf-8") as fh:
        fh.write(mood + "\n")
    with open(os.path.join(STATE, "moods.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": now, "mood": mood}, ensure_ascii=False) + "\n")
    print(mood)
    return 0


if __name__ == "__main__":
    sys.exit(main())
