#src/core/deciders/
from abc import ABC, abstractmethod
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class TriumphDecider(ABC):
    """凯旋审批决策器接口"""

    @abstractmethod
    def decide_triumph(self, war: War, commander: Figure, state: GameState) -> bool:
        """
        决定是否批准凯旋。
        返回 True 表示批准，False 表示否决。
        """
        pass