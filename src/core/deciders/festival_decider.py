#src/core/deciders/
from abc import ABC, abstractmethod
from typing import List, Dict
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class FestivalDecider(ABC):
    """庆典决策器接口：决定派系中哪些候选人举办庆典，花费多少"""

    @abstractmethod
    def decide_festivals(self, faction: Faction, candidates: List[Figure], state: GameState) -> Dict[int, int]:
        """
        返回该派系中人物举办庆典的花费映射：{figure_id: amount}
        参数：
            faction: 当前派系
            candidates: 该派系在当前回合所有官职中的候选人列表（已去重）
            state: 游戏状态
        返回：
            一个字典，键为人物ID，值为花费金额。可为空字典（表示不举办）。
        """
        pass