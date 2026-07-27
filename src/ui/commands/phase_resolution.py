# src/ui/commands/phase_resolution.py
"""
决议阶段命令 - 精简打印，只显示胜利条件
"""
import logging
from typing import List, Dict, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.ui.utils import get_progress_bar
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.api.resolution_api import execute_resolution

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ResolutionCommand(Command):
    """决议阶段命令"""

    name = "resolution"
    aliases = ["x"]
    description = "执行决议阶段 (Resolution Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        # 委托给 resolution_api 共享用例
        result = execute_resolution(self.state)

        if not result["success"]:
            print(f"⚠️ {result['message']}")
            return False

        dto = result.get("data", {})
        terms = TerminologyService.get()
        year_display = dto.get("year_display", f"{abs(self.state.turn.year)} BC")
        print(f"\n--- {terms.phase_resolution} Phase ({year_display}) ---")

        # 打印胜利条件
        self._print_victory_conditions(dto)

        # 打印军团恢复
        legion = dto.get("legion_recovery", {})
        if legion.get("recovered", 0) > 0:
            print(f"\n   🛡️ 军团恢复: {legion['details']}")

        # 打印关键事件
        key_events = dto.get("key_events", [])
        if key_events:
            print(f"\n   📋 关键事件:")
            for evt in key_events:
                print(f"      • {evt}")

        return True

    # ================================= MVP 0.7 ===========================================

    # ======== MVP 0.7.1 停战议和 =======

    def _check_truce_expiry(self):
        """Shell method — logic moved to GameState.advance_year()"""
        return []

    # ================================= MVP 0.1-0.5 =======================================

    def _process_governor_return(self):
        """Shell method — logic moved to GameState.advance_year()"""
        return []

    def _print_victory_conditions(self, dto: dict):
        """从 DTO 打印胜利条件结果"""
        victory = dto.get("victory", {})
        conditions = victory.get("conditions", [])
        summary = victory.get("summary", {})
        print(f"\n   🏆 胜利/失败条件检查:")
        for cond in conditions:
            icon = "💀" if cond.get("critical") else "⚠️"
            print(f"      {icon} {cond['details']}")
        if summary.get("top_faction"):
            tf = summary["top_faction"]
            print(f"      📊 元老院主导派系: {tf['name']} ({tf['share']:.1%} 影响力)")
        else:
            print(f"      📊 元老院无派系")

    def _process_contract_expiration(self, terms, verbose=False):
        """Shell method — logic moved to GameState.advance_year()"""
        return 0

    def _prepare_next_year(self, verbose=False):
        """准备下一年（无打印）"""
        # 实际 advance_year 会重置阶段标记，这里不需要额外操作
        pass

    def _apply_annual_decay(self, terms, verbose=False):
        """年度衰减（无打印）"""
        decay_rates = {
            "veterans": 0.20,
            "popularity": 0.50
        }
        for fig in self.state.get_living_members():
            fig.apply_annual_decay(decay_rates)
            fig.age += 1

    def _process_temp_influence_decay(self, verbose=False):
        """处理所有存活人物的临时影响力衰减（无打印）"""
        for fig in self.state.get_living_members():
            if fig.get_temp_influence() > 0:
                fig.decay_temp_influence_tasks()
                fig.update_influence()

