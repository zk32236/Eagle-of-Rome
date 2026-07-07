#src/core/deciders/
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from src.core.entities.contract import Contract
from src.core.entities.figure import Figure
from src.core.game_state import GameState


class BidDecider(ABC):
    """合同竞标决策器抽象基类"""

    @abstractmethod
    def decide_tax_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float]]:
        """决定包税合同出价，返回 (骑士, 出价金额, 加价比例) 或 None"""
        pass

    @abstractmethod
    def decide_works_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float, int, int]]:
        """决定工程合同出价，返回 (骑士, 出价, 折扣率, 施工周期, 质保期) 或 None"""
        pass

    @abstractmethod
    def decide_fleet_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float]]:
        """决定舰队建造合同出价，返回 (骑士, 出价, 折扣率) 或 None"""
        pass