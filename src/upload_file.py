import os
import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass

import cv2
import numpy as np
import srt

from battle_result import BattleResult
from wrapper.ffmpeg import FFmpeg
from models.rate import RateBase, XP, Udemae


@dataclass
class UploadFile:
    DATETIME_FORMAT = "%Y-%m-%d %H-%M-%S"

    path: str
    battle_result: BattleResult

    @staticmethod
    def make_file_base_name(battle_result: BattleResult) -> str:
        return "_".join(battle_result.to_list())

    def __init__(self, path: str):
        self.path = path
        file_name = os.path.basename(path)
        file_base_name = os.path.splitext(file_name)[0]
        metadata = file_base_name.split("_")
        if len(metadata) != 9:
            raise ValueError(f"Invalid file name format: {file_base_name}")
        self.battle_result = BattleResult.from_list(metadata)

    @property
    def extension(self) -> str:
        file_name = os.path.basename(self.path)
        return os.path.splitext(file_name)[1]

    @property
    def result(self) -> str:
        return self.battle_result.result or ""

    @property
    def rate(self) -> Optional[RateBase]:
        return self.battle_result.rate

    @property
    def kill(self) -> Optional[int]:
        return self.battle_result.kill

    @property
    def death(self) -> Optional[int]:
        return self.battle_result.death

    @property
    def special(self) -> Optional[int]:
        return self.battle_result.special

    @property
    def stage(self) -> str:
        return self.battle_result.stage or ""

    @property
    def start(self) -> datetime.datetime:
        if self.battle_result.start is None:
            raise ValueError("Invalid start time")
        return self.battle_result.start

    @property
    def battle(self) -> str:
        return self.battle_result.battle or ""

    @property
    def rule(self) -> str:
        return self.battle_result.rule or ""

    @property
    def srt(self) -> Optional[List[srt.Subtitle]]:
        srt_str = FFmpeg.get_subtitle(self.path)
        if srt_str.is_err():
            return None
        return list(srt.parse(srt_str.unwrap()))

    @property
    def length(self) -> float:
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
