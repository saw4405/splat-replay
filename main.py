import os
import time
import datetime
import locale
from typing import Dict
from enum import Enum

import cv2
import numpy as np
import dotenv

from obs import Obs
from template_matcher import TemplateMatcher
from youtube import Youtube


class RecordStatus(Enum):
    OFF = 1
    WAIT = 2
    RECORD = 3



def upload_video(youtube, path, title, description, privacy_status):
    try:
        print("YouTubeにアップロードを開始します")
        youtube.upload(path, title, description, privacy_status)
        print("YouTubeにアップロードしました")
    except Exception as e:
        print(f"アップロード中にエラーが発生しました: {e}")
        
def is_screen_off(image: np.ndarray) -> bool:
    if image.max() <= 10:
        return True
    return False

def main():
    
    # 画像判定に使用する画像を読み込んでおく
    start_matcher = TemplateMatcher("templates\\start.png")
    stop_matcher = TemplateMatcher("templates\\stop.png")
    win_matcher = TemplateMatcher("templates\\win.png")
    lose_matcher = TemplateMatcher("templates\\lose.png")
    match_matchers: Dict[str, TemplateMatcher] = {
        "レギュラーマッチ": TemplateMatcher("templates\\regular.png"),
        "バンカラマッチ(チャレンジ)": TemplateMatcher("templates\\bankara_challenge.png"),
        "バンカラマッチ(オープン)": TemplateMatcher("templates\\bankara_open.png"),
        "Xマッチ": TemplateMatcher("templates\\x.png")
    }
    rule_matchers: Dict[str, TemplateMatcher] = {
        "ナワバリ": TemplateMatcher("templates\\nawabari.png"),
        "ガチホコ": TemplateMatcher("templates\\hoko.png"),
        "ガチエリア": TemplateMatcher("templates\\area.png"),
        "ガチヤグラ": TemplateMatcher("templates\\yagura.png"),
        "ガチアサリ": TemplateMatcher("templates\\asari.png")
    }

    obs = Obs()
    if not obs.start_virtual_cam():
        raise Exception("仮想カメラの起動に失敗しました")
    
    index = int(os.environ["CAPTURE_DEVICE_INDEX"])
    width = int(os.environ["CAPTURE_WIDTH"])
    height = int(os.environ["CAPTURE_HEIGHT"])
    capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        raise Exception("カメラが見つかりません")
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    upload = bool(os.environ["UPLOAD_YOUTUBE"])
    youtube = Youtube() if upload == True else None

    status = RecordStatus.OFF
    buttle_result = ""
    on_counter = 0
    record_counter = 0

    try:
        # Switchの起動有無に関わらず、ずっと監視する (起動してないときは1分周期で起動待ちをする)
        while True:
            ret, frame = capture.read()
            if not ret:
                print("フレームの読み込みに失敗しました。")
                time.sleep(60)
                continue

            # Switchの起動確認
            if status == RecordStatus.OFF:
                # まだ起動してなかったら、また1分待つ
                if is_screen_off(frame):
                    time.sleep(60)
                    continue

                print("Switchが起動しました")
                status = RecordStatus.WAIT
                continue
            
            # 処理負荷を下げるため、Switchの電源OFF確認は60フレーム毎とする
            on_counter += 1
            if on_counter > 60:
                on_counter = 0
                if is_screen_off(frame):
                    status = RecordStatus.OFF
                    continue

            # バトル開始確認
            if status == RecordStatus.WAIT:
                match, _ = start_matcher.match(frame)
                if match:
                    print("録画を開始します")
                    obs.start_record()
                    record_counter = 0
                    buttle_result = ""
                    status = RecordStatus.RECORD
                continue

            # 以降、バトル終了までの処理

            # 万一、バトル終了を画像検知できなかったときのため、600フレーム(10分)でタイムアウトさせる
            record_counter += 1
            if record_counter > 600:
                print("録画がタイムアウトしたため、録画を停止します")
                _, path = obs.stop_record()
                status = RecordStatus.WAIT
                continue

            # 勝敗判定
            if buttle_result == "":
                match, _ = win_matcher.match(frame)
                if match:
                    buttle_result = "WIN"
                    print("勝利しました")
                    continue

                match, _ = lose_matcher.match(frame)
                if match:
                    buttle_result = "LOSE"
                    print("敗北しました")
                    continue

            # 処理負荷を下げるため、勝敗が決まってから録画停止タイミングを監視する
            match, _ = stop_matcher.match(frame)
            if not match:
                continue

            print("録画を停止します")
            _, path = obs.stop_record()

            # マッチ・ルールを分析する
            buttle = ""
            for match_name, matcher in match_matchers.items():
                match, _ = matcher.match(frame)
                if match:
                    buttle = match_name
                    print(f"マッチ: {match_name}")
                    break
            rule = ""
            for rule_name, matcher in rule_matchers.items():
                match, _ = matcher.match(frame)
                if match:
                    rule = rule_name
                    print(f"ルール: {rule_name}")
                    break

            day_names = ["月", "火", "水", "木", "金", "土", "日"]
            now = datetime.datetime.now()
            day = now.strftime(f"%Y年%m月%d日({day_names[now.weekday()]})")

            if youtube:
                print("YouTubeにアップロードします")
                youtube.upload(
                    path, 
                    f"{day} {buttle} {rule} {buttle_result}",
                    f"{day} {buttle} {rule} {buttle_result}の試合をプレイしました",
                    privacy_status='private')
                print("YouTubeにアップロードしました")
            
            # リネーム
            directory = os.path.dirname(path)
            file_name = f"{day} {buttle} {rule} {buttle_result}"
            extension = os.path.splitext(path)[1]
            os.rename(path, f"{directory}\\{file_name}{extension}")
            
            status = RecordStatus.WAIT
    
    except Exception as e:
        print(e)

    finally:
        # カメラリソースとウィンドウを解放
        capture.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':

    # 日本語の日付に変換できるようにロケーションを設定
    locale.setlocale(locale.LC_TIME, 'ja_JP.UTF-8')

    dotenv.load_dotenv()

    main()