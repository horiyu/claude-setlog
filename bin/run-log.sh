#!/bin/bash
# One Log per trigger: boot the emulator, draw the screen, shoot, caption, send, and
# shut the emulator down again. Nothing stays resident between triggers (a week-long
# emulator had grown past 50 GB of RAM).
cd "$(dirname "$0")/.."
. ./env.sh
. ./state/capture.conf
export DISPLAY="${DISPLAY_ID:-${DISPLAY:-:0}}"
log() { echo "$(date '+%F %T') $*"; }

exec 9> state/run.lock
flock -n 9 || { log "another Log is in progress; it films this session if it has not started drawing"; exit 0; }
bin/capture-log.sh --check || { log "rate limit; skipping"; exit 0; }   # before paying for a boot

started=0
child=
# An emulator this run booted is shut down however the run ends: a failed step, or
# a kill / logout / shutdown that would otherwise leave it eating RAM for days.
cleanup() {
  set +e
  if [ -n "$child" ]; then
    # The capture runs in its own process group (setsid below), so this reaches
    # mood.py / claude -p / sleep as well, not just the shell waiting on them; and
    # waiting for it means the lock fd it inherited is released before we return.
    kill -TERM -- "-$child" 2>/dev/null
    wait "$child" 2>/dev/null
  fi
  if [ $started = 1 ]; then
    adb emu kill >/dev/null 2>&1
    log "emulator stopped"
  fi
}
trap cleanup EXIT
trap 'exit 143' TERM INT HUP

if ! adb devices | grep -q '^emulator-5554[[:space:]]*device'; then
  log "booting emulator"
  # A fresh clone has no camera video yet; give the emulator something to open.
  # capture-log.sh draws the real one before setlog opens the camera.
  for v in card card_front; do
    [ -s "state/$v.mp4" ] || ffmpeg -loglevel error -f lavfi -i color=c=0x0e0e10:s=1710x1280:d=1 \
      -pix_fmt yuv420p "state/$v.mp4"
  done
  # -no-snapshot: the saved snapshot would not load anyway, and saving one on exit
  # costs 20 s and 4 GB of disk. A cold boot takes about 20 s.
  # 9>&-: the emulator's helpers (netsimd, crashpad) outlive it, and if they inherit
  # the lock fd every later trigger sees "in progress" and skips.
  emulator -avd setlog -no-snapshot -no-audio -no-boot-anim -gpu swiftshader_indirect \
    -camera-back "videofile:$PWD/state/card.mp4" \
    -camera-front "videofile:$PWD/state/card_front.mp4" \
    > /tmp/setlog-emu.log 2>&1 < /dev/null 9>&- &
  started=1
  timeout 120 adb wait-for-device
  booted=0
  for _ in $(seq 1 120); do
    [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && { booted=1; break; }
    sleep 1
  done
  if [ $booted != 1 ]; then
    log "emulator did not finish booting; giving up (see /tmp/setlog-emu.log)"
    exit 1                                  # the trap stops the emulator
  fi
  sleep 5                                   # let the launcher settle before tapping
fi

# Run as a job in its own process group and wait, so a signal reaches the trap now
# rather than after the capture has finished on its own, and cleanup() can stop the
# whole capture, not only its shell.
setsid bin/capture-log.sh & child=$!
wait "$child"; rc=$?
child=
# Bundles from other machines (bin/on-remote.sh): keep the newest 5. Done here, with
# the lock held and the capture over, so a bundle is never removed while being drawn.
ls -dt state/remote/*/ 2>/dev/null | tail -n +6 | xargs -r rm -rf
log "done rc=$rc"
exit "$rc"
