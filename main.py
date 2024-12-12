import os
import threading

import dotenv

from recorder import Recorder
from uploader import Uploader

if __name__ == '__main__':

    dotenv.load_dotenv()

    upload = bool(os.environ["UPLOAD_YOUTUBE"])
    if upload:
        uploader = Uploader()
        thread = threading.Thread(target=uploader.run, daemon=True)
        thread.start()
    
    recorder = Recorder()
    recorder.run()