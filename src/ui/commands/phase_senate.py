# src/ui/commands/phase_senate.py
"""
元老院阶段命令 - 负责公职选举、派系领袖更新、合同处理等
"""

import random
from typing import List, Dict, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.figure import OfficeTerm
from src.ui.commands.func_status import get_progress_bar

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.figure import Figure


class SenateCommand(Command):
    """元老院阶段命令"""

    name = "senate"
    aliases = ["s"]
    description = "执行元老院阶段 (Senate Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """
        执行元老院阶段
        """
        # 检查阶段是否已执行
        if self.state.is_phase_executed("senate"):
            print("⚠️ 元老院阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_senate} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # ========== 第1步：公职选举（按优先级）==========
        print(f"\n{'=' * 50}")
        print("   🏛️  MAGISTRATE ELECTIONS")
        print(f"{'=' * 50}")

        election_order = ["consul", "praetor", "quqaestor"]  # 注意拼写与原代码一致

        for office_type in election_order:
            count = self.state.get_offices_per_election(office_type)
            print(f"\n   Electing {office_type.upper()} ({count} seat(s)):")

            for i in range(count):
                winner = self._elect_single_magistrate(office_type, terms)
                if winner:
                    emoji = {"consul": "🏛️", "praetor": "⚖️", "quqaestor": "💰"}.get(office_type, "📋")
                    print(f"      {emoji} {winner.name} elected as {office_type}")

                    # 执政官特殊处理：添加到leader_ids（兼容现有逻辑）
                    if office_type == "consul":
                        if winner.id not in self.state.turn.leader_ids:
                            self.state.turn.leader_ids.append(winner.id)
                else:
                    print(f"      ⚠️  No eligible candidate for {office_type}")

        # ========== 第2步：更新派系领袖 ==========
        print(f"\n   👑 Faction Leaders Updated:")
        for faction in self.state.factions.values():
            leader = faction.update_faction_leader(self.state)
            if leader:
                print(f"      {faction.name}: {leader.name} (Power: {leader.power})")

        # ========== 第3步：主持人确定 ==========
        presiding = self.state.get_presiding_officer()
        if not presiding:
            self.state.log_event("Error: No presiding officer!")
            return False

        print(f"\n   🎤 Presiding Officer: {presiding.name}")

        # ========== 第4步：合同处理 ==========
        self._process_pending_contracts(terms)

        # 兼容旧逻辑：设置当前阶段（如果turn有该属性）
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "senate"

        # 标记阶段已执行
        self.state.mark_phase_executed("senate")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # ---------- 选举相关私有方法 ----------

    def _elect_single_magistrate(self, office_type: str, terms) -> Optional['Figure']:
        """选举单个官员"""
        current_turn = self.state.turn.turn_number

        # 获取候选人数量配置（默认2）
        num_candidates = self.state.config.get("political_rules", {}).get("candidates_per_election", {}).get(office_type, 2)

        # 1. 筛选合格候选人
        eligible = []
        print(f"\n      Checking eligibility for {office_type.upper()}:")
        print(f"      Requirements: Age≥{self._get_min_age(office_type)}, "
              f"Cooldown={self.state.get_office_cooldown(office_type)}y, "
              f"Prerequisite={self._get_prerequisite(office_type)}")

        for fig in self.state.get_living_members():
            can_hold, reason = fig.can_hold_office(office_type, current_turn, self.state.config)

            status = "✅" if can_hold else "❌"
            faction = self.state.get_faction(fig.faction_id)
            fname = faction.name[:8] if faction else "?"

            qual_attr = fig.get_qualification_attribute(office_type)
            qual_name = {"consul": "CHA", "praetor": "MAN", "quqaestor": "STR"}.get(office_type, "PWR")

            has_prereq = self._check_prerequisite(fig, office_type)
            prereq_str = "✓" if has_prereq else "✗"

            in_cooldown = self._check_in_cooldown(fig, office_type, current_turn)
            cooldown_str = "OK" if not in_cooldown else "CD"

            print(f"         {status} {fig.name[:20]:20} ({fname:8}) "
                  f"Age:{fig.age:2} {qual_name}:{qual_attr:2} "
                  f"Prereq:{prereq_str} Cooldown:{cooldown_str} "
                  f"→ {reason if not can_hold else 'Eligible'}")

            if can_hold:
                eligible.append(fig)

        if not eligible:
            print(f"      ⚠️  No eligible candidates for {office_type}!")
            return None

        # 2. 按资格属性取TOP N
        top_candidates = self._get_top_candidates_by_attribute(eligible, office_type, num_candidates)
        qual_name = {"consul": "CHA", "praetor": "MAN", "quqaestor": "STR"}.get(office_type, "PWR")
        print(f"\n      🏆 TOP {num_candidates} CANDIDATES (by {qual_name}):")

        for idx, c in enumerate(top_candidates, 1):
            attr_val = c.get_qualification_attribute(office_type)
            faction = self.state.get_faction(c.faction_id)
            pop = c.popularity

            history_str = ", ".join([f"{h.office_type}({h.start_turn})" for h in c.office_history[:3]])
            print(f"         {idx}. {c.name[:20]:20} ({faction.name if faction else '?'})")
            print(f"            {qual_name}:{attr_val:2} | Pop:{pop:2} | "
                  f"Age:{c.age:2} | History: {history_str or 'None'}")

        # 3. 派系人气投票
        votes = self._conduct_popularity_voting(top_candidates)

        print(f"\n      🗳️  VOTING RESULTS:")
        total_votes = sum(votes.values())
        for cid, v in sorted(votes.items(), key=lambda x: x[1], reverse=True):
            c = next((x for x in top_candidates if x.id == cid), None)
            if c:
                pct = (v / total_votes * 100) if total_votes > 0 else 0
                bar = "█" * int(pct / 5)
                print(f"         {c.name[:20]:20}: {v:4} ({pct:5.1f}%) {bar}")

        # 4. 判定胜者
        winner = self._determine_winner(votes, top_candidates, office_type)

        if winner:
            win_faction = self.state.get_faction(winner.faction_id)
            self._remove_office_holders(office_type)
            print(f"\n      ✓ WINNER: {winner.name} ({win_faction.name if win_faction else '?'})")
            print(f"        Power bonus: +{self._get_power_bonus(office_type)}")

            # 任命
            winner.office = office_type
            winner.office_history.append(OfficeTerm(office_type, current_turn))

            # 权力加成
            power_bonus = self._get_power_bonus(office_type)
            winner.power += power_bonus

            # 派系领袖可能变更
            faction = self.state.get_faction(winner.faction_id)
            if faction:
                old_leader = faction.get_leader(self.state)
                faction.update_faction_leader(self.state)
                new_leader = faction.get_leader(self.state)
                if old_leader != new_leader:
                    print(f"        👑 New faction leader: {new_leader.name} "
                          f"(was {old_leader.name if old_leader else 'None'})")

        return winner

    def _get_top_candidates_by_attribute(self, candidates: List['Figure'], office_type: str, n: int) -> List['Figure']:
        """按资格属性取前N名"""
        sorted_candidates = sorted(
            candidates,
            key=lambda f: f.get_qualification_attribute(office_type),
            reverse=True
        )
        return sorted_candidates[:n]

    def _conduct_popularity_voting(self, candidates: List['Figure']) -> Dict[int, int]:
        """派系人气投票（只看人气总和）"""
        votes = {c.id: 0 for c in candidates}

        for faction in self.state.factions.values():
            # 计算派系总人气
            faction_pop = sum(
                m.popularity for m in faction.get_members(self.state)
                if not m.is_dead
            )

            # 找本派系候选人
            own = [c for c in candidates if c.faction_id == faction.id]

            if own:
                # 投给本派系人气最高的
                target = max(own, key=lambda c: c.popularity)
                reason = f"support_{faction.name}"
            else:
                # 随机投给其他派系
                target = random.choice(candidates)
                reason = "random_support"

            votes[target.id] += faction_pop

        return votes

    def _determine_winner(self, votes: Dict[int, int], candidates: List['Figure'], office_type: str) -> Optional['Figure']:
        """判定胜者"""
        if not votes or all(v == 0 for v in votes.values()):
            # 无投票，选资格属性最高的
            return max(candidates, key=lambda c: c.get_qualification_attribute(office_type))

        winner_id = max(votes, key=votes.get)
        return next((c for c in candidates if c.id == winner_id), None)

    def _remove_office_holders(self, office_type: str):
        """卸任该职位的所有现任者"""
        for fig in self.state.get_living_members():
            if fig.office == office_type:
                old_office = fig.office
                fig.office = None
                fig.get_voting_power()  # 这会更新fig.power
                print(f"      📤 {fig.name} steps down as {old_office} (power: {fig.power})")

    # ---------- 合同处理私有方法 ----------

    def _process_pending_contracts(self, terms):
        """处理待决合同"""
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if not pending:
            return

        print(f"\n   📋 Processing {len(pending)} pending contract(s)...")

        for contract in pending:
            if contract.contract_type == ContractType.TAX_FARMING:
                self._vote_tax_contract(contract, terms)
            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                self._assign_works_contract(contract, terms)

    def _vote_tax_contract(self, contract, terms):
        """参议院投票决定包税合同授予"""
        print(f"\n   📊 Voting: {contract.name}")
        print(f"      Cost: {contract.base_cost} | Expected: {contract.expected_profit}")

        # 获取骑士阶层候选人（排除贵族）
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.class_tier.value == "eques":
                    candidates.append((member, faction))

        if not candidates:
            print(f"      ⚠️  No eligible {terms.cavalry_class} candidates")
            return

        print(f"\n      Candidates ({terms.cavalry_class}):")
        for idx, (member, faction) in enumerate(candidates[:5], 1):
            print(f"         {idx}. {member.name} ({faction.name}) [Wealth:{member.wealth}]")

        # 简化：自动投票给最富有的骑士（模拟竞标）
        candidates.sort(key=lambda x: x[0].wealth, reverse=True)
        winner, winner_faction = candidates[0]

        # 授予合同
        if contract.award(winner.id, winner_faction.id, self.state.turn.turn_number):
            self.state.add_figure_wealth(winner.id, -contract.base_cost)
            self.state.add_treasury(contract.base_cost)
            print(f"\n      ✅ Awarded to {winner.name} ({winner_faction.name})")
            print(f"         {winner.name} paid {contract.base_cost} {terms.currency}")
            print(f"         Treasury +{contract.base_cost} {terms.currency}")

    def _assign_works_contract(self, contract, terms):
        """执政官指派工程合同"""
        print(f"\n   🏗️ Assigning: {contract.name}")
        print(f"      Budget: {contract.base_cost} | Profit: {contract.expected_profit}")

        # 获取执政官
        consuls = [self.state.get_member(cid) for cid in self.state.turn.leader_ids]
        consuls = [c for c in consuls if c]

        if not consuls:
            print(f"      ⏳ Awaiting {terms.leader_title} election...")
            return

        assigning_consul = consuls[0]
        print(f"      👑 Assigned by {terms.leader_title} {assigning_consul.name}")

        # 获取骑士候选人
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.class_tier.value == "eques":
                    candidates.append((member, faction))

        if not candidates:
            print(f"      ⚠️  No eligible {terms.cavalry_class} contractors")
            return

        print(f"\n      Available {terms.cavalry_class}:")
        for idx, (member, faction) in enumerate(candidates[:5], 1):
            mgmt = getattr(member, 'management', 5)
            print(f"         {idx}. {member.name} ({faction.name}) [Mgmt:{mgmt}]")

        # 执政官指派给本派系骑士，否则随机
        own_faction_candidates = [(m, f) for m, f in candidates
                                  if m.faction_id == assigning_consul.faction_id]

        if own_faction_candidates:
            winner, winner_faction = random.choice(own_faction_candidates)
            reason = f"loyal_to_{assigning_consul.faction_id}"
        else:
            winner, winner_faction = random.choice(candidates)
            reason = "political_favor"

        # 授予合同
        if contract.award(winner.id, winner_faction.id, self.state.turn.turn_number):
            print(f"\n      ✅ Assigned to {winner.name} ({winner_faction.name})")
            print(f"         Reason: {reason}")
            print(f"         Duration: {contract.duration_years} years")

    # ---------- 席位占比显示（原代码中未调用，但保留）----------

    def _show_seat_standings(self, terms):
        """显示席位占比排名"""
        # 计算全国总资产
        all_figures = [m for m in self.state.get_living_members() if not m.is_dead]
        total_land = sum(m.land for m in all_figures)
        total_veterans = sum(m.veterans for m in all_figures)
        total_assets = total_land + total_veterans

        if total_assets == 0:
            print(f"\n   📊 No assets for seat distribution")
            return

        print(f"\n   📊 Senate Seat Distribution (Total 300 seats):")
        print(f"      National Assets: Land={total_land}, Veterans={total_veterans}")

        # 按个人资产排序
        sorted_figures = sorted(all_figures, key=lambda m: m.get_seat_share(), reverse=True)[:10]

        for idx, fig in enumerate(sorted_figures, 1):
            faction = self.state.get_faction(fig.faction_id)
            fname = faction.name if faction else "Unknown"
            assets = fig.get_seat_share()
            seat_count = int((assets / total_assets) * 300)
            seat_pct = (assets / total_assets) * 100
            print(f"      {idx}. {fig.name} ({fname}): {seat_count} seats ({seat_pct:.1f}%) "
                  f"[Land:{fig.land} Vet:{fig.veterans}]")

        # 派系总计
        print(f"\n   🏛️  Faction Totals:")
        for faction in self.state.factions.values():
            members = faction.get_members(self.state)
            fact_land = sum(m.land for m in members)
            fact_vets = sum(m.veterans for m in members)
            fact_assets = fact_land + fact_vets
            fact_seats = int((fact_assets / total_assets) * 300)
            seat_pct = (fact_assets / total_assets) * 100
            print(f"      {faction.name}: {fact_seats} seats ({seat_pct:.1f}%) "
                  f"[Land:{fact_land} Vet:{fact_vets}]")


    # ---------- 资格检查辅助方法 ----------

    def _get_min_age(self, office_type: str) -> int:
        """获取最低年龄要求"""
        return {"consul": 40, "praetor": 35, "quqaestor": 30}.get(office_type, 30)

    def _get_prerequisite(self, office_type: str) -> str:
        """获取前置职务要求"""
        return {"consul": "Praetor", "praetor": "Quaestor", "quqaestor": "None"}.get(office_type, "None")

    def _check_prerequisite(self, fig: 'Figure', office_type: str) -> bool:
        """检查是否满足前置职务"""
        if office_type == "consul":
            return any(h.office_type == "praetor" for h in fig.office_history)
        elif office_type == "praetor":
            return any(h.office_type == "quqaestor" for h in fig.office_history)
        return True  # Quaestor无前置

    def _check_in_cooldown(self, fig: 'Figure', office_type: str, current_turn: int) -> bool:
        """检查是否在冷却期"""
        cooldown = fig.get_office_cooldown_years(office_type, self.state.config)
        for term in fig.office_history:
            if term.office_type == office_type:
                years_ago = current_turn - term.start_turn
                if years_ago < cooldown:
                    return True
        return False

    def _get_power_bonus(self, office_type: str) -> int:
        """获取职务权力加成"""
        return {"consul": 5, "praetor": 3, "quqaestor": 2}.get(office_type, 0)