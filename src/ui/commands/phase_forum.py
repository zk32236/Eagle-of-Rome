# src/ui/commands/phase_forum.py
"""
广场阶段命令 - 完整功能版，严格遵循 UI 设计师流程
支持三种运行模式：
- 全自动模式 (auto_forum=True): 所有派系自动决策，但显示完整UI，无需玩家输入
- 正常模式 (auto_forum=False, bypass_player_check=False): 人类玩家手动，AI玩家自动
- 全人工测试模式 (auto_forum=False, bypass_player_check=True): 所有玩家手动，权限检查绕过
"""
import sys
import traceback
import random
import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.api import forum_api, figure_api, player_api
from src.core.i18n import i18n
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.localization import TerminologyService
from src.core.systems.war_system import War, WarStatus
from src.core.entities.player import PlayerType

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ForumCommand(Command):
    """广场阶段命令 - 支持多步骤玩家交互，包含完整功能"""

    name = "forum"
    aliases = ["f"]
    description = "执行广场阶段 (Forum Phase) - 包含裁员、招募、竞标、土地交易"

    def __init__(self, state: "GameState",
                 retirement_decider=None,
                 recruitment_decider=None,
                 bid_decider=None,
                 land_trade_decider=None,
                 triumph_decider=None):
        super().__init__(state)
        self._step = 0  # 0: 公告, 1: 裁员, 2: 市场, 3: 公示, 4: 交易市场, 5: 完成
        self._current_player_index = 0
        self._players = []
        self.terms = TerminologyService.get()
        self._resolution_done = False  # 控制公示只执行一次
        self._auto_mode = False        # 是否处于自动模式（由配置决定，用于UI显示）

        # 根据配置创建决策器实例
        auto_forum = state.config.get("testing.auto_forum", False)

        if retirement_decider is not None:
            self.retirement_decider = retirement_decider
        else:
            from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
            self.retirement_decider = AutoRetirementDecider(state)

        if recruitment_decider is not None:
            self.recruitment_decider = recruitment_decider
        else:
            from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
            self.recruitment_decider = AutoRecruitmentDecider()

        if bid_decider is not None:
            self.bid_decider = bid_decider
        else:
            from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
            self.bid_decider = AutoBidDecider()

        if land_trade_decider is not None:
            self.land_trade_decider = land_trade_decider
        else:
            from src.core.deciders.impl.auto_land_trade_decider import AutoLandTradeDecider
            self.land_trade_decider = AutoLandTradeDecider()

        if triumph_decider is not None:
            self.triumph_decider = triumph_decider
        else:
            from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
            self.triumph_decider = AutoTriumphDecider()

    # ==================== 辅助函数 ====================

    def _get_quaestor_players(self) -> List[str]:
        """返回所有担任财务官的人物所属的玩家ID列表（去重）"""
        players = set()
        for member in self.state.get_living_members():
            if member.office == "quaestor" and member.faction_id:
                player = self.state.get_player_by_faction(member.faction_id)
                if player:
                    players.add(player.player_id)
        return list(players)

    def _has_quaestor(self) -> bool:
        """检查是否有存活人物担任财务官 (quaestor)"""
        for member in self.state.get_living_members():
            if member.office == "quaestor":
                return True
        return False

    def _get_war_triumph(self) -> Optional[Dict]:
        """获取待凯旋的战争信息（用于投票）"""
        war_system = self.state.get_war_system()
        if not war_system:
            return None
        for war in war_system._war_discard:
            if war.status == WarStatus.RESOLVED and war.soldier_share > 0 and war.triumph_commander_id is None:
                commander = self.state.get_member(war.commander_id)
                if commander and not commander.is_dead:
                    return {
                        "war": war,
                        "commander": commander
                    }
        return None

    def _get_available_contracts(self) -> List[Contract]:
        """获取可竞标的合同（BUDGETED 状态）"""
        return [c for c in self.state.contracts if c.status == ContractStatus.BUDGETED]

    def _get_available_land_for_sale(self) -> int:
        """获取可用于出售的国家公地数量（根据待执行的土地法案）"""
        acts = self.state.get_pending_land_acts()
        total = 0
        for act in acts:
            if act['type'] == 'sale':
                total += act['amount']
        return total

    # ==================== 原有功能函数移植 ====================

    def _generate_new_figures(self):
        """生成新人物并加入 curia"""
        rules = self.state.config.get("forum_rules", {})
        count = rules.get("new_figures_count", 3)
        class_probs = rules.get("class_probabilities", {
            "nobile": 0.5,
            "eques": 0.3,
            "plebeian": 0.2
        })

        new_figures = []
        for _ in range(count):
            tier = random.choices(
                list(class_probs.keys()),
                weights=list(class_probs.values())
            )[0]
            figure_id = self.state.allocate_id()
            if tier == "nobile":
                fig = Figure.create_nobile(figure_id, None, age=random.randint(30, 50))
            elif tier == "eques":
                fig = Figure.create_eques(figure_id, None, age=random.randint(25, 45))
            else:
                fig = Figure.create_plebeian(figure_id, None, age=random.randint(20, 40))
            self.state.add_member(fig)
            self.state.curia.add_figure(fig)
            new_figures.append(fig)
        if new_figures:
            print(f"\n   📢 {len(new_figures)} new figure(s) arrive in the Rome:")
            sys.stdout.flush()

    def _generate_contracts(self):
        """生成新合同（包税、工程、舰队建造），仅对已征服行省生效，意大利本土只生成工程合同"""
        contracts = []  # 用于记录新生成的合同（可选）
        config = self.state.config
        land_price = config.get("economic_rules.land_price_per_unit", 10)
        private_income_rate = config.get("economic_rules.private_land_income_rate", 0.05)
        province_tax_rate = config.get("economic_rules.province_tax_rate", 0.1)
        auction_ratio = config.get("economic_rules.tax_auction_ratio", 0.8)
        infra_rate = config.get("economic_rules.infrastructure_cost_rate", 0.001)
        budget_margin = config.get("economic_rules.project_budget_margin", 0.2)
        tax_duration = config.get("economic_rules.tax_contract_duration", 5)
        works_duration = config.get("economic_rules.works_contract_duration", 3)

        # ---------- 1. 续约合同（仅针对已征服行省）----------
        for contract in self.state.contracts:
            # 包税合同续约（剩余1年时生成新合同）
            if contract.contract_type == ContractType.TAX_FARMING and contract.status == ContractStatus.ACTIVE:
                if contract.remaining_years == 1:
                    province = self.state.get_province(contract.province_id)
                    if not province or not province.conquered:
                        continue
                    existing = any(c for c in self.state.contracts
                                   if c.province_id == contract.province_id
                                   and c.contract_type == ContractType.TAX_FARMING
                                   and c.status == ContractStatus.PENDING)
                    if not existing and province.land_public > 0:
                        land_value = province.land_public * land_price
                        base_income = int(land_value * private_income_rate)
                        base_tax = int(base_income * province_tax_rate)
                        base_cost = int(base_tax * auction_ratio)

                        new_contract = self.state.create_contract(
                            ContractType.TAX_FARMING,
                            province.province_id,
                            base_cost,
                            self.state.turn.turn_number
                        )
                        year = self.state.turn.year
                        year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                        new_contract.name = f"{province.name}包税权 ({year_display})"
                        new_contract.expected_profit = base_tax - base_cost
                        new_contract.duration_years = tax_duration
                        contracts.append(new_contract)

            # 工程合同续约（质保期剩余1年时生成新合同）
            elif contract.contract_type == ContractType.PUBLIC_WORKS and contract.status == ContractStatus.COMPLETED:
                if contract.warranty_remaining == 1:
                    province = self.state.get_province(contract.province_id)
                    if not province or not province.conquered:
                        continue
                    existing = any(c for c in self.state.contracts
                                   if c.province_id == contract.province_id
                                   and c.contract_type == ContractType.PUBLIC_WORKS
                                   and c.status == ContractStatus.PENDING)
                    if not existing and province.land_public > 0:
                        land_value = province.land_public * land_price
                        infra_cost = int(land_value * infra_rate)
                        budget = int(infra_cost * (1 + budget_margin))

                        year = self.state.turn.year
                        year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                        new_contract = self.state.create_contract(
                            ContractType.PUBLIC_WORKS,
                            province.province_id,
                            budget,
                            self.state.turn.turn_number
                        )
                        new_contract.name = f"{province.name}工程 ({year_display})"
                        new_contract._original_budget = budget
                        new_contract.duration_years = works_duration
                        contracts.append(new_contract)

        # ---------- 2. 全新合同 ----------
        for province in self.state.get_all_provinces():
            # 包税合同：仅已征服的非意大利行省
            if province.province_id != 0 and province.conquered and province.land_public > 0:
                has_tax_active = any(c for c in self.state.contracts
                                     if c.province_id == province.province_id
                                     and c.contract_type == ContractType.TAX_FARMING
                                     and c.status in (
                                     ContractStatus.ACTIVE, ContractStatus.PENDING, ContractStatus.BUDGETED))
                if not has_tax_active:
                    land_value = province.land_public * land_price
                    base_income = int(land_value * private_income_rate)
                    base_tax = int(base_income * province_tax_rate)
                    base_cost = int(base_tax * auction_ratio)

                    contract = self.state.create_contract(
                        ContractType.TAX_FARMING,
                        province.province_id,
                        base_cost,
                        self.state.turn.turn_number
                    )
                    year = self.state.turn.year
                    year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                    contract.name = f"{province.name}包税权 ({year_display})"
                    contract.expected_profit = base_tax - base_cost
                    contract.duration_years = tax_duration
                    contracts.append(contract)

            # 工程合同：已征服的行省 或 意大利本土
            if (province.conquered or province.province_id == 0) and province.land_public > 0:
                has_works = any(c for c in self.state.contracts
                                if c.province_id == province.province_id
                                and c.contract_type == ContractType.PUBLIC_WORKS
                                and c.status not in (ContractStatus.EXPIRED, ContractStatus.COMPLETED))
                if not has_works:
                    land_value = province.land_public * land_price
                    infra_cost = int(land_value * infra_rate)
                    budget = int(infra_cost * (1 + budget_margin))

                    year = self.state.turn.year
                    year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                    contract = self.state.create_contract(
                        ContractType.PUBLIC_WORKS,
                        province.province_id,
                        budget,
                        self.state.turn.turn_number
                    )
                    contract.name = f"{province.name}工程 ({year_display})"
                    contract._original_budget = budget
                    contract.duration_years = works_duration
                    contracts.append(contract)

        # ---------- 3. 舰队建造合同（通过 naval_system）----------
        if self.state.naval_system:
            construction_contracts = self.state.naval_system.generate_construction_contracts(
                self.state.turn.turn_number)
            if construction_contracts:
                print(f"\n   ⚓ 检测到海战威胁，生成 {len(construction_contracts)} 个舰队建造合同")
                sys.stdout.flush()
            replacement_contracts = self.state.naval_system.generate_replacement_contracts(
                self.state.turn.turn_number)
            if replacement_contracts:
                print(f"\n   ⚓ 罗马舰队不足，生成 {len(replacement_contracts)} 个补充舰队建造合同")
                sys.stdout.flush()

        return contracts

    def _generate_fleet_construction_contract(self, war: War):
        """为指定战争生成舰队建造合同"""
        contract = self.state.create_contract(
            ContractType.PUBLIC_WORKS,
            0,  # 意大利
            80,  # 预算，实际应从配置读取
            self.state.turn.turn_number
        )
        contract._is_fleet_construction = True
        contract.name = f"舰队建造（{war.name}）"
        contract._target_war_id = war.id
        composition = [{"type": "trireme", "count": 2}]
        contract.set_fleet_composition(composition, war.enemy_naval_current, 80)

    # ==================== 新增：战争威胁、民变、凯旋等状态更新方法 ====================

    def _update_war_threats(self):
        """更新战争威胁：触发和升级"""
        ws = self.state.get_war_system()
        if ws:
            ws.check_triggers(self.state.turn.year)
            events = ws.escalate_threats()
            for event in events:
                print(f"   {event}")

    def _update_civil_unrest(self):
        """更新行省民怨（自动升级、合同税率触发、起义检测）"""
        if not self.state.config.get("enable_threats", True):
            return
        base_tax_rate = self.state.get_economic_rule("province_tax_rate", 0.1)
        italy_unrest_trigger = self.state.config.get("economic_rules.italy_unrest_trigger_turns", 3)
        provinces = self.state.get_all_provinces()
        if not provinces:
            return

        active_contracts = [c for c in self.state.contracts
                            if c.status == ContractStatus.ACTIVE and c.contract_type == ContractType.TAX_FARMING]
        province_contracts = {}
        for contract in active_contracts:
            pid = contract.province_id
            if pid == 0:
                continue
            province_contracts.setdefault(pid, []).append(contract)

        any_change = False
        print("\n   📊 行省民变状态：")

        # 意大利本土
        italy = self.state.get_province(0)
        if italy:
            old_grievance = italy.grievance
            if old_grievance == 0:
                italy._turns_since_last_land_distribution += 1
                if italy._turns_since_last_land_distribution >= italy_unrest_trigger:
                    italy.set_grievance(1)
                    print(f"      ⚠️ 意大利本土因长期未分地，民怨升至 1 级")
                    any_change = True
            elif 0 < old_grievance < 3:
                italy.set_grievance(old_grievance + 1)
                print(f"      ⚠️ 意大利本土 民怨升级至 {italy.grievance} 级")
                if italy.grievance == 3:
                    print(f"         意大利本土爆发平民起义！政府面临倒台，马上行动！")
                any_change = True

        # 行省
        for province in provinces:
            if province.province_id == 0:
                continue

            # 起义检测（民怨达到3且未起义）
            if province.grievance >= 3 and not province.event_flags.get("rebellion_active"):
                war_system = self.state.get_war_system()
                if war_system:
                    rebellion_war = war_system.create_rebellion_war(province)
                    war_system._active_wars.append(rebellion_war)
                    province.set_event_flag("rebellion_active", True)
                    print(f"      ⚔️ 行省 {province.name} 爆发起义！战争 {rebellion_war.name} 已激活。")
                    self.state.log_event(
                        f"行省起义：{province.name}",
                        extra={"type": "rebellion", "province_id": province.province_id}
                    )
                    any_change = True

            # 自动升级（1->2, 2->3）
            if 0 < province.grievance < 3:
                province.set_grievance(province.grievance + 1)
                print(f"      ⚠️ 行省 {province.name} 民怨升级至 {province.grievance} 级")
                if province.grievance == 3:
                    print(f"         行省 {province.name} 爆发平民起义！")
                any_change = True

            # 合同税率触发
            contracts = province_contracts.get(province.province_id, [])
            if contracts:
                for contract in contracts:
                    tax_rate = getattr(contract, 'tax_rate', 0.0)
                    if tax_rate > base_tax_rate:
                        if province.grievance < 1:
                            province.set_grievance(1)
                            print(f"      🔔 行省 {province.name} 因包税合同税率 {tax_rate * 100:.0f}% > {base_tax_rate * 100:.0f}%，民怨升至 1 级")
                            any_change = True
                        else:
                            print(f"      📌 行省 {province.name} 包税合同税率 {tax_rate * 100:.0f}%，当前民怨 {province.grievance} 级")
                    else:
                        print(f"      ✅ 行省 {province.name} 包税合同税率 {tax_rate * 100:.0f}% 在允许范围内，民怨 {province.grievance} 级")
            else:
                if province.grievance > 0:
                    print(f"      ℹ️ 行省 {province.name} 当前民怨 {province.grievance} 级")
                    any_change = True

        if not any_change:
            print(f"      所有行省安居乐业，无民变威胁。")

    def _process_triumphs(self):
        """处理待凯旋战争，根据决策器批准凯旋并添加临时影响力"""
        ws = self.state.get_war_system()
        if not ws:
            return

        for war in ws._war_discard:
            if war.soldier_share > 0 and war.status == WarStatus.RESOLVED:
                commander_id = war.triumph_commander_id or war.commander_id
                commander = self.state.get_member(commander_id) if commander_id else None
                if not commander or commander.is_dead:
                    war.set_soldier_share(0)
                    continue

                if self.triumph_decider.decide_triumph(war, commander, self.state):
                    duration = self.state.config.get("combat_rules.triumph_veteran_duration", 5)
                    per_turn = war.soldier_share // duration
                    if per_turn > 0:
                        commander.add_temp_influence_task(per_turn, duration)
                        war.set_triumph_approved(True)
                        print(f"   🏆 元老院决定授予 {commander.get_formal_name()} 凯旋！未来几年他将获得士兵的拥戴！")
                        self.state.log_event(
                            f"凯旋批准：{commander.name} 获得 {war.soldier_share} 士兵份额，分 {duration} 回合",
                            extra={"commander_id": commander.id, "amount": war.soldier_share, "duration": duration}
                        )
                else:
                    print(f"   ⏳ {commander.get_formal_name()} 的凯旋被元老院否决")
                war.set_soldier_share(0)

    def _display_truce_treaties(self):
        """显示待评议的停战草案"""
        ws = self.state.get_war_system()
        if ws:
            pending_treaties = ws.get_truce_wars_with_pending_treaty()
            if pending_treaties:
                print(f"   📜 停战草案待评议：")
                for war in pending_treaties:
                    treaty = war.peace_treaty
                    indemnity = treaty['indemnity'] if treaty else 0
                    print(f"\t\t{war.name} 赔款 {indemnity} 塔兰特")

    def _display_active_wars(self):
        """显示当前活跃战争"""
        ws = self.state.get_war_system()
        if ws:
            active_wars = ws.get_active_wars()
            if active_wars:
                print(f"   ⚔️ 活跃战争：{len(active_wars)}场")
                for war in active_wars:
                    print(f"\t\t{war.name}")
            else:
                print("   ⚔️ 当前无活跃战争")

    # ==================== 步骤展示函数 ====================

    def _print_ui_03_0(self):
        """打印 UI_03-0 公告环节（集成所有状态更新）"""
        print("\n############################################################")
        print(f" UI_03-0 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]")
        print("\n############################################################")
        print("--- 阶段预览---")
        print("广场阶段为玩家交互核心环节，包含人才招募、合同拍卖、土地交易三大核心玩法。")
        print("你可出价招募人物、竞标工程/舰队合同、手动促成土地交易，结果直接影响派系")
        print("实力、个人财富及后续元老院的议程和利益分配，请务必谨慎使用你的资源争取最")
        print("大的利益！")
        # 安民告示
        print("\n\t====================== 安民告示 ====================")

        # 战争威胁升级
        self._update_war_threats()

        # 显示活跃战争
        self._display_active_wars()

        # 显示停战草案
        self._display_truce_treaties()

        # 行省民变更新
        self._update_civil_unrest()

        # 凯旋审批
        self._process_triumphs()

        # 注意：舰队建造合同已在 _generate_contracts 中生成并打印提示，此处不再重复调用

        print("\n🔧 本阶段可操作(ANY)：")
        print("   1. next/n → 进入裁员环节")
        sys.stdout.flush()

    def _print_ui_03_1(self, player_id: str, faction_id: str):
        """打印 UI_03-1 裁员环节"""
        player = self.state.get_player(player_id)
        faction = self.state.get_faction(faction_id)
        faction_name = faction.name if faction else "未知"
        print("\n############################################################")
        print(f" UI_03-1 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]")
        print("\n############################################################")
        print("\n--- 步骤说明 ---")
        print("新鲜血液是保持组织活力的重要源泉，裁汰掉对组织没有贡献的成员，才能腾出空")
        print("间招募更优秀的人才。请从你的成员列表中挑选需要淘汰的成员，让他们去广场上")
        print("自谋生路吧。")

        # 显示派系成员列表
        result = figure_api.get_figure_info(self.state)
        if result["success"]:
            members = [f for f in result["data"] if f["faction_id"] == faction_id]
            if members:
                print("\n================================================================================")
                print(f"   👥 {faction_name} 存活派系人物列表")
                print("================================================================================")
                for m in members:
                    status = "👑" if m["is_faction_leader"] else "🟢"
                    tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(m["class_tier"], "❓")
                    print(f"{status}{tier_emoji} ID:{m['id']:<3} {m['name']:<25} 派系:{m['faction_id']:<12} 影响力:{m['influence']} 财富:{m['wealth']} 人气:{m['popularity']} 私地:{m['land_private']} 老兵:{m['veterans']} 官职:{m['office']}")

        print(f"\n🔧 本阶段可操作 (PLAYER {player_id} {faction_name})：")
        print("   1. investigate → 查询人物详情；")
        print("   2. retire → 驱逐不需要的派系成员；")
        print("   3. next/n → 下一个玩家；")
        sys.stdout.flush()

    def _print_ui_03_2(self, player_id: str, faction_id: str):
        """打印 UI_03-2 市场环节"""
        player = self.state.get_player(player_id)
        faction = self.state.get_faction(faction_id)
        faction_name = faction.name if faction else "未知"
        print("\n############################################################")
        print(f" UI_03-2 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]")
        print("\n############################################################")
        print("\n--- 步骤说明 ---")
        print("罗马广场藏龙卧虎，物欲横流。是你利用金钱的力量扩张你的实力，招揽人才，竞标")
        print("合同，兼并土地，结交权贵的最佳场所。当然，这一切都是在罗马法律的统治下公平")
        print("竞争的结果。现在请你下注吧！")

        # 人才市场
        print("\n====================== 人才市场 ====================")
        curia = self.state.curia.get_all_available()
        if curia:
            for fig in curia:
                tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(fig.class_tier.value, "❓")
                print(f"      {tier_emoji} ID:{fig.id} {fig.get_formal_name()} ({fig.class_tier.value})(军略 {fig.martial}, 智略 {fig.intelligence}, 魅力 {fig.charisma}, 热诚 {fig.zeal})")
        else:
            print("   📭 广场无人物")

        # 可竞标合同
        print("\n====================== 交易市场 ====================")
        contracts = self._get_available_contracts()
        if contracts:
            for c in contracts:
                type_emoji = "📊" if c.contract_type == ContractType.TAX_FARMING else "🏗️"
                print(f"      🔔 标的 {c.id} {type_emoji} {c.name} 预算 {c.base_cost}")
        else:
            print("   📭 没有待竞标的预算合同")

        # 待决合同（仅显示）
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if pending:
            print("\n   📋 Pending Contracts (等待元老院预算表决):")
            for c in pending:
                type_emoji = "📊" if c.contract_type == ContractType.TAX_FARMING else "🏗️"
                if c.contract_type == ContractType.TAX_FARMING:
                    print(f"      {type_emoji} ID:{c.id} {c.name}	预付:{c.base_cost} 预期利润:{c.expected_profit}")
                else:
                    print(f"      {type_emoji} ID:{c.id} {c.name}	预算:{c.base_cost}")

        # 土地法案
        acts = self.state.get_pending_land_acts()
        if acts:
            print("\n   🏞️ 执行土地法案：")
            for act in acts:
                if act['type'] == 'distribution':
                    print(f"      ✅ 平民分地 {act['amount']} C 土地（占国家公地 {act['percent']*100:.1f}%），转入意大利私地，民怨重置。")
                elif act['type'] == 'sale':
                    print(f"      🏛️ 贵族买地：出售 {act['amount']} C 国家公地。")

        # 凯旋信息
        triumph = self._get_war_triumph()
        if triumph:
            commander = triumph["commander"]
            print(f"\n   🏆 {commander.get_formal_name()} 的凯旋等待投票")

        print(f"\n🔧 本阶段可操作(PLAYER {player_id} {faction_name})：")
        print("   1. investigate → 查看人才详情")
        print("   2. recruit <人物ID> <金额> → 招募新人")
        print("   3. bid <合同ID> <金额> → 竞标合同")
        print("   4. buy <数量> → 认购公地")
        print("   5. vote yes/no → 投票授予凯旋")
        print("   6. balance → 查询派系金库；")
        print("   7. next → 下一个玩家；")
        sys.stdout.flush()

    def _print_ui_03_4(self, player_id: Optional[str], faction_id: Optional[str]):
        """打印 UI_03-4 交易市场环节（财务官）"""
        faction_name = "未知"
        if player_id and faction_id:
            faction = self.state.get_faction(faction_id)
            faction_name = faction.name if faction else "未知"

        print("\n############################################################")
        print(f" UI_03-4 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]")
        print("\n############################################################")
        print("\n--- 步骤说明 ---")
        print("贵族有土地，骑士有金钱，土地是地位的象征，而金钱是权力的保证，没有比土地")
        print("交易更适合罗马城里权钱交易的游戏了。所有的土地交易都必须通过政府注册，因此")
        print("这将成为有据可查的反腐利器！")

        if not self._has_quaestor():
            print("\n⚠️ 罗马城里没有财务官，无法进行土地交易。")
            print("\n🔧 本阶段可操作(ANY)：")
            print("   1. next/n → 下一阶段；")
        else:
            print(f"\n🔧 本阶段可操作(QUAESTOR {player_id} {faction_name})：")
            print("   1. transact <卖家ID> <买家ID> <土地数量> <价格> → 交易土地")
            print("   2. next → 下一阶段；")
        sys.stdout.flush()

    def _print_ui_03_3(self):
        """打印 UI_03-3 公示环节"""
        print("\n############################################################")
        print(f" UI_03-3 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]")
        print("\n############################################################")
        print("\n喧嚣散去，尘埃落下。")
        sys.stdout.flush()

    # ==================== 命令处理函数 ====================

    def _handle_retire(self, args: List[str]) -> bool:
        if len(args) != 1:
            print(i18n.get("error_usage_retire"), file=sys.stderr)
            sys.stderr.flush()
            return False
        try:
            fig_id = int(args[0])
        except ValueError:
            print(i18n.get("error_invalid_id"), file=sys.stderr)
            sys.stderr.flush()
            return False
        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), file=sys.stderr)
            sys.stderr.flush()
            return False
        result = forum_api.retire_figure(self.state, player_id, fig_id)
        print(result["message"])
        sys.stdout.flush()
        sys.stderr.flush()
        return result["success"]

    def _handle_recruit(self, args: List[str]) -> bool:
        if len(args) != 2:
            print(i18n.get("error_usage_recruit"), file=sys.stderr)
            sys.stderr.flush()
            return False
        try:
            fig_id = int(args[0])
            amount = int(args[1])
        except ValueError:
            print(i18n.get("error_invalid_id"), file=sys.stderr)
            sys.stderr.flush()
            return False

        fig = next((f for f in self.state.curia.get_all_available() if f.id == fig_id), None)
        if not fig:
            print(i18n.get("error_figure_not_in_curia"), file=sys.stderr)
            sys.stderr.flush()
            return False

        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), file=sys.stderr)
            sys.stderr.flush()
            return False

        player = self.state.get_player(player_id)
        if not player:
            return False

        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return False

        num_factions = len(self.state.factions)
        if num_factions == 3:
            max_members = 6
        elif num_factions == 4:
            max_members = 5
        elif num_factions == 6:
            max_members = 4
        else:
            max_members = 5

        current_members = len(faction.get_members(self.state))
        vacancies = max_members - current_members
        if vacancies <= 0:
            print(i18n.get("error_no_vacancies", faction=faction.name), file=sys.stderr)
            sys.stderr.flush()
            return False

        result = forum_api.recruit_figure(self.state, player_id, fig_id, amount)
        print(result["message"])
        sys.stdout.flush()
        sys.stderr.flush()
        return result["success"]

    def _handle_bid(self, args: List[str]) -> bool:
        if len(args) != 2:
            print(i18n.get("error_usage_bid"), file=sys.stderr)
            sys.stderr.flush()
            return False
        try:
            contract_id = int(args[0])
            amount = int(args[1])
        except ValueError:
            print(i18n.get("error_invalid_id"), file=sys.stderr)
            sys.stderr.flush()
            return False
        contract = self.state.get_contract(contract_id)
        if not contract:
            print(i18n.get("contract_not_found", id=contract_id), file=sys.stderr)
            sys.stderr.flush()
            return False
        if contract.status != ContractStatus.BUDGETED:
            print(i18n.get("error_contract_not_auctionable"), file=sys.stderr)
            sys.stderr.flush()
            return False
        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), file=sys.stderr)
            sys.stderr.flush()
            return False
        result = forum_api.place_bid(self.state, player_id, contract_id, amount)
        print(result["message"])
        sys.stdout.flush()
        sys.stderr.flush()
        return result["success"]

    def _handle_buy(self, args: List[str]) -> bool:
        if len(args) != 1:
            print(i18n.get("error_usage_buy"), file=sys.stderr)
            sys.stderr.flush()
            return False
        try:
            amount = int(args[0])
        except ValueError:
            print(i18n.get("error_invalid_amount"), file=sys.stderr)
            sys.stderr.flush()
            return False
        if self._get_available_land_for_sale() == 0:
            print("   📭 没有公地可购买", file=sys.stderr)
            sys.stderr.flush()
            return False
        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), file=sys.stderr)
            sys.stderr.flush()
            return False
        result = forum_api.buy_land(self.state, player_id, amount)
        print(result["message"])
        sys.stdout.flush()
        sys.stderr.flush()
        return result["success"]

    def _handle_vote(self, args: List[str]) -> bool:
        if len(args) != 1:
            print(i18n.get("error_usage_vote"), file=sys.stderr)
            sys.stderr.flush()
            return False
        vote_str = args[0].lower()
        if vote_str not in ("yes", "no"):
            print(i18n.get("error_invalid_vote"), file=sys.stderr)
            sys.stderr.flush()
            return False
        if not self._get_war_triumph():
            print("   📭 没有凯旋仪式需要授予", file=sys.stderr)
            sys.stderr.flush()
            return False
        vote = (vote_str == "yes")
        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), file=sys.stderr)
            sys.stderr.flush()
            return False
        result = forum_api.vote_triumph(self.state, player_id, vote)
        print(result["message"])
        sys.stdout.flush()
        sys.stderr.flush()
        return result["success"]

    def _handle_transact(self, args: List[str]) -> bool:
        if len(args) != 4:
            print(i18n.get("error_usage_transact"), file=sys.stderr)
            sys.stderr.flush()
            return False
        try:
            seller = int(args[0])
            buyer = int(args[1])
            land = int(args[2])
            price = int(args[3])
        except ValueError:
            print(i18n.get("error_invalid_number"), file=sys.stderr)
            sys.stderr.flush()
            return False
        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), file=sys.stderr)
            sys.stderr.flush()
            return False
        result = forum_api.transact_land(self.state, player_id, seller, buyer, land, price)
        print(result["message"])
        sys.stdout.flush()
        sys.stderr.flush()
        return result["success"]

    def _handle_investigate(self, args: List[str]) -> bool:
        if len(args) == 0:
            player_id = self._get_current_player_id()
            if not player_id:
                print(i18n.get("error_no_current_player"), file=sys.stderr)
                sys.stderr.flush()
                return False
            player = self.state.get_player(player_id)
            if not player:
                return False
            faction = self.state.get_faction(player.faction_id)
            if not faction:
                return False

            result = figure_api.get_figure_info(self.state)
            if not result["success"]:
                print(result["message"], file=sys.stderr)
                sys.stderr.flush()
                return False
            all_figures = result["data"]

            faction_members = [fig for fig in all_figures if
                               fig["faction_id"] == faction.id and not fig.get("is_dead", False)]

            if faction_members:
                print("\n================================================================================")
                print(f"   👥 {faction.name} 存活派系人物列表")
                print("================================================================================")
                for m in faction_members:
                    status = "👑" if m.get("is_faction_leader", False) else "🟢"
                    tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(m["class_tier"], "❓")
                    office_display = m["office"] if m.get("office") and not m["office"].startswith("ex-") else "无"
                    print(
                        f"{status}{tier_emoji} ID:{m['id']:<3} {m['name']:<25} 派系:{m['faction_id']:<12} 影响力:{m['influence']} 财富:{m['wealth']} 人气:{m['popularity']} 私地:{m['land_private']} 老兵:{m['veterans']} 官职:{office_display}")
                sys.stdout.flush()
            else:
                print(i18n.get("no_members_in_faction", faction=faction.name), file=sys.stderr)

            if self._step == 2:
                curia_figures = self.state.curia.get_all_available()
                if curia_figures:
                    print("\n================================================================================")
                    print("   📢 广场可招募人物列表")
                    print("================================================================================")
                    for fig in curia_figures:
                        tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(fig.class_tier.value, "❓")
                        print(
                            f"   {tier_emoji} ID:{fig.id} {fig.get_formal_name()} ({fig.class_tier.value})(军略 {fig.martial}, 智略 {fig.intelligence}, 魅力 {fig.charisma}, 热诚 {fig.zeal})")
                    sys.stdout.flush()
                else:
                    print("\n   📭 广场无人物")

            sys.stderr.flush()
            return True

        elif len(args) == 1:
            try:
                fig_id = int(args[0])
            except ValueError:
                print(i18n.get("error_invalid_id"), file=sys.stderr)
                sys.stderr.flush()
                return False
            result = figure_api.get_figure_info(self.state, fig_id)
            print(result["message"])
            sys.stdout.flush()
            sys.stderr.flush()
            return result["success"]

        else:
            print(i18n.get("error_usage_investigate"), file=sys.stderr)
            sys.stderr.flush()
            return False

    def _handle_balance(self, args: List[str]) -> bool:
        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), file=sys.stderr)
            sys.stderr.flush()
            return False
        player = self.state.get_player(player_id)
        if not player:
            return False
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return False
        print(i18n.get("info_balance", faction=faction.name, treasury=faction.treasury))
        sys.stdout.flush()
        sys.stderr.flush()
        return True

    def _handle_next(self, args: List[str]) -> bool:
        if self._step == 0:
            self._step = 1
            self._players = self._get_step_players()
            self._current_player_index = 0
            print("\n--- 进入裁员环节 ---", flush=True)
        elif self._step == 3:
            self._step = 4
            self._players = self._get_step_players()
            self._current_player_index = 0
            print("\n--- 进入私地交易环节 ---", flush=True)
        elif self._step in (1, 2, 4):
            next_player_id = self._next_player()
            if next_player_id:
                player = self.state.get_player(next_player_id)
                faction = self.state.get_faction(player.faction_id) if player else None
                print(i18n.get("info_next_player", player=next_player_id, faction=faction.name if faction else "无"),
                      flush=True)
            else:
                self._step += 1
                self._players = self._get_step_players()
                self._current_player_index = 0
                if self._step == 2:
                    print("\n--- 进入市场环节 ---", flush=True)
                elif self._step == 3:
                    print("\n--- 进入公示环节 ---", flush=True)
                elif self._step == 5:
                    print("\n--- 广场阶段完成 ---", flush=True)
        return True

    def _do_resolution(self):
        """执行公示结算（先执行土地法案，再结算玩家操作）"""
        # 先执行待决土地法案
        self._execute_pending_land_acts()
        # 再结算玩家操作
        result = forum_api.resolve_forum(self.state)
        self._print_ui_03_3()
        print(result["message"])
        sys.stdout.flush()
        sys.stderr.flush()

    def _execute_pending_land_acts(self):
        """执行已通过的平民分地和贵族买地法案"""
        acts = self.state.get_pending_land_acts()
        if not acts:
            return
        print(f"\n   🏞️ 执行土地法案：")
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        for act in acts:
            if act['type'] == 'distribution':
                self._execute_land_distribution(act, land_price)
            elif act['type'] == 'sale':
                self._execute_land_sale(act, land_price)
        self.state.clear_pending_land_acts()

    def _execute_land_distribution(self, act, land_price):
        national_land = self.state.get_national_public_land()
        amount = int(national_land * act['percent'])
        if amount <= 0:
            print(f"      ⚠️ 国家公地不足，无法分配。")
            return
        self.state.add_national_public_land(-amount)
        italy = self.state.get_province(0)
        if italy:
            italy._land_private += amount
            italy._turns_since_last_land_distribution = 0
            italy.set_grievance(0)
        print(f"      ✅ 平民分地 {amount} C 土地（占国家公地 {act['percent'] * 100:.1f}%），转入意大利私地，民怨重置。")

    def _execute_land_sale(self, act, land_price):
        national_land = self.state.get_national_public_land()
        amount = int(national_land * act['percent'])
        if amount <= 0:
            print(f"      ⚠️ 国家公地不足，无法出售。")
            return
        print(f"      🏛️ 贵族买地：出售 {amount} C 国家公地。")
        nobles = [fig for fig in self.state.get_living_members() if fig.class_tier.value == "nobile"]
        nobles.sort(key=lambda f: f.influence, reverse=True)
        remaining = amount
        for fig in nobles:
            if remaining <= 0:
                break
            max_buy = fig.wealth // land_price
            if max_buy <= 0:
                continue
            buy = random.randint(1, min(remaining, max_buy))
            cost = buy * land_price
            fig.wealth -= cost
            fig._land_private += buy
            fig.update_influence()
            remaining -= buy
            print(f"         {fig.name} 购买 {buy} C，花费 {cost}，剩余土地 {remaining} C")
        sold = amount - remaining
        if sold > 0:
            self.state.add_national_public_land(-sold)
            self.state.add_treasury(sold * land_price)
            print(f"      共售出 {sold} C，国库 +{sold * land_price} Talents，国家公地剩余 {self.state.get_national_public_land()} C")
        else:
            print(f"      无土地售出。")

    # ==================== 步骤处理函数 ====================

    def _handle_step_0(self):
        self._print_ui_03_0()
        if self._auto_mode:
            # 自动模式：直接进入下一环节
            self._handle_next([])
            return
        while True:
            print("\n> 请输入操作(ANY): ", end="", flush=True)
            cmd_input = input("").strip()
            if not cmd_input:
                continue
            parts = cmd_input.split()
            cmd = parts[0].lower()
            if cmd in ("next", "n"):
                self._handle_next([])
                break
            else:
                print(i18n.get("error_unknown_command"), file=sys.stderr)
                sys.stderr.flush()

    def _handle_step_1(self):
        """处理裁员环节"""
        player_id = self._get_current_player_id()
        if not player_id:
            self._step += 1
            return
        player = self.state.get_player(player_id)
        if not player:
            self._step += 1
            return

        if self._auto_mode:
            # 自动模式：走 AI 分支，但先打印界面
            self._print_ui_03_1(player_id, player.faction_id)
            faction = self.state.get_faction(player.faction_id)
            fig_id = self.retirement_decider.decide_whom_to_retire(faction)
            if fig_id is not None:
                forum_api.retire_figure(self.state, player_id, fig_id)
            self._handle_next([])
            return

        # 正常/全人工测试模式
        bypass = self.state.config.get("testing.bypass_player_check", False)
        if bypass or player.player_type == PlayerType.HUMAN:
            self._print_ui_03_1(player_id, player.faction_id)
            while True:
                print(f"\n> 请输入操作(PLAYER {player_id}): ", end="", flush=True)
                cmd_input = input("").strip()
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                args = parts[1:]

                if cmd in ("next", "n"):
                    self._handle_next([])
                    break
                elif cmd == "investigate":
                    self._handle_investigate(args)
                elif cmd == "retire":
                    self._handle_retire(args)
                else:
                    print(i18n.get("error_unknown_command"), file=sys.stderr)
                    sys.stderr.flush()
        else:
            # AI 分支（正常模式下的AI玩家）
            self._print_ui_03_1(player_id, player.faction_id)  # AI 也打印界面
            faction = self.state.get_faction(player.faction_id)
            fig_id = self.retirement_decider.decide_whom_to_retire(faction)
            if fig_id is not None:
                forum_api.retire_figure(self.state, player_id, fig_id)
            self._handle_next([])

    def _handle_step_2(self):
        """处理市场环节"""
        player_id = self._get_current_player_id()
        if not player_id:
            self._step += 1
            return
        player = self.state.get_player(player_id)
        if not player:
            self._step += 1
            return

        if self._auto_mode:
            # 自动模式：走 AI 分支，但先打印界面
            self._print_ui_03_2(player_id, player.faction_id)
            faction = self.state.get_faction(player.faction_id)
            available_figures = self.state.curia.get_all_available()
            vacancies = faction.get_vacancies(self.state, self.state.get_economic_rule("faction_member_limit", 6))
            bids = self.recruitment_decider.decide_bids(faction, available_figures, vacancies, self.state)
            for fig_id, amount in bids.items():
                self.state.add_forum_action("recruitment_bids", (faction.id, fig_id, amount))

            budgeted_contracts = self._get_available_contracts()
            for contract in budgeted_contracts:
                knights = [m for m in faction.get_members(self.state)
                           if m.class_tier == ClassTier.EQUES and not m.is_dead]
                if not knights:
                    continue
                if contract.contract_type == ContractType.TAX_FARMING:
                    result = self.bid_decider.decide_tax_bid(contract, knights, self.state)
                    if result:
                        knight, amount, tax_rate = result
                        self.state.add_forum_action("contract_bids", (contract.id, faction.id, amount))
                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    if getattr(contract, '_is_fleet_construction', False):
                        result = self.bid_decider.decide_fleet_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r = result
                            self.state.add_forum_action("contract_bids", (contract.id, faction.id, amount))
                    else:
                        result = self.bid_decider.decide_works_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r, construction, warranty = result
                            self.state.add_forum_action("contract_bids", (contract.id, faction.id, amount))

            trade_info = self.land_trade_decider.decide_trade(self.state)
            if trade_info:
                seller_id, buyer_id, amount = trade_info
                seller = self.state.get_member(seller_id)
                buyer = self.state.get_member(buyer_id)
                if seller and buyer:
                    from src.core.service.land_trading_service import LandTradingService
                    service = LandTradingService(self.state)
                    unit_price = service.calculate_land_price(seller, buyer)
                    total_price = amount * unit_price
                    self.state.add_forum_action("land_trades", (seller_id, buyer_id, amount, total_price))

            triumph = self._get_war_triumph()
            if triumph:
                vote = self.triumph_decider.decide_triumph(triumph["war"], triumph["commander"], self.state)
                self.state.add_forum_action("triumph_votes", (faction.id, vote))

            self._handle_next([])
            return

        # 正常/全人工测试模式
        bypass = self.state.config.get("testing.bypass_player_check", False)
        if bypass or player.player_type == PlayerType.HUMAN:
            self._print_ui_03_2(player_id, player.faction_id)
            while True:
                print(f"\n> 请输入操作(PLAYER {player_id}): ", end="", flush=True)
                cmd_input = input("").strip()
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                args = parts[1:]

                if cmd in ("next", "n"):
                    self._handle_next([])
                    break
                elif cmd == "investigate":
                    self._handle_investigate(args)
                elif cmd == "recruit":
                    self._handle_recruit(args)
                elif cmd == "bid":
                    self._handle_bid(args)
                elif cmd == "buy":
                    self._handle_buy(args)
                elif cmd == "vote":
                    self._handle_vote(args)
                elif cmd == "balance":
                    self._handle_balance(args)
                else:
                    print(i18n.get("error_unknown_command"), file=sys.stderr)
                    sys.stderr.flush()
        else:
            # AI 分支
            self._print_ui_03_2(player_id, player.faction_id)
            faction = self.state.get_faction(player.faction_id)
            available_figures = self.state.curia.get_all_available()
            vacancies = faction.get_vacancies(self.state, self.state.get_economic_rule("faction_member_limit", 6))
            bids = self.recruitment_decider.decide_bids(faction, available_figures, vacancies, self.state)
            for fig_id, amount in bids.items():
                self.state.add_forum_action("recruitment_bids", (faction.id, fig_id, amount))

            budgeted_contracts = self._get_available_contracts()
            for contract in budgeted_contracts:
                knights = [m for m in faction.get_members(self.state)
                           if m.class_tier == ClassTier.EQUES and not m.is_dead]
                if not knights:
                    continue
                if contract.contract_type == ContractType.TAX_FARMING:
                    result = self.bid_decider.decide_tax_bid(contract, knights, self.state)
                    if result:
                        knight, amount, tax_rate = result
                        self.state.add_forum_action("contract_bids", (contract.id, faction.id, amount))
                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    if getattr(contract, '_is_fleet_construction', False):
                        result = self.bid_decider.decide_fleet_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r = result
                            self.state.add_forum_action("contract_bids", (contract.id, faction.id, amount))
                    else:
                        result = self.bid_decider.decide_works_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r, construction, warranty = result
                            self.state.add_forum_action("contract_bids", (contract.id, faction.id, amount))

            trade_info = self.land_trade_decider.decide_trade(self.state)
            if trade_info:
                seller_id, buyer_id, amount = trade_info
                seller = self.state.get_member(seller_id)
                buyer = self.state.get_member(buyer_id)
                if seller and buyer:
                    from src.core.service.land_trading_service import LandTradingService
                    service = LandTradingService(self.state)
                    unit_price = service.calculate_land_price(seller, buyer)
                    total_price = amount * unit_price
                    self.state.add_forum_action("land_trades", (seller_id, buyer_id, amount, total_price))

            triumph = self._get_war_triumph()
            if triumph:
                vote = self.triumph_decider.decide_triumph(triumph["war"], triumph["commander"], self.state)
                self.state.add_forum_action("triumph_votes", (faction.id, vote))

            self._handle_next([])

    def _handle_step_3(self):
        """公示环节：显示结果后等待玩家输入next"""
        if not self._resolution_done:
            self._do_resolution()
            self._resolution_done = True

        if self._auto_mode:
            # 自动模式：直接进入下一环节
            self._handle_next([])
            return

        while True:
            print("\n🔧 本阶段可操作(ANY):", flush=True)
            print("   1. next/n → 进入私地交易环节", flush=True)
            print("\n> 请输入操作(ANY): ", end="", flush=True)
            cmd_input = input("").strip()
            if not cmd_input:
                continue
            parts = cmd_input.split()
            cmd = parts[0].lower()
            if cmd in ("next", "n"):
                self._handle_next([])
                break
            else:
                print(i18n.get("error_unknown_command"), flush=True)

    def _handle_step_4(self):
        """处理交易市场环节"""
        has_quaestor = self._has_quaestor()

        if not has_quaestor:
            self._print_ui_03_4(None, None)
            if self._auto_mode:
                # 自动模式：直接跳过
                self._step = 5
                return
            while True:
                print("\n> 请输入操作(ANY): ", end="", flush=True)
                cmd_input = input("").strip()
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                if cmd in ("next", "n"):
                    self._handle_next([])
                    break
                else:
                    print(i18n.get("error_unknown_command"), flush=True)
            return

        player_id = self._get_current_player_id()
        if not player_id:
            self._step = 5
            return
        player = self.state.get_player(player_id)
        if not player:
            self._step = 5
            return

        if self._auto_mode:
            # 自动模式：有财务官，走 AI 分支，但先打印界面
            self._print_ui_03_4(player_id, player.faction_id)
            trade_info = self.land_trade_decider.decide_trade(self.state)
            if trade_info:
                seller_id, buyer_id, amount = trade_info
                seller = self.state.get_member(seller_id)
                buyer = self.state.get_member(buyer_id)
                if seller and buyer:
                    from src.core.service.land_trading_service import LandTradingService
                    service = LandTradingService(self.state)
                    unit_price = service.calculate_land_price(seller, buyer)
                    total_price = amount * unit_price
                    self.state.add_forum_action("land_trades", (seller_id, buyer_id, amount, total_price))
            self._handle_next([])
            return

        bypass = self.state.config.get("testing.bypass_player_check", False)
        if bypass or player.player_type == PlayerType.HUMAN:
            self._print_ui_03_4(player_id, player.faction_id)
            while True:
                print(f"\n> 请输入操作(QUAESTOR {player_id}): ", end="", flush=True)
                cmd_input = input("").strip()
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                args = parts[1:]
                if cmd in ("next", "n"):
                    self._handle_next([])
                    break
                elif cmd == "transact":
                    self._handle_transact(args)
                else:
                    print(i18n.get("error_unknown_command"), flush=True)
        else:
            # AI 分支
            self._print_ui_03_4(player_id, player.faction_id)
            trade_info = self.land_trade_decider.decide_trade(self.state)
            if trade_info:
                seller_id, buyer_id, amount = trade_info
                seller = self.state.get_member(seller_id)
                buyer = self.state.get_member(buyer_id)
                if seller and buyer:
                    from src.core.service.land_trading_service import LandTradingService
                    service = LandTradingService(self.state)
                    unit_price = service.calculate_land_price(seller, buyer)
                    total_price = amount * unit_price
                    self.state.add_forum_action("land_trades", (seller_id, buyer_id, amount, total_price))
            self._handle_next([])

    # ==================== 核心执行函数 ====================

    def execute(self, args: List[str]) -> bool:
        auto = self.state.config.get("testing.auto_forum", False)
        self._auto_mode = auto
        # 无论自动还是手动，都走统一的状态机
        return self._execute_normal()

    def _execute_normal(self) -> bool:
        """正常/全人工测试/自动模式：使用状态机，根据配置自动跳过输入"""
        sys.stderr.flush()
        try:
            if self.state.is_phase_executed("forum"):
                print(i18n.get("error_phase_already_executed", phase="forum"), file=sys.stderr)
                sys.stderr.flush()
                return False

            self._step = 0
            self._players = self._get_step_players()
            self._current_player_index = 0

            self._generate_new_figures()
            self._generate_contracts()

            while self._step < 5:
                sys.stderr.flush()
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

            self.state.mark_phase_executed("forum")
            return True

        except Exception as e:
            print(f"!!! UNCAUGHT EXCEPTION in ForumCommand: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            return False

    # ==================== 辅助方法 ====================

    def _get_step_players(self) -> List[str]:
        if self._step == 1 or self._step == 2:
            return [p.player_id for p in self.state.get_all_players() if p.player_type.value == "human"]
        elif self._step == 4:
            return self._get_quaestor_players()
        return []

    def _next_player(self) -> Optional[str]:
        if not self._players:
            sys.stderr.flush()
            return None
        self._current_player_index += 1
        if self._current_player_index >= len(self._players):
            sys.stderr.flush()
            return None
        next_id = self._players[self._current_player_index]
        sys.stderr.flush()
        return next_id

    def _get_current_player_id(self) -> Optional[str]:
        if 0 <= self._current_player_index < len(self._players):
            pid = self._players[self._current_player_index]
            sys.stderr.flush()
            return pid
        sys.stderr.flush()
        return None