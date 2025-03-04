from typing import Union, Tuple

import cv2
import numpy as np

from utility.result import Result, Ok, Err


class Capture:

    @classmethod
    def create(cls, index_or_path: Union[int, str], width: int, height: int) -> Result["Capture", str]:
        """カメラのキャプチャを作成する

        Args:
            index (int): カメラのインデックス
            width (int): キャプチャする画像の幅
            height (int): キャプチャする画像の高さ

        Returns:
            Result[Capture, str]: 成功した場合にはOkにCaptureが格納され、失敗した場合にはErrにエラーメッセージが格納される
        """
        try:
            return Ok(Capture(index_or_path, width, height))
        except Exception as e:
            return Err(str(e))

    def __init__(self, index_or_path: Union[int, str], width: int, height: int):
        self._capture = cv2.VideoCapture(index_or_path)
        if not self._capture.isOpened():
            raise Exception("カメラが見つかりません")

        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def read(self) -> Result[Tuple[np.ndarray, float], str]:
        """フレームを読み込む

        Returns:
            Result[Tuple[np.ndarray, float], str]: 成功した場合はOkにフレームと経過時間が格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        ret, frame = self._capture.read()
        if not ret:
            return Err("フレームの読み込みに失敗しました")

        frame_count = self._capture.get(cv2.CAP_PROP_POS_FRAMES)
        fps = self._capture.get(cv2.CAP_PROP_FPS)
        elapsed_time = frame_count / fps
        return Ok((frame, elapsed_time))

    def show(self, frame: np.ndarray, resize_ratio: float = 1.0):
        """フレームをリサイズして表示する

        Args:
            frame (np.ndarray): 表示するフレーム
            resize_ratio (float): リサイズの比率 (1.0の場合はリサイズなし)
        """
        if resize_ratio != 1.0:
            frame = cv2.resize(frame, (0, 0), fx=resize_ratio, fy=resize_ratio)
        cv2.imshow("Capture Frame", frame)
        cv2.waitKey(1)

    def release(self):
        """キャプチャを解放する"""
        self._capture.release()
        cv2.destroyAllWindows()

    def __del__(self):
        """デストラクタ: オブジェクトが削除される時に呼ばれる"""
        self.release()
