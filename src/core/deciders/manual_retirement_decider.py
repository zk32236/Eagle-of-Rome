from src.core.deciders.retirement_decider import RetirementDecider
from src.core.entities.entities import Faction
from src.core.game_state import GameState
from typing import Optional

class ManualRetirementDecider(RetirementDecider):
    """手动淘汰决策器（骨架）"""
    def decide_whom_to_retire(self, faction: Faction, state: GameState) -> Optional[int]:
        print("手动淘汰决策器被调用（当前为骨架）")
        return None