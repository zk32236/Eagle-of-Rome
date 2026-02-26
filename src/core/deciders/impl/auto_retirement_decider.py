# src/core/deciders/impl/auto_retirement_decider.py
import random
from typing import Optional
from src.core.deciders.retirement_decider import RetirementDecider
from src.core.entities.entities import Faction
from src.core.game_state import GameState


class AutoRetirementDecider(RetirementDecider):
    """自动随机淘汰人物决策器"""

    def __init__(self, state: GameState):
        self.state = state

    def decide_whom_to_retire(self, faction: Faction) -> Optional[int]:
        # 获取派系所有存活成员
        members = faction.get_members(self.state)
        # 筛选条件：非领袖、无现任公职（允许ex-xxx）、无活跃合同
        eligible = [
            m for m in members
            if not m.is_faction_leader
            and not (m.office and not m.office.startswith("ex-"))
            and not m.has_active_contract
        ]
        if not eligible:
            return None
        chosen = random.choice(eligible)
        return chosen.id