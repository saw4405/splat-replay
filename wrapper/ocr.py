import os

import pytesseract
import numpy as np

from utility.result import Result, Ok, Err


class OCR:
    def __init__(self, path: str):
        pytesseract.pytesseract.tesseract_cmd = path

    def read_text(self, image: np.ndarray) -> Result[str, str]:
        """ 画像からテキストを取得する

        Args:
            image (np.ndarray): テキストを読み取る画像

        Returns:
            Result[str, str]: 成功した場合はOkに読み取ったテキストが格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        try:
            text = str(pytesseract.image_to_string(image))
            return Ok(text)
        except pytesseract.TesseractNotFoundError:
            return Err("Tesseractがインストールされていません")
        except Exception as e:
            return Err(f"Tesseractでエラーが発生しました: {e}")
