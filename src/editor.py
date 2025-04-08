import os
import datetime
import shutil
import io
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import logging

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import srt

from upload_file import UploadFile
from wrapper.ffmpeg import FFmpeg
import utility.os as os_utility
from models.rate import RateBase

logger = logging.getLogger(__name__)


class Editor:
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

    def __init__(self, output_dir: str):
        self.OUTPUT_DIR = output_dir
        self._title_template = os.environ.get(
            "YOUTUBE_TITLE_TEMPLATE", "{BATTLE}({RATE}) {RULE} {WIN}勝{LOSE}敗 {DAY} {SCHEDULE}時～")
        self._description_template = os.environ.get(
            "YOUTUBE_DESCRIPTION_TEMPLATE", "{CHAPTERS}")
        self._chapter_template = os.environ.get(
            "YOUTUBE_CHAPTER_TITLE_TEMPLATE", "{RESULT} {KILL}k {DEATH}d {SPECIAL}s {STAGE}")
        self.volume_multiplier = float(
            os.environ.get("VOLUME_MULTIPLIER", 1.0))

    def start(self, recorded_files: List[UploadFile]):
        logger.info("タイムスケジュール毎に動画を結合します")
        time_scheduled_files = self._split_by_time_ranges(recorded_files)
        for (day, time, battle, rule), files in time_scheduled_files.items():
            day_str = day.strftime("%Y-%m-%d")
            time_str = time.strftime("%H")
            logger.info(
                f"タイムスケジュールが{day_str} {time_str}時～の{battle} {rule}の動画を結合します")

            out_path = os.path.join(self.OUTPUT_DIR, f"{day_str}_{time_str}_{battle}_{rule}{files[0].extension}")

            # 動画を結合する
            if len(files) == 1:
                shutil.copyfile(files[0].path, out_path)
            else:
                file_names = [file.path for file in files]
                FFmpeg.concat(file_names, out_path)

            # タイトルと説明を動画に埋め込む
            title, description = self._generate_title_and_description(
                files, day, time, battle, rule)
            FFmpeg.write_metadata(out_path, FFmpeg.Metadata(title, description))

            # サムネイル画像を作成して動画に埋め込む
            thumnail_data = self._create_thumbnail(files)
            if thumnail_data is not None:
                FFmpeg.set_thumbnail(out_path, thumnail_data)

            # 字幕を結合して動画に埋め込む (最初のファイルに字幕がないと、結合後のファイルに字幕が埋め込まれないため、手動で結合)
            combined_subtitles = self._combine_subtitles(files)
            combined_srt: str = srt.compose(combined_subtitles)
            FFmpeg.set_subtitle(out_path, combined_srt)

            # 音量を変更する
            self._change_volume(out_path, self.volume_multiplier)

            # 編集完了したので、元のファイルを削除
            if any(os_utility.remove_file(file.path).is_err() for file in files):
                logger.warning(
                    "結合前のファイル削除に失敗したため、結合後のファイルが再度アップロードされる可能性があります")

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

    def _generate_title_and_description(self, files: List[UploadFile], day: datetime.date, time: datetime.time, battle: str, rule: str) -> Tuple[str, str]:
        def format_seconds(seconds: float) -> str:
            total_seconds = int(seconds)
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02}:{minutes:02}:{seconds:02}"

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

            tokens = {
                "RESULT": f"{file.result}  " if file.result == "WIN" else file.result,
                "KILL": "??" if file.kill is None else f"  {file.kill}" if file.kill < 10 else f"{file.kill}",
                "DEATH": "??" if file.death is None else f"  {file.death}" if file.death < 10 else f"{file.death}",
                "SPECIAL": "??" if file.special is None else f"  {file.special}" if file.special < 10 else f"{file.special}",
                "STAGE": file.stage,
                "RATE": f"{file.rate.label}{file.rate}" if file.rate else "",
                "BATTLE": file.battle,
                "RULE": file.rule,
                "START_TIME": file.start.strftime("%H:%M:%S")
            }
            chapter_title = self._chapter_template.format(**tokens)
            chapters += f"{format_seconds(elapsed_time)} {chapter_title}\n"
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

        tokens = {
            "BATTLE": battle,
            "RULE": rule,
            "RATE": rate,
            "WIN": win_count,
            "LOSE": lose_count,
            "DAY": day.strftime("'%y.%m.%d"),
            "SCHEDULE": time.strftime("%H").lstrip("0"),
            "STAGES": ",".join(list(dict.fromkeys([file.stage for file in files]))),
            "CHAPTERS": chapters
        }
        title = self._title_template.format(**tokens)
        description = self._description_template.format(**tokens)
        return title, description

    def _select_bright_thumbnail(self, files: List[UploadFile]) -> Optional[bytes]:
        best_thumbnail_data = None
        best_brightness = -1
        for file in files:
            result = FFmpeg.get_thumbnail(file.path)
            if result.is_err():
                continue
            data = result.unwrap()
            try:
                image = Image.open(io.BytesIO(data)).convert("HSV")
                width, height = image.size
                cropped_image = image.crop((0, 0, min(750, width), height))
                pixel_array = np.array(cropped_image)
                v_channel = pixel_array[:, :, 2]
                flat_pixels = v_channel.flatten()
                num_pixels = len(flat_pixels)
                n_top = max(1, int(num_pixels * 0.2))
                top_pixels = np.sort(flat_pixels)[-n_top:]
                brightness = np.mean(top_pixels)
            except Exception as e:
                logger.warning(f"サムネイル画像の明るさ計算失敗: {e}")
                brightness = 0
            if brightness > best_brightness:
                best_brightness = brightness
                best_thumbnail_data = data
        return best_thumbnail_data

    def _create_thumbnail(self, files: List[UploadFile]) -> Optional[bytes]:
        # 明るいサムネイルの選定処理を新関数に委譲
        thumbnail_data = self._select_bright_thumbnail(files)
        if thumbnail_data is None:
            logger.warning("サムネイル画像が見つかりません")
            return None

        win_count = sum(1 for file in files if file.result == "WIN")
        lose_count = sum(1 for file in files if file.result == "LOSE")
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
            thumbnail_data, win_count, lose_count, battle, rule, rate, stage1, stage2)
        return thumbnail_data

    def _draw_text_with_outline(self, draw: ImageDraw.ImageDraw, position: Tuple[int, int], text: str, font: ImageFont.FreeTypeFont, outline_color: str, fill_color: str):
        offsets = [(-5, 0), (5, 0), (0, -5), (0, 5), (-5, -5), (-5, 5), (5, -5), (5, 5)]
        for dx, dy in offsets:
            draw.text((position[0]+dx, position[1]+dy), text, fill=outline_color, font=font)
        draw.text(position, text, fill=fill_color, font=font)

    def _get_asset_path(self, filename: str) -> str:
        return os.path.join(self.THUMBNAIL_ASSETS_DIR, filename)
    
    def _load_font(self, font_filename: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self._get_asset_path(font_filename), size)

    def _design_thumbnail(self, thumbnail_data: bytes, win_count: int, lose_count: int, battle: str, rule: str, rate: Optional[str], stage1: Optional[str], stage2: Optional[str]) -> bytes:
        thumbnail = Image.open(io.BytesIO(thumbnail_data)).convert("RGBA")
        draw = ImageDraw.Draw(thumbnail)
        # 不要なステージ部分を塗りつぶし
        draw.rounded_rectangle((777, 21, 1849, 750), radius=40,
                               fill=(28, 28, 28), outline=(28, 28, 28), width=1)

        # 勝敗数を追加
        win_lose = f"{win_count} - {lose_count}"
        font = self._load_font("Paintball_Beta.otf", 120)
        bbox = draw.textbbox((0, 0), win_lose, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        centered_position = (458 - text_width // 2, 100 - text_height // 2)
        self._draw_text_with_outline(draw, centered_position, win_lose, font, outline_color="black", fill_color="yellow")

        # バトルのアイコンを追加
        battle_name = battle.split("(")[0]
        battle_path = self._get_asset_path(f"{battle_name}.png")
        if os.path.exists(battle_path):
            battle_image = Image.open(battle_path).convert("RGBA")
            battle_image = battle_image.resize((300, 300))
            thumbnail.paste(battle_image, (800, 40), battle_image)
        else:
            logger.warning(f"バトルアイコンが見つかりません: {battle_name}")

        # ルールの文字を追加
        font = self._load_font("ikamodoki1.ttf", 140)
        draw.text((1120, 50), rule, fill="white", font=font)

        # ルールのアイコンを追加
        rule_path = self._get_asset_path(f"{rule}.png")
        if os.path.exists(rule_path):
            rule_image = Image.open(rule_path).convert("RGBA")
            rule_image = rule_image.resize((150, 150))
            thumbnail.paste(rule_image, (1660, 70), rule_image)
        else:
            logger.warning(f"ルールアイコンが見つかりません: {rule}")

        # レートの文字を追加
        if rate:
            text_color = (1, 249, 196) if battle == "Xマッチ" else (250, 97, 0) if battle.startswith("バンカラマッチ") else "white"
            font = self._load_font("Paintball_Beta.otf", 70)
            draw.text((1125, 230), rate, fill=text_color, font=font)

        # ステージ画像を追加
        if stage1:
            stage1_path = self._get_asset_path(f"{stage1}.png")
            if os.path.exists(stage1_path):
                stage1_image = Image.open(stage1_path).convert("RGBA")
                stage1_image = stage1_image.resize((960, 168))
                thumbnail.paste(stage1_image, (860, 360), stage1_image)
            else:
                logger.warning(f"ステージ画像が見つかりません: {stage1}")
        else:
            logger.warning("ステージを検出できていません")

        if stage2:
            stage2_path = self._get_asset_path(f"{stage2}.png")
            if os.path.exists(stage2_path):
                stage2_image = Image.open(stage2_path).convert("RGBA")
                stage2_image = stage2_image.resize((960, 168))
                thumbnail.paste(stage2_image, (860, 540), stage2_image)
            else:
                logger.warning(f"ステージ画像が見つかりません: {stage2}")
        # 2つ目のステージがないことはあるので、警告は出さない

        buf = io.BytesIO()
        thumbnail.save(buf, format='PNG')
        return buf.getvalue()

    def _combine_subtitles(self, files: List[UploadFile]):
        logger.info("字幕を結合します")
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
        return combined_subtitles

    def _change_volume(self, path: str, volume_multiplier: float):
        if volume_multiplier == 1.0:
            return

        logger.info(f"動画の音量を{volume_multiplier}倍に変更します")
        FFmpeg.change_volume(path, volume_multiplier)
