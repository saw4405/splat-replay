import os
import shutil
import glob
import time
import datetime
from collections import defaultdict
import threading
from typing import Dict, List
from dataclasses import dataclass

import cv2
import schedule

from youtube import Youtube

@dataclass
class UploadFile:
    file_name: str
    path: str
    start_datetime: datetime.datetime
    buttle: str
    rule: str
    result: str
    length: float

class Uploader:
    OUT_DIR = "out"
    UPLOAD_DIR = "upload"

    @classmethod
    def queue(cls, path: str, start_datetime: datetime.datetime, buttle: str, rule: str, result: str):
        _, extension = os.path.splitext(os.path.basename(path))
        # スケジュール毎に結合できるよう、録画開始日時(バトル開始日時)、マッチ、ルールをファイル名に含める
        # 動画説明に各試合の結果を記載するため、結果もファイル名に含める
        new_file_base_name = f"{start_datetime.strftime('%Y-%m-%d %H-%M-%S')}_{buttle}_{rule}_{result}{extension}"
        directory = os.path.dirname(__file__)
        new_path = os.path.join(directory, Uploader.OUT_DIR, new_file_base_name)
        os.rename(path, new_path)

    def __init__(self):
        self._youtube = Youtube()
        upload_time = os.environ["UPLOAD_TIME"]
        schedule.every().day.at(upload_time).do(self._upload_daily)
        print(f"アップロードスケジュールを設定しました: {upload_time}")

    def run(self):
        print("アップロード処理の待機中です")
        while True:
            schedule.run_pending()
            time.sleep(360)
    
    def _get_upload_files(self) -> List[UploadFile]:
        update_files: List[UploadFile] = []

        directory = os.path.join(os.path.dirname(__file__), self.OUT_DIR)
        files = glob.glob(f'{directory}/*.*')
        for path in files:
            file = os.path.basename(path)
            start_datetime_str, buttle, rule, result = os.path.splitext(file)[0].split("_")
            start_datetime = datetime.datetime.strptime(start_datetime_str, "%Y-%m-%d %H-%M-%S")
            video = cv2.VideoCapture(path)
            length = video.get(cv2.CAP_PROP_FRAME_COUNT) / video.get(cv2.CAP_PROP_FPS)
            video.release()
            update_files.append(UploadFile(file, path, start_datetime, buttle, rule, result, length))

        return update_files
        
    def _split_by_time_ranges(self, upload_files: List[UploadFile]) -> Dict[int, List[UploadFile]]:
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
            
            for _, (start, end) in enumerate(time_ranges):
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

    def _timedelta_to_str(self, delta: datetime.timedelta) -> str:
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"
        return formatted_time
    
    def _concat(self, files: List[UploadFile], out_path: str):
            
        if len(files) == 1:
            shutil.copyfile(files[0].file_name, out_path)
            return

        directory = os.path.dirname(files[0].path)
        _, extention = os.path.splitext(files[0].file_name)

        concat_list = "list.txt"
        concat_list_path = os.path.join(directory, concat_list)
        try:
            with open(concat_list_path, "w", encoding="utf-8") as f:
                f.writelines([f"file '{os.path.basename(file.file_name)}'\n" for file in files])

            os.chdir(directory)
            command = f"ffmpeg -f concat -safe 0 -i {concat_list} -c copy temp{extention}"
            os.system(command)
            os.rename(f"temp{extention}", out_path)

        finally:
            os.remove(concat_list_path)

    def _upload_daily(self):
        print("アップロード処理を開始します")

        directory = os.path.join(os.path.dirname(__file__), self.OUT_DIR, self.UPLOAD_DIR)
        if not os.path.exists(directory):
            os.makedirs(directory)

        update_files = self._get_upload_files()
        buckets = self._split_by_time_ranges(update_files)
        for key, files in buckets.items():        
            day: datetime.date = key[0]
            time: datetime.time = key[1]
            buttle: str = key[2]
            rule: str = key[3]
            extention = os.path.splitext(files[0].file_name)[1]
            file_name = f"{day.strftime("%Y-%m-%d")}_{time.strftime("%H")}_{buttle}_{rule}{extention}"
            path = os.path.join(directory, file_name)

            self._concat(files, path)

            title = f"{day.strftime("%Y-%m-%d")} {time.strftime("%H")}:00～ {buttle} {rule}"
            description = ""
            elapsed_time = 0
            for file in files:
                elapsed_time_str = self._timedelta_to_str(datetime.timedelta(seconds=elapsed_time))
                description += f"{elapsed_time_str} {file.result}\n"
                elapsed_time += file.length

            # ファイルアップロード
            print(f"YouTubeにアップロードします: {file_name}")
            res = self._youtube.upload(path, title, description)
            if res:
                print("YouTubeにアップロードしました")
                os.remove(path)
                for file in files:
                    os.remove(file.path)
            else:
                print("YouTubeへのアップロードに失敗しました")