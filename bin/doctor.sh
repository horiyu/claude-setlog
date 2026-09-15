#!/bin/bash
# Check that everything claude-setlog needs is in place. Changes nothing.
cd "$(dirname "$0")/.."
. ./env.sh
. ./state/capture.conf
display="${DISPLAY_ID:-${DISPLAY:-:0}}"
ok=0
ng=0
check() {   # check "label" command...
  local label=$1
  shift
  if "$@" > /dev/null 2>&1; then
    echo "  ok  $label"; ok=$((ok + 1))
  else
    echo "  NG  $label"; ng=$((ng + 1))
  fi
}
py() { python3 -c "import sys; sys.path[:0] = ['bin', 'vendor']; $1"; }

echo "Android"
check "KVM (/dev/kvm)"            test -w /dev/kvm
check "java"                      command -v java
check "emulator"                  command -v emulator
check "adb"                       command -v adb
check "an AVD named setlog"       sh -c 'emulator -list-avds | grep -qx setlog'
echo "Desktop"
check "X display $display"        env DISPLAY="$display" python3 -c \
      "import sys; sys.path.insert(0, 'vendor'); from Xlib import display; display.Display()"
check "ffmpeg"                    command -v ffmpeg
echo "Python"
for m in PIL pygments fontTools Xlib; do
  check "module $m"               py "import $m"
done
echo "Fonts"
check "Noto Sans CJK"             py "import feed, os; assert os.path.isfile(feed.CJK.format('Regular'))"
check "DejaVu Sans Mono"          py "import feed, os; assert os.path.isfile(feed.DEJA)"
echo "Claude Code"
check "claude command"            command -v claude
check "hook in ~/.claude/settings.json" grep -q "$PWD/bin/on-prompt.sh" "$HOME/.claude/settings.json"

echo
echo "$ok ok, $ng NG"
[ "$ng" -eq 0 ]
