from abc import ABC, abstractmethod
import re
from typing import Literal, Union


class RateBase(ABC):
    def __init__(self):
        pass

    @property
    @abstractmethod
    def label(self) -> str:
        pass

    @abstractmethod
    def compare_rate(self, other: "RateBase") -> int:
        """
        self と other を比較し、selfが小さい場合は -1、
        同じ場合は 0、大きい場合は 1 を返す。
        """
        pass

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RateBase):
            return NotImplemented
        return self.compare_rate(other) == 0

    def __lt__(self, other: "RateBase") -> bool:
        if not isinstance(other, RateBase):
            return NotImplemented
        return self.compare_rate(other) == -1

    @abstractmethod
    def __str__(self) -> str:
        pass

    @abstractmethod
    def short_str(self) -> str:
        pass

    @classmethod
    def create(cls, value: Union[float, int, str]) -> "RateBase":
        """
        引数の型に応じてXPまたはUdemaeのインスタンスを生成します。

        数値（int, float）の場合はXP、文字列の場合はUdemaeを生成します。
        """
        if isinstance(value, (int, float)):
            return XP(float(value))
        elif isinstance(value, str):
            try:
                # 数値として解釈できる文字列の場合はXPとして生成
                xp = float(value)
                return XP(xp)
            except:
                return Udemae(value)
        else:
            raise ValueError("XPまたはUdemaeのインスタンスを生成できませんでした。")


class XP(RateBase):
    def __init__(self, xp: float):
        self.xp = xp

    @property
    def label(self) -> str:
        return "XP"

    @property
    def value(self) -> float:
        return self.xp

    def compare_rate(self, other: "RateBase") -> int:
        if not isinstance(other, XP):
            raise TypeError("XP 型同士でのみ比較可能です")
        if self.xp < other.xp:
            return -1
        elif self.xp > other.xp:
            return 1
        else:
            return 0

    def __str__(self) -> str:
        return str(self.xp)

    def short_str(self) -> str:
        return str(int(self.xp) // 100)


class Udemae(RateBase):
    Rank = Literal["C-", "C", "C+", "B-",
                   "B", "B+", "A-", "A", "A+", "S", "S+"]
    RANK_ORDER = {
        "C-": 0, "C": 1, "C+": 2,
        "B-": 3, "B": 4, "B+": 5,
        "A-": 6, "A": 7, "A+": 8,
        "S": 9, "S+": 10
    }

    def __init__(self, udemae: Union[Rank, str]):
        if udemae not in self.RANK_ORDER:
            raise ValueError("無効な評価ランクが指定されています")
        self.udemae = udemae

    @property
    def label(self) -> str:
        return "ウデマエ"

    @property
    def value(self) -> str:
        return self.udemae

    def compare_rate(self, other: "RateBase") -> int:
        if not isinstance(other, Udemae):
            raise TypeError("Udemae 型同士でのみ比較可能です")
        self_rank = self.RANK_ORDER.get(self.udemae)
        other_rank = self.RANK_ORDER.get(other.udemae)
        if self_rank is None or other_rank is None:
            raise ValueError("無効な評価ランクが指定されています")
        if self_rank < other_rank:
            return -1
        elif self_rank > other_rank:
            return 1
        else:
            return 0

    def __str__(self) -> str:
        return self.udemae

    def short_str(self) -> str:
        return self.udemae
