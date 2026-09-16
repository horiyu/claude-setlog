#!/bin/bash
# UserPromptSubmit hook (~/.claude/settings.json): each time the user talks to Claude,
# take one Log while Claude works on the answer. Returns at once; the work is
# detached into bin/run-log.sh so the prompt is never held up.
SETLOG_HOME="$(cd "$(dirname "$0")/.." && pwd)"
input=$(cat)
kind="${CLAUDE_CODE_ENVIRONMENT_KIND:-}/${CLAUDE_CODE_ENTRYPOINT:-}"

# Every Claude Code session on this PC counts: terminal, remote-control, Desktop,
# claude -p, SDK. The one exception is our own claude -p from mood.py, or each Log
# would trigger the next. (kind is logged only; it can't tell sessions apart anyway,
# since a claude -p started inside a bridge session inherits "bridge".)
decision=run
[ -n "${SETLOG_INNER:-}" ] && decision=skip

transcript=$(printf '%s' "$input" | "${SETLOG_PYTHON:-python3}" -c \
  'import sys,json; print(json.load(sys.stdin).get("transcript_path",""))' 2>/dev/null)
# Without a transcript path (malformed input, or a hook payload without one) the feed
# would fall back to whichever session was written last, which need not be the one
# spoken to; skip instead. Only the shape is checked: on a session's first prompt the
# file does not exist yet, and is written by the time the emulator has booted.
case $transcript in
  /*.jsonl) ;;
  *) [ "$decision" = run ] && { decision=skip; transcript="no transcript"; } ;;
esac
echo "$(date '+%F %T') $decision kind=$kind $transcript" >> "$SETLOG_HOME/state/triggers.log"

if [ "$decision" = run ]; then
  # Remember who was spoken to last. A run already booting reads this when it starts
  # drawing, so a question asked in another session seconds later is what gets filmed.
  printf '%s\n' "$transcript" > "$SETLOG_HOME/state/latest-transcript.tmp" &&
    mv "$SETLOG_HOME/state/latest-transcript.tmp" "$SETLOG_HOME/state/latest-transcript"
  SETLOG_TRANSCRIPT="$transcript" setsid nohup "$SETLOG_HOME/bin/run-log.sh" \
    >> /tmp/setlog-run.log 2>&1 < /dev/null &
fi
exit 0
