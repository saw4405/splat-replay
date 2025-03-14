import os
import logging
import shutil
import glob
import datetime
import io
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from wrapper.youtube import Youtube, PrivacyStatus
from battle_result import BattleResult
from models.rate import RateBase, XP, Udemae
from wrapper.ffmpeg import FFmpeg
from upload_file import UploadFile
import utility.os as os_utility
import logger_config

logger = logging.getLogger(__name__)


class Uploader:
    RECORDED_DIR = os.path.join(os.getcwd(), "output", "recorded")
    PENDING_DIR = os.path.join(os.getcwd(), "output", "edited")
    THUMBNAIL_ASSETS_DIR = os.path.join(os.getcwd(), "assets", "thumbnail")
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
    def queue(path: str, battle_result: BattleResult, result_image: Optional[np.ndarray], srt_str: Optional[str]):
        # 動画を規定の場所に移動(キューに追加)
        new_file_base_name = UploadFile.make_file_base_name(battle_result)
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

        self._private_status: PrivacyStatus = "private" if os.environ.get(
            "YOUTUBE_VIDEO_PUBLIC", "false").lower() == "false" else "public"
        self._playlist_id = os.environ.get("YOUTUBE_PLAYLIST_ID")
        self._title_template = os.environ.get(
            "YOUTUBE_TITLE_TEMPLATE", "{BATTLE}({RATE}) {RULE} {WIN}勝{LOSE}敗 {DAY} {SCHEDULE}時～")
        self._description_template = os.environ.get(
            "YOUTUBE_DESCRIPTION_TEMPLATE", "{CHAPTERS}")
        self._chapter_template = os.environ.get(
            "YOUTUBE_CHAPTER_TITLE_TEMPLATE", "{RESULT} {KILL}k {DEATH}d {SPECIAL}s {STAGE}")
        self.volume_multiplier = float(
            os.environ.get("VOLUME_MULTIPLIER", 1.0))

        os.makedirs(self.RECORDED_DIR, exist_ok=True)
        os.makedirs(self.PENDING_DIR, exist_ok=True)

        self._youtube = Youtube()

    @staticmethod
    def format_seconds(seconds: float) -> str:
        total_seconds = int(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    def _generate_title_and_description(self, files: List[UploadFile], day: datetime.date, time: datetime.time, battle: str, rule: str) -> Tuple[str, str]:
        elapsed_time = 0
        win_count = 0
        lose_count = 0
        last_rate: Optional[RateBase] = None

        chapters = ""
        for file in files:
            # タイトルに付けるため、勝敗数をカウント
            win_count += (file.result == "WIN")
            lose_count += (file.result == "LOSE")

            # Xパワーの変動があったタイミングだけ説明にXパワーを記載
            if file.rate and last_rate != file.rate:
                chapters += f"{file.rate.label}: {file.rate}\n"
                last_rate = file.rate

            elapsed_time_str = Uploader.format_seconds(elapsed_time)

            chapter_title = self._chapter_template.replace("{RESULT}", file.result).replace("{KILL}", str(file.kill) if file.kill else "-").replace("{DEATH}", str(file.death) if file.death else "-").replace("{SPECIAL}", str(file.special) if file.special else "-").replace(
                "{STAGE}", file.stage).replace("{RATE}", f"{file.rate.label}{file.rate}" if file.rate else "").replace("{BATTLE}", file.battle).replace("{RULE}", file.rule).replace("{START_TIME}", file.start.strftime("%H:%M:%S"))
            chapter = f"{elapsed_time_str} {chapter_title}\n"
            chapters += chapter
            elapsed_time += file.length

        rates = [file.rate for file in files if file.rate]
        if len(rates) == 0:
            rate = ""
        else:
            max_rate = max(rates).short_str()
            min_rate = min(rates).short_str()
            rate_prefix = rates[0].label if battle == "Xマッチ" else ""
            if min_rate == max_rate:
                rate = f"{rate_prefix}{min_rate}"
            else:
                rate = f"{rate_prefix}{min_rate}-{max_rate}"

        stages = ",".join(list(dict.fromkeys([file.stage for file in files])))

        day_str = day.strftime("'%y.%m.%d")
        time_str = time.strftime("%H").lstrip("0")

        title = self._title_template.replace("{BATTLE}", battle).replace("{RULE}", rule).replace("{RATE}", rate).replace(
            "{WIN}", str(win_count)).replace("{LOSE}", str(lose_count)).replace("{DAY}", day_str).replace("{SCHEDULE}", time_str).replace("{STAGES}", stages)
        description = self._description_template.replace("{CHAPTERS}", chapters).replace("{BATTLE}", battle).replace("{RULE}", rule).replace("{RATE}", rate).replace(
            "{WIN}", str(win_count)).replace("{LOSE}", str(lose_count)).replace("{DAY}", day_str).replace("{SCHEDULE}", time_str).replace("{STAGES}", stages)
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
        logger.info("タイムスケジュール毎に動画を結合します")
        files = glob.glob(f'{self.RECORDED_DIR}/*.*')
        recorded_video_files = [UploadFile(path) for path in files]
        time_scheduled_files = self._split_by_time_ranges(recorded_video_files)

        for key, files in time_scheduled_files.items():
            day, time, battle, rule = key
            day_str = day.strftime("%Y-%m-%d")
            time_str = time.strftime("%H")
            logger.info(
                f"タイムスケジュールが{day_str} {time_str}時～の{battle} {rule}の動画を結合します")

            extension = files[0].extension
            file_name = f"{day_str}_{time_str}_{battle}_{rule}{extension}"
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
        rates = [file.rate for file in files if file.rate]
        if len(rates) == 0:
            rate = None
        else:
            min_rate = min(rates)
            max_rate = max(rates)
            rate_prefix = f"{min_rate.label}: " if battle == "Xマッチ" else ""
            if min_rate == max_rate:
                rate = f"{rate_prefix}{min_rate}"
            else:
                rate = f"{rate_prefix}{min_rate} ~ {max_rate}"
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
            text_color = (1, 249, 196) if battle == "Xマッチ" else \
                (250, 97, 0) if battle.startswith("バンカラマッチ") else "white"
            path = os.path.join(self.THUMBNAIL_ASSETS_DIR,
                                "Paintball_Beta.otf")
            font = ImageFont.truetype(path, 70)
            draw.text((1125, 230), rate, fill=text_color, font=font)

        # ステージ画像を追加
        if stage1:
            path = os.path.join(self.THUMBNAIL_ASSETS_DIR, f"{stage1}.png")
            if os.path.exists(path):
                stage1_image = Image.open(path).convert("RGBA")
                stage1_image = stage1_image.resize((960, 168))
                thumbnail.paste(stage1_image, (860, 360), stage1_image)
            else:
                logger.warning(f"ステージ画像が見つかりません: {stage1}")
        else:
            logger.warning("ステージを検出できていません")

        if stage2:
            path = os.path.join(self.THUMBNAIL_ASSETS_DIR, f"{stage2}.png")
            if os.path.exists(path):
                stage2_image = Image.open(path).convert("RGBA")
                stage2_image = stage2_image.resize((960, 168))
                thumbnail.paste(stage2_image, (860, 540), stage2_image)
            else:
                logger.warning(f"ステージ画像が見つかりません: {stage2}")
        # 2つ目のステージがないことはあるので、警告は出さない

        buf = io.BytesIO()
        thumbnail.save(buf, format='PNG')
        return buf.getvalue()

    def _change_volume(self, path: str, volume_multiplier: float):
        if volume_multiplier == 1.0:
            return

        logger.info(f"動画の音量を{volume_multiplier}倍に変更します")
        FFmpeg.change_volume(path, volume_multiplier)

    def _upload_video(self, path: str) -> Optional[str]:
        result = FFmpeg.read_metadata(path)
        if result.is_err():
            logger.error("アップロードする動画のメタデータ取得に失敗しました")
            return None

        metadata = result.unwrap()
        logger.info(f"YouTubeにアップロードします: {metadata.title}")
        result = self._youtube.upload(
            path, metadata.title, metadata.comment, ["スプラトゥーン3"], privacy_status=self._private_status)
        if result.is_err():
            logger.info(f"YouTubeへのアップロードに失敗しました: {result.unwrap_err()}")
            return None

        video_id = result.unwrap()
        logger.info(f"YouTubeにアップロードしました: {video_id}")
        return video_id

    def _set_thumbnail(self, path: str, video_id: str):
        result = FFmpeg.get_thumbnail(path)
        if result.is_err():
            logger.warning(f"サムネイルの取得に失敗しました: {result.unwrap_err()}")
            return

        logger.info("サムネイルをアップロードします")
        thumbnail_data = result.unwrap()
        thumbnail_path = os.path.join(self.PENDING_DIR, f"{video_id}.png")
        try:
            with open(thumbnail_path, "wb") as f:
                f.write(thumbnail_data)
            result = self._youtube.set_thumbnail(video_id, thumbnail_path)
            if result.is_err():
                logger.warning(
                    f"サムネイルのアップロードに失敗しました: {result.unwrap_err()}")
        except Exception as e:
            logger.warning(f"サムネイルのアップロードに失敗しました: {e}")
        finally:
            if os_utility.remove_file(thumbnail_path).is_err():
                logger.warning(f"サムネイルの削除に失敗しました: {thumbnail_path}")

    def _insert_caption(self, path: str, video_id: str):
        result = FFmpeg.get_subtitle(path)
        if result.is_err():
            logger.warning(f"字幕の取得に失敗しました: {result.unwrap_err()}")
            return

        logger.info("字幕をアップロードします")
        srt = result.unwrap()
        srt_path = os.path.join(self.PENDING_DIR, f"{video_id}.srt")
        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt)
            result = self._youtube.insert_caption(video_id, srt_path, "ひとりごと")
            if result.is_err():
                logger.warning(
                    f"字幕のアップロードに失敗しました: {result.unwrap_err()}")
        except Exception as e:
            logger.warning(f"字幕のアップロードに失敗しました: {e}")
        finally:
            if os_utility.remove_file(srt_path).is_err():
                logger.warning(f"字幕の削除に失敗しました: {srt_path}")

    def _insert_to_playlist(self, video_id: str):
        if not self._playlist_id:
            logger.warning("プレイリストIDが指定されていません")
            return

        logger.info("プレイリストに挿入します")
        result = self._youtube.insert_to_playlist(video_id, self._playlist_id)
        if result.is_err():
            logger.warning(f"プレイリストへの挿入に失敗しました: {result.unwrap_err()}")

    def _upload_to_youtube(self):
        logger.info("YouTubeに動画をアップロードします")
        files = glob.glob(f'{self.PENDING_DIR}/*.*')
        for path in files:
            self._change_volume(path, self.volume_multiplier)

            video_id = self._upload_video(path)
            if video_id is None:
                continue

            self._set_thumbnail(path, video_id)
            self._insert_caption(path, video_id)
            self._insert_to_playlist(video_id)

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
    logger_config.setup_logger()
    uploader = Uploader()
    uploader.upload()
