import os
import time
import datetime
from typing import Dict, Callable, Optional
from enum import Enum

import cv2
import numpy as np

from obs import Obs
from template_matcher import TemplateMatcher
from uploader import Uploader

class RecordStatus(Enum):
    OFF = 1
    WAIT = 2
    RECORD = 3

class Capture:
    def __init__(self):
        self.INDEX = int(os.environ["CAPTURE_DEVICE_INDEX"])
        self.WIDTH = int(os.environ["CAPTURE_WIDTH"])
        self.HEIGHT = int(os.environ["CAPTURE_HEIGHT"])

        self._capture = cv2.VideoCapture(self.INDEX)
        if not self._capture.isOpened():
            raise Exception("カメラが見つかりません")
        
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.HEIGHT)

    def read(self) -> np.ndarray:
        ret, frame = self._capture.read()
        if ret:
            return frame
        raise Exception("フレームの読み込みに失敗しました")
        
    def release(self):
        self._capture.release()
        cv2.destroyAllWindows()

class FrameAnalyzer:
    def __init__(self):
        # 画像判定に使用する画像を読み込んでおく
        self._start_matcher = TemplateMatcher("templates\\start.png")
        self._stop_matcher = TemplateMatcher("templates\\stop.png")
        self._win_matcher = TemplateMatcher("templates\\win.png")
        self._lose_matcher = TemplateMatcher("templates\\lose.png")
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

    def screen_off(self, image: np.ndarray) -> bool:
        return image.max() <= 10
    
    def buttle_start(self, frame: np.ndarray) -> bool:
        match, _ = self._start_matcher.match(frame)
        return match

    def buttle_stop(self, frame: np.ndarray) -> bool:
        match, _ = self._stop_matcher.match(frame)
        return match

    def buttle_result(self, frame: np.ndarray) -> str:
        match, _ = self._win_matcher.match(frame)
        if match:
            return "WIN!"

        match, _ = self._lose_matcher.match(frame)
        if match:
            return "LOSE..."
        
        return ""
        
    def match_name(self, frame: np.ndarray) -> str:
        for match_name, matcher in self._match_matchers.items():
            match, _ = matcher.match(frame)
            if match:
                return match_name
        return ""
    
    def rule_name(self, frame: np.ndarray) -> str:
        for rule_name, matcher in self._rule_matchers.items():
            match, _ = matcher.match(frame)
            if match:
                return rule_name
        return ""

class Recorder:
    def __init__(self):
        self._obs = Obs()
        # バトル開始等の画像判定への入力として仮想カメラを起動する
        if not self._obs.start_virtual_cam():
            raise Exception("仮想カメラの起動に失敗しました")
        
        self._capture = Capture()
        self._analyzer = FrameAnalyzer()
        
        self._buttle_result = ""
        self._record_start_time = time.time()
        self._last_power_check_time = time.time()

        self._power_off_callback: Optional[Callable[[], None]] = None

    def register_power_off_callback(self, callback: Callable[[], None]):
        self._power_off_callback = callback

    def run(self):
        try:
            # Switchの起動有無に関わらず、ずっと映像入力を監視する (起動してないときは1分周期で起動待ちをする)
            status = RecordStatus.OFF
            while True:
                frame = self._capture.read()
                
                if status == RecordStatus.OFF:
                    # Switchの起動確認
                    status = self._handle_off_status(frame)
                
                else:
                    status = self._check_power_off(frame) or status
                        
                    if status == RecordStatus.WAIT:
                        # バトル開始確認し、開始したら録画開始
                        status = self._handle_wait_status(frame)

                    elif status == RecordStatus.RECORD:
                        # バトル終了確認し、終了したら録画停止＆アップロード待ちに追加
                        status = self._handle_record_status(frame)

        except KeyboardInterrupt:
            print("監視を終了します")

        finally:
            self._capture.release()
    
    def _handle_off_status(self, frame: np.ndarray) -> RecordStatus:
        # まだ起動してなかったら、1分後に再度確認する
        if self._analyzer.screen_off(frame):
            time.sleep(60)
            return RecordStatus.OFF
        
        print("Switchが起動しました")
        return RecordStatus.WAIT

    def _check_power_off(self, frame: np.ndarray) -> Optional[RecordStatus]:
        # Switchが電源OFFされたかの確認 (処理負荷を下げるため1分毎に確認する)
        if time.time() - self._last_power_check_time < 60:
            return None
        
        self._last_power_check_time = time.time()
        if not self._analyzer.screen_off(frame):
            return None
        
        print("Switchが電源OFFされました")
        if self._power_off_callback:
            self._power_off_callback()
        return RecordStatus.OFF

    def _handle_wait_status(self, frame: np.ndarray) -> RecordStatus:
        start = self._analyzer.buttle_start(frame)
        if not start:
            return RecordStatus.WAIT
        
        self._start_record()
        return RecordStatus.RECORD

    def _handle_record_status(self, frame: np.ndarray) -> RecordStatus:
        # 万一、バトル終了を画像検知できなかったときのため、10分でタイムアウトさせる
        if time.time() - self._record_start_time > 600:
            print("録画がタイムアウトしたため、録画を停止します")
            self._stop_record(frame)
            return RecordStatus.WAIT
        
        # 勝敗判定
        if self._buttle_result == "":
            self._buttle_result = self._analyzer.buttle_result(frame)
            if self._buttle_result != "":
                print(f"バトル結果: {self._buttle_result}")
            return RecordStatus.RECORD
        
        # 処理負荷を下げるため、勝敗が決まってから録画停止タイミングを監視する
        stop = self._analyzer.buttle_stop(frame)
        if stop:
            self._stop_record(frame)
            return RecordStatus.WAIT
        
        return RecordStatus.RECORD
    
    def _start_record(self):
        print("録画を開始します")
        self._obs.start_record()
        self._record_start_time = time.time()
        self._buttle_result = ""

    def _stop_record(self, frame: np.ndarray):
        print("録画を停止します")
        _, path = self._obs.stop_record()

        # マッチ・ルールを分析する
        match = self._analyzer.match_name(frame)
        print(f"マッチ: {match}")
        rule = self._analyzer.rule_name(frame)
        print(f"ルール: {rule}")

        # アップロードキューに追加
        file_base_name, _ = os.path.splitext(os.path.basename(path))
        start_datetime = datetime.datetime.strptime(file_base_name, "%Y-%m-%d %H-%M-%S")
        Uploader.queue(path, start_datetime, match, rule, self._buttle_result)
        print("アップロードキューに追加しました")

        if match == "" or rule == "":
            print("マッチ・ルールの判定に失敗しました")
