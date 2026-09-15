#!/bin/bash
# List candidate windows, or set the one to film:  bin/pick-window.sh 0x1a0004c
cd "$(dirname "$0")/.."
. ./state/capture.conf
export DISPLAY="${DISPLAY_ID:-${DISPLAY:-:0}}"
if [ -n "$1" ]; then
  sed -i "s/^WINDOW_ID=.*/WINDOW_ID=$1/" state/capture.conf
  echo "filming $1"
  exit 0
fi
echo "候補（id / サイズ+位置 / 名前）:"
xwininfo -root -tree 2>/dev/null | grep -E '^\s+0x' \
  | grep -viE '\b(10x10|200x200|16x16|1x1)\+' | grep -v 'has no name' \
  | sed -E 's/^\s+(0x[0-9a-f]+) +"([^"]*)".*  ([0-9]+x[0-9]+\+[-0-9]+\+[-0-9]+) .*/  \1  \3  \2/'
echo
echo "使い方: bin/pick-window.sh <id>    （全画面に戻すなら id を空で capture.conf を編集）"
