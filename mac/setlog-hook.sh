#!/bin/bash
# claude-setlog, Mac side: a UserPromptSubmit hook for Claude Code on the Mac.
# When you talk to Claude here, send the session's recent transcript and the few files
# Claude last touched to the Linux PC running claude-setlog, which draws, films and
# sends the Log. Returns at once; the upload runs in the background.
# (bash 3.2 compatible: this is macOS.)

# Where to send. Set these in ~/.claude/setlog-hook.conf, which is sourced if present.
PC="you@your-linux-pc"                     # ssh destination, e.g. its Tailscale name
REMOTE="claude-setlog/bin/on-remote.sh"    # on-remote.sh on the PC (relative to its home)
[ -f "$HOME/.claude/setlog-hook.conf" ] && . "$HOME/.claude/setlog-hook.conf"
PC="${SETLOG_PC:-$PC}"

input=$(cat)
[ -n "$SETLOG_INNER" ] && exit 0
field() { printf '%s' "$input" | sed -n "s/.*\"$1\" *: *\"\([^\"]*\)\".*/\1/p" | head -1; }
transcript=$(field transcript_path)
sid=$(field session_id)
[ -f "$transcript" ] || exit 0

(
  stage=$(mktemp -d /tmp/setlog.XXXXXX) || exit 1
  tail -n 400 "$transcript" > "$stage/transcript.jsonl"
  mkdir -p "$stage/root"
  # The last three files Claude touched, newest first, if small and not secret.
  grep -o '"file_path" *: *"[^"]*"' "$stage/transcript.jsonl" | sed 's/.*: *"//; s/"$//' |
    awk '{a[NR]=$0} END {for (i = NR; i > 0; i--) if (!seen[a[i]]++) print a[i]}' | head -3 |
    while IFS= read -r f; do
      case "$f" in "$HOME"/.claude/*) continue ;; esac
      case "$(printf '%s' "$f" | tr 'A-Z' 'a-z')" in
        *.env*|*secret*|*token*|*credential*|*id_rsa*|*.pem|*.key|*password*) continue ;;
      esac
      [ -f "$f" ] || continue
      size=$(wc -c < "$f" 2>/dev/null | tr -d ' ')      # stat differs between macOS and Linux
      [ "${size:-99999999}" -lt 2000000 ] || continue
      mkdir -p "$stage/root$(dirname "$f")" && cp "$f" "$stage/root$f"
    done
  if [ -n "$SETLOG_DRY_RUN" ]; then            # testing: write the bundle to a file instead
    tar czf "$SETLOG_DRY_RUN" -C "$stage" transcript.jsonl root
  else
    tar czf - -C "$stage" transcript.jsonl root |
      ssh -o BatchMode=yes -o ConnectTimeout=8 "$PC" "$REMOTE" "${sid:-mac}" "$(hostname -s)"
  fi
  rm -rf "$stage"
) > /dev/null 2>&1 &
exit 0
