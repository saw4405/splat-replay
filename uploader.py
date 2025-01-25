import os
import logging
import shutil
import glob
import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import cv2

from youtube import Youtube
from ffmpeg import FFmpeg

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

    def _extract_metadata(self, file_base_name: str) -> List[str]:
        metadata = file_base_name.split("_")
        if len(metadata) not in (5, 6):
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
    def make_file_base_name(cls, start: datetime.datetime, match: str, rule: str, stage: str, result: str, xpower: Optional[float] = None) -> str:
        # スケジュール毎に結合できるよう、録画開始日時(バトル開始日時)、マッチ、ルールをファイル名に含める
        # 動画説明に各試合の結果を記載するため、結果もファイル名に含める
        start_str = start.strftime(cls.DATETIME_FORMAT)
        file_base_name = f"{start_str}_{match}_{rule}_{stage}_{result}"
        if xpower:
            file_base_name += f"_{xpower}"
        return file_base_name


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
        (datetime.time(23, 0), datetime.time(1, 0))
    ]

    @staticmethod
    def queue(path: str, start_datetime: datetime.datetime, match: str, rule: str, stage: str, result: str, xpower: Optional[float] = None):
        new_file_base_name = UploadFile.make_file_base_name(
            start_datetime, match, rule, stage, result, xpower)
        _, extension = os.path.splitext(os.path.basename(path))
        new_path = os.path.join(Uploader.RECORDED_DIR,
                                new_file_base_name + extension)
        os.rename(path, new_path)

    def __init__(self):
        super().__init__()

        os.makedirs(self.RECORDED_DIR, exist_ok=True)
        os.makedirs(self.PENDING_DIR, exist_ok=True)

        self._youtube = Youtube()

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
        time_scheduled_files = defaultdict(list)

        for upload_file in upload_files:
            file_datetime = upload_file.start
            file_date = file_datetime.date()
            file_time = file_datetime.time()

            for _, (schedule_start_time, schedule_end_time) in enumerate(self.TIME_RANGES):
                # 日をまたがない時間帯 (1:00-23:00)
                if schedule_start_time < schedule_end_time:
                    # スケジュールに該当する場合
                    if schedule_start_time <= file_time < schedule_end_time:
                        key = (file_date, schedule_start_time,
                               upload_file.battle, upload_file.rule)
                        time_scheduled_files[key].append(upload_file)
                        break

                # 日をまたぐ時間帯 (23:00-1:00)
                else:
                    # スケジュールに該当する場合
                    if file_time >= schedule_start_time or file_time < schedule_end_time:
                        # 日をまたぐ場合は1:00を含む日付に調整
                        adjusted_date = file_date if file_time >= schedule_start_time else file_date - \
                            datetime.timedelta(days=1)
                        key = (adjusted_date, schedule_start_time,
                               upload_file.battle, upload_file.rule)
                        time_scheduled_files[key].append(upload_file)
                        break
        return time_scheduled_files

    def _concat_files(self, files: List[UploadFile], output_path: str):
        # ファイルが一つの場合は結合する必要がないのでリネーム＆移動
        if len(files) == 1:
            shutil.copyfile(files[0].path, output_path)
            return

        file_names = [file.path for file in files]
        FFmpeg.concat(file_names, output_path)

    def _generate_title_and_description(self, files: List[UploadFile], day: datetime.date, time: datetime.time, battle: str, rule: str) -> Tuple[str, str]:
        description = ""
        elapsed_time = 0
        win_count = 0
        lose_count = 0
        last_xpower = 0.0
        max_xpower: Optional[float] = None
        min_xpower: Optional[float] = None

        for file in files:
            # タイトルに付けるため、勝敗数をカウント
            if "WIN" in file.result:
                win_count += 1
            elif "LOSE" in file.result:
                lose_count += 1

            if file.xpower:
                # タイトルにつけるため、最大と最小のXパワーを取得
                max_xpower = max(
                    max_xpower, file.xpower) if max_xpower is not None else file.xpower
                min_xpower = min(
                    min_xpower, file.xpower) if min_xpower is not None else file.xpower

                # Xパワーの変動があったタイミングだけ説明にXパワーを記載
                if last_xpower != file.xpower:
                    description += f"XP: {file.xpower}\n"
                    last_xpower = file.xpower

            elapsed_time_str = self._timedelta_to_str(
                datetime.timedelta(seconds=elapsed_time))
            description += f"{elapsed_time_str} {file.result} {file.stage} \n"
            elapsed_time += file.length

        if max_xpower and min_xpower:
            if max_xpower == min_xpower:
                xpower = f"({max_xpower})"
            else:
                common_prefix_length = 0
                min_xpower_str = str(min_xpower)
                max_xpower_str = str(max_xpower)
                for i in range(min(len(min_xpower_str), len(max_xpower_str))):
                    if min_xpower_str[i] == max_xpower_str[i]:
                        common_prefix_length += 1
                    else:
                        break
                xpower = f"({
                    min_xpower_str}-{max_xpower_str[common_prefix_length:]})"
        else:
            xpower = ""

        day_str = day.strftime("'%y.%m.%d")
        time_str = time.strftime("%H").lstrip("0")

        title = f"{day_str} {time_str}時～ {battle}{
            xpower} {rule} {win_count}勝{lose_count}敗"
        return title, description

    def _delete_files(self, files: List[str]) -> bool:
        result = True
        for file in files:
            try:
                os.remove(file)
            except Exception as e:
                logger.error(f"ファイルの削除に失敗しました: {e}\n{file}")
                result = False

        return result

    def upload(self):
        logger.info("アップロード処理を開始します")
        upload_files = self._get_upload_files()
        time_scheduled_files = self._split_by_time_ranges(upload_files)

        # 時間帯ごとにファイルを結合してアップロード
        for key, files in time_scheduled_files.items():
            day, time, battle, rule = key

            extension = files[0].extension
            file_name = f"{day.strftime(
                "%Y-%m-%d")}_{time.strftime("%H")}_{battle}_{rule}{extension}"
            path = os.path.join(self.PENDING_DIR, file_name)

            self._concat_files(files, path)
            title, description = self._generate_title_and_description(
                files, day, time, battle, rule)

            logger.info(f"YouTubeにアップロードします: {title}")
            res = self._youtube.upload(path, title, description)
            if res:
                logger.info("YouTubeにアップロードしました")
                delete_files = [path] + [file.path for file in files]
                if not self._delete_files(delete_files):
                    logger.warning(
                        "アップロード後のファイル削除に失敗したため、同じファイルが再度アップロードされる可能性があります")
            else:
                logger.info("YouTubeへのアップロードに失敗しました")

        logger.info("アップロード処理が完了しました")


# 直接Uploaderスクリプトを実行したとき、アップロードを実行する
if __name__ == '__main__':
    uploader = Uploader()
    uploader.upload()
