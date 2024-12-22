import os
import logging
import shutil
import glob
import time
import datetime
from collections import defaultdict
import subprocess
from typing import Dict, List, Tuple
from dataclasses import dataclass

import cv2
import schedule

from youtube import Youtube

logger = logging.getLogger(__name__)

@dataclass
class UploadFile:
    file_name: str
    path: str
    start_datetime: datetime.datetime
    buttle: str
    rule: str
    result: str
    length: float

class FileProcessor:
    @staticmethod
    def get_upload_files(directory: str) -> List['UploadFile']:
        upload_files: List[UploadFile] = []

        files = glob.glob(f'{directory}/*.*')
        for path in files:
            file = os.path.basename(path)
            start_datetime_str, buttle, rule, result = os.path.splitext(file)[0].split("_")
            start_datetime = datetime.datetime.strptime(start_datetime_str, "%Y-%m-%d %H-%M-%S")
            video = cv2.VideoCapture(path)
            length = video.get(cv2.CAP_PROP_FRAME_COUNT) / video.get(cv2.CAP_PROP_FPS)
            video.release()
            upload_files.append(UploadFile(file, path, start_datetime, buttle, rule, result, length))

        return upload_files
        
    @staticmethod
    def split_by_time_ranges(upload_files: List['UploadFile'], time_ranges: List[tuple]) -> Dict[Tuple[datetime.date, datetime.time, str, str], List['UploadFile']]:
        # 時間帯ごとのリストを格納する辞書
        buckets = defaultdict(list)

        for upload_file in upload_files:
            file_datetime = upload_file.start_datetime
            file_date = file_datetime.date()
            file_time = file_datetime.time()
            
            for _, (start, end) in enumerate(time_ranges):
                if start < end:  # 通常の時間帯
                    if start <= file_time < end:
                        bucket_key = (file_date, start, upload_file.buttle, upload_file.rule)
                        buckets[bucket_key].append(upload_file)
                        break
                else:  # 日をまたぐ時間帯 (23:00-1:00)
                    if file_time >= start or file_time < end:
                        # 日をまたぐ場合は1:00を含む日付に調整
                        adjusted_date = file_date if file_time >= start else file_date - datetime.timedelta(days=1)
                        bucket_key = (adjusted_date, start, upload_file.buttle, upload_file.rule)
                        buckets[bucket_key].append(upload_file)
                        break
        return buckets
    
    @staticmethod
    def concat(files: List['UploadFile'], out_path: str):
        if len(files) == 1:
            shutil.copyfile(files[0].file_name, out_path)
            return

        directory = os.path.dirname(files[0].path)
        _, extension = os.path.splitext(files[0].file_name)

        concat_list = "list.txt"
        concat_list_path = os.path.join(directory, concat_list)
        try:
            with open(concat_list_path, "w", encoding="utf-8") as f:
                f.writelines([f"file '{os.path.basename(file.file_name)}'\n" for file in files])

            os.chdir(directory)
            command = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                f"temp{extension}"
            ]
            subprocess.run(command, check=True)
            os.rename(f"temp{extension}", out_path)

        finally:
            os.remove(concat_list_path)

class Uploader:
    RECORDED_DIR = os.path.join(os.path.dirname(__file__), "videos", "recorded")
    PENDING_DIR = os.path.join(os.path.dirname(__file__), "videos", "upload_pending")
    TIME_RANGES = [
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
    
    @staticmethod
    def queue(path: str, start_datetime: datetime.datetime, match: str, rule: str, result: str):
        _, extension = os.path.splitext(os.path.basename(path))
        # スケジュール毎に結合できるよう、録画開始日時(バトル開始日時)、マッチ、ルールをファイル名に含める
        # 動画説明に各試合の結果を記載するため、結果もファイル名に含める
        new_file_base_name = f"{start_datetime.strftime('%Y-%m-%d %H-%M-%S')}_{match}_{rule}_{result}{extension}"
        new_path = os.path.join(Uploader.RECORDED_DIR, new_file_base_name)
        os.rename(path, new_path)

    def __init__(self):
        os.makedirs(self.RECORDED_DIR, exist_ok=True)
        os.makedirs(self.PENDING_DIR, exist_ok=True)

        self._youtube = Youtube()
    
    def set_upload_schedule(self, upload_time: str):
        schedule.every().day.at(upload_time).do(self.start_upload)
        logger.info(f"アップロードスケジュールを設定しました: {upload_time}")

    def run(self):
        logger.info("アップロード処理の待機中です")
        while True:
            schedule.run_pending()
            time.sleep(360)

    def _timedelta_to_str(self, delta: datetime.timedelta) -> str:
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"
        return formatted_time

    def start_upload(self):
        logger.info("アップロード処理を開始します")

        upload_files = FileProcessor.get_upload_files(self.RECORDED_DIR)
        buckets = FileProcessor.split_by_time_ranges(upload_files, self.TIME_RANGES)
        for key, files in buckets.items():   
            day, time, buttle, rule = key

            description = ""
            elapsed_time = 0
            win_count = 0
            lose_count = 0
            for file in files:
                elapsed_time_str = self._timedelta_to_str(datetime.timedelta(seconds=elapsed_time))
                description += f"{elapsed_time_str} {file.result}\n"
                elapsed_time += file.length
                if "WIN" in file.result:
                    win_count += 1
                elif "LOSE" in file.result:
                    lose_count += 1

            # ファイル結合
            extension = os.path.splitext(files[0].file_name)[1]
            file_name = f"{day.strftime("%Y-%m-%d")}_{time.strftime("%H")}_{buttle}_{rule}_{win_count}wins{lose_count}losses{extension}"
            path = os.path.join(self.PENDING_DIR, file_name)
            FileProcessor.concat(files, path)

            # ファイルアップロード
            title = f"{day.strftime("%Y-%m-%d")} {time.strftime("%H")}:00～ {buttle} {rule} {win_count}勝{lose_count}敗"
            logger.info(f"YouTubeにアップロードします: {title}")
            res = self._youtube.upload(path, title, description)
            if res:
                logger.info("YouTubeにアップロードしました")
                os.remove(path)
                for file in files:
                    os.remove(file.path)
            else:
                logger.info("YouTubeへのアップロードに失敗しました")

        shutdoen_after_upload = bool(os.environ["SHUTDOWN_AFTER_UPLOAD"])
        if shutdoen_after_upload:
            logger.info("アップロード処理が完了したため、PCをシャットダウンします")
            os.system("shutdown -s -t 0")