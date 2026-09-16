#!/bin/bash
# Refresh the one-liner every MOOD_INTERVAL seconds. Costs one small model call
# each time, so it runs far slower than the video feed.
cd "$(dirname "$0")/.."
. ./state/capture.conf
echo $$ > state/mood.pid
trap 'rm -f state/mood.pid; exit 0' TERM INT
while :; do
  if SETLOG_PROJECT="$SETLOG_PROJECT" "${SETLOG_PYTHON:-python3}" bin/mood.py >/dev/null 2>>/tmp/setlog-mood.err; then
    bin/clip-set.sh     # keep the clipboard holding the latest line, ready to paste
  fi
  sleep "${MOOD_INTERVAL:-300}"
done
