# src/ui/commands/phase_resolution.py
"""
决议阶段命令 - 处理胜利条件、革命风险、合同过期、年度衰减，准备下一回合
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
        """
        执行决议阶段
        """
        if not self.state.is_phase_executed("combat"):
            print("⚠️ 必须先执行战斗阶段 (combat)")
            return False

        # 检查阶段是否已执行
        if self.state.is_phase_executed("resolution"):
            print("⚠️ 决议阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_resolution} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 1. 胜利条件检查
        victory_check = self._check_victory_conditions(terms)

        # 2. 革命/叛乱检查
        revolution_risk = self._check_revolution_risk(terms)

        # 3. 合同过期处理
        self._process_contract_expiration(terms)

        # 4. 年度总结
        self._generate_annual_report(terms, victory_check, revolution_risk)

        # 5. 清理和准备下一年
        self._prepare_next_year()

        # 6. 年度衰减（原代码中在 _prepare_next_year 后调用 _apply_annual_decay）
        self._apply_annual_decay(terms)

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

    # ---------- 私有方法（移植自原 resolution_phase.py）----------

    def _check_victory_conditions(self, terms) -> Dict:
        """检查胜利条件（MVP 0.3简化版）"""
        print(f"\n   🏆 Victory Conditions Check:")

        max_influence = 0
        dominant_faction = None

        for faction in self.state.factions.values():
            influence = faction.get_total_influence(self.state)
            if influence > max_influence:
                max_influence = influence
                dominant_faction = faction

        if dominant_faction:
            print(f"      Leading: {dominant_faction.name} ({max_influence} {terms.influence})")
            return {'dominant_faction': dominant_faction, 'influence': max_influence}
        return {}

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

    def _generate_annual_report(self, terms, victory: Dict, risks: List):
        """生成年度总结报告"""
        print(f"\n{'=' * 50}")
        print(f"   📜 ANNUAL REPORT - Year {abs(self.state.turn.year)} BC")
        print(f"{'=' * 50}")

        # 国库状况
        print(f"\n   💰 Treasury: {self.state.treasury} {terms.currency}")

        # 派系影响力排名
        print(f"\n   📊 {terms.faction} Standings:")
        standings = sorted(
            self.state.factions.values(),
            key=lambda f: f.get_total_influence(self.state),
            reverse=True
        )
        for idx, faction in enumerate(standings, 1):
            influence = faction.get_total_influence(self.state)
            # 检查是否有成员担任执政官或派系领袖
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