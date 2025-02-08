import os
import logging
import shutil
import glob
import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from youtube import Youtube
from ffmpeg import FFmpeg
from upload_file import UploadFile
import utility.os as os_utility

logger = logging.getLogger(__name__)


class Uploader:
    RECORDED_DIR = os.path.join(
        os.path.dirname(__file__), "videos", "recorded")
    PENDING_DIR = os.path.join(os.path.dirname(
        __file__), "videos", "upload_pending")
    THUMBNAIL_ASSETS_DIR = os.path.join(
        os.path.dirname(__file__), "thumbnail_assets")
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
    def queue(path: str, start_datetime: datetime.datetime, match: str, rule: str, stage: str, result: str, xpower: Optional[float], result_image: Optional[np.ndarray]):
        # リザルト画像がある場合、サムネイル画像として動画に付与する
        if result_image is not None:
            image_path = os.path.splitext(path)[0] + ".png"
            cv2.imwrite(image_path, result_image)
            FFmpeg.set_thumbnail(path, image_path)
            os_utility.remove_file(image_path)

        # 動画を規定の場所に移動(キューに追加)
        new_file_base_name = UploadFile.make_file_base_name(
            start_datetime, match, rule, stage, result, xpower)
        _, extension = os.path.splitext(os.path.basename(path))
        new_path = os.path.join(Uploader.RECORDED_DIR,
                                new_file_base_name + extension)
        os_utility.rename_file(path, new_path)

    def __init__(self):
        super().__init__()

        os.makedirs(self.RECORDED_DIR, exist_ok=True)
        os.makedirs(self.PENDING_DIR, exist_ok=True)

        self._youtube = Youtube()

    def _timedelta_to_str(self, delta: datetime.timedelta) -> str:
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def _generate_title_and_description(self, files: List[UploadFile], day: datetime.date, time: datetime.time, battle: str, rule: str) -> Tuple[str, str]:
        description = ""
        elapsed_time = 0
        win_count = 0
        lose_count = 0
        last_xpower = 0.0

        for file in files:
            # タイトルに付けるため、勝敗数をカウント
            if file.result == "WIN":
                win_count += 1
            elif file.result == "LOSE":
                lose_count += 1

            # Xパワーの変動があったタイミングだけ説明にXパワーを記載
            if file.xpower and last_xpower != file.xpower:
                description += f"XP: {file.xpower}\n"
                last_xpower = file.xpower

            elapsed_time_str = self._timedelta_to_str(
                datetime.timedelta(seconds=elapsed_time))
            description += f"{elapsed_time_str} {
                file.result.ljust(4)} {file.stage} \n"
            elapsed_time += file.length

        xpowers = [file.xpower for file in files if file.xpower]
        max_xpower = max(xpowers) if len(xpowers) > 0 else None
        min_xpower = min(xpowers) if len(xpowers) > 0 else None
        if len(xpowers) == 0:
            xpower = ""
        elif max_xpower == min_xpower:
            xpower = f"({max_xpower})"
        else:
            common_length = 0
            min_xpower_str = str(min_xpower)
            max_xpower_str = str(max_xpower)
            for i in range(min(len(min_xpower_str), len(max_xpower_str))):
                if min_xpower_str[i] == max_xpower_str[i]:
                    common_length += 1
                else:
                    break
            xpower = f"({min_xpower_str}-{max_xpower_str[common_length:]})"

        day_str = day.strftime("'%y.%m.%d")
        time_str = time.strftime("%H").lstrip("0")

        title = f"{day_str} {time_str}時～ {battle}{
            xpower} {rule} {win_count}勝{lose_count}敗"
        return title, description

    def _concat_videos_by_time_range(self):
        files = glob.glob(f'{self.RECORDED_DIR}/*.*')
        recorded_video_files = [UploadFile(path) for path in files]
        time_scheduled_files = UploadFile.split_by_time_ranges(
            recorded_video_files, self.TIME_RANGES)
        for key, files in time_scheduled_files.items():
            day, time, battle, rule = key

            extension = files[0].extension
            file_name = f"{day.strftime(
                "%Y-%m-%d")}_{time.strftime("%H")}_{battle}_{rule}{extension}"
            path = os.path.join(self.PENDING_DIR, file_name)

            if len(files) == 1:
                shutil.copyfile(files[0].path, path)
            else:
                file_names = [file.path for file in files]
                FFmpeg.concat(file_names, path)

            title, description = self._generate_title_and_description(
                files, day, time, battle, rule)
            FFmpeg.write_metadata(path, FFmpeg.Metadata(title, description))

            thumnail_path = os.path.splitext(path)[0] + ".png"
            thumnail_path = self._create_thumbnail(thumnail_path, files)
            if thumnail_path and os.path.exists(thumnail_path):
                FFmpeg.set_thumbnail(path, thumnail_path)
                os_utility.remove_file(thumnail_path)

            if any(os_utility.remove_file(file.path).is_err() for file in files):
                logger.warning(
                    "結合前のファイル削除に失敗したため、結合後のファイルが再度アップロードされる可能性があります")

    def _create_thumbnail(self, thumnail_path: str, files: List[UploadFile]) -> Optional[str]:
        for file in files:
            if FFmpeg.has_thumbnail(file.path) and FFmpeg.get_thumbnail(file.path, thumnail_path):
                break
        if not os.path.exists(thumnail_path):
            return None

        battle = files[0].battle
        rule = files[0].rule
        xpowers = [file.xpower for file in files if file.xpower]
        min_xpower = min(xpowers) if len(xpowers) > 0 else None
        max_xpower = max(xpowers) if len(xpowers) > 0 else None
        rate = None if min_xpower is None else \
            f"XP: {min_xpower}" if min_xpower == max_xpower else \
            f"XP: {min_xpower} ~ {max_xpower}"
        stages = [file.stage for file in files]
        stages = list(dict.fromkeys(stages))
        stage1 = stages[0] if len(stages) > 0 else None
        stage2 = stages[1] if len(stages) > 1 else None

        self._design_thumbnail(
            thumnail_path, battle, rule, rate, stage1, stage2)
        return thumnail_path

    def _design_thumbnail(self, thumbnail_path: str, battle: str, rule: str, rate: Optional[str], stage1: Optional[str], stage2: Optional[str]):
        thumbnail = Image.open(thumbnail_path).convert("RGBA")
        draw = ImageDraw.Draw(thumbnail)
        # 不要なステージ部分を塗りつぶし
        draw.rounded_rectangle((777, 21, 1849, 750), radius=40,
                               fill=(28, 28, 28), outline=(28, 28, 28), width=1)

        # バトルのアイコンを追加
        path = os.path.join(self.THUMBNAIL_ASSETS_DIR, f"{battle}.png")
        if os.path.exists(path):
            battle_image = Image.open(path).convert("RGBA")
            battle_image = battle_image.resize((300, 300))
            thumbnail.paste(battle_image, (800, 40), battle_image)
        else:
            logger.warning(f"バトルアイコンが見つかりません: {battle}")

        # ルールの文字を追加
        path = os.path.join(self.THUMBNAIL_ASSETS_DIR, "ikamodoki1.ttf")
        font = ImageFont.truetype(path, 140)
        draw.text((1120, 50), rule, fill="white", font=font)

        # ルールのアイコンを追加
        path = os.path.join(self.THUMBNAIL_ASSETS_DIR, f"{rule}.png")
        if os.path.exists(path):
            rule_image = Image.open(path).convert("RGBA")
            rule_image = rule_image.resize((150, 150))
            thumbnail.paste(rule_image, (1660, 70), rule_image)
        else:
            logger.warning(f"ルールアイコンが見つかりません: {rule}")

        # レートの文字を追加
        if rate:
            text_color = (1, 249, 196) if battle == "Xマッチ" else "white"
            path = os.path.join(self.THUMBNAIL_ASSETS_DIR,
                                "Paintball_Beta.otf")
            font = ImageFont.truetype(path, 70)
            draw.text((1125, 230), rate, fill=text_color, font=font)

        # ステージ画像を追加
        path = os.path.join(self.THUMBNAIL_ASSETS_DIR, f"{stage1}.png")
        if stage1 and os.path.exists(path):
            stage1_image = Image.open(path).convert("RGBA")
            stage1_image = stage1_image.resize((960, 168))
            thumbnail.paste(stage1_image, (860, 360), stage1_image)
        else:
            logger.warning(f"ステージ画像が見つかりません: {stage1}")

        path = os.path.join(self.THUMBNAIL_ASSETS_DIR, f"{stage2}.png")
        if stage2 and os.path.exists(path):
            stage2_image = Image.open(path).convert("RGBA")
            stage2_image = stage2_image.resize((960, 168))
            thumbnail.paste(stage2_image, (860, 540), stage2_image)
        else:
            logger.warning(f"ステージ画像が見つかりません: {stage2}")

        thumbnail.save(thumbnail_path)

    def _upload_to_youtube(self):
        files = glob.glob(f'{self.PENDING_DIR}/*.*')
        for path in files:
            metadata = FFmpeg.read_metadata(path)
            logger.info(f"YouTubeにアップロードします: {metadata.title}")
            video_id = self._youtube.upload(
                path, metadata.title, metadata.comment)
            if not video_id:
                logger.info("YouTubeへのアップロードに失敗しました")
                continue

            logger.info("YouTubeにアップロードしました")
            try:
                thumbnail_path = os.path.join(
                    self.PENDING_DIR, f"{video_id}.png")
                FFmpeg.get_thumbnail(path, thumbnail_path)
                self._youtube.set_thumbnail(video_id, thumbnail_path)
            except Exception as e:
                logger.warning(f"サムネイルのアップロードに失敗しました: {e}")

            if os_utility.remove_file(thumbnail_path).is_err():
                logger.warning("サムネイルの削除に失敗しました")

            if os_utility.remove_file(path).is_err():
                logger.warning(
                    "アップロード後のファイル削除に失敗したため、同じファイルが再度アップロードされる可能性があります")

    def upload(self):
        logger.info("アップロード処理を開始します")
        self._concat_videos_by_time_range()
        self._upload_to_youtube()
        logger.info("アップロード処理が完了しました")


# 直接Uploaderスクリプトを実行したとき、アップロードを実行する
if __name__ == '__main__':
    uploader = Uploader()
    uploader.upload()
