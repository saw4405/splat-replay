import os
import logging
from logging.handlers import TimedRotatingFileHandler


def setup_logger():
    directory = os.path.join(os.getcwd(), 'logs')
    path = os.path.join(directory, 'splat-replay.log')
    os.makedirs(directory, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s',
        handlers=[
            TimedRotatingFileHandler(
                path,
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
