# （任意）Mac など別のマシンの Claude Code から Log を投稿する

この設定は必須ではなく、本体だけでも動作します。
別のマシンでも Claude Code を使っていて、そちらで話しかけたときも Log にしたい場合にのみ設定してください。

Mac で Claude に話しかけると、`setlog-hook.sh` がその会話の直近部分と、Claude が最後に触ったファイル（最大 3 つ、2 MB 未満、秘密情報を含みそうな名前と `~/.claude/` 以下は除く）を、claude-setlog を動かしている Linux PC に送ります。
撮影・一言の生成・投稿は PC 側で通常どおり行います（`bin/on-remote.sh`）。

経路は Tailscale SSH を想定しています。Mac → PC の一方向のみで、PC 側に新しい常駐プロセスは増えません（tailscaled が受け付けます）。
通常の sshd でも動作します。

## 1. PC 側（初回のみ。sudo が必要です）

```sh
sudo tailscale set --ssh
```

Tailscale の管理画面（Access controls）の `ssh` ルールが `"action": "check"` になっていると、ときどきブラウザでの再認証を求められ、そのあいだフックは黙って失敗します。
自分の端末どうしであれば `"action": "accept"` にしておくことを推奨します。

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
REMOTE="claude-setlog/bin/on-remote.sh"         # PC 上の on-remote.sh（PC のホームからの相対パスで可）
EOF
ssh -o BatchMode=yes you@your-linux-pc true && echo "接続できました"
```

`~/.claude/settings.json` の `hooks.UserPromptSubmit` に**追加**してください（既存のフックは消さないでください）。

```json
{
  "hooks": [
    { "type": "command", "command": "~/.claude/setlog-hook.sh", "async": true, "timeout": 10 }
  ]
}
```

Mac の Claude Code にこの README を読ませて「これを設定して」と頼む方法もあります。

## 3. 動作確認

Mac で Claude に何か話しかけてから、PC で次を実行します。

```sh
tail -3 claude-setlog/state/triggers.log   # "run kind=remote:<Mac の名前>" が出れば OK
```

届かない場合は、次を確認してください。

- 送る内容が作れているか。Mac で次を実行します。

  ```sh
  echo '{"transcript_path":"<会話の .jsonl>","session_id":"t"}' | SETLOG_DRY_RUN=/tmp/b.tgz ~/.claude/setlog-hook.sh
  sleep 2; tar tzf /tmp/b.tgz
  ```

- 経路が通っているか。Mac で次を実行します。

  ```sh
  ssh -o BatchMode=yes you@your-linux-pc true
  ```

Mac の会話ではシステムモニターは表示しません（描けるのは PC の数値だけで、Mac の話としては正しくないためです）。
フォルダのウィンドウは、中のファイルが送られてきたときだけ表示されます。
