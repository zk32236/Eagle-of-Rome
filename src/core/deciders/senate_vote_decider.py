#src/core/deciders/
from abc import ABC, abstractmethod
from typing import Any
from src.core.entities.entities import Faction
from src.core.game_state import GameState

class SenateVoteDecider(ABC):
    """元老院投票决策器接口（通用）"""

    @abstractmethod
    def decide_vote(self, issue: Any, faction: Faction, state: GameState) -> bool:
        """
        根据议题和派系决定是否支持。
        issue: 议题对象，可以是 Contract、War 或其他需要投票的实体。
        """
        pass