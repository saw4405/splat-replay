import os
import logging
import time
import subprocess
from typing import Optional, Tuple

import psutil
from obswebsocket import obsws, requests

logger = logging.getLogger(__name__)

# https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md

class Obs:
    def __init__(self):
        self.DIRECTORY = os.environ["OBS_DIRECTORY"]
        self.FILE = os.environ["OBS_FILE"]
        self.HOST = os.environ["OBS_WS_HOST"]
        self.PORT = os.environ["OBS_WS_PORT"]
        self.PASSWORD = os.environ["OBS_WS_PASSWORD"]

        self._process = self._start_process()
        
        self._ws = obsws(self.HOST, self.PORT, self.PASSWORD)
        self._ws.connect()
        logger.info("OBS WebSocketに接続しました")

    def _start_process(self) -> Optional[subprocess.Popen]:
        if self._is_running():
            logger.info("OBSは既に起動しています")
            return None
        
        os.chdir(self.DIRECTORY)
        process = subprocess.Popen(self.FILE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info("OBSを起動しました")

        # 起動直後はWebSocket接続に失敗するので起動待ちする
        while not self._is_running():
            time.sleep(1)
        time.sleep(5)
        return process

    def _is_running(self) -> bool:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == self.FILE:
                return True
        return False

    def __del__(self):
        self._ws.disconnect()
        if self._process:
            self._process.terminate()
            logger.info("OBSを終了しました")

    def start_virtual_cam(self) -> bool:

        result = self._ws.call(requests.GetVirtualCamStatus())
        status = result.datain.get("outputActive", False)
        if status:
            logger.info("仮想カメラは既に起動しています")
            return True
        
        result = self._ws.call(requests.StartVirtualCam())
        if not result.status:
            logger.info("仮想カメラの起動に失敗しました")
            return False
        
        logger.info("仮想カメラを開始しました")
        return True

    def start_record(self) -> bool:

        result = self._ws.call(requests.GetRecordStatus())
        status = result.datain.get("outputActive", False)
        if status:
            logger.info("録画は既に開始しています")
            return True
        
        result = self._ws.call(requests.StartRecord())
        if not result.status:
            logger.info("録画の開始に失敗しました")
            return False
        
        logger.info("録画を開始しました")
        return True

    def stop_record(self) -> Tuple[bool, Optional[str]]:

        result = self._ws.call(requests.StopRecord())
        if not result.status:
            logger.info("録画の停止に失敗しました")
            return False, None
        
        output = result.datain.get("outputPath", None)
        if not output:
            logger.info("録画ファイルが見つかりません")
            return False, None
        
        logger.info("録画を停止しました")
        return True, output
