import os
import threading

import dotenv

from recorder import Recorder
from uploader import Uploader

def main():
    dotenv.load_dotenv()

    recorder = Recorder()

    upload_mode = os.environ["UPLOAD_MODE"]
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