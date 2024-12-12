import os
import time
import subprocess
from typing import Optional, Tuple

import psutil
from obswebsocket import obsws, requests

# https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md

class Obs:

    def __init__(self):
        self.__process = None

        self._start()
        self.__ws = self._connect()

    def _start(self):
        if self._is_running():
            print("OBSは既に起動しています")
            return
        
        directory = os.environ["OBS_DIRECTORY"]
        file = os.environ["OBS_FILE"]
        os.chdir(directory)
        self.__process = subprocess.Popen(file, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # 起動直後はWebSocket接続に失敗するので起動待ちする
        while not self._is_running():
            time.sleep(1)
        time.sleep(5)
        print("OBSを起動しました")

    def _is_running(self) -> bool:
        """OBSが既に起動しているか確認する"""
        file = os.environ["OBS_FILE"]

        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == file:
                return True
        return False
            
    def _connect(self) -> obsws:
        host = os.environ["OBS_WS_HOST"]
        port = os.environ["OBS_WS_PORT"]
        password = os.environ["OBS_WS_PASSWORD"]
        ws = obsws(host, port, password)
        ws.connect()
        print("OBS WebSocketに接続しました")
        return ws

    def __del__(self):
        self._disconnect()
        self._end()

    def _end(self):
        if not self.__process:
            return
        self.__process.terminate()
        print("OBSを終了しました")

    def _disconnect(self):
        self.__ws.disconnect()

    def start_virtual_cam(self) -> bool:

        result = self.__ws.call(requests.GetVirtualCamStatus())
        status = result.datain.get("outputActive", False)
        if status:
            return True
        
        result = self.__ws.call(requests.StartVirtualCam())

        if not result.status:
            print("仮想カメラの起動に失敗しました")
            return False
        
        print("仮想カメラを開始しました")
        return True

    def start_record(self) -> bool:

        result = self.__ws.call(requests.GetRecordStatus())
        status = result.datain.get("outputActive", False)
        if status:
            return True
        
        result = self.__ws.call(requests.StartRecord())
        
        if not result.status:
            print("録画の開始に失敗しました")
            return False
        
        print("録画を開始しました")
        return True

    def stop_record(self) -> Tuple[bool, Optional[str]]:
        result = self.__ws.call(requests.StopRecord())

        if not result.status:
            print("録画の停止に失敗しました")
            return False, None
        
        output = result.datain.get("outputPath", None)
        if not output:
            print("録画ファイルが見つかりません")
            return False, None
        
        print("録画を停止しました")
        return True, output
