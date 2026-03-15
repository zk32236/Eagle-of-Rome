from src.core.deciders.recruitment_decider import RecruitmentDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from typing import List, Dict

class ManualRecruitmentDecider(RecruitmentDecider):
    """手动招募决策器（骨架）"""
    def decide_bids(
        self,
        faction: Faction,
        available_figures: List[Figure],
        vacancies: int,
        state: GameState
    ) -> Dict[int, int]:
        print("手动招募决策器被调用（当前为骨架）")
        return {}