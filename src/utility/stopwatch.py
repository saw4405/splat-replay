import time
from typing import Optional


class StopWatch:
    """StopWatchクラスは、計測開始、停止、一時停止、再開機能を持つストップウォッチを提供します."""

    def __init__(self):
        """
        初期化メソッド.
        ストップウォッチの内部状態（開始時間、経過時間、一時停止状態など）を初期化します.
        """
        self._start_time: Optional[float] = None
        self._elapsed: float = 0.0
        self._is_running: bool = False
        self._is_paused: bool = False

    def reset(self):
        """
        ストップウォッチをリセットします.
        内部状態を初期化し、経過時間をゼロにします.
        """
        self._start_time = None
        self._elapsed = 0.0
        self._is_running = False
        self._is_paused = False

    def start(self):
        """
        ストップウォッチを開始します.
        まだ開始されていない場合、開始時刻を記録し、経過時間をリセットします.
        """
        if not self._is_running:
            self._start_time = time.perf_counter()
            self._elapsed = 0.0
            self._is_running = True
            self._is_paused = False

    def pause(self):
        """
        ストップウォッチを一時停止します.
        作動中でかつ一時停止中でない場合、現在の経過時間を加算し一時停止状態にします.
        """
        if self._is_running and not self._is_paused and self._start_time is not None:
            self._elapsed += time.perf_counter() - self._start_time
            self._is_paused = True
            self._start_time = None

    @property
    def is_paused(self) -> bool:
        """
        ストップウォッチが一時停止中かどうかを返します.
        """
        return self._is_paused

    def resume(self):
        """
        一時停止状態のストップウォッチを再開します.
        """
        if self._is_running and self._is_paused:
            self._start_time = time.perf_counter()
            self._is_paused = False

    def stop(self) -> float:
        """
        ストップウォッチを停止し、総経過時間を返します.
        停止前に一時停止でない場合、最後の経過時間を加算します.
        """
        if self._is_running:
            if not self._is_paused and self._start_time is not None:
                self._elapsed += time.perf_counter() - self._start_time
            self._is_running = False
            self._is_paused = False
        return self._elapsed

    def elapsed(self) -> float:
        """
        現在の経過時間を返します.
        作動中の場合、実際の経過時間を計算して返却します.
        """
        if self._is_running and not self._is_paused and self._start_time is not None:
            return self._elapsed + (time.perf_counter() - self._start_time)
        return self._elapsed
