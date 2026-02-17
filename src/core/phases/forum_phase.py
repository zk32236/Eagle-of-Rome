# src/core/phases/forum_phase.py

from typing import List, Optional
from src.core.game_state import GameState
from src.core.localization import TerminologyService, GamePhase
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus


class ForumPhase:
    """
    广场阶段（Forum Phase）- MVP 0.4 + 0.4.3

    核心职责：
    1. 检查死亡池，有新死亡时生成新人物
    2. 将新人物放入 Curia 等待区
    3. 显示当前等待的人物
    4. 为 persuade/recruit 做准备
    5. MVP 0.4.3: 生成合同并记录创建回合
    """

    def __init__(self):
        self.phase_id = GamePhase.FORUM

    def execute(self, state: GameState) -> bool:
        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_forum} Phase (Year {abs(state.turn.year)} BC) ---")

        # 1. 检查并生成新人物（基于死亡池）
        new_figures = self._generate_new_figures(state)

        if new_figures:
            print(f"\n   📢 {len(new_figures)} new figure(s) arrive in the {terms.assembly}:")
            for fig in new_figures:
                tier_emoji = {
                    "nobile": "🏛️",
                    "eques": "💰",
                    "plebeian": "👤"
                }.get(fig.class_tier.value, "❓")
                print(f"      {tier_emoji} {fig.get_formal_name()} ({fig.class_tier.value})")
        else:
            print(f"\n   📭 No new figures this year.")

        # 2. 显示 Curia 状态
        self._display_curia(state, terms)

        # 3. 生成合同（MVP 0.4.3: 记录创建回合）
        new_contracts = self._generate_contracts(state)
        if new_contracts:
            print(f"\n   📜 {len(new_contracts)} new contract(s) announced:")
            for c in new_contracts:
                type_name = "包税" if c.contract_type.value == "tax_farming" else "工程"
                print(f"      {type_name}: {c.name}")

        # 4. 显示合同（新增）
        self._display_contracts(state, terms)

        # 5. 显示提示
        print(f"\n   💡 Use 'persuade <id>' to recruit figures into your faction.")
        print(f"   💡 Use 'contracts' to view pending contracts.")

        state.turn.current_phase = "forum"
        return True

    def _generate_new_figures(self, state: GameState) -> List[Figure]:
        """
        生成新人物
        MVP 0.4 规则：每回合固定生成1-2个新人物
        未来：基于死亡池、事件卡触发
        """
        import random

        new_figures = []

        # MVP简化：每回合固定生成1-2人
        count = random.randint(1, 2)

        # 获取下一个可用ID
        next_id = max(state.members.keys(), default=0) + 1

        for i in range(count):
            figure_id = next_id + i

            # 随机阶层，但偏向平民（罗马人口结构）
            tier_roll = random.random()
            if tier_roll < 0.1:  # 10% 贵族
                figure = Figure.create_nobile(figure_id, "unaffiliated", age=random.randint(30, 50))
            elif tier_roll < 0.35:  # 25% 骑士
                figure = Figure.create_eques(figure_id, "unaffiliated", age=random.randint(25, 40))
            else:  # 65% 平民
                figure = Figure.create_plebeian(figure_id, "unaffiliated", age=random.randint(20, 35))

            # 添加到游戏状态（但不属于任何派系）
            state.add_member(figure)

            # 放入 Curia 等待区
            state.curia.add_figure(figure)

            new_figures.append(figure)

        return new_figures

    def _display_curia(self, state: GameState, terms):
        """显示 Curia 状态"""
        curia = state.curia

        if curia.is_empty():
            print(f"\n   📭 The {terms.assembly} is empty.")
            return

        print(f"\n   🏛️  Figures in {terms.assembly}:")

        # 按阶层分组显示
        for tier in ["nobile", "eques", "plebeian"]:
            figures = curia.get_available_by_tier(tier)
            if not figures:
                continue

            tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(tier, "❓")
            print(f"\n      {tier_emoji} {tier.upper()} ({len(figures)}):")

            for fig in figures:
                # 基础属性
                power = f"权{fig.power}" if fig.power > 0 else ""
                wealth = f"财{fig.wealth}" if fig.wealth > 0 else ""
                pop = f"人{fig.popularity}" if fig.popularity > 0 else ""

                # MVP 0.4: 显示家族（贵族专属）
                family_info = ""
                if fig.family:
                    family_info = f" 家族:{fig.family}"

                print(f"         ID:{fig.id} {fig.get_formal_name()}")
                print(f"            [{power}{wealth}{pop}]{family_info}")

    def _generate_contracts(self, state: GameState) -> List[Contract]:
        """生成合同机会（MVP 0.4.3: 记录创建回合）"""
        import random
        from src.core.entities.contract import Contract, ContractType

        contracts = []
        next_id = max([c.id for c in state.contracts], default=0) + 1

        # 生成1个包税合同
        provinces = ["西西里", "撒丁尼亚", "科西嘉", "山南高卢", "伊利里亚"]
        province = random.choice(provinces)
        tax_cost = random.randint(20, 40)  # 预付成本
        tax_profit = random.randint(10, 25)  # 年预期收益（5年总收益）

        tax_contract = Contract.create_tax_farming(
            next_id, province, tax_cost, tax_profit
        )
        # MVP 0.4.3: 记录创建回合用于过期判断
        tax_contract._created_turn = state.turn.turn_number
        state.contracts.append(tax_contract)
        contracts.append(tax_contract)
        next_id += 1

        # 生成1个工程合同
        projects = ["罗马大道", "公共浴场", "水道桥", "港口扩建", "神殿修缮"]
        project = random.choice(projects)
        budget = random.randint(30, 60)  # 国库预算

        works_contract = Contract.create_public_works(
            next_id, project, budget
        )
        # MVP 0.4.3: 记录创建回合
        works_contract._created_turn = state.turn.turn_number
        state.contracts.append(works_contract)
        contracts.append(works_contract)

        return contracts

    def _display_contracts(self, state: GameState, terms):
        """显示待授予合同"""
        pending = [c for c in state.contracts if c.status.value == "pending"]

        if not pending:
            print(f"\n   📭 No pending contracts.")
            return

        print(f"\n   📋 Pending Contracts:")

        tax_contracts = [c for c in pending if c.contract_type.value == "tax_farming"]
        works_contracts = [c for c in pending if c.contract_type.value == "public_works"]

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