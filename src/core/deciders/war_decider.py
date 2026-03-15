#src/core/deciders/
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from src.core.entities.war import War
from src.core.game_state import GameState
from src.core.entities.entities import Faction

class WarProposalDecider(ABC):
    """宣战提案决策器接口"""
    @abstractmethod
    def decide_proposal(self, war: War, state: GameState) -> Optional[Tuple[bool, int]]:
        """
        返回 (是否提议宣战, 提议的军团数量)
        若返回 None 或 (False, 0) 表示不提议。
        """
        pass

class WarVoteDecider(ABC):
    """元老院投票决策器接口"""
    @abstractmethod
    def decide_vote(self, war: War, faction: Faction, state: GameState) -> bool:
        """
        返回该派系是否支持宣战（True 支持，False 反对）
        执政官派系由上层逻辑直接处理，本接口用于其他派系。
        """
        pass