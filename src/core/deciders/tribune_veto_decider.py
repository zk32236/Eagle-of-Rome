#src/core/deciders/
from abc import ABC, abstractmethod
from typing import Any
from src.core.game_state import GameState


class TribuneVetoDecider(ABC):
    """保民官否决决策器接口"""

    @abstractmethod
    def decide_veto(self, issue: Any, tribune_id: int, state: GameState) -> bool:
        """
        决定是否否决某议题。
        issue: 议题对象，可以是宣战提案、合同、土地法案等。
        tribune_id: 保民官的人物ID
        返回 True 表示否决，False 表示不否决。
        """
        pass