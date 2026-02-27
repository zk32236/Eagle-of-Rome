import random
from typing import List
from src.core.deciders.budget_decider import BudgetDecider
from src.core.entities.contract import Contract, ContractType
from src.core.game_state import GameState

class AutoBudgetDecider(BudgetDecider):
    """自动预算决策器：随机选取部分合同，随机表决；可配置为总是通过"""

    def decide_proposals(self, pending_contracts: List[Contract], state: GameState) -> List[Contract]:
        """
        从待决合同中选取本次提交表决的合同列表。
        包税合同：若所在行省已有非延期的活跃包税合同，则禁止提交表决。
        工程合同：无限制。
        """
        # 过滤掉不允许提交的包税合同
        filtered = []
        for contract in pending_contracts:
            if contract.contract_type == ContractType.TAX_FARMING:
                province = state.get_province(contract.province_id)
                if province and province.tax_contract_id is not None:
                    # 获取活跃合同
                    active_contract = state.get_contract(province.tax_contract_id)
                    # 如果活跃合同存在且不是延期合同，则跳过
                    if active_contract and not getattr(active_contract, 'is_extended', False):
                        continue
            # 工程合同直接加入，包税合同通过检查的也加入
            filtered.append(contract)

        if not filtered:
            return []

        # 如果开启了总是通过，返回所有过滤后的合同
        if state.config.get("testing.budget_always_pass", False):
            return filtered

        # 否则随机选择 1 到所有合同数之间的数量
        num = random.randint(1, len(filtered))
        return random.sample(filtered, num)

    def decide_vote(self, contract: Contract, state: GameState) -> bool:
        """
        对单个合同进行表决。
        如果开启了总是通过，则返回 True；否则随机：50% 通过。
        """
        if state.config.get("testing.budget_always_pass", False):
            return True
        return random.random() < 0.5