import os
import logging
import shutil
import glob
import datetime
import io
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import srt

from wrapper.youtube import Youtube
from wrapper.ffmpeg import FFmpeg
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
    def queue(path: str, start_datetime: datetime.datetime, match: str, rule: str, stage: str, result: str, xpower: Optional[float], result_image: Optional[np.ndarray], srt_str: Optional[str]):
        # 動画を規定の場所に移動(キューに追加)
        new_file_base_name = UploadFile.make_file_base_name(
            start_datetime, match, rule, stage, result, xpower)
        _, extension = os.path.splitext(os.path.basename(path))
        new_path = os.path.join(Uploader.RECORDED_DIR,
                                new_file_base_name + extension)
        os_utility.rename_file(path, new_path)

        upload_file = UploadFile(new_path)

        # リザルト画像がある場合、サムネイル画像として動画に埋め込む
        if result_image is not None:
            upload_file.set_thumbnail(result_image)

        # 字幕を動画に埋め込む
        if srt_str:
            upload_file.embed_subtitles(srt_str)

    def __init__(self):
        super().__init__()

        os.makedirs(self.RECORDED_DIR, exist_ok=True)
        os.makedirs(self.PENDING_DIR, exist_ok=True)

        self._youtube = Youtube()

    @staticmethod
    def format_seconds(seconds: float) -> str:
        total_seconds = int(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    @staticmethod
    def xp_prefix(xpower: float) -> str:
        return str(int(xpower) // 100)

    def _generate_title_and_description(self, files: List[UploadFile], day: datetime.date, time: datetime.time, battle: str, rule: str) -> Tuple[str, str]:
        description = ""
        elapsed_time = 0
        win_count = 0
        lose_count = 0
        last_xpower = 0.0

        for file in files:
            # タイトルに付けるため、勝敗数をカウント
            win_count += (file.result == "WIN")
            lose_count += (file.result == "LOSE")

            # Xパワーの変動があったタイミングだけ説明にXパワーを記載
            if file.xpower and last_xpower != file.xpower:
                description += f"XP: {file.xpower}\n"
                last_xpower = file.xpower

            elapsed_time_str = Uploader.format_seconds(elapsed_time)
            line = f"{elapsed_time_str} {file.result.ljust(4)} {file.stage} \n"
            description += line
            elapsed_time += file.length

        xpowers = [file.xpower for file in files if file.xpower]
        if len(xpowers) == 0:
            xpower = ""
        else:
            max_xpower_prefix = Uploader.xp_prefix(max(xpowers))
            min_xpower_prefix = Uploader.xp_prefix(min(xpowers))
            if min_xpower_prefix == max_xpower_prefix:
                xpower = f"(XP{min_xpower_prefix})"
            else:
                xpower = f"(XP{min_xpower_prefix}-{max_xpower_prefix})"

        day_str = day.strftime("'%y.%m.%d")
        time_str = time.strftime("%H").lstrip("0")

        title = f"{battle}{xpower} {rule} {win_count}勝{lose_count}敗 {day_str} {time_str}時～"
        return title, description

    def _split_by_time_ranges(self, files: List[UploadFile]) -> Dict[Tuple[datetime.date, datetime.time, str, str], List[UploadFile]]:
        time_scheduled_files = defaultdict(list)
        for file in files:
            file_datetime = file.start
            file_date = file_datetime.date()
            file_time = file_datetime.time()

            for schedule_start_time, schedule_end_time in self.TIME_RANGES:
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

    def _concat_videos_by_time_range(self):
        files = glob.glob(f'{self.RECORDED_DIR}/*.*')
        recorded_video_files = [UploadFile(path) for path in files]
        time_scheduled_files = self._split_by_time_ranges(recorded_video_files)
        for key, files in time_scheduled_files.items():
            day, time, battle, rule = key

            extension = files[0].extension
            file_name = f"{day.strftime(
                "%Y-%m-%d")}_{time.strftime("%H")}_{battle}_{rule}{extension}"
            path = os.path.join(self.PENDING_DIR, file_name)

            # 動画を結合する
            if len(files) == 1:
                shutil.copyfile(files[0].path, path)
            else:
                file_names = [file.path for file in files]
                FFmpeg.concat(file_names, path)

            # タイトルと説明を動画に埋め込む
            title, description = self._generate_title_and_description(
                files, day, time, battle, rule)
            FFmpeg.write_metadata(path, FFmpeg.Metadata(title, description))

            # サムネイル画像を作成して動画に埋め込む
            thumnail_data = self._create_thumbnail(files)
            if thumnail_data is not None:
                FFmpeg.set_thumbnail(path, thumnail_data)

            # 字幕を結合して動画に埋め込む
            combined_subtitles: List[srt.Subtitle] = []
            offset = datetime.timedelta(seconds=0)
            for file in files:
                subtitles = file.srt
                if subtitles:
                    for subtitle in subtitles:
                        subtitle.start += offset
                        subtitle.end += offset
                    combined_subtitles.extend(subtitles)
                offset += datetime.timedelta(seconds=file.length)
            combined_srt: str = srt.compose(combined_subtitles)
            FFmpeg.set_subtitle(path, combined_srt)

            if any(os_utility.remove_file(file.path).is_err() for file in files):
                logger.warning(
                    "結合前のファイル削除に失敗したため、結合後のファイルが再度アップロードされる可能性があります")

    def _create_thumbnail(self, files: List[UploadFile]) -> Optional[bytes]:
        thumbnail_data = None
        for file in files:
            result = FFmpeg.get_thumbnail(file.path)
            if result.is_ok():
                thumbnail_data = result.unwrap()
                break
        if thumbnail_data is None:
            logger.warning("サムネイル画像が見つかりません")
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

        thumbnail_data = self._design_thumbnail(
            thumbnail_data, battle, rule, rate, stage1, stage2)
        return thumbnail_data

    def _design_thumbnail(self, thumbnail_data: bytes, battle: str, rule: str, rate: Optional[str], stage1: Optional[str], stage2: Optional[str]) -> bytes:
        thumbnail = Image.open(io.BytesIO(thumbnail_data)).convert("RGBA")
        draw = ImageDraw.Draw(thumbnail)
        # 不要なステージ部分を塗りつぶし
        draw.rounded_rectangle((777, 21, 1849, 750), radius=40,
                               fill=(28, 28, 28), outline=(28, 28, 28), width=1)

        # バトルのアイコンを追加
        battle = battle.split("(")[0]
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

        buf = io.BytesIO()
        thumbnail.save(buf, format='PNG')
        return buf.getvalue()

    def _upload_to_youtube(self):
        files = glob.glob(f'{self.PENDING_DIR}/*.*')
        for path in files:
            result = FFmpeg.read_metadata(path)
            if result.is_err():
                logger.error("アップロードする動画のメタデータ取得に失敗しました")
                continue
            metadata = result.unwrap()
            logger.info(f"YouTubeにアップロードします: {metadata.title}")
            result = self._youtube.upload(
                path, metadata.title, metadata.comment)
            if result.is_err():
                logger.info("YouTubeへのアップロードに失敗しました")
                continue
            logger.info("YouTubeにアップロードしました")
            video_id = result.unwrap()

            thumbnail_path = os.path.join(self.PENDING_DIR, f"{video_id}.png")
            try:
                result = FFmpeg.get_thumbnail(path)
                if result.is_ok():
                    with open(thumbnail_path, "wb") as f:
                        f.write(result.unwrap())
                    self._youtube.set_thumbnail(video_id, thumbnail_path)
            except Exception as e:
                logger.warning(f"サムネイルのアップロードに失敗しました: {e}")
            finally:
                if os_utility.remove_file(thumbnail_path).is_err():
                    logger.warning("サムネイルの削除に失敗しました")

            srt_path = os.path.join(self.PENDING_DIR, f"{video_id}.srt")
            try:
                result = FFmpeg.get_subtitle(path)
                if result.is_ok():
                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(result.unwrap())
                    self._youtube.insert_caption(video_id, srt_path, "ひとりごと")
            except Exception as e:
                logger.warning(f"字幕のアップロードに失敗しました: {e}")
            finally:
                if os_utility.remove_file(srt_path).is_err():
                    logger.warning("字幕の削除に失敗しました")

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
