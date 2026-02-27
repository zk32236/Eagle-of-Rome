from abc import ABC, abstractmethod
from typing import List
from src.core.entities.contract import Contract
from src.core.game_state import GameState

class BudgetDecider(ABC):
    """预算决策器接口：决定将哪些合同提交表决，以及每个合同的表决结果"""

    @abstractmethod
    def decide_proposals(self, pending_contracts: List[Contract], state: GameState) -> List[Contract]:
        """从待决合同中选取本次提交表决的合同列表"""
        pass

    @abstractmethod
    def decide_vote(self, contract: Contract, state: GameState) -> bool:
        """对单个合同进行表决，返回 True 表示通过，False 表示否决"""
        pass