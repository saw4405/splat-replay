import os
import logging
from logging.handlers import TimedRotatingFileHandler

def setup_logger():
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
