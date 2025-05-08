import os
import logging
import time
import datetime
from typing import Dict, Callable, Optional
from enum import Enum

import numpy as np

from wrapper.obs import Obs
from uploader import Uploader
from wrapper.capture import Capture
from analyzer import Analyzer
from transcriber import Transcriber
from battle_result import BattleResult
from utility.graceful_thread import GracefulThread
import utility.os as os_utility

logger = logging.getLogger(__name__)


class RecordStatus(Enum):
    OFF = 1
    WAIT = 2
    RECORD = 3
    PAUSE = 4


class Recorder(GracefulThread):
    def __init__(self, path: Optional[str] = None):
        super().__init__()

        # 通常は録画モードで、ファイルが指定されている場合はファイルモード(デバッグ)とする
        self.is_recording_mode = path is None
        logger.info("録画モード" if self.is_recording_mode else "ファイルモード")

        self._obs = self._initialize_obs()
        self._capture = self._initialize_capture(path)
        self._analyzer = Analyzer()
        self._transcriber = self._initialize_transcriber()

        self._battle_result = BattleResult()
        self._record_start_time = time.time()
        self._last_power_check_time = 0
        self._power_off_count = 0
        self._should_resume_recording: Optional[Callable[[
            np.ndarray], bool]] = None

        self._power_off_callback: Optional[Callable[[], None]] = None

    def _on_disconnect_obs(self, _):
        logger.error("OBSとの接続が切れたので、Recorderを停止します")
        self.stop()

    def _initialize_obs(self) -> Optional[Obs]:
        if not self.is_recording_mode:
            return None

        path = os.environ["OBS_PATH"]
        host = os.environ["OBS_WS_HOST"]
        port = int(os.environ["OBS_WS_PORT"])
        password = os.environ["OBS_WS_PASSWORD"]
        obs = Obs(path, host, port, password, self._on_disconnect_obs)

        # バトル開始等の画像判定への入力として仮想カメラを起動する
        if obs.start_virtual_cam().is_err():
            raise Exception("仮想カメラの起動に失敗しました")
        return obs

    def _initialize_capture(self, path: Optional[str]) -> Capture:
        index = int(os.environ["CAPTURE_DEVICE_INDEX"])
        width = int(os.environ["CAPTURE_WIDTH"])
        height = int(os.environ["CAPTURE_HEIGHT"])
        result = Capture.create(index if not path else path, width, height)
        if result.is_err():
            raise Exception(
                "キャプチャーの初期化に失敗しました。\nCAPTURE_DEVICE_INDEXの設定が合っているか確認してください。")
        return result.unwrap()

    def _load_glossary(self) -> list[str]:
        glossary_path = os.path.join(os.getcwd(), "assets", "glossary.txt")
        try:
            with open(glossary_path, encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception as e:
            logger.error(f"用語集の読み込みに失敗しました: {e}")
            return []

    def _initialize_transcriber(self) -> Optional[Transcriber]:
        if not self.is_recording_mode:
            return None

        mic_device = os.environ.get("MIC_DEVICE", "")
        if len(mic_device) == 0:
            logger.info("マイクデバイスが設定されていないため、音声認識機能は無効化されます")
            return None

        if Transcriber.find_microphone(mic_device) is None:
            logger.error(f"指定されたマイクデバイス({mic_device})が見つからないため、音声認識機能は無効化されます")
            return None

        dictionary = self._load_glossary()
        return Transcriber(mic_device, custom_dictionary=dictionary)

    def register_power_off_callback(self, callback: Callable[[], None]):
        self._power_off_callback = callback

    def run(self):
        logger.info("Recorderを起動します")
        try:
            status = RecordStatus.OFF
            while not self.stopped:
                result = self._capture.read()
                if result.is_err():
                    raise Exception(
                        "フレームの読み込みに失敗しました。\n他のアプリケーションがカメラを使用していないか確認してください。")
                frame, elapsed_time = result.unwrap()
                if not self.is_recording_mode:
                    self._capture.show(frame, 0.5)

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
            if self._obs:
                self._obs.close()

    def _check_switch_power_status(self, frame: np.ndarray, current_status: RecordStatus) -> RecordStatus:
        # Switchの電源状態を確認する (処理負荷を下げるため10秒毎に確認する)
        if time.time() - self._last_power_check_time < 10:
            return current_status
        self._last_power_check_time = time.time()

        if self._analyzer.power_off(frame):
            self._power_off_count += 1
        else:
            self._power_off_count = 0

        if self._power_off_count >= 3:
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
            if self._obs and self._obs.start_virtual_cam().is_err():
                logger.warning("仮想カメラの再起動に失敗しました")
                self.stop()
            return RecordStatus.OFF

        # 電源OFF→ON
        if current_status == RecordStatus.OFF:
            logger.info("Switchが起動しました")
            return RecordStatus.WAIT

        # 電源ON→ON
        return current_status

    def _handle_wait_status(self, frame: np.ndarray) -> RecordStatus:

        # スケジュール変更を検知したら、状態リセットする
        if (self._battle_result.start is not None or self._battle_result.rate is not None) and self._analyzer.change_schedule(frame):
            logger.info("スケジュール変更を検知しました")
            self._battle_result = BattleResult()
            return RecordStatus.WAIT

        if self._battle_result.start is None:
            # マッチ選択時のレート(XP/ウデマエ)を記録する
            if (rate := self._analyzer.rate(frame)) is not None and self._battle_result.rate != rate:
                self._battle_result.rate = rate
                logger.info(f"{rate.label}: {rate}")

            # 動画のスケジュール分けを正確にできるよう、マッチング開始時の日時を記録しておく
            if self._analyzer.matching_start(frame):
                self._battle_result.start = datetime.datetime.now()
                logger.info("マッチング開始を検知しました")

            # ファイルモードの場合、マッチング中が録画されていない場合があるため、マッチング開始していなくてもバトル開始を監視する
            if self.is_recording_mode:
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
        if self._battle_result.result is None:
            # Finish!表示中は録画を一時停止する
            if self._analyzer.battle_finish(frame):
                logger.info("Finish!表示を検知したため、録画を一時停止します")
                self._should_resume_recording = lambda frame: not self._analyzer.battle_result_latter_half(
                    frame)
                self._pause_record()
                return RecordStatus.PAUSE

            self._battle_result.result = self._analyzer.battle_result(frame)
            if self._battle_result.result:
                logger.info(f"バトル結果: {self._battle_result.result}")
            return RecordStatus.RECORD

        # ローディング中は録画を一時停止する
        if self._analyzer.loading(frame):
            logger.info("ローディング中を検知したため、録画を一時停止します")
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
        if self._obs:
            self._obs.start_record()
        if self._transcriber:
            logger.info("字幕起こしを開始します")
            self._transcriber.start()
        self._record_start_time = time.time()

    def _pause_record(self):
        logger.info("録画を一時停止します")
        if self._obs:
            self._obs.pause_record()

    def _resume_record(self):
        logger.info("録画を再開します")
        if self._obs:
            self._obs.resume_record()

    def _cancel_record(self):
        logger.info("録画を中止します")
        try:
            if self._transcriber:
                logger.info("字幕起こしを停止します")
                self._transcriber.stop()

            if self._obs:
                result = self._obs.stop_record()
                if result.is_err():
                    logger.error(f"録画の停止に失敗しました: {result.unwrap_err()}")
                    return
                path = result.unwrap()
                if os_utility.remove_file(path).is_err():
                    logger.warning(f"中断された録画ファイルの削除に失敗しました")
        finally:
            self._battle_result = BattleResult()

    def _stop_record(self, frame: np.ndarray):
        logger.info("録画を停止します")
        try:
            srt = None
            if self._transcriber:
                logger.info("字幕起こしを停止します")
                self._transcriber.stop()
                srt = self._transcriber.get_srt()

            if self._obs:
                result = self._obs.stop_record()
                if result.is_err():
                    logger.error(f"録画の停止に失敗しました: {result.unwrap_err()}")
                    return
                path = result.unwrap()

                # マッチ・ルールを分析する
                if self._battle_result.start is None:
                    self._battle_result.start = Obs.extract_start_datetime(path) or \
                        datetime.datetime.now()
                self._battle_result.battle = self._analyzer.match_name(frame)
                logger.info(f"マッチ: {self._battle_result.battle}")
                self._battle_result.rule = self._analyzer.rule_name(frame)
                logger.info(f"ルール: {self._battle_result.rule}")
                self._battle_result.stage = self._analyzer.stage_name(frame)
                logger.info(f"ステージ: {self._battle_result.stage}")
                if (kill_record := self._analyzer.kill_record(frame)) is not None:
                    self._battle_result.kill, self._battle_result.death, self._battle_result.special = kill_record
                logger.info(f"キルレ: {kill_record}")

                # アップロードキューに追加
                Uploader.queue(path, self._battle_result, frame, srt)
                logger.info("アップロードキューに追加しました")
        finally:
            self._battle_result = BattleResult()
