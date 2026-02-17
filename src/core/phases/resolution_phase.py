# src/core/phases/resolution_phase.py

from typing import List, Dict
from core.game_state import GameState
from core.localization import TerminologyService, GamePhase
from core.entities.contract import ContractStatus


class ResolutionPhase:
    """
    决议阶段（Resolution Phase / Revolution Phase）

    核心职责：
    1. 检查胜利条件（MVP 0.3简化）
    2. 处理派系革命/叛乱（高Unrest时）
    3. 清理临时状态，准备下一年
    4. 生成年度总结报告
    5. MVP 0.4.3: 合同过期处理

    这是回合的最后阶段，确保所有状态一致性
    """

    def __init__(self):
        self.phase_id = GamePhase.RESOLUTION

    def execute(self, state: GameState) -> bool:
        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_resolution} Phase (Year {abs(state.turn.year)} BC) ---")

        # 1. 胜利条件检查（MVP 0.3简化）
        victory_check = self._check_victory_conditions(state, terms)

        # 2. 革命/叛乱检查（框架预留）
        revolution_risk = self._check_revolution_risk(state, terms)

        # MVP 0.4.3: 3. 合同过期处理
        self._process_contract_expiration(state, terms)

        # 4. 年度总结
        self._generate_annual_report(state, terms, victory_check, revolution_risk)

        # 5. 清理和准备下一年
        self._prepare_next_year(state)

        state.turn.current_phase = "resolution"
        return True

    def _check_victory_conditions(self, state: GameState, terms) -> Dict:
        """检查胜利条件（MVP 0.3简化版）"""
        print(f"\n   🏆 Victory Conditions Check:")

        # 简化条件：影响力最高的派系
        max_influence = 0
        dominant_faction = None

        for faction in state.factions.values():
            influence = faction.get_total_influence(state)
            if influence > max_influence:
                max_influence = influence
                dominant_faction = faction

        if dominant_faction:
            print(f"      Leading: {dominant_faction.name} ({max_influence} {terms.influence})")
            return {'dominant_faction': dominant_faction, 'influence': max_influence}

        return {}

    def _check_revolution_risk(self, state: GameState, terms) -> List[str]:
        """检查革命风险（框架预留，第5阶段完善）"""
        print(f"\n   ⚠️  {terms.phase_resolution} Risk Assessment:")

        risks = []

        # 检查每个派系的忠诚度/不满度
        for faction in state.factions.values():
            members = faction.get_members(state)
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

    def _process_contract_expiration(self, state: GameState, terms):
        """处理合同过期 - MVP 0.4.3"""
        # 将长期未授予的待决合同标记为过期
        expired_count = 0

        for contract in state.contracts:
            if contract.status == ContractStatus.PENDING:
                # MVP简化：待决合同在3回合后过期
                turns_pending = state.turn.turn_number - getattr(contract, '_created_turn', state.turn.turn_number)
                if turns_pending >= 3:
                    contract.expire()
                    expired_count += 1

        if expired_count > 0:
            print(f"\n   📜 {expired_count} contract(s) expired")

        # 显示合同年度总结
        active = [c for c in state.contracts if c.status == ContractStatus.ACTIVE]
        completed = [c for c in state.contracts if c.status == ContractStatus.COMPLETED]

        if active or completed:
            print(f"\n   📊 Contract Year Summary:")
            if active:
                print(f"      ▶️  Active: {len(active)}")
            if completed:
                print(f"      ✅ Completed this year: {len([c for c in completed if c.remaining_years == 0])}")

    def _generate_annual_report(self, state: GameState, terms, victory: Dict, risks: List):
        """生成年度总结报告"""
        print(f"\n{'=' * 50}")
        print(f"   📜 ANNUAL REPORT - Year {abs(state.turn.year)} BC")
        print(f"{'=' * 50}")

        # 国库状况
        print(f"\n   💰 Treasury: {state.treasury} {terms.currency}")

        # 派系影响力排名
        print(f"\n   📊 {terms.faction} Standings:")
        standings = sorted(
            state.factions.values(),
            key=lambda f: f.get_total_influence(state),
            reverse=True
        )
        for idx, faction in enumerate(standings, 1):
            influence = faction.get_total_influence(state)
            # 修复：is_leader -> is_faction_leader
            # 或者检查是否担任执政官（consul）
            leader = "👑" if any(
                state.get_member(mid) and
                (state.get_member(mid).is_faction_leader or state.get_member(mid).office == "consul")
                for mid in faction.member_ids
            ) else "  "
            print(f"      {idx}. {leader} {faction.name}: {influence} {terms.influence}")

        # 活跃战争
        wars = getattr(state, '_temp_wars', [])
        if wars:
            print(f"\n   ⚔️  Ongoing Conflicts: {len(wars)}")
        else:
            print(f"\n   ☮️  Peace prevails")

        # 合同状况 - MVP 0.4.3
        active_contracts = [c for c in state.contracts if c.status == ContractStatus.ACTIVE]
        if active_contracts:
            total_revenue = sum(c.get_annual_revenue() for c in active_contracts)
            print(f"\n   📜 Active Contracts: {len(active_contracts)} (Annual Revenue: {total_revenue})")

        # 风险提示
        if risks:
            names = [state.get_faction(fid).name for fid in risks if state.get_faction(fid)]
            print(f"\n   🚨 Risk Alert: {', '.join(names)}")

        print(f"\n{'=' * 50}")

    def _prepare_next_year(self, state: GameState):
        """准备下一年（清理临时状态）"""
        # 清理已完成的临时标记
        # 注意：不清理_temp_wars，战争跨年度持续

        print(f"\n   🔄 Preparing for next year...")
        print(f"      Phase tracking reset (done in advance_year)")

    def _apply_annual_decay(self, state: GameState, terms):
        """年度衰减（庆典人气50%，老兵20%）"""
        print(f"\n   📉 Annual Decay:")

        decay_rates = {
            "veterans": 0.20,  # 20%
            "popularity": 0.50  # 50%
        }

        for fig in state.get_living_members():
            changes = []

            # 应用衰减
            fig.apply_annual_decay(decay_rates)

            # 记录变更
            if fig.veterans > 0:
                changes.append(f"vets-{int(fig.veterans * 0.20)}")
            if fig.popularity > 0:
                changes.append(f"pop-{int(fig.popularity * 0.50)}(-50%)")

            # 年龄+1
            fig.age += 1

            if changes:
                print(f"      {fig.name}: {', '.join(changes)}, age {fig.age}")