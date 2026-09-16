#!/bin/bash
# Take one Log in setlog and send it to the room, with a fresh one-liner as the caption.
# Automated tapping was permitted by New Chat on 2026-09-15 (docs/permission-reply-*.md),
# on the promise of "1 to 10 an hour". No spacing between Logs (the user asked for
# none); only the hourly count is capped, over a sliding hour.
#
# Coordinates are for the 1080x2400 AVD. The send screen plays the video, so
# uiautomator cannot dump it ("could not get idle state"); those taps are fixed.
set -e
cd "$(dirname "$0")/.."
. ./env.sh
. ./state/capture.conf
export DISPLAY="${DISPLAY_ID:-${DISPLAY:-:0}}"

MAX_PER_HOUR=10
POSTS=state/posts.jsonl
# Taps for a 1080x2400 AVD. Override these in state/capture.conf for another screen,
# or if the room you send to is not the first row.
TAP_RECORD=${TAP_RECORD:-"540 1836"}   # the shutter button
TAP_ROOM=${TAP_ROOM:-"120 ${ROOM_Y:-1106}"}  # checkbox of the room row on the send screen
TAP_SEND=${TAP_SEND:-"984 206"}        # the send arrow

recent=$("$SETLOG_PYTHON" -c 'import sys,json,time
n=0
for l in open(sys.argv[1]):
    try: n += time.time() - json.loads(l)["epoch"] < 3600
    except (ValueError, KeyError): pass
print(n)' "$POSTS" 2>/dev/null || echo 0)
if [ "$recent" -ge $MAX_PER_HOUR ]; then
  echo "already $recent Logs in the last hour; skipping" >&2; exit 1
fi
[ "${1:-}" = --check ] && exit 0            # run-log.sh asks before booting the emulator

# Whatever happens below (set -e stops at the first failed step), leave nothing
# behind: no clip.py waiting for a clipboard that will never be read, and an
# emulator that is still running back in portrait.
cleanup() {
  set +e
  if [ -f state/clip.pid ]; then
    kill "$(cat state/clip.pid)" 2>/dev/null
    rm -f state/clip.pid
  fi
  adb emu sensor set acceleration 0:9.81:0.8 >/dev/null 2>&1
}
trap cleanup EXIT
trap 'exit 143' TERM INT HUP    # so a kill from run-log.sh still reaches cleanup

# 0. Film the session the user spoke to most recently, not the one that started this
#    run: on-prompt.sh keeps recording triggers while the emulator boots.
[ -s state/latest-transcript ] && export SETLOG_TRANSCRIPT="$(cat state/latest-transcript)"

# 1. Caption. Written now, so it reacts to what is on screen at this moment. The
#    previous caption is removed first: if claude -p fails (timeout, expired login,
#    no network) this Log must not go out with last time's words on it.
rm -f state/mood.txt
if ! SETLOG_PROJECT="$SETLOG_PROJECT" "$SETLOG_PYTHON" bin/mood.py >/dev/null 2>>/tmp/setlog-mood.err; then
  echo "caption failed (see /tmp/setlog-mood.err)" >&2; exit 1
fi
mood=$(head -1 state/mood.txt)
[ -n "$mood" ] || { echo "no caption" >&2; exit 1; }

# 2. Japanese can't go through `input text`, so hand it over via the clipboard the
#    emulator shares with X. clip.py exits once Android has taken the selection.
[ -f state/clip.pid ] && kill "$(cat state/clip.pid)" 2>/dev/null || true
setsid nohup "$SETLOG_PYTHON" bin/clip.py "$mood" > /tmp/setlog-clip.log 2>&1 < /dev/null 9>&- &
echo $! > state/clip.pid
sleep 3

# 3. Draw the screen once, now. There is no resident feed any more.
SETLOG_ORIENT="$ORIENT" SETLOG_PROJECT="$SETLOG_PROJECT" SETLOG_SCENE="${SCENE:-desktop}" \
  "$SETLOG_PYTHON" bin/feed.py --once

# Fresh camera session, so the emulator picks up that card.mp4.
adb emu sensor set acceleration 0:9.81:0.8 >/dev/null
adb shell am force-stop com.newchat.setlog
sleep 1
adb shell monkey -p com.newchat.setlog -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 6
# The "back up encryption key" dialog sometimes greets us; dismiss it.
if adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; then
  xy=$(adb shell cat /sdcard/ui.xml 2>/dev/null | python3 -c '
import sys,re
m=re.search(r"resource-id=\"android:id/button2\"[^>]*bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"",sys.stdin.read())
if m: a,b,c,d=map(int,m.groups()); print((a+c)//2,(b+d)//2)')
  [ -n "$xy" ] && { adb shell input tap $xy; sleep 2; }
  adb shell rm -f /sdcard/ui.xml
fi

# 4. Tilt to landscape: setlog only captures sideways ("rotate to capture").
adb emu sensor set acceleration -9.81:0:0 >/dev/null
sleep 5
adb shell input tap $TAP_RECORD
sleep 7

# 5. Caption, room, send.
adb shell input keyevent 279        # KEYCODE_PASTE into the caption field
sleep 1
adb exec-out screencap -p > state/last-send.png
adb shell input tap $TAP_ROOM
sleep 1
adb shell input tap $TAP_SEND

# 6. Wait for the upload. "sent" appears at once, but the video goes up in the
#    background afterwards; stopping the emulator right away left the friend with a
#    "sent" row and no video. Watch the guest's outgoing bytes: at least 150 KB out
#    (a Log measured ~320 KB), then 9 s of near silence (or give up after ~3 min).
tx() { adb shell cat /proc/net/dev 2>/dev/null | awk '/eth0|wlan0/{t+=$10} END{print t+0}'; }
tx_start=$(tx); tx_prev=$tx_start; quiet=0; settled=0
for _ in $(seq 1 60); do
  sleep 3
  tx_now=$(tx)
  if [ $(( tx_now - tx_prev )) -lt 20000 ]; then quiet=$(( quiet + 1 )); else quiet=0; fi
  tx_prev=$tx_now
  [ $(( tx_now - tx_start )) -gt 150000 ] && [ $quiet -ge 3 ] && { settled=1; break; }
done
uploaded=$(( tx_prev - tx_start ))
echo "uploaded ~${uploaded} bytes (settled=$settled)"

# setlog's UI has no text nodes for uiautomator, so keep the room list as evidence:
# the room row should read "sent log 1m" or so.
adb exec-out screencap -p > state/last-sent.png
# clip.py and the orientation are put back by cleanup() on exit.

# 7. Record the attempt either way: the send button was tapped, so the post may
#    exist even if the upload was not seen, and the hourly promise to New Chat is
#    about posts, not about proof. But only an upload that was seen to finish counts
#    as success: bytes still flowing at the 3-minute mark mean the video is not up
#    yet, and stopping the emulator now would leave a "sent" row with no video.
ok=true; [ $settled = 1 ] || ok=false
"$SETLOG_PYTHON" -c 'import json,sys,time,datetime
print(json.dumps({"time":datetime.datetime.now().isoformat(timespec="seconds"),
                  "epoch":int(time.time()),"caption":sys.argv[1],
                  "uploaded_bytes":int(sys.argv[2]),"ok":sys.argv[3]=="true"},
                 ensure_ascii=False))' "$mood" "$uploaded" "$ok" >> "$POSTS"
if [ "$ok" = true ]; then
  echo "sent: $mood"
else
  echo "upload not finished (~$uploaded bytes in 3 min): check state/last-send.png and" \
       "state/last-sent.png for a wrong tap, a logged-out setlog, or a bad network" >&2
  exit 1
fi
