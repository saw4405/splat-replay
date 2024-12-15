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
        self._template = cv2.imread(template_path)
        if self._template is None:
            raise ValueError(f"Failed to load template image: {template_path}")
        
        self._mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE) if mask_path else None
        if mask_path and self._mask is None:
            raise ValueError(f"Failed to load mask image: {mask_path}")

        self._threshold = threshold
        
        self.height, self.width = self._template.shape[:2]

    def match(self, frame: np.ndarray) -> Tuple[bool, Optional[Tuple[int, int]]]:
        """
        フレーム内でテンプレートを探し、一致したかどうかを返す。

        :param frame: 検索対象のフレーム。
        :return: (一致フラグ, 一致した位置) のタプル。位置は (x, y) の座標。
        """
        if not isinstance(frame, np.ndarray):
            raise TypeError("Frame must be a numpy ndarray.")

        # テンプレートマッチングを実行
        if self._mask is not None:
            result: np.ndarray = cv2.matchTemplate(
                frame, self._template, cv2.TM_CCOEFF_NORMED, mask=self._mask
            )
        else:
            result: np.ndarray = cv2.matchTemplate(
                frame, self._template, cv2.TM_CCOEFF_NORMED
            )

        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # 一致が閾値以上かどうかを判定
        return max_val >= self._threshold, max_loc if max_val >= self._threshold else None
    