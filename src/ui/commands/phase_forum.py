# src/ui/commands/phase_forum.py
"""
广场阶段命令 - 生成新人物和合同，并展示 Curia 状态
"""

import random
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType
from src.ui.commands.func_status import get_progress_bar

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ForumCommand(Command):
    """广场阶段命令"""

    name = "forum"
    aliases = ["f"]
    description = "执行广场阶段 (Forum Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """
        执行广场阶段

        1. 检查阶段是否已执行
        2. 生成新人物并放入 Curia
        3. 显示 Curia 中等待的人物
        4. 生成新合同并加入合同列表
        5. 显示合同状态
        6. 标记阶段为已执行

        Args:
            args: 命令参数（忽略）

        Returns:
            bool: 执行成功返回 True
        """
        if self.state.is_phase_executed("forum"):
            print("⚠️ 广场阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_forum} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 1. 生成新人物
        new_figures = self._generate_new_figures()
        if new_figures:
            print(f"\n   📢 {len(new_figures)} new figure(s) arrive in the {terms.assembly}:")
            for fig in new_figures:
                tier_emoji = {
                    ClassTier.NOBILE: "🏛️",
                    ClassTier.EQUES: "💰",
                    ClassTier.PLEBEIAN: "👤"
                }.get(fig.class_tier, "❓")
                print(f"      {tier_emoji} {fig.get_formal_name()} ({fig.class_tier.value})")
        else:
            print(f"\n   📭 No new figures this year.")

        # 2. 显示 Curia 状态
        self._display_curia(terms)

        # 3. 生成合同
        new_contracts = self._generate_contracts()
        if new_contracts:
            print(f"\n   📜 {len(new_contracts)} new contract(s) announced:")
            for c in new_contracts:
                type_name = "包税" if c.contract_type == ContractType.TAX_FARMING else "工程"
                print(f"      {type_name}: {c.name}")
        else:
            print(f"\n   📭 No new contracts.")

        # 4. 显示合同列表
        self._display_contracts(terms)

        # 5. 提示可用命令
        print(f"\n   💡 Use 'persuade <id>' to recruit figures into your faction.")
        print(f"   💡 Use 'contracts' to view pending contracts.")

        # 标记阶段已执行
        self.state.mark_phase_executed("forum")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _generate_new_figures(self) -> List[Figure]:
        """生成新人物（逻辑与原 forum_phase.py 一致）"""
        new_figures = []
        count = random.randint(1, 2)  # 每回合生成1-2人

        # 获取下一个可用ID（简单递增，但需避免冲突）
        next_id = max((mid for mid in self.state.members.keys()), default=0) + 1

        for i in range(count):
            figure_id = next_id + i
            tier_roll = random.random()
            if tier_roll < 0.1:          # 10% 贵族
                figure = Figure.create_nobile(figure_id, None, age=random.randint(30, 50))
            elif tier_roll < 0.35:        # 25% 骑士
                figure = Figure.create_eques(figure_id, None, age=random.randint(25, 40))
            else:                          # 65% 平民
                figure = Figure.create_plebeian(figure_id, None, age=random.randint(20, 35))

            # 添加到全局成员列表
            self.state.add_member(figure)
            # 放入 Curia 等待区
            self.state.curia.add_figure(figure)
            new_figures.append(figure)

        return new_figures

    def _display_curia(self, terms):
        """显示 Curia 中等待的人物"""
        curia = self.state.curia
        if curia.is_empty():
            print(f"\n   📭 The {terms.assembly} is empty.")
            return

        print(f"\n   🏛️  Figures in {terms.assembly}:")
        for tier in ["nobile", "eques", "plebeian"]:
            figures = curia.get_available_by_tier(tier)
            if not figures:
                continue
            tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(tier, "❓")
            print(f"\n      {tier_emoji} {tier.upper()} ({len(figures)}):")
            for fig in figures:
                power = f"权{fig.power}" if fig.power > 0 else ""
                wealth = f"财{fig.wealth}" if fig.wealth > 0 else ""
                pop = f"人{fig.popularity}" if fig.popularity > 0 else ""
                family_info = f" 家族:{fig.family}" if fig.family else ""
                print(f"         ID:{fig.id} {fig.get_formal_name()}")
                print(f"            [{power}{wealth}{pop}]{family_info}")

    def _generate_contracts(self) -> List[Contract]:
        """生成合同（基于配置和行省状态）"""
        from src.core.entities.contract import ContractType
        contracts = []
        config = self.state.config

        # 包税合同：遍历所有行省，为未绑定的生成
        for province in self.state.get_all_provinces():
            if province.tax_contract_id is not None:
                continue
            # 根据行省名称确定基础税金（可从配置扩展）
            if "西西里" in province.name:
                base_cost = config.get("economic_rules.tax_base_sicily", 90)
            elif "撒丁" in province.name:
                base_cost = config.get("economic_rules.tax_base_sardinia", 70)
            else:
                base_cost = 50  # 默认
            # 创建合同
            contract = self.state.create_contract(
                ContractType.TAX_FARMING,
                province.province_id,
                base_cost,
                self.state.turn.turn_number
            )
            # 设置额外字段
            contract.name = f"{province.name}包税权"
            contract.description = f"{province.name}行省税收承包权"
            profit_rate = config.get("economic_rules.tax_contract_profit_rate", 0.2)
            contract.expected_profit = int(base_cost * profit_rate)
            contract.duration_years = config.get("economic_rules.tax_contract_exec_turn", 10)
            # 绑定行省
            province.bind_tax_contract(contract.id)
            contracts.append(contract)
            print(f"      📊 包税权合同生成：{province.name} 底价 {base_cost}")

        # 公共工程合同：国库资金足够时生成
        treasury = self.state.treasury
        project_base = config.get("economic_rules.project_base_cost", 200)
        total_needed = 0
        candidates = []
        for province in self.state.get_all_provinces():
            if province.project_contract_id is None and not province.has_project:
                total_needed += project_base
                candidates.append(province)

        if total_needed <= treasury:
            for province in candidates:
                contract = self.state.create_contract(
                    ContractType.PUBLIC_WORKS,
                    province.province_id,
                    project_base,
                    self.state.turn.turn_number
                )
                contract.name = f"{province.name}工程"
                contract.description = f"{province.name}公共建设项目"
                profit_rate = config.get("economic_rules.project_contract_profit_rate", 0.15)
                contract.expected_profit = int(project_base * profit_rate)
                contract.duration_years = config.get("economic_rules.project_contract_exec_turn", 15)
                province.bind_project_contract(contract.id)
                contracts.append(contract)
                print(f"      🏗️ 公共工程合同生成：{province.name} 预算 {project_base}")
        else:
            print(f"      ⚠️ 国库资金不足，无法生成全部公共工程合同")

        return contracts

    def _display_contracts(self, terms):
        """显示待授予合同"""
        pending = [c for c in self.state.contracts if c.status.value == "pending"]
        if not pending:
            print(f"\n   📭 No pending contracts.")
            return

        print(f"\n   📋 Pending Contracts:")
        tax_contracts = [c for c in pending if c.contract_type == ContractType.TAX_FARMING]
        works_contracts = [c for c in pending if c.contract_type == ContractType.PUBLIC_WORKS]

        if tax_contracts:
            print(f"\n      📊 Tax Farming (Senate Vote Required):")
            for c in tax_contracts:
                print(f"         ID:{c.id} {c.name}")
                print(f"            预付:{c.base_cost} 年收益:{c.expected_profit} 期限:{c.duration_years}年")
                print(f"            💡 Senate Phase: use 'vote contract {c.id}'")

        if works_contracts:
            print(f"\n      🏗️ Public Works (Consul Assigns):")
            for c in works_contracts:
                print(f"         ID:{c.id} {c.name}")
                print(f"            预算:{c.base_cost} 预期利润:{c.expected_profit}")
                print(f"            💡 Senate Phase: Consul uses 'assign works {c.id} <figure_id>'")