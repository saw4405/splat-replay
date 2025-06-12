import os
from typing import Optional, Dict, Tuple, Union
from dataclasses import dataclass
import logging

import cv2
import numpy as np

from image_matcher import TemplateMatcher, HSVMatcher, HashMatcher, UniformColorMatcher
from wrapper.ocr import OCR
from models.rate import XP, RateBase, Udemae

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rectangle:
    x1: int
    y1: int
    x2: int
    y2: int


class Analyzer:
    def __init__(self):
        self._init_ocr()
        self._init_matchers()

    def _init_ocr(self):
        tesseract_path = os.environ.get("TESSERACT_PATH")

        if tesseract_path and os.path.exists(tesseract_path):
            self._ocr = OCR(tesseract_path)
        else:
            logger.warning(
                "環境変数TESSERACT_PATHが設定されていないか、指定されたパスが存在しません。OCR機能は使用できません。")
            self._ocr = None

    def _init_matchers(self):
        def get_full_path(filename: str) -> str:
            directory = os.path.join(os.getcwd(), "assets", "templates")
            return os.path.join(directory, filename)

        def create_template_matchers(filenames: Dict[str, Union[str, Tuple[str, str]]]) -> Dict[str, TemplateMatcher]:
            return {name: TemplateMatcher(get_full_path(filename)) if isinstance(filename, str) else TemplateMatcher(get_full_path(filename[0]), get_full_path(filename[1])) for name, filename in filenames.items()}

        self._matching_matcher = TemplateMatcher(get_full_path("matching.png"))
        self._matching_mask_matcher = HSVMatcher(
            (0, 0, 200), (179, 20, 255), get_full_path("matching_mask.png"))
        self._change_schedule_matcher = TemplateMatcher(
            get_full_path("change_schedule.png"))
        self._wait_matcher = TemplateMatcher(get_full_path("wait.png"))
        self._start_matcher = TemplateMatcher(get_full_path("start.png"))
        self._stop_matcher = TemplateMatcher(
            get_full_path("stop.png"), threshold=0.95)
        self._stop_message_matcher = HSVMatcher(
            (0, 0, 200), (179, 20, 255), get_full_path("stop_mask.png"))
        self._stop_icon_matcher = HSVMatcher(
            (0, 0, 200), (179, 20, 255), get_full_path("stop_icon_mask.png"))
        self._stop_gear_matcher = HSVMatcher(
            (0, 0, 0), (179, 255, 50), get_full_path("stop_gear_mask.png"))
        self._stop_background_matcher = HSVMatcher(
            (0, 0, 25), (179, 30, 40), get_full_path("stop_background_mask.png"))
        self._abort_background_matcher = HSVMatcher((0, 0, 25), (0, 0, 35))
        self._abort_matcher = TemplateMatcher(get_full_path("abort.png"))
        self._result_matchers = create_template_matchers({
            "WIN": "win.png",
            "LOSE": "lose.png"
        })
        self._match_matchers = create_template_matchers({
            "レギュラーマッチ": "regular.png",
            "バンカラマッチ(チャレンジ)": "bankara_challenge.png",
            "バンカラマッチ(オープン)": "bankara_open.png",
            "Xマッチ": "x.png",
            "フェスマッチ(チャレンジ)": "fes_challenge.png",
            "フェスマッチ(オープン)": "fes_open.png",
            "トリカラマッチ": "torikara_match.png"
        })
        self._rule_matchers = create_template_matchers({
            "ナワバリ": "nawabari.png",
            "ガチホコ": "hoko.png",
            "ガチエリア": "area.png",
            "ガチヤグラ": "yagura.png",
            "ガチアサリ": "asari.png",
            "トリカラ": "torikara_battle.png"
        })
        self._stage_matchers = create_template_matchers({
            "海女美術大学": "amabi.png",
            "バイガイ亭": "baigai.png",
            "ゴンズイ地区": "gonzui.png",
            "ヒラメが丘団地": "hirame.png",
            "カジキ空港": "kajiki.png",
            "キンメダイ美術館": "kinme.png",
            "コンブトラック": "konbu.png",
            "クサヤ温泉": "kusaya.png",
            "マヒマヒリゾート&スパ": "mahimahi.png",
            "マンタマリア号": "manta.png",
            "マサバ海峡大橋": "masaba.png",
            "マテガイ放水路": "mategai.png",
            "ナメロウ金属": "namero.png",
            "ナンプラー遺跡": "nanpura-.png",
            "ネギトロ炭鉱": "negitoro.png",
            "オヒョウ海運": "ohyo.png",
            "リュウグウターミナル": "ryugu.png",
            "スメーシーワールド": "sume-shi-.png",
            "タカアシ経済特区": "takaashi.png",
            "タラポートショッピングパーク": "tarapo.png",
            "チョウザメ造船": "chouzame.png",
            "ヤガラ市場": "yagara.png",
            "ユノハナ大渓谷": "yunohana.png",
            "ザトウマーケット": "zatou.png",
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
            (80, 230, 230), (90, 255, 255))
        self._select_bankara_match_matcher = HSVMatcher(
            (13, 230, 230), (15, 255, 255))
        self._udemae_matchers = create_template_matchers({
            "S+": "s_plus.png",
            "S": ("s.png", "s_mask.png"),
        })
        self._finish_text_matcher = HSVMatcher(
            (0, 0, 0), (179, 255, 50), get_full_path("finish_text_mask.png"))
        self._finish_band_matcher = HSVMatcher(
            (0, 0, 50), (179, 255, 255), get_full_path("finish_band_mask.png"))
        self._virtual_camera_off_matcher = HashMatcher(
            get_full_path("virtual_camera_off.png"))
        power_off_image_path = get_full_path("power_off.png")
        self._power_off_matcher = TemplateMatcher(
            power_off_image_path) if os.path.exists(power_off_image_path) else None

    def virtual_camera_off(self, image: np.ndarray) -> bool:
        return self._virtual_camera_off_matcher.match(image)

    def power_off(self, image: np.ndarray) -> bool:
        return self.black_screen(image) or (self._power_off_matcher.match(image) if self._power_off_matcher else False)

    def black_screen(self, image: np.ndarray) -> bool:
        return image.max() <= 20

    def loading(self, image: np.ndarray) -> bool:
        # ロード画面は上部800pxが真っ黒
        top_image = image[:800, :]
        bottom_image = image[800:, :]
        return self.black_screen(top_image) and not self.black_screen(bottom_image)

    def matching_start(self, image: np.ndarray) -> bool:
        # TemplateMatcherは遅いため、先にHSVMatcherで検出する
        if not self._matching_mask_matcher.match(image):
            return False
        return self._matching_matcher.match(image)

    def change_schedule(self, image: np.ndarray) -> bool:
        cropped_image = image[444:555, 555:666]
        if not self.black_screen(cropped_image):
            return False

        return self._change_schedule_matcher.match(image)

    def wait(self, image: np.ndarray) -> bool:
        return self._wait_matcher.match(image)

    def battle_start(self, image: np.ndarray) -> bool:
        cropped_image = image[360:380, 900:1040]
        if not self.black_screen(cropped_image):
            return False
        return self._start_matcher.match(image)

    def battle_finish(self, image: np.ndarray) -> bool:
        cropped_image = image[400:440, 810:840]
        matcher = UniformColorMatcher()
        if not matcher.match(cropped_image) or self.black_screen(cropped_image):
            return False

        # 全体が黒いときに誤判定しないよう、Finishの帯が黒色でないことも確認する
        return self._finish_text_matcher.match(image) and self._finish_band_matcher.match(image)

    def battle_stop(self, image: np.ndarray) -> bool:
        # リザルト画面をサムネイルのベースに使用するため、厳密に判定する
        # 「ゲットした表彰」という文字がある。キャラクターアイコンが表示されている。ギア名が表示されている。ローディング画面が表示されていない。
        return self._stop_message_matcher.match(image) and not self._stop_icon_matcher.match(image) and not self._stop_gear_matcher.match(image) and self._stop_background_matcher.match(image)

    def battle_abort(self, image: np.ndarray) -> bool:
        background_image = image[220:300, 800:1100]
        if not self._abort_background_matcher.match(background_image):
            return False

        return self._abort_matcher.match(image)

    def _find(self, image: np.ndarray, matchers: Dict[str, TemplateMatcher]) -> Optional[str]:
        for name, matcher in matchers.items():
            if matcher.match(image):
                return name
        return None

    def battle_result(self, image: np.ndarray) -> Optional[str]:
        top_left_image = image[0:40, 0:230]
        if not self.black_screen(top_left_image) or self.loading(image):
            return None
        return self._find(image, self._result_matchers)

    def battle_result_latter_half(self, image: np.ndarray) -> bool:
        # 後半の勝敗表示画面は右上が黒い
        right_top_image = image[0:100, 1820:1920]
        if not self.black_screen(right_top_image):
            return False
        return self.battle_result(image) != None

    def match_name(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._match_matchers)

    def rule_name(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._rule_matchers)

    def stage_name(self, image: np.ndarray) -> Optional[str]:
        return self._find(image, self._stage_matchers)

    def _rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        rows, cols = image.shape[:2]
        M = cv2.getRotationMatrix2D((cols/2, rows/2), angle, 1)
        return cv2.warpAffine(image, M, (cols, rows))

    def rate(self, image: np.ndarray) -> Optional[RateBase]:
        cropped_image = image[390:410, 280:300]
        # cropped_image_fes = image[450:470, 280:300]
        matcher = UniformColorMatcher()
        if not matcher.match(cropped_image):
            return None

        if self._select_xmatch_matcher.match(cropped_image):
            if (xp := self.x_power(image)) is not None:
                return xp[1]
        elif self._select_bankara_match_matcher.match(cropped_image):
            if (udemae := self.udemae(image)) is not None:
                return udemae
        return None

    def udemae(self, image: np.ndarray) -> Optional[Udemae]:
        if (udemae := self._find(image, self._udemae_matchers)) is None:
            return None
        return Udemae(udemae)

    def x_power(self, image: np.ndarray) -> Optional[Tuple[str, XP]]:
        if self._ocr is None:
            return None

        # XPは色んな画面で表示されるため、それら表示されるタイミング違いに応じて判定する
        for rect, matchers in self._xp_machers_dictionary.items():
            match_name = self._find(image, matchers)
            if match_name is None:
                continue

            # OCRで読み取るようにXP表示部のみ切り取る (精度向上のため、4度回転させて文字を水平にする)
            xp_image = image[rect.y1:rect.y2, rect.x1:rect.x2]
            xp_image = self._rotate_image(xp_image, -4)
            result = self._ocr.read_text(xp_image)
            if result.is_err():
                logger.warning(f"XパワーのOCRに失敗しました: {result.unwrap_err()}")
                return None
            xp_str = result.unwrap().strip()

            try:
                xp = float(xp_str)
            except ValueError:
                logger.warning(f"Xパワーが数値ではありません: {xp_str}")
                return None

            if xp < 500 or xp > 5500:
                logger.warning(f"Xパワーが異常です: {xp}")
                return None

            return match_name, XP(xp)

        return None

    def kill_record(self, image: np.ndarray) -> Optional[Tuple[int, int, int]]:
        if self._ocr is None:
            return None

        rule = self.rule_name(image)
        if rule is None:
            return None

        if rule == "トリカラ":
            record_positions: Dict[str, Dict[str, int]] = {
                "kill": {"x1": 1556, "y1": 293, "x2": 1585, "y2": 316},
                "death": {"x1": 1616, "y1": 293, "x2": 1644, "y2": 316},
                "special": {"x1": 1674, "y1": 293, "x2": 1703, "y2": 316}
            }
        else:
            record_positions: Dict[str, Dict[str, int]] = {
                "kill": {"x1": 1519, "y1": 293, "x2": 1548, "y2": 316},
                "death": {"x1": 1597, "y1": 293, "x2": 1626, "y2": 316},
                "special": {"x1": 1674, "y1": 293, "x2": 1703, "y2": 316}
            }

        records: Dict[str, int] = {}
        for name, position in record_positions.items():
            count_image = image[position["y1"]
                :position["y2"], position["x1"]:position["x2"]]

            # 文字認識の精度向上のため、拡大・余白・白文字・細字化を行う
            count_image = cv2.resize(count_image, (0, 0), fx=3.5, fy=3.5)
            count_image = cv2.copyMakeBorder(
                count_image, 50, 50, 50, 50, cv2.BORDER_CONSTANT, value=(0, 0, 0))
            count_image = cv2.cvtColor(count_image, cv2.COLOR_BGR2GRAY)
            count_image = cv2.threshold(
                count_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            count_image = cv2.erode(
                count_image, np.ones((2, 2), np.uint8), iterations=5)
            count_image = cv2.bitwise_not(count_image)

            result = self._ocr.read_text(
                count_image, "SINGLE_LINE", "0123456789")
            if result.is_err():
                logger.warning(f"{name}数のOCRに失敗しました: {result.unwrap_err()}")
                return None

            count_str = result.unwrap().strip()
            try:
                count = int(count_str)
                records[name] = count
            except ValueError:
                logger.warning(f"{name}数が数値ではありません: {count_str}")

        if len(records) != 3:
            return None
        return records["kill"], records["death"], records["special"]
