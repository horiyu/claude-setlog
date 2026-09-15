#!/bin/bash
# Keep state/card.mp4 filled with live footage of the terminal.
# The emulator reads this file when a camera session opens, so whatever the
# last clip captured is what setlog sees when you open it.
set -u
cd "$(dirname "$0")/.."
. ./state/capture.conf
export DISPLAY="${DISPLAY_ID:-${DISPLAY:-:0}}"

SRC_W=1710      # 4:3 source frame; the camera crops a left-anchored window out of it
SRC_H=1280
SAFE_W=720      # survives the narrowest crop measured (9:16 video)
BG=0x0e0e10
NEXT=state/.card.next.$$.mp4   # must keep an .mp4 suffix: ffmpeg infers the container from it

echo $$ > state/screencast.pid
trap 'rm -f state/screencast.pid "$NEXT"; exit 0' TERM INT

while :; do
  BASE="scale=${SAFE_W}:${SRC_H}:force_original_aspect_ratio=decrease,pad=${SRC_W}:${SRC_H}:0:(${SRC_H}-ih)/2:color=${BG}"
  if [ "${CAPTION:-0}" = 1 ] && [ -f state/caption.png ]; then
    FILTER=(-i state/caption.png -filter_complex "[0:v]${BASE}[bg];[bg][1:v]overlay=0:${SRC_H}-h-56[v]" -map "[v]")
  else
    FILTER=(-vf "$BASE")
  fi
  if ffmpeg -y -loglevel error -f x11grab ${WINDOW_ID:+-window_id $WINDOW_ID} \
      -framerate "$FPS" -t "$CLIP_SECONDS" -i "$DISPLAY" \
      "${FILTER[@]}" \
      -pix_fmt yuv420p -c:v libx264 -preset veryfast -g 12 \
      "$NEXT" 2>>/tmp/setlog-screencast.err; then
    mv -f "$NEXT" state/card.mp4
  else
    echo "grab failed, see /tmp/setlog-screencast.err" >&2
    sleep 5
  fi
done
