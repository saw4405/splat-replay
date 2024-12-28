import os

import cv2
import numpy as np


class Capture:
    def __init__(self):
        INDEX = int(os.environ["CAPTURE_DEVICE_INDEX"])
        WIDTH = int(os.environ["CAPTURE_WIDTH"])
        HEIGHT = int(os.environ["CAPTURE_HEIGHT"])

        self._capture = cv2.VideoCapture(INDEX)
        if not self._capture.isOpened():
            raise Exception("カメラが見つかりません")

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

    def read(self) -> np.ndarray:
        ret, frame = self._capture.read()
        if ret:
            return frame
        raise Exception("フレームの読み込みに失敗しました")

    def release(self):
        self._capture.release()
        cv2.destroyAllWindows()
