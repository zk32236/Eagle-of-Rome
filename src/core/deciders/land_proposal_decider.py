from abc import ABC, abstractmethod
from typing import Optional, Tuple
from src.core.game_state import GameState

class LandProposalDecider(ABC):
    """土地法案提案决策器接口"""

    @abstractmethod
    def decide_proposal(self, faction_id: str, state: GameState) -> Optional[Tuple[str, float]]:
        """
        决定是否提出土地法案。
        返回 (法案类型, 比例) 或 None。
        法案类型: 'distribution' 平民分地, 'sale' 贵族买地
        """
        pass