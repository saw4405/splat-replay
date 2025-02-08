import os
import subprocess
from typing import List, Optional
import logging
import json
from dataclasses import dataclass

import utility.os as os_utility

logger = logging.getLogger(__name__)


class FFmpeg:
    @dataclass
    class Metadata:
        title: str
        comment: str

    @staticmethod
    def concat(files: List[str], out_path: str) -> bool:
        directory = os.path.dirname(files[0])
        extension = os.path.splitext(out_path)[1]
        temp_path = f"temp{extension}"

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
                temp_path
            ]
            result = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8")
            if result.returncode != 0:
                logger.error(f"動画の結合に失敗しました: {result.stderr}")
                return False

            os_utility.rename_file(temp_path, out_path)
            return True

        finally:
            try:
                os_utility.remove_file(concat_list_path)
            except Exception as e:
                logger.warning(f"一時ファイルの削除に失敗しました: {e}")

    @staticmethod
    def write_metadata(file: str, metadata: Metadata) -> bool:
        extension = os.path.splitext(file)[1]
        out_file = f"temp{extension}"
        directory = os.path.dirname(file)
        os.chdir(directory)
        command = [
            "ffmpeg",
            "-i", file,
            "-metadata", f"title={metadata.title}",
            "-metadata", f"comment={metadata.comment}",
            "-c", "copy",
            out_file
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            logger.error(f"メタデータの書き込みに失敗しました: {result.stderr}")
            return False
        os_utility.remove_file(file)
        os_utility.rename_file(out_file, file)
        return True

    @staticmethod
    def read_metadata(file: str) -> Optional[Metadata]:
        command = [
            "ffprobe",
            "-v", "error",
            "-show_format",
            "-print_format", "json",
            file
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            logger.error(f"メタデータの取得に失敗しました: {result.stderr}")
            return None

        data = json.loads(result.stdout)
        tags = data["format"].get("tags", {})
        tags = {k.lower(): v for k, v in tags.items()}
        return FFmpeg.Metadata(
            title=tags.get("title", ""),
            comment=tags.get("comment", "")
        )

    @staticmethod
    def set_thumbnail(video_path: str, thumbnail_path: str) -> bool:
        extension = os.path.splitext(video_path)[1]
        out_file = f"temp{extension}"
        directory = os.path.dirname(video_path)
        os.chdir(directory)
        command = [
            "ffmpeg",
            "-i", video_path,
            "-i", thumbnail_path,
            "-map", "0",
            "-map", "1",
            "-c", "copy",
            out_file
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            logger.error(f"サムネイルの設定に失敗しました: {result.stderr}")
            return False

        os_utility.remove_file(video_path)
        os_utility.rename_file(out_file, video_path)
        return True

    @staticmethod
    def get_thumbnail(video_path: str, thumbnail_output_path: str) -> bool:
        directory = os.path.dirname(video_path)
        os.chdir(directory)
        command = [
            "ffmpeg",
            "-i", video_path,
            "-map", "0:v:1",
            "-c", "copy",
            thumbnail_output_path
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            logger.error(f"サムネイルの取得に失敗しました: {result.stderr}")
            return False
        return True

    @staticmethod
    def has_thumbnail(video_path: str) -> bool:
        # 映像・音声・サムネイル画像の3つのストリームがあるかどうかで簡易的に判定
        return FFmpeg.get_stream_count(video_path) >= 3

    @staticmethod
    def get_stream_count(video_path: str) -> int:
        command = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream",
            "-of", "json",
            video_path
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            logger.error(f"ストリーム情報の取得に失敗しました: {result.stderr}")
            return 0

        try:
            info = json.loads(result.stdout)
            streams = info.get("streams", [])
            return len(streams)
        except Exception as e:
            logger.error(f"出力の解析中にエラーが発生しました: {e}")
            return 0
