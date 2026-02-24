# src/ui/commands/phase_mortality.py
"""
天命阶段命令 - 处理事件卡和人物死亡
"""

import random
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import ClassTier
from src.ui.commands.func_status import get_progress_bar

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

        # 抽取事件卡
        for i in range(draw_count):
            event = random.choice(deck)
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
        """死神来了：随机抽取死亡人数，财产归公"""
        rules = self.state.config.get("mortality_rules", {})
        death_count = rules.get("death_count", 1)

        living = self.state.get_living_members()
        if not living:
            print("   😇 无存活人物，死神空手而归")
            return

        # 从所有存活人物中随机抽取
        victims = random.sample(living, min(death_count, len(living)))

        for victim in victims:
            print(f"   💀 死神选中了 {victim.name} (阶级: {victim.class_tier.value})")

            # 转移财产：财富归国库
            self.state.add_treasury(victim.wealth)
            print(f"      💰 {victim.wealth} {TerminologyService.get().currency} 归入国库")

            # 提前保存私地数量
            land = victim.land_private
            national_land_before = self.state._national_public_land
            print(f"      🏞️ 当前国家公地: {national_land_before} C (土地回收前)")

            self.state.mark_member_dead(victim.id, transfer_land=True)

            national_land_after = self.state._national_public_land
            print(f"      🏞️ 土地回收后国家公地: {national_land_after} C (+{land})")

        self.state.log_event(f"💀 死神来了：{len(victims)} 人死亡，财产归公")