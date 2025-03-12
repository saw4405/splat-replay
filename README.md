# Splat Replay

## 概要

スプラトゥーンのプレイをスマートフォンやPC等で見返せるよう、プレイ動画を録画してYouTubeにアップロードします。
スプラトゥーンにはメモリープレイヤー機能がありますが、Switchを起動しないとプレイ動画を見れないため、もっと手軽に見返せるよう本スクリプトを作成することにしました。

## 機能

* バトルのプレイ動画を自動で録画し、マイク入力を字幕に追加する (`recorder.py`)
  * OBSを起動し、仮想カメラ機能を有効にする
  * Xマッチ選択時にXPを読み取る
  * バトル開始を検知し、録画と文字起こしを開始する
  * バトル終了を検知し、録画と文字起こしを停止する
  * バトル終了時に勝敗・マッチ・ルール・ステージを自動判定する
* 録画した動画をYouTubeににアップロードする (`uploader.py`)
  * 設定した時トリガがかかったら、スケジュール・マッチ(ルール)毎にプレイ動画を結合する
    * トリガは時刻指定、もしくはSwitch電源OFFのどちらかを選択可能
  * スケジュール・マッチ・ルール・XP・勝敗をタイトルに、勝敗・XP・ステージを説明に設定し、YouTubeにアップロードする
  * 武器・ギア・マッチ・ルール・XP・ステージ情報をサムネイル画像として自動生成し、YouTubeのサムネイルに自動設定する

## 使い方

### 動作確認環境

* Windows 11 23H2
* OBS 31.0.1
* Python 3.13.2
* uv 0.5.29 (ca73c4754 2025-02-05)
* FFmpeg N-109468-gd39b34123d-20221230
* tesseract v5.5.0.20241111

### 前提条件

* OBS(28.0.0以降)をインストールしていること
  * OBSのソースを設定しておくこと [[参考]](https://dc.wondershare.jp/recorder-review/how-to-use-obs-and-capture-board.html)
  * OBSのWebSocket機能を有効にしていること [[参考]](https://note.com/213414/n/nd9981ad5bb19)
  * 必要に応じてOBSの録画設定をしておくこと [[参考]](https://obsproject.com/kb/standard-recording-output-guide)
* Pythonをインストールしていること
* uvをインストールしていること [[参考]](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)
* YouTubeの認証情報を取得し、YouTube APIを有効化しておくこと [[参照]](https://qiita.com/ny7760/items/5a728fd9e7b40588237c)
  * 認証情報をjsonファイルとしてダウンロードする
  * 15分以上の動画をアップロードできるよう、YouTubeアカウントの確認を実施しておく [[参照]](https://www.howtonote.jp/youtube/movie/index4.html#google_vignette)
* FFmpegをインストールしていること [[参照]](https://taziku.co.jp/blog/windows-ffmpeg)
  * パスを通しておく
* Tesseractをインストールしていること [[参照]](https://qiita.com/ku_a_i/items/93fdbd75edacb34ec610)
  * best版の`eng.traineddata`をダウンロードし、Tesseractインストール先(`C:\Program Files\Tesseract-OCR`)の`tessdata`フォルダに保存する
* イカモドキフォントをダウンロードしておくこと [[参照]](https://web.archive.org/web/20150906013956/http://aramugi.com/?page_id=807)
  * イカモドキフォントは二次配布が禁止されているため (Project Paintballフォントは二次配布が許可されているため、本プロジェクトに同梱)
  * サムネイル画像を自動生成するためにフォントファイルを使用している
* GroqのAPIキーを取得しておくこと [[参照]](https://zenn.dev/mizunny/articles/58be26d25f9589)

### 初回手順

1. 本リポジトリをクローンする

    ```bash
    git clone https://github.com/saw4405/splat-replay.git
    ```

2. YouTubeの認証情報を`client_secrets.json`として保存する

3. イカモドキフォントを`assets\thumbnail`フォルダに保存する

4. 仮想環境を作成してアクティベートする

    ```bash
    uv venv
    .venv\Scripts\activate
    ```

5. パッケージをインストールする

    ```bash
    uv sync
    ```

    * `opencv-python`：バトルの開始・終了等を検知するために使用
    * `obs-websocket-py`：OBSで録画等をするために使用 (OpenCVでは音声を含む動画を録画できないためOBSを使用)
    * `psutil`：OBSの起動有無を確認するために使用
    * `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`：YouTubeに動画をアップロードするために使用
    * `python-dotenv`：`.env`ファイルから環境変数を読み込むために使用
    * `schedule`：動画のアップロードを定期的にバッチ処理するために使用
    * `pytesseract`：XPの読み込み等でOCRを使うために使用
    * `pywin32`：キャプチャボードの接続確認のために使用
    * `pyaudio`：マイク入力を取得するために使用
    * `speechrecognition`：音声を文字起こしするために使用
    * `groq`：音声を文字起こしするためと、音声認識の補正をするために使用

6. `.example.env`を`.env`にリネームする

7. `.env`の環境変数を設定する
    特に設定が必要な環境変数は以下

    - `CAPTURE_DEVICE_INDEX`：`src\test_capture_device.py`を使ってキャプチャデバイスが認識されているインデックスを設定する
    - `CAPTURE_DEVICE_NAME`：接続しているキャプチャデバイス名を設定する (OBS等で名称を調査)
    - `MIC_DEVICE`：文字起こしする場合、マイクデバイス名を設定する (OBS等で名称を調査)
    - `OBS_WS_PASSWORD`：WebSocket機能を有効にしたときのパスワードを設定する
    - `GROQ_API_KEY`：文字起こしする場合、取得したGroqのAPIキーを設定する

8. SwitchをPower OFFしたとき、キャプチャボードからの入力が黒画面でない場合、その画像を取得する

    1. Switch・キャプチャボード・PCを接続する
    2. Switchを起動する
    3. OBSを起動する
    4. ゲーム画面が表示されたら、SwitchをPower OFFする
    5. OBSでスクリーンショットを撮る
    6. `assets\templates`フォルダに`power_off.png`として保存する



### 録画手順

1. Switch・キャプチャボード・PCを接続する

2. 本アプリを起動する

    ```bash
    python main.py
    ```

3. YouTubeの認証情報を求められたら、認証する

4. バトルをして、後はお任せ
