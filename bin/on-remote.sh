#!/bin/bash
# Entry point for Claude Code on another machine (the Mac). Its UserPromptSubmit hook
# (mac/setlog-hook.sh) streams a tar.gz here over Tailscale SSH: transcript.jsonl (the
# tail of that session) and root/ holding the few files Claude last touched, under
# their original absolute paths. Unpack it, film it next, run the usual pipeline.
#
#   tar czf - ... | ssh you@this-pc claude-setlog/bin/on-remote.sh <session> <host>
SETLOG_HOME="$(cd "$(dirname "$0")/.." && pwd)"
sid=$(printf '%s' "${1:-unknown}" | tr -cd 'A-Za-z0-9._-' | cut -c1-80)
host=$(printf '%s' "${2:-remote}" | tr -cd 'A-Za-z0-9._-' | cut -c1-40)
mkdir -p "$SETLOG_HOME/state/remote"
# Every bundle gets its own directory, and nothing is deleted here: a Log may be
# drawing from an earlier bundle right now (the caption alone can take minutes).
# run-log.sh prunes old bundles once a capture has finished, under its lock.
dir=$(mktemp -d "$SETLOG_HOME/state/remote/$host-$sid.XXXXXX")

# GNU tar drops leading "/" and refuses ".." members; 20 MB is far more than a Log needs.
if ! head -c 20000000 | tar xzf - -C "$dir" --no-same-owner --no-same-permissions 2>/dev/null \
   || [ ! -s "$dir/transcript.jsonl" ]; then
  rm -rf "$dir"
  echo "$(date '+%F %T') skip kind=remote:$host bad bundle" >> "$SETLOG_HOME/state/triggers.log"
  exit 1
fi

transcript="$dir/transcript.jsonl"
echo "$(date '+%F %T') run kind=remote:$host $transcript" >> "$SETLOG_HOME/state/triggers.log"
printf '%s\n' "$transcript" > "$SETLOG_HOME/state/latest-transcript.tmp" &&
  mv "$SETLOG_HOME/state/latest-transcript.tmp" "$SETLOG_HOME/state/latest-transcript"
SETLOG_TRANSCRIPT="$transcript" setsid nohup "$SETLOG_HOME/bin/run-log.sh" \
  >> /tmp/setlog-run.log 2>&1 < /dev/null &
exit 0
