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
        """检查所有胜利/失败条件，打印简洁信息"""
        print(f"\n   🏆 胜利/失败条件检查:")

        # 1. 国库连续赤字（共和覆灭条件）
        if self.state.treasury < 0:
            self.state.increment_treasury_deficit_turns()
            deficit = self.state.treasury_deficit_turns
            if deficit >= 3:
                print(f"      💀 国库连续3回合赤字，共和覆灭！")
            else:
                print(f"      ⚠️ 国库赤字（第{deficit}回合），再持续{3 - deficit}回合将导致共和覆灭")
        else:
            self.state.reset_treasury_deficit_turns()

        # 2. 军团全军覆没
        ms = self.state.get_military_system()
        if ms:
            all_legions = ms.get_all_legions()
            if all_legions and all(l.status.name == "DESTROYED" for l in all_legions):
                print(f"      💀 所有军团已被消灭，共和覆灭！")

        # 3. 行省大范围暴动（超过半数行省民怨≥3）
        provinces = self.state.get_all_provinces()
        if provinces:
            revolt_provinces = [p for p in provinces if p.grievance >= 3]
            if len(revolt_provinces) > len(provinces) // 2:
                print(f"      💀 超过半数行省爆发起义，共和覆灭！")

        # 4. 派系独裁（元老院影响力占比≥70%）
        total_senate_influence = 0
        faction_influences = {}
        for faction in self.state.factions.values():
            inf = faction.get_senate_influence(self.state)
            total_senate_influence += inf
            faction_influences[faction.id] = inf
        if total_senate_influence > 0:
            for faction in self.state.factions.values():
                share = faction_influences[faction.id] / total_senate_influence
                if share >= 0.7:
                    print(f"      👑 {faction.name} 获得元老院 {share:.1%} 影响力，可能宣布独裁！")

        # 5. 意大利本土民怨3级
        italy = self.state.get_province(0)
        if italy and italy.grievance == 3:
            print(f"      💀 意大利本土民怨已达3级，若不在本年度内处理，共和国将面临覆灭！")

        # 6. 元老院主导派系（按影响力百分比）
        if total_senate_influence > 0:
            top_faction_id = max(faction_influences, key=lambda fid: faction_influences[fid])
            top_faction = self.state.get_faction(top_faction_id)
            top_share = faction_influences[top_faction_id] / total_senate_influence
            print(f"      📊 元老院主导派系: {top_faction.name} ({top_share:.1%} 影响力)")
        else:
            print(f"      📊 元老院无派系")

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