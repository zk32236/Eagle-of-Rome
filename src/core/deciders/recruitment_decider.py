from abc import ABC, abstractmethod
from typing import List, Dict
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class RecruitmentDecider(ABC):
    """招募决策器接口：决定派系对广场中哪些人物出价，以及出价多少"""

    @abstractmethod
    def decide_bids(self, faction: Faction, available_figures: List[Figure],
                    vacancies: int, state: GameState) -> Dict[int, int]:
        """
        返回该派系对人物的出价映射：{figure_id: bid_amount}
        参数：
            faction: 当前派系
            available_figures: 广场中的所有可用人物列表
            vacancies: 派系当前空缺数（成员上限 - 现有成员数）
            state: 游戏状态，可用于获取配置或检查财富
        返回：
            一个字典，键为人物ID，值为出价金额。可为空字典（表示不出价）。
        """
        pass