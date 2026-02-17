# src/core/phases/senate_phase.py - MVP 0.4.5 完整版

import random
from typing import Dict, List, Optional, Tuple
from core.game_state import GameState
from core.localization import TerminologyService, GamePhase
from core.entities.contract import ContractType, ContractStatus


class SenatePhase:
    """元老院阶段 - MVP 0.4.5：公职选举优先"""

    def __init__(self):
        self.phase_id = GamePhase.SENATE

    def execute(self, state: GameState) -> bool:
        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_senate} Phase (Year {abs(state.turn.year)} BC) ---")

        # ========== 第1步：公职选举（按优先级）==========
        print(f"\n{'=' * 50}")
        print("   🏛️  MAGISTRATE ELECTIONS")
        print(f"{'=' * 50}")

        election_order = ["consul", "praetor", "quqaestor"]

        for office_type in election_order:
            count = state.get_offices_per_election(office_type)
            print(f"\n   Electing {office_type.upper()} ({count} seat(s)):")

            for i in range(count):
                winner = self._elect_single_magistrate(state, office_type, terms)
                if winner:
                    emoji = {"consul": "🏛️", "praetor": "⚖️", "quqaestor": "💰"}.get(office_type, "📋")
                    print(f"      {emoji} {winner.name} elected as {office_type}")

                    # 执政官特殊处理：添加到leader_ids（兼容现有逻辑）
                    if office_type == "consul":
                        if winner.id not in state.turn.leader_ids:
                            state.turn.leader_ids.append(winner.id)
                else:
                    print(f"      ⚠️  No eligible candidate for {office_type}")

        # ========== 第2步：更新派系领袖 ==========
        print(f"\n   👑 Faction Leaders Updated:")
        for faction in state.factions.values():
            leader = faction.update_faction_leader(state)
            if leader:
                print(f"      {faction.name}: {leader.name} (Power: {leader.power})")

        # ========== 第3步：主持人确定 ==========
        presiding = state.get_presiding_officer()
        if not presiding:
            state.log_event("Error: No presiding officer!")
            return False

        print(f"\n   🎤 Presiding Officer: {presiding.name}")

        # ========== 第4步：合同处理 ==========
        self._process_pending_contracts(state, terms)

        state.turn.current_phase = "senate"
        return True

    def _elect_single_magistrate(self, state: GameState, office_type: str, terms) -> Optional['Figure']:
        """选举单个官员（增强资质信息打印）"""
        current_turn = state.turn.turn_number

        # 获取候选人数量配置（默认2）
        num_candidates = state.config.get("political_rules", {}).get("candidates_per_election", {}).get(office_type, 2)

        # 1. 筛选合格候选人
        eligible = []
        print(f"\n      Checking eligibility for {office_type.upper()}:")
        print(f"      Requirements: Age≥{self._get_min_age(office_type)}, "
              f"Cooldown={state.get_office_cooldown(office_type)}y, "
              f"Prerequisite={self._get_prerequisite(office_type)}")

        for fig in state.get_living_members():
            can_hold, reason = fig.can_hold_office(office_type, current_turn, state.config)

            # 打印每个人的资质检查结果
            status = "✅" if can_hold else "❌"
            faction = state.get_faction(fig.faction_id)
            fname = faction.name[:8] if faction else "?"

            # 获取资格属性值
            qual_attr = fig.get_qualification_attribute(office_type)
            qual_name = {"consul": "CHA", "praetor": "MAN", "quqaestor": "STR"}.get(office_type, "PWR")

            # 检查前置条件
            has_prereq = self._check_prerequisite(fig, office_type)
            prereq_str = "✓" if has_prereq else "✗"

            # 检查冷却期
            in_cooldown = self._check_in_cooldown(fig, office_type, current_turn, state.config)
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

        # 2. 按资格属性取TOP3
        top_candidates = self._get_top_candidates_by_attribute(eligible, office_type, num_candidates)
        # 显示候选人
        print(f"\n      🏆 TOP {num_candidates} CANDIDATES (by {qual_name}):")



        for idx, c in enumerate(top_candidates, 1):
            attr_val = c.get_qualification_attribute(office_type)
            faction = state.get_faction(c.faction_id)
            pop = c.popularity

            # 显示完整公职历史
            history_str = ", ".join([f"{h.office_type}({h.start_turn})" for h in c.office_history[:3]])

            print(f"         {idx}. {c.name[:20]:20} ({faction.name if faction else '?'})")
            print(f"            {qual_name}:{attr_val:2} | Pop:{pop:2} | "
                  f"Age:{c.age:2} | History: {history_str or 'None'}")

        # 3. 派系人气投票
        votes = self._conduct_popularity_voting(state, top_candidates)

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
            win_faction = state.get_faction(winner.faction_id)
            self._remove_office_holders(state, office_type)
            print(f"\n      ✓ WINNER: {winner.name} ({win_faction.name if win_faction else '?'})")
            print(f"        Power bonus: +{self._get_power_bonus(office_type)}")

            # 任命
            from core.entities.figure import OfficeTerm
            winner.office = office_type
            winner.office_history.append(OfficeTerm(office_type, current_turn))

            # 权力加成
            power_bonus = self._get_power_bonus(office_type)
            winner.power += power_bonus

            # 派系领袖可能变更
            faction = state.get_faction(winner.faction_id)
            if faction:
                old_leader = faction.get_leader(state)
                faction.update_faction_leader(state)
                new_leader = faction.get_leader(state)
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

    def _conduct_popularity_voting(self, state: GameState, candidates: List['Figure']) -> Dict[int, int]:
        """派系人气投票（只看人气总和）"""
        votes = {c.id: 0 for c in candidates}

        for faction in state.factions.values():
            # 计算派系总人气
            faction_pop = sum(
                m.popularity for m in faction.get_members(state)
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

    def _determine_winner(self, votes: Dict[int, int], candidates: List['Figure'], office_type: str) -> Optional[
        'Figure']:
        """判定胜者"""
        if not votes or all(v == 0 for v in votes.values()):
            # 无投票，选资格属性最高的
            return max(candidates, key=lambda c: c.get_qualification_attribute(office_type))

        winner_id = max(votes, key=votes.get)
        return next((c for c in candidates if c.id == winner_id), None)

    def _process_pending_contracts(self, state: GameState, terms):
        """处理待决合同"""
        pending = [c for c in state.contracts if c.status == ContractStatus.PENDING]
        if not pending:
            return

        print(f"\n   📋 Processing {len(pending)} pending contract(s)...")

        for contract in pending:
            if contract.contract_type == ContractType.TAX_FARMING:
                self._vote_tax_contract(state, contract, terms)
            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                self._assign_works_contract(state, contract, terms)

    def _vote_tax_contract(self, state, contract, terms):
        """参议院投票决定包税合同授予"""
        print(f"\n   📊 Voting: {contract.name}")
        print(f"      Cost: {contract.base_cost} | Expected: {contract.expected_profit}")

        # 获取骑士阶层候选人
        # 获取骑士阶层候选人（排除贵族）
        candidates = []
        for faction in state.factions.values():
            for member in faction.get_members(state):
                # ✅ 修改：排除贵族，仅限骑士
                if (not member.is_dead and
                        member.class_tier.value == "eques"):  # 仅骑士
                    candidates.append((member, faction))

        if not candidates:
            print(f"      ⚠️  No eligible {terms.cavalry_class} candidates")
            return

        # 显示候选人
        print(f"\n      Candidates ({terms.cavalry_class}):")
        for idx, (member, faction) in enumerate(candidates[:5], 1):
            print(f"         {idx}. {member.name} ({faction.name}) [Wealth:{member.wealth}]")

        # 简化：自动投票给最富有的骑士（模拟竞标）
        candidates.sort(key=lambda x: x[0].wealth, reverse=True)
        winner, winner_faction = candidates[0]

        # 授予合同
        if contract.award(winner.id, winner_faction.id, state.turn.turn_number):
            winner.wealth -= contract.base_cost
            state.treasury += contract.base_cost
            print(f"\n      ✅ Awarded to {winner.name} ({winner_faction.name})")
            print(f"         {winner.name} paid {contract.base_cost} {terms.currency}")
            print(f"         Treasury +{contract.base_cost} {terms.currency}")

    def _assign_works_contract(self, state, contract, terms):
        """执政官指派工程合同"""
        print(f"\n   🏗️ Assigning: {contract.name}")
        print(f"      Budget: {contract.base_cost} | Profit: {contract.expected_profit}")

        # 获取执政官
        consuls = [state.get_member(cid) for cid in state.turn.leader_ids]
        consuls = [c for c in consuls if c]

        if not consuls:
            print(f"      ⏳ Awaiting {terms.leader_title} election...")
            return

        assigning_consul = consuls[0]
        print(f"      👑 Assigned by {terms.leader_title} {assigning_consul.name}")

        # 获取骑士候选人
        candidates = []
        candidates = []
        for faction in state.factions.values():
            for member in faction.get_members(state):
                # ✅ 修改：排除贵族，仅限骑士
                if (not member.is_dead and
                        member.class_tier.value == "eques"):
                    candidates.append((member, faction))

        if not candidates:
            print(f"      ⚠️  No eligible {terms.cavalry_class} contractors")
            return

        # 显示候选人
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
        if contract.award(winner.id, winner_faction.id, state.turn.turn_number):
            print(f"\n      ✅ Assigned to {winner.name} ({winner_faction.name})")
            print(f"         Reason: {reason}")
            print(f"         Duration: {contract.duration_years} years")

    def _show_seat_standings(self, state: GameState, terms):
        """显示席位占比排名 - MVP 0.4.4（修复比例计算）"""
        # 计算全国总资产
        all_figures = [m for m in state.get_living_members() if not m.is_dead]
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
            faction = state.get_faction(fig.faction_id)
            fname = faction.name if faction else "Unknown"
            assets = fig.get_seat_share()

            # 按比例计算席位
            seat_count = int((assets / total_assets) * 300)
            seat_pct = (assets / total_assets) * 100

            print(f"      {idx}. {fig.name} ({fname}): {seat_count} seats ({seat_pct:.1f}%) "
                  f"[Land:{fig.land} Vet:{fig.veterans}]")

        # 派系总计
        print(f"\n   🏛️  Faction Totals:")
        for faction in state.factions.values():
            members = faction.get_members(state)
            fact_land = sum(m.land for m in members)
            fact_vets = sum(m.veterans for m in members)
            fact_assets = fact_land + fact_vets

            fact_seats = int((fact_assets / total_assets) * 300)
            seat_pct = (fact_assets / total_assets) * 100

            print(f"      {faction.name}: {fact_seats} seats ({seat_pct:.1f}%) "
                  f"[Land:{fact_land} Vet:{fact_vets}]")

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

    def _check_in_cooldown(self, fig: 'Figure', office_type: str, current_turn: int, config: Dict) -> bool:
        """检查是否在冷却期"""
        cooldown = fig.get_office_cooldown_years(office_type, config)
        for term in fig.office_history:
            if term.office_type == office_type:
                years_ago = current_turn - term.start_turn
                if years_ago < cooldown:
                    return True
        return False

    def _get_power_bonus(self, office_type: str) -> int:
        """获取职务权力加成"""
        return {"consul": 5, "praetor": 3, "quqaestor": 2}.get(office_type, 0)

    def _remove_office_holders(self, state, office_type):
        """卸任该职位的所有现任者"""
        for fig in state.get_living_members():
            if fig.office == office_type:
                # 清除职位
                old_office = fig.office
                fig.office = None

                # 🆕 关键：重新计算权力（自动失去加成）
                fig.get_voting_power()  # 这会更新fig.power

                print(f"      📤 {fig.name} steps down as {old_office} (power: {fig.power})")