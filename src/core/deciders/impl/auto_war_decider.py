import random
import logging
from typing import Optional, Tuple
from src.core.deciders.war_decider import WarProposalDecider, WarVoteDecider
from src.core.entities.war import War
from src.core.game_state import GameState
from src.core.entities.entities import Faction


class AutoWarProposalDecider(WarProposalDecider):
    """自动宣战提案决策器"""

    def decide_proposal(self, war: War, state: GameState) -> Optional[Tuple[bool, int]]:
        # 从配置读取概率
        chance = state.config.get("testing.propose_war_chance", 0.5)
        random_val = random.random()
        propose = random_val < chance

        # ===== 新增 DEBUG 日志 =====
        state.log_event(
            f"WarProposalDecider: 战争 {war.name} 概率 {chance} 随机值 {random_val:.3f} 提议 {propose}",
            level=logging.DEBUG,
            extra={"war_id": war.id, "chance": chance, "random": random_val, "propose": propose}
        )

        if propose:
            # 在 min_legions 和 max_legions 之间随机
            min_leg = state.config.get("testing.min_legions", 4)
            max_leg = state.config.get("testing.max_legions", 8)
            legions = random.randint(min_leg, max_leg)

            # ===== 新增 DEBUG 日志 =====
            state.log_event(
                f"WarProposalDecider: 提议宣战 {war.name} 军团数 {legions}",
                level=logging.DEBUG,
                extra={"war_id": war.id, "legions": legions}
            )

            return True, legions
        else:
            return False, 0


class AutoWarVoteDecider(WarVoteDecider):
    """自动元老院投票决策器"""

    def decide_vote(self, war: War, faction: Faction, state: GameState) -> bool:
        chance = state.config.get("testing.other_faction_approve_chance", 0.5)
        random_val = random.random()
        result = random_val < chance

        # ===== 新增 DEBUG 日志 =====
        if state:
            state.log_event(
                f"WarVoteDecider: 战争 {war.name} 派系 {faction.name} 概率 {chance} 随机值 {random_val:.3f} 投票 {result}",
                level=logging.DEBUG,
                extra={"war_id": war.id, "faction_id": faction.id, "chance": chance, "random": random_val, "vote": result}
            )

        return result