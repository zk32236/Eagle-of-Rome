import random
from typing import Any
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.entities.entities import Faction
from src.core.game_state import GameState
from src.core.entities.contract import Contract
from src.core.entities.war import War

class AutoSenateVoteDecider(SenateVoteDecider):
    """自动元老院投票决策器，根据议题类型从配置读取概率"""

    def decide_vote(self, issue: Any, faction: Faction, state: GameState) -> bool:
        config = state.config

        if isinstance(issue, Contract):
            always_pass = config.get("testing.budget_always_pass", False)
        elif isinstance(issue, War):
            always_pass = config.get("testing.war_always_pass", False)
        else:
            always_pass = False

        if always_pass:
            return True

        # 没有强制通过时，随机决定（50% 概率）
        return random.random() < 0.5