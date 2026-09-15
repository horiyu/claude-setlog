#!/bin/bash
cd "$(dirname "$0")/.."
. ./env.sh
for f in state/feed.pid state/mood.pid state/clip.pid state/screencast.pid; do
  [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null; rm -f "$f"
done
adb -s emulator-5554 emu kill 2>/dev/null || true
echo stopped
