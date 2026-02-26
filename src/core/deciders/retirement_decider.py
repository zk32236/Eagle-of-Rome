from abc import ABC, abstractmethod
from typing import Optional
from src.core.entities.entities import Faction

class RetirementDecider(ABC):
    """人物淘汰决策器接口"""

    @abstractmethod
    def decide_whom_to_retire(self, faction: Faction) -> Optional[int]:
        """
        决定抛弃哪个人物，返回人物ID；若无可抛弃人物，返回None。
        """
        pass