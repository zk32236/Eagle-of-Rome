# src/ui/commands/phase_senate.py
"""
元老院阶段命令 - 处理合同、更新派系领袖、确定主持人
集成停战草案审批流程（MVP 0.7.1）
"""
import random
import sys
import logging
from src.api import senate_api
from typing import List, TYPE_CHECKING, Optional, Tuple, Any
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractType, ContractStatus
from src.core.deciders.impl.auto_budget_decider import AutoBudgetDecider
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.deciders.impl.auto_senate_vote_decider import AutoSenateVoteDecider
from src.core.entities.war import War, WarStatus
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.war_takeover_decider import WarTakeoverDecider
from src.core.deciders.impl.auto_land_proposal_decider import AutoLandProposalDecider
from src.core.deciders.land_proposal_decider import LandProposalDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.deciders.impl.auto_tribune_veto_decider import AutoTribuneVetoDecider
from src.core.entities.player import PlayerType

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.war import War
    from src.core.entities.contract import Contract


class SenateCommand(Command):
    """元老院阶段命令"""

    name = "senate"
    aliases = ["s"]
    description = "执行元老院阶段 (Senate Phase) - 处理合同、更新派系领袖、确定主持人、审批停战草案"

    def __init__(self, state: "GameState",
                 vote_decider: Optional[SenateVoteDecider] = None,
                 takeover_decider: Optional[WarTakeoverDecider] = None,
                 land_proposal_deciders: Optional[List[LandProposalDecider]] = None,
                 veto_decider: Optional[TribuneVetoDecider] = None):
        super().__init__(state)
        self.vote_decider = vote_decider if vote_decider is not None else AutoSenateVoteDecider()
        self.budget_decider = AutoBudgetDecider()
        self.takeover_decider = takeover_decider if takeover_decider is not None else AutoWarTakeoverDecider()
        self.land_proposal_deciders = land_proposal_deciders if land_proposal_deciders is not None else [
            AutoLandProposalDecider("populares", "distribution"),
            AutoLandProposalDecider("optimates", "sale")
        ]
        self.veto_decider = veto_decider if veto_decider is not None else AutoTribuneVetoDecider()
        self.proposed_governors = []   # 存储总督任命提案
        self.passed_peace_treaties = []  # 存储通过的停战草案
        self.rejected_peace_treaties = []  # 存储被否决的停战草案（待恢复战争）

        # 状态机变量
        self._step = 0
        self._current_player_index = 0
        self._players = []
        self._auto_mode = state.config.get("testing.auto_senate", True)

        # 步骤间传递的临时数据
        self._passed_wars = []
        self._passed_contracts = []
        self._passed_land_acts = []
        self._peace_proposals = []

    def execute(self, args: List[str]) -> bool:
        # 原有前置检查（是否已执行、是否先执行人口阶段等）保持不变
        if not self.state.is_phase_executed("population"):
            print("⚠️ 必须先执行人口阶段 (population)")
            return False

        if self.state.is_phase_executed("senate"):
            print("⚠️ 元老院阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_senate} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 初始化状态机
        self._step = 0
        self._players = self._get_step_players()
        self._current_player_index = 0
        # 重置临时数据
        self._passed_wars = []
        self._passed_contracts = []
        self._passed_land_acts = []
        self._peace_proposals = []

        # 将游戏状态中的当前玩家设置为元老院阶段的第一个玩家（通常是执政官所属玩家）
        if self._players:
            self.state.set_current_player(self._players[0])

        self._show_current_player_overview()

        # 状态机主循环
        while self._step <= 5:
            if self._step == 0:
                self._handle_step_0()
            elif self._step == 1:
                self._handle_step_1()
            elif self._step == 2:
                self._handle_step_2()
            elif self._step == 3:
                self._handle_step_3()
            elif self._step == 4:
                self._handle_step_4()
            elif self._step == 5:
                self._handle_step_5()

        self.state.mark_phase_executed("senate")
        return True

    # =================================== MVP 0.7 =============================================

    # ==================== 新增：MVP0.7-11 CLI-UI====================

    def _handle_step_0(self):
        # 获取初始信息
        from src.api import senate_api
        result = senate_api.get_senate_initial_info(self.state)
        if result["success"]:
            data = result["data"]
        else:
            data = {}

        # 打印 Senate in Meeting 框
        print("\n==========================================================")
        print("   🏛️  Senate in Meeting")
        print("==========================================================\n")

        # 主持人
        presiding = data.get("presiding_officer")
        if presiding:
            print(f"   🎤 Presiding Officer: {presiding['name']} ({presiding['office']})\n")
        else:
            print("   🎤 Presiding Officer: 无\n")

        # 各派系领袖及影响力
        for leader in data.get("faction_leaders", []):
            print(f"      {leader['faction_name']}: {leader['leader_name']} (Influence: {leader['influence']})")
        print()

        # 战争与和平
        print("   ⚔️ 战争与和平：")
        active_wars = data.get("active_foreign_wars", [])
        war_threats = data.get("war_threats", [])
        pending_peace = data.get("pending_peace_treaties", [])

        if not active_wars and not war_threats and not pending_peace:
            print("\t\t无")
        else:
            # 先显示进行中的外国战争
            for war in active_wars:
                print(f"\t\t{war['name']} 进行中")
            # 再显示威胁战争
            for war in war_threats:
                print(f"\t\t{war['name']} 威胁等级：{war['threat_level']}")
            # 最后显示停战草案
            for peace in pending_peace:
                print(f"\t\t{peace['name']} 停战草案（赔款 {peace['indemnity']}）")
        print()

        # 行省总督空缺
        vacancies = data.get("governor_vacancies", {})
        proconsul = vacancies.get("proconsul", [])
        propraetor = vacancies.get("propraetor", [])
        print("   🏛️ 行省总督空缺:")
        print("\t\tProconsul行省： " + (", ".join([p['province_name'] for p in proconsul]) if proconsul else ""))
        print("\t\tPropraetor行省： " + (", ".join([p['province_name'] for p in propraetor]) if propraetor else ""))
        print()

        # 待审批预算案
        pending_contracts = data.get("pending_contracts", [])
        print("   📋 待审批预算案：")
        if pending_contracts:
            for contract in pending_contracts:
                print(f"\t\t{contract['name']}")
        else:
            print("\t\t无")
        print()

        # 待提交土地法案
        print("   🏞️ 待提交土地法案")
        print("\t\t公地出售法案")
        print("\t\t公地分配法案")
        print()

        if self._auto_mode:
            self._handle_next([])
        else:
            print("🔧 本阶段可操作（ANYONE）：")
            print("   1. investigate → 查询人物详情")
            print("   2. next/n → 进入执政官提案环节")
            while True:
                print("\n> 请输入操作(ANY): ", end="", flush=True)
                cmd_input = input().strip()
                self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                if cmd in ("next", "n"):
                    self._handle_next([])
                    break
                elif cmd == "investigate":
                    # 调用 investigate 命令（复用现有的命令处理或直接调用 figure_api）
                    if len(parts) >= 2:
                        try:
                            fig_id = int(parts[1])
                        except ValueError:
                            print("❌ 人物ID必须是数字", flush=True)
                            continue
                        from src.api import figure_api
                        result = figure_api.get_figure_info(self.state, fig_id)
                        print(result["message"])
                        sys.stdout.flush()
                    else:
                        # 未指定ID，显示当前玩家派系成员列表
                        player = self.state.get_current_player()
                        if player:
                            faction = self.state.get_faction(player.faction_id)
                            if faction:
                                from src.api import figure_api
                                result = figure_api.get_figure_info(self.state)
                                if result["success"]:
                                    members = [f for f in result["data"] if
                                               f["faction_id"] == faction.id and not f.get("is_dead", False)]
                                    if members:
                                        print(
                                            "\n================================================================================")
                                        print(f"   👥 {faction.name} 存活派系人物列表")
                                        print(
                                            "================================================================================")
                                        for m in members:
                                            status = "👑" if m.get("is_faction_leader", False) else "🟢"
                                            tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(
                                                m["class_tier"], "❓")
                                            office_display = m["office"] if m.get("office") and not m[
                                                "office"].startswith("ex-") else "无"
                                            print(
                                                f"{status}{tier_emoji} ID:{m['id']:<3} {m['name']:<25} 派系:{m['faction_id']:<12} 影响力:{m['influence']} 财富:{m['wealth']} 人气:{m['popularity']} 私地:{m['land_private']} 老兵:{m['veterans']} 官职:{office_display}")
                                        sys.stdout.flush()
                                    else:
                                        print(f"派系 {faction.name} 无存活成员", flush=True)
                                else:
                                    print(result["message"], flush=True)
                        else:
                            print("无法获取当前玩家", flush=True)
                else:
                    print("未知命令，支持 investigate <人物ID>、next/n", flush=True)

    def _handle_step_1(self):
        # 清空上一回合的临时数据（提案、投票、否决）
        self.state.clear_senate_pending()

        if self._auto_mode:
            # 获取执政官人物
            consul_figure = None
            for member in self.state.get_living_members():
                if member.office == "consul" and not member.is_absent:
                    consul_figure = member
                    break
            # 若找不到，尝试通过 leader_ids 获取（兼容测试环境）
            if not consul_figure and self.state.turn.leader_ids:
                leader_id = self.state.turn.leader_ids[0]
                consul_figure = self.state.get_member(leader_id)
            if not consul_figure:
                print("⚠️ 没有执政官，无法进行提案", flush=True)
                self._handle_next([])
                return

            consul_player = self.state.get_player_by_faction(consul_figure.faction_id)
            if not consul_player:
                print("⚠️ 执政官无对应玩家", flush=True)
                self._handle_next([])
                return

            self._current_consul_player_id = consul_player.player_id

            # 打印提案环节标题
            print("\n############################################################")
            print(f" UI-05-1 回合 {abs(self.state.turn.year)} BC - 元老院阶段 [5/7] --- 提案环节")
            print("############################################################\n")
            self._auto_generate_proposals()
            self._handle_next([])
        else:
            # 正常模式：获取执政官人物及其所属玩家
            print("\n############################################################")
            print(f" UI-05-1 回合 {abs(self.state.turn.year)} BC - 元老院阶段 [5/7] --- 提案环节")
            print("############################################################\n")
            print()
            consul_figure = None
            for member in self.state.get_living_members():
                if member.office == "consul" and not member.is_absent:
                    consul_figure = member
                    break

            if not consul_figure:
                print("⚠️ 没有执政官，无法进行提案", flush=True)
                self._handle_next([])
                return

            consul_player = self.state.get_player_by_faction(consul_figure.faction_id)
            if not consul_player:
                print("⚠️ 执政官无对应玩家", flush=True)
                self._handle_next([])
                return

            self._current_consul_player_id = consul_player.player_id

            bypass = self.state.config.get("testing.bypass_player_check", False)
            if bypass or consul_player.player_type == PlayerType.HUMAN:
                # 人类玩家：手动交互
                # 显示可选提案列表
                self._print_proposal_options()

                while True:
                    consul_faction = self.state.get_faction(consul_figure.faction_id)
                    print(f"\n> 请输入操作({consul_faction.id}_CONSUL): ", end="", flush=True)
                    cmd_input = input().strip()
                    self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                    if not cmd_input:
                        continue
                    parts = cmd_input.split()
                    cmd = parts[0].lower()
                    if cmd in ("next", "n"):
                        # 玩家结束提案，直接进入下一步（无需转换）
                        self._handle_next([])
                        break
                    elif cmd == "propose":
                        self._handle_propose(parts[1:])
                    else:
                        print("未知命令，支持 propose 和 next", flush=True)
            else:
                # AI 玩家：自动生成提案
                self.state.log_event(
                    f"AI玩家 {consul_player.player_id} 进入自动提案环节",
                    level=logging.INFO,
                    extra={"player_id": consul_player.player_id}
                )
                # 生成所有提案并存入 _senate_pending
                self._auto_generate_proposals()
                self._handle_next([])

    def _handle_step_2(self):
        proposals = self.state.get_senate_proposals()
        if not proposals:
            print("\n 📭 无待表决提案")
            self._handle_next([])
            return

        if self._auto_mode:
            # 自动模式：一次性对所有派系进行自动投票
            print("\n############################################################")
            print(f" UI-05-2 回合 {abs(self.state.turn.year)} BC - 元老院阶段 [5/7] - 表决环节")
            print("############################################################\n")
            print("==========================================================")
            print("   🏛️  Senate Vote Stage")
            print("==========================================================\n")
            print("\n 📜 待表决提案：")
            for prop in proposals:
                prop_id = prop["id"]
                desc = self._generate_proposal_description(prop["type"], prop)
                print(f" B{prop_id:02d}: {desc}")
            # 清空旧投票记录
            self.state.clear_senate_votes()
            self._vote_on_proposals(proposals)
            self._handle_next([])
        else:
            # 手动模式
            # 打印表决环节框
            print("\n############################################################")
            print(f" UI-05-2 回合 {abs(self.state.turn.year)} BC - 元老院阶段 [5/7] - 表决环节")
            print("############################################################\n")
            print("==========================================================")
            print("   🏛️  Senate Vote Stage")
            print("==========================================================\n")

            print("\t📜 可表决法案：")
            for prop in proposals:
                prop_id = prop["id"]
                desc = self._generate_proposal_description(prop["type"], prop)
                print(f"\t\tB{prop_id:02d} {desc}")
            print()

            print("🔧 本阶段可操作（PLAYER X）：")
            print("\t1. vote <法案ID1> <法案ID2>... → 表决支持")
            print("\t2. next/n → 进入元老院表决环节")

            # 获取所有玩家（按回合顺序）
            all_players = [p for p in self.state.get_all_players() if p.player_type != "auto"]
            if not all_players:
                print("⚠️ 无有效玩家，跳过投票")
                self._handle_next([])
                return

            # 重置投票记录
            self.state.clear_senate_votes()

            # 保存原当前玩家，以便结束后恢复
            original_player_id = self.state.get_current_player().player_id

            for player in all_players:
                player_id = player.player_id
                faction = self.state.get_faction(player.faction_id)
                if not faction:
                    continue
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    print(f"\n⚠️ {faction.name} 派系无元老在场，自动弃权。")
                    continue

                # 切换当前玩家
                self.state.set_current_player(player_id)

                if player.player_type == PlayerType.HUMAN:
                    print(f"\n🔹 轮到 {faction.name} 派系投票（玩家 {player_id}）")
                    # 增加 PIN 校验（预留）
                    self._wait_for_pin()
                    self._prompt_player_vote(proposals, player_id, faction.name)
                else:
                    # AI 玩家自动投票（使用决策器）
                    self._auto_vote_for_player(player_id, proposals)
                    print(f"\n🤖 {faction.name} 派系已完成自动投票。")

            # 恢复原当前玩家
            self.state.set_current_player(original_player_id)
            self._handle_next([])

    def _handle_step_3(self):
        # 公示环节：输出投票结果（手动模式按 UI 格式）
        print("\n############################################################")
        print(f" UI-05-3 回合 {abs(self.state.turn.year)} BC - 元老院阶段 [5/7] - 公示环节")
        print("############################################################\n")
        print("==========================================================")
        print("   🏛️  Senate Result Stage")
        print("==========================================================\n")
        if not self._auto_mode:
            proposals = self.state.get_senate_proposals()
            if proposals:
                self._print_senate_results(proposals)
            else:
                print("   📭 无提案需要公示")
            print("\n🔧 本阶段可操作（ANY）：")
            print("\t1. next/n → 进入保民官否决环节")
            # 等待玩家输入 next
            original_player_id = self.state.get_current_player().player_id
            while True:
                player = self.state.get_player(original_player_id)
                if player:
                    faction = self.state.get_faction(player.faction_id)
                    faction_display = faction.id if faction else "ANY"
                else:
                    faction_display = "ANY"
                print(f"\n> 请输入操作（{faction_display}）：", end="", flush=True)
                cmd_input = input().strip()
                self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                if cmd in ("next", "n"):
                    break
                else:
                    print("未知命令，支持 next/n", flush=True)
            self.state.set_current_player(original_player_id)
            self._handle_next([])
        else:
            # 自动模式保持原样
            proposals = self.state.get_senate_proposals()
            if proposals:
                self._print_senate_results(proposals)
            else:
                print("   📭 无提案需要公示")
            self._handle_next([])

    def _handle_step_4(self):
        print("\n############################################################")
        print(f" UI-05-4 回合 {abs(self.state.turn.year)} BC - 元老院阶段 [5/7] - 否决环节")
        print("############################################################\n")

        tribune = self._get_tribune()
        if not tribune:
            print(f"\n   🛡️ 当前无保民官，不行使否决权")
            self._handle_next([])
            return

        proposals = self.state.get_senate_proposals()
        if not proposals:
            print("\n 📭 无提案需要通过保民官否决")
            self._handle_next([])
            return


        passed_proposals = self._get_passed_proposals()

        if not passed_proposals:
            print("\n 📭 无提案需要通过保民官否决")
            self._handle_next([])
            return

        # 获取保民官玩家
        tribune_player = self.state.get_player_by_faction(tribune.faction_id)
        if not tribune_player:
            print("⚠️ 无法获取保民官玩家，跳过否决")
            self._handle_next([])
            return

        if self._auto_mode:

            print(f"\n   🛡️ 保民官行使否决权:")
            for prop in passed_proposals:
                issue = self._build_issue_from_proposal(prop)
                if self.veto_decider.decide_veto(issue, tribune.id, self.state):
                    print(f"      ❌ 保民官已否决提案：{self._generate_proposal_description(prop['type'], prop)}")
                    self.state.record_senate_veto(prop["id"])
                else:
                    print(f"      ✅ 保民官未否决提案：{self._generate_proposal_description(prop['type'], prop)}")
            self._handle_next([])
        else:
            # 手动模式：打印 UI 标题框
            print(f"\n   🛡️ 保民官行使否决权:")
            print("\t📜 可否决法案：")
            for prop in passed_proposals:
                prop_id = prop["id"]
                desc = self._generate_proposal_description(prop["type"], prop)
                print(f"\t\tB{prop_id:02d} {desc}")
            print()

            # 获取保民官玩家对象
            tribune_player = self.state.get_player_by_faction(tribune.faction_id)
            if not tribune_player:
                print("⚠️ 无法获取保民官玩家，跳过否决")
                self._handle_next([])
                return

            # 根据保民官玩家类型决定处理方式
            if tribune_player.player_type != PlayerType.HUMAN:
                # AI 保民官：自动执行否决决策
                print(f"\n   🛡️ 保民官行使否决权（AI）:")
                for prop in passed_proposals:
                    issue = self._build_issue_from_proposal(prop)
                    if self.veto_decider.decide_veto(issue, tribune.id, self.state):
                        print(f"      ❌ 保民官已否决提案：{self._generate_proposal_description(prop['type'], prop)}")
                        self.state.record_senate_veto(prop["id"])
                    else:
                        print(f"      ✅ 保民官未否决提案：{self._generate_proposal_description(prop['type'], prop)}")
                self._handle_next([])
                return
            else:
                # 人类保民官：手动交互模式
                # 保存原当前玩家并切换为保民官玩家
                original_player_id = self.state.get_current_player().player_id
                self.state.set_current_player(tribune_player.player_id)

                # 构建提案映射
                proposal_map = {}
                for prop in passed_proposals:
                    real_id = prop["id"]
                    proposal_map[f"B{real_id:02d}"] = real_id
                    proposal_map[str(real_id)] = real_id

            while True:
                print("\n🔧 本阶段可操作（TRIBUNE）：")
                print("   1. veto <提案ID1> <提案ID2> ... → 否决指定提案")
                print("   2. next/n → 进入下一环节")
                tribune_faction = self.state.get_faction(tribune.faction_id)
                print(f"\n> 请输入操作（{tribune_faction.id}_TRIBUNE）：", end="", flush=True)
                cmd_input = input().strip()
                self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                if cmd in ("next", "n"):
                    break
                elif cmd == "veto":
                    veto_ids = []
                    invalid = False
                    for token in parts[1:]:
                        if token.upper() in proposal_map:
                            veto_ids.append(proposal_map[token.upper()])
                        else:
                            print(f"❌ 无效的提案ID: {token}，请重新输入")
                            invalid = True
                            break
                    if invalid:
                        continue
                    if not veto_ids:
                        print("❌ 请指定至少一个提案ID")
                        continue

                    from src.api import senate_api
                    result = senate_api.veto(self.state, tribune_player.player_id, veto_ids)
                    if result["success"]:
                        print(f"✅ 已否决 {len(veto_ids)} 个提案")
                        # 从本地列表中移除已否决的提案，并更新映射
                        for vid in veto_ids:
                            passed_proposals = [p for p in passed_proposals if p["id"] != vid]
                            for key in list(proposal_map.keys()):
                                if proposal_map[key] == vid:
                                    del proposal_map[key]
                        if not passed_proposals:
                            print("📭 无其他提案需否决")
                            break
                        # 打印剩余提案（保持格式）
                        print("\n\t📜 剩余可否决法案：")
                        for prop in passed_proposals:
                            prop_id = prop["id"]
                            desc = self._generate_proposal_description(prop["type"], prop)
                            print(f"\t\tB{prop_id:02d} {desc}")
                        print()
                    else:
                        print(f"❌ 否决失败: {result['message']}")
                else:
                    print("未知命令，支持 veto <提案ID> 或 next", flush=True)

            # 恢复原当前玩家
            self.state.set_current_player(original_player_id)
            self._handle_next([])

    def _handle_step_5(self):

        """打印宣布环节标题框和通过的提案列表"""
        print("\n############################################################")
        print(f" UI 05-5 回合 {abs(self.state.turn.year)} BC - 元老院阶段 [5/7] - 宣布环节")
        print("############################################################\n")
        print("\t📜 元老院最终通过的法案：")

        from src.api import senate_api
        result = senate_api.resolve_senate(
            self.state,
            vote_decider=self.vote_decider,
            takeover_decider=self.takeover_decider,
        )
        if result["success"]:
            passed_snapshot = result["data"].get("passed_proposals_snapshot", [])
            self._print_announcement_header(passed_snapshot)
            if result["message"]:
                print(result["message"])

            fleet_result = senate_api.assign_fleets_to_active_wars(self.state)
            if fleet_result["success"] and fleet_result["message"]:
                print(fleet_result["message"])
            self._assign_rebellion_commanders()
        else:
            print(f"❌ 结算失败: {result['message']}", flush=True)

        self._step += 1

    def _handle_next(self, args: List[str]):
        """推进状态机到下一步（自动模式）或等待玩家输入（手动模式后续实现）"""
        if self._auto_mode:
            self._step += 1
            # 重置玩家列表（当前步骤不需要玩家轮流）
            self._players = self._get_step_players()
            self._current_player_index = 0
        else:
            # 手动模式留空，后续任务实现
            # 这里暂时直接推进，等待后续添加输入处理
            self._step += 1

    def _get_step_players(self) -> List[str]:
        """返回当前步骤需要轮流的玩家列表"""
        if self._step == 1:
            # 提案环节：只有执政官玩家
            consul_players = []
            for member in self.state.get_living_members():
                if member.office == "consul" and not member.is_absent:
                    player = self.state.get_player_by_faction(member.faction_id)
                    if player and player.player_id not in consul_players:
                        consul_players.append(player.player_id)
            return consul_players
        elif self._step in (2, 3):
            # 投票环节：所有玩家（后续任务实现）
            return [p.player_id for p in self.state.get_all_players()]
        # 其他步骤不需要玩家轮流
        return []

    def _print_proposal_options(self):
        """打印手动模式下可选提案列表，使用 B01/B02 格式，与 UI 设计一致"""
        from src.api import senate_api
        result = senate_api.get_senate_initial_info(self.state)
        if not result["success"]:
            print(f"⚠️ 无法获取提案列表: {result['message']}")
            return

        data = result["data"]
        print("\n   📜 可选法案：")

        # 获取战争系统，用于后续过滤
        ws = self.state.get_war_system()

        # 构建提案映射并分配 ID
        proposals_map = {}
        idx = 1

        # 战争威胁
        for war in data.get("war_threats", []):
            # 确保 war 状态为 THREAT
            war_obj = ws.get_war_by_id(war["war_id"]) if ws else None
            if war_obj and war_obj.peace_treaty and war_obj.peace_treaty.get('status') == 'pending':
                continue
            proposals_map[f"B{idx:02d}"] = ("war", {"war_id": war["war_id"]})
            print(f"       B{idx:02d} {war['name']}（威胁等级 {war['threat_level']}）")
            idx += 1

        # 新增：进行中的外国战争（接管选项）
        for war in data.get("active_foreign_wars", []):
            proposals_map[f"B{idx:02d}"] = ("takeover", {"war_id": war["war_id"]})
            print(f"       B{idx:02d} 接管 {war['name']}（进行中）")
            idx += 1

        # 停战草案
        for peace in data.get("pending_peace_treaties", []):
            war_obj = ws.get_war_by_id(peace["war_id"]) if ws else None
            if war_obj and war_obj.status == WarStatus.TRUCE and war_obj.peace_treaty and war_obj.peace_treaty.get(
                    'status') == 'pending':
                proposals_map[f"B{idx:02d}"] = ("peace", {"war_id": peace["war_id"]})
                print(f"       B{idx:02d} {peace['name']}（赔款 {peace['indemnity']}）")
                idx += 1

        # 行省空缺（proconsul）
        for prov in data.get("governor_vacancies", {}).get("proconsul", []):
            proposals_map[f"B{idx:02d}"] = ("governor", {"province_id": prov["province_id"]})
            print(f"       B{idx:02d} 任命 {prov['province_name']} 总督（执政官行省）")
            idx += 1

        # 行省空缺（propraetor）
        for prov in data.get("governor_vacancies", {}).get("propraetor", []):
            proposals_map[f"B{idx:02d}"] = ("governor", {"province_id": prov["province_id"]})
            print(f"       B{idx:02d} 任命 {prov['province_name']} 总督（大法官行省）")
            idx += 1

        # 待审批合同
        for contract in data.get("pending_contracts", []):
            proposals_map[f"B{idx:02d}"] = ("budget", {"contract_id": contract["contract_id"]})
            if contract["type"] == "tax_farming":
                print(f"       B{idx:02d} {contract['name']} 税额案 {contract['expected_profit']}T")
            else:
                print(f"       B{idx:02d} {contract['name']} 预算案 {contract['base_cost']}T")
            idx += 1

        # 土地法案
        proposals_map[f"B{idx:02d}"] = ("land", {"act_type": "sale"})
        print(f"       B{idx:02d} 公地出售法案")
        idx += 1
        proposals_map[f"B{idx:02d}"] = ("land", {"act_type": "distribution"})
        print(f"       B{idx:02d} 公地分配法案")

        # 存储映射供 _handle_propose 使用
        self._proposals_map = proposals_map

        print("\n🔧 本阶段可操作（CONSUL）：")
        print("   1. propose <法案ID> [参数] → 提出提案")
        print("      示例: ")
        print("            propose B01 6     (宣战，6个军团)")
        print("            propose B02 80    (工程或包税权合同预算，80塔兰特)")
        print("            propose B03       (和约，提交停战协议，无参数)")
        print("            propose B04 1     (总督，提名候选人ID)")
        print("            propose B05 0.05  (公地出售，5%国家公地)")
        print("            propose B06 0.06  (分地法案，6%国家公地)")
        print("   2. next/n → 进入元老院表决环节")


    def _handle_propose(self, args: List[str]):
        """处理 propose 命令，格式：propose <提案ID> [参数]"""
        if len(args) < 1:
            print("❌ 用法: propose <法案ID> [参数]", flush=True)
            return

        proposal_id = args[0].upper()
        if not hasattr(self, "_proposals_map") or proposal_id not in self._proposals_map:
            print(f"❌ 无效的法案ID: {proposal_id}", flush=True)
            return

        proposal_type, base_params = self._proposals_map[proposal_id]
        kwargs = base_params.copy()

        existing_proposals = self.state.get_senate_proposals()
        for prop in existing_proposals:
            if prop["type"] == proposal_type:
                if proposal_type == "budget" and prop.get("contract_id") == kwargs.get("contract_id"):
                    print(f"❌ 合同 {kwargs.get('contract_id')} 已有待表决提案，请勿重复提交")
                    return
                elif proposal_type == "war" and prop.get("war_id") == kwargs.get("war_id"):
                    print(f"❌ 战争 {kwargs.get('war_id')} 已有宣战提案")
                    return
                elif proposal_type == "peace" and prop.get("war_id") == kwargs.get("war_id"):
                    print(f"❌ 战争 {kwargs.get('war_id')} 已有停战草案提案")
                    return
                elif proposal_type == "governor" and prop.get("province_id") == kwargs.get("province_id"):
                    print(f"❌ 行省 {kwargs.get('province_id')} 已有总督任命提案")
                    return

        # 根据提案类型补充额外参数
        if proposal_type == "war":
            if len(args) < 2:
                print("❌ 宣战提案需要指定军团数量", flush=True)
                return
            try:
                legions = int(args[1])
            except ValueError:
                print("❌ 军团数量必须是数字", flush=True)
                return
            kwargs["legions"] = legions

            # 检查战争是否需要海战，若需要则验证舰队可用性
            war_id = kwargs["war_id"]
            ws = self.state.get_war_system()
            war = ws.get_war_by_id(war_id) if ws else None
            if not war:
                print("❌ 战争不存在", flush=True)
                return
            if war.naval_required:
                naval_system = self.state.naval_system
                if not naval_system or not naval_system.get_available_fleets():
                    print("❌ 战争需要海战，但当前无可用舰队，无法宣战。请先建造舰队。", flush=True)
                    return

        elif proposal_type == "peace":
            # 停战不需要额外参数
            pass

        elif proposal_type == "governor":
            if len(args) < 2:
                print("❌ 总督任命需要指定候选人ID", flush=True)
                return
            try:
                candidate_id = int(args[1])
            except ValueError:
                print("❌ 候选人ID必须是数字", flush=True)
                return
            kwargs["candidate_id"] = candidate_id

        elif proposal_type == "budget":
            # 预算合同可选的修改预算
            if len(args) >= 2:
                try:
                    modified_budget = int(args[1])
                    kwargs["modified_budget"] = modified_budget
                except ValueError:
                    print("❌ 修改预算必须是数字，请使用纯数字（如 80）", flush=True)
                    return  # 参数错误，不提交提案

        elif proposal_type == "land":
            if len(args) < 2:
                print("❌ 土地法案需要指定百分比（如 0.05 表示 5%）", flush=True)
                return
            try:
                percent = float(args[1])  # 直接使用小数，不再除以100
            except ValueError:
                print("❌ 百分比必须是数字", flush=True)
                return
            kwargs["percent"] = percent

        # 获取当前玩家
        if hasattr(self, "_current_consul_player_id") and self._current_consul_player_id:
            player_id = self._current_consul_player_id
        else:
            player_id = self._get_current_player_id()
            if not player_id:
                print("❌ 无法获取当前玩家", flush=True)
                return

        # 特殊处理 takeover：直接执行，不经过 API
        if proposal_type == "takeover":
            if len(args) < 2:
                print("❌ 接管战争需要指定增援军团数量", flush=True)
                return
            try:
                additional_legions = int(args[1])
            except ValueError:
                print("❌ 军团数量必须是数字", flush=True)
                return

            war_id = kwargs["war_id"]
            # 执行接管
            success = self._execute_war_takeover_manual(war_id, player_id, additional_legions)
            if success:
                # 注意：实际征召数量在 _execute_war_takeover_manual 内部打印，无需额外打印
                # print(f"✅ 已接管战争，增援 {additional_legions} 个军团")
                pass
            else:
                print(f"❌ 接管失败，请检查战争状态或权限", flush=True)
            return

        # 调用 API
        from src.api import senate_api
        result = senate_api.propose(self.state, player_id, proposal_type, bypass_turn_check=True, **kwargs)
        if result["success"]:
            description = self._generate_proposal_description(proposal_type, kwargs)
            print(f"✅ {description}")
        else:
            print(f"❌ {result['message']}", flush=True)

    def _get_current_player_id(self) -> Optional[str]:
        """获取当前玩家ID（直接使用游戏状态中的当前玩家）"""
        player = self.state.get_current_player()
        return player.player_id if player else None

    def _execute_war_takeover_manual(self, war_id: str, player_id: str, additional_legions: int) -> bool:
        """手动执行战争接管：执政官接管外国战争并增派军团"""
        player = self.state.get_player(player_id)
        if not player:
            return False
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return False
        # 获取执政官人物
        consul = None
        for member in faction.get_members(self.state):
            if member.office == "consul" and not member.is_dead and not member.is_absent:
                consul = member
                break
        if not consul:
            print("❌ 您没有在罗马的执政官可以出征", flush=True)
            return False

        ws = self.state.get_war_system()
        war = ws.get_war_by_id(war_id) if ws else None
        if not war:
            print("❌ 战争不存在", flush=True)
            return False
        if war.rebellion_province_id is not None:
            print("❌ 起义战争应由总督自动接管，不能由执政官接管", flush=True)
            return False
        if war.status != WarStatus.ACTIVE:
            print(f"❌ 战争 {war.name} 状态为 {war.status}，无法接管", flush=True)
            return False
        if war.commander_id is not None:
            # 已有指挥官，但可能为其他执政官或前执政官
            print(f"⚠️ 战争已有指挥官，执政官将接管并增派军团", flush=True)

        # 执行接管
        # 1. 设置指挥官
        old_commander = self.state.get_member(war.commander_id) if war.commander_id else None
        war.commander_id = consul.id
        consul.is_absent = True

        # 2. 增派军团
        ms = self.state.get_military_system()
        if not ms:
            print("❌ 军事系统不可用", flush=True)
            return False

        # 获取可用军团
        available = ms.get_available_legions()
        if not available:
            print("❌ 没有可用军团", flush=True)
            return False

        recruit_count = min(additional_legions, len(available))
        if recruit_count == 0:
            print("❌ 无法征召军团", flush=True)
            return False
        print(f"✅ 已接管战争，增援 {recruit_count} 个军团")

        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [r[0] for r in results if r[1]]
        if not recruited_numbers:
            print("❌ 军团征召失败", flush=True)
            return False

        # 指派军团到战争（不覆盖已有军团）
        assigned, msg = ms.assign_to_war(recruited_numbers, war.id, consul.id)
        if assigned > 0:
            for num in recruited_numbers:
                war.add_legion_number(num)
            print(f"      {msg}")
        else:
            print(f"❌ 军团指派失败: {msg}", flush=True)
            return False

        # 如果旧指挥官存在且是 proconsul，将其召回
        if old_commander and old_commander.office in ("proconsul", "ex-consul") and old_commander.is_absent:
            old_commander.is_absent = False
            old_commander.office = "ex-proconsul"
            print(f"      🔄 原指挥官 {old_commander.name} 返回罗马")

        self.state.log_event(
            f"执政官 {consul.name} 手动接管战争 {war.name}，增援 {recruit_count} 个军团",
            level=logging.INFO,
            extra={"war_id": war.id, "consul_id": consul.id, "legions": recruit_count}
        )
        return True

    def _generate_proposal_description(self, proposal_type: str, kwargs: dict) -> str:
        """根据提案类型和参数生成友好描述"""
        if proposal_type == "war":
            war_id = kwargs.get("war_id")
            legions = kwargs.get("legions")
            war = self.state.get_war_system().get_war_by_id(war_id) if war_id else None
            war_name = war.name if war else "未知战争"
            return f"对 {war_name} 宣战，申请征召 {legions} 个军团"
        elif proposal_type == "peace":
            war_id = kwargs.get("war_id")
            war = self.state.get_war_system().get_war_by_id(war_id) if war_id else None
            war_name = war.name if war else "未知战争"
            return f"对 {war_name} 的停战协议进行表决"
        elif proposal_type == "governor":
            province_id = kwargs.get("province_id")
            candidate_id = kwargs.get("candidate_id")
            province = self.state.get_province(province_id) if province_id else None
            candidate = self.state.get_member(candidate_id) if candidate_id else None
            province_name = province.name if province else f"ID {province_id}"
            candidate_name = candidate.get_formal_name() if candidate else f"ID {candidate_id}"
            return f"任命 {candidate_name} 为 {province_name} 行省总督"
        elif proposal_type == "budget":
            contract_id = kwargs.get("contract_id")
            modified_budget = kwargs.get("modified_budget")
            contract = self.state.get_contract(contract_id) if contract_id else None
            contract_name = contract.name if contract else f"合同 {contract_id}"
            budget_display = modified_budget if modified_budget else (contract.base_cost if contract else "?")
            return f"{contract_name} 预算 {budget_display} 塔兰特"
        elif proposal_type == "land":
            act_type = kwargs.get("act_type")
            percent = kwargs.get("percent")
            act_name = "公地出售法案" if act_type == "sale" else "公地分配法案"
            return f"{act_name} {percent * 100:.1f}% 国家公地"
        elif proposal_type == "takeover":
            war_id = kwargs.get("war_id")
            legions = kwargs.get("legions", 0)
            war = self.state.get_war_system().get_war_by_id(war_id) if war_id else None
            war_name = war.name if war else "未知战争"
            return f"接管 {war_name}，增援 {legions} 个军团"
        else:
            return "提案已记录"

    def _vote_on_proposals(self, proposals: list):
        """对提案列表进行投票统计，结果存入 _senate_pending["votes"]"""
        for proposal in proposals:
            pid = proposal["id"]
            # 遍历所有派系
            for faction in self.state.get_active_factions():
                player = self.state.get_player_by_faction(faction.id)
                if not player:
                    continue
                player_id = player.player_id

                # 检查该玩家是否已对此提案投票
                if self.state.has_senate_vote(player_id, pid):
                    continue

                # 构造 issue
                issue = self._build_issue_from_proposal(proposal)
                # 调用决策器
                support = self.vote_decider.decide_vote(issue, faction, self.state)
                # 记录投票
                self.state.record_senate_vote(player_id, pid, support)

                # 日志
                self.state.log_event(
                    f"自动投票: 派系 {faction.name} 对提案 {pid} 投票 {support}",
                    level=logging.DEBUG,
                    extra={"proposal_id": pid, "faction_id": faction.id, "vote": support}
                )

    def _build_issue_from_proposal(self, proposal: dict):
        """根据提案类型构造 issue 对象，供决策器使用，包含 proposer_faction"""
        ptype = proposal["type"]
        proposer_faction = proposal.get("proposer_faction")  # 提案发起派系

        if ptype == "war":
            ws = self.state.get_war_system()
            war = ws.get_war_by_id(proposal["war_id"]) if ws else None
            return {"type": "war", "war": war, "proposer_faction": proposer_faction}
        elif ptype == "peace":
            return {
                "type": "peace",
                "war_id": proposal["war_id"],
                "treaty": proposal.get("treaty"),
                "proposer_faction": proposer_faction
            }
        elif ptype == "governor":
            return {
                "type": "governor",
                "province_id": proposal["province_id"],
                "candidate_id": proposal["candidate_id"],
                "old_governor_id": proposal.get("old_governor_id"),
                "proposer_faction": proposer_faction
            }
        elif ptype == "budget":
            contract = self.state.get_contract(proposal["contract_id"])
            return {
                "type": "contract",
                "contract": contract,
                "proposer_faction": proposer_faction
            }
        elif ptype == "land":
            return {
                "type": "land",
                "act_type": proposal["act_type"],
                "percent": proposal["percent"],
                "proposer_faction": proposer_faction
            }
        else:
            return None

    def _get_passed_proposals(self) -> list:
        """获取已通过且未被否决的提案列表"""
        proposals = self.state.get_senate_proposals()
        votes = self.state.get_senate_votes_copy()
        vetoes = self.state.get_senate_vetoes_copy()
        passed = []

        for proposal in proposals:
            pid = proposal["id"]
            if pid in vetoes:
                continue

            support_influence = 0
            oppose_influence = 0
            total_influence = 0

            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence

                player = self.state.get_player_by_faction(faction.id)
                if not player:
                    continue
                player_id = player.player_id

                # 优先使用已记录投票
                if player_id in votes and pid in votes[player_id]:
                    if votes[player_id][pid]:
                        support_influence += influence
                    else:
                        oppose_influence += influence
                else:
                    # 未投票的派系，使用决策器补投（与 resolve_senate 逻辑一致）
                    issue = self._build_issue_from_proposal(proposal)
                    support = self.vote_decider.decide_vote(issue, faction, self.state)
                    if support:
                        support_influence += influence
                    else:
                        oppose_influence += influence

            if total_influence == 0:
                continue
            support_ratio = support_influence / total_influence
            if support_ratio > 0.5:
                passed.append(proposal)

        return passed

    def _auto_generate_proposals(self):
        """为AI玩家自动生成所有提案，存入 _senate_pending"""
        from src.api import senate_api

        consul_player_id = self._current_consul_player_id
        if not consul_player_id:
            return

        # 收集成功提案的描述
        proposal_descriptions = []

        # 1. 宣战提案（战争威胁）
        ws = self.state.get_war_system()
        if ws:
            threats = ws.get_threat_wars()
            if threats:
                propose_chance = self.state.config.get("testing.propose_war_chance", 0.7)
                always_declare = self.state.config.get("testing.always_declare", False)
                min_legions = self.state.config.get("testing.min_legions", 4)
                max_legions = self.state.config.get("testing.max_legions", 8)

                for war in threats:
                    # 如果战争已有 pending 停战草案，则跳过
                    if war.peace_treaty and war.peace_treaty.get('status') == 'pending':
                        continue
                    # 检查海战条件
                    if war.naval_required:
                        naval_system = self.state.naval_system
                        if not naval_system or not naval_system.get_available_fleets():
                            continue

                    if always_declare or random.random() < propose_chance:
                        legions = random.randint(min_legions, max_legions)
                        result = senate_api.propose(
                            self.state, consul_player_id, "war",
                            bypass_turn_check=True,
                            war_id=war.id,
                            legions=legions
                        )
                        if result["success"]:
                            desc = self._generate_proposal_description("war", {"war_id": war.id, "legions": legions})
                            proposal_descriptions.append(desc)
                        else:
                            print(f"⚠️ 提案失败: {result['message']}", flush=True)
                            self.state.log_event(f"AI自动宣战失败: {result['message']}", level=logging.WARNING)

        # 2. 停战草案（待决停战）
        if ws:
            pending_peace = ws.get_truce_wars_with_pending_treaty()
            for war in pending_peace:
                result = senate_api.propose(
                    self.state, consul_player_id, "peace",
                    bypass_turn_check=True,
                    war_id=war.id
                )
                if result["success"]:
                    desc = self._generate_proposal_description("peace", {"war_id": war.id})
                    proposal_descriptions.append(desc)
                else:
                    print(f"⚠️ 提案失败: {result['message']}", flush=True)
                    self.state.log_event(f"AI自动停战提案失败: {result['message']}", level=logging.WARNING)

        # 3. 总督任命（行省空缺）
        all_provinces = [p for p in self.state.get_all_provinces() if p.conquered and p.province_id != 0]
        proconsul_provinces = [p for p in all_provinces if p.governor_type == "proconsul"]
        propraetor_provinces = [p for p in all_provinces if p.governor_type == "propraetor"]

        def get_candidates(office_type: str):
            cand_list = []
            for fig in self.state.get_living_members():
                if fig.is_absent:
                    continue
                if fig.office is not None and not fig.office.startswith("ex-"):
                    continue
                last_end = None
                for term in fig.office_history:
                    if term.office_type == office_type and term.end_turn is not None:
                        if last_end is None or term.end_turn > last_end:
                            last_end = term.end_turn
                if last_end is not None:
                    cand_list.append((fig, last_end))
            cand_list.sort(key=lambda x: -x[1])
            return [c[0] for c in cand_list]

        consuls = get_candidates('consul')
        praetors = get_candidates('praetor')

        used = set()

        def assign(provinces, candidates, used_set):
            remaining = list(provinces)
            random.shuffle(remaining)
            assignments = []
            for cand in candidates:
                if cand.id in used_set:
                    continue
                if not remaining:
                    break
                chosen = random.choice(remaining)
                remaining.remove(chosen)
                assignments.append((chosen, cand))
                used_set.add(cand.id)
            return assignments

        proconsul_assignments = assign(proconsul_provinces, consuls, used)
        propraetor_assignments = assign(propraetor_provinces, praetors, used)

        for province, candidate in proconsul_assignments + propraetor_assignments:
            result = senate_api.propose(
                self.state, consul_player_id, "governor",
                bypass_turn_check=True,
                province_id=province.province_id,
                candidate_id=candidate.id
            )
            if result["success"]:
                desc = self._generate_proposal_description("governor", {"province_id": province.province_id,
                                                                        "candidate_id": candidate.id})
                proposal_descriptions.append(desc)
            else:
                print(f"⚠️ 提案失败: {result['message']}", flush=True)
                self.state.log_event(f"AI自动总督任命失败: {result['message']}", level=logging.WARNING)

        # 4. 预算合同
        pending_contracts = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if pending_contracts:
            proposals = self.budget_decider.decide_proposals(pending_contracts, self.state)
            for contract in proposals:
                kwargs = {"contract_id": contract.id}
                # 仅对公共工程合同（包括舰队）进行随机预算加成
                if contract.contract_type == ContractType.PUBLIC_WORKS:
                    margin_range = self.state.config.get("economic_rules.public_work_budget_margin_range", [0.05, 0.20])
                    r = random.uniform(margin_range[0], margin_range[1])
                    modified_budget = int(contract.base_cost * (1 + r))
                    kwargs["modified_budget"] = modified_budget
                    self.state.log_event(
                        f"自动预算提案加成: 合同 {contract.name} 原始预算 {contract.base_cost} 加成 {r * 100:.1f}% → {modified_budget}",
                        level=logging.DEBUG
                    )
                result = senate_api.propose(
                    self.state, consul_player_id, "budget",
                    bypass_turn_check=True,
                    **kwargs
                )

        # 5. 土地法案
        for faction in self.state.factions.values():
            for decider in self.land_proposal_deciders:
                decider_result = decider.decide_proposal(faction.id, self.state)
                if decider_result:
                    act_type, percent = decider_result
                    result = senate_api.propose(
                        self.state, consul_player_id, "land",
                        bypass_turn_check=True,
                        act_type=act_type,
                        percent=percent
                    )
                    if result["success"]:
                        desc = self._generate_proposal_description("land", {"act_type": act_type, "percent": percent})
                        proposal_descriptions.append(desc)
                    else:
                        print(f"⚠️ 提案失败: {result['message']}", flush=True)
                        self.state.log_event(f"AI自动土地法案失败: {result['message']}", level=logging.WARNING)

        # 打印成功提案列表
        if proposal_descriptions:
            print("\n✅ 执政官提案:")
            for idx, desc in enumerate(proposal_descriptions, 1):
                print(f"\tB{idx:02d} {desc}")

    def _prompt_player_vote(self, proposals: list, player_id: str, faction_name: str):
        proposal_map = {}
        for prop in proposals:
            real_id = prop["id"]
            proposal_map[f"B{real_id:02d}"] = real_id
            proposal_map[str(real_id)] = real_id

        while True:

            print(f"\n> 请输入操作({faction_name}): ", end="", flush=True)
            cmd_input = input().strip()
            self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
            if not cmd_input:
                continue
            parts = cmd_input.split()
            cmd = parts[0].lower()
            if cmd in ("next", "n"):
                print(f"{faction_name} 派系未投票，视为弃权。")
                break
            elif cmd == "vote":
                # 解析提案ID，要求所有参数都是有效ID
                vote_ids = []
                invalid = False
                for token in parts[1:]:
                    if token.upper() in proposal_map:
                        vote_ids.append(proposal_map[token.upper()])
                    else:
                        print(f"❌ 无效的提案ID: {token}，请重新输入")
                        invalid = True
                        break
                if invalid:
                    continue
                if not vote_ids:
                    print("❌ 请指定至少一个提案ID")
                    continue
                votes = [True] * len(vote_ids)
                from src.api import senate_api
                result = senate_api.vote(self.state, player_id, vote_ids, votes)
                if result["success"]:
                    print(f"✅ {faction_name} 派系已投票：{', '.join([f'B{vid:02d}' for vid in vote_ids])}")
                    break
                else:
                    print(f"❌ 投票失败: {result['message']}")
            else:
                print("未知命令，支持 vote <提案ID1> <提案ID2> ... 或 next", flush=True)

    def _get_passed_proposals_from_votes(self, proposals: list) -> list:
        """仅根据已记录的投票计算通过提案（不调用决策器补投）"""
        passed = []
        for proposal in proposals:
            pid = proposal["id"]
            support_influence = 0
            oppose_influence = 0
            total_influence = 0
            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence
                player = self.state.get_player_by_faction(faction.id)
                if not player:
                    continue
                player_id = player.player_id
                votes = self.state.get_senate_votes_copy().get(player_id, {})
                if pid in votes:
                    if votes[pid]:
                        support_influence += influence
                    else:
                        oppose_influence += influence
                # 未投票的派系视为弃权，不参与统计
            if total_influence == 0:
                continue
            support_ratio = support_influence / total_influence
            if support_ratio > 0.5:
                passed.append(proposal)
        return passed

    def _restore_rejected_peace_wars(self, wars: List[War]) -> None:
        """将否决/未提交的停战草案恢复为活跃战争，保留旧指挥官信息，由接管逻辑处理"""
        if not wars:
            return
        ws = self.state.get_war_system()
        for war in wars:
            ws.restore_rejected_peace_treaty(war.id, preserve_commander=True)

    def _execute_passed_peace_treaty(self, war):
        """执行通过的停战草案（手动模式）"""
        treaty = war.peace_treaty
        if not treaty or treaty.get("status") != "submitted":
            return
        war.set_peace_treaty_status("approved")
        war.set_indemnity_due(treaty["indemnity"])
        ms = self.state.get_military_system()
        if ms:
            ms.recall_from_war(war.id)
        ws = self.state.get_war_system()
        if war.legion_numbers:
            ws.add_legions_to_disband(war.legion_numbers)
        end_turn = self.state.turn.turn_number + treaty["duration"]
        war.set_truce_end_turn(end_turn)
        war.status = WarStatus.TRUCE

    def _print_senate_results(self, proposals: list):
        """打印元老院公示环节的详细投票结果（符合 UI 设计）"""
        votes = self.state.get_senate_votes_copy()
        for prop in proposals:
            pid = prop["id"]
            desc = self._generate_proposal_description(prop["type"], prop)
            print(f"\n   📋 {desc}")
            support_influence = 0
            oppose_influence = 0
            total_influence = 0
            faction_details = []
            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence
                player = self.state.get_player_by_faction(faction.id)
                if not player:
                    continue
                player_id = player.player_id
                if player_id in votes and pid in votes[player_id]:
                    if votes[player_id][pid]:
                        support_influence += influence
                        faction_details.append(f"          {faction.name} 支持，影响力 {influence}")
                    else:
                        oppose_influence += influence
                        faction_details.append(f"          {faction.name} 反对，影响力 {influence}")
            if faction_details:
                for detail in faction_details:
                    print(detail)
            else:
                print("          无元老在场，无人投票。")
            if total_influence > 0:
                support_ratio = support_influence / total_influence
                print(
                    f"          总影响力：{total_influence}，支持 {support_influence}，反对 {oppose_influence}，支持率 {support_ratio:.1%}")
                if support_ratio > 0.5:
                    print("          ✅ 元老院批准")
                else:
                    print("          ❌ 元老院否决")
            else:
                print("          无元老在场，提案未通过。")

    def _auto_vote_for_player(self, player_id: str, proposals: list):
        """为指定玩家（派系）自动投票"""
        player = self.state.get_player(player_id)
        if not player:
            return
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return
        for proposal in proposals:
            pid = proposal["id"]
            # 检查是否已投票
            votes = self.state.get_senate_votes_copy().get(player_id, {})
            if pid in votes:
                continue
            issue = self._build_issue_from_proposal(proposal)
            support = self.vote_decider.decide_vote(issue, faction, self.state)
            self.state.record_senate_vote(player_id, pid, support)

    def _print_announcement_header(self, passed_proposals: list):

        for prop in passed_proposals:
            prop_id = prop["id"]
            desc = self._generate_proposal_description(prop["type"], prop)
            print(f"\t\tB{prop_id:02d} {desc}")
        print()


    # ==================== 新增：MVP 0.7-4 行省起义镇压 ====================
    def _assign_rebellion_commanders(self):
        """为起义战争指派总督作为指挥官并征召军团"""
        war_system = self.state.get_war_system()
        if not war_system:
            return

        ms = self.state.get_military_system()
        if not ms:
            return

        rebellion_strength = self.state.config.get("combat_rules.rebellion_strength", 5)
        # 计算所需军团数量（假设每个军团基础战力2）
        legion_count = (rebellion_strength + 1) // 2
        if legion_count < 1:
            legion_count = 1

        for war in war_system.get_active_wars():
            if war.rebellion_province_id is None or war.commander_id is not None:
                continue

            province = self.state.get_province(war.rebellion_province_id)
            if not province:
                continue

            # 优先使用候任总督，若无则使用现任总督
            governor_id = province.governor_designate_id or province.governor_id
            if governor_id is None:
                continue

            commander = self.state.get_member(governor_id)
            if not commander or commander.is_dead:
                continue

            # 征召军团
            available = ms.get_available_legions()
            if not available:
                print(f"      ⚠️ 无可用军团镇压 {province.name} 起义")
                continue

            recruit_count = min(legion_count, len(available))
            results = ms.recruit_multiple(recruit_count)
            recruited_numbers = [r[0] for r in results if r[1]]
            if not recruited_numbers:
                print(f"      ⚠️ 军团征召失败，无法镇压 {province.name} 起义")
                continue

            # 指派指挥官和军团
            war_system.assign_commander(war.id, governor_id, len(recruited_numbers))
            ms.assign_to_war(recruited_numbers, war.id, governor_id)
            commander.is_absent = True  # 总督出征

            print(f"      ✅ 任命 {commander.name} 为 {war.name} 指挥官，征召 {len(recruited_numbers)} 个军团")
            self.state.log_event(
                f"指派总督 {commander.name} 镇压起义",
                extra={"war_id": war.id, "commander_id": governor_id}
            )


# =================================== MVP 0.1-0.5 =============================================

    def _execute_governor_appointments(self):
        if not self.proposed_governors:
            return
        print("\n\t====================== 总督任命执行 ====================")
        for gov in self.proposed_governors:
            province = self.state.get_province(gov['province_id'])
            if not province:
                continue
            new_fig = self.state.get_member(gov['new_governor_id'])
            old_fig = self.state.get_member(gov['old_governor_id']) if gov['old_governor_id'] else None

            # 记录旧总督并设置候任总督，供决算阶段返回
            province.set_governor_designate(gov['new_governor_id'], gov['old_governor_id'])

            if new_fig:
                # 新总督离开罗马（在途），但暂不授予官职
                new_fig.is_absent = True
                new_fig_name = new_fig.get_formal_name()
            else:
                new_fig_name = "未知"

            old_name = old_fig.get_formal_name() if old_fig else "无"
            print(f"      ✅ {province.name} 任命新总督: {new_fig_name} (候任)，旧总督 {old_name} 仍在任")
            self.state.log_event(
                f"行省 {province.name} 任命候任总督 {new_fig_name}",
                extra={
                    'type': 'governor_appointed_designate',
                    'province_id': province.province_id,
                    'new_governor': gov['new_governor_id'],
                    'old_governor': gov['old_governor_id']
                }
            )

    def _process_governor_appointments(self, terms):
        print("\n\t====================== 行省总督任命 ====================")

        # 获取所有已征服的行省（排除意大利行省 ID 0）
        all_provinces = [p for p in self.state.get_all_provinces() if p.conquered and p.province_id != 0]

        # 行省分类
        proconsul_provinces = [p for p in all_provinces if p.governor_type == "proconsul"]
        propraetor_provinces = [p for p in all_provinces if p.governor_type == "propraetor"]

        # 候选人获取函数（原内嵌函数）
        def get_candidates(office_type: str):
            cand_list = []
            for fig in self.state.get_living_members():
                if fig.is_absent:
                    continue
                if fig.office is not None and not fig.office.startswith("ex-"):
                    continue
                last_end = None
                for term in fig.office_history:
                    if term.office_type == office_type and term.end_turn is not None:
                        if last_end is None or term.end_turn > last_end:
                            last_end = term.end_turn
                if last_end is not None:
                    cand_list.append((fig, last_end))
            cand_list.sort(key=lambda x: -x[1])
            return [c[0] for c in cand_list]

        consuls = get_candidates('consul')
        praetors = get_candidates('praetor')

        # 分配逻辑
        def assign(provinces, candidates, used_set):
            remaining = list(provinces)
            random.shuffle(remaining)
            assignments = []
            for cand in candidates:
                if cand.id in used_set:
                    continue
                if not remaining:
                    break
                chosen = random.choice(remaining)
                remaining.remove(chosen)
                assignments.append((chosen, cand))
                used_set.add(cand.id)
            return assignments

        used = set()
        proconsul_assignments = assign(proconsul_provinces, consuls, used)
        propraetor_assignments = assign(propraetor_provinces, praetors, used)

        # 打印分配结果
        def print_assignments(title, assignments):
            print(f"\n   {title}:")
            if not assignments:
                print("      无行省需要任命")
                return
            for prov, cand in assignments:
                # 计算卸任年份显示
                last_year = None
                req_office = 'consul' if title == '执政官行省' else 'praetor'
                for term in cand.office_history:
                    if term.office_type == req_office and term.end_turn is not None:
                        last_year = term.end_turn
                        break
                if last_year is not None:
                    year = self.state.turn.year + (last_year - self.state.turn.turn_number)
                    year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                else:
                    year_display = "未知"
                print(f"      → {cand.get_formal_name()} (卸任 {year_display}) 抽中 {prov.name}")

        print_assignments("执政官行省 (Proconsul)", proconsul_assignments)
        print_assignments("大法官行省 (Propraetor)", propraetor_assignments)

        # 提示未被分配的行省
        all_provinces_set = set(proconsul_provinces + propraetor_provinces)
        assigned_provinces = set(p for p, _ in proconsul_assignments + propraetor_assignments)
        unassigned = all_provinces_set - assigned_provinces
        if unassigned:
            for p in unassigned:
                print(f"      ⚠️ {p.name} 无合格候选人，现任总督留任一年")

        # 构建提案
        self.proposed_governors = []
        for prov, cand in proconsul_assignments + propraetor_assignments:
            self.proposed_governors.append({
                'province_id': prov.province_id,
                'new_governor_id': cand.id,
                'old_governor_id': prov.governor_id,
                'governor_type': prov.governor_type
            })

        self.state.log_event(
            f"总督任命提案收集完成，共 {len(self.proposed_governors)} 项",
            level=logging.DEBUG,
            extra={"proposals": [p['province_id'] for p in self.proposed_governors]}
        )

    def _get_tribune(self) -> Optional['Figure']:
        """获取当前保民官（假设只有一人）"""
        for fig in self.state.get_living_members():
            if fig.office == "tribune":
                return fig
        return None

    def _execute_war_declaration(self, war: "War", consul_id: int, legions: int):
        """实际执行宣战：激活战争、征召军团、指派指挥官"""
        ws = self.state.get_war_system()
        if not ws:
            print(f"      ⚠️ 战争系统不可用，无法执行宣战")
            return
        success = ws.activate_war(war.id, consul_id, legions)
        if not success:
            print(f"      ⚠️ 激活战争失败")
            return

        war.commander_id = consul_id

        consul = self.state.get_member(consul_id)
        if not consul:
            return

        # 征召军团并指派（会自动打印宣战及征召信息）
        self._auto_recruit_and_assign_legions_for_war(war, consul_id, action="declare")
        new_presiding = self.state.get_presiding_officer()
        if new_presiding:
            print(f"      元老院新主持人：{new_presiding.name}（官职 {new_presiding.office}）")

    def _process_land_proposals(self, terms, passed_land_acts: List[dict]):
        """处理土地法案提案，通过的放入 passed_land_acts"""
        land_rules = self.state.config.get("political_rules.land_proposal", {})
        submit_chance = land_rules.get("submit_chance", 0.7)

        presiding = self.state.get_presiding_officer()
        if not presiding:
            print(f"\n   ⚠️ 无主持人，无法处理土地法案。")
            return

        proposals = []
        for faction in self.state.factions.values():
            for decider in self.land_proposal_deciders:
                result = decider.decide_proposal(faction.id, self.state)
                if result:
                    act_type, percent = result
                    proposals.append({
                        'type': act_type,
                        'percent': percent,
                        'proposer_faction': faction.id,
                        'description': self._get_land_act_description(act_type, percent)
                    })

        if not proposals:
            print(f"\n   📭 无土地法案提案。")
            return

        for prop in proposals:
            if random.random() < submit_chance:
                print(f"\n   📋 {prop['description']} 由执政官 {presiding.name} 提交元老院表决。")
                votes_for = 0
                votes_against = 0
                total_influence = 0

                for faction in self.state.get_active_factions():
                    influence = faction.get_senate_influence(self.state)
                    if influence == 0:
                        continue
                    total_influence += influence

                    support = self.vote_decider.decide_vote(prop, faction, self.state)
                    if support:
                        votes_for += influence
                        print(f"          {faction.name} 支持，影响力 {influence}")
                    else:
                        votes_against += influence
                        print(f"          {faction.name} 反对，影响力 {influence}")

                if total_influence == 0:
                    print(f"          无元老在场，法案未通过。")
                    continue

                support_ratio = votes_for / total_influence
                print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")
                if support_ratio > 0.5:
                    national_land = self.state.get_national_public_land()
                    amount = int(national_land * prop['percent'])
                    prop['amount'] = amount
                    passed_land_acts.append(prop)
                    print(f"          ✅ 法案通过，等待保民官否决")
                else:
                    print(f"          ❌ 法案否决。")
            else:
                print(f"\n   ⏳ 执政官 {presiding.name} 决定不提交 {prop['description']}。")

    def _get_land_act_description(self, act_type: str, percent: float) -> str:
        if act_type == 'distribution':
            return f"平民分地法案（分配 {percent * 100:.1f}% 国家公地）"
        else:
            return f"贵族买地法案（出售 {percent * 100:.1f}% 国家公地）"

    # ===== 在 phase_senate.py 中完善 _auto_recruit_and_assign_legions_for_war =====
    def _auto_recruit_and_assign_legions_for_war(self, war, consul_id, action="declare"):
        """
        自动征召军团并指派给战争，返回 (征召数量, 总花费)
        action: "declare" 宣战, "takeover" 执政官接管, "restart" 停战恢复
        """
        ms = self.state.get_military_system()
        if not ms:
            print("      ⚠️ 军事系统不可用，无法征召军团")
            return 0, 0

        # 检查战争是否已有军团
        existing_legions = ms.get_legions_for_battle(war.id) if ms else []
        if existing_legions:
            if action == "takeover":
                consul = self.state.get_member(consul_id)
                consul_name = consul.get_formal_name() if consul else "执政官"
                print(f"      ✅ 执政官 {consul_name} 接管战争 {war.name}（已有 {len(existing_legions)} 个军团）")
            return 0, 0

        # 获取应征召的军团数量
        legions = getattr(war, 'proposed_legions', 0)
        if legions <= 0:
            min_leg = self.state.config.get("testing.min_legions", 4)
            max_leg = self.state.config.get("testing.max_legions", 8)
            legions = random.randint(min_leg, max_leg)
            print(f"      ℹ️ 战争未指定军团数，自动分配 {legions} 个")

        available = ms.get_available_legions()
        recruit_cost = self.state.get_economic_rule("legion_recruit_cost", 10)

        recruit_count = min(legions, len(available))
        if recruit_count == 0:
            print("      ⚠️ 没有可用军团，无法征召")
            return 0, 0

        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [r[0] for r in results if r[1]]
        if not recruited_numbers:
            print("      ⚠️ 军团征召失败")
            return 0, 0

        assigned, msg = ms.assign_to_war(recruited_numbers, war.id, consul_id)
        if assigned <= 0:
            print(f"      {msg}")
            return 0, 0

        for num in recruited_numbers:
            war.add_legion_number(num)

        total_cost = recruit_cost * len(recruited_numbers)
        consul = self.state.get_member(consul_id)
        consul_name = consul.get_formal_name() if consul else "执政官"

        if action == "takeover":
            print(
                f"      ✅ 执政官 {consul_name} 接管战争 {war.name}，征召 {recruit_count} 个军团，总花费 {total_cost} Talents，国库剩余 {self.state.treasury} Talents")
        elif action == "restart":
            print(
                f"      ✅ 战争 {war.name} 恢复，执政官 {consul_name} 征召 {recruit_count} 个军团，总花费 {total_cost} Talents，国库剩余 {self.state.treasury} Talents")
        else:  # declare
            print(f"      ✅ 宣战通过！执政官 {consul_name} 出征，影响力不再计入元老院。")
            print(
                f"      ✅ 征召 {recruit_count} 个军团，总花费 {total_cost} Talents，国库剩余 {self.state.treasury} Talents")

        self.state.log_event(
            f"{'宣战' if action == 'declare' else '接管' if action == 'takeover' else '恢复'} {war.name}，征召 {len(recruited_numbers)} 军团")
        return recruit_count, total_cost
