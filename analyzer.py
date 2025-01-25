import os
import hashlib
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
import logging

import numpy as np

from image_matcher import TemplateMatcher, HSVMatcher, HashMatcher
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
        self._init_matchers()

    def _init_matchers(self):
        def get_full_path(filename: str) -> str:
            directory = os.path.join(os.path.dirname(__file__), "templates")
            return os.path.join(directory, filename)

        def create_template_matchers(filenames: Dict[str, str]) -> Dict[str, TemplateMatcher]:
            return {name: TemplateMatcher(get_full_path(filename)) for name, filename in filenames.items()}

        self._matching_matcher = TemplateMatcher(get_full_path("matching.png"))
        self._wait_matcher = TemplateMatcher(get_full_path("wait.png"))
        self._start_matcher = TemplateMatcher(get_full_path("start.png"))
        self._stop_matcher = TemplateMatcher(get_full_path("stop.png"))
        self._abort_matcher = TemplateMatcher(get_full_path("abort.png"))
        self._result_matchers = create_template_matchers({
            "WIN!": "win.png",
            "LOSE...": "lose.png"
        })
        self._match_matchers = create_template_matchers({
            "レギュラーマッチ": "regular.png",
            "バンカラマッチ(チャレンジ)": "bankara_challenge.png",
            "バンカラマッチ(オープン)": "bankara_open.png",
            "Xマッチ": "x.png"
        })
        self._rule_matchers = create_template_matchers({
            "ナワバリ": "nawabari.png",
            "ガチホコ": "hoko.png",
            "ガチエリア": "area.png",
            "ガチヤグラ": "yagura.png",
            "ガチアサリ": "asari.png"
        })
        self._xp_machers_dictionary = {
            Rectangle(1730, 190, 1880, 240): create_template_matchers({
                "ガチホコ": "xp_hoko1.png",
                "ガチエリア": "xp_area1.png",
                "ガチヤグラ": "xp_yagura1.png",
                "ガチアサリ": "xp_asari1.png"
            })
        }
        self._select_xmatch_matcher = HSVMatcher(
            (80, 255, 250), (90, 255, 255), get_full_path("select_xmatch_mask.png"))
        self._finish_matcher = HSVMatcher(
            (0, 0, 0), (180, 255, 50), get_full_path("finish_mask.png"))
        self._virtual_camera_off_matcher = HashMatcher(
            get_full_path("virtual_camera_off.png"))

    def virtual_camera_off(self, image: np.ndarray) -> bool:
        return self._virtual_camera_off_matcher.match(image)

    def black_screen(self, image: np.ndarray) -> bool:
        return image.max() <= 10

    def loading(self, image: np.ndarray) -> bool:
        # ロード画面は上部800pxが真っ黒
        top_image = image[:800, :]
        bottom_image = image[800:, :]
        return self.black_screen(top_image) and not self.black_screen(bottom_image)

    def matching_start(self, image: np.ndarray) -> bool:
        return self._matching_matcher.match(image)

    def wait(self, image: np.ndarray) -> bool:
        return self._wait_matcher.match(image)

    def battle_start(self, image: np.ndarray) -> bool:
        return self._start_matcher.match(image)

    def battle_finish(self, image: np.ndarray) -> bool:
        # Finish!の黒文字で判定するため、画面が黒いと誤検知してしまうため、黒画像は除外
        if self.black_screen(image):
            return False
        return self._finish_matcher.match(image)

    def battle_stop(self, image: np.ndarray) -> bool:
        return self._stop_matcher.match(image)

    def battle_abort(self, image: np.ndarray) -> bool:
        return self._abort_matcher.match(image)

    def _find(self, image: np.ndarray, matchers: Dict[str, TemplateMatcher]) -> Optional[str]:
        for name, matcher in matchers.items():
            if matcher.match(image):
                return name
        return None

    def battle_result(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._result_matchers)

    def battle_result_latter_half(self, image: np.ndarray) -> bool:
        # 後半の勝敗表示画面は右上が黒い
        right_top_image = image[0:200, 1720:1920]
        if not self.black_screen(right_top_image):
            return False
        return self.battle_result(image) != None

    def match_name(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._match_matchers)

    def rule_name(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._rule_matchers)

    def x_power(self, image: np.ndarray) -> Optional[Tuple[str, float]]:
        if not self._select_xmatch_matcher.match(image):
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
