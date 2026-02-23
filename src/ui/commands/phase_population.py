# src/ui/commands/phase_population.py
"""
人口阶段命令 - 计算国家状态、处理军团解散、触发人口事件
"""

import random
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.ui.commands.func_status import get_progress_bar

if TYPE_CHECKING:
    from src.core.game_state import GameState


class PopulationCommand(Command):
    """人口阶段命令"""

    name = "population"
    aliases = ["p"]
    description = "执行人口阶段 (Population Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """
        执行人口阶段

        1. 检查阶段是否已执行
        2. 计算共和国状态
        3. 处理军团解散建议/强制解散
        4. 触发随机人口事件
        5. 标记阶段为已执行
        """
        if self.state.is_phase_executed("population"):
            print("⚠️ 人口阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_population} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 1. 计算国家状态
        republic_state = self._calculate_republic_state(terms)
        print(f"\n   🏛️  State of the Republic: {republic_state}")

        # 2. 军团解散逻辑
        self._process_legion_disbandment(terms, republic_state)

        # 3. 人口阶段事件
        self._process_population_events(terms)

        # 标记阶段已执行
        self.state.mark_phase_executed("population")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _calculate_republic_state(self, terms) -> str:
        """计算国家状态"""
        treasury = self.state.treasury
        has_wars = len(self.state.get_active_wars()) > 0

        # 获取军事系统信息
        ms = self.state.get_military_system()
        legion_pressure = 0
        if ms:
            active = len(ms.get_active_legions()) if hasattr(ms, 'get_active_legions') else 0
            unraised = len(ms.get_available_legions()) if hasattr(ms, 'get_available_legions') else 0
            legion_pressure = active / 10 if active > 0 else 0

        if treasury < 0 and has_wars:
            state_name = terms.state_bad
            emoji = "🔴"
        elif treasury < 50 or (has_wars and legion_pressure > 0.5):
            state_name = terms.state_tense
            emoji = "🟠"
        elif treasury < 100:
            state_name = terms.state_uneasy
            emoji = "🟡"
        else:
            state_name = terms.state_calm
            emoji = "🟢"

        print(f"   {emoji} Treasury: {treasury} {terms.currency}")
        if has_wars:
            print(f"   ⚔️  Active wars: {len(self.state.get_active_wars())}")
        if ms:
            print(f"   🛡️  Active legions: {len(ms.get_active_legions() if hasattr(ms, 'get_active_legions') else [])}/10")

        return state_name

    def _process_legion_disbandment(self, terms, republic_state: str):
        """处理军团解散"""
        ms = self.state.get_military_system()
        if not ms:
            return

        print(f"\n   🛡️  {terms.legion} Review:")

        # 根据状态决定是否建议解散
        if republic_state == terms.state_bad:
            # Bad状态：强制解散一半军团
            active_legions = ms.get_active_legions() if hasattr(ms, 'get_active_legions') else []
            to_disband = len(active_legions) // 2
            print(f"      🔴 Crisis! Must disband {to_disband} {terms.legion}(s)")
            self._auto_disband(ms, to_disband)

        elif republic_state == terms.state_tense:
            # Tense状态：建议解散
            print(f"      🟠 Tense state: Consider disbanding unassigned {terms.legion}s")
            unassigned = ms.get_unassigned_legions() if hasattr(ms, 'get_unassigned_legions') else []
            if unassigned:
                print(f"      {len(unassigned)} {terms.legion}(s) available for disbandment")

        elif republic_state == terms.state_calm:
            # Calm状态：可以征召新军团
            available = ms.get_available_legions() if hasattr(ms, 'get_available_legions') else []
            if available:
                print(f"      🟢 Calm state: {len(available)} {terms.legion}(s) available for recruitment")

    def _auto_disband(self, ms, count: int):
        """自动解散军团"""
        unassigned = ms.get_unassigned_legions() if hasattr(ms, 'get_unassigned_legions') else []
        disbanded = 0
        for legion in unassigned[:count]:
            if hasattr(ms, 'disband_legion'):
                success, msg = ms.disband_legion(legion.number)
                if success:
                    disbanded += 1
                    print(f"      ⚫ {legion.name} disbanded")
        if disbanded < count:
            terms = TerminologyService.get()
            print(f"      ⚠️  Could only disband {disbanded}/{count} {terms.legion}(s)")

    def _process_population_events(self, terms):
        """处理人口事件"""
        print(f"\n   👥 {terms.phase_population} Events:")
        if random.random() < 0.2:  # 20%概率
            events = [
                "Population growth in rural areas",
                "Urban unrest in the capital",
                "Migration from the provinces",
                "Recruitment drives popular",
                "Veterans demand land grants",
            ]
            event = random.choice(events)
            print(f"      📢 {event}")
        else:
            print("      No significant events")