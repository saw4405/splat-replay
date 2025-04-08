import os
import logging
import glob
from typing import Optional, Callable

import numpy as np

from wrapper.youtube import Youtube, PrivacyStatus
from wrapper.ffmpeg import FFmpeg
from battle_result import BattleResult
from upload_file import UploadFile
import utility.os as os_utility
from utility.result import Result
import logger_config
from editor import Editor

logger = logging.getLogger(__name__)


class Uploader:
    RECORDED_DIR = os.path.join(os.getcwd(), "output", "recorded")
    EDITED_DIR = os.path.join(os.getcwd(), "output", "edited")

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
        self._private_status: PrivacyStatus = "private" if os.environ.get(
            "YOUTUBE_VIDEO_PUBLIC", "false").lower() == "false" else "public"
        self._video_tags = os.environ.get("YOUTUBE_VIDEO_TAGS", "").split(",")
        self._playlist_id = os.environ.get("YOUTUBE_PLAYLIST_ID")

        os.makedirs(self.RECORDED_DIR, exist_ok=True)
        os.makedirs(self.EDITED_DIR, exist_ok=True)

        self._youtube = Youtube()

    def start(self):
        logger.info("アップロード処理を開始します")
        self._edit()
        logger.info("編集処理が完了したので、アップロードを開始します")
        self._upload()
        logger.info("アップロード処理が完了しました")

    def _edit(self):
        files = glob.glob(f'{self.RECORDED_DIR}/*.*')
        recorded_files = [UploadFile(path) for path in files]
        editor = Editor(self.EDITED_DIR)
        editor.start(recorded_files)

    def _upload(self):
        edited_files = glob.glob(f'{self.EDITED_DIR}/*.*')
        for file in edited_files:
            if (video_id := self._upload_video(file)) is None:
                continue
            self._set_thumbnail(file, video_id)
            self._insert_caption(file, video_id)
            self._insert_to_playlist(video_id)

            if os_utility.remove_file(file).is_err():
                logger.warning(
                    "アップロード後のファイル削除に失敗したため、同じファイルが再度アップロードされる可能性があります")

    def _upload_video(self, path: str) -> Optional[str]:
        metadata_result = FFmpeg.read_metadata(path)
        if metadata_result.is_err():
            logger.error("アップロードする動画のメタデータ取得に失敗しました")
            return None

        metadata = metadata_result.unwrap()
        logger.info(f"YouTubeにアップロードします: {metadata.title}")
        metadata_result = self._youtube.upload(
            path, metadata.title, metadata.comment, self._video_tags, privacy_status=self._private_status)
        if metadata_result.is_err():
            logger.info(
                f"YouTubeへのアップロードに失敗しました: {metadata_result.unwrap_err()}")
            return None

        video_id = metadata_result.unwrap()
        logger.info(f"YouTubeにアップロードしました: {video_id}")
        return video_id

    def _handle_temp_file(self, temp_path: str, data, mode: str, process_func: Callable[[str], Result], context: str, encoding: Optional[str] = None):
        try:
            with open(temp_path, mode, encoding=encoding) as f:
                f.write(data)
            result = process_func(temp_path)
            if result is None or result.is_err():
                error = result.unwrap_err() if result and result.is_err() else ""
                logger.warning(f"{context}に失敗しました: {error}")
            return result

        except Exception as e:
            logger.warning(f"一時ファイル処理中にエラーが発生しました: {e}")
            return None

        finally:
            if os_utility.remove_file(temp_path).is_err():
                logger.warning(f"一時ファイルの削除に失敗しました: {temp_path}")

    def _set_thumbnail(self, path: str, video_id: str):
        thumbnail_result = FFmpeg.get_thumbnail(path)
        if thumbnail_result.is_err():
            logger.warning(f"サムネイルの取得に失敗しました: {thumbnail_result.unwrap_err()}")
            return

        logger.info("サムネイルをアップロードします")
        self._handle_temp_file(
            temp_path=os.path.join(self.EDITED_DIR, f"{video_id}.png"),
            data=thumbnail_result.unwrap(),
            mode="wb",
            process_func=lambda path: self._youtube.set_thumbnail(
                video_id, path),
            context="サムネイルのアップロード"
        )

    def _insert_caption(self, path: str, video_id: str):
        subtitle_result = FFmpeg.get_subtitle(path)
        if subtitle_result.is_err():
            logger.warning(f"字幕の取得に失敗しました: {subtitle_result.unwrap_err()}")
            return

        logger.info("字幕をアップロードします")
        self._handle_temp_file(
            temp_path=os.path.join(self.EDITED_DIR, f"{video_id}.srt"),
            data=subtitle_result.unwrap(),
            mode="w",
            process_func=lambda path: self._youtube.insert_caption(
                video_id, path, "ひとりごと"),
            encoding="utf-8",
            context="字幕のアップロード"
        )

    def _insert_to_playlist(self, video_id: str):
        if not self._playlist_id:
            logger.warning("プレイリストIDが指定されていません")
            return

        logger.info("プレイリストに挿入します")
        result = self._youtube.insert_to_playlist(video_id, self._playlist_id)
        if result is None or result.is_err():
            error = result.unwrap_err() if result and result.is_err() else ""
            logger.warning(f"プレイリストへの挿入に失敗しました: {error}")


# 直接Uploaderスクリプトを実行したとき、アップロードを実行する
if __name__ == '__main__':
    logger_config.setup_logger()
    uploader = Uploader()
    uploader.start()
