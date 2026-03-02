# src/ui/commands/phase_mortality.py
"""
天命阶段命令 - 处理事件卡和人物死亡
"""

import random
import logging
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.ui.commands.func_status import get_progress_bar
from src.core.entities.contract import ContractStatus, ContractType

if TYPE_CHECKING:
    from src.core.game_state import GameState


class MortalityCommand(Command):
    """天命阶段命令"""

    name = "mortality"
    aliases = ["m"]
    description = "执行天命阶段 (Mortality Phase) - 抽取事件卡"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        if self.state.is_phase_executed("mortality"):
            print("⚠️ 天命阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_mortality} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 从配置获取事件卡池
        rules = self.state.config.get("mortality_rules", {})
        deck = rules.get("event_deck", [])
        draw_count = rules.get("event_draw_count", 1)

        if not deck:
            print("   ⚠️ 未配置事件卡")
            self.state.mark_phase_executed("mortality")
            print(f"\n   Progress: {get_progress_bar(self.state)}")
            return True

        # 按权重抽取事件卡
        weights = [e.get("weight", 1) for e in deck]
        if sum(weights) == 0:
            # 所有权重为0时回退到等概率
            weights = [1] * len(deck)

        drawn_events = random.choices(deck, weights=weights, k=draw_count)

        for event in drawn_events:
            event_name = event["name"]
            effect = event["effect"]

            print(f"   🎴 事件卡: {event_name}")

            if effect == "death":
                self._handle_death_event()
            else:
                # 其他事件暂不实现，仅打印
                print(f"      (效果暂未实现)")
                self.state.log_event(f"{event_name}")

        self.state.mark_phase_executed("mortality")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _handle_death_event(self):
        """死神来了：随机抽取死亡人数，财产归公，同时终止死亡人物的合同"""
        rules = self.state.config.get("mortality_rules", {})
        death_count = rules.get("death_count", 1)

        living = self.state.get_living_members()
        if not living:
            print("   😇 无存活人物，死神空手而归")
            return

        victims = random.sample(living, min(death_count, len(living)))

        for victim in victims:
            print(f"   💀 死神选中了 {victim.name} (阶级: {victim.class_tier.value})")

            # 终止该人物持有的所有活跃合同
            if victim.has_active_contract:
                for contract_id in victim.contract_ids:
                    contract = self.state.get_contract(contract_id)
                    if contract and contract.status == ContractStatus.ACTIVE:
                        contract.terminate()
                        province = self.state.get_province(contract.province_id)
                        if province:
                            if contract.contract_type == ContractType.TAX_FARMING:
                                province.unbind_tax_contract()
                            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                                province.unbind_project_contract()
                        print(f"      📜 {victim.name} 的合同 {contract.name} 已终止")

            # 调用 mark_member_dead 统一处理资产回收
            self.state.mark_member_dead(victim.id, transfer_land=True, transfer_wealth=True)

            # ===== 新增日志 =====
            self.state.log_event(
                f"人物死亡: {victim.name} (ID:{victim.id})",
                extra={"type": "figure_death", "figure_id": victim.id, "name": victim.name}
            )

        self.state.log_event(f"💀 死神来了：{len(victims)} 人死亡，财产归公")