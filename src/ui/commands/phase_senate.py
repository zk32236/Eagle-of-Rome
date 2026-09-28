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
                 land_proposal_deciders: Optional[List[LandProposalDecider]] = None,
                 veto_decider: Optional[TribuneVetoDecider] = None):
        super().__init__(state)
        self.vote_decider = vote_decider if vote_decider is not None else AutoSenateVoteDecider()
        self.budget_decider = AutoBudgetDecider()
        # AU-R1-05a（C1，D-1 采纳）：takeover_decider 参数/属性已移除——resolve_senate 零
        # takeover；R5（DA-4）三入口统一经 propose_many / advance_senate_phase。
        # 继承 AI 接管触发（Direct Action 语义，D-4 语义不回归）。
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
        # R6（SA §A.4）：会话本地整包草稿（编辑阶段累积；Proposal 阶段一次 propose_many）
        self._package_drafts = []

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
        # WP-G-R4 (§2.3b)：失败不推进标记（guard/M/结算/部署拒绝 → 不 mark executed、
        # execute 返回非 True，给重试/退出窄路径）
        self._phase_failed = False
        # 重置临时数据
        self._passed_wars = []
        self._passed_contracts = []
        self._passed_land_acts = []
        self._peace_proposals = []
        self._package_drafts = []

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

        # WP-G-R4（SA v1.7 §2.3b）：尾部推进改经 senate_api.advance_senate_phase（唯一部署
        # owner）——CLI 不再自行 mark_phase_executed 绕过；失败不推进（不 mark executed、
        # 返回非 True），真实 R + 部署成功才完成阶段。
        if self._phase_failed:
            print("⚠️ 元老院阶段未完成（guard/结算/部署拒绝），未标记 executed；可重试或退出", flush=True)
            return False
        from src.api import senate_api as _sa
        player_id = getattr(self, "_current_consul_player_id", None) or self._get_current_player_id()
        if player_id:
            if self.state.get_current_player() is None or not self.state.is_current_player(player_id):
                self.state.set_current_player(player_id)
        adv = _sa.advance_senate_phase(self.state, player_id)
        if not adv["success"]:
            print(f"❌ 元老院阶段推进失败（不标记 executed，可重试/退出）: {adv['message']}", flush=True)
            return False
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
            # 获取主持人（WP-M D6：CLI 统一经单一权威 GameState.get_presiding_officer；无主持人 → 跳过提案）。
            host_figure = self.state.get_presiding_officer()
            if not host_figure:
                print("⚠️ 没有执政官，无法进行提案", flush=True)
                self._handle_next([])
                return

            consul_player = self.state.get_player_by_faction(host_figure.faction_id)
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
            # 获取主持人（WP-M D6：与 auto 模式同源——单一权威 GameState.get_presiding_officer）。
            host_figure = self.state.get_presiding_officer()

            if not host_figure:
                print("⚠️ 没有执政官，无法进行提案", flush=True)
                self._handle_next([])
                return

            consul_player = self.state.get_player_by_faction(host_figure.faction_id)
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
                    consul_faction = self.state.get_faction(host_figure.faction_id)
                    print(f"\n> 请输入操作({consul_faction.id}_CONSUL): ", end="", flush=True)
                    cmd_input = input().strip()
                    self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                    if not cmd_input:
                        continue
                    parts = cmd_input.split()
                    cmd = parts[0].lower()
                    if cmd in ("next", "n"):
                        # R6（SA §A.4）：Proposal 阶段一次 propose_many（0…N）；
                        # 失败停留编辑且保留 draft，成功后进入下一步。
                        if self._submit_local_package():
                            self._handle_next([])
                            break
                        continue
                    elif cmd == "propose":
                        self._handle_propose(parts[1:])
                    else:
                        print("未知命令，支持 propose、next", flush=True)
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


        from src.core.systems.political_system import PoliticalSystem
        politics = PoliticalSystem(self.state)
        passed_proposals = []
        for proposal in proposals:
            result = politics.calculate_vote_result(proposal)
            if result.get("passed") and not result.get("vetoed"):
                passed_proposals.append(proposal)

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
        # R5（SA §2.3b/§2.7 A-I14 / §5.2 C-M09，DA-4）：human 零提案 next/n 路径——先显式空选择写 P
        # （提交 []，合法政治决策）；mandatory Takeover 门（M_open）已退役，不再拒绝空结束；
        # 结算失败/guard 拒绝 → _phase_failed（不 mark executed/不 return True，可重试/退出）
        player_id = self._proposal_player_id()
        if (not self.state.get_senate_proposals()
                and not self.state.senate_proposal_decision_complete
                and not self.state.get_phase_result("senate")):
            empty = senate_api.propose_many(self.state, player_id, [])
            if not empty.get("success"):
                print(f"❌ 显式空选择失败: {empty.get('message')}", flush=True)
                self._phase_failed = True
                self._step += 1
                return
            print("   （显式空选择：本会期不提交法案——提案选择完成）")

        # R6（SA §D.1.1，DA-4 B1／承接 DA-3 P-B4-5）：CLI 与 GUI/API 同入口——直接调用服务端
        # 唯一 finalization 完成协议 `finalize_senate_if_ready`（`resolve_senate` 已退役为其
        # 兼容别名，二者等价）；CLI 不再自持第二结算路径。
        result = senate_api.finalize_senate_if_ready(
            self.state,
            vote_decider=self.vote_decider,
        )
        if result["success"]:
            passed_snapshot = result["data"].get("passed_proposals_snapshot", [])
            self._print_announcement_header(passed_snapshot)
            if result["message"]:
                print(result["message"])

            # R6（SA §C.5.2，DA-3 B4）：CLI 第二调用退役——删除 `_handle_step_5` 内
            # Fleet / Governor / Rebellion 三个 hook 的**直接调用**（含其打印分支）。
            # 政治 finalization（含 Governor 政治步骤 + 只读 `retained_effect_intents` 登记）
            # 已由 `senate_api.resolve_senate` 服务端完成；军事效果（Fleet / 起义）的唯一
            # 调用点 = 边界事务自动层（`PoliticalSystem.commit_war_resolution`）。CLI 仅消费
            # `resolve_senate` / 服务端 `finalize_senate_if_ready`，与 GUI/AI 同源，
            # 无第二军事执行者。
        else:
            # WP-G-R4（§2.3b）：resolve 被 guard/M/phase/权限拒绝 → 失败不推进
            print(f"❌ 结算失败: {result['message']}", flush=True)
            self._phase_failed = True

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

        # 构建提案映射并分配 ID
        proposals_map = {}
        idx = 1

        # R6（SA §A.4）：War 草案统一消费同一 WarCardView（含真实 command / pending peace）；
        # route 唯一来源 = card.authority_by_mode（缺 route 不列出，不 fallback）。
        from src.core.systems.political_system import PoliticalSystem
        current_turn = self.state.turn.turn_number if self.state.turn else None
        cards = PoliticalSystem(self.state).build_war_card_views({"current_turn": current_turn})
        for card in cards:
            routes = card.get("authority_by_mode") or {}
            for mode in (card.get("allowed_modes") or []):
                authority = routes.get(mode)
                if authority not in ("senate_vote", "consul_direct"):
                    continue
                key = f"B{idx:02d}"
                proposals_map[key] = ("war", {"war_id": card.get("war_id"), "mode": mode,
                                              "card": card})
                route_label = "元老院表决" if authority == "senate_vote" else "执政官决定"
                mode_label = "停战" if mode == "peace" else "作战"
                print(f"       {key} {card.get('war_name')}（{mode_label} · {route_label}）")
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
        print("   1. propose <草案ID> [参数] → 加入整包草稿（不发布；可多次编辑）")
        print("      示例:")
        print("            propose B01 2 6   (War 草案：target Commander=2，N=6)")
        print("            propose B02 80    (预算草案 80 塔兰特)")
        print("            propose B03       (停战草案，无参数)")
        print("            propose B04 1     (总督草案：候选人ID)")
        print("            propose B05 50    (土地草案：50 C)")
        # R6（SA §A.4）：CLI 入口与 Human/AI 同源——编辑本地整包草稿，一次 propose_many（0…N），
        # 推进统一经 advance_senate_phase（唯一 owner）；legacy 单提案入口不再是生产 CLI 路径。
        print("   2. next/n → 一次提交整包（propose_many 0…N）并进入元老院表决环节")

    def _handle_propose(self, args: List[str]):
        """R6（SA §A.4）：编辑会话本地整包草稿（不发布）。

        格式：``propose <草案ID> [参数]``
          - War 草案（统一 War Card）：``propose B01 [target_id] [N]``
          - 非 War 草案：``propose B0x [参数]``（governor/budget/land）

        发布统一在 Proposal 阶段 ``next/n`` 一次 ``propose_many``（0…N）；失败停留编辑
        且保留草稿。legacy 单提案入口（senate_api.propose）不再是生产 CLI 路径。
        """
        if len(args) < 1:
            print("❌ 用法: propose <法案ID> [参数]", flush=True)
            return

        proposal_id = args[0].upper()
        if not hasattr(self, "_proposals_map") or proposal_id not in self._proposals_map:
            print(f"❌ 无效的法案ID: {proposal_id}", flush=True)
            return

        proposal_type, base_params = self._proposals_map[proposal_id]
        if proposal_type == "war":
            self._stage_war_draft(base_params, args[1:])
            return
        kwargs, ok = self._parse_non_war_params(proposal_type, base_params, args[1:])
        if not ok:
            return
        self._stage_non_war_draft(proposal_type, kwargs)

    def _stage_war_draft(self, card_params: dict, extra_args: List[str]):
        """R6（SA §A.4）：把一张 War Card 的（mode + target + N）加入会话本地整包草稿。

        一个 (session_id, war_id) 最多一个 authoritative item，command/peace 互斥——
        同 war 再次 propose 覆盖旧草案；绝不在发布后再换将。缺 route 不 fallback
        （fail-closed，不入草稿）。
        """
        card = card_params.get("card") or {}
        mode = card_params.get("mode", "command")
        war_id = card_params.get("war_id")
        authority = (card.get("authority_by_mode") or {}).get(mode)
        if authority not in ("senate_vote", "consul_direct"):
            print("❌ 该 War Card 缺可用路由（请刷新后重试），不入草稿", flush=True)
            return
        defaults = card.get("defaults") or {}
        target = defaults.get("target_commander_id")
        n = defaults.get("reinforcement_n")
        remaining = list(extra_args or [])
        if mode == "peace":
            target, n = None, None  # 停战：丢弃 Commander/N 缓存
        else:
            if remaining:
                try:
                    target = int(remaining[0])
                    remaining = remaining[1:]
                except ValueError:
                    print("❌ target Commander ID 必须是整数", flush=True)
                    return
            if remaining:
                try:
                    n = int(remaining[0])
                except ValueError:
                    print("❌ 军团数量必须是整数", flush=True)
                    return
            if target is None:
                print("❌ 缺 target Commander（无 DTO default 可用），请显式指定", flush=True)
                return
        self._package_drafts = [
            d for d in self._package_drafts
            if not (d.get("type") == "war_proposal" and d.get("war_id") == war_id)
        ]
        self._package_drafts.append({
            "type": "war_proposal", "war_id": war_id, "checked": True, "mode": mode,
            "target_commander_id": target, "reinforcement_n": n,
        })
        mode_label = "停战" if mode == "peace" else "作战"
        detail = "" if mode == "peace" else f"（Commander={target}，N={n}）"
        print(f"✅ 已加入整包草稿：{card.get('war_name')} [{mode_label}]{detail}", flush=True)
        self._print_package_drafts()

    def _parse_non_war_params(self, proposal_type: str, base_params: dict, extra_args: List[str]):
        """解析非 War 草案参数（返回 (kwargs, ok)）；不发布。"""
        kwargs = dict(base_params)
        args = list(extra_args or [])
        if proposal_type == "governor":
            if not args:
                print("❌ 总督任命需要指定候选人ID", flush=True)
                return kwargs, False
            try:
                kwargs["candidate_id"] = int(args[0])
            except ValueError:
                print("❌ 候选人ID必须是数字", flush=True)
                return kwargs, False
        elif proposal_type == "budget":
            if args:
                try:
                    kwargs["modified_budget"] = int(args[0])
                except ValueError:
                    print("❌ 修改预算必须是数字，请使用纯数字（如 80）", flush=True)
                    return kwargs, False
        elif proposal_type == "land":
            if not args:
                print("❌ 土地法案需要指定数量（C）", flush=True)
                return kwargs, False
            try:
                raw = float(args[0])
            except ValueError:
                print("❌ 土地数量必须是数字", flush=True)
                return kwargs, False
            # R6（SA §A.4）：旧 percent 输入在 CLI 归一为既有 amount_C（不扩大公地规则）。
            national = self.state.get_national_public_land()
            amount_C = int(round(raw * national)) if 0 < raw < 1 else int(raw)
            kwargs.pop("percent", None)
            kwargs["amount_C"] = amount_C
        return kwargs, True

    def _draft_identity(self, draft: dict):
        t = draft.get("type")
        params = draft.get("params") or {}
        if t == "war_proposal":
            return (t, draft.get("war_id"), draft.get("mode"))
        if t == "budget":
            return (t, params.get("contract_id"))
        if t == "governor":
            return (t, params.get("province_id"))
        if t == "land":
            return (t, params.get("act_type"))
        return (t, params.get("contract_id") or params.get("province_id") or params.get("act_type"))

    def _stage_non_war_draft(self, proposal_type: str, kwargs: dict):
        """R6（SA §A.4）：把非 War 草案加入会话本地整包草稿（同 identity 覆盖，不发布）。"""
        new_draft = {"type": proposal_type, "params": dict(kwargs)}
        identity = self._draft_identity(new_draft)
        self._package_drafts = [
            d for d in self._package_drafts if self._draft_identity(d) != identity
        ]
        self._package_drafts.append(new_draft)
        print(f"✅ 已加入整包草稿：{self._generate_proposal_description(proposal_type, kwargs)}",
              flush=True)
        self._print_package_drafts()

    def _print_package_drafts(self):
        if not self._package_drafts:
            print("   （整包草稿为空——next 将提交空选择）", flush=True)
            return
        print(f"   📦 当前整包草稿（{len(self._package_drafts)} 项）：", flush=True)
        for draft in self._package_drafts:
            print(f"      · {self._describe_draft(draft)}", flush=True)

    def _describe_draft(self, draft: dict) -> str:
        t = draft.get("type")
        if t == "war_proposal":
            ws = self.state.get_war_system()
            war = ws.get_war_by_id(draft.get("war_id")) if ws else None
            name = war.name if war else draft.get("war_id")
            mode_label = "停战" if draft.get("mode") == "peace" else "作战"
            return (f"{name} [{mode_label}] Commander={draft.get('target_commander_id')} "
                    f"N={draft.get('reinforcement_n')}")
        return self._generate_proposal_description(t, draft.get("params") or {})

    def _submit_local_package(self) -> bool:
        """R6（SA §A.4）：一次 propose_many 提交整包（0…N）。

        失败 → 返回 False（停留编辑、保留草稿）；成功 → 关闭本会期选择。
        """
        from src.api import senate_api
        if self.state.senate_proposal_decision_complete:
            return True
        player_id = self._proposal_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", flush=True)
            return False
        result = senate_api.propose_many(self.state, player_id, list(self._package_drafts))
        if result.get("success"):
            created = (result.get("data") or {}).get("created") or []
            print(f"✅ 已提交整包（{len(self._package_drafts)} 项草案；{len(created)} 项已发布）",
                  flush=True)
            return True
        print(f"❌ 整包提交失败: {result.get('message')}（草稿保留，可继续编辑或重试）", flush=True)
        return False

    # R5（SA §5.2 C-M08，DA-4）：CLI 旧接管/取消子命令及处理器已退役——
    # Human/AI/CLI 三入口统一经 Package Submit（propose_many）；无第二 mutation owner。
    def _proposal_player_id(self):
        if hasattr(self, "_current_consul_player_id") and self._current_consul_player_id:
            return self._current_consul_player_id
        return self._get_current_player_id()

    def _get_current_player_id(self) -> Optional[str]:
        """获取当前玩家ID（直接使用游戏状态中的当前玩家）"""
        player = self.state.get_current_player()
        return player.player_id if player else None

    # _execute_war_takeover_manual removed in S5 — logic migrated to senate_api.process_war_takeover

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



    def _auto_generate_proposals(self):
        """为AI玩家自动生成所有提案（委托至 senate_api.auto_submit_proposals）"""
        from src.api import senate_api

        consul_player_id = self._current_consul_player_id
        if not consul_player_id:
            return

        result = senate_api.auto_submit_proposals(
            self.state,
            budget_decider=self.budget_decider,
            land_proposal_deciders=self.land_proposal_deciders,
        )
        if result["success"]:
            proposals = result["data"].get("proposals", [])
            if proposals:
                print("\n✅ 执政官提案:")
                for idx, prop in enumerate(proposals, 1):
                    print(f"\tB{idx:02d} {prop['description']}")
        else:
            print(f"⚠️ 自动提案失败: {result['message']}", flush=True)

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



    def _restore_rejected_peace_wars(self, wars: List[War]) -> None:
        """将否决/未提交的停战草案恢复为活跃战争，保留旧指挥官信息，由接管逻辑处理"""
        if not wars:
            return
        ws = self.state.get_war_system()
        for war in wars:
            ws.restore_rejected_peace_treaty(war.id, preserve_commander=True)

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
        """为指定玩家（派系）自动投票（委托 senate_api）"""
        from src.api import senate_api
        senate_api.auto_vote(self.state, player_id, proposals, self.vote_decider)

    def _print_announcement_header(self, passed_proposals: list):

        for prop in passed_proposals:
            prop_id = prop["id"]
            desc = self._generate_proposal_description(prop["type"], prop)
            print(f"\t\tB{prop_id:02d} {desc}")
        print()


    # ==================== S5: _assign_rebellion_commanders removed — logic migrated to war_system.assign_rebellion_commanders ====================


