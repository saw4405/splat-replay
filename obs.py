import os
import logging
import time
import datetime
import subprocess
from typing import Optional, Tuple
import win32gui

import psutil
from obswebsocket import obsws, requests
from obswebsocket.exceptions import ConnectionFailure
from obswebsocket.base_classes import Baserequests
from websocket import WebSocketConnectionClosedException

logger = logging.getLogger(__name__)

# https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md


class Obs:
    @staticmethod
    def extract_start_datetime(path: str) -> Optional[datetime.datetime]:
        try:
            file_base_name, _ = os.path.splitext(os.path.basename(path))
            start_datetime = datetime.datetime.strptime(
                file_base_name, "%Y-%m-%d %H-%M-%S")
            return start_datetime
        except:
            return None

    def __init__(self):
        self.DIRECTORY = os.environ["OBS_DIRECTORY"]
        self.FILE = os.environ["OBS_FILE"]
        self.HOST = os.environ["OBS_WS_HOST"]
        self.PORT = os.environ["OBS_WS_PORT"]
        self.PASSWORD = os.environ["OBS_WS_PASSWORD"]

        self._process: Optional[subprocess.Popen] = None
        self._ws: Optional[obsws] = None

        self._start_and_connect_obs()

    def _start_and_connect_obs(self):
        self._start_obs_process()
        self._connect_obs()

    def _start_obs_process(self):
        if self._is_running():
            logger.info("OBSは既に起動しています")
            return None

        os.chdir(self.DIRECTORY)
        self._process = subprocess.Popen(self.FILE)
        logger.info("OBSを起動しました")

        # 起動直後はWebSocket接続に失敗するので起動待ちする
        while not self._is_running():
            time.sleep(1)

    def _connect_obs(self):
        if self._ws is None:
            self._ws = obsws(self.HOST, self.PORT, self.PASSWORD)

        if not self._ws.ws or not self._ws.ws.connected:
            self._ws.connect()
            logger.info("OBS WebSocketに接続しました")

    def _is_running(self) -> bool:
        def exists_process() -> bool:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == self.FILE:
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

    def close(self):
        self.stop_virtual_cam()
        self._ws.disconnect()
        if self._process:
            self._process.terminate()
            logger.info("OBSを終了しました")

    def _request_obs(self, request: Baserequests) -> Baserequests:
        # 途中でOBSが終了している場合に備えて、起動と接続を確認する
        self._start_and_connect_obs()

        result = self._ws.call(request)
        return result

    def start_virtual_cam(self) -> bool:
        result = self._request_obs(requests.GetVirtualCamStatus())

        status = result.datain.get("outputActive", False)
        if status:
            logger.info("仮想カメラは既に起動しています")
            return True

        result = self._request_obs(requests.StartVirtualCam())
        if not result.status:
            logger.info("仮想カメラの起動に失敗しました")
            return False

        logger.info("仮想カメラを開始しました")
        return True

    def stop_virtual_cam(self) -> bool:
        result = self._request_obs(requests.GetVirtualCamStatus())
        status = result.datain.get("outputActive", False)
        if status == False:
            logger.info("仮想カメラは既に停止しています")
            return True

        result = self._request_obs(requests.StopVirtualCam())
        if not result.status:
            logger.info("仮想カメラの停止に失敗しました")
            return False

        logger.info("仮想カメラを停止しました")
        return True

    def get_record_status(self) -> Tuple[bool, bool]:
        result = self._request_obs(requests.GetRecordStatus())
        active = result.datain.get("outputActive", False)
        paused = result.datain.get("outputPaused", False)
        return active, paused

    def start_record(self) -> bool:
        active, _ = self.get_record_status()
        if active:
            logger.info("録画は既に開始しています")
            return True

        result = self._request_obs(requests.StartRecord())
        if not result.status:
            logger.info("録画の開始に失敗しました")
            return False

        logger.info("録画を開始しました")
        return True

    def stop_record(self) -> Tuple[bool, Optional[str]]:
        active, _ = self.get_record_status()
        if not active:
            logger.info("録画は既に停止しています")
            return True, None

        result = self._request_obs(requests.StopRecord())
        if not result.status:
            logger.info("録画の停止に失敗しました")
            return False, None

        output = result.datain.get("outputPath", None)
        if not output:
            logger.info("録画ファイルが見つかりません")
            return False, None

        logger.info("録画を停止しました")
        return True, output

    def pause_record(self) -> bool:
        _, paused = self.get_record_status()
        if paused:
            logger.info("録画は既に一時停止しています")
            return True

        result = self._request_obs(requests.PauseRecord())
        if not result.status:
            logger.info("録画の一時停止に失敗しました")
            return False

        logger.info("録画を一時停止しました")
        return True

    def resume_record(self) -> bool:
        _, paused = self.get_record_status()
        if not paused:
            logger.info("録画は一時停止していません")
            return True

        result = self._request_obs(requests.ResumeRecord())
        if not result.status:
            logger.info("録画の再開に失敗しました")
            return False

        logger.info("録画を再開しました")
        return True
