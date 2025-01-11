import os
import hashlib
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
import logging

import cv2
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
    DIRECTORY = os.path.join(os.path.dirname(__file__), "templates")

    def __init__(self):
        self._ocr = OCR()

        self._start_matcher = self._create_matcher("start.png")
        self._stop_matcher = self._create_matcher("stop.png")
        self._abort_matcher = self._create_matcher("abort.png")
        self._result_matchers = self._create_matchers({
            "WIN!": "win.png",
            "LOSE...": "lose.png"
        })
        self._match_matchers = self._create_matchers({
            "レギュラーマッチ": "regular.png",
            "バンカラマッチ(チャレンジ)": "bankara_challenge.png",
            "バンカラマッチ(オープン)": "bankara_open.png",
            "Xマッチ": "x.png"
        })
        self._rule_matchers = self._create_matchers({
            "ナワバリ": "nawabari.png",
            "ガチホコ": "hoko.png",
            "ガチエリア": "area.png",
            "ガチヤグラ": "yagura.png",
            "ガチアサリ": "asari.png"
        })
        self._select_xmatch_matcher = self._create_matcher("select_xmatch.png")
        self._xp_machers_dictionary = {
            Rectangle(1730, 190, 1880, 240): self._create_matchers({
                "ガチホコ": "xp_hoko1.png",
                "ガチエリア": "xp_area1.png",
                "ガチヤグラ": "xp_yagura1.png",
                "ガチアサリ": "xp_asari1.png"
            })
        }
        virtual_camera_off_image = cv2.imread(
            os.path.join(self.DIRECTORY, "virtual_camera_off.png"))
        self._virtual_camera_off = self._hash(virtual_camera_off_image)

    def _create_matcher(self, filename: str) -> TemplateMatcher:
        path = os.path.join(self.DIRECTORY, filename)
        return TemplateMatcher(path)

    def _create_matchers(self, filenames: Dict[str, str]) -> Dict[str, TemplateMatcher]:
        return {name: self._create_matcher(filename) for name, filename in filenames.items()}

    def _hash(self, image: np.ndarray) -> str:
        hash = hashlib.sha1(image).hexdigest()
        return hash

    def virtual_camera_off(self, image: np.ndarray) -> bool:
        return self._hash(image) == self._virtual_camera_off

    def screen_off(self, image: np.ndarray) -> bool:
        return 0 < image.max() <= 10

    def battle_start(self, image: np.ndarray) -> bool:
        match, _ = self._start_matcher.match(image)
        return match

    def battle_stop(self, image: np.ndarray) -> bool:
        match, _ = self._stop_matcher.match(image)
        return match

    def battle_abort(self, image: np.ndarray) -> bool:
        match, _ = self._abort_matcher.match(image)
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
