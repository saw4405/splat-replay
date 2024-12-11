import os
import time
import datetime
from typing import Dict, Tuple, List
from enum import Enum
import threading
from dataclasses import dataclass
from collections import defaultdict
import shutil
import glob

import cv2
import numpy as np
import schedule

from obs import Obs
from template_matcher import TemplateMatcher
from youtube import Youtube

class RecordStatus(Enum):
    OFF = 1
    WAIT = 2
    RECORD = 3

class SplatReplay:

    def __init__(self):
        self._load_templates()
        self._start_obs()
        self._setup_capture()
        self._setup_upload()

    def _load_templates(self):
        # 画像判定に使用する画像を読み込んでおく
        self._start_matcher = TemplateMatcher("templates\\start.png")
        self._stop_matcher = TemplateMatcher("templates\\stop.png")
        self._win_matcher = TemplateMatcher("templates\\win.png")
        self._lose_matcher = TemplateMatcher("templates\\lose.png")
        self._match_matchers: Dict[str, TemplateMatcher] = {
            "レギュラーマッチ": TemplateMatcher("templates\\regular.png"),
            "バンカラマッチ(チャレンジ)": TemplateMatcher("templates\\bankara_challenge.png"),
            "バンカラマッチ(オープン)": TemplateMatcher("templates\\bankara_open.png"),
            "Xマッチ": TemplateMatcher("templates\\x.png")
        }
        self._rule_matchers: Dict[str, TemplateMatcher] = {
            "ナワバリ": TemplateMatcher("templates\\nawabari.png"),
            "ガチホコ": TemplateMatcher("templates\\hoko.png"),
            "ガチエリア": TemplateMatcher("templates\\area.png"),
            "ガチヤグラ": TemplateMatcher("templates\\yagura.png"),
            "ガチアサリ": TemplateMatcher("templates\\asari.png")
        }

    def _start_obs(self):
        self._obs = Obs()
        if not self._obs.start_virtual_cam():
            raise Exception("仮想カメラの起動に失敗しました")

    def _setup_capture(self):
        index = int(os.environ["CAPTURE_DEVICE_INDEX"])
        width = int(os.environ["CAPTURE_WIDTH"])
        height = int(os.environ["CAPTURE_HEIGHT"])
        self._capture = cv2.VideoCapture(index)
        if not self._capture.isOpened():
            raise Exception("カメラが見つかりません")
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def _setup_upload(self):
        upload = bool(os.environ["UPLOAD_YOUTUBE"])
        if not upload:
            self._uploader_thread = None
            return
        
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(360)

        self._youtube = Youtube()
        upload_time = os.environ["UPLOAD_TIME"]
        schedule.every().day.at(upload_time).do(self._upload_daily)
        self._uploader_thread = threading.Thread(target=run_schedule, daemon=True)
        self._uploader_thread.start()
        print(f"アップロードスケジュールを設定しました: {upload_time}")

    def _upload_daily(self):
        print("アップロード処理を開始します")

        @dataclass
        class UploadFile:
            file_name: str
            path: str
            start_datetime: datetime.datetime
            buttle: str
            rule: str
            result: str
            length: float
        
        def timedelta_to_mmss(td):
            total_seconds = int(td.total_seconds())  # 総秒数を取得
            minutes, seconds = divmod(total_seconds, 60)  # 分と秒に分割
            return f"{minutes:02}:{seconds:02}"  # ゼロ埋めでフォーマット

        def split_by_time_ranges(upload_files: List[UploadFile]) -> Dict[int, List[UploadFile]]:
            time_ranges = [
                (datetime.time(1, 0), datetime.time(3, 0)),
                (datetime.time(3, 0), datetime.time(5, 0)),
                (datetime.time(5, 0), datetime.time(7, 0)),
                (datetime.time(7, 0), datetime.time(9, 0)),
                (datetime.time(9, 0), datetime.time(11, 0)),
                (datetime.time(11, 0), datetime.time(13, 0)),
                (datetime.time(13, 0), datetime.time(15, 0)),
                (datetime.time(15, 0), datetime.time(17, 0)),
                (datetime.time(17, 0), datetime.time(19, 0)),
                (datetime.time(19, 0), datetime.time(21, 0)),
                (datetime.time(21, 0), datetime.time(23, 0)),
                (datetime.time(23, 0), datetime.time(1, 0))  # 日をまたぐ時間帯
            ]
            # 時間帯ごとのリストを格納する辞書
            buckets = defaultdict(list)

            for upload_file in upload_files:
                file_datetime = upload_file.start_datetime
                file_date = file_datetime.date()
                file_time = file_datetime.time()
                buttle = upload_file.buttle
                rule = upload_file.rule
                
                for idx, (start, end) in enumerate(time_ranges):
                    if start < end:  # 通常の時間帯
                        if start <= file_time < end:
                            bucket_key = (file_date, start, buttle, rule)
                            buckets[bucket_key].append(upload_file)
                            break
                    else:  # 日をまたぐ時間帯 (23:00-1:00)
                        if file_time >= start or file_time < end:
                            # 日をまたぐ場合は1:00を含む日付に調整
                            adjusted_date = file_date if file_time >= start else file_date - datetime.timedelta(days=1)
                            bucket_key = (adjusted_date, start, buttle, rule)
                            buckets[bucket_key].append(upload_file)
                            break

            return buckets

        directory = os.path.join(os.path.dirname(__file__), "out")
        files = glob.glob(f'{directory}/*.*')
        update_files: List[UploadFile] = []
        for path in files:
            file = os.path.basename(path)
            start_datetime_str, buttle, rule, result = os.path.splitext(file)[0].split("_")
            start_datetime = datetime.datetime.strptime(start_datetime_str, "%Y-%m-%d %H-%M-%S")
            video = cv2.VideoCapture(path)
            length = video.get(cv2.CAP_PROP_FRAME_COUNT) / video.get(cv2.CAP_PROP_FPS)
            video.release()
            update_files.append(UploadFile(file, path, start_datetime, buttle, rule, result, length))

        buckets = split_by_time_ranges(update_files)
        for key, files in buckets.items():        
            day: datetime.date = key[0]
            time: datetime.time = key[1]
            buttle: str = key[2]
            rule: str = key[3]
            extention = os.path.splitext(files[0].file_name)[1]
            file_name = f"{day.strftime("%Y-%m-%d")}_{time.strftime("%H")}_{buttle}_{rule}{extention}"
            path = os.path.join(directory, "upload", file_name)

            if len(files) == 1:
                shutil.copyfile(files[0].file_name, path)
                
            else:
                concat_list = "list.txt"
                concat_list_path = os.path.join(directory, concat_list)
                with open(concat_list_path, "w", encoding="utf-8") as f:
                    f.writelines([f"file '{os.path.basename(file.file_name)}'\n" for file in files])

                os.chdir(directory)
                command = f"ffmpeg -f concat -safe 0 -i {concat_list} -c copy temp{extention}"
                os.system(command)
                os.rename(f"temp{extention}", path)
                os.remove(concat_list_path)


            title = f"{day.strftime("%Y-%m-%d")} {time.strftime("%H")}:00～ {buttle} {rule}"
            description = ""
            elapsed_time = 0
            for file in files:
                description += f"{timedelta_to_mmss(datetime.timedelta(seconds=elapsed_time))} {file.result}\n"
                elapsed_time += file.length

            # ファイルアップロード
            print(f"YouTubeにアップロードします")
            res = self._youtube.upload(path, title, description)
            if res:
                print(f"YouTubeにアップロードしました: {path}")
                os.remove(path)
                for file in files:
                    os.remove(file.path)
            else:
                print(f"YouTubeへのアップロードに失敗しました: {path}")

    def run(self):
        self._status = RecordStatus.OFF
        self._buttle_result = ""
        self._on_counter = 0
        self._record_counter = 0

        try:
            # Switchの起動有無に関わらず、ずっと監視する (起動してないときは1分周期で起動待ちをする)
            while True:
                ret, frame = self._capture.read()
                if not ret:
                    print("フレームの読み込みに失敗しました。")
                    time.sleep(60)
                    continue

                self._process_frame(frame)
        except KeyboardInterrupt:
            print("監視を終了します")
        finally:
            self._capture.release()
            cv2.destroyAllWindows()
            if self._uploader_thread:
                self._uploader_thread.join()

    def _is_screen_off(self, image: np.ndarray) -> bool:
        if image.max() <= 10:
            return True
        return False
    
    def _process_frame(self, frame: np.ndarray):
        # Switchの起動確認
        if self._status == RecordStatus.OFF:
            # まだ起動してなかったら、また1分待つ
            if self._is_screen_off(frame):
                time.sleep(60)
                return

            print("Switchが起動しました")
            self._status = RecordStatus.WAIT
            return
            
        # 処理負荷を下げるため、Switchの電源OFF確認は60フレーム毎とする
        self._on_counter += 1
        if self._on_counter > 60:
            self._on_counter = 0
            if self._is_screen_off(frame):
                self._status = RecordStatus.OFF
                return

        # バトル開始確認
        if self._status == RecordStatus.WAIT:
            match, _ = self._start_matcher.match(frame)
            if match:
                print("録画を開始します")
                self._obs.start_record()
                self._record_counter = 0
                self._buttle_result = ""
                self._status = RecordStatus.RECORD
            return

        # 以降、バトル終了までの処理

        # 万一、バトル終了を画像検知できなかったときのため、600フレーム(10分)でタイムアウトさせる
        self._record_counter += 1
        if self._record_counter > 600:
            print("録画がタイムアウトしたため、録画を停止します")
            _, path = self._obs.stop_record()
            self._status = RecordStatus.WAIT
            return

        # 勝敗判定
        if self._buttle_result == "":
            match, _ = self._win_matcher.match(frame)
            if match:
                self._buttle_result = "WIN"
                print("勝ちました")
                return

            match, _ = self._lose_matcher.match(frame)
            if match:
                self._buttle_result = "LOSE"
                print("負けました")
                return

        # 処理負荷を下げるため、勝敗が決まってから録画停止タイミングを監視する
        match, _ = self._stop_matcher.match(frame)
        if not match:
            return

        # バトル終了後の処理
        print("録画を停止します")
        _, path = self._obs.stop_record()
        self._status = RecordStatus.WAIT

        # マッチ・ルールを分析する
        buttle = ""
        for match_name, matcher in self._match_matchers.items():
            match, _ = matcher.match(frame)
            if match:
                buttle = match_name
                print(f"マッチ: {match_name}")
                break
        rule = ""
        for rule_name, matcher in self._rule_matchers.items():
            match, _ = matcher.match(frame)
            if match:
                rule = rule_name
                print(f"ルール: {rule_name}")
                break

        # ファイルリネーム＆移動
        # スケジュールの分類をできるよう、録画開始日時(バトル開始日時)をファイル名に含める
        file_base_name, extension = os.path.splitext(os.path.basename(path))
        start_datetime = datetime.datetime.strptime(file_base_name, "%Y-%m-%d %H-%M-%S")
        directory = os.path.dirname(__file__)
        new_file_base_name = f"{start_datetime.strftime('%Y-%m-%d %H-%M-%S')}_{buttle}_{rule}_{self._buttle_result}{extension}"
        new_path = os.path.join(directory, "out", new_file_base_name)
        os.rename(path, new_path)
        print(f"ファイルを移動しました: {new_path}")
