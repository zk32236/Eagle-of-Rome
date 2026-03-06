# src/ui/commands/phase_resolution.py
"""
决议阶段命令 - 精简打印，只显示胜利条件
"""
import logging
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
        # 2. 和约到期检查（新增）
        self._check_truce_expiry()
        # 3. 总督返回处理
        self._process_governor_return()

        # 4. 后台功能（不打印）
        self._process_contract_expiration(terms, verbose=False)
        self._prepare_next_year(verbose=False)
        self._apply_annual_decay(terms, verbose=False)
        self._process_temp_influence_decay(verbose=False)


        ms = self.state.get_military_system()
        if ms:
            ms.process_legion_recovery(self.state.turn.turn_number)  # 该方法内部已无打印或需修改

        self.state.mark_phase_executed("resolution")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # ================================= MVP 0.7 ===========================================

    # ======== MVP 0.7.1 停战议和 =======

    def _check_truce_expiry(self):
        """检查和约是否到期，若到期则转为威胁状态"""
        war_system = self.state.get_war_system()
        if not war_system:
            return

        current_turn = self.state.turn.turn_number
        # 获取所有停战中且和约已批准的战争
        truce_wars = war_system.get_truce_wars_with_approved_treaty()
        expired = []
        for war in truce_wars:
            if war.is_truce_expired(current_turn):
                # 将战争从停战列表移至威胁列表
                war_system._move_to_threat(war, threat_level=1)
                war.clear_peace_treaty()
                expired.append(war.name)
                print(f"      ⏰ {war.name} 和约到期，重启威胁！")
                self.state.log_event(
                    f"{war.name} 和约到期，重启威胁",
                    extra={'type': 'truce_expired', 'war_id': war.id}
                )
        if expired:
            print(f"      📢 {len(expired)} 场战争和约到期。")

    # ================================= MVP 0.1-0.5 =======================================

    def _process_governor_return(self):
        for province in self.state.get_all_provinces():
            # 先处理返回罗马的旧总督
            old_id = province._old_governor_id
            if old_id is not None:
                old_fig = self.state.get_member(old_id)
                if old_fig and not old_fig.is_dead:
                    old_fig.is_absent = False
                    old_fig.office = None  # 卸任总督官职
                    old_fig.update_influence()
                    print(f"      🔄 旧总督 {old_fig.get_formal_name()} 返回罗马")
                    self.state.log_event(f"旧总督 {old_fig.get_formal_name()} 返回罗马")
                province._old_governor_id = None

            # 再处理候任总督上任
            designate_id = province._governor_designate_id
            if designate_id is not None:
                new_fig = self.state.get_member(designate_id)
                if new_fig and not new_fig.is_dead:
                    # 新总督正式上任
                    province._governor_id = designate_id
                    new_fig.office = province.governor_type
                    new_fig.update_influence()
                    print(f"      👑 新总督 {new_fig.get_formal_name()} 正式上任 {province.name}")
                    self.state.log_event(f"新总督 {new_fig.get_formal_name()} 正式上任 {province.name}")
                province._governor_designate_id = None

    def _check_all_conditions(self, terms):
        """检查所有胜利/失败条件，打印简洁信息"""
        # ====== 新增：更新赤字计数 ======
        if self.state.treasury < 0:
            self.state.increment_treasury_deficit_turns()
        else:
            self.state.reset_treasury_deficit_turns()

        deficit = self.state.treasury_deficit_turns
        limit = self.state.get_economic_rule("national_opex_deficit_limit", 3)
        if deficit >= limit:
            print(f"      💀 国库连续{limit}回合赤字，共和覆灭！（调试模式仅提示）")
            self.state.log_event(
                f"国库连续{limit}回合赤字，共和覆灭",
                extra={"type": "game_over", "reason": "bankruptcy", "deficit_turns": deficit},
                level=logging.CRITICAL
            )
        elif deficit > 0:
            print(f"      ⚠️ 国库赤字（第{deficit}回合），再持续{limit - deficit}回合将导致共和覆灭")

        # 原有其他胜利条件检查（军团、行省起义、派系独裁等）保持不变
        print(f"\n   🏆 胜利/失败条件检查:")

        # 1. 军团全军覆没（原代码已存在，此处仅示意）
        ms = self.state.get_military_system()
        if ms:
            all_legions = ms.get_all_legions()
            if all_legions and all(l.status.name == "DESTROYED" for l in all_legions):
                print(f"      💀 所有军团已被消灭，共和覆灭！")

        # 2. 行省大范围暴动
        provinces = self.state.get_all_provinces()
        if provinces:
            revolt_provinces = [p for p in provinces if p.grievance >= 3]
            if len(revolt_provinces) > len(provinces) // 2:
                print(f"      💀 超过半数行省爆发起义，共和覆灭！")

        # 3. 派系独裁（元老院影响力占比≥70%）
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

        # 4. 意大利本土民怨3级
        italy = self.state.get_province(0)
        if italy and italy.grievance == 3:
            print(f"      💀 意大利本土民怨已达3级，若不在本年度内处理，共和国将面临覆灭！")

        # 5. 元老院主导派系
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

