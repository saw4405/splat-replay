import os
import datetime
from typing import List, Optional, Tuple, Dict
from collections import defaultdict
from dataclasses import dataclass

import cv2


@dataclass
class UploadFile:
    DATETIME_FORMAT = "%Y-%m-%d %H-%M-%S"

    path: str
    file_name: str
    extension: str
    start: datetime.datetime
    battle: str
    rule: str
    stage: str
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
        self.battle, self.rule, self.stage, self.result = metadata[1:5]
        self.xpower = float(metadata[5]) if len(metadata) == 6 else None

        self.length = self._get_video_length()

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

    def _extract_metadata(self, file_base_name: str) -> List[str]:
        metadata = file_base_name.split("_")
        if len(metadata) not in (5, 6):
            raise ValueError(f"Invalid file name format: {file_base_name}")
        return metadata

    @staticmethod
    def make_file_base_name(start: datetime.datetime, match: str, rule: str, stage: str, result: str, xpower: Optional[float] = None) -> str:
        # スケジュール毎に結合できるよう、録画開始日時(バトル開始日時)、マッチ、ルールをファイル名に含める
        # 動画説明に各試合の結果を記載するため、結果もファイル名に含める
        start_str = start.strftime(UploadFile.DATETIME_FORMAT)
        file_base_name = f"{start_str}_{match}_{rule}_{stage}_{result}"
        if xpower:
            file_base_name += f"_{xpower}"
        return file_base_name

    @staticmethod
    def split_by_time_ranges(files: List['UploadFile'], time_ranges: List[Tuple[datetime.time, datetime.time]]) -> Dict[Tuple[datetime.date, datetime.time, str, str], List['UploadFile']]:
        time_scheduled_files = defaultdict(list)
        for file in files:
            file_datetime = file.start
            file_date = file_datetime.date()
            file_time = file_datetime.time()

            for schedule_start_time, schedule_end_time in time_ranges:
                # 日をまたがない時間帯 (1:00-23:00)
                if schedule_start_time < schedule_end_time:
                    # スケジュールに該当する場合
                    if schedule_start_time <= file_time < schedule_end_time:
                        key = (file_date, schedule_start_time,
                               file.battle, file.rule)
                        time_scheduled_files[key].append(file)
                        break

                # 日をまたぐ時間帯 (23:00-1:00)
                else:
                    # スケジュールに該当する場合
                    if file_time >= schedule_start_time or file_time < schedule_end_time:
                        # 日をまたぐ場合は1:00を含む日付に調整
                        adjusted_date = file_date if file_time >= schedule_start_time else file_date - \
                            datetime.timedelta(days=1)
                        key = (adjusted_date, schedule_start_time,
                               file.battle, file.rule)
                        time_scheduled_files[key].append(file)
                        break
        return time_scheduled_files
