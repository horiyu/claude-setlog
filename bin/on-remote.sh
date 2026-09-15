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
dir="$SETLOG_HOME/state/remote/$host-$sid"
tmp=$(mktemp -d "$SETLOG_HOME/state/remote/.in.XXXXXX")

# GNU tar drops leading "/" and refuses ".." members; 20 MB is far more than a Log needs.
if ! head -c 20000000 | tar xzf - -C "$tmp" --no-same-owner --no-same-permissions 2>/dev/null \
   || [ ! -s "$tmp/transcript.jsonl" ]; then
  rm -rf "$tmp"
  echo "$(date '+%F %T') skip kind=remote:$host bad bundle" >> "$SETLOG_HOME/state/triggers.log"
  exit 1
fi
rm -rf "$dir" && mv "$tmp" "$dir"
ls -dt "$SETLOG_HOME"/state/remote/*/ 2>/dev/null | tail -n +6 | xargs -r rm -rf   # keep 5

transcript="$dir/transcript.jsonl"
echo "$(date '+%F %T') run kind=remote:$host $transcript" >> "$SETLOG_HOME/state/triggers.log"
printf '%s\n' "$transcript" > "$SETLOG_HOME/state/latest-transcript.tmp" &&
  mv "$SETLOG_HOME/state/latest-transcript.tmp" "$SETLOG_HOME/state/latest-transcript"
SETLOG_TRANSCRIPT="$transcript" setsid nohup "$SETLOG_HOME/bin/run-log.sh" \
  >> /tmp/setlog-run.log 2>&1 < /dev/null &
exit 0
