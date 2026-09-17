# 補助機能と旧機能

通常の投稿フローでは使用しない、校正・デバッグ用の機能です。

## 常駐モード

`bin/start.sh`と`bin/stop.sh`は、画面描画とキャプション生成を常駐させ、Android Emulatorを起動したままにします。通常は`bin/run-log.sh`を使用してください。

## 実ウィンドウの撮影

常駐モードでは、`state/capture.conf`に`SOURCE=window`を指定すると、実際のX11ウィンドウを撮影します。

- `bin/pick-window.sh`: 撮影対象を選択
- `bin/screencast.sh`: ウィンドウを動画へ変換
- `bin/screencast-stop.sh`: 撮影を停止

## 校正用スクリプト

`bin/shoot.sh`は標準カメラで静止画を撮影し、映像の切り出し範囲を確認するためのスクリプトです。

初期版の`bin/capture.py`はStopフックから会話の要約を`state/thought.json`へ保存し、`bin/caption.py`でキャプション画像を生成します。現在の標準フローでは使用しません。
