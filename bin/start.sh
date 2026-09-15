#!/bin/bash
# Start the camera feed, then boot the emulator with it wired to both cameras.
set -e
cd "$(dirname "$0")/.."
. ./env.sh
. ./state/capture.conf
export DISPLAY="${DISPLAY_ID:-${DISPLAY:-:0}}"

if [ "${SOURCE:-feed}" = "feed" ]; then
  export SETLOG_ORIENT="$ORIENT" SETLOG_PROJECT="$SETLOG_PROJECT" SETLOG_SCENE="${SCENE:-desktop}"
  [ -s state/card.mp4 ] || python3 bin/feed.py --once
  nohup python3 bin/feed.py > /tmp/setlog-feed.log 2>&1 &
  echo $! > state/feed.pid
  nohup bin/mood-loop.sh > /tmp/setlog-mood.log 2>&1 &
  echo "feed started ($ORIENT, project glob: $SETLOG_PROJECT)"
else
  [ -f state/screencast.pid ] || { nohup bin/screencast.sh > /tmp/setlog-screencast.log 2>&1 & }
  echo "screencast started (filming ${WINDOW_ID:-whole screen})"
fi

exec emulator -avd setlog -no-audio -no-boot-anim \
  -gpu swiftshader_indirect \
  -camera-back  "videofile:$PWD/state/card.mp4" \
  -camera-front "videofile:$PWD/state/card_front.mp4" "$@"
