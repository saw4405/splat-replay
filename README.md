# Splat Replay

## 概要

スプラトゥーンのプレイをスマートフォンやPC等で見返せるよう、プレイ動画を録画してYouTubeにアップロードします。
スプラトゥーンにはメモリープレイヤー機能がありますが、Switchを起動しないとプレイ動画を見れないため、もっと手軽に見返せるよう本スクリプトを作成することにしました。

## 機能

* バトルのプレイ動画を自動で録画する (`recorder.py`)
  * OBSを起動する
  * OBSの仮想カメラ機能を有効にする
  * バトル開始を検知し、録画を開始する
  * バトル終了を検知し、録画を停止する
  * バトル終了時に勝敗・マッチ・ルールを自動判定する
  
* 録画した動画をYouTubeに指定した時刻にアップロードする (`uploader.py`)
  * 設定した時刻になったら、スケジュール・マッチ・ルール毎にプレイ動画を結合する
  * スケジュール・マッチ・ルールをタイトルに、勝敗を説明に設定し、YouTubeにアップロードする

## 使い方

### 動作確認環境

* Windows 11 23H2
* OBS 30.2.3
* Python 3.12.8
* FFmpeg N-109468-gd39b34123d-20221230

### 前提条件

* OBS(28.0.0以降)をインストールしていること
  * OBSのソースを設定しておくこと [[参考]](https://dc.wondershare.jp/recorder-review/how-to-use-obs-and-capture-board.html)
  * OBSのWebSocket機能を有効にしていること [[参考]](https://note.com/213414/n/nd9981ad5bb19)
  * 必要に応じてOBSの録画設定をしておくこと [[参考]](https://obsproject.com/kb/standard-recording-output-guide)
* Pythonをインストールしていること
* YouTubeの認証情報を取得し、YouTubeAPIを有効化しておくこと [[参照]](https://qiita.com/ny7760/items/5a728fd9e7b40588237c)
  * 認証情報をjsonファイルとしてダウンロードしておく
  * 15分以上の動画をアップロードできるよう、YouTubeアカウントの確認を実施しておく [[参照]](https://www.howtonote.jp/youtube/movie/index4.html#google_vignette)
* FFmpegをインストールしていること [[参照]](https://taziku.co.jp/blog/windows-ffmpeg)
  * パスを通しておくこと

### 初回手順

1. 本リポジトリをクローンする

2. YouTubeの認証情報を`client_secrets.json`として保存する

3. パッケージをインストールする

    ```bash
    pip install -r requirements.txt
    ```

    * `opencv-python`
        * バトルの開始・終了等を検知するために使用
    * `obs-websocket-py`
        * OBSで録画等をするために使用 (OpenCVでは音声を含む動画を録画できないためOBSを使用)
    * `psutil`
        * OBSの起動有無を確認するために使用
    * `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`
        * YouTubeに動画をアップロードするために使用
    * `python-dotenv`
        * `.env`ファイルから環境変数を読み込むために使用
    * `schedule`
        * 動画のアップロードを定期的にバッチ処理するために使用

4. `.example.env`を`.env`にリネームし、OBSのWebSocketのパスワード等を設定する

5. `templates`フォルダに画像認識するためのテンプレート画像を保存する
   (`templates(sample)`フォルダ内の画像を参考にしてください)
  
    1. OBSを起動した状態でバトルをする
    2. 判定に使用する画面のスクリーンショットをとる
       * バトル開始時に敵・味方のプレートが表示されている画面
         * `start.png`
       * バトル終了時に勝敗判定をしている画面
         * `win.png`、`lose.png`
       * バトル終了後に自分のキルレや表彰が表示されている画面
         * `stop.png`、`regular.png`、`bankara_challenge.png`、`bankara_open.png`、`x.png`、`nawabari.png`、`area.png`、`asari.png`、`hoko.png`、`yagura.png`
    3. トリミングする

### 録画手順

1. Switch・キャプチャボード・PCを接続する

2. 本アプリを起動する

    ```bash
    python main.py
    ```

3. YouTubeの認証情報を求められたら、認証する

4. バトルをして、後はお任せ
