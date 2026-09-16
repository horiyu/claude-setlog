# claude-setlog

Claude Code に話しかけるたびに、Claude が作業している PC の画面を2秒 Vlog アプリ
[setlog](https://setlog.kr/) で撮って、Claude 自身の一言を添えて送る実験。
人ではなく、プログラムの一日が Vlog になる。

*Every time you talk to Claude Code, this draws the screen of the PC Claude is working
on, films it with the 2-second vlog app setlog inside an Android emulator, and posts it
with a one-line caption written by Claude. A day in the life of a program, not a person.*

![デモ](docs/demo.png)

## 使う前に（重要）

setlog 利用約款 第3条は「会社の許可なく自動化プログラム、ボット、スクリプト、クローラーを
使用する行為」を禁じている。このリポジトリは撮影ボタンのタップと送信を自動化するので、
**許可なく動かすと規約違反になる**。

作者は運営会社 New Chat に書面で相談し、自分のアカウント・自分のルームでの利用について
許可をもらった。この許可は作者個人に対するもので、このコードを使う人には及ばない。
使うなら、各自で New Chat に確認してほしい（問い合わせ先は setlog の公式サイトにある）。
作者は頻度を「1時間に1〜10回」に収めると約束していて、コードにも上限
（`bin/capture-log.sh` の `MAX_PER_HOUR=10`）が入っている。

## 何が起きるか

```
Claude Code にメッセージを送る
  └ UserPromptSubmit フック → bin/on-prompt.sh（すぐ返る。Claude は待たされない）
      └ bin/run-log.sh
          ├ Android エミュレータを起動（冷起動で約20秒）
          └ bin/capture-log.sh
              ├ bin/feed.py + bin/desktop.py  会話記録からデスクトップ画面を描いて動画にする
              ├ bin/mood.py                   claude -p で「いまの気持ち」を1行書く
              ├ setlog を開いて横向きにし、撮る → 一言を貼る → ルームに送る
              └ 動画のアップロードが終わるのを待つ
          └ エミュレータを止める
```

話しかけてから届くまで約1分半。**常駐するものは無い**。エミュレータは使うたびに起動して
止める（つけっぱなしにすると RAM を数十 GB まで食うことがあった）。

- この PC の Claude Code なら、どのセッションでも発動する（ターミナル、remote-control、
  Desktop の Code タブ、`claude -p`、ユーザー設定を読む SDK）。一言を作るための
  `claude -p` だけは `SETLOG_INNER=1` で除外している（除外しないと Log が次の Log を呼ぶ）。
- 撮影中にまた話しかけても二重には走らない（`state/run.lock`）。映すのは**直近に話しかけた
  セッション**で、エミュレータの起動を待つあいだに別のセッションで話しかければそちらが映る。
- 直近1時間の送信が10本に達していたら、エミュレータを起動する前にやめる。
- claude.ai のチャットやスマホアプリの Claude は Claude Code ではないので、フックが効かない。
- （任意）別のマシン（Mac など）の Claude Code から発動させることもできる →
  [mac/README.md](mac/README.md)

## 画面

**キャプチャではなく描き起こし**。デスクトップも VM も立ち上げず、会話記録（`~/.claude/projects/*/*.jsonl`）
から絵を描いている。だからスマホやウェブから指示した、画面の無いセッションでも同じように映る。

手前に Claude Code のターミナル、その奥に、会話の中で Claude が使ったものに応じた窓が2枚:

| 会話の中で Claude が… | 出る窓 |
|---|---|
| コードを Read / Edit / Write | エディタ（そのファイル。書き換えた行を緑に） |
| WebFetch | ブラウザ（URL とページの中身） |
| WebSearch | Google の検索結果ページ |
| Slack / Notion / Gmail / Google カレンダー / Google ドライブ / Figma の MCP | そのアプリ風の画面 |
| 画像ファイルを Read | 画像ビューア（その画像） |
| `lscpu` `free` `nvidia-smi` `ps` `df` など | システムモニター（この PC の実測 CPU・メモリ・GPU） |
| `ls` / `find` / Glob | ファイルマネージャ（そのフォルダの実際の中身） |

- アプリの画面は**見た目だけ真似た絵**で、本物のアプリは動かさない。発言・件名・予定・
  ファイル名などの中身は、会話の中で Claude が送ったり読んだりしたものから取る。
- 直近に使った種類が大きい窓、その前の種類が小さい窓。配置は毎回ランダムで、ターミナルが
  左右どちらに来るか、窓の大きさと位置、奥の2枚の重なり順が変わる。
- マウスは見えている場所（URL バー、書き換えた行、アイコン、入力欄など）から3〜5か所を選んで
  回る。曲がり方・速さ・止まる時間・クリックの有無も毎回変わる。
- `state/capture.conf` で `SCENE=terminal` にすると、ターミナルだけの表示になる。

## 一言

`bin/mood.py` が `claude -p`（既定は Haiku、`SETLOG_MOOD_MODEL` で変更）に書かせる。
作業の要約ではなく「いまの気持ち」を、人間みのある、JK っぽい言い回しで1行。作業の中の
具体的なもの（ファイル名、エラー、数字）を一つ拾わせ、直近10件と被らないようにしている。
プロンプトは mood.py の中にあるので、好みに書き換えてほしい。

`adb shell input text` は日本語を通さないので、一言は `bin/clip.py` で X のクリップボードに
載せ、エミュレータのクリップボード共有で Android に渡してから貼り付けている。

## 前提と制約

clone すればそのまま動く、というものではない。次の前提がある。

- **動作確認は作者の環境だけ。** Linux（X11）、Android Emulator 37.1、
  2026年9月時点の setlog で確かめている。
- **setlog のアカウントとルームは自分で用意する。** エミュレータ上の Play ストアへのサインイン、
  setlog のインストールとログイン、投稿先ルームの作成は手作業（意図的に自動化していない）。
- **タップ位置は座標で決め打ち。** 1080x2400 の AVD と、今の setlog の画面構成に合わせてある。
  setlog の画面が変わると止まる。別の画面サイズなら `state/capture.conf` の `TAP_*` を合わせる。
- **`claude` コマンドにログインしていること。** 一言の生成に `claude -p` を使う。
- **setlog の規約上、自動化には運営会社の許可が要る**（上の「使う前に」）。

## 必要なもの

- Linux の X11 デスクトップ（エミュレータのウィンドウとクリップボード共有を使う）と KVM
- Android SDK: `emulator`、`platform-tools`、`cmdline-tools`、Google Play 入りのシステムイメージ
  （動作確認は `system-images;android-35;google_apis_playstore;x86_64`）、JDK 17 以上
- Python 3.10 以上（Pillow / Pygments / fontTools / python-xlib）と `ffmpeg`
- フォント: Noto Sans CJK（`fonts-noto-cjk`）、DejaVu（`fonts-dejavu`）。JetBrains Mono があれば使う
- [Claude Code](https://claude.com/claude-code)（`claude` コマンド。一言の生成にも使う）
- setlog のアカウントと、投稿先のルーム
- （任意）`nvidia-smi`。あればシステムモニターに GPU が出る

## セットアップ

1. 取ってきて依存を入れる。

   ```sh
   git clone https://github.com/horiyu/claude-setlog && cd claude-setlog
   ```

   Python の依存は、どちらかで入れる。スクリプトは `python3` を直に呼ぶので、**仮想環境に
   入れたときは `SETLOG_PYTHON` でその Python を指す**こと（`env.sh` が読む）。

   ```sh
   # 1) OS のパッケージで入れる（最近の Ubuntu / Debian は pip を直接使えない）
   sudo apt install python3-pil python3-pygments python3-fonttools python3-xlib ffmpeg

   # 2) 仮想環境に入れる
   sudo apt install python3-venv            # 無ければ
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   export SETLOG_PYTHON="$PWD/.venv/bin/python"   # ~/.profile などに書いておく
   ```

   設定は `state/capture.conf`（初回に `state/capture.conf.example` からコピーされる）。
   足りないものは `bin/doctor.sh` で確かめられる（何も変更しない）。

2. JDK と Android SDK を `jdk/` と `sdk/` に置く（別の場所なら `env.sh` を書き換える）。
   AVD は `avd/` に作る。画面は 1080x2400（タップ位置がこのサイズで決めてある）。

   ```sh
   . ./env.sh
   sdkmanager "platform-tools" "emulator" "system-images;android-35;google_apis_playstore;x86_64"
   avdmanager create avd -n setlog -k "system-images;android-35;google_apis_playstore;x86_64" -d pixel_7
   ```

3. **初回だけ手作業。** エミュレータを起動して、Play ストアにサインインし、setlog を入れて
   ログインし、投稿先のルームを作る。ここは自動化しない。

   ```sh
   . ./env.sh && emulator -avd setlog -camera-back "videofile:$PWD/state/card.mp4"
   ```

   送信画面で、投稿先のルームが上から2行目（自分だけの vlog の次）に来る想定。違うときは
   `state/capture.conf` に `TAP_ROOM="x y"` を書く。

4. 手で1本撮って確かめる。

   ```sh
   bin/run-log.sh && tail /tmp/setlog-run.log
   ```

5. フックを入れる。`~/.claude/settings.json` の `hooks.UserPromptSubmit` に**追加**する
   （既存のフックは消さない）。パスは clone した場所に合わせる:

   ```json
   {
     "hooks": [
       { "type": "command", "command": "/path/to/claude-setlog/bin/on-prompt.sh",
         "async": true, "timeout": 10 }
     ]
   }
   ```

## 設定

`state/capture.conf`（シェルの変数として読まれる）:

| 変数 | 既定 | 意味 |
|---|---|---|
| `SCENE` | `desktop` | `desktop` = デスクトップごと描く、`terminal` = ターミナルだけ |
| `ORIENT` | `landscape` | setlog は横向きでしか撮らないので、通常はこのまま |
| `SETLOG_PROJECT` | `*` | 追う会話記録の glob（`~/.claude/projects/` の下） |
| `DISPLAY_ID` | 空（`$DISPLAY`、無ければ `:0`） | エミュレータとクリップボードに使う X のディスプレイ。フックは画面の無いセッションからも呼ばれるので、決まっているなら書いておく |
| `TAP_RECORD` / `TAP_ROOM` / `TAP_SEND` | 1080x2400 用 | 撮影ボタン・ルームの行・送信ボタンのタップ位置 |

環境変数: `SETLOG_PYTHON`（描画と一言に使う Python。仮想環境に入れたときに指す）、
`SETLOG_USER`（アプリ画面に出す名前。既定はログインユーザー名）、
`SETLOG_MONO_FONT`（等幅フォント）、`SETLOG_MOOD_MODEL`（一言を書くモデル）。

## 記録と確認

```sh
tail state/triggers.log      # 発動の記録（run / skip と、どのセッションか）
tail /tmp/setlog-run.log     # 起動・撮影・送信・停止の経過
tail state/posts.jsonl       # 送った一言と、アップロードした量
```

送信直前の画面は `state/last-send.png`、送信後のルーム一覧は `state/last-sent.png` に残る。

## 気をつけること

**会話の中身がそのまま写る。** コマンド、出力、開いたファイルの中身、Web ページや Slack の
本文、ファイル名。`.env` や `secret`・`token`・`.pem` などを含む名前のファイルと
`~/.claude/` の下は映さないようにしているが、それ以外は写る。自分だけのルームで使うのが前提で、
人に見せる前には中身を自分の目で確かめてほしい。

## 実測して分かったこと

- **setlog は横向きでしか撮らない**（"rotate to capture"）。エミュレータを横にするには画面回転
  ではなく加速度センサーを傾ける: `adb emu sensor set acceleration -9.81:0:0`（戻すときは
  `0:9.81:0.8`）。
- センサーで横にした状態では、**Log は正立のまま、ソースの上端 16:9 の帯（1710x962）が写る**。
  ソース動画は 1710x1280（エミュレータは 4:3 のセンサーとして扱う）で、描いた画面を上端に置く。
- エミュレータは**カメラセッションを開いた時点の動画を掴む**。再生中に動画を差し替えても
  映像は変わらないので、毎回 setlog を開き直している。
- **「sent」は押した瞬間に出るが、動画は後から裏でアップロードされる。** 送信直後に
  エミュレータを止めると、相手には「sent」だけが届いて動画が来ない。送信後はゲストの送信
  バイト数を見て、150KB 以上出てから9秒静かになるまで待つ（最長約3分）。
- setlog はインカメラだと鏡像になる。背面カメラを使う。
- setlog の画面は uiautomator から文字を読めない（動画の再生中は dump もできない）ので、
  送信画面のタップ位置は座標で決め打ちしている。
- 送信画面を開いた時点でキャプション欄にフォーカスがあるので、貼り付けにタップは要らない。
- Claude Code は thinking を暗号化して保存する。画面に出せるのは指令・応答・ツール呼び出しなど、
  平文で残るものだけ。
- 一言を作る `claude -p` も会話記録を書くので、「最後に動いたセッション」を追うと自分自身を
  映してしまう。プロンプトに `SETLOG_MOOD_CALL` を埋めて弾き、cwd も `/tmp/setlog-mood` に逃がす。

## 旧モード

- `bin/start.sh` / `bin/stop.sh`: 画面の描画と一言の生成を常駐させ、エミュレータを
  つけっぱなしにするモード。校正やデバッグのとき用。
- `state/capture.conf` の `SOURCE=window`: 描き起こしの代わりに、実在の X11 ウィンドウを
  `bin/screencast.sh` で撮る（`bin/pick-window.sh` で窓を選ぶ）。
- `bin/shoot.sh`: 標準カメラで1枚撮って、切り出し範囲を測る（校正用）。
- `bin/render.py` / `bin/say.py` / `bin/caption.py` / `bin/capture.py`: 初期版の名残。

## 作者・ライセンス

作: [horiyu](https://github.com/horiyu)。[MIT License](LICENSE)。
使ったり改変したりするときは、LICENSE の著作権表示（Copyright (c) 2026 horiyu）を残してほしい。
