#!/bin/bash
# Put the current one-liner on the X clipboard (the emulator shares it into Android).
cd "$(dirname "$0")/.."
[ -f state/clip.pid ] && kill "$(cat state/clip.pid)" 2>/dev/null
DISPLAY="${DISPLAY_ID:-${DISPLAY:-:0}}" setsid nohup python3 bin/clip.py "$@" \
  > /tmp/setlog-clip.log 2>&1 < /dev/null &
echo $! > state/clip.pid
