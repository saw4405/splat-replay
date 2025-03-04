import os
import time
from typing import Optional
import logging
import threading

import dotenv
import schedule
import win32com.client

from recorder import Recorder
from uploader import Uploader
import logger_config


class Main:
    def __init__(self):
        dotenv.load_dotenv()
        logger_config.setup_logger()
        self._logger = logging.getLogger(__name__)
        self._load_config()
        self._recorder: Optional[Recorder] = None
        self._uploader = Uploader()

    def _load_config(self):
        self.SLEEP_AFTER_UPLOAD = bool(os.environ["SLEEP_AFTER_UPLOAD"])
        self.UPLOAD_MODE = os.environ["UPLOAD_MODE"]
        self.CAPTURE_DEVICE_NAME = os.environ["CAPTURE_DEVICE_NAME"]
        self.UPLOAD_TIME = os.environ["UPLOAD_TIME"]

    def _check_capture_device(self, device_name: str) -> bool:
        wmi = win32com.client.GetObject("winmgmts:")
        devices = wmi.InstancesOf("Win32_PnPEntity")
        return any(str(device.Name) == device_name for device in devices)

    def _wait_for_device(self):
        animation = ["(●´・ω・)    ", "(●´・ω・)σ   ",
                     "(●´・ω・)σσ  ", "(●´・ω・)σσσ ", "(●´・ω・)σσσσ"]

        print("\033[?25l")  # カーソル非表示
        try:
            idx = 0
            while not self._check_capture_device(self.CAPTURE_DEVICE_NAME):
                message = f"\rキャプチャボード({self.CAPTURE_DEVICE_NAME})の接続待ち {animation[idx % len(animation)]}"
                print(message, end="")
                idx += 1
                time.sleep(0.5)
        finally:
            print('\033[?25h')

    def _setup_periodic_upload(self):
        schedule.every().day.at(self.UPLOAD_TIME).do(self._handle_upload)
        self._logger.info(f"アップロードスケジュールを設定しました: {self.UPLOAD_TIME}")

        def upload_loop():
            while True:
                schedule.run_pending()
                time.sleep(60)

        threading.Thread(target=upload_loop, daemon=True).start()

    def _handle_upload(self):
        self._uploader.upload()

        if self.SLEEP_AFTER_UPLOAD:
            self._logger.info("スリープします")
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

            # スリーブするとOBSの接続が切れるので、いったん終了する (メインループで再接続する)
            if self._recorder:
                self._logger.info("Recorderを一旦終了します")
                self._recorder.stop()

    def run(self):
        # 定期アップロードの場合、別スレッドで指定時刻にアップロードするループを回す
        if self.UPLOAD_MODE == "PERIODIC":
            self._setup_periodic_upload()

        while True:
            self._wait_for_device()
            self._recorder = Recorder()

            if self.UPLOAD_MODE == "AUTO":
                self._recorder.register_power_off_callback(self._handle_upload)
                self._logger.info("アップロードコールバックを登録しました")

            self._recorder.start()
            self._recorder.join()


if __name__ == '__main__':
    main = Main()
    main.run()
