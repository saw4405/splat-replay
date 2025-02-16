import os
import logging
import time
import datetime
import subprocess
from typing import Optional, Tuple
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

    def __init__(self, path: str, host: str, port: int, password: str):
        self.directory = os.path.dirname(path)
        self.file = os.path.basename(path)
        self.host = host
        self.port = port
        self.password = password

        self._process = self._start_obs_process()
        self._ws = obsws(self.host, self.port, self.password)
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

        os.chdir(self.directory)
        process = subprocess.Popen(self.file)

        # 起動直後はWebSocket接続に失敗するので起動待ちする
        while not self._is_running():
            time.sleep(1)

        return process

    def _connect_obs(self):
        """ OBSに接続する """
        if not self._ws.ws or not self._ws.ws.connected:
            self._ws.connect()

    def close(self):
        """ OBSを終了する """
        self.stop_virtual_cam()
        self._ws.disconnect()
        if self._process:
            self._process.terminate()

    def _request_obs(self, request: Baserequests) -> Baserequests:
        """ OBSにリクエストを送信する

        Args:
            request (Baserequests): リクエスト

        Returns:
            Baserequests: レスポンス
        """
        # 途中でOBSが終了している場合に備えて、起動と接続を確認する
        self._process = self._start_obs_process() or self._process
        self._connect_obs()

        result = self._ws.call(request)
        return result

    def start_virtual_cam(self) -> Result[None, str]:
        """ 仮想カメラを起動する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._request_obs(requests.GetVirtualCamStatus())

        status = result.datain.get("outputActive", False)
        if status:
            return Ok(None)

        result = self._request_obs(requests.StartVirtualCam())
        if not result.status:
            return Err("仮想カメラの起動に失敗しました")

        return Ok(None)

    def stop_virtual_cam(self) -> Result[None, str]:
        """ 仮想カメラを停止する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        result = self._request_obs(requests.GetVirtualCamStatus())
        status = result.datain.get("outputActive", False)
        if status == False:
            return Ok(None)

        result = self._request_obs(requests.StopVirtualCam())
        if not result.status:
            return Err("仮想カメラの停止に失敗しました")

        return Ok(None)

    def _get_record_status(self) -> Tuple[bool, bool]:
        """ 録画の状態を取得する

        Returns:
            Tuple[bool, bool]: 録画中かどうかと一時停止中かどうか
        """
        result = self._request_obs(requests.GetRecordStatus())
        active = result.datain.get("outputActive", False)
        paused = result.datain.get("outputPaused", False)
        return active, paused

    def start_record(self) -> Result[None, str]:
        """ 録画を開始する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        active, _ = self._get_record_status()
        if active:
            return Ok(None)

        result = self._request_obs(requests.StartRecord())
        if not result.status:
            return Err("録画の開始に失敗しました")

        return Ok(None)

    def stop_record(self) -> Result[str, str]:
        """ 録画を停止する

        Returns:
            Result[str, str]: 成功した場合はOkに録画ファイルのパスが格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        active, _ = self._get_record_status()
        if not active:
            return Err("録画は開始されていません")

        result = self._request_obs(requests.StopRecord())
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
        _, paused = self._get_record_status()
        if paused:
            return Ok(None)

        result = self._request_obs(requests.PauseRecord())
        if not result.status:
            return Err("録画の一時停止に失敗しました")

        return Ok(None)

    def resume_record(self) -> Result[None, str]:
        """ 録画を再開する

        Returns:
            Result[None, str]: 成功した場合はOk、失敗した場合はErrにエラーメッセージが格納される
        """
        _, paused = self._get_record_status()
        if not paused:
            return Ok(None)

        result = self._request_obs(requests.ResumeRecord())
        if not result.status:
            return Err("録画の再開に失敗しました")

        return Ok(None)
