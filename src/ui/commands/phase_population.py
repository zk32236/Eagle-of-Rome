# src/ui/commands/phase_population.py
"""
人口阶段命令（公民大会） - 优化布局，仅显示关键信息
"""

import random
import logging
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import OfficeTerm, Figure
from src.ui.commands.func_status import get_progress_bar
from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
from src.core.deciders.festival_decider import FestivalDecider
from typing import List, Optional, Dict, TYPE_CHECKING
from collections import defaultdict
from src.core.entities.war import WarStatus

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

        # 清理广场中未被招募的人物
        curia = self.state.curia
        if not curia.is_empty():
            ids_to_remove = [fig.id for fig in curia.get_all_available()]
            for fid in ids_to_remove:
                if fid in self.state._members:
                    del self.state._members[fid]
            curia.clear()
            print(f"      🗑️ {len(ids_to_remove)} 名未被招募的人物已从罗马消失，不知去向。")

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_population} Phase (Year {abs(self.state.turn.year)} BC) ---\n")

        # ========== 1. 军团凯旋与解散 ==========
        print("=" * 58)
        print("   🏛️  Legions Return Rome from Battlefield")
        print("=" * 58)
        self._process_legion_disbandment_and_triumphs()
        print()

        # ========== 2. 卸任所有现任官员（普通卸任） ==========
        election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
        for office_type in election_order:
            self._remove_office_holders(office_type)

        # ===== MVP0.7.01 战场指挥官转换（在普通卸任后执行） =====
        self._convert_battlefield_commanders()

        # ========== 3. 庆典盛况 ==========
        print("=" * 58)
        print("   🏛️  ELECTIONS Campaign")
        print("=" * 58)

        # 计算候选人并按派系分组
        candidates_by_faction = self._compute_candidates_by_faction()

        # 获取庆典前各派系影响力
        pre_influences = self._get_faction_influences()

        # 自动举办庆典（内部统计总花费，不逐条打印）
        total_spent, total_boost = self._process_automatic_festivals(candidates_by_faction)

        # 获取庆典后各派系影响力
        post_influences = self._get_faction_influences()

        # 打印影响力变化表格
        self._print_influence_table(pre_influences, post_influences, total_spent, total_boost)

        # ========== 4. 公职选举 ==========
        print()
        election_results = {}
        for office_type in election_order:
            count = self.state.get_offices_per_election(office_type)
            winners = []
            for i in range(count):
                winner = self._elect_single_magistrate(office_type, terms)
                if winner:
                    winners.append(winner)
                    if office_type == "consul":
                        if winner.id not in self.state.turn.leader_ids:
                            self.state.turn.leader_ids.append(winner.id)
            election_results[office_type] = winners

        # 打印选举结果
        self._print_election_results(election_results)

        # 打印选举后各派系影响力
        post_election_influences = self._get_faction_influences()
        self._print_faction_summary("选举后", post_election_influences)

        self.state.mark_phase_executed("population")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # ================================= MVP 0.7 ===========================================

    # ======== MVP 0.7.1 停战议和 =======

    def _convert_battlefield_commanders(self):
        """
        将战场上（is_absent=True）的执政官/大法官转为 proconsul/propraetor，
        同时记录历史官职。
        """
        current_turn = self.state.turn.turn_number
        war_system = self.state.get_war_system()
        if not war_system:
            return

        # 获取所有存活人物中 is_absent=True 且 office 为 consul/praetor 的
        for figure in self.state.get_living_members():
            if not figure.is_absent:
                continue
            if figure.office not in ('consul', 'praetor'):
                continue

            old_office = figure.office
            # 查找该人物指挥的战争
            war = war_system.get_war_by_commander(figure.id)
            if not war:
                # 理论上不应发生，但若找不到则用当前回合-1作为上任回合的近似
                assigned_turn = current_turn - 1
                self.state.log_event(
                    f"警告：战场指挥官 {figure.name} 找不到指挥的战争，使用默认上任回合",
                    extra={'type': 'truce_conversion_warning', 'figure_id': figure.id},
                    level=logging.WARNING
                )
            else:
                assigned_turn = war.commander_assigned_turn or (current_turn - 1)

            # 记录历史官职（卸任）
            figure.add_office_history(old_office, assigned_turn, current_turn - 1)

            # 授予前线官职
            new_office = 'proconsul' if old_office == 'consul' else 'propraetor'
            figure.office = new_office
            figure.update_influence()

            # ===== 新增：更新战争中的上任回合 =====
            if war:
                war.set_commander_assigned_turn(current_turn)

            # 输出日志
            print(f"      🔄 战场指挥官 {figure.name} 转为 {new_office}，继续指挥战争。")
            self.state.log_event(
                f"战场指挥官 {figure.name} 转为 {new_office}",
                extra={
                    'type': 'commander_conversion',
                    'figure_id': figure.id,
                    'old_office': old_office,
                    'new_office': new_office,
                    'assigned_turn': assigned_turn
                }
            )

    # ================================= MVP 0.1-0.5 =======================================

    # ---------- 辅助方法 ----------
    def _get_faction_influences(self) -> Dict[str, int]:
        """获取各派系当前总影响力"""
        return {faction.id: faction.get_total_influence(self.state) for faction in self.state.factions.values()}

    def _print_influence_table(self, pre: Dict[str, int], post: Dict[str, int], spent: int, boost: int):
        """打印庆典前后影响力表格"""
        print("\n   📊 各派系影响力：\t\t庆典前\t\t庆典后")
        for faction in self.state.factions.values():
            pre_val = pre.get(faction.id, 0)
            post_val = post.get(faction.id, 0)
            print(f"      {faction.name}:\t\t{pre_val}\t\t{post_val}")
        print(f"\n      总计花费 {spent}，增加人气 {boost}")

    def _print_election_results(self, results: Dict[str, List[Figure]]):
        """打印选举结果"""
        print("\n   📋 选举结果：")
        for office_type, winners in results.items():
            emoji = {"consul": "🏛️", "censor": "📜", "praetor": "⚖", "quaestor": "💰", "tribune": "🛡️"}.get(office_type, "📋")
            if len(winners) == 1:
                faction_name = self.state.get_faction(winners[0].faction_id).name if winners[0].faction_id else "无"
                print(f"      {emoji} {office_type.upper()}: {winners[0].name} ({faction_name})")
            else:
                names = ", ".join([f"{w.name}({self.state.get_faction(w.faction_id).name if w.faction_id else '无'})" for w in winners])
                print(f"      {emoji} {office_type.upper()} ({len(winners)} seats): {names}")

    def _print_faction_summary(self, label: str, influences: Dict[str, int]):
        """打印派系影响力汇总"""
        print(f"\n   📊 各派系影响力（{label}）：")
        for faction in self.state.factions.values():
            val = influences.get(faction.id, 0)
            print(f"      {faction.name}: {val}")

    def _process_legion_disbandment_and_triumphs(self):
        """处理军团解散和凯旋式"""
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()
        if not ws or not ms:
            return

        # 遍历所有已解决的战争
        for war in ws._war_discard:
            if war.status != WarStatus.RESOLVED:
                continue

            # 凯旋式
            if war.triumph_approved:
                commander_id = war.triumph_commander_id or war.commander_id
                commander = self.state.get_member(commander_id) if commander_id else None
                if commander and not commander.is_dead:
                    print(f"      🏛️ {commander.name} 的军团举行凯旋式！")
                    self.state.log_event(
                        f"凯旋式: {commander.name} 举行凯旋",
                        extra={"type": "triumph", "commander_id": commander.id, "war_id": war.id}
                    )

            # 解散参与该战争的所有军团
            if war.legion_numbers:
                disbanded, errors = ms.disband_legions_for_war(war.legion_numbers)
                if disbanded > 0:
                    print(f"      解散 {disbanded} 个参与 {war.name} 的军团")
                    self.state.log_event(
                        f"军团解散: 战争 {war.name} 解散 {disbanded} 个军团",
                        extra={"type": "legion_disband", "war_id": war.id, "count": disbanded}
                    )
                for err in errors:
                    print(f"      ⚠️ {err}")
                war.clear_legion_numbers()

        # 处理小胜后需解散的军团
        if ws._legions_to_disband:
            disbanded, errors = ms.disband_legions_for_war(ws._legions_to_disband)
            if disbanded > 0:
                print(f"      解散 {disbanded} 个从降级战争返回的军团")
                self.state.log_event(
                    f"军团解散: 小胜返回军团 {disbanded} 个",
                    extra={"type": "legion_disband", "count": disbanded}
                )
            for err in errors:
                print(f"      ⚠️ {err}")
            ws._legions_to_disband.clear()

    def _process_automatic_festivals(self, candidates_by_faction: Dict[str, List[Figure]]) -> (int, int):
        """自动举办庆典，返回（总花费，总人气增加）"""
        total_spent = 0
        total_boost = 0
        for faction in self.state.factions.values():
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
        return total_spent, total_boost

    def _remove_office_holders(self, office_type: str):
        """
        卸任所有现任官员（不包括战场指挥官，由 _convert_battlefield_commanders 处理）。
        """
        for fig in self.state.get_living_members():
            if fig.office != office_type:
                continue

            # 战场指挥官由专门方法处理，这里跳过
            if fig.is_absent and office_type in ('consul', 'praetor'):
                continue

            # 普通卸任
            fig.add_office_history(office_type, self.state.turn.turn_number - 1, self.state.turn.turn_number)
            fig.office = f"ex-{office_type}"
            fig.update_influence()

            if office_type == "consul" and fig.id in self.state.turn.leader_ids:
                self.state.turn.leader_ids.remove(fig.id)

    def _elect_single_magistrate(self, office_type: str, terms) -> Optional['Figure']:
        """选举单个官员（不打印过程）"""
        current_turn = self.state.turn.turn_number
        num_candidates = self.state.config.get("political_rules", {}).get("candidates_per_election", {}).get(office_type, 2)

        eligible = []
        for fig in self.state.get_living_members():
            can_hold, _ = fig.can_hold_office(office_type, current_turn, self.state.config)
            if can_hold:
                eligible.append(fig)

        if not eligible:
            return None

        top_candidates = self._get_top_candidates_by_attribute(eligible, office_type, num_candidates)
        votes = self._conduct_influence_voting(top_candidates)

        if not votes or all(v == 0 for v in votes.values()):
            return max(top_candidates, key=lambda c: c.get_qualification_attribute(office_type))
        winner_id = max(votes, key=votes.get)
        winner = next((c for c in top_candidates if c.id == winner_id), None)
        if winner:
            winner.office = office_type
            winner.update_influence()

            faction = self.state.get_faction(winner.faction_id)
            if faction:
                faction.update_faction_leader(self.state)

        # ===== 新增日志 =====
        self.state.log_event(
            f"选举结果: {office_type} 当选者 {winner.name} (派系 {faction.name if faction else '无'})",
            extra={"type": "election", "office": office_type, "figure_id": winner.id}
        )

        return winner

    def _get_top_candidates_by_attribute(self, candidates: List['Figure'], office_type: str, n: int) -> List['Figure']:
        sorted_candidates = sorted(
            candidates,
            key=lambda f: f.get_qualification_attribute(office_type),
            reverse=True
        )
        return sorted_candidates[:n]

    def _conduct_influence_voting(self, candidates: List['Figure']) -> dict:
        votes = {c.id: 0 for c in candidates}
        for faction in self.state.factions.values():
            faction_influence = sum(
                m.influence for m in faction.get_members(self.state)
                if not m.is_dead
            )
            own = [c for c in candidates if c.faction_id == faction.id]
            if own:
                target = max(own, key=lambda c: c.influence)
            else:
                target = random.choice(candidates)
            votes[target.id] += faction_influence
        return votes

    def _compute_candidates_by_faction(self) -> Dict[str, List[Figure]]:
        candidates_by_faction = defaultdict(list)
        election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
        for office_type in election_order:
            num_candidates = self.state.config.get("political_rules", {}).get("candidates_per_election", {}).get(
                office_type, 2)
            eligible = self._get_eligible_for_office(office_type)
            if not eligible:
                continue
            top_candidates = self._get_top_candidates_by_attribute(eligible, office_type, num_candidates)
            for fig in top_candidates:
                if fig.faction_id:
                    candidates_by_faction[fig.faction_id].append(fig)
        for faction_id in list(candidates_by_faction.keys()):
            unique = {fig.id: fig for fig in candidates_by_faction[faction_id]}
            candidates_by_faction[faction_id] = list(unique.values())
        return candidates_by_faction

    def _get_eligible_for_office(self, office_type: str) -> List[Figure]:
        current_turn = self.state.turn.turn_number
        eligible = []
        for fig in self.state.get_living_members():
            if fig.is_absent:  # 不在罗马不能参选
                continue
            can_hold, _ = fig.can_hold_office(office_type, current_turn, self.state.config)
            if can_hold:
                eligible.append(fig)
        return eligible