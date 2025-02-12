import cv2
import numpy as np

from utility.result import Result, Ok, Err


class Capture:

    @classmethod
    def create(cls, index: int, width: int, height: int) -> Result["Capture", str]:
        """カメラのキャプチャを作成する

        Args:
            index (int): カメラのインデックス
            width (int): キャプチャする画像の幅
            height (int): キャプチャする画像の高さ

        Returns:
            Result[Capture, str]: 成功した場合にはOkにCaptureが格納され、失敗した場合にはErrにエラーメッセージが格納される
        """
        try:
            return Ok(Capture(index, width, height))
        except Exception as e:
            return Err(str(e))

    def __init__(self, index: int, width: int, height: int):
        self._capture = cv2.VideoCapture(index)
        if not self._capture.isOpened():
            raise Exception("カメラが見つかりません")

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> Result[np.ndarray, str]:
        """フレームを読み込む

        Returns:
            Result[np.ndarray, str]: 成功した場合はOkにフレームが格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        ret, frame = self._capture.read()
        return Ok(frame) if ret else Err("フレームの読み込みに失敗しました")

    def release(self):
        """キャプチャを解放する"""
        self._capture.release()
        cv2.destroyAllWindows()
