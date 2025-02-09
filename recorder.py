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
from transcriber import Transcriber
from utility.graceful_thread import GracefulThread
import utility.os as os_utility

logger = logging.getLogger(__name__)


class RecordStatus(Enum):
    OFF = 1
    WAIT = 2
    RECORD = 3
    PAUSE = 4


class Recorder(GracefulThread):
    def __init__(self):
        super().__init__()

        self._obs = Obs()
        # バトル開始等の画像判定への入力として仮想カメラを起動する
        if not self._obs.start_virtual_cam():
            raise Exception("仮想カメラの起動に失敗しました")

        self._capture = Capture()
        self._analyzer = Analyzer()
        self._transcriber = self._create_transcriber()

        self._matching_start_time: Optional[datetime.datetime] = None
        self._battle_result: Optional[str] = None
        self._x_power: Dict[str, float] = {}
        self._record_start_time = time.time()
        self._last_power_check_time = time.time()
        self._screen_off_count = 0
        self._should_resume_recording: Optional[Callable[[
            np.ndarray], bool]] = None

        self._power_off_callback: Optional[Callable[[], None]] = None

    def _create_transcriber(self) -> Optional[Transcriber]:
        mic_device = os.environ.get("MIC_DEVICE", "")
        if len(mic_device) == 0:
            logger.warning("マイクデバイスが設定されていないため、音声認識機能は無効化されます")
            return None

        model_path = os.path.join(os.path.dirname(__file__), "vosk_model")

        try:
            mic_device = int(mic_device)
        except:
            pass

        return Transcriber(mic_device, model_path)

    def register_power_off_callback(self, callback: Callable[[], None]):
        self._power_off_callback = callback

    def run(self):
        logger.info("Recorderを起動します")
        try:
            status = RecordStatus.OFF
            while not self.stopped:
                frame = self._capture.read()

                status = self._check_switch_power_status(frame, status)

                if status == RecordStatus.WAIT:
                    # バトル開始確認し、開始したら録画開始
                    status = self._handle_wait_status(frame)

                elif status == RecordStatus.RECORD:
                    # バトル終了確認し、終了したら録画停止＆アップロード待ちに追加
                    status = self._handle_record_status(frame)

                elif status == RecordStatus.PAUSE:
                    # ローディング終了を監視し、終了したら録画再開
                    status = self._handle_pause_status(frame)

        except Exception as e:
            logger.error(f"Recorderでエラーが発生しました: {e}")

        finally:
            logger.info("Recorderのリソースを解放します")
            self._capture.release()
            self._obs.close()

    def _check_switch_power_status(self, frame: np.ndarray, current_status: RecordStatus) -> RecordStatus:
        # Switchの電源状態を確認する (処理負荷を下げるため10秒毎に確認する)
        if time.time() - self._last_power_check_time < 10:
            return current_status
        self._last_power_check_time = time.time()

        if self._analyzer.black_screen(frame):
            self._screen_off_count += 1
        else:
            self._screen_off_count = 0

        if self._screen_off_count >= 3:
            # 電源ON→OFF
            if current_status != RecordStatus.OFF:
                logger.info("Switchが電源OFFされました")
                if self._power_off_callback:
                    self._power_off_callback()
                    logger.info("電源OFF時のコールバックを実行しました")
            return RecordStatus.OFF

        # PCがスリープから復帰したとき、キャプチャボードの接続が切れているので、再接続する
        if self._analyzer.virtual_camera_off(frame):
            logger.info("仮想カメラがOFFされました")
            if not self._obs.start_virtual_cam():
                logger.warning("仮想カメラの再起動に失敗しました")
            return RecordStatus.OFF

        # 電源OFF→ON
        if current_status == RecordStatus.OFF:
            logger.info("Switchが起動しました")
            return RecordStatus.WAIT

        # 電源ON→ON
        return current_status

    def _handle_wait_status(self, frame: np.ndarray) -> RecordStatus:

        if self._matching_start_time is None:
            # XPが表示されたら記録しとく (XPはマッチング開始前に表示される)
            if result := self._analyzer.x_power(frame):
                rule, xp = result
                if self._x_power.get(rule, 0.0) != xp:
                    logger.info(f"{rule}のXパワー: {xp}")
                    self._x_power[rule] = xp

            # 動画のスケジュール分けを正確にできるよう、マッチング開始時の日時を記録しておく
            if self._analyzer.matching_start(frame):
                self._matching_start_time = datetime.datetime.now()
                logger.info("マッチング開始を検知しました")

            return RecordStatus.WAIT

        # 処理負荷を低減するため、マッチング開始を検知した後にバトル開始を監視する
        if self._analyzer.battle_start(frame):
            self._start_record()
            return RecordStatus.RECORD

        return RecordStatus.WAIT

    def _handle_record_status(self, frame: np.ndarray) -> RecordStatus:

        record_time = time.time() - self._record_start_time

        # 万一、バトル終了を画像検知できなかったときのため、10分でタイムアウトさせる
        if record_time > 600:
            logger.info("録画がタイムアウトしたため、録画を停止します")
            self._stop_record(frame)
            return RecordStatus.WAIT

        # 開始1分くらいはバトル中断があり得るので、それを監視する
        if record_time < 90 and self._analyzer.battle_abort(frame):
            logger.info("バトルが中断されたため、録画を中止します")
            self._cancel_record()
            return RecordStatus.WAIT

        # 勝敗判定
        if self._battle_result is None:
            # Finish!表示中は録画を一時停止する
            if self._analyzer.battle_finish(frame):
                self._should_resume_recording = lambda frame: not self._analyzer.battle_result_latter_half(
                    frame)
                self._pause_record()
                return RecordStatus.PAUSE

            self._battle_result = self._analyzer.battle_result(frame)
            if self._battle_result:
                logger.info(f"バトル結果: {self._battle_result}")
            return RecordStatus.RECORD

        # ローディング中は録画を一時停止する
        if self._analyzer.loading(frame):
            self._should_resume_recording = self._analyzer.loading
            self._pause_record()
            return RecordStatus.PAUSE

        # 処理負荷を下げるため、勝敗が決まってから録画停止タイミングを監視する
        if self._analyzer.battle_stop(frame):
            self._stop_record(frame)
            return RecordStatus.WAIT

        return RecordStatus.RECORD

    def _handle_pause_status(self, frame: np.ndarray) -> RecordStatus:
        if self._should_resume_recording is None:
            raise Exception("resume_check_callbackが設定されていません")

        if not self._should_resume_recording(frame):
            self._resume_record()
            return RecordStatus.RECORD

        return RecordStatus.PAUSE

    def _start_record(self):
        logger.info("録画を開始します")
        self._obs.start_record()
        if self._transcriber:
            self._transcriber.start_recognition()
        self._record_start_time = time.time()
        self._battle_result = None

    def _pause_record(self):
        logger.info("録画を一時停止します")
        self._obs.pause_record()

    def _resume_record(self):
        logger.info("録画を再開します")
        self._obs.resume_record()

    def _cancel_record(self):
        logger.info("録画を中止します")
        _, path = self._obs.stop_record()
        if self._transcriber:
            self._transcriber.stop_recognition()

        self._matching_start_time = None

        if os_utility.remove_file(path).is_err():
            logger.warning(f"中断された録画ファイルの削除に失敗しました")

    def _stop_record(self, frame: np.ndarray):
        logger.info("録画を停止します")
        _, path = self._obs.stop_record()
        self._transcriber.stop_recognition()
        srt = self._transcriber.get_srt()

        # マッチ・ルールを分析する
        match = self._analyzer.match_name(frame) or ""
        logger.info(f"マッチ: {match}")
        rule = self._analyzer.rule_name(frame) or ""
        logger.info(f"ルール: {rule}")
        stage = self._analyzer.stage_name(frame) or ""
        logger.info(f"ステージ: {stage}")

        # アップロードキューに追加
        start_datetime = self._matching_start_time or \
            Obs.extract_start_datetime(path)
        Uploader.queue(path, start_datetime, match, rule, stage,
                       self._battle_result, self._x_power.get(rule, None), frame, srt)
        logger.info("アップロードキューに追加しました")

        self._matching_start_time = None
        self._x_power = {}  # バトル後はXPが更新されている可能性があるので、いったんリセットする
