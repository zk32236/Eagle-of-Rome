# src/ui/commands/phase_resolution.py
"""
决议阶段命令 - 精简打印，只显示胜利条件
"""

from typing import List, Dict, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractStatus
from src.ui.commands.func_status import get_progress_bar

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

        # 2. 后台功能（不打印）
        self._process_contract_expiration(terms, verbose=False)
        self._prepare_next_year(verbose=False)
        self._apply_annual_decay(terms, verbose=False)
        self._process_temp_influence_decay(verbose=False)

        ms = self.state.get_military_system()
        if ms:
            ms.process_legion_recovery(self.state.turn.turn_number)  # 该方法内部已无打印或需修改

        self.state.mark_phase_executed("resolution")
        # 不打印进度条
        return True

    def _check_all_conditions(self, terms):
        """检查所有胜利/失败条件，仅打印元老院主导派系"""
        print(f"\n   🏆 胜利/失败条件检查:")

        # 计算元老院影响力
        total_senate_influence = 0
        faction_influences = {}
        for faction in self.state.factions.values():
            inf = faction.get_senate_influence(self.state)
            total_senate_influence += inf
            faction_influences[faction.id] = inf

        if total_senate_influence > 0:
            top_faction_id = max(faction_influences, key=lambda fid: faction_influences[fid])
            top_faction = self.state.get_faction(top_faction_id)
            top_share = faction_influences[top_faction_id] / total_senate_influence
            print(f"      📊 元老院主导派系: {top_faction.name} ({top_share:.1%} 影响力)")
        else:
            print(f"      📊 元老院无派系")

        # 其他条件仍检查但不打印（可选，可保留逻辑但注释打印）
        # 可保留但不输出
        # 例如国库赤字、军团覆没等，如果需要保持逻辑，可以继续执行但不打印。

    def _process_contract_expiration(self, terms, verbose=False):
        """处理合同过期（无打印）"""
        expired_count = 0
        for contract in self.state.contracts:
            if contract.status == ContractStatus.PENDING:
                turns_pending = self.state.turn.turn_number - getattr(contract, '_created_turn', self.state.turn.turn_number)
                if turns_pending >= 3:
                    contract.expire()
                    expired_count += 1
        # 不打印

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