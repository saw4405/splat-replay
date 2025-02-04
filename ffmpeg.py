import os
import subprocess
from typing import List
import logging
import json
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class FFmpeg:
    @dataclass
    class Metadata:
        title: str
        comment: str

    @staticmethod
    def concat(files: List[str], out_path: str):
        directory = os.path.dirname(files[0])
        extension = os.path.splitext(out_path)[1]

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
                f"temp{extension}"
            ]
            subprocess.run(command, check=True)
            os.rename(f"temp{extension}", out_path)

        finally:
            try:
                os.remove(concat_list_path)
            except Exception as e:
                logger.warning(f"一時ファイルの削除に失敗しました: {e}")

    @staticmethod
    def write_metadata(file: str, metadata: Metadata):
        extension = os.path.splitext(file)[1]
        out_file = f"temp{extension}"
        command = [
            "ffmpeg",
            "-i", file,
            "-metadata", f"title={metadata.title}",
            "-metadata", f"comment={metadata.comment}",
            "-c", "copy",
            out_file
        ]
        subprocess.run(command, check=True, encoding="utf-8")
        os.remove(file)
        os.rename(out_file, file)

    @staticmethod
    def read_metadata(file: str) -> Metadata:
        command = [
            "ffprobe",
            "-v", "error",
            "-show_format",
            "-print_format", "json",
            file
        ]
        result = subprocess.run(command, check=True,
                                capture_output=True, text=True, encoding="utf-8")
        data = json.loads(result.stdout)
        tags = data["format"].get("tags", {})
        tags = {k.lower(): v for k, v in tags.items()}
        return FFmpeg.Metadata(
            title=tags.get("title", ""),
            comment=tags.get("comment", "")
        )
