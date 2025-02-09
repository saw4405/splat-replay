import os
import subprocess
from typing import List, Optional, Literal
import logging
import json
from dataclasses import dataclass

import utility.os as os_utility
from utility.result import Result, Ok, Err

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
        result = FFmpeg._find_streams(video_path, "video", "png")
        if result.is_err():
            return False
        if len(result.unwrap()) == 0:
            logger.error("サムネイルが見つかりませんでした")
            return False
        index = result.unwrap()[0]

        directory = os.path.dirname(video_path)
        os.chdir(directory)
        command = [
            "ffmpeg",
            "-i", video_path,
            "-map", f"0:v:{index}",
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
    def set_subtitle(video_path: str, srt: str) -> Result[None, str]:
        """ 動画に字幕を埋め込む

        Args:
            video_path (str): 動画ファイルのパス
            srt (str): SRT形式の字幕

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        extension = os.path.splitext(video_path)[1]
        out_file = f"temp{extension}"
        os_utility.remove_file(out_file)

        directory = os.path.dirname(video_path)
        os.chdir(directory)
        command = [
            "ffmpeg",
            "-i", video_path,
            "-f", "srt",
            "-i", "-",
            "-c", "copy",
            "-c:s", "srt",
            "-metadata:s:s:0", "title=Subtitles",
            out_file
        ]
        result = subprocess.run(
            command, input=srt, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            return Err("字幕の設定に失敗しました")

        os_utility.remove_file(video_path)
        if os_utility.rename_file(out_file, video_path).is_err():
            return Err("字幕付き動画ファイルの更新に失敗しました")

        return Ok()

    @staticmethod
    def get_subtitle(video_path: str) -> Result[str, str]:
        """ 動画から字幕を取得する

        Args:
            video_path (str): 動画ファイルのパス

        Returns:
            Result[str, str]: 成功した場合はOkにSRT形式の字幕が格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        result = FFmpeg._find_streams(video_path, "subtitle", "subrip")
        if result.is_err():
            return Err(result.unwrap_err())
        if len(result.unwrap()) == 0:
            return Err("字幕が見つかりませんでした")
        index = result.unwrap()[0]

        command = [
            "ffmpeg",
            "-i", video_path,
            "-map", f"0:s:{index}",
            "-c", "copy",
            "-f", "srt",
            "-"
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            return Err("字幕の取得に失敗しました")

        return Ok(result.stdout)

    @staticmethod
    def _find_streams(video_path: str, codec_type: Literal["video", "audio", "subtitle"], codec_name: str) -> Result[List[int], str]:
        """ 動画ファイルから指定されたコーデックのストリームを探す

        Args:
            video_path (str): 動画ファイルのパス
            codec_type (Literal["video", "audio"]): コーデックの種類
            codec_name (str): コーデック名

        Returns:
            Result[List[int], str]: 成功した場合はOkにストリームの相対インデックスが格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        command = [
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-of", "json",
            video_path
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            return Err("ストリーム情報の取得に失敗しました")

        try:
            info = json.loads(result.stdout)
        except Exception as e:
            return Err("JSON解析中にエラーが発生しました")

        target_streams = [stream for stream in info["streams"]
                          if stream.get("codec_type") == codec_type]
        relative_indices = [
            i for i, stream in enumerate(target_streams) if stream.get("codec_name") == codec_name
        ]

        return Ok(relative_indices)
