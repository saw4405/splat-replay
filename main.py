import os
import threading
import logging
from logging.handlers import TimedRotatingFileHandler

import dotenv

from recorder import Recorder
from uploader import Uploader

def setup_logger():
    # ログディレクトリの作成
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    # ロガーの設定
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s',
        handlers=[
            TimedRotatingFileHandler(
                os.path.join(log_dir, 'splat-replay.log'),
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )

def main():
    dotenv.load_dotenv()
    setup_logger()
    logger = logging.getLogger(__name__)

    recorder = Recorder()

    upload_mode = os.environ["UPLOAD_MODE"]
    logger.info(f"UPLOAD_MODE: {upload_mode}")
    match upload_mode:
        case "AUTO":
            uploader = Uploader()
            recorder.register_power_off_callback(uploader.start_upload)

        case "PERIODIC":
            uploader = Uploader()
            upload_time = os.environ["UPLOAD_TIME"]
            uploader.set_upload_schedule(upload_time)
            thread = threading.Thread(target=uploader.run, daemon=True)
            thread.start()

        case "NONE":
            pass

        case _:
            raise ValueError(f"Invalid UPLOAD_MODE: {upload_mode}")
    
    recorder.run()

if __name__ == '__main__':
    main()