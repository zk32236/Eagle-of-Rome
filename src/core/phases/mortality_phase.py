# src/core/phases/mortality_phase.py

from typing import List
from src.core.game_state import GameState
from src.core.entities import Senator
from src.core.localization import TerminologyService, GamePhase


class MortalityPhase:
    """天命阶段（原Mortality Phase）"""

    def __init__(self):
        self.phase_id = GamePhase.MORTALITY

    def execute(self, state: GameState) -> bool:
        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_mortality} Phase (Year {abs(state.turn.year)} BC) ---")

        deaths_this_turn: List[Senator] = []
        living_count = len(state.get_living_members())

        # 计算抽取数量
        rules = state.config.get("mortality_rules", {})
        base = rules.get("base_draw_count", 1)
        per = rules.get("draw_per_members", 5)
        max_draws = rules.get("max_draws", 3)
        draw_count = max(1, min(max_draws, living_count // per))

        print(f"Drawing {draw_count} number(s) from pool (1-300)...")
        print(f"Current living: {living_count}")

        for i in range(draw_count):
            drawn_number = state.draw_mortality_number()
            print(f"  [Draw {i + 1}] Number {drawn_number}...")

            member = state.get_living_member(drawn_number)

            if member:
                self._process_death(state, member, terms)
                deaths_this_turn.append(member)
            else:
                print(f"     -> No member assigned (safe)")

        if deaths_this_turn:
            names = ", ".join([m.name for m in deaths_this_turn])
            state.log_event(f"💀 {terms.nobles} died: {names}")
        else:
            state.log_event(f"✅ No deaths this year")

        state.turn.current_phase = "mortality"
        return True

    def _process_death(self, state: GameState, member: Senator, terms):
        """处理死亡"""
        member.is_dead = True

        if member.is_faction_leader:
            member.is_faction_leader = False
            if member.id in state.turn.leader_ids:
                state.turn.leader_ids.remove(member.id)

        faction = state.get_faction(member.faction_id)
        fname = faction.name if faction else "Unknown"

        print(f"     -> 💀 {member.name} of {fname} has died!")

        if faction:
            remaining = len([m for m in faction.get_members(state) if not m.is_dead])
            print(f"        {fname} has {remaining} {terms.nobles.lower()} remaining")