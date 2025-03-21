from typing import Optional
import datetime
from dataclasses import dataclass
from models.rate import RateBase


@dataclass
class BattleResult:
    DATETIME_FORMAT = "%Y-%m-%d %H-%M-%S"

    start: Optional[datetime.datetime] = None
    battle: Optional[str] = None
    rule: Optional[str] = None
    stage: Optional[str] = None
    result: Optional[str] = None
    kill: Optional[int] = None
    death: Optional[int] = None
    special: Optional[int] = None
    rate: Optional[RateBase] = None

    def to_list(self) -> list[str]:
        start_str = self.start.strftime(
            BattleResult.DATETIME_FORMAT) if self.start else ""
        return [start_str, self.battle or "", self.rule or "", self.stage or "", self.result or "", str(self.kill) if self.kill is not None else "", str(self.death) if self.death is not None else "", str(self.special) if self.special is not None else "", str(self.rate or "")]

    @staticmethod
    def from_list(data: list[str]) -> "BattleResult":
        start = datetime.datetime.strptime(
            data[0], BattleResult.DATETIME_FORMAT) if data[0] else None
        battle = data[1] or None
        rule = data[2] or None
        stage = data[3] or None
        result = data[4] or None
        kill = int(data[5]) if data[5] else None
        death = int(data[6]) if data[6] else None
        special = int(data[7]) if data[7] else None
        rate = RateBase.create(data[8]) if data[8] else None
        return BattleResult(start, battle, rule, stage, result, kill, death, special, rate)
