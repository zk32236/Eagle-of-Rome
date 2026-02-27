import random
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
        if random.random() < chance:
            # 在 min_legions 和 max_legions 之间随机
            min_leg = state.config.get("testing.min_legions", 4)
            max_leg = state.config.get("testing.max_legions", 8)
            legions = random.randint(min_leg, max_leg)
            return True, legions
        else:
            return False, 0

class AutoWarVoteDecider(WarVoteDecider):
    """自动元老院投票决策器"""

    def decide_vote(self, war: War, faction: Faction, state: GameState) -> bool:
        chance = state.config.get("testing.other_faction_approve_chance", 0.5)
        return random.random() < chance