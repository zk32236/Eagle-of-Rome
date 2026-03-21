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
from src.core.entities.war import WarStatus
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.war_takeover_decider import WarTakeoverDecider
from src.core.deciders.impl.auto_land_proposal_decider import AutoLandProposalDecider
from src.core.deciders.land_proposal_decider import LandProposalDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.deciders.impl.auto_tribune_veto_decider import AutoTribuneVetoDecider

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

    # ==================== 新增：MVP0.7-11 ====================
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
                            print("❌ 人物ID必须是数字", file=sys.stderr)
                            sys.stderr.flush()
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
                                        print(f"派系 {faction.name} 无存活成员", file=sys.stderr)
                                        sys.stderr.flush()
                                else:
                                    print(result["message"], file=sys.stderr)
                                    sys.stderr.flush()
                        else:
                            print("无法获取当前玩家", file=sys.stderr)
                            sys.stderr.flush()
                else:
                    print("未知命令，支持 investigate <人物ID>、next/n", file=sys.stderr)
                    sys.stderr.flush()

    def _handle_step_1(self):
        if self._auto_mode:
            # 自动模式：原有逻辑
            self._process_war_proposals(self._passed_wars)
            peace_proposals = self._process_peace_proposals(TerminologyService.get())
            self._process_governor_appointments(TerminologyService.get())
            self._process_budget_proposals(TerminologyService.get(), self._passed_contracts)
            self._process_land_proposals(TerminologyService.get(), self._passed_land_acts)

            if peace_proposals:
                self.passed_peace_treaties = self._vote_on_peace_proposals(peace_proposals)
                for war in self.passed_peace_treaties:
                    print(f"  - {war.name}")
            if self._auto_mode:
                self._handle_next([])

        else:
            # 手动模式：获取当前玩家
            player = self.state.get_current_player()
            if not player:
                print("⚠️ 无法获取当前玩家", file=sys.stderr)
                self._handle_next([])
                return

            # 先处理停战草案（自动投票）
            peace_proposals = self._process_peace_proposals(TerminologyService.get())
            if peace_proposals:
                self.passed_peace_treaties = self._vote_on_peace_proposals(peace_proposals)
                for war in self.passed_peace_treaties:
                    print(f"  - {war.name}")

            # 显示可选提案列表并进入交互循环
            self._print_proposal_options()
            while True:
                print("\n> 请输入操作(CONSUL): ", end="", flush=True)
                cmd_input = input().strip()
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                if cmd in ("next", "n"):
                    self._handle_next([])
                    break
                elif cmd == "propose":
                    self._handle_propose(parts[1:])
                else:
                    print("未知命令，支持 propose 和 next", file=sys.stderr)
                    sys.stderr.flush()

    def _handle_step_2(self):
        # 表决环节（现有逻辑中无单独表决，直接跳过）
        #if self._auto_mode:
        self._handle_next([])

    def _handle_step_3(self):
        # 公示环节（现有逻辑中结果已在提案时打印，直接跳过）
        #if self._auto_mode:
        self._handle_next([])

    def _handle_step_4(self):
        tribune = self._get_tribune()
        if tribune:
            print(f"\n   🛡️ 保民官 {tribune.name} 正在审查通过的提案...")
            # 宣战否决
            new_wars = []
            for war, consul_id, legions in self._passed_wars:
                if self.veto_decider.decide_veto(war, tribune.id, self.state):
                    print(f"      ❌ 保民官否决了宣战：{war.name}")
                    self.state.log_event(f"保民官否决宣战: {war.name}")
                else:
                    new_wars.append((war, consul_id, legions))
            self._passed_wars = new_wars

            # 停战草案否决
            new_peace = []
            for war in self.passed_peace_treaties:
                issue = {'type': 'peace', 'war_id': war.id, 'treaty': war.peace_treaty}
                veto_result = self.veto_decider.decide_veto(issue, tribune.id, self.state)
                if veto_result:
                    print(f"      ❌ 保民官否决了 {war.name} 的停战草案")
                    self.state.log_event(f"保民官否决停战草案: {war.name}")
                    war.clear_peace_treaty()
                    war_system = self.state.get_war_system()
                    if war_system:
                        war_system._move_to_active(war)
                else:
                    new_peace.append(war)
            self.passed_peace_treaties = new_peace

            # 总督否决
            new_governors = []
            for gov in self.proposed_governors:
                issue = {
                    'type': 'governor_appointment',
                    'province_id': gov['province_id'],
                    'new_governor_id': gov['new_governor_id'],
                    'old_governor_id': gov['old_governor_id']
                }
                if self.veto_decider.decide_veto(issue, tribune.id, self.state):
                    province = self.state.get_province(gov['province_id'])
                    prov_name = province.name if province else f"ID:{gov['province_id']}"
                    print(f"      ❌ 保民官否决了行省 {prov_name} 的总督任命")
                    self.state.log_event(f"保民官否决行省 {prov_name} 总督任命")
                else:
                    new_governors.append(gov)
            self.proposed_governors = new_governors

            # 合同否决
            new_contracts = []
            for contract in self._passed_contracts:
                if self.veto_decider.decide_veto(contract, tribune.id, self.state):
                    print(f"      ❌ 保民官否决了合同：{contract.name}")
                    self.state.log_event(f"保民官否决合同: {contract.name} (ID:{contract.id})")
                else:
                    new_contracts.append(contract)
            self._passed_contracts = new_contracts

            # 土地法案否决
            new_acts = []
            for act in self._passed_land_acts:
                if self.veto_decider.decide_veto(act, tribune.id, self.state):
                    act_type = act['type']
                    percent = act['percent']
                    desc = self._get_land_act_description(act_type, percent)
                    print(f"      ❌ 保民官否决了土地法案：{desc}")
                    self.state.log_event(f"保民官否决土地法案: {desc}")
                else:
                    new_acts.append(act)
            self._passed_land_acts = new_acts
        else:
            print(f"\n   🛡️ 当前无保民官，不行使否决权")

        # 无论自动还是手动，都推进到下一步
        self._handle_next([])

    def _handle_step_5(self):
        # 原执行逻辑
        # 5.1 宣战
        for war, consul_id, legions in self._passed_wars:
            self._execute_war_declaration(war, consul_id, legions)

        # 5.2 总督任命
        self._execute_governor_appointments()
        self._assign_rebellion_commanders()

        # 5.3 战争接管
        self._process_war_takeover()

        # 5.4 停战草案执行
        self._execute_passed_peace_treaties()

        # 5.5 合同状态变更
        for contract in self._passed_contracts:
            contract.status = ContractStatus.BUDGETED
            print(f"      ✅ {contract.name} 预算通过，状态变为 BUDGETED")
            self.state.log_event(f"合同预算通过：{contract.name}")

        # 5.6 土地法案存储
        for act in self._passed_land_acts:
            if act['type'] == 'sale':
                national_land = self.state.get_national_public_land()
                amount = int(national_land * act['percent'])
                self.state.set_pending_land_sale_quota(amount)
                print(f"      ✅ {act['description']} 通过，批准出售 {amount} C 国家公地，待下回合认购。")
            else:
                self.state.add_pending_land_act(act)
                amount_disp = act.get('amount', 0)
                print(f"      ✅ {act['description']} 通过，批准分配 {amount_disp} C 国家公地，待下回合执行。")

        # 自动模式下直接完成（无下一步）
        self._step += 1  # 退出循环

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

        # 战争威胁
        for war in data.get("war_threats", []):
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
            print(f"       B{idx:02d} {contract['name']} 预算案")
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

    def _handle_manual_proposal_loop(self):
        """手动模式下处理提案输入循环"""
        while True:
            print("\n> 请输入操作(CONSUL): ", end="", flush=True)
            cmd_input = input().strip()
            if not cmd_input:
                continue
            parts = cmd_input.split()
            cmd = parts[0].lower()
            if cmd in ("next", "n"):
                break
            elif cmd == "propose":
                self._handle_propose(parts[1:])
            else:
                print("未知命令，支持 propose 和 next", file=sys.stderr)
                sys.stderr.flush()

    def _handle_propose(self, args: List[str]):
        """处理 propose 命令，格式：propose <提案ID> [参数]"""
        if len(args) < 1:
            print("❌ 用法: propose <法案ID> [参数]", file=sys.stderr)
            return

        proposal_id = args[0].upper()
        if not hasattr(self, "_proposals_map") or proposal_id not in self._proposals_map:
            print(f"❌ 无效的法案ID: {proposal_id}", file=sys.stderr)
            return

        proposal_type, base_params = self._proposals_map[proposal_id]
        kwargs = base_params.copy()

        # 根据提案类型补充额外参数
        if proposal_type == "war":
            if len(args) < 2:
                print("❌ 宣战提案需要指定军团数量", file=sys.stderr)
                return
            try:
                legions = int(args[1])
            except ValueError:
                print("❌ 军团数量必须是数字", file=sys.stderr)
                return
            kwargs["legions"] = legions

        elif proposal_type == "peace":
            # 停战不需要额外参数
            pass

        elif proposal_type == "governor":
            if len(args) < 2:
                print("❌ 总督任命需要指定候选人ID", file=sys.stderr)
                return
            try:
                candidate_id = int(args[1])
            except ValueError:
                print("❌ 候选人ID必须是数字", file=sys.stderr)
                return
            kwargs["candidate_id"] = candidate_id

        elif proposal_type == "budget":
            # 预算合同可选的修改预算
            if len(args) >= 2:
                try:
                    modified_budget = int(args[1])
                    kwargs["modified_budget"] = modified_budget
                except ValueError:
                    print("❌ 修改预算必须是数字，忽略该参数", file=sys.stderr)

        elif proposal_type == "land":
            if len(args) < 2:
                print("❌ 土地法案需要指定百分比（如 0.05 表示 5%）", file=sys.stderr)
                return
            try:
                percent = float(args[1])  # 直接使用小数，不再除以100
            except ValueError:
                print("❌ 百分比必须是数字", file=sys.stderr)
                return
            kwargs["percent"] = percent

        # 获取当前玩家
        player_id = self._get_current_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", file=sys.stderr)
            return

        # 特殊处理 takeover：直接执行，不经过 API
        if proposal_type == "takeover":
            if len(args) < 2:
                print("❌ 接管战争需要指定增援军团数量", file=sys.stderr)
                return
            try:
                additional_legions = int(args[1])
            except ValueError:
                print("❌ 军团数量必须是数字", file=sys.stderr)
                return

            war_id = kwargs["war_id"]
            # 执行接管
            success = self._execute_war_takeover_manual(war_id, player_id, additional_legions)
            if success:
                # 注意：实际征召数量在 _execute_war_takeover_manual 内部打印，无需额外打印
                # print(f"✅ 已接管战争，增援 {additional_legions} 个军团")
                pass
            else:
                print(f"❌ 接管失败，请检查战争状态或权限", file=sys.stderr)
            return

        # 调用 API
        from src.api import senate_api
        result = senate_api.propose(self.state, player_id, proposal_type, **kwargs)
        if result["success"]:
            description = self._generate_proposal_description(proposal_type, kwargs)
            print(f"✅ {description}")
        else:
            print(f"❌ {result['message']}", file=sys.stderr)

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
            print("❌ 您没有在罗马的执政官可以出征", file=sys.stderr)
            return False

        ws = self.state.get_war_system()
        war = ws.get_war_by_id(war_id) if ws else None
        if not war:
            print("❌ 战争不存在", file=sys.stderr)
            return False
        if war.rebellion_province_id is not None:
            print("❌ 起义战争应由总督自动接管，不能由执政官接管", file=sys.stderr)
            return False
        if war.status != WarStatus.ACTIVE:
            print(f"❌ 战争 {war.name} 状态为 {war.status}，无法接管", file=sys.stderr)
            return False
        if war.commander_id is not None:
            # 已有指挥官，但可能为其他执政官或前执政官
            print(f"⚠️ 战争已有指挥官，执政官将接管并增派军团", file=sys.stderr)

        # 执行接管
        # 1. 设置指挥官
        old_commander = self.state.get_member(war.commander_id) if war.commander_id else None
        war.commander_id = consul.id
        consul.is_absent = True

        # 2. 增派军团
        ms = self.state.get_military_system()
        if not ms:
            print("❌ 军事系统不可用", file=sys.stderr)
            return False

        # 获取可用军团
        available = ms.get_available_legions()
        if not available:
            print("❌ 没有可用军团", file=sys.stderr)
            return False

        recruit_count = min(additional_legions, len(available))
        if recruit_count == 0:
            print("❌ 无法征召军团", file=sys.stderr)
            return False
        print(f"✅ 已接管战争，增援 {recruit_count} 个军团")

        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [r[0] for r in results if r[1]]
        if not recruited_numbers:
            print("❌ 军团征召失败", file=sys.stderr)
            return False

        # 指派军团到战争（不覆盖已有军团）
        assigned, msg = ms.assign_to_war(recruited_numbers, war.id, consul.id)
        if assigned > 0:
            for num in recruited_numbers:
                war.add_legion_number(num)
            print(f"      {msg}")
        else:
            print(f"❌ 军团指派失败: {msg}", file=sys.stderr)
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

    # ==================== 新增：停战草案相关方法 ====================

    def _process_peace_proposals(self, terms):
        """收集所有待决停战草案，并自动提交给元老院"""
        war_system = self.state.get_war_system()
        if not war_system:
            return []

        pending_wars = war_system.get_truce_wars_with_pending_treaty()
        if not pending_wars:
            return []

        print(f"\n\t====================== 停战草案审批 ====================")
        proposals = []
        for war in pending_wars:
            treaty = war.peace_treaty
            print(f"      📜 {war.name}：赔款 {treaty['indemnity']} 塔兰特，有效期 {treaty['duration']} 回合")
            proposals.append(war)

        # 标记为已提交
        for war in proposals:
            treaty = war.peace_treaty
            if treaty:
                war.set_peace_treaty_status('submitted')
        return proposals

    def _vote_on_peace_proposals(self, proposals: List["War"]):
        """对提交的停战草案进行元老院投票"""
        if not proposals:
            return []

        passed = []
        for war in proposals:
            print(f"\n      📜 表决停战：{war.name}")
            treaty = war.peace_treaty

            votes_for = 0
            votes_against = 0
            total_influence = 0

            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence

                issue = {'type': 'peace', 'war_id': war.id, 'treaty': treaty}
                support = self.vote_decider.decide_vote(issue, faction, self.state)

                if support:
                    votes_for += influence
                    print(f"          {faction.name} 支持，影响力 {influence}")
                else:
                    votes_against += influence
                    print(f"          {faction.name} 反对，影响力 {influence}")

            if total_influence == 0:
                print(f"          无元老在场，草案未通过。")
                continue

            support_ratio = votes_for / total_influence
            print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                passed.append(war)
                print(f"          ✅ 停战草案通过，等待保民官否决")
            else:
                print(f"          ❌ 停战草案否决")
                war.clear_peace_treaty()
                war_system = self.state.get_war_system()
                if war_system:
                    war_system._move_to_active(war)


        for war in passed:
            print(f"  - {war.name}")

        return passed

    def _execute_passed_peace_treaties(self):
        """执行通过的停战草案：记录赔款、待解散军团、到期回合"""
        war_system = self.state.get_war_system()
        if not war_system or not self.passed_peace_treaties:
            return

        for war in self.passed_peace_treaties:
            print(f"  - {war.name}")
            treaty = war.peace_treaty
            if not treaty or treaty.get('status') != 'submitted':
                continue

            war.set_peace_treaty_status('approved')
            war.set_indemnity_due(treaty['indemnity'])

            # ===== 新增：召回所有军团，解除与战争的关联 =====
            ms = self.state.get_military_system()
            if ms:
                ms.recall_from_war(war.id)

            if war.legion_numbers:
                war_system.add_legions_to_disband(war.legion_numbers)

            end_turn = self.state.turn.turn_number + treaty['duration']
            war.set_truce_end_turn(end_turn)

            print(f"      ✅ {war.name} 停战草案已批准，赔款 {treaty['indemnity']}，有效期 {treaty['duration']} 回合")
            self.state.log_event(
                f"停战草案批准: {war.name} 赔款 {treaty['indemnity']}",
                extra={'type': 'peace_treaty_approved', 'war_id': war.id}
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

            # 记录旧总督，供决算阶段返回
            province._old_governor_id = gov['old_governor_id']
            # 设置候任总督
            province._governor_designate_id = gov['new_governor_id']

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

        # 获取所有已征服的行省
        all_provinces = [p for p in self.state.get_all_provinces() if p.conquered and p.province_id != 0]

        # 行省分类（仅基于已征服行省）
        proconsul_provinces = [p for p in all_provinces if p.governor_type == "proconsul"]
        propraetor_provinces = [p for p in all_provinces if p.governor_type == "propraetor"]

        # 候选人获取函数（不变）
        def get_candidates(office_type: str):
            cand_list = []
            for fig in self.state.get_living_members():
                if fig.is_absent:
                    continue
                # 排除现任官职（非 ex- 开头）
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

        # 修改 assign 函数，增加 used_set 参数
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

        # 打印分配结果（不变）
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

        # 提示未被分配的行省（仅针对已征服行省）
        all_provinces_set = set(proconsul_provinces + propraetor_provinces)
        assigned_provinces = set(p for p, _ in proconsul_assignments + propraetor_assignments)
        unassigned = all_provinces_set - assigned_provinces
        if unassigned:
            for p in unassigned:
                print(f"      ⚠️ {p.name} 无合格候选人，现任总督留任一年")

        # 构建提案（仅针对已征服行省）
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

        # 征召军团并指派
        ms = self.state.get_military_system()
        if ms:
            # 原有自动征召逻辑（可复用 _auto_recruit_and_assign_legions_for_war）
            self._auto_recruit_and_assign_legions_for_war(war, consul_id)

        consul.is_absent = True
        self.state.log_event(f"宣战通过：{war.name}，执政官 {consul.name} 出征，批准军团 {legions}")
        print(f"      ✅ 宣战通过！执政官 {consul.name} 出征，影响力不再计入元老院。")
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

    def _vote_on_land_act(self, act: dict):
        """对土地法案进行元老院投票"""
        votes_for = 0
        votes_against = 0
        total_influence = 0

        for faction in self.state.get_active_factions():
            influence = faction.get_senate_influence(self.state)
            if influence == 0:
                continue
            total_influence += influence

            # 使用通用投票决策器
            support = self.vote_decider.decide_vote(act, faction, self.state)
            if support:
                votes_for += influence
                print(f"          {faction.name} 支持，影响力 {influence}")
            else:
                votes_against += influence
                print(f"          {faction.name} 反对，影响力 {influence}")

        if total_influence == 0:
            print(f"          无元老在场，法案未通过。")
            return

        support_ratio = votes_for / total_influence
        print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")
        if support_ratio > 0.5:
            print(f"          ✅ 法案通过！")
            self.state.add_pending_land_act(act)
            self.state.log_event(
                f"土地法案通过: {act['description']}",
                extra={"type": "land_act", "act": act['type'], "percent": act['percent']}
            )
        else:
            print(f"          ❌ 法案否决。")

    def _process_war_takeover(self):
        ws = self.state.get_war_system()
        if not ws:
            self.state.log_event(
                "[DEBUG] _process_war_takeover: 无战争系统",
                level=logging.DEBUG,
                extra={"function": "_process_war_takeover", "reason": "no_war_system"}
            )
            return

        active_wars = ws.get_active_wars()
        self.state.log_event(
            f"[DEBUG] _process_war_takeover 开始: 活跃战争列表 = {[w.id for w in active_wars]}",
            level=logging.DEBUG,
            extra={"function": "_process_war_takeover", "active_wars": [w.id for w in active_wars], "phase": "enter"}
        )

        # ----- 防御性清理：移除 leader_ids 中已死亡或不存在的人物 -----
        if self.state.turn and hasattr(self.state.turn, 'leader_ids'):
            valid_leaders = []
            for lid in self.state.turn.leader_ids:
                leader = self.state.get_member(lid)
                if leader and not leader.is_dead:
                    valid_leaders.append(lid)
                else:
                    self.state.log_event(
                        f"[DEBUG] 清理 leader_ids 中的死亡/无效人物 {lid}",
                        level=logging.DEBUG,
                        extra={"function": "_process_war_takeover", "removed_id": lid}
                    )
            self.state.turn.leader_ids = valid_leaders
        # ------------------------------------------------------------

        if not active_wars:
            self.state.log_event(
                "[DEBUG] _process_war_takeover 结束: 无活跃战争",
                level=logging.DEBUG,
                extra={"function": "_process_war_takeover", "phase": "exit", "reason": "no_active_wars"}
            )
            return

        # 获取执政官（清理后取第一个）
        if not self.state.turn.leader_ids:
            self.state.log_event(
                "[DEBUG] _process_war_takeover 结束: 无存活执政官",
                level=logging.DEBUG,
                extra={"function": "_process_war_takeover", "phase": "exit", "reason": "no_surviving_consul"}
            )
            return
        consul_id = self.state.turn.leader_ids[0]
        consul = self.state.get_member(consul_id)
        if not consul:
            # 理论上不应发生，但保留防御
            self.state.log_event(
                f"[DEBUG] _process_war_takeover 结束: 执政官 {consul_id} 无效",
                level=logging.DEBUG,
                extra={"function": "_process_war_takeover", "phase": "exit", "reason": "consul_invalid"}
            )
            if consul_id in self.state.turn.leader_ids:
                self.state.turn.leader_ids.remove(consul_id)
            return

        # 打印每个战争的当前状态
        for war in active_wars:
            print(f"  - {war.name}, status: {war.status}, commander_id: {war.commander_id}")
            self.state.log_event(
                f"[DEBUG] _process_war_takeover 检查战争: {war.id}, 状态={war.status.value}, 指挥官ID={war.commander_id}",
                level=logging.DEBUG,
                extra={"function": "_process_war_takeover", "war_id": war.id, "status": war.status.value,
                       "commander_id": war.commander_id}
            )

        for war in active_wars:
            if war.status != WarStatus.ACTIVE:
                continue

            if war.commander_id is None:
                takeover_decision = self.takeover_decider.decide_takeover(war, consul, None, self.state)
                self.state.log_event(
                    f"[DEBUG] _process_war_takeover: 无指挥官战争 {war.id}, 接管决策={takeover_decision}",
                    level=logging.DEBUG,
                    extra={"function": "_process_war_takeover", "war_id": war.id, "branch": "no_commander",
                           "takeover_decision": takeover_decision}
                )
                if takeover_decision:
                    war.commander_id = consul.id
                    consul.is_absent = True
                    print(f"      ✅ 执政官 {consul.name} 接管战争 {war.name}")
                    self._auto_recruit_and_assign_legions_for_war(war, consul.id)
                    self.state.log_event(f"执政官 {consul.name} 接管 {war.name}")
                else:
                    print(f"      ⏳ 执政官 {consul.name} 决定不接管 {war.name}")
            else:
                old_cmd = self.state.get_member(war.commander_id)
                if not old_cmd:
                    self.state.log_event(
                        f"[DEBUG] _process_war_takeover: 战争 {war.id} 的指挥官 {war.commander_id} 不存在，跳过",
                        level=logging.DEBUG,
                        extra={"function": "_process_war_takeover", "war_id": war.id, "reason": "old_commander_missing"}
                    )
                    continue
                if old_cmd.office in ("proconsul", "ex-consul") and old_cmd.is_absent:
                    takeover_decision = self.takeover_decider.decide_takeover(war, consul, old_cmd, self.state)
                    self.state.log_event(
                        f"[DEBUG] _process_war_takeover: 已有指挥官战争 {war.id}, 旧指挥官={old_cmd.id}, 接管决策={takeover_decision}",
                        level=logging.DEBUG,
                        extra={"function": "_process_war_takeover", "war_id": war.id, "branch": "has_commander",
                               "old_commander_id": old_cmd.id, "takeover_decision": takeover_decision}
                    )
                    if takeover_decision:
                        old_cmd.is_absent = False
                        old_cmd.office = "ex-proconsul"
                        war.commander_id = consul.id
                        consul.is_absent = True
                        print(f"      🔄 执政官 {consul.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回罗马")
                        self._auto_recruit_and_assign_legions_for_war(war, consul.id)
                        self.state.log_event(f"执政官 {consul.name} 接管战争 {war.name}，原指挥官 {old_cmd.name} 返回")
                    else:
                        print(f"      ⏳ 执政官 {consul.name} 决定不接管 {war.name}，由 {old_cmd.name} 继续指挥")
                else:
                    self.state.log_event(
                        f"[DEBUG] _process_war_takeover: 战争 {war.id} 已有指挥官 {old_cmd.id}，且不符合接管条件",
                        level=logging.DEBUG,
                        extra={"function": "_process_war_takeover", "war_id": war.id,
                               "branch": "has_commander_no_action"}
                    )
        self.state.log_event(
            "[DEBUG] _process_war_takeover 结束",
            level=logging.DEBUG,
            extra={"function": "_process_war_takeover", "phase": "exit"}
        )

    def _auto_recruit_and_assign_legions_for_war(self, war, consul_id):
        """自动征召军团并指派给战争（用于宣战和接管）"""
        ms = self.state.get_military_system()
        if not ms:
            print("      ⚠️ 军事系统不可用，无法征召军团")
            return

        # 检查战争是否已有军团，如果有则直接使用现有军团，不再征召
        existing_legions = ms.get_legions_for_battle(war.id) if ms else []
        if existing_legions:
            print(f"      ℹ️ 战争已有 {len(existing_legions)} 个军团，无需征召")
            return

        # 获取应征召的军团数量
        legions = getattr(war, 'proposed_legions', 0)
        if legions <= 0:
            min_leg = self.state.config.get("testing.min_legions", 4)
            max_leg = self.state.config.get("testing.max_legions", 8)
            legions = random.randint(min_leg, max_leg)
            print(f"      ℹ️ 战争未指定军团数，自动分配 {legions} 个")

        available = ms.get_available_legions()
        recruit_cost = self.state.get_economic_rule("legion_recruit_cost", 10)

        # 移除国库资金限制，允许负债征召
        recruit_count = min(legions, len(available))  # 只受可用军团数和需求数限制
        if recruit_count == 0:
            print("      ⚠️ 没有可用军团，无法征召")
            return

        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [r[0] for r in results if r[1]]
        if not recruited_numbers:
            print("      ⚠️ 军团征召失败")
            return

        assigned, msg = ms.assign_to_war(recruited_numbers, war.id, consul_id)
        print(f"      {msg}")
        for num in recruited_numbers:
            war.add_legion_number(num)

        self.state.log_event(f"宣战 {war.name}，征召 {len(recruited_numbers)} 军团")

    def _process_war_proposals(self, passed_wars: List[Tuple["War", int, int]]):
        """处理宣战提案，通过的放入 passed_wars"""
        ws = self.state.get_war_system()
        if not ws:
            return

        threats = [w for w in ws._threats if w.status == WarStatus.THREAT]
        if not threats:
            print(f"\n   ⚔️ 没有战争威胁需要处理。")
            return

        consul_id = self.state.turn.leader_ids[0] if self.state.turn.leader_ids else None
        if not consul_id:
            print(f"\n   ⚠️ 没有执政官，无法处理宣战提案。")
            return
        consul = self.state.get_member(consul_id)
        if not consul:
            return

        print(f"\n   ⚔️ 战争威胁处理（执政官：{consul.name}）：")

        propose_chance = self.state.config.get("testing.propose_war_chance", 0.7)
        always_declare = self.state.config.get("testing.always_declare", False)
        min_legions = self.state.config.get("testing.min_legions", 4)
        max_legions = self.state.config.get("testing.max_legions", 8)

        # 获取海军系统（用于检查舰队）
        naval_system = self.state.naval_system

        for war in threats:
            # 如果战争需要海战，检查是否有可用舰队
            if war.naval_required:
                if not naval_system or not naval_system.get_available_fleets():
                    print(f"\n      📋 战争威胁：{war.name}（需要海战）")
                    print(f"         当前无可用舰队，无法宣战。")
                    continue

            print(f"\n      📋 战争威胁：{war.name}")
            print(f"         威胁等级：{war.threat_level}")

            if always_declare or random.random() < propose_chance:
                legions = random.randint(min_legions, max_legions)
                print(f"         执政官提议宣战，要求批准 {legions} 个军团。")
            else:
                print(f"         执政官决定暂不宣战。")
                continue

            votes_for = 0
            votes_against = 0
            total_influence = 0

            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence

                if faction.id == consul.faction_id:
                    support = True
                else:
                    support = self.vote_decider.decide_vote(war, faction, self.state)

                if support:
                    votes_for += influence
                    print(f"          {faction.name} 支持，影响力 {influence}")
                else:
                    votes_against += influence
                    print(f"          {faction.name} 反对，影响力 {influence}")

            if total_influence == 0:
                print(f"          无元老在场，宣战失败。")
                continue

            support_ratio = votes_for / total_influence
            print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                # 不立即激活，放入 passed_wars
                passed_wars.append((war, consul_id, legions))
                self.state.log_event(
                    f"宣战通过 (待否决): {war.name}，批准军团 {legions}",
                    extra={"type": "war_declaration_passed", "war_id": war.id, "legions": legions}
                )
                print(f"          ✅ 元老院批准宣战，等待保民官否决")
            else:
                print(f"          ❌ 宣战被元老院否决。")

    def _process_budget_proposals(self, terms, passed_contracts: List["Contract"]):
        """处理预算提案，通过的放入 passed_contracts"""
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if not pending:
            print(f"\n   📭 No pending contracts for budget.")
            return

        print(f"\n   📋 Budget Proposals:")
        proposals = self.budget_decider.decide_proposals(pending, self.state)
        if not proposals:
            print(f"      No contracts selected for vote.")
            return

        for contract in proposals:
            print(f"\n      📊 {contract.name}")

            votes_for = 0
            votes_against = 0
            total_influence = 0

            for faction in self.state.get_active_factions():
                influence = faction.get_senate_influence(self.state)
                if influence == 0:
                    continue
                total_influence += influence

                support = self.vote_decider.decide_vote(contract, faction, self.state)
                if support:
                    votes_for += influence
                    print(f"          {faction.name} 支持，影响力 {influence}")
                else:
                    votes_against += influence
                    print(f"          {faction.name} 反对，影响力 {influence}")

            if total_influence == 0:
                print(f"          无元老在场，合同无法表决。")
                continue

            support_ratio = votes_for / total_influence
            print(f"          总影响力：{total_influence}，支持 {votes_for}，反对 {votes_against}，支持率 {support_ratio:.1%}")

            if support_ratio > 0.5:
                passed_contracts.append(contract)
                print(f"          ✅ 预算通过，等待保民官否决")
            else:
                print(f"          ❌ 预算否决，保持 PENDING")

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
        else:
            winner, winner_faction = random.choice(candidates)

        # 授予合同
        if contract.award(winner.id, winner_faction.id, self.state.turn.turn_number):
            print(f"\n      ✅ Assigned to {winner.name} ({winner_faction.name})")
            print(f"         Duration: {contract.duration_years} years")