import os
import subprocess
from typing import List
import logging

logger = logging.getLogger(__name__)


class FFmpeg:
    @staticmethod
    def concat(files: List[str], out_path: str):
        directory = os.path.dirname(files[0])
        _, extension = os.path.splitext(out_path)

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
