# src/core/deciders/impl/auto_senate_vote_decider.py
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
        # ========== 优先处理：提案发起派系自动支持 ==========
        if isinstance(issue, dict) and "proposer_faction" in issue:
            if faction.id == issue["proposer_faction"]:
                state.log_event(
                    f"SenateVoteDecider: 派系 {faction.name} 支持自己的提案",
                    level=logging.DEBUG,
                    extra={"faction_id": faction.id, "proposer_faction": issue["proposer_faction"]}
                )
                return True

        # ========== 工程合同国库不足强制否决（兼容字典和对象） ==========
        contract = None
        if isinstance(issue, Contract):
            contract = issue
        elif isinstance(issue, dict) and issue.get("type") in ("budget", "contract"):
            contract = issue.get("contract")

        if contract and contract.contract_type == ContractType.PUBLIC_WORKS:
            if state.treasury < 100:
                state.log_event(
                    f"SenateVoteDecider: 工程合同 {contract.name} 因国库低于100被否决",
                    level=logging.DEBUG,
                    extra={"issue_type": "contract", "contract_id": contract.id, "reason": "treasury < 100"}
                )
                return False
            if state.treasury < contract.base_cost:
                state.log_event(
                    f"SenateVoteDecider: 工程合同 {contract.name} 因国库不足预算被否决",
                    level=logging.DEBUG,
                    extra={"issue_type": "contract", "contract_id": contract.id, "reason": "treasury < base_cost"}
                )
                return False

        # ========== 处理字典类型的土地法案（非本派系提案） ==========
        if isinstance(issue, dict) and 'type' in issue:
            # 提案派系已在前面处理，此处直接随机
            result = random.random() < 0.5
            state.log_event(
                f"SenateVoteDecider: 土地法案 {issue['type']} 派系 {faction.name} 投票 {result}",
                level=logging.DEBUG,
                extra={"issue_type": "land_act", "faction_id": faction.id, "vote": result}
            )
            return result

        # ========== 原有合同/战争逻辑（对象类型） ==========
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
        state.log_event(
            f"SenateVoteDecider: 议题 {issue_type} ID {getattr(issue, 'id', '?')} 派系 {faction.name} 投票 {result}",
            level=logging.DEBUG,
            extra={"issue_type": issue_type, "faction_id": faction.id, "vote": result}
        )
        return result