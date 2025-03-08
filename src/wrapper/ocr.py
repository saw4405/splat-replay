from typing import Optional, Literal

import pytesseract
import numpy as np

from utility.result import Result, Ok, Err

# ps_modeの型を定義する
PSMode = Literal["AUTO", "SINGLE_COLUMN", "SINGLE_LINE",
                 "SINGLE_WORD", "SINGLE_BLOCK", "SINGLE_CHAR"]


class OCR:
    def __init__(self, path: str):
        pytesseract.pytesseract.tesseract_cmd = path

    def read_text(self, image: np.ndarray, ps_mode: Optional[PSMode] = None, whitelist: Optional[str] = None) -> Result[str, str]:
        """ 画像からテキストを取得する

        Args:
            image (np.ndarray): テキストを読み取る画像
            ps_mode (Optional[PSMode], optional): ページ分割モード（例: "AUTO", "SINGLE_COLUMN", "SINGLE_LINE", "SINGLE_WORD"）
            whitelist (Optional[str], optional): 読み取る文字のホワイトリスト

        Returns:
            Result[str, str]: 成功した場合はOkに読み取ったテキストが格納され、失敗した場合はErrにエラーメッセージが格納される
        """
        try:
            # ps_modeの文字列をTesseractの数字に変換するマッピング
            psm_mapping = {
                "AUTO": 3,
                "SINGLE_COLUMN": 4,
                "SINGLE_BLOCK": 6,
                "SINGLE_LINE": 7,
                "SINGLE_WORD": 8,
                "SINGLE_CHAR": 10,

            }
            config = ""
            if ps_mode:
                psm_value = psm_mapping.get(ps_mode.upper())
                if psm_value is not None:
                    config += f"--psm {psm_value} "
            if whitelist:
                config += f"-c tessedit_char_whitelist={whitelist}"
            text = str(pytesseract.image_to_string(image, config=config))
            return Ok(text)
        except pytesseract.TesseractNotFoundError:
            return Err("Tesseractがインストールされていません")
        except Exception as e:
            return Err(f"Tesseractでエラーが発生しました: {e}")
