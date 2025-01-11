import os
import time
from typing import Optional
import logging
from logging.handlers import TimedRotatingFileHandler
import threading

import dotenv
import schedule
import win32com.client

from recorder import Recorder
from uploader import Uploader


class Main:
    def __init__(self):
        dotenv.load_dotenv()
        self._setup_logger()
        self._logger = logging.getLogger(__name__)
        self._load_config()
        self._recorder: Optional[Recorder] = None
        self._uploader = Uploader()

    def _setup_logger(self):
        LOG_DIRECTORY = 'logs'
        LOG_FILE_NAME = 'splat-replay.log'
        os.makedirs(LOG_DIRECTORY, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s',
            handlers=[
                TimedRotatingFileHandler(
                    os.path.join(LOG_DIRECTORY, LOG_FILE_NAME),
                    when='midnight',
                    interval=1,
                    backupCount=30,
                    encoding='utf-8'
                ),
                logging.StreamHandler()
            ]
        )

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
        while not self._check_capture_device(self.CAPTURE_DEVICE_NAME):
            self._logger.error("キャプチャデバイスが見つかりません")
            print("キャプチャボードを接続してください")
            time.sleep(1)

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
                self._recorder.stop()

    def run(self):
        if self.UPLOAD_MODE == "PERIODIC":
            self._setup_periodic_upload()

        while True:
            self._wait_for_device()
            self._recorder = Recorder()

            if self.UPLOAD_MODE == "AUTO":
                self._recorder.register_power_off_callback(self._handle_upload)
                self._logger.info("アップロードコールバックを登録しました")

            self._recorder.start()
            self._logger.info("recorder開始")
            self._recorder.join()
            self._logger.info("recorder終了")


if __name__ == '__main__':
    main = Main()
    main.run()
