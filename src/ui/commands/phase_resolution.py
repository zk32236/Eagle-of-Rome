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
        if not self.state.is_phase_executed("combat"):
            print("⚠️ 必须先执行战斗阶段 (combat)")
            return False

        if self.state.is_phase_executed("resolution"):
            print("⚠️ 决议阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_resolution} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 1. 胜利条件检查（精简打印）
        self._check_all_conditions(terms)
        # 2. 和约到期检查（新增）
        self._check_truce_expiry()
        # 3. 总督返回处理
        self._process_governor_return()

        # 4. 后台功能（不打印）
        self._process_contract_expiration(terms, verbose=False)
        self._prepare_next_year(verbose=False)
        ms = self.state.get_military_system()
        if ms:
            ms.process_legion_recovery(self.state.turn.turn_number)  # 该方法内部已无打印或需修改

        # 清除本回合生效的事件（天命）
        self.state.clear_active_events()

        self.state.mark_phase_executed("resolution")

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

    def _check_all_conditions(self, terms):
        """检查所有胜利/失败条件，打印简洁信息"""
        results = self.state.check_victory_conditions()
        print(f"\n   🏆 胜利/失败条件检查:")
        for cond in results["conditions"]:
            icon = "💀" if cond["critical"] else "⚠️"
            print(f"      {icon} {cond['details']}")
        # 赤字日志（critical 条件已由 check_victory_conditions 内部记录）
        for cond in results["conditions"]:
            if cond["type"] == "bankruptcy" and cond["triggered"]:
                self.state.log_event(
                    f"国库连续{results['summary']['deficit_limit']}回合赤字，共和覆灭",
                    extra={"type": "game_over", "reason": "bankruptcy",
                           "deficit_turns": results["summary"]["deficit_turns"]},
                    level=logging.CRITICAL
                )
        summary = results["summary"]
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

