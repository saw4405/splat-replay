import os
import time
import datetime
from typing import Dict
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

class Recorder:

    def __init__(self):
        self._load_templates()
        self._start_obs()
        self._setup_capture()

    def _load_templates(self):
        # 画像判定に使用する画像を読み込んでおく
        self._start_matcher = TemplateMatcher("templates\\start.png")
        self._stop_matcher = TemplateMatcher("templates\\stop.png")
        self._win_matcher = TemplateMatcher("templates\\win.png")
        self._lose_matcher = TemplateMatcher("templates\\lose.png")
        self._match_matchers: Dict[str, TemplateMatcher] = {
            "レギュラーマッチ": TemplateMatcher("templates\\regular.png"),
            "バンカラマッチ(チャレンジ)": TemplateMatcher("templates\\bankara_challenge.png"),
            "バンカラマッチ(オープン)": TemplateMatcher("templates\\bankara_open.png"),
            "Xマッチ": TemplateMatcher("templates\\x.png")
        }
        self._rule_matchers: Dict[str, TemplateMatcher] = {
            "ナワバリ": TemplateMatcher("templates\\nawabari.png"),
            "ガチホコ": TemplateMatcher("templates\\hoko.png"),
            "ガチエリア": TemplateMatcher("templates\\area.png"),
            "ガチヤグラ": TemplateMatcher("templates\\yagura.png"),
            "ガチアサリ": TemplateMatcher("templates\\asari.png")
        }

    def _start_obs(self):
        self._obs = Obs()
        if not self._obs.start_virtual_cam():
            raise Exception("仮想カメラの起動に失敗しました")

    def _setup_capture(self):
        index = int(os.environ["CAPTURE_DEVICE_INDEX"])
        width = int(os.environ["CAPTURE_WIDTH"])
        height = int(os.environ["CAPTURE_HEIGHT"])
        self._capture = cv2.VideoCapture(index)
        if not self._capture.isOpened():
            raise Exception("カメラが見つかりません")
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def run(self):
        self._status = RecordStatus.OFF
        self._buttle_result = ""
        self._on_counter = 0
        self._record_counter = 0

        try:
            # Switchの起動有無に関わらず、ずっと監視する (起動してないときは1分周期で起動待ちをする)
            while True:
                ret, frame = self._capture.read()
                if not ret:
                    print("フレームの読み込みに失敗しました。")
                    time.sleep(60)
                    continue

                self._process_frame(frame)
        except KeyboardInterrupt:
            print("監視を終了します")
        finally:
            self._capture.release()
            cv2.destroyAllWindows()
            if self._uploader_thread:
                self._uploader_thread.join()

    def _is_screen_off(self, image: np.ndarray) -> bool:
        if image.max() <= 10:
            return True
        return False
    
    def _process_frame(self, frame: np.ndarray):
        # Switchの起動確認
        if self._status == RecordStatus.OFF:
            # まだ起動してなかったら、また1分待つ
            if self._is_screen_off(frame):
                time.sleep(60)
                return

            print("Switchが起動しました")
            self._status = RecordStatus.WAIT
            return
            
        # 処理負荷を下げるため、Switchの電源OFF確認は60フレーム毎とする
        self._on_counter += 1
        if self._on_counter > 60:
            self._on_counter = 0
            if self._is_screen_off(frame):
                self._status = RecordStatus.OFF
                return

        # バトル開始確認
        if self._status == RecordStatus.WAIT:
            match, _ = self._start_matcher.match(frame)
            if match:
                print("録画を開始します")
                self._obs.start_record()
                self._record_counter = 0
                self._buttle_result = ""
                self._status = RecordStatus.RECORD
            return

        # 以降、バトル終了までの処理

        # 万一、バトル終了を画像検知できなかったときのため、600フレーム(10分)でタイムアウトさせる
        self._record_counter += 1
        if self._record_counter > 600:
            print("録画がタイムアウトしたため、録画を停止します")
            _, path = self._obs.stop_record()
            self._status = RecordStatus.WAIT
            return

        # 勝敗判定
        if self._buttle_result == "":
            match, _ = self._win_matcher.match(frame)
            if match:
                self._buttle_result = "WIN"
                print("勝ちました")
                return

            match, _ = self._lose_matcher.match(frame)
            if match:
                self._buttle_result = "LOSE"
                print("負けました")
                return

        # 処理負荷を下げるため、勝敗が決まってから録画停止タイミングを監視する
        match, _ = self._stop_matcher.match(frame)
        if not match:
            return

        # バトル終了後の処理
        print("録画を停止します")
        _, path = self._obs.stop_record()
        self._status = RecordStatus.WAIT

        # マッチ・ルールを分析する
        buttle = ""
        for match_name, matcher in self._match_matchers.items():
            match, _ = matcher.match(frame)
            if match:
                buttle = match_name
                print(f"マッチ: {match_name}")
                break
        rule = ""
        for rule_name, matcher in self._rule_matchers.items():
            match, _ = matcher.match(frame)
            if match:
                rule = rule_name
                print(f"ルール: {rule_name}")
                break

        # アップロードキューに追加
        file_base_name, _ = os.path.splitext(os.path.basename(path))
        start_datetime = datetime.datetime.strptime(file_base_name, "%Y-%m-%d %H-%M-%S")
        Uploader.queue(path, start_datetime, buttle, rule, self._buttle_result)
        print("アップロードキューに追加しました")
