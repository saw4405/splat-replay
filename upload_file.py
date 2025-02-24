import os
import datetime
from typing import List, Optional
from dataclasses import dataclass

import cv2
import numpy as np
import srt

from wrapper.ffmpeg import FFmpeg
from rate import RateBase, XP, Udemae


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
    rate: Optional[RateBase]
    length: float

    def __init__(self, path):
        self.path = path
        self.file_name = os.path.basename(path)
        file_base_name, self.extension = os.path.splitext(self.file_name)

        metadata = self._extract_metadata(file_base_name)
        self.start = datetime.datetime.strptime(
            metadata[0], self.DATETIME_FORMAT)
        self.battle, self.rule, self.stage, self.result = metadata[1:5]
        self.rate = RateBase.create(
            metadata[5]) if len(metadata) == 6 else None

        self.length = self._get_video_length()

    @property
    def srt(self) -> Optional[List[srt.Subtitle]]:
        srt_str = FFmpeg.get_subtitle(self.path)
        if srt_str.is_err():
            return None
        return list(srt.parse(srt_str.unwrap()))

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
    def make_file_base_name(start: datetime.datetime, match: str, rule: str, stage: str, result: str, rate: Optional[RateBase] = None) -> str:
        # スケジュール毎に結合できるよう、録画開始日時(バトル開始日時)、マッチ、ルールをファイル名に含める
        # 動画説明に各試合の結果を記載するため、結果もファイル名に含める
        start_str = start.strftime(UploadFile.DATETIME_FORMAT)
        file_base_name = f"{start_str}_{match}_{rule}_{stage}_{result}"
        if rate:
            file_base_name += f"_{rate}"
        return file_base_name

    def set_thumbnail(self, thumbnail: np.ndarray) -> None:
        ret, buffer = cv2.imencode('.png', thumbnail)
        if not ret:
            raise ValueError("画像のエンコードに失敗しました")

        binary_data = buffer.tobytes()
        FFmpeg.set_thumbnail(self.path, binary_data)

    def embed_subtitles(self, srt_str: str) -> None:
        subtitles = list(srt.parse(srt_str))
        valid_subs = []
        for sub in subtitles:
            if sub.start.total_seconds() > self.length:
                break
            if sub.end.total_seconds() > self.length:
                sub = srt.Subtitle(index=sub.index, start=sub.start, end=datetime.timedelta(
                    seconds=self.length), content=sub.content, proprietary=sub.proprietary)
            valid_subs.append(sub)
        new_srt = srt.compose(valid_subs)
        FFmpeg.set_subtitle(self.path, new_srt)
