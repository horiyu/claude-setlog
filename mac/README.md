# Macからのリモート実行

別のMacからClaude Codeのセッションを送信するための任意設定です。本体の動作には必要ありません。

MacでClaudeに話しかけると、`setlog-hook.sh`が会話ログの直近部分と、Claudeが最後に触ったファイルをLinux PCへ送信します。ファイルは最大3件、1件あたり2 MB未満です。秘密情報を含みそうな名前のファイルと`~/.claude/`以下は除外します。
撮影・一言の生成・投稿はPC側で通常どおり行います（`bin/on-remote.sh`）。

通信経路にはTailscale SSHを想定しています。通信方向はMacからLinux PCへの一方向で、PC側に新しい常駐プロセスは追加しません。通常のsshdでも動作します。

## 1. PC側（初回のみ。sudoが必要です）

```sh
sudo tailscale set --ssh
```

Tailscaleの管理画面（Access controls）の`ssh`ルールが`"action": "check"`になっていると、ときどきブラウザでの再認証を求められ、再認証が必要な間はフックが失敗する場合があります。この失敗は画面には表示されません。
自分の端末どうしであれば`"action": "accept"`にしておくことを推奨します。

```json
"ssh": [{ "action": "accept", "src": ["autogroup:member"], "dst": ["autogroup:self"],
          "users": ["autogroup:nonroot"] }]
```

## 2. Mac側

```sh
scp you@your-linux-pc:claude-setlog/mac/setlog-hook.sh ~/.claude/setlog-hook.sh
chmod +x ~/.claude/setlog-hook.sh
cat > ~/.claude/setlog-hook.conf <<'EOF'
PC="you@your-linux-pc"                          # ssh の宛先（Tailscale のマシン名など）
REMOTE="claude-setlog/bin/on-remote.sh"         # PC 上の on-remote.sh（PC のホームからの相対パスで可）
EOF
ssh -o BatchMode=yes you@your-linux-pc true && echo "接続できました"
```

次のJSONオブジェクトを、`~/.claude/settings.json`の`hooks.UserPromptSubmit`配列に要素として追加します。設定ファイル全体を置き換える例ではありません。既存の設定とフックは残してください。

```json
{
  "hooks": [
    { "type": "command", "command": "~/.claude/setlog-hook.sh", "async": true, "timeout": 10 }
  ]
}
```

MacのClaude CodeにこのREADMEを読ませて「これを設定して」と頼む方法もあります。

## 3. 動作確認

MacでClaudeに何か話しかけてから、PCで次を実行します。

```sh
tail -3 claude-setlog/state/triggers.log   # "run kind=remote:<Mac の名前>" が出れば OK
```

ログが届かない場合は、次を確認してください。

- 送る内容が作れているか。Macで次を実行します。

  ```sh
  echo '{"transcript_path":"<会話の .jsonl>","session_id":"t"}' | SETLOG_DRY_RUN=/tmp/b.tgz ~/.claude/setlog-hook.sh
  sleep 2; tar tzf /tmp/b.tgz
  ```

- 経路が通っているか。Macで次を実行します。

  ```sh
  ssh -o BatchMode=yes you@your-linux-pc true
  ```

Linux PCの情報をMacの情報として表示しないよう、Macのセッションではシステムモニターを表示しません。
フォルダのウィンドウは、中のファイルが送られてきたときだけ表示されます。
