#src/core/deciders/
from abc import ABC, abstractmethod
from typing import List
from src.core.entities.fleet import Fleet
from src.core.game_state import GameState

class FleetDisbandDecider(ABC):
    """舰队解散决策器接口"""

    @abstractmethod
    def should_disband_fleet(self, fleet: Fleet, state: GameState) -> bool:
        """
        判断是否应解散指定舰队。
        返回 True 表示解散，False 表示保留。
        """
        pass