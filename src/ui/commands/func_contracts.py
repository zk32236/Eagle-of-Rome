# src/ui/commands/func_contracts.py
"""
合同功能命令：显示合同状态、投票授予包税合同
"""

from typing import List, TYPE_CHECKING, Optional
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractType, ContractStatus
import src.api.contract_api as contract_api

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ContractsCommand(Command):
    name = "contracts"
    aliases = []
    description = "显示所有合同状态（待决、执行中、已完成）"

    def execute(self, args: List[str]) -> bool:
        result = contract_api.get_contracts_status(self.state)
        print(result["message"])
        return result["success"]


class VoteCommand(Command):
    """投票授予包税合同"""
    name = "vote"
    aliases = []
    description = "投票授予包税合同，用法: vote contract <合同ID>"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _input_int(self, prompt: str, min_val: int = 1, max_val: Optional[int] = None) -> Optional[int]:
        """获取整数输入"""
        try:
            val = int(input(prompt))
            if val < min_val:
                print(f"   ❌ 必须大于等于 {min_val}")
                return None
            if max_val is not None and val > max_val:
                print(f"   ❌ 必须小于等于 {max_val}")
                return None
            return val
        except ValueError:
            print("   ❌ 请输入有效数字")
            return None
        except KeyboardInterrupt:
            print("\n   操作取消")
            return None

    def execute(self, args: List[str]) -> bool:
        # 参数检查
        if len(args) < 2 or args[0].lower() != "contract":
            print("❌ 用法: vote contract <合同ID>")
            return False

        # 解析合同ID
        try:
            contract_id = int(args[1])
        except ValueError:
            print(f"❌ 无效的合同ID: {args[1]}")
            return False

        # 查找合同
        contract = None
        for c in self.state.contracts:
            if c.id == contract_id:
                contract = c
                break
        if not contract:
            print(f"❌ 合同 {contract_id} 不存在")
            return False

        # 验证合同状态和类型
        if contract.status != ContractStatus.PENDING:
            print(f"⚠️ 合同已处理（{contract.status.value}）")
            return False
        if contract.contract_type != ContractType.TAX_FARMING:
            print(f"❌ 这不是包税合同")
            return False

        terms = TerminologyService.get()

        # 获取骑士候选人（排除贵族和平民）
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.class_tier.value == "eques":
                    candidates.append((member, faction))

        if not candidates:
            print(f"❌ 没有符合资格的骑士候选人")
            return False

        # 显示候选人
        print(f"\n   📊 Voting: {contract.name}")
        print(f"      Prepayment: {contract.base_cost} {terms.currency}")
        print(f"      Expected Profit: {contract.expected_profit} {terms.currency}")
        print(f"      Duration: {contract.duration_years} years")

        print(f"\n   Candidates ({terms.cavalry_class}):")
        for idx, (member, faction) in enumerate(candidates, 1):
            can_afford = "✅" if member.wealth >= contract.base_cost else "❌"
            print(f"      {idx}. {member.name} ({faction.name})")
            print(f"         Wealth: {member.wealth} {can_afford}")

        # 选择候选人
        choice = self._input_int(f"\n   选择候选人 (1-{len(candidates)}): ", 1, len(candidates))
        if choice is None:
            return False
        winner, winner_faction = candidates[choice - 1]

        # 检查财富
        if winner.wealth < contract.base_cost:
            print(f"❌ {winner.name} 无法支付 {contract.base_cost} {terms.currency}")
            return False

        # 授予合同
        if contract.award(winner.id, winner_faction.id, self.state.turn.turn_number):
            # 扣除财富，增加国库
            self.state.add_figure_wealth(winner.id, -contract.base_cost)
            self.state.add_treasury(contract.base_cost)
            print(f"\n✅ 合同授予 {winner.name}！")
            print(f"   {winner.name} 支付 {contract.base_cost} {terms.currency}")
            print(f"   国库 +{contract.base_cost} {terms.currency}")
            return True
        else:
            print(f"❌ 合同授予失败")
            return False