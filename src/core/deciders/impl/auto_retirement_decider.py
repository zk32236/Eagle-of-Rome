import random
import logging
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

        # ===== 新增 DEBUG 日志 =====
        if self.state:
            self.state.log_event(
                f"RetirementDecider: 派系 {faction.name} 成员 {len(members)} 人，符合淘汰条件 {len(eligible)} 人",
                level=logging.DEBUG,
                extra={"faction_id": faction.id, "member_count": len(members), "eligible_count": len(eligible)}
            )

        if not eligible:
            return None

        chosen = random.choice(eligible)
        # ===== 新增 DEBUG 日志 =====
        if self.state:
            self.state.log_event(
                f"RetirementDecider: 派系 {faction.name} 淘汰人物 {chosen.name}(ID:{chosen.id})",
                level=logging.DEBUG,
                extra={"faction_id": faction.id, "figure_id": chosen.id}
            )
            return chosen.id