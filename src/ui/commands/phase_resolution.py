# src/ui/commands/phase_resolution.py
"""
决议阶段命令 - 处理胜利条件、革命风险、合同过期、年度衰减，准备下一回合
新增：临时影响力衰减处理
"""
import sys
from typing import List, Dict, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractStatus
from src.ui.commands.func_status import get_progress_bar
from src.core.entities.war import WarStatus

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

        # 1. 胜负条件检查
        self._check_all_conditions(terms)

        # 2. 革命/叛乱检查
        revolution_risk = self._check_revolution_risk(terms)

        # 3. 合同过期处理
        self._process_contract_expiration(terms)

        # 4. 年度总结
        self._generate_annual_report(terms, revolution_risk)

        # 5. 清理和准备下一年
        self._prepare_next_year()

        # 6. 年度衰减（原代码中在 _prepare_next_year 后调用 _apply_annual_decay）
        self._apply_annual_decay(terms)

        # ========== 新增：处理临时影响力衰减 ==========
        self._process_temp_influence_decay()
        # =============================================

        # ========== 新增：处理军团恢复 ==========
        ms = self.state.get_military_system()
        if ms:
            recovered = ms.process_legion_recovery(self.state.turn.turn_number)
            if recovered:
                print(f"      ♻️ 军团 {recovered} 已恢复，可重新征召")
        # =====================================

        # 兼容旧逻辑：设置当前阶段
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "resolution"

        self.state.mark_phase_executed("resolution")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # ---------- 私有方法 ----------

    def _process_temp_influence_decay(self):
        """处理所有存活人物的临时影响力衰减"""
        print(f"\n   📉 临时影响力衰减：")
        any_decay = False
        for fig in self.state.get_living_members():
            before = fig.get_temp_influence()
            if before > 0:
                fig.decay_temp_influence_tasks()
                after = fig.get_temp_influence()
                if before != after:
                    fig.update_influence()
                    any_decay = True
                    # 可以打印详细变化，但为避免刷屏，只在有变化时打印汇总
                    print(f"      {fig.name}: 临时影响力 {before} → {after}")
        if not any_decay:
            print(f"      无临时影响力变化")

    def _check_all_conditions(self, terms):
        """检查所有胜利/失败条件，仅打印信息，不结束游戏"""
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

    def _check_revolution_risk(self, terms) -> List[str]:
        """检查革命风险（框架预留）"""
        print(f"\n   ⚠️  {terms.phase_resolution} Risk Assessment:")

        risks = []
        for faction in self.state.factions.values():
            members = faction.get_members(self.state)
            avg_loyalty = sum(m.loyalty for m in members) / len(members) if members else 5

            if avg_loyalty < 4:
                risk_level = "HIGH"
                emoji = "🔴"
            elif avg_loyalty < 6:
                risk_level = "MODERATE"
                emoji = "🟡"
            else:
                risk_level = "LOW"
                emoji = "🟢"

            print(f"      {emoji} {faction.name}: {risk_level} risk (avg {terms.loyalty}: {avg_loyalty:.1f})")

            if risk_level == "HIGH":
                risks.append(faction.id)

        return risks

    def _process_contract_expiration(self, terms):
        """处理合同过期"""
        expired_count = 0
        for contract in self.state.contracts:
            if contract.status == ContractStatus.PENDING:
                # 简化：待决合同在3回合后过期
                turns_pending = self.state.turn.turn_number - getattr(contract, '_created_turn', self.state.turn.turn_number)
                if turns_pending >= 3:
                    contract.expire()
                    expired_count += 1

        if expired_count > 0:
            print(f"\n   📜 {expired_count} contract(s) expired")

        active = [c for c in self.state.contracts if c.status == ContractStatus.ACTIVE]
        completed = [c for c in self.state.contracts if c.status == ContractStatus.COMPLETED]

        if active or completed:
            print(f"\n   📊 Contract Year Summary:")
            if active:
                print(f"      ▶️  Active: {len(active)}")
            if completed:
                print(f"      ✅ Completed this year: {len([c for c in completed if c.remaining_years == 0])}")

    def _generate_annual_report(self, terms, risks: List):
        """生成年度总结报告（移除胜利条件部分）"""
        print(f"\n{'=' * 50}")
        print(f"   📜 ANNUAL REPORT - Year {abs(self.state.turn.year)} BC")
        print(f"{'=' * 50}")

        # 国库状况
        print(f"\n   💰 Treasury: {self.state.treasury} {terms.currency}")

        # 派系影响力排名（可保留，但不是胜利条件）
        print(f"\n   📊 {terms.faction} Standings:")
        standings = sorted(
            self.state.factions.values(),
            key=lambda f: f.get_total_influence(self.state),
            reverse=True
        )
        for idx, faction in enumerate(standings, 1):
            influence = faction.get_total_influence(self.state)
            leader = "👑" if any(
                self.state.get_member(mid) and
                (self.state.get_member(mid).is_faction_leader or self.state.get_member(mid).office == "consul")
                for mid in faction.member_ids
            ) else "  "
            print(f"      {idx}. {leader} {faction.name}: {influence} {terms.influence}")

        # 活跃战争
        wars = self.state.get_active_wars()
        if wars:
            print(f"\n   ⚔️  Ongoing Conflicts: {len(wars)}")
        else:
            print(f"\n   ☮️  Peace prevails")

        # 合同状况
        active_contracts = [c for c in self.state.contracts if c.status == ContractStatus.ACTIVE]
        if active_contracts:
            total_revenue = sum(c.get_annual_revenue() for c in active_contracts)
            print(f"\n   📜 Active Contracts: {len(active_contracts)} (Annual Revenue: {total_revenue})")

        # 风险提示
        if risks:
            names = [self.state.get_faction(fid).name for fid in risks if self.state.get_faction(fid)]
            print(f"\n   🚨 Risk Alert: {', '.join(names)}")

        print(f"\n{'=' * 50}")

    def _prepare_next_year(self):
        """准备下一年（清理临时状态）"""
        print(f"\n   🔄 Preparing for next year...")
        print(f"      Phase tracking reset (done in advance_year)")

    def _apply_annual_decay(self, terms):
        """年度衰减（庆典人气50%，老兵20%）"""
        print(f"\n   📉 Annual Decay:")

        decay_rates = {
            "veterans": 0.20,
            "popularity": 0.50
        }

        for fig in self.state.get_living_members():
            changes = []

            fig.apply_annual_decay(decay_rates)

            if fig.veterans > 0:
                changes.append(f"vets-{int(fig.veterans * 0.20)}")
            if fig.popularity > 0:
                changes.append(f"pop-{int(fig.popularity * 0.50)}(-50%)")

            fig.age += 1

            if changes:
                print(f"      {fig.name}: {', '.join(changes)}, age {fig.age}")