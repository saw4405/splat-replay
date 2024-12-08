from typing import Optional, Tuple

import cv2
import numpy as np


class TemplateMatcher:
    def __init__(self, template_path: str, mask_path: Optional[str] = None, threshold: float = 0.99):
        """
        テンプレートマッチングを行うクラス。

        :param template_path: 照合に使用するテンプレート画像のパス。
        :param mask_path: マスク画像のパス（オプション）。
        :param threshold: 一致とみなすスコアの閾値（0.0〜1.0）。
        """
        # self.template: np.ndarray = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        self.template: np.ndarray = cv2.imread(template_path)
        if self.template is None:
            raise ValueError(f"Failed to load template image: {template_path}")
        
        self.mask: Optional[np.ndarray] = (
            cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE) if mask_path else None
        )
        if mask_path and self.mask is None:
            raise ValueError(f"Failed to load mask image: {mask_path}")

        self.threshold: float = threshold
        
        self.template_height, self.template_width = self.template.shape[:2]

    def match(self, frame: np.ndarray) -> Tuple[bool, Optional[Tuple[int, int]]]:
        """
        フレーム内でテンプレートを探し、一致したかどうかを返す。

        :param frame: 検索対象のフレーム。
        :return: (一致フラグ, 一致した位置) のタプル。位置は (x, y) の座標。
        """
        if not isinstance(frame, np.ndarray):
            raise TypeError("Frame must be a numpy ndarray.")

        # フレームをグレースケールに変換
        # gray_frame: np.ndarray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_frame = frame

        # テンプレートマッチングを実行
        if self.mask is not None:
            result: np.ndarray = cv2.matchTemplate(
                gray_frame, self.template, cv2.TM_CCOEFF_NORMED, mask=self.mask
            )
        else:
            result: np.ndarray = cv2.matchTemplate(
                gray_frame, self.template, cv2.TM_CCOEFF_NORMED
            )

        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # 一致が閾値以上かどうかを判定
        return max_val >= self.threshold, max_loc if max_val >= self.threshold else None
    