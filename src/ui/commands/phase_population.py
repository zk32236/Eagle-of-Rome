# src/ui/commands/phase_population.py
"""
人口阶段命令（公民大会） - 处理公职选举、国家状态评估、军团解散、人口事件
"""

import random
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import OfficeTerm, Figure
from src.ui.commands.func_status import get_progress_bar
from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
from src.core.deciders.festival_decider import FestivalDecider
from typing import List, Optional, Dict, TYPE_CHECKING
from collections import defaultdict

if TYPE_CHECKING:
    from src.core.game_state import GameState


class PopulationCommand(Command):
    """人口阶段命令（公民大会）"""

    name = "population"
    aliases = ["p"]
    description = "执行人口阶段 (Population Phase) - 举行公职选举、评估共和国状态、处理军团"

    def __init__(self, state: "GameState", festival_decider: Optional[FestivalDecider] = None):
        super().__init__(state)
        self.festival_decider = festival_decider or AutoFestivalDecider()

    def execute(self, args: List[str]) -> bool:
        if not self.state.is_phase_executed("forum"):
            print("⚠️ 必须先执行广场阶段 (forum)")
            return False

        if self.state.is_phase_executed("population"):
            print("⚠️ 人口阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_population} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 选举顺序
        election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]

        # ========== 1. 卸任所有现任官员（任期一年） ==========
        print(f"\n   📤 所有官员卸任：")
        for office_type in election_order:
            self._remove_office_holders(office_type)

        # 打印卸任后影响力
        self._print_faction_influences("庆典前")

        # ========== 2. 计算候选人并按派系分组 ==========
        candidates_by_faction = self._compute_candidates_by_faction()

        # ========== 3. 自动举办庆典 ==========
        self._process_automatic_festivals(candidates_by_faction)

        # 打印庆典后影响力
        self._print_faction_influences("庆典后")

        # ========== 4. 公职选举 ==========
        print(f"\n{'=' * 50}")
        print("   🏛️  MAGISTRATE ELECTIONS")
        print(f"{'=' * 50}")

        for office_type in election_order:
            count = self.state.get_offices_per_election(office_type)
            print(f"\n   Electing {office_type.upper()} ({count} seat(s)):")

            for i in range(count):
                winner = self._elect_single_magistrate(office_type, terms)
                if winner:
                    emoji = {"consul": "🏛️", "censor": "📜", "praetor": "⚖️", "quaestor": "💰", "tribune": "🛡️"}.get(
                        office_type, "📋")
                    print(f"      {emoji} {winner.name} elected as {office_type}")

                    if office_type == "consul":
                        if winner.id not in self.state.turn.leader_ids:
                            self.state.turn.leader_ids.append(winner.id)
                else:
                    print(f"      ⚠️  No eligible candidate for {office_type}")

            # 每个官职选举完毕后打印一次影响力
            self._print_faction_influences(f"选举后 ({office_type})")

        # ========== 5. 原有国家状态评估、军团解散、人口事件 ==========
        republic_state = self._calculate_republic_state(terms)
        print(f"\n   🏛️  State of the Republic: {republic_state}")
        self._process_legion_disbandment(terms, republic_state)
        self._process_population_events(terms)

        self.state.mark_phase_executed("population")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    def _print_faction_influences(self, label: str):
        """打印当前所有派系的总影响力"""
        print(f"\n   📊 {label} 各派系影响力：")
        for faction in self.state.factions.values():
            total = faction.get_total_influence(self.state)
            print(f"      {faction.name}: {total}")

    def _compute_candidates_by_faction(self) -> Dict[str, List[Figure]]:
        """计算所有官职的候选人并按派系分组（去重）"""
        candidates_by_faction = defaultdict(list)
        election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]

        for office_type in election_order:
            # 获取该官职的候选人（前N名）
            num_candidates = self.state.config.get("political_rules", {}).get("candidates_per_election", {}).get(
                office_type, 2)
            eligible = self._get_eligible_for_office(office_type)
            if not eligible:
                continue
            top_candidates = self._get_top_candidates_by_attribute(eligible, office_type, num_candidates)
            for fig in top_candidates:
                if fig.faction_id:
                    candidates_by_faction[fig.faction_id].append(fig)
        # 按派系ID去重（同一人物可能出现在多个官职中，但只需一个实例）
        for faction_id in list(candidates_by_faction.keys()):
            # 用字典去重（基于id）
            unique = {fig.id: fig for fig in candidates_by_faction[faction_id]}
            candidates_by_faction[faction_id] = list(unique.values())
        return candidates_by_faction

    def _get_eligible_for_office(self, office_type: str) -> List[Figure]:
        """获取某个官职的所有合格候选人（不考虑人数限制）"""
        current_turn = self.state.turn.turn_number
        eligible = []
        for fig in self.state.get_living_members():
            can_hold, _ = fig.can_hold_office(office_type, current_turn, self.state.config)
            if can_hold:
                eligible.append(fig)
        return eligible

    def _process_automatic_festivals(self, candidates_by_faction: Dict[str, List[Figure]]):
        """为所有派系的候选人自动举办庆典（调试阶段，玩家派系也自动执行）"""
        print(f"\n   🎉 自动举办庆典：")
        total_spent = 0
        total_boost = 0
        for faction in self.state.factions.values():
            # 调试阶段：所有派系都自动庆典（无论是否玩家）
            candidates = candidates_by_faction.get(faction.id, [])
            if not candidates:
                continue
            decisions = self.festival_decider.decide_festivals(faction, candidates, self.state)
            for fig_id, amount in decisions.items():
                figure = self.state.get_member(fig_id)
                if not figure or figure.is_dead or figure.wealth < amount:
                    continue
                figure.wealth -= amount
                figure.add_popularity(amount)
                figure.update_influence()
                total_spent += amount
                total_boost += amount
                print(
                    f"      {faction.name} 的 {figure.get_formal_name()} 花费 {amount} 举办庆典，人气 +{amount}，新影响力 {figure.influence}")
        if total_spent > 0:
            print(f"      总计花费 {total_spent}，增加人气 {total_boost}")
        else:
            print(f"      无人举办庆典")

    # ---------- 选举相关私有方法（从 phase_senate.py 移植）----------

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
            qual_name = {"consul": "CHA", "praetor": "MAN", "quaestor": "STR"}.get(office_type, "PWR")

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
        qual_name = {"consul": "CHA", "praetor": "MAN", "quaestor": "STR"}.get(office_type, "PWR")
        print(f"\n      🏆 TOP {num_candidates} CANDIDATES (by {qual_name}):")

        for idx, c in enumerate(top_candidates, 1):
            attr_val = c.get_qualification_attribute(office_type)
            faction = self.state.get_faction(c.faction_id)
            pop = c.popularity

            history_str = ", ".join([f"{h.office_type}({h.start_turn})" for h in c.office_history[:3]])
            print(f"         {idx}. {c.name[:20]:20} ({faction.name if faction else '?'})")
            print(f"            {qual_name}:{attr_val:2} | Pop:{pop:2} | "
                  f"Age:{c.age:2} | History: {history_str or 'None'}")

        # 3. 派系影响力投票
        votes = self._conduct_influence_voting(top_candidates)

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
            self._remove_office_holders(office_type)  # 先卸任同职位的人
            print(f"\n      ✓ WINNER: {winner.name} ({win_faction.name if win_faction else '?'})")

            # 任命
            winner.office = office_type
            winner.office_history.append(OfficeTerm(office_type, current_turn))
            winner.update_influence()  # 重新计算影响力（包括公职加成）

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

    def _conduct_influence_voting(self, candidates: List['Figure']) -> dict:
        """派系影响力投票（看影响力总和）"""
        votes = {c.id: 0 for c in candidates}

        for faction in self.state.factions.values():
            # 计算派系总影响力
            faction_influence = sum(
                m.influence for m in faction.get_members(self.state)
                if not m.is_dead
            )

            # 找本派系候选人
            own = [c for c in candidates if c.faction_id == faction.id]

            if own:
                # 投给本派系影响力最高的
                target = max(own, key=lambda c: c.influence)
            else:
                # 随机投给其他派系
                target = random.choice(candidates)

            votes[target.id] += faction_influence

        return votes

    def _determine_winner(self, votes: dict, candidates: List['Figure'], office_type: str) -> Optional['Figure']:
        """判定胜者"""
        if not votes or all(v == 0 for v in votes.values()):
            # 无投票，选资格属性最高的
            return max(candidates, key=lambda c: c.get_qualification_attribute(office_type))

        winner_id = max(votes, key=votes.get)
        return next((c for c in candidates if c.id == winner_id), None)

    def _remove_office_holders(self, office_type: str):
        """卸任该职位的所有现任者，并设置前任公职"""
        for fig in self.state.get_living_members():
            if fig.office == office_type:
                # 记录历史（结束回合）
                fig.add_office_history(office_type, self.state.turn.turn_number - 1, self.state.turn.turn_number)
                # 设置为前任公职
                fig.office = f"ex-{office_type}"
                fig.update_influence()
                print(f"      📤 {fig.name} steps down as {office_type}, now {fig.office} (influence: {fig.influence})")

    def _get_min_age(self, office_type: str) -> int:
        """从配置获取最低年龄要求"""
        return self.state.get_min_age(office_type)

    def _get_prerequisite(self, office_type: str) -> str:
        prereq = {
            "consul": "Praetor",
            "praetor": "Quaestor",
            "quaestor": "None",
            "censor": "Consul",
            "tribune": "None"
        }.get(office_type, "None")
        return prereq

    def _check_prerequisite(self, fig: 'Figure', office_type: str) -> bool:
        if office_type == "consul":
            return any(h.office_type == "praetor" for h in fig.office_history)
        elif office_type == "praetor":
            return any(h.office_type == "quaestor" for h in fig.office_history)
        elif office_type == "censor":
            return any(h.office_type == "consul" for h in fig.office_history)
        elif office_type == "tribune":
            return True  # 无前置
        return True

    def _check_in_cooldown(self, fig: 'Figure', office_type: str, current_turn: int) -> bool:
        """检查是否在冷却期"""
        cooldown = fig.get_office_cooldown_years(office_type, self.state.config)
        for term in fig.office_history:
            if term.office_type == office_type:
                years_ago = current_turn - term.start_turn
                if years_ago < cooldown:
                    return True
        return False

    # ---------- 原有国家状态评估、军团解散、人口事件方法（保持不变）----------

    def _calculate_republic_state(self, terms) -> str:
        """计算国家状态"""
        treasury = self.state.treasury
        has_wars = len(self.state.get_active_wars()) > 0

        # 获取军事系统信息
        ms = self.state.get_military_system()
        legion_pressure = 0
        if ms:
            active = len(ms.get_active_legions()) if hasattr(ms, 'get_active_legions') else 0
            unraised = len(ms.get_available_legions()) if hasattr(ms, 'get_available_legions') else 0
            legion_pressure = active / 10 if active > 0 else 0

        if treasury < 0 and has_wars:
            state_name = terms.state_bad
            emoji = "🔴"
        elif treasury < 50 or (has_wars and legion_pressure > 0.5):
            state_name = terms.state_tense
            emoji = "🟠"
        elif treasury < 100:
            state_name = terms.state_uneasy
            emoji = "🟡"
        else:
            state_name = terms.state_calm
            emoji = "🟢"

        print(f"   {emoji} Treasury: {treasury} {terms.currency}")
        if has_wars:
            print(f"   ⚔️  Active wars: {len(self.state.get_active_wars())}")
        if ms:
            print(f"   🛡️  Active legions: {len(ms.get_active_legions() if hasattr(ms, 'get_active_legions') else [])}/10")

        return state_name

    def _process_legion_disbandment(self, terms, republic_state: str):
        """处理军团解散"""
        ms = self.state.get_military_system()
        if not ms:
            return

        print(f"\n   🛡️  {terms.legion} Review:")

        # 根据状态决定是否建议解散
        if republic_state == terms.state_bad:
            # Bad状态：强制解散一半军团
            active_legions = ms.get_active_legions() if hasattr(ms, 'get_active_legions') else []
            to_disband = len(active_legions) // 2
            print(f"      🔴 Crisis! Must disband {to_disband} {terms.legion}(s)")
            self._auto_disband(ms, to_disband)

        elif republic_state == terms.state_tense:
            # Tense状态：建议解散
            print(f"      🟠 Tense state: Consider disbanding unassigned {terms.legion}s")
            unassigned = ms.get_unassigned_legions() if hasattr(ms, 'get_unassigned_legions') else []
            if unassigned:
                print(f"      {len(unassigned)} {terms.legion}(s) available for disbandment")

        elif republic_state == terms.state_calm:
            # Calm状态：可以征召新军团
            available = ms.get_available_legions() if hasattr(ms, 'get_available_legions') else []
            if available:
                print(f"      🟢 Calm state: {len(available)} {terms.legion}(s) available for recruitment")

    def _auto_disband(self, ms, count: int):
        """自动解散军团"""
        unassigned = ms.get_unassigned_legions() if hasattr(ms, 'get_unassigned_legions') else []
        disbanded = 0
        for legion in unassigned[:count]:
            if hasattr(ms, 'disband_legion'):
                success, msg = ms.disband_legion(legion.number)
                if success:
                    disbanded += 1
                    print(f"      ⚫ {legion.name} disbanded")
        if disbanded < count:
            terms = TerminologyService.get()
            print(f"      ⚠️  Could only disband {disbanded}/{count} {terms.legion}(s)")

    def _process_population_events(self, terms):
        """处理人口事件"""
        print(f"\n   👥 {terms.phase_population} Events:")
        if random.random() < 0.2:  # 20%概率
            events = [
                "Population growth in rural areas",
                "Urban unrest in the capital",
                "Migration from the provinces",
                "Recruitment drives popular",
                "Veterans demand land grants",
            ]
            event = random.choice(events)
            print(f"      📢 {event}")
        else:
            print("      No significant events")