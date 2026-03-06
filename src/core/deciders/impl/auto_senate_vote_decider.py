import random
import logging
from typing import Any
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.entities.entities import Faction
from src.core.game_state import GameState
from src.core.entities.contract import Contract, ContractType
from src.core.entities.war import War


class AutoSenateVoteDecider(SenateVoteDecider):
    """自动元老院投票决策器，根据议题类型从配置读取概率"""

    def decide_vote(self, issue: Any, faction: Faction, state: GameState) -> bool:
        # ---------- 新增：国库资金不足时的强制否决规则 ----------
        if isinstance(issue, Contract) and issue.contract_type == ContractType.PUBLIC_WORKS:
            # 如果国库低于 100 Talents，直接否决所有工程合同
            if state.treasury < 100:
                result = False
                state.log_event(
                    f"SenateVoteDecider: 工程合同 {issue.name} 因国库低于100被否决",
                    level=logging.DEBUG,
                    extra={"issue_type": "contract", "contract_id": issue.id, "reason": "treasury < 100"}
                )
                return result
            # 如果国库低于该合同的预算，直接否决
            if state.treasury < issue.base_cost:
                result = False
                state.log_event(
                    f"SenateVoteDecider: 工程合同 {issue.name} 因国库不足预算被否决",
                    level=logging.DEBUG,
                    extra={"issue_type": "contract", "contract_id": issue.id, "reason": "treasury < base_cost"}
                )
                return result
        # --------------------------------------------------------

        # 如果是土地法案
        if isinstance(issue, dict) and 'type' in issue:
            # 提案派系自动支持
            if faction.id == issue.get('proposer_faction'):
                result = True
            else:
                result = random.random() < 0.5

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

        issue_type = type(issue).__name__
        if state:
            state.log_event(
                f"SenateVoteDecider: 议题 {issue_type} ID {getattr(issue, 'id', '?')} 派系 {faction.name} 投票 {result}",
                level=logging.DEBUG,
                extra={"issue_type": issue_type, "faction_id": faction.id, "vote": result}
            )

        return result