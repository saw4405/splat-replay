import hashlib
from typing import Optional, Tuple
from abc import ABC, abstractmethod

import cv2
import numpy as np


class BaseMatcher(ABC):
    def __init__(self, mask_path: Optional[str] = None):
        self._mask = cv2.imread(
            mask_path, cv2.IMREAD_GRAYSCALE) if mask_path else None
        if mask_path and self._mask is None:
            raise ValueError(f"Failed to load mask image: {mask_path}")

    @abstractmethod
    def match(self, image: np.ndarray) -> bool:
        pass


class HashMatcher(BaseMatcher):
    """ ハッシュ値を使用して画像の一致を検出するクラス (約0.004秒) """

    def __init__(self, image_path: str):
        """
        ハッシュ値を使用して画像の一致を検出するクラス。

        :param image_path: 照合に使用する画像のパス。
        """
        self._hash_value = self._compute_hash(cv2.imread(image_path))

    def _compute_hash(self, image: np.ndarray) -> str:
        """
        画像のハッシュ値を計算する。

        :param image: ハッシュ値を計算する対象の画像。
        :return: 画像のハッシュ値。
        """
        return hashlib.sha1(image).hexdigest()

    def match(self, image: np.ndarray) -> bool:
        """
        画像のハッシュ値を比較して一致を検出する。

        :param image: 検索対象のイメージ。
        :return: 一致したかどうか。
        """
        image_hash = self._compute_hash(image)
        return image_hash == self._hash_value


class HSVMatcher(BaseMatcher):
    """ HSV色空間での色の一致を検出するクラス (約0.013秒) """

    def __init__(self, lower_bound: Tuple[int, int, int], upper_bound: Tuple[int, int, int], mask_path: Optional[str] = None, threshold: float = 0.9):
        """
        HSV色空間での色の一致を検出するクラス。

        :param lower_bound: 色相・彩度・明度の下限値。
        :param upper_bound: 色相・彩度・明度の上限値。
        :param mask_path: マスク画像のパス（オプション）。
        :param threshold: 一致とみなす割合の閾値（0.0〜1.0）。
        """
        super().__init__(mask_path)
        self._lower_bound = np.array(lower_bound, dtype=np.uint8)
        self._upper_bound = np.array(upper_bound, dtype=np.uint8)
        self._threshold = threshold

    def match(self, image: np.ndarray) -> bool:
        """
        イメージ内で色の一致を検出する。

        :param image: 検索対象のイメージ。
        :return: 一致したかどうか。
        """
        if self._mask is not None:
            masked_image = cv2.bitwise_and(image, image, mask=self._mask)
        else:
            masked_image = image
        hsv_image = cv2.cvtColor(masked_image, cv2.COLOR_BGR2HSV)
        color_mask = cv2.inRange(
            hsv_image, self._lower_bound, self._upper_bound)
        if self._mask is not None:
            combined_mask = cv2.bitwise_and(
                color_mask, color_mask, mask=self._mask)
            total_mask_pixels = cv2.countNonZero(self._mask)
            color_pixel_count = cv2.countNonZero(combined_mask)
        else:
            total_mask_pixels = image.shape[0] * image.shape[1]
            color_pixel_count = cv2.countNonZero(color_mask)
        color_ratio = color_pixel_count / total_mask_pixels if total_mask_pixels > 0 else 0
        return color_ratio >= self._threshold


class UniformColorMatcher(BaseMatcher):
    """ 画像全体が同系色かどうかを判定するクラス (約0.013秒) """

    def __init__(self, mask_path: Optional[str] = None, hue_threshold: float = 10.0):
        """
        画像全体が同系色かどうかを判定するクラス。

        :param mask_path: マスク画像のパス（オプション）。マスクが指定された場合、その領域のみで判定する。
        :param hue_threshold: 同系色とみなすための色相の標準偏差の閾値（デフォルト: 10.0）。
                              OpenCVのHSV表色系では色相は0〜179の値になる。
        """
        super().__init__(mask_path)
        self._hue_threshold = hue_threshold

    def match(self, image: np.ndarray) -> bool:
        """
        画像全体が同系色（色相のばらつきが小さい）かどうかを判定する。

        :param image: 検索対象のイメージ。
        :return: 同系色の場合True、そうでない場合False。
        """
        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hue_channel = hsv_image[:, :, 0]
        if self._mask is not None:
            # マスクがある場合は、マスク領域の色相のみを評価
            hue_values = hue_channel[self._mask == 255]
        else:
            hue_values = hue_channel.flatten()

        if hue_values.size == 0:
            return False

        std_hue = np.std(hue_values.astype(np.float32))
        return bool(std_hue <= self._hue_threshold)


class RGBMatcher(BaseMatcher):
    """ RGB色空間での色の一致を検出するクラス (約0.05秒) """

    def __init__(self, rgb: Tuple[int, int, int], mask_path: Optional[str] = None, threshold: float = 0.9):
        """
        RGB色空間での色の一致を検出するクラス。

        :param rgb: 赤、緑、青の値。
        :param mask_path: マスク画像のパス（オプション）。
        :param threshold: 一致とみなす割合の閾値（0.0〜1.0）。
        """
        super().__init__(mask_path)
        self._rgb = rgb
        self._threshold = threshold

    def match(self, image: np.ndarray) -> bool:
        """
        イメージ内で色の一致を検出する。

        :param image: 検索対象のイメージ。
        :return: 一致したかどうか。
        """

        if self._mask is not None:
            mask = self._mask == 255
            masked_image = image[mask]
        else:
            masked_image = image.reshape(-1, 3)
            mask = np.ones(image.shape[:2], dtype=bool)

        match_pixels = np.all(masked_image == self._rgb, axis=-1)
        match_count = int(np.sum(match_pixels))

        total_masked_pixels = int(np.sum(mask))
        if total_masked_pixels == 0:
            return False
        match_ratio = match_count / total_masked_pixels
        return match_ratio >= self._threshold


class TemplateMatcher(BaseMatcher):
    """ テンプレートマッチングを行うクラス (約0.07秒) """

    def __init__(self, template_path: str, mask_path: Optional[str] = None, threshold: float = 0.9):
        """
        テンプレートマッチングを行うクラス。

        :param template_path: 照合に使用するテンプレート画像のパス。
        :param mask_path: マスク画像のパス（オプション）。
        :param threshold: 一致とみなすスコアの閾値（0.0〜1.0）。
        """
        super().__init__(mask_path)
        template = cv2.imread(template_path)
        if template is None:
            raise ValueError(f"Failed to load template image: {template_path}")
        self._template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        self._threshold = threshold
        self.height, self.width = self._template.shape[:2]

    def match(self, image: np.ndarray) -> bool:
        """
        フレーム内でテンプレートを探し、一致したかどうかを返す。

        :param image: 検索対象のイメージ。
        :return: 一致したかどうか。
        :return: (一致フラグ, 一致した位置) のタプル。位置は (x, y) の座標。
        """
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # maskがある場合とない場合で処理を分岐
        if self._mask is not None:
            result = cv2.matchTemplate(
                gray_image, self._template, cv2.TM_CCOEFF_NORMED, mask=self._mask)
        else:
            result = cv2.matchTemplate(
                gray_image, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        return max_val >= self._threshold