# =================================== MVP 0.1-0.5 =============================================

    # S5: _execute_governor_appointments and _process_governor_appointments removed — logic migrated to senate_api.assign_governors

    def _get_tribune(self) -> Optional['Figure']:
        """获取当前保民官（假设只有一人）。

        AU-R2-3c（T5 收敛）：委托 PoliticalSystem._find_any_eligible_tribune——全局 living
        成员 + 单一谓词 _is_eligible_tribune（FACT-6：living 成员下 is_dead 校验冗余 →
        行为等价；方案 B：is_absent 不参与判定）。
        """
        from src.core.systems.political_system import PoliticalSystem
        return PoliticalSystem(self.state)._find_any_eligible_tribune()

    def _execute_war_declaration(self, war: "War", consul_id: int, legions: int):
        """[DA-3 B4 / DA-Plan R-1 退役 shim] — **死代码**（静态负测证明零调用者）。

        原 S4 单提案 CLI 宣战路径（激活战争 + `ws.auto_recruit_and_assign()` 征召）已随
        R6 整包发布 + 唯一边界事务退役；保留签名以维持兼容面，返回**无副作用失败 shim**
        （不激活战争、不征召、不改 commander、不改主持人）。统一语义 =
        `LEGACY_WAR_EXECUTION_RETIRED`。
        """
        return {
            "success": False,
            "code": "LEGACY_WAR_EXECUTION_RETIRED",
            "message": "use package and advance",
        }

    # _process_land_proposals and _get_land_act_description have been removed.
    # Land proposals are now handled entirely through senate_api.auto_submit_proposals()
    # and senate_api.resolve_senate(). See wave-02 S3/S4.

    # S5: _auto_recruit_and_assign_legions_for_war removed — logic migrated to war_system.auto_recruit_and_assign
