import os
import time

from utility.result import Result, Ok, Err


def remove_file(path: str, timeout_intervals: int = 10) -> Result[None, str]:
    """ファイルを削除する（リトライあり）

    指定されたパスのファイルを削除します。削除に失敗した場合は、各リトライごとに100ミリ秒の待機時間を設けて再試行します。

    Args:
        path (str): ファイルのパス
        timeout_intervals (int): 100ミリ秒単位のリトライ回数

    Returns:
        bool: ファイルが正常に削除された場合 True、削除できなかった場合 False
    """
    if not os.path.exists(path):
        return Ok(None)

    for _ in range(timeout_intervals):
        try:
            os.remove(path)
            return Ok(None)
        except:
            time.sleep(0.1)

    return Err("削除できませんでした")


def rename_file(old_path: str, new_path: str, timeout_intervals: int = 10) -> Result[None, str]:
    """ファイルをリネームする（リトライあり）

    指定されたパスのファイルをリネームします。リネームに失敗した場合は、各リトライごとに100ミリ秒の待機時間を設けて再試行します。

    Args:
        old_path (str): ファイルの元のパス
        new_path (str): ファイルの新しいパス
        timeout_intervals (int): 100ミリ秒単位のリトライ回数

    Returns:
        bool: ファイルが正常にリネームされた場合 True、リネームできなかった場合 False
    """
    if not os.path.exists(old_path):
        return Err("元のファイルが存在しません")

    for _ in range(timeout_intervals):
        try:
            os.rename(old_path, new_path)
            return Ok(None)
        except:
            time.sleep(0.1)

    return Err("リネームできませんでした")
