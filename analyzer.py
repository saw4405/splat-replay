import os
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
import logging

import numpy as np

from template_matcher import TemplateMatcher
from ocr import OCR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rectangle:
    x1: int
    y1: int
    x2: int
    y2: int


class Analyzer:
    def __init__(self):
        self._ocr = OCR()

        # 画像判定に使用する画像を読み込んでおく
        directory = os.path.dirname(__file__)
        self._start_matcher = TemplateMatcher(
            os.path.join(directory, "templates", "start.png"))
        self._stop_matcher = TemplateMatcher("templates\\stop.png")
        self._result_matchers = {
            "WIN!": TemplateMatcher("templates\\win.png"),
            "LOSE...": TemplateMatcher("templates\\lose.png")
        }
        self._match_matchers = {
            "レギュラーマッチ": TemplateMatcher("templates\\regular.png"),
            "バンカラマッチ(チャレンジ)": TemplateMatcher("templates\\bankara_challenge.png"),
            "バンカラマッチ(オープン)": TemplateMatcher("templates\\bankara_open.png"),
            "Xマッチ": TemplateMatcher("templates\\x.png")
        }
        self._rule_matchers = {
            "ナワバリ": TemplateMatcher("templates\\nawabari.png"),
            "ガチホコ": TemplateMatcher("templates\\hoko.png"),
            "ガチエリア": TemplateMatcher("templates\\area.png"),
            "ガチヤグラ": TemplateMatcher("templates\\yagura.png"),
            "ガチアサリ": TemplateMatcher("templates\\asari.png")
        }
        self._select_xmatch_matcher = TemplateMatcher(
            "templates\\select_xmatch.png")
        self._xp_machers_dictionary = {
            Rectangle(1730, 190, 1880, 240): {
                "ガチホコ": TemplateMatcher("templates\\xp_hoko1.png"),
                "ガチエリア": TemplateMatcher("templates\\xp_area1.png"),
                "ガチヤグラ": TemplateMatcher("templates\\xp_yagura1.png"),
                "ガチアサリ": TemplateMatcher("templates\\xp_asari1.png"),
            }
        }

    def screen_off(self, image: np.ndarray) -> bool:
        return image.max() <= 10

    def battle_start(self, image: np.ndarray) -> bool:
        match, _ = self._start_matcher.match(image)
        return match

    def battle_stop(self, image: np.ndarray) -> bool:
        match, _ = self._stop_matcher.match(image)
        return match

    def _find(self, image: np.ndarray, matchers: Dict[str, TemplateMatcher]) -> Optional[str]:
        for name, matcher in matchers.items():
            match, _ = matcher.match(image)
            if match:
                return name
        return None

    def battle_result(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._result_matchers)

    def match_name(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._match_matchers)

    def rule_name(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._rule_matchers)

    def x_power(self, image: np.ndarray) -> Optional[Tuple[str, float]]:
        match, _ = self._select_xmatch_matcher.match(image)
        if not match:
            return None

        # XPは色んな画面で表示されるため、それら表示されるタイミング違いに応じて判定する
        for rect, matchers in self._xp_machers_dictionary.items():
            match_name = self._find(image, matchers)
            if match_name is None:
                continue
            logger.info(f"XP読み取ります: {match_name}")

            # OCRで読み取るようにXP表示部のみ切り取る
            xp_image = image[rect.y1:rect.y2, rect.x1:rect.x2]
            xp_str = self._ocr.get_text(xp_image).strip()

            try:
                xp = float(xp_str)
            except ValueError:
                logger.warning(f"Xパワーが数値ではありません: {xp_str}")
                return None

            if xp < 500 or xp > 5500:
                logger.warning(f"Xパワーが異常です: {xp}")
                return None

            return match_name, xp

        return None
