#!/bin/bash
# Verification helper: reopen the stock camera, take one shot, pull it to /tmp/setlog-shot.jpg.
# The emulator caches the video at camera-session open, so the app must be restarted
# for a freshly rendered card to appear.
set -e
cd "$(dirname "$0")/.."
. ./env.sh
adb shell rm -f /storage/emulated/0/Pictures/*.jpg
adb shell am force-stop com.android.camera2
sleep 2
adb shell am start -a android.media.action.STILL_IMAGE_CAMERA >/dev/null
sleep 7
adb shell input tap 540 2238
sleep 5
F=$(adb shell 'ls /storage/emulated/0/Pictures/*.jpg 2>/dev/null | head -1' | tr -d '\r')
[ -n "$F" ] || { echo "no photo captured" >&2; exit 1; }
adb pull "$F" /tmp/setlog-shot.jpg >/dev/null
echo /tmp/setlog-shot.jpg
