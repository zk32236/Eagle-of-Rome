from abc import ABC, abstractmethod
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class WarTakeoverDecider(ABC):
    """战争接管决策器接口"""

    @abstractmethod
    def decide_takeover(self, war: War, new_consul: Figure, old_commander: Figure, state: GameState) -> bool:
        """
        决定新执政官是否接管旧战争。
        返回 True 表示接管，False 表示不接管。
        """
        pass