import logging
import queue
import json
import threading
import datetime
from typing import Optional, List, Dict, Any, Union, TypedDict

from vosk import Model, KaldiRecognizer
import srt
import sounddevice as sd

logger = logging.getLogger(__name__)


class Device(TypedDict):
    index: int
    name: str
    max_input_channels: int
    default_samplerate: float


class Transcriber:
    def __init__(self, device: Union[int, str], model_path: str, sample_rate: int = 16000, block_size: int = 8000, gap_threshold: float = 1.0, custom_dictionary: Optional[List[str]] = None) -> None:
        """
        :param device: マイクのデバイスインデックス(int)、またはデバイス名(str)
        :param model_path: Vosk のモデルディレクトリのパス
        :param sample_rate: 録音サンプルレート (例: 16000)
        :param block_size: １回の読み込みで取得するフレーム数
        :param gap_threshold: 単語間の無音がこの秒数以上ならセグメントの区切りとする
        :param custom_dictionary: 独自に定義した辞書 (例: ["word1", "word2", ...])
        """
        self.device_index = self._find_device_index(device)
        self.model = Model(model_path)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.gap_threshold = gap_threshold
        self.custom_dictionary = json.dumps(
            custom_dictionary) if custom_dictionary else None

        self._recognizer: Optional[KaldiRecognizer] = None
        self._queue: queue.Queue = queue.Queue()
        self._segments: List[List[Dict[str, Any]]] = []  # 各セグメントの型定義
        self._running: bool = False
        self._stream: Any = None
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def get_audio_devices() -> List[Device]:
        """
        使用可能なオーディオデバイスを一覧表示する
        """
        devices: List[Device] = []
        for i, device in enumerate(sd.query_devices()):
            if "BOYA" in device["name"]:
                pass
            devices.append({
                "index": device["index"],
                "name": device["name"],
                "max_input_channels": device["max_input_channels"],
                "default_samplerate": device["default_samplerate"]
            })
        return devices

    def _find_device_index(self, device: Union[int, str]) -> Optional[int]:
        """
        デバイスインデックスを取得する
        """
        if isinstance(device, int):
            return device
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if device in dev["name"]:
                logger.info(f"Device {i}: {dev['name']}")
                return i
        return None

    def _process_result(self, result_json: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
        """
        Vosk の認識結果 JSON から単語情報（"result" リスト）を取得し、
        単語間の間隔が gap_threshold 以上のときにセグメント分割を行う。
        """
        if "result" not in result_json:
            return []
        words: List[Dict[str, Any]] = result_json["result"]
        segments: List[List[Dict[str, Any]]] = []
        if not words:
            return segments
        current_segment = [words[0]]
        for w in words[1:]:
            # 前の単語の終了時刻と今回の開始時刻の差が gap_threshold 以上なら区切る
            if w["start"] - current_segment[-1]["end"] > self.gap_threshold:
                segments.append(current_segment)
                current_segment = [w]
            else:
                current_segment.append(w)
        if current_segment:
            segments.append(current_segment)
        return segments

    def _segments_to_srt(self, segments: List[List[Dict[str, Any]]]) -> str:
        """
        srt パッケージを使用して、字幕のリストを SRT フォーマットに変換する
        """
        subtitles: List[srt.Subtitle] = []
        for index, seg in enumerate(segments, start=1):
            start_time = datetime.timedelta(seconds=seg[0]["start"])
            end_time = datetime.timedelta(seconds=seg[-1]["end"])
            text = "".join(word["word"] for word in seg)
            subtitles.append(srt.Subtitle(index, start_time, end_time, text))

        return srt.compose(subtitles)

    def _audio_callback(self, indata: Any, frames: int, time_info: Dict[str, Any], status: Any) -> None:
        if status:
            logger.debug(f"Error: {status}")
        self._queue.put(bytes(indata))

    def _recognition_loop(self) -> None:
        """
        別スレッドで回す認識ループ。キューからデータを取得し、
        Vosk で音声認識を行い、結果から字幕用セグメントを抽出する。
        """
        while self._running:
            if self._queue.empty():
                continue
            data = self._queue.get(timeout=0.1)

            if self._recognizer.AcceptWaveform(data):
                result_str = self._recognizer.Result()
                result = json.loads(result_str)
                segments = self._process_result(result)
                self._segments.extend(segments)
                try:
                    if result.get("text", ""):
                        logger.info(f"音声入力:{result.get("text", "")}")
                        print(f"音声入力:{result.get("text", "")}")
                except Exception as e:
                    logger.error(f"音声入力エラー: {e}")

        # ループ終了後、最終結果をフラッシュする
        final_result_str = self._recognizer.FinalResult()
        final_result = json.loads(final_result_str)
        segments = self._process_result(final_result)
        self._segments.extend(segments)

    def start_recognition(self) -> None:
        """
        音声認識処理を開始する。マイクからの入力を取得し、別スレッドで認識ループを実行する。
        """
        if self._running:
            logger.debug("既に音声認識中です")
            return
        self._running = True
        self._segments = []
        self._queue.queue.clear()

        if self.custom_dictionary:
            self._recognizer = KaldiRecognizer(
                self.model, self.sample_rate, self.custom_dictionary)
        else:
            self._recognizer = KaldiRecognizer(self.model, self.sample_rate)
        self._recognizer.SetWords(True)  # 単語ごとの開始・終了タイムスタンプを取得する

        self._stream = sd.RawInputStream(samplerate=self.sample_rate,
                                         blocksize=self.block_size,
                                         dtype='int16',
                                         channels=1,
                                         device=self.device_index,
                                         callback=self._audio_callback)

        self._stream.start()
        self._thread = threading.Thread(target=self._recognition_loop)
        self._thread.start()
        logger.info("音声認識を開始しました")

    def stop_recognition(self) -> None:
        """
        音声認識処理を停止する。マイクストリームを閉じ、認識ループのスレッドを終了する。
        """
        if not self._running:
            logger.debug("音声認識中ではありません")
            return
        self._running = False
        self._stream.stop()
        self._stream.close()
        self._thread.join()
        logger.info("音声認識を停止しました")

    def get_srt(self) -> str:
        """
        これまでに取得した認識結果から SRT 形式のテキストを返す
        """
        return self._segments_to_srt(self._segments)

    def save_srt(self, filename: str = "output.srt", encoding: str = "utf-8") -> None:
        """
        SRT テキストをファイルに保存する
        """
        srt_content = self.get_srt()
        with open(filename, "w", encoding=encoding) as f:
            f.write(srt_content)
        logger.info(f"SRT ファイルを保存しました: {filename}")


# 利用例
if __name__ == "__main__":
    devices = Transcriber.get_audio_devices()
    print("利用可能なオーディオデバイス:")
    for device in devices:
        print(
            f"  {device['index']}: {device['name']} ({device['max_input_channels']} channels) {device['default_samplerate']} Hz")

    # デバイスインデックスを入力する
    try:
        device_index = int(input("使用するデバイスのインデックスを入力してください: "))
    except ValueError:
        print("有効な数値を入力してください。")
        exit(1)

    recognizer = Transcriber(model_path="vosk_model",
                             device=device_index)
    while True:
        try:
            recognizer.start_recognition()
            print("音声認識中です。終了するには Enter キーを押してください。")
            input()  # Enter キーが押されるまで認識継続
        except KeyboardInterrupt:
            pass
        finally:
            recognizer.stop_recognition()
            recognizer.save_srt("output.srt")
            print("音声認識を終了しました")
