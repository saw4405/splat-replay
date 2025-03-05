import os
import logging
import time
import datetime
import subprocess
from typing import Optional, Tuple, Callable
import win32gui

import psutil
from obswebsocket import obsws, requests
from obswebsocket.base_classes import Baserequests

from utility.result import Result, Ok, Err

# https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md


class Obs:
    @staticmethod
    def extract_start_datetime(path: str) -> Optional[datetime.datetime]:
        """ ファイル名から録画開始日時を抽出する

        Args:
            path (str): ファイルのパス

        Returns:
            Optional[datetime.datetime]: 録画開始日時が抽出できた場合はdatetime.datetimeに変換した値、抽出できなかった場合はNone
        """
        try:
            file_base_name, _ = os.path.splitext(os.path.basename(path))
            start_datetime = datetime.datetime.strptime(
                file_base_name, "%Y-%m-%d %H-%M-%S")
            return start_datetime
        except:
            return None

    def __init__(self, path: str, host: str, port: int, password: str, on_disconnect: Optional[Callable[[obsws], None]] = None):
        """ OBSの操作を行うクラス """
        self.directory = os.path.dirname(path)
        self.file = os.path.basename(path)
        self.host = host
        self.port = port
        self.password = password

        self._process = self._start_obs_process()
        self._ws = obsws(self.host, self.port, self.password,
                         on_disconnect=on_disconnect)
        self._connect_obs()

    def _is_running(self) -> bool:
        """ OBSが起動しているか確認する

        Returns:
            bool: OBSが起動している場合はTrue、それ以外はFalse
        """
        def exists_process() -> bool:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == self.file:
                    return True
            return False

        def exists_window() -> bool:
            def enum_window(hwnd, result):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if "OBS" in title:
                        result.append(hwnd)
            windows = []
            win32gui.EnumWindows(enum_window, windows)
            return bool(windows)

        return exists_process() and exists_window()

    def _start_obs_process(self) -> Optional[subprocess.Popen]:
        """ OBSを起動する

        Returns:
            Optional[subprocess.Popen]: OBSのプロセス
        """
        if self._is_running():
            return None

        process = subprocess.Popen(self.file, cwd=self.directory, shell=True)

        # 起動直後はWebSocket接続に失敗するので起動待ちする
        while not self._is_running():
            time.sleep(1)

        return process

    @property
    def is_connected(self) -> bool:
        """ OBSに接続されているか確認する """
        return self._ws.ws is not None and self._ws.ws.connected

    def _connect_obs(self):
        """ OBSに接続する """
        if not self.is_connected:
            self._ws.connect()

    def close(self):
        """ OBSを終了する """
        if self.is_connected:
            self.stop_virtual_cam()
            self._ws.disconnect()
        if self._process:
            self._process.terminate()

    def _request_obs(self, request: Baserequests) -> Result[Baserequests, str]:
        """ OBSにリクエストを送信する

        Args:
            request (Baserequests): リクエスト

        Returns:
            Result[Baserequests, str]: レスポンス
        """
        if not self.is_connected:
            return Err("OBSに接続されていません")

        result = self._ws.call(request)

        return Ok(result)

    def start_virtual_cam(self) -> Result[None, str]:
        """ 仮想カメラを起動する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._request_obs(requests.GetVirtualCamStatus())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()

        # 既に起動している場合は何もしない
        status = result.datain.get("outputActive", False)
        if status:
            return Ok(None)

        result = self._request_obs(requests.StartVirtualCam())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()
        if not result.status:
            return Err("仮想カメラの起動に失敗しました")

        return Ok(None)

    def stop_virtual_cam(self) -> Result[None, str]:
        """ 仮想カメラを停止する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._request_obs(requests.GetVirtualCamStatus())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()

        # 既に停止している場合は何もしない
        status = result.datain.get("outputActive", False)
        if status == False:
            return Ok(None)

        result = self._request_obs(requests.StopVirtualCam())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()
        if not result.status:
            return Err("仮想カメラの停止に失敗しました")

        return Ok(None)

    def _get_record_status(self) -> Result[Tuple[bool, bool], str]:
        """ 録画の状態を取得する

        Returns:
            Result[Tuple[bool, bool], str]: 録画中かどうかと一時停止中かどうか
        """
        result = self._request_obs(requests.GetRecordStatus())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()

        active = result.datain.get("outputActive", False)
        paused = result.datain.get("outputPaused", False)
        return Ok((active, paused))

    def start_record(self) -> Result[None, str]:
        """ 録画を開始する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._get_record_status()
        if result.is_err():
            return Err(result.unwrap_err())

        active, _ = result.unwrap()
        if active:
            return Ok(None)

        result = self._request_obs(requests.StartRecord())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()
        if not result.status:
            return Err("録画の開始に失敗しました")

        return Ok(None)

    def stop_record(self) -> Result[str, str]:
        """ 録画を停止する

        Returns:
            Result[str, str]: 成功した場合はOkに録画ファイルのパスが格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._get_record_status()
        if result.is_err():
            return Err(result.unwrap_err())

        active, _ = result.unwrap()
        if not active:
            return Err("録画は開始されていません")

        result = self._request_obs(requests.StopRecord())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()
        if not result.status:
            return Err("録画の停止に失敗しました")

        output = result.datain.get("outputPath", None)
        if not output:
            return Err("録画ファイルが見つかりません")

        return Ok(output)

    def pause_record(self) -> Result[None, str]:
        """ 録画を一時停止する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._get_record_status()
        if result.is_err():
            return Err(result.unwrap_err())

        _, paused = result.unwrap()
        if paused:
            return Ok(None)

        result = self._request_obs(requests.PauseRecord())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()
        if not result.status:
            return Err("録画の一時停止に失敗しました")

        return Ok(None)

    def resume_record(self) -> Result[None, str]:
        """ 録画を再開する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._get_record_status()
        if result.is_err():
            return Err(result.unwrap_err())

        _, paused = result.unwrap()
        if not paused:
            return Ok(None)

        result = self._request_obs(requests.ResumeRecord())
        if result.is_err():
            return Err(result.unwrap_err())
        result = result.unwrap()
        if not result.status:
            return Err("録画の再開に失敗しました")

        return Ok(None)
