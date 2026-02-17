# src/core/phases/population_phase.py

from typing import Dict
from core.game_state import GameState
from core.localization import TerminologyService, GamePhase


class PopulationPhase:
    """
    人口阶段（Population Phase）

    核心职责：
    1. 计算国家状态（State of the Republic）
    2. 军团解散检查（根据国库和Unrest）
    3. 处理人口相关事件
    """

    def __init__(self):
        self.phase_id = GamePhase.POPULATION

    def execute(self, state: GameState) -> bool:
        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_population} Phase (Year {abs(state.turn.year)} BC) ---")

        # 1. 计算国家状态
        republic_state = self._calculate_republic_state(state, terms)
        print(f"\n   🏛️  State of the Republic: {republic_state}")

        # 2. 军团解散逻辑（根据状态）
        self._process_legion_disbandment(state, terms, republic_state)

        # 3. 人口阶段事件
        self._process_population_events(state, terms)

        state.turn.current_phase = "population"
        return True

    def _calculate_republic_state(self, state: GameState, terms) -> str:
        """计算国家状态"""
        treasury = state.treasury
        has_wars = len(state.get_active_wars()) > 0

        # 获取军事系统信息
        ms = state.get_military_system()
        legion_pressure = 0
        if ms:
            active = len(ms.get_active_legions())
            unraised = len(ms.get_available_legions())
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
            print(f"   ⚔️  Active wars: {len(state.get_active_wars())}")
        if ms:
            print(f"   🛡️  Active legions: {len(ms.get_active_legions())}/10")

        return state_name

    def _process_legion_disbandment(self, state: GameState, terms, republic_state: str):
        """处理军团解散"""
        ms = state.get_military_system()
        if not ms:
            return

        print(f"\n   🛡️  {terms.legion} Review:")

        # 根据状态决定是否建议解散
        if republic_state == terms.state_bad:
            # Bad状态：强制解散一半军团
            to_disband = len(ms.get_active_legions()) // 2
            print(f"      🔴 Crisis! Must disband {to_disband} {terms.legion}(s)")
            self._auto_disband(state, ms, to_disband)

        elif republic_state == terms.state_tense:
            # Tense状态：建议解散
            print(f"      🟠 Tense state: Consider disbanding unassigned {terms.legion}s")
            unassigned = ms.get_unassigned_legions()
            if unassigned:
                print(f"      {len(unassigned)} {terms.legion}(s) available for disbandment")

        elif republic_state == terms.state_calm:
            # Calm状态：可以征召新军团
            available = ms.get_available_legions()
            if available:
                print(f"      🟢 Calm state: {len(available)} {terms.legion}(s) available for recruitment")

    def _auto_disband(self, state: GameState, ms, count: int):
        """自动解散军团"""
        terms = TerminologyService.get()
        unassigned = [l for l in ms.get_active_legions() if l.war_id is None]

        disbanded = 0
        for legion in unassigned[:count]:
            success, msg = ms.disband_legion(legion.number)
            if success:
                disbanded += 1
                print(f"      ⚫ {legion.name} disbanded")

        if disbanded < count:
            print(f"      ⚠️  Could only disband {disbanded}/{count} {terms.legion}(s)")

    def _process_population_events(self, state: GameState, terms):
        """处理人口事件"""
        print(f"\n   👥 {terms.phase_population} Events:")

        # MVP 0.3简化：随机人口事件
        import random
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