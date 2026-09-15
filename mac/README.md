# （任意）Mac など別のマシンの Claude Code から Log を送る

使わなくても本体は動く。別のマシンでも Claude Code を使っていて、そちらで話しかけたときも
Log にしたい場合だけ。

Mac で Claude に話しかけると、`setlog-hook.sh` がその会話の直近部分と、Claude が最後に
触ったファイル（最大3つ、2MB 未満、秘密っぽい名前と `~/.claude/` は除く）を、
claude-setlog を動かしている Linux PC に送る。撮影・一言・送信は PC 側でいつもどおり行う
（`bin/on-remote.sh`）。

経路は Tailscale SSH を想定している。Mac → PC の一方向だけで、PC 側に新しい常駐は増えない
（tailscaled が受ける）。普通の sshd でも動く。

## 1. PC 側（1回だけ、sudo が要る）

```sh
sudo tailscale set --ssh
```

Tailscale の管理画面（Access controls）の `ssh` ルールが `"action": "check"` だと、ときどき
ブラウザでの再認証を求められ、そのあいだフックは黙って失敗する。自分の端末どうしなら
`"action": "accept"` にしておく:

```json
"ssh": [{ "action": "accept", "src": ["autogroup:member"], "dst": ["autogroup:self"],
          "users": ["autogroup:nonroot"] }]
```

## 2. Mac 側

```sh
scp you@your-linux-pc:claude-setlog/mac/setlog-hook.sh ~/.claude/setlog-hook.sh
chmod +x ~/.claude/setlog-hook.sh
cat > ~/.claude/setlog-hook.conf <<'EOF'
PC="you@your-linux-pc"                          # ssh の宛先（Tailscale のマシン名など）
REMOTE="claude-setlog/bin/on-remote.sh"         # PC 上の on-remote.sh（PC のホームからの相対でよい）
EOF
ssh -o BatchMode=yes you@your-linux-pc true && echo "つながった"
```

`~/.claude/settings.json` の `hooks.UserPromptSubmit` に**追加**する（既存のフックは消さない）:

```json
{
  "hooks": [
    { "type": "command", "command": "~/.claude/setlog-hook.sh", "async": true, "timeout": 10 }
  ]
}
```

Mac の Claude Code にこの README を読ませて「これを入れて」と頼んでもいい。

## 3. 確かめる

Mac で Claude に何か話しかけて、PC で:

```sh
tail -3 claude-setlog/state/triggers.log   # "run kind=remote:<Macの名前>" が出ればOK
```

届かないとき:
- Mac で `echo '{"transcript_path":"<会話の.jsonl>","session_id":"t"}' | SETLOG_DRY_RUN=/tmp/b.tgz ~/.claude/setlog-hook.sh; sleep 2; tar tzf /tmp/b.tgz`
  → 送る中身が作れているか
- Mac で `ssh -o BatchMode=yes you@your-linux-pc true` → 経路が通っているか

Mac の会話ではシステムモニターは出さない（描けるのは PC の数値だけで、Mac の話としては
嘘になるため）。フォルダの窓は、中のファイルが送られてきたときだけ出る。
