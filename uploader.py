import os
import logging
import shutil
import glob
import time
import datetime
from collections import defaultdict
import subprocess
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import cv2
import schedule

from youtube import Youtube

logger = logging.getLogger(__name__)


@dataclass
class UploadFile:
    DATETIME_FORMAT = "%Y-%m-%d %H-%M-%S"

    path: str
    file_name: str
    extension: str
    start: datetime.datetime
    battle: str
    rule: str
    result: str
    xpower: Optional[float]
    length: float

    def __init__(self, path):
        self.path = path
        self.file_name = os.path.basename(path)
        file_base_name, self.extension = os.path.splitext(self.file_name)

        metadata = self._extract_metadata(file_base_name)
        self.start = datetime.datetime.strptime(
            metadata[0], self.DATETIME_FORMAT)
        self.battle = metadata[1]
        self.rule = metadata[2]
        self.result = metadata[3]
        self.xpower = metadata[4] if len(metadata) == 5 else None
        self.length = self._get_video_length()

    def _extract_metadata(self, file_base_name: str) -> List[str]:
        metadata = file_base_name.split("_")
        if len(metadata) not in (4, 5):
            raise ValueError(f"Invalid file name format: {file_base_name}")
        return metadata

    def _get_video_length(self) -> float:
        video = None
        try:
            video = cv2.VideoCapture(self.path)
            length = video.get(cv2.CAP_PROP_FRAME_COUNT) / \
                video.get(cv2.CAP_PROP_FPS)
            return length
        except Exception as e:
            raise e
        finally:
            if video:
                video.release()

    @classmethod
    def make_file_base_name(cls, start: datetime.datetime, match: str, rule: str, result: str, xpower: Optional[float] = None) -> str:
        # スケジュール毎に結合できるよう、録画開始日時(バトル開始日時)、マッチ、ルールをファイル名に含める
        # 動画説明に各試合の結果を記載するため、結果もファイル名に含める
        start_str = start.strftime(cls.DATETIME_FORMAT)
        file_base_name = f"{start_str}_{match}_{rule}_{result}"
        if xpower:
            file_base_name += f"_{xpower}"
        return file_base_name


class FFmpeg:
    @staticmethod
    def concat(files: List[str], out_path: str):
        directory = os.path.dirname(files[0])
        _, extension = os.path.splitext(out_path)

        concat_list = "list.txt"
        concat_list_path = os.path.join(directory, concat_list)
        try:
            with open(concat_list_path, "w", encoding="utf-8") as f:
                f.writelines(
                    [f"file '{os.path.basename(file)}'\n" for file in files])

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
    RECORDED_DIR = os.path.join(
        os.path.dirname(__file__), "videos", "recorded")
    PENDING_DIR = os.path.join(os.path.dirname(
        __file__), "videos", "upload_pending")
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
    def queue(path: str, start_datetime: datetime.datetime, match: str, rule: str, result: str, xpower: Optional[float] = None):
        _, extension = os.path.splitext(os.path.basename(path))
        new_file_base_name = UploadFile.make_file_base_name(
            start_datetime, match, rule, result, xpower)
        new_path = os.path.join(Uploader.RECORDED_DIR,
                                new_file_base_name + extension)
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

    def _get_upload_files(self) -> List[UploadFile]:
        upload_files: List[UploadFile] = []
        files = glob.glob(f'{self.RECORDED_DIR}/*.*')
        for path in files:
            upload_file = UploadFile(path)
            upload_files.append(upload_file)
        return upload_files

    def _split_by_time_ranges(self, upload_files: List[UploadFile]) -> Dict[Tuple[datetime.date, datetime.time, str, str], List[UploadFile]]:
        # 時間帯ごとのリストを格納する辞書
        buckets = defaultdict(list)

        for upload_file in upload_files:
            file_datetime = upload_file.start
            file_date = file_datetime.date()
            file_time = file_datetime.time()

            for _, (start, end) in enumerate(self.TIME_RANGES):
                if start < end:  # 通常の時間帯
                    if start <= file_time < end:
                        bucket_key = (file_date, start,
                                      upload_file.battle, upload_file.rule)
                        buckets[bucket_key].append(upload_file)
                        break
                else:  # 日をまたぐ時間帯 (23:00-1:00)
                    if file_time >= start or file_time < end:
                        # 日をまたぐ場合は1:00を含む日付に調整
                        adjusted_date = file_date if file_time >= start else file_date - \
                            datetime.timedelta(days=1)
                        bucket_key = (adjusted_date, start,
                                      upload_file.battle, upload_file.rule)
                        buckets[bucket_key].append(upload_file)
                        break
        return buckets

    def _concat_files(self, files: List[UploadFile], day: datetime.date, time: datetime.time, battle: str, rule: str) -> str:
        extension = files[0].extension
        file_name = f"{day.strftime(
            "%Y-%m-%d")}_{time.strftime("%H")}_{battle}_{rule}{extension}"
        path = os.path.join(self.PENDING_DIR, file_name)

        # ファイルが一つの場合は結合する必要がないのでリネーム＆移動
        if len(files) == 1:
            shutil.copyfile(files[0].path, path)
            return path

        file_names = [file.path for file in files]
        FFmpeg.concat(file_names, path)
        return path

    def _generate_title_and_description(self, files: List[UploadFile], day: datetime.date, time: datetime.time, battle: str, rule: str) -> Tuple[str, str]:
        description = ""
        elapsed_time = 0
        win_count = 0
        lose_count = 0
        max_xpower: Optional[float] = None
        min_xpower: Optional[float] = None
        for file in files:
            if file.xpower:
                if max_xpower is None or file.xpower > max_xpower:
                    max_xpower = file.xpower
                if min_xpower is None or file.xpower < min_xpower:
                    min_xpower = file.xpower
                description += f"XP: {file.xpower}\n"

            elapsed_time_str = self._timedelta_to_str(
                datetime.timedelta(seconds=elapsed_time))
            description += f"{elapsed_time_str} {file.result}\n"
            elapsed_time += file.length

            if "WIN" in file.result:
                win_count += 1
            elif "LOSE" in file.result:
                lose_count += 1

        if max_xpower and min_xpower:
            if max_xpower == min_xpower:
                xpower = f"({max_xpower})"
            else:
                xpower = f"({min_xpower}～{max_xpower})"
        else:
            xpower = ""

        title = f"{day.strftime(
            "%Y-%m-%d")} {time.strftime("%H")}:00～ {battle}{xpower} {rule} {win_count}勝{lose_count}敗"
        return title, description

    def start_upload(self):
        logger.info("アップロード処理を開始します")
        upload_files = self._get_upload_files()
        buckets = self._split_by_time_ranges(upload_files)
        for key, files in buckets.items():
            day, time, battle, rule = key
            path = self._concat_files(files, day, time, battle, rule)
            title, description = self._generate_title_and_description(
                files, day, time, battle, rule)

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
            os.system("shutdown -s -t 0 -f")
