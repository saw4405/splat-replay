import os
from typing import Optional
import logging
from logging.handlers import TimedRotatingFileHandler

import dotenv

from recorder import Recorder
from uploader import Uploader


class Main:
    def __init__(self):
        dotenv.load_dotenv()
        self._setup_logger()
        self._logger = logging.getLogger(__name__)

        SLEEP_AFTER_UPLOAD = bool(os.environ["SLEEP_AFTER_UPLOAD"])
        self._logger.info(f"SLEEP_AFTER_UPLOAD: {SLEEP_AFTER_UPLOAD}")
        self._upload_complete_callback = self.sleep_windows if SLEEP_AFTER_UPLOAD else None

        self._UPLOAD_MODE = os.environ["UPLOAD_MODE"]
        self._logger.info(f"UPLOAD_MODE: {self._UPLOAD_MODE}")

    def _setup_logger(self):
        LOG_DIRECTORY = 'logs'
        LOG_FILE_NAME = 'splat-replay.log'

        os.makedirs(LOG_DIRECTORY, exist_ok=True)

        # ロガーの設定
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

    def sleep_windows(self):
        self._logger.info("スリーブします")
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        self._logger.info("スリープから復帰しました")

    def run(self):
        recorder = Recorder()
        uploader: Optional[Uploader] = None

        if self._UPLOAD_MODE == "AUTO":
            uploader = Uploader(self._upload_complete_callback)
            recorder.register_power_off_callback(uploader.upload)

        elif self._UPLOAD_MODE == "PERIODIC":
            uploader = Uploader(self._upload_complete_callback)
            UPLOAD_TIME = os.environ["UPLOAD_TIME"]
            uploader.monitor_upload_schedule(UPLOAD_TIME)

        recorder.run()


if __name__ == '__main__':
    main = Main()
    main.run()
