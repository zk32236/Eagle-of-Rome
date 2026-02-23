# src/ui/commands/phase_mortality.py
"""
天命阶段命令 - 处理事件卡和人物死亡（测试版：每回合固定死神来了，优先选元老）
"""

import random
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import ClassTier  # 新增导入

if TYPE_CHECKING:
    from src.core.game_state import GameState


class MortalityCommand(Command):
    """天命阶段命令"""

    name = "mortality"
    aliases = ["m"]
    description = "执行天命阶段 (Mortality Phase) - 当前固定触发死神来了"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        if self.state.is_phase_executed("mortality"):
            print("⚠️ 天命阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_mortality} Phase (Year {abs(self.state.turn.year)} BC) ---")

        print("   🎴 事件卡: 死神来了 (厄运)")
        self._handle_death_event()

        self.state.mark_phase_executed("mortality")
        return True

    def _handle_death_event(self):
        """死神来了：优先选择元老死亡（测试用），显示国库公地数量"""
        rules = self.state.config.get("mortality_rules", {})
        death_count = rules.get("death_count", 1)

        living = self.state.get_living_members()
        if not living:
            print("   😇 无存活人物，死神空手而归")
            return

        # 优先选择元老（仅测试用）
        nobles = [f for f in living if f.class_tier == ClassTier.NOBILE]
        if nobles:
            victims = random.sample(nobles, min(death_count, len(nobles)))
        else:
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

    # ---------- 预留事件处理接口 ----------
    def _handle_bountiful_harvest(self):
        print("   🌾 丰调雨顺：今年土地产出增加50%（预留）")
        self.state.log_event("🌾 丰调雨顺")

    def _handle_peace_and_stability(self):
        print("   🕊️ 国泰民安：民变和战争威胁降低（预留）")
        self.state.log_event("🕊️ 国泰民安")

    def _handle_mighty_man(self):
        print("   💪 天降猛男：一位强力平民将在广场阶段出现（预留）")
        self.state.log_event("💪 天降猛男")

    def _handle_natural_disaster(self):
        print("   🌪️ 无妄天灾：随机行省遭受自然灾害（预留）")
        self.state.log_event("🌪️ 无妄天灾")