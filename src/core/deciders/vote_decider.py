# src/core/deciders/vote_decider.py
from abc import ABC, abstractmethod
from typing import List, Optional
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction
from src.core.game_state import GameState


class VoteDecider(ABC):
    """投票决策器接口"""

    @abstractmethod
    def decide_vote(self, office: str, candidates: List[Figure], faction: Faction, state: GameState) -> Optional[int]:
        """
        返回该派系投票支持的人物ID，若弃权则返回None。

        Args:
            office: 公职名称，如 "consul"
            candidates: 该公职的候选人列表
            faction: 投票的派系
            state: 游戏状态

        Returns:
            选中的人物ID，或None表示弃权
        """
        pass