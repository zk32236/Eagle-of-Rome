# src/ui/commands/phase_population.py
"""
人口阶段命令 - 多步骤交互版本
支持手动庆典、投票，自动/手动模式切换
"""
import sys
import logging
from typing import List, Optional, Dict

from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.player import PlayerType
from src.core.entities.war import WarStatus
from src.core.entities.contract import ContractStatus
from src.api import population_api
from src.api import figure_api
from src.core.i18n import i18n
from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
from src.core.deciders.impl.auto_vote_decider import AutoVoteDecider


class PopulationCommand(Command):
    """人口阶段命令 - 支持多步骤玩家交互"""

    name = "population"
    aliases = ["p"]
    description = "执行人口阶段 (Population Phase) - 举办庆典、投票选举、凯旋式"

    def __init__(self, state):
        super().__init__(state)
        self._step = 0
        self._players = []
        self._current_player_index = 0
        self._auto_mode = False
        self._resolution_done = False
        self.terms = TerminologyService.get()

        from src.ui.processors.auto_player_processor import AutoPlayerProcessor
        from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
        from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
        from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
        from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
        from src.core.deciders.impl.auto_fleet_disband_decider import AutoFleetDisbandDecider

        self.auto_processor = AutoPlayerProcessor(
            state,
            retirement_decider=AutoRetirementDecider(state),
            recruitment_decider=AutoRecruitmentDecider(),
            bid_decider=AutoBidDecider(),
            triumph_decider=AutoTriumphDecider()
        )
        self.auto_processor.festival_decider = AutoFestivalDecider()
        self.auto_processor.vote_decider = AutoVoteDecider()
        self.fleet_disband_decider = AutoFleetDisbandDecider()
        self._startup_done = False
        self._pre_election_influences = {}  # 存储选举前各派系影响力

    # ---------- 核心执行 ----------
    def execute(self, args: List[str]) -> bool:
        if not self.state.is_phase_executed("forum"):
            print("⚠️ 必须先执行广场阶段 (forum)", file=sys.stderr, flush=True)
            return False

        if self.state.is_phase_executed("population"):
            print("⚠️ 人口阶段在本回合已执行过", file=sys.stderr, flush=True)
            return False

        self._auto_mode = self.state.config.get("testing.auto_population", False)

        # 初始化状态机
        self._step = 0
        self._players = self._get_step_players()
        self._current_player_index = 0
        self._resolution_done = False
        self._startup_done = False

        while self._step < 4:  # 原5改为4
            if self._step == 0:
                self._handle_step_0()
            elif self._step == 1:
                self._handle_step_1()  # 合并后的庆典+投票环节
            elif self._step == 2:
                self._handle_step_2()  # 公示环节（原步骤3）
            elif self._step == 3:
                self._handle_step_3()  # 完成环节（原步骤4）

        self.state.mark_phase_executed("population")
        return True

    # ---------- 步骤0：公告 ----------
    def _handle_step_0(self):
        """公告环节：显示阶段预览和凯旋信息"""

        # 只在第一次进入步骤0时执行凯旋、解散等操作
        if not self._startup_done:
            # 凯旋信息,解散军团
            # 打印军团凯旋标题
            print("=" * 58)
            print("   🏛️  Legions Return Rome from Battlefield")
            print("=" * 58)
            self._process_legion_disbandment_and_triumphs()
            if self.state.naval_system:
                disbanded = self.state.naval_system.disband_unused_fleets(
                    self.state.turn.turn_number,
                    self.fleet_disband_decider
                )
                if disbanded:
                    print(f"      ⚓ 舰队 {disbanded} 已解散（无需要海战的战争）")


            # 清理广场中未被招募的人物
            curia = self.state.curia
            if not curia.is_empty():
                ids_to_remove = [fig.id for fig in curia.get_all_available()]
                for fid in ids_to_remove:
                    if fid in self.state._members:
                        del self.state._members[fid]
                curia.clear()
                print(f"      🗑️ {len(ids_to_remove)} 名未被招募的人物已从罗马消失，不知去向。")

            # 卸任所有现任官员（不包括战场指挥官）
            election_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
            for office_type in election_order:
                self._remove_office_holders(office_type)

            # 转换战场指挥官
            self._convert_battlefield_commanders()

            print()  # 空行分隔
            self._startup_done = True

        # 打印操作提示
        print("\n🔧 本阶段可操作(ANYONE)：")
        print("   1. next/n → 进入庆典环节")
        sys.stdout.flush()

        if self._auto_mode:
            self._step += 1
            return

        while True:
            print("\n> 请输入操作(ANYONE): ", end="", flush=True)
            cmd_input = input().strip()
            if not cmd_input:
                continue
            parts = cmd_input.split()
            cmd = parts[0].lower()
            if cmd in ("next", "n"):
                self._step += 1
                break
            else:
                print(i18n.get("error_unknown_command"), file=sys.stderr, flush=True)


    def _remove_office_holders(self, office_type: str):
        """
        卸任所有现任官员（不包括战场指挥官，由 _convert_battlefield_commanders 处理）。
        """
        current_turn = self.state.turn.turn_number
        for fig in self.state.get_living_members():
            if fig.office != office_type:
                continue

            # 战场指挥官由专门方法处理，这里跳过
            if fig.is_absent and office_type in ('consul', 'praetor'):
                continue

            # 普通卸任
            fig.add_office_history(office_type, current_turn - 1, current_turn)
            fig.office = f"ex-{office_type}"
            fig.update_influence()

            if office_type == "consul" and fig.id in self.state.turn.leader_ids:
                self.state.turn.leader_ids.remove(fig.id)

    # ---------- 步骤1：庆典环节 ----------
    def _handle_step_1(self):
        """合并环节：玩家可进行庆典和投票"""
        # 记录进入环节前的各派系影响力（用于后续对比）
        pre_influences = self._get_faction_influences()
        self._pre_election_influences = pre_influences

        # 重置玩家列表，确保从第一个玩家开始
        player_id = self._get_current_player_id()
        if not player_id:
            self._step += 1
            return
        player = self.state.get_player(player_id)
        if not player:
            self._step += 1
            return

        if self._auto_mode:
            # 自动模式：打印 UI、执行自动庆典和投票，但不输出影响力表格
            print("\n" + "=" * 58)
            print("   🏛️  ELECTIONS Campaign")
            print("=" * 58)

            # 显示当前影响力
            print("\n   📊 各派系影响力：\t\t当前")
            for faction in self.state.factions.values():
                val = pre_influences.get(faction.id, 0)
                print(f"      {faction.name}:\t\t{val}")

            # 打印候选人列表
            result = population_api.get_candidates(self.state)
            if result["success"] and result["message"]:
                print(result["message"])
            else:
                print("\n   📋 当前无候选人")

            # 执行自动庆典和投票
            for player in self.state.get_all_players():
                faction = self.state.get_faction(player.faction_id)
                if faction:
                    self.auto_processor.process_festival(player.player_id, faction, bypass_permission=True)
            for player in self.state.get_all_players():
                faction = self.state.get_faction(player.faction_id)
                if faction:
                    self.auto_processor.process_vote(player.player_id, faction, bypass_permission=True)

            # 统计总花费（仅用于内部，不打印表格）
            total_spent = sum(amount for _, _, amount in self.state._population_pending.get("campaigns", []))
            # 不打印影响力表格，直接进入下一步
            self._step += 1
            return

        # 手动模式
        bypass = self.state.config.get("testing.bypass_player_check", False)
        if bypass or player.player_type == PlayerType.HUMAN:
            # 手动模式：先显示“ELECTIONS Campaign”标题和当前影响力
            print("\n" + "=" * 58)
            print("   🏛️  ELECTIONS Campaign")
            print("=" * 58)
            print("\n   📊 各派系影响力：\t\t当前")
            for faction in self.state.factions.values():
                val = pre_influences.get(faction.id, 0)
                print(f"      {faction.name}:\t\t{val}")

            # 打印候选人列表和操作界面
            self._print_ui_04_1(player_id, player.faction_id)

            while True:
                print(f"\n> 请输入操作(PLAYER {player_id}): ", end="", flush=True)
                cmd_input = input().strip()
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                args = parts[1:]

                if cmd in ("next", "n"):
                    next_id = self._next_player()
                    if next_id:
                        print(i18n.get("info_next_player", player=next_id), flush=True)
                        break
                    else:
                        # 所有玩家已完成，不打印影响力表格，直接进入下一步
                        self._step += 1
                        return
                elif cmd == "campaign":
                    self._handle_campaign(args)
                elif cmd == "vote":
                    self._handle_vote(args)
                elif cmd == "investigate":
                    self._handle_investigate(args)
                else:
                    print(i18n.get("error_unknown_command"), file=sys.stderr, flush=True)
        else:
            # AI玩家自动处理（手动模式下遇到AI玩家进入此分支）
            faction = self.state.get_faction(player.faction_id) if player else None
            self.auto_processor.process_festival(player.player_id, faction, bypass_permission=True)
            self.auto_processor.process_vote(player.player_id, faction, bypass_permission=True)
            self._next_player()
            if self._current_player_index >= len(self._players):
                # 所有玩家已完成，不打印表格
                self._step += 1

    def _auto_mode_festival_and_vote(self):
        """全自动模式：为所有玩家依次执行庆典和投票（绕过权限）"""
        for player in self.state.get_all_players():
            faction = self.state.get_faction(player.faction_id)
            if faction:
                self.auto_processor.process_festival(player.player_id, faction, bypass_permission=True)
        for player in self.state.get_all_players():
            faction = self.state.get_faction(player.faction_id)
            if faction:
                self.auto_processor.process_vote(player.player_id, faction, bypass_permission=True)

    def _print_ui_04_1(self, player_id: str, faction_id: str):
        """打印合并环节UI（庆典+投票）"""
        faction = self.state.get_faction(faction_id)
        faction_name = faction.name if faction else "未知"
        print("\n############################################################")
        print(f" UI-04-1 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 人口阶段 [4/7]")
        print("############################################################")
        print("\n--- 庆典环节 ---")
        print("举办庆典可以提升候选人在选民中的声望，但需要从个人财富中支出。")
        print("每花费1塔兰特，增加1点人气，并提升影响力。")

        # 显示候选人列表
        result = population_api.get_candidates(self.state)
        if result["success"] and result["message"]:
            print(result["message"])

        # 显示本派系资金
        if faction:
            print(f"\n   💰 派系 {faction_name} 资金: {faction.treasury}")

        print(f"\n🔧 本阶段可操作(PLAYER {player_id} {faction_name})：")
        print("   1. investigate → 查看人物私库余额")
        print("   2. campaign <人物ID> <金额> → 举办庆典")
        print("   3. vote <公职> <人物ID> → 投票")
        print("   4. next/n → 下一个玩家")
        sys.stdout.flush()

    def _handle_campaign(self, args):
        if len(args) != 2:
            print(i18n.get("error_usage_campaign", default="用法: campaign <人物ID> <金额>"), file=sys.stderr, flush=True)
            return
        try:
            fig_id = int(args[0])
            amount = int(args[1])
        except ValueError:
            print(i18n.get("error_invalid_id"), file=sys.stderr, flush=True)
            return

        player_id = self._get_current_player_id()
        if not player_id:
            return
        result = population_api.campaign(self.state, player_id, fig_id, amount)
        print(result["message"], flush=True)

    def _handle_vote(self, args):
        if len(args) != 2:
            print(i18n.get("error_usage_vote", default="用法: vote <公职> <人物ID>"), file=sys.stderr, flush=True)
            return
        office = args[0].lower()
        try:
            fig_id = int(args[1])
        except ValueError:
            print(i18n.get("error_invalid_id"), file=sys.stderr, flush=True)
            return
        player_id = self._get_current_player_id()
        if not player_id:
            return
        result = population_api.vote(self.state, player_id, office, fig_id)
        print(result["message"], flush=True)

    # ---------- 步骤3：公示环节 ----------
    def _handle_step_2(self):
        """公示环节：统计选举结果，执行凯旋、军团解散等"""
        if not self._resolution_done:
            # 打印 UI_04-2 标题（手动模式）
            if not self._auto_mode:
                self._print_ui_04_2()
            self._do_resolution()
            self._resolution_done = True
        if self._auto_mode:
            self._step += 1
            return
        while True:
            print("\n🔧 本阶段可操作(ANYONE):", flush=True)
            print("   1. next/n → 进入元老院阶段", flush=True)
            print("\n> 请输入操作(ANYONE): ", end="", flush=True)
            cmd_input = input().strip()
            if not cmd_input:
                continue
            parts = cmd_input.split()
            cmd = parts[0].lower()
            if cmd in ("next", "n"):
                self._step += 1
                break
            else:
                print(i18n.get("error_unknown_command"), file=sys.stderr, flush=True)

    def _print_ui_04_2(self):
        """打印选举结果公示 UI 标题"""
        print("\n############################################################")
        print(f" UI_04-2 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 人口阶段 [4/7]")
        print("############################################################")
        print()  # 空行分隔

    def _do_resolution(self):
        """执行公示结算：选举统计、凯旋、军团解散等"""
        # 1. 执行选举统计
        result = population_api.resolve_election(self.state)
        if result["message"]:
            print(result["message"])

        # 2. 手动模式下打印选举后影响力表格（选举前 → 选举后）
        if not self._auto_mode and self._pre_election_influences:
            post_influences = self._get_faction_influences()
            total_spent = sum(amount for _, _, amount in self.state._population_pending.get("campaigns", []))
            self._print_influence_table(self._pre_election_influences, post_influences, total_spent, total_spent)

        # 3. 清除临时数据
        self.state._population_pending["campaigns"] = []
        self.state._population_pending["votes"] = []
        self._pre_election_influences = {}

    def _process_legion_disbandment_and_triumphs(self):
        """处理军团解散和凯旋式（仅执行一次）"""
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()
        if not ws or not ms:
            return

        for war in ws._war_discard:
            if war.status != WarStatus.RESOLVED:
                continue

            if war.triumph_approved:
                commander_id = war.triumph_commander_id or war.commander_id
                commander = self.state.get_member(commander_id) if commander_id else None
                if commander and not commander.is_dead:
                    print(f"      🏛️ {commander.name} 的军团举行凯旋式！")
                    self.state.log_event(
                        f"凯旋式: {commander.name} 举行凯旋",
                        extra={"type": "triumph", "commander_id": commander.id, "war_id": war.id}
                    )
                    # 重置标记，避免重复
                    war.set_triumph_approved(False)

            if war.legion_numbers:
                disbanded, errors = ms.disband_legions_for_war(war.legion_numbers)
                if disbanded > 0:
                    print(f"      解散 {disbanded} 个参与 {war.name} 的军团")
                for err in errors:
                    print(f"      ⚠️ {err}")
                war.clear_legion_numbers()

        if ws._legions_to_disband:
            disbanded, errors = ms.disband_legions_for_war(ws._legions_to_disband)
            if disbanded > 0:
                print(f"      解散 {disbanded} 个从降级战争返回的军团")
            for err in errors:
                print(f"      ⚠️ {err}")
            ws._legions_to_disband.clear()

    def _convert_battlefield_commanders(self):
        """战场指挥官转换（支持无战争情况）"""
        current_turn = self.state.turn.turn_number
        war_system = self.state.get_war_system()
        if not war_system:
            return

        for figure in self.state.get_living_members():
            if not figure.is_absent:
                continue
            if figure.office not in ('consul', 'praetor'):
                continue

            old_office = figure.office
            war = war_system.get_war_by_commander(figure.id)

            # 确定任职开始回合
            assigned_turn = (war.commander_assigned_turn if war and war.commander_assigned_turn is not None
                             else current_turn - 1)

            # 添加历史记录（使用 assigned_turn 和结束回合 current_turn-1）
            figure.add_office_history(old_office, assigned_turn, current_turn - 1)

            # 转换官职
            new_office = 'proconsul' if old_office == 'consul' else 'propraetor'
            figure.office = new_office
            figure.update_influence()

            # 如果有战争，更新其 commander_assigned_turn
            if war:
                war.set_commander_assigned_turn(current_turn)

            print(f"      🔄 战场指挥官 {figure.name} 转为 {new_office}，继续指挥战争。")

    # ---------- 步骤4：完成 ----------
    def _handle_step_3(self):
        """完成环节：标记阶段结束"""
        print("\n--- 人口阶段完成 ---", flush=True)
        self._step += 1

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

    def _get_step_players(self) -> List[str]:
        """获取当前步骤的玩家列表（所有玩家）"""
        return [p.player_id for p in self.state.get_all_players()]

    def _next_player(self) -> Optional[str]:
        """切换到下一个玩家，返回新玩家ID，如果已轮完则返回None"""
        if not self._players:
            return None
        self._current_player_index += 1
        if self._current_player_index >= len(self._players):
            return None
        return self._players[self._current_player_index]

    def _get_current_player_id(self) -> Optional[str]:
        """获取当前正在操作的玩家ID"""
        if 0 <= self._current_player_index < len(self._players):
            return self._players[self._current_player_index]
        return None

    def _handle_investigate(self, args):
        """复用原有 investigate 逻辑（简化）"""
        if len(args) == 0:
            # 显示本派系人物列表
            player_id = self._get_current_player_id()
            if not player_id:
                return
            player = self.state.get_player(player_id)
            if not player:
                return
            faction = self.state.get_faction(player.faction_id)
            if not faction:
                return
            members = faction.get_members(self.state)
            print("\n================================================================================")
            print(f"   👥 {faction.name} 存活派系人物列表")
            print("================================================================================")
            for m in members:
                print(f"      🟢 ID:{m.id} {m.get_formal_name()} 影响力:{m.influence} 财富:{m.wealth}")
        elif len(args) == 1:
            try:
                fig_id = int(args[0])
            except ValueError:
                print(i18n.get("error_invalid_id"), file=sys.stderr, flush=True)
                return
            result = figure_api.get_figure_info(self.state, fig_id)
            print(result["message"])
        else:
            print(i18n.get("error_usage_investigate"), file=sys.stderr, flush=True)