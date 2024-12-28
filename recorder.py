import os
import logging
import time
import datetime
from typing import Dict, Callable, Optional
from enum import Enum

import numpy as np

from obs import Obs
from uploader import Uploader
from capture import Capture
from analyzer import Analyzer

logger = logging.getLogger(__name__)


class RecordStatus(Enum):
    OFF = 1
    WAIT = 2
    RECORD = 3


class Recorder:
    def __init__(self):
        self._obs = Obs()
        # バトル開始等の画像判定への入力として仮想カメラを起動する
        if not self._obs.start_virtual_cam():
            raise Exception("仮想カメラの起動に失敗しました")

        self._capture = Capture()
        self._analyzer = Analyzer()

        self._battle_result: Optional[str] = None
        self._x_power: Dict[str, float] = {}
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
            logger.info("監視を終了します")

        finally:
            self._capture.release()

    def _handle_off_status(self, frame: np.ndarray) -> RecordStatus:
        # まだ起動してなかったら、1分後に再度確認する
        if self._analyzer.screen_off(frame):
            time.sleep(60)
            return RecordStatus.OFF

        logger.info("Switchが起動しました")
        return RecordStatus.WAIT

    def _check_power_off(self, frame: np.ndarray) -> Optional[RecordStatus]:
        # Switchが電源OFFされたかの確認 (処理負荷を下げるため1分毎に確認する)
        if time.time() - self._last_power_check_time < 60:
            return None
        self._last_power_check_time = time.time()

        if not self._analyzer.screen_off(frame):
            return None

        logger.info("Switchが電源OFFされました")
        if self._power_off_callback:
            self._power_off_callback()
        return RecordStatus.OFF

    def _handle_wait_status(self, frame: np.ndarray) -> RecordStatus:

        # XPが表示されたら記録しとく
        result = self._analyzer.x_power(frame)
        if result:
            rule, xp = result
            if self._x_power.get(rule, 0.0) != xp:
                logger.info(f"{rule}のXパワー: {xp}")
                self._x_power[rule] = xp

        start = self._analyzer.battle_start(frame)
        if not start:
            return RecordStatus.WAIT

        self._start_record()
        return RecordStatus.RECORD

    def _handle_record_status(self, frame: np.ndarray) -> RecordStatus:
        # 万一、バトル終了を画像検知できなかったときのため、10分でタイムアウトさせる
        if time.time() - self._record_start_time > 600:
            logger.info("録画がタイムアウトしたため、録画を停止します")
            self._stop_record(frame)
            return RecordStatus.WAIT

        # 勝敗判定
        if self._battle_result is None:
            self._battle_result = self._analyzer.battle_result(frame)
            if self._battle_result:
                logger.info(f"バトル結果: {self._battle_result}")
            return RecordStatus.RECORD

        # 処理負荷を下げるため、勝敗が決まってから録画停止タイミングを監視する
        stop = self._analyzer.battle_stop(frame)
        if stop:
            self._stop_record(frame)
            return RecordStatus.WAIT

        return RecordStatus.RECORD

    def _start_record(self):
        logger.info("録画を開始します")
        self._obs.start_record()
        self._record_start_time = time.time()
        self._battle_result = None

    def _stop_record(self, frame: np.ndarray):
        logger.info("録画を停止します")
        _, path = self._obs.stop_record()

        # マッチ・ルールを分析する
        match = self._analyzer.match_name(frame) or ""
        logger.info(f"マッチ: {match}")
        rule = self._analyzer.rule_name(frame) or ""
        logger.info(f"ルール: {rule}")

        # アップロードキューに追加
        file_base_name, _ = os.path.splitext(os.path.basename(path))
        start_datetime = datetime.datetime.strptime(
            file_base_name, "%Y-%m-%d %H-%M-%S")
        Uploader.queue(path, start_datetime, match, rule,
                       self._battle_result, self._x_power.get(rule, None))
        logger.info("アップロードキューに追加しました")

        if match == "" or rule == "":
            logger.info("マッチ・ルールの判定に失敗しました")

        self._x_power = {}
