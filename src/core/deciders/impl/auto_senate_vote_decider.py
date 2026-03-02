import random
import logging
from typing import Any
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.entities.entities import Faction
from src.core.game_state import GameState
from src.core.entities.contract import Contract
from src.core.entities.war import War


class AutoSenateVoteDecider(SenateVoteDecider):
    """自动元老院投票决策器，根据议题类型从配置读取概率"""

    def decide_vote(self, issue: Any, faction: Faction, state: GameState) -> bool:
        # 如果是土地法案
        if isinstance(issue, dict) and 'type' in issue:
            # 提案派系自动支持
            if faction.id == issue.get('proposer_faction'):
                result = True
            else:
                result = random.random() < 0.5

            # ===== 新增 DEBUG 日志 =====
            if state:
                state.log_event(
                    f"SenateVoteDecider: 土地法案 {issue['type']} 派系 {faction.name} 投票 {result}",
                    level=logging.DEBUG,
                    extra={"issue_type": "land_act", "faction_id": faction.id, "vote": result}
                )
            return result

        # 原有合同/战争逻辑
        if isinstance(issue, Contract):
            always_pass = state.config.get("testing.budget_always_pass", False)
        elif isinstance(issue, War):
            always_pass = state.config.get("testing.war_always_pass", False)
        else:
            always_pass = False

        if always_pass:
            result = True
        else:
            result = random.random() < 0.5

        # ===== 新增 DEBUG 日志 =====
        issue_type = type(issue).__name__
        if state:
            state.log_event(
                f"SenateVoteDecider: 议题 {issue_type} ID {getattr(issue, 'id', '?')} 派系 {faction.name} 投票 {result}",
                level=logging.DEBUG,
                extra={"issue_type": issue_type, "faction_id": faction.id, "vote": result}
            )

        return result