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
from typing import List, Optional, Dict, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.api import forum_api, figure_api
from src.core.i18n import i18n
from src.core.entities.figure import Figure, ClassTier,RomanNameGenerator
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.localization import TerminologyService
from src.core.systems.war_system import WarStatus
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
        # 步骤顺序：0: 公告, 1: 裁员, 2: 市场, 3: 交易市场, 4: 公示, 5: 完成
        self._step = 0
        self._current_player_index = 0
        self._players = []
        self.terms = TerminologyService.get()
        self._resolution_done = False
        self._auto_mode = False
        self._war_events = []

        auto_forum = state.config.get("testing.auto_forum", False)

        # 初始化决策器
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

        # 创建自动玩家处理器，传入所有需要的决策器
        from src.ui.processors.auto_player_processor import AutoPlayerProcessor
        self.auto_processor = AutoPlayerProcessor(
            state,
            retirement_decider=self.retirement_decider,
            recruitment_decider=self.recruitment_decider,
            bid_decider=self.bid_decider,
            triumph_decider=self.triumph_decider
        )

    # ==================== 辅助函数 ====================

    def _update_war_system_silent(self):
        ws = self.state.get_war_system()
        if not ws:
            return []
        # 获取触发事件（新威胁），不打印
        trigger_events = ws.check_triggers(self.state.turn.year, verbose=False)
        # 获取升级事件
        escalate_events = ws.escalate_threats()
        self._war_events = trigger_events + escalate_events
        return self._war_events

    def _apply_market_decisions(self, player_id: str, faction):
        """为指定派系应用市场环节的 AI 决策（招募、竞标、凯旋投票）"""
        self.state.log_event(
            f"[DEBUG] 为派系 {faction.name} 执行自动市场决策",
            level=logging.DEBUG,
            extra={"function": "_apply_market_decisions", "faction_id": faction.id}
        )
        # 1. 招募
        try:
            available_figures = self.state.curia.get_all_available()
            vacancies = faction.get_vacancies(self.state, self.state.get_economic_rule("faction_member_limit", 6))
            bids = self.recruitment_decider.decide_bids(faction, available_figures, vacancies, self.state)
            for fig_id, amount in bids.items():
                forum_api.recruit_figure(self.state, player_id, fig_id, amount)
        except Exception as e:
            logging.exception("招募决策异常")

        # 2. 合同竞标
        try:
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
                        forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, tax_rate)
                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    if getattr(contract, '_is_fleet_construction', False):
                        result = self.bid_decider.decide_fleet_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r = result
                            forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, r)
                    else:
                        result = self.bid_decider.decide_works_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r, construction, warranty = result
                            forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, r)
        except Exception as e:
            logging.exception("竞标决策异常")

        # 3. 凯旋投票
        try:
            war_system = self.state.get_war_system()
            if war_system:
                for war in war_system.get_resolved_wars():
                    # 修正：使用 triumph_commander_id 且不为 None
                    if war.soldier_share > 0 and war.status == WarStatus.RESOLVED and war.triumph_commander_id is not None:
                        commander = self.state.get_member(war.triumph_commander_id)
                        if not commander or commander.is_dead:
                            continue
                        vote = self.triumph_decider.decide_triumph(war, commander, self.state)
                        forum_api.vote_triumph(self.state, player_id, war.id, vote)
        except Exception as e:
            logging.exception("凯旋投票异常")

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
        war_system = self.state.get_war_system()
        if not war_system:
            return None
        for war in war_system.get_resolved_wars():
            # 使用 triumph_commander_id，且必须不为 None
            if war.status == WarStatus.RESOLVED and war.soldier_share > 0 and war.triumph_commander_id is not None:
                commander = self.state.get_member(war.triumph_commander_id)
                if commander and not commander.is_dead:
                    return {
                        "war": war,
                        "commander": commander
                    }
        return None

    def _get_available_contracts(self) -> List[Contract]:
        """获取可竞标的合同（BUDGETED 状态）"""
        return [c for c in self.state.contracts if c.status == ContractStatus.BUDGETED]


    # ==================== 原有功能函数移植 ====================

    def _generate_new_figures(self) -> List[Figure]:
        """生成新人物，包括普通人和英雄，返回新人物列表"""
        new_figures = []
        forum_rules = self.state.config.get("forum_rules", {})
        count = forum_rules.get("new_figures_count", 3)
        probs = forum_rules.get("class_probabilities", {})
        nobile_prob = probs.get("nobile", 0.1)
        eques_prob = probs.get("eques", 0.25)
        pleb_prob = 1 - nobile_prob - eques_prob
        if pleb_prob < 0:
            pleb_prob = 0.65

        # 生成普通新人
        for _ in range(count):
            tier_roll = random.random()
            if tier_roll < nobile_prob:
                fig = Figure.create_nobile(self.state.allocate_id(), None, age=random.randint(30, 50))
            elif tier_roll < nobile_prob + eques_prob:
                fig = Figure.create_eques(self.state.allocate_id(), None, age=random.randint(25, 40))
            else:
                fig = Figure.create_plebeian(self.state.allocate_id(), None, age=random.randint(20, 35))
            self.state.add_member(fig)
            self.state.curia.add_figure(fig)
            new_figures.append(fig)

        # ===== 天降猛男：额外生成英雄 =====
        if self.state.hero_spawned_this_turn and self.state.hero_to_spawn:
            hero_info = self.state.hero_to_spawn
            if hero_info["type"] == "historical":
                hero = self._create_historical_hero(hero_info["data"])
            else:
                hero = self._create_random_mighty_man()

            self.state.add_member(hero)
            self.state.curia.add_figure(hero)
            new_figures.append(hero)
            print(f"      🌟 英雄降临: {hero.get_formal_name()} "
                  f"(军略 {hero.martial}, 智略 {hero.intelligence}, "
                  f"魅力 {hero.charisma}, 热诚 {hero.zeal})")
            self.state.log_event(
                f"天降猛男生成: {hero.get_formal_name()}",
                extra={"type": "hero_spawn", "figure_id": hero.id}
            )

            # 清除标记
            self.state.hero_spawned_this_turn = False
            self.state.hero_to_spawn = None

        return new_figures

    def _create_historical_hero(self, data: dict) -> Figure:
        """根据历史英雄数据创建人物"""
        birth_year = data["birth_year"]
        current_year = self.state.turn.year
        # 计算年龄：公元前年份差取绝对值
        age = abs(current_year - birth_year)
        figure_id = self.state.allocate_id()
        hero = Figure(
            id=figure_id,
            name=data["name"],
            age=age,
            martial=data["martial"],
            intelligence=data["intelligence"],
            charisma=data["charisma"],
            zeal=data["zeal"],
            family_prestige=data.get("family_prestige", 0)
        )
        hero.class_tier = ClassTier.NOBILE
        self.state.add_spawned_hero_id(data["id"])
        return hero

    def _create_random_mighty_man(self) -> Figure:
        """生成随机猛人，属性基于当前存活人物最大值"""
        living = self.state.get_living_members()
        if living:
            max_martial = max(f.martial for f in living)
            max_intel = max(f.intelligence for f in living)
            max_charisma = max(f.charisma for f in living)
            max_zeal = max(f.zeal for f in living)
        else:
            # 无存活人物时使用默认值
            max_martial = max_intel = max_charisma = max_zeal = 5

        # 生成罗马名字
        praenomen, nomen, cognomen, full_name = RomanNameGenerator.generate_nobile_name()
        figure_id = self.state.allocate_id()
        hero = Figure(
            id=figure_id,
            name=full_name,
            age=random.randint(30, 45),
            martial=max_martial,
            intelligence=max_intel,
            charisma=max_charisma,
            zeal=max_zeal,
            family_prestige=random.randint(1, 3)
        )
        hero.class_tier = ClassTier.NOBILE
        hero.praenomen = praenomen
        hero.nomen = nomen
        hero.cognomen = cognomen
        return hero

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

    # ==================== 新增：战争威胁、民变、凯旋等状态更新方法 ====================

    def _update_civil_unrest(self):
        """更新行省民怨（自动升级、合同税率触发、起义检测）"""
        if not self.state.config.get("enable_threats", True):
            return
        base_tax_rate = self.state.get_economic_rule("province_tax_rate", 0.1)
        italy_unrest_trigger = self.state.config.get("economic_rules.italy_unrest_trigger_turns", 3)
        # ===== 新增：获取土地价格和私地收入率 =====
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        private_income_rate = self.state.get_economic_rule("private_land_income_rate", 0.05)
        # =========================================
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

        # 意大利本土处理（省略，保持原样）
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

        # 行省处理
        for province in provinces:
            if province.province_id == 0:
                continue

            # 起义检测
            if province.grievance >= 3 and not province.event_flags.get("rebellion_active"):
                war_system = self.state.get_war_system()
                if war_system:
                    rebellion_war = war_system.create_rebellion_war(province)
                    if war_system.register_rebellion_war(rebellion_war):
                        province.set_event_flag("rebellion_active", True)
                        print(f"      ⚔️ 行省 {province.name} 爆发起义！战争 {rebellion_war.name} 已激活。")
                        self.state.log_event(
                            f"行省起义：{province.name}",
                            extra={"type": "rebellion", "province_id": province.province_id}
                        )
                        any_change = True

            # 自动升级
            if 0 < province.grievance < 3:
                province.set_grievance(province.grievance + 1)
                print(f"      ⚠️ 行省 {province.name} 民怨升级至 {province.grievance} 级")
                if province.grievance == 3:
                    print(f"         行省 {province.name} 爆发平民起义！")
                any_change = True

            # 包税合同实际税率触发民变
            contracts = province_contracts.get(province.province_id, [])
            if contracts:
                for contract in contracts:
                    # 计算实际税率
                    land_value = province.land_private * land_price
                    expected_income = int(land_value * private_income_rate)
                    if expected_income <= 0:
                        continue
                    total_collected = contract.contract_price * (1 + contract.profit_rate)
                    actual_tax_rate = total_collected / expected_income
                    if actual_tax_rate > base_tax_rate:
                        if province.grievance < 1:
                            province.set_grievance(1)
                            print(
                                f"      🔔 行省 {province.name} 因包税合同实际税率 {actual_tax_rate * 100:.1f}% > {base_tax_rate * 100:.1f}%，民怨升至 1 级")
                            any_change = True
                        else:
                            print(
                                f"      📌 行省 {province.name} 包税合同实际税率 {actual_tax_rate * 100:.1f}%，当前民怨 {province.grievance} 级")
                    else:
                        if province.grievance > 0:
                            province.set_grievance(province.grievance - 1)
                            print(
                                f"      🍃 行省 {province.name} 因包税合同实际税率降低，民怨下降至 {province.grievance} 级")
                            any_change = True
            else:
                if province.grievance > 0:
                    print(f"      ℹ️ 行省 {province.name} 当前民怨 {province.grievance} 级")
                    any_change = True

        if not any_change:
            print(f"      所有行省安居乐业，无民变威胁。")

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
        for event in self._war_events:
            print(f"   {event}")

        # 显示活跃战争
        self._display_active_wars()
        # 显示停战草案
        self._display_truce_treaties()
        ws = self.state.get_war_system()
        if ws:
            threat_wars = ws.get_threat_wars()
            if threat_wars:
                print("   ⚠️ 当前威胁战争：")
                for war in threat_wars:
                    print(f"\t\t{war.name} (等级 {war.threat_level})")

        # 行省民变更新
        self._update_civil_unrest()

        # 凯旋信息（仅显示待投票的凯旋，不在此处审批）
        triumph = self._get_war_triumph()
        if triumph:
            commander = triumph["commander"]
            print(f"\n   🏆 {commander.get_formal_name()} 的凯旋等待投票")

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
                # 添加调试日志
                self.state.log_event(
                    f"广场阶段显示合同 {c.id} 预算 {c.base_cost}",
                    level=logging.DEBUG,
                    extra={"contract_id": c.id, "budget": c.base_cost}
                )
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
                    print(
                        f"      ✅ 平民分地 {act['amount']} C 土地（占国家公地 {act['percent'] * 100:.1f}%），转入意大利私地，民怨重置。")
                # 卖地法案不再出现在这里

        # 显示待售公地配额（来自元老院通过的卖地法案）
        pending_quota = self.state.pending_land_sale_quota
        if pending_quota > 0:
            print(f"\n   🏞️ 待售公地配额：{pending_quota} C（可通过 buy <人物ID> <数量> 认购）")

        # 凯旋信息
        triumph = self._get_war_triumph()
        if triumph:
            commander = triumph["commander"]
            print(f"\n   🏆 {commander.get_formal_name()} 的凯旋等待投票")

        print(f"\n🔧 本阶段可操作(PLAYER {player_id} {faction_name})：")
        print("   1. investigate → 查看人才详情")
        print("   2. recruit <人物ID> <金额> → 招募新人")
        print("   3. bid <合同ID> <骑士ID> <金额> → 竞标合同")
        print("   4. buy <人物ID> <数量> → 认购公地")
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
        print("\n--- 步骤说明(未开放功能) ---")
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
            print("❌ 用法: retire <人物ID>", flush=True)
            return False
        try:
            fig_id = int(args[0])
        except ValueError:
            print("❌ 人物ID必须为数字", flush=True)
            return False

        player_id = self._get_current_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", flush=True)
            return False
        result = forum_api.retire_figure(self.state, player_id, fig_id)
        print(result["message"])
        sys.stdout.flush()
        return result["success"]

    def _handle_recruit(self, args: List[str]) -> bool:
        if len(args) != 2:
            print("❌ 用法: recruit <人物ID> <金额>", flush=True)
            return False
        try:
            fig_id = int(args[0])
            amount = int(args[1])
        except ValueError:
            print("❌ 人物ID和金额必须为数字", flush=True)
            return False

        if amount <= 0:
            print("❌ 金额必须为正整数", flush=True)
            return False

        fig = next((f for f in self.state.curia.get_all_available() if f.id == fig_id), None)
        if not fig:
            print(f"❌ 人物 ID {fig_id} 不在广场中", flush=True)
            return False

        player_id = self._get_current_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", flush=True)
            return False

        player = self.state.get_player(player_id)
        if not player:
            return False
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return False

        # 检查派系空缺（已有逻辑）
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
            print(f"❌ {faction.name} 派系成员已满，无法招募", flush=True)
            return False

        result = forum_api.recruit_figure(self.state, player_id, fig_id, amount)
        print(result["message"])
        sys.stdout.flush()
        return result["success"]

    def _handle_bid(self, args: List[str]) -> bool:
        # 参数个数检查：3或4
        if len(args) not in (3, 4):
            print("❌ 用法: bid <合同ID> <骑士ID> <金额> [利润率(0-1)]", flush=True)
            return False
        try:
            contract_id = int(args[0])
            figure_id = int(args[1])
            amount = int(args[2])
        except ValueError:
            print("❌ 合同ID、骑士ID、金额必须为数字", flush=True)
            return False

        # 利润率处理
        profit_rate = None
        if len(args) == 4:
            try:
                profit_rate = float(args[3])
            except ValueError:
                print("❌ 利润率必须为数字", flush=True)
                return False
            if profit_rate <= 0 or profit_rate >= 1:
                print("❌ 利润率必须在0到1之间", flush=True)
                return False
        else:
            # 从配置获取默认利润率
            profit_rate = self.state.get_economic_rule("default_bid_profit_rate", 0.2)
            if profit_rate <= 0 or profit_rate >= 1:
                profit_rate = 0.2

        # 检查合同是否存在且可竞标
        contract = self.state.get_contract(contract_id)
        if not contract:
            print(f"❌ 合同 ID {contract_id} 不存在", flush=True)
            return False
        if contract.status != ContractStatus.BUDGETED:
            print(f"❌ 合同 {contract.name} 不可竞标", flush=True)
            return False

        # 获取当前玩家
        player_id = self._get_current_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", flush=True)
            return False
        player = self.state.get_player(player_id)
        if not player:
            return False
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return False

        # 检查骑士是否属于该派系且存活
        figure = self.state.get_member(figure_id)
        if not figure or figure.is_dead:
            print(f"❌ 骑士 ID {figure_id} 不存在或已死亡", flush=True)
            return False
        if figure.faction_id != faction.id:
            print(f"❌ 骑士 {figure.get_formal_name()} 不属于您的派系", flush=True)
            return False
        if figure.class_tier.value != "eques":
            print(f"❌ 人物 {figure.get_formal_name()} 不是骑士，无法参与竞标", flush=True)
            return False

        # 金额合法性校验
        if amount <= 0:
            print("❌ 金额必须为正整数", flush=True)
            return False

        result = forum_api.place_bid(self.state, player_id, figure_id, contract_id, amount, profit_rate)
        print(result["message"])
        sys.stdout.flush()
        return result["success"]

    def _handle_buy(self, args: List[str]) -> bool:
        if len(args) != 2:
            print("❌ 用法: buy <人物ID> <数量>", flush=True)
            return False
        try:
            figure_id = int(args[0])
            amount = int(args[1])
        except ValueError:
            print("❌ 人物ID和数量必须为数字", flush=True)
            return False

        if amount <= 0:
            print("❌ 数量必须为正整数", flush=True)
            return False

        figure = self.state.get_member(figure_id)
        if not figure or figure.is_dead:
            print(f"❌ 人物 ID {figure_id} 不存在或已死亡", flush=True)
            return False

        player_id = self._get_current_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", flush=True)
            return False
        player = self.state.get_player(player_id)
        if not player:
            return False
        if figure.faction_id != player.faction_id:
            print(f"❌ 人物 {figure.get_formal_name()} 不属于您的派系", flush=True)
            return False

        result = forum_api.buy_land(self.state, player_id, figure_id, amount)
        print(result["message"])
        sys.stdout.flush()
        return result["success"]

    def _handle_vote(self, args: List[str]) -> bool:
        if len(args) != 1:
            print("❌ 用法: vote yes/no", flush=True)
            return False
        vote_str = args[0].lower()
        if vote_str not in ("yes", "no"):
            print("❌ 投票值必须是 'yes' 或 'no'", flush=True)
            return False
        if not self._get_war_triumph():
            print("   📭 没有凯旋仪式需要授予", flush=True)
            return False

        vote = (vote_str == "yes")
        player_id = self._get_current_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", flush=True)
            return False

        triumph = self._get_war_triumph()
        if not triumph:
            return False

        war_id = triumph["war"].id
        commander = triumph["commander"]

        result = forum_api.vote_triumph(self.state, player_id, war_id, vote)
        if result["success"]:
            # 自定义友好的投票结果消息
            commander_name = commander.get_formal_name()
            vote_text = "支持" if vote else "反对"
            print(f"✅ 已记录对 {commander_name} 凯旋的 {vote_text} 投票", flush=True)
        else:
            print(result["message"], flush=True)  # 保留原错误信息

        return result["success"]

    def _handle_transact(self, args: List[str]) -> bool:
        enable_private_trade = self.state.config.get("forum_rules.enable_private_land_trade", False)
        if not enable_private_trade:
            print("⚠️ 私地交易功能暂未开放", flush=True)
            return False
        if len(args) != 4:
            print("❌ 用法: transact <卖家ID> <买家ID> <土地数量> <价格>", flush=True)
            return False
        try:
            seller = int(args[0])
            buyer = int(args[1])
            land = int(args[2])
            price = int(args[3])
        except ValueError:
            print("❌ 所有参数必须为数字", flush=True)
            return False
        if land <= 0 or price <= 0:
            print("❌ 土地数量和价格必须为正整数", flush=True)
            return False

        player_id = self._get_current_player_id()
        if not player_id:
            print("❌ 无法获取当前玩家", flush=True)
            return False
        result = forum_api.transact_land(self.state, player_id, seller, buyer, land, price)
        print(result["message"])
        sys.stdout.flush()
        return result["success"]

    def _handle_investigate(self, args: List[str]) -> bool:
        if len(args) == 0:
            player_id = self._get_current_player_id()
            if not player_id:
                print(i18n.get("error_no_current_player"), flush=True)
                return False
            player = self.state.get_player(player_id)
            if not player:
                return False
            faction = self.state.get_faction(player.faction_id)
            if not faction:
                return False

            result = figure_api.get_figure_info(self.state)
            if not result["success"]:
                print(result["message"], flush=True)
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
                print(i18n.get("no_members_in_faction", faction=faction.name), flush=True)

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

            return True

        elif len(args) == 1:
            try:
                fig_id = int(args[0])
            except ValueError:
                print(i18n.get("error_invalid_id"), flush=True)
                return False
            result = figure_api.get_figure_info(self.state, fig_id)
            print(result["message"])
            sys.stdout.flush()
            return result["success"]

        else:
            print(i18n.get("error_usage_investigate"), flush=True)
            return False

    def _handle_balance(self, args: List[str]) -> bool:
        player_id = self._get_current_player_id()
        if not player_id:
            print(i18n.get("error_no_current_player"), flush=True)
            return False
        player = self.state.get_player(player_id)
        if not player:
            return False
        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return False
        print(i18n.get("info_balance", faction=faction.name, treasury=faction.treasury))
        sys.stdout.flush()
        return True

    def _handle_next(self, args: List[str]) -> bool:
        if self._step == 0:
            self._step = 1
            self._players = self._get_step_players()
            self._current_player_index = 0
            if self._players:
                self.state.set_current_player(self._players[0])
            print("\n--- 进入裁员环节 ---", flush=True)
        elif self._step in (1, 2, 3):
            if self._switch_to_next_player():
                return True
            else:
                # 所有玩家已完成，进入下一环节
                enable_private_trade = self.state.config.get("forum_rules.enable_private_land_trade", False)
                if self._step == 3 and not enable_private_trade:
                    # 跳过步骤4，直接完成
                    self._step = 5
                    self._players = []
                    self._current_player_index = 0
                    print("\n--- 广场阶段完成 ---", flush=True)
                else:
                    self._step += 1
                    self._players = self._get_step_players()
                    self._current_player_index = 0
                    # 同步游戏状态中的当前玩家为新步骤的第一个玩家
                    if self._players:
                        self.state.set_current_player(self._players[0])
                    if self._step == 2:
                        print("\n--- 进入市场环节 ---", flush=True)
                    elif self._step == 3:
                        print("\n--- 进入公示环节 ---", flush=True)
                    elif self._step == 4:
                        print("\n--- 进入私地交易环节 ---", flush=True)
                    elif self._step == 5:
                        print("\n--- 广场阶段完成 ---", flush=True)
        elif self._step == 4:
            if self._switch_to_next_player():
                return True
            else:
                self._step = 5
                self._players = []
                self._current_player_index = 0
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

    def _execute_pending_land_acts(self):
        acts = self.state.get_pending_land_acts()
        if not acts:
            return
        print(f"\n   🏞️ 执行土地法案：")
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        for act in acts:
            try:
                if act['type'] == 'distribution':
                    self._execute_land_distribution(act, land_price)
                elif act['type'] == 'sale':
                    # 卖地法案已经在元老院阶段设置了配额，这里无需处理
                    # 仅打印提示，避免遗漏
                    print(f"      🏛️ 贵族买地法案已批准，配额 {act.get('amount', 0)} C 待认购")
            except Exception as e:
                print(f"      ⚠️ 执行土地法案异常（已跳过）: {e}", flush=True)
                logging.exception(f"执行土地法案异常: act={act}")
                continue
        self.state.clear_pending_land_acts()

    def _execute_land_distribution(self, act, land_price):
        try:
            national_land = self.state.get_national_public_land()
            # 调试日志：打印法案数据和 national_land

            if 'percent' not in act:
                raise ValueError("法案缺少 'percent' 字段")
            percent = act['percent']
            if not isinstance(percent, (int, float)):
                raise TypeError(f"percent 类型错误: {type(percent)}")
            amount = int(national_land * percent)
            if amount <= 0:
                print(f"      ⚠️ 国家公地不足，无法分配。")
                return
            self.state.add_national_public_land(-amount)
            italy = self.state.get_province(0)
            if italy:
                italy.update_land_type(0, amount)  # 公地不变，私地增加
                italy.reset_turns_since_last_distribution()
                italy.set_grievance(0)
            print(f"      ✅ 平民分地 {amount} C 土地（占国家公地 {percent * 100:.1f}%），转入意大利私地，民怨重置。")
        except Exception as e:
            logging.exception(f"执行分地法案异常: act={act}")
            raise


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
            self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
            if not cmd_input:
                continue
            parts = cmd_input.split()
            cmd = parts[0].lower()
            if cmd in ("next", "n"):
                self._handle_next([])
                break
            else:
                print(i18n.get("error_unknown_command"), flush=True)

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
            self._print_ui_03_1(player_id, player.faction_id)
            faction = self.state.get_faction(player.faction_id)
            try:
                fig_id = self.retirement_decider.decide_whom_to_retire(faction)
                if fig_id is not None:
                    forum_api.retire_figure(self.state, player_id, fig_id)
                    print(f"🤖 AI派系 {faction.name} 进行了裁员操作。")
            except Exception as e:
                logging.exception("裁员环节自动决策异常")
            self._handle_next([])
            return

        # 正常/全人工测试模式
        bypass = self.state.config.get("testing.bypass_player_check", False)
        if bypass or player.player_type == PlayerType.HUMAN:
            self._print_ui_03_1(player_id, player.faction_id)
            while True:
                print(f"\n> 请输入操作(PLAYER {player_id}): ", end="", flush=True)
                cmd_input = input("").strip()
                self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
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
                    if not self._handle_retire(args):
                        continue  # 继续输入
                else:
                    print(i18n.get("error_unknown_command"), flush=True)
        else:  # _handle_step_1 AI 分支（正常模式下的AI玩家）
            faction = self.state.get_faction(player.faction_id) if player else None
            self.state.log_event(
                f"[DEBUG] AI玩家 {player_id} 进入自动裁员环节",
                level=logging.DEBUG,
                extra={
                    "function": "_handle_step_1",
                    "player_id": player_id,
                    "faction_id": faction.id if faction else None
                }
            )
            # 调用处理器执行裁员（内部已处理异常）
            self.auto_processor.process_retirement(player_id, faction)
            self._handle_next([])

    def _handle_step_2(self):
        """处理市场环节（招募、竞标、凯旋投票）"""
        player_id = self._get_current_player_id()
        if not player_id:
            self._step += 1
            return
        player = self.state.get_player(player_id)
        if not player:
            self._step += 1
            return

        if self._auto_mode:
            self._print_ui_03_2(player_id, player.faction_id)
            faction = self.state.get_faction(player.faction_id)
            if faction:
                try:
                    # ===== 新增：市场环节开始前打印骑士财富 =====
                    knights = [m for m in faction.get_members(self.state) if
                               m.class_tier == ClassTier.EQUES and not m.is_dead]

                    for k in knights:
                        print(f"   {k.name}: {k.wealth}")
                    self._apply_market_decisions(player_id, faction)
                    print(f"🤖 AI派系 {faction.name} 进行了市场操作。")  # 新增
                    # ===== 新增：市场环节结束后打印骑士财富 =====
                    knights = [m for m in faction.get_members(self.state) if
                               m.class_tier == ClassTier.EQUES and not m.is_dead]

                    for k in knights:
                        print(f"   {k.name}: {k.wealth}")
                except Exception as e:
                    logging.exception("市场环节自动决策异常")
            self._handle_next([])
            return

        # 正常/全人工测试模式
        bypass = self.state.config.get("testing.bypass_player_check", False)
        if bypass or player.player_type == PlayerType.HUMAN:
            self._print_ui_03_2(player_id, player.faction_id)
            while True:
                print(f"\n> 请输入操作(PLAYER {player_id}): ", end="", flush=True)
                cmd_input = input("").strip()
                self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                args = parts[1:]

                if cmd in ("next", "n"):
                    self._handle_next([])
                    break
                elif cmd == "investigate":
                    if not self._handle_investigate(args):
                        continue
                elif cmd == "recruit":
                    if not self._handle_recruit(args):
                        continue
                elif cmd == "bid":
                    if not self._handle_bid(args):
                        continue
                elif cmd == "buy":
                    if not self._handle_buy(args):
                        continue
                elif cmd == "vote":
                    if not self._handle_vote(args):
                        continue
                elif cmd == "balance":
                    if self._handle_balance(args):
                        continue
                else:
                    print(i18n.get("error_unknown_command"), flush=True)
        else:  # AI 分支
            faction = self.state.get_faction(player.faction_id) if player else None
            self.state.log_event(
                f"[DEBUG] AI玩家 {player_id} 进入市场竞价环节",
                level=logging.DEBUG,
                extra={
                    "function": "_handle_step_2",
                    "player_id": player_id,
                    "faction_id": faction.id if faction else None
                }
            )
            # 调用处理器执行市场决策
            self.auto_processor.process_market(player_id, faction)
            print(f"🤖 AI派系 {faction.name} 进行了市场操作。")  # 新增
            self._handle_next([])

    def _handle_step_3(self):
        """公示环节：显示结果后等待玩家输入next"""
        if not self._resolution_done:
            self._do_resolution()
            self._resolution_done = True

        # 获取配置开关
        enable_private_trade = self.state.config.get("forum_rules.enable_private_land_trade", False)

        # 如果私地交易被禁用，直接跳过
        if not enable_private_trade:
            self._handle_next([])
            return

        if self._auto_mode:
            self._handle_next([])
            return

        while True:
            print("\n🔧 本阶段可操作(ANY):", flush=True)
            print("   1. next/n → 进入私地交易环节", flush=True)
            print("\n> 请输入操作(ANY): ", end="", flush=True)
            cmd_input = input("").strip()
            self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
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
        player_id = self._get_current_player_id() if has_quaestor else None
        faction_id = None
        if player_id:
            player = self.state.get_player(player_id)
            faction_id = player.faction_id if player else None
        self._print_ui_03_4(player_id, faction_id)

        if self._auto_mode:
            # 自动模式：生成土地交易并立即执行
            if has_quaestor:
                try:
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
                            result = forum_api.transact_land(
                                self.state,
                                player_id or "",
                                seller_id,
                                buyer_id,
                                amount,
                                total_price,
                                bypass_permission=True
                            )
                            if result["success"]:
                                print(f"🤖 AI派系 {self.state.get_faction(seller.faction_id).name} 进行了土地交易。",
                                      flush=True)
                            else:
                                print(f"⚠️ 土地交易失败：{result['message']}", flush=True)
                except Exception as e:
                    logging.exception("交易市场环节自动决策异常")
            try:
                land_result = forum_api.resolve_land_trades(self.state)
                if land_result["message"]:
                    print(land_result["message"])
                for faction in self.state.factions.values():
                    members = faction.get_members(self.state)
                    faction.update_total_land(members)
            except Exception as e:
                logging.exception("交易市场结算异常")
            self._step = 5
            return

        # 手动模式
        if not has_quaestor:
            while True:
                print("\n> 请输入操作(ANY): ", end="", flush=True)
                cmd_input = input("").strip()
                self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                if cmd in ("next", "n"):
                    if self._switch_to_next_player():
                        continue
                    else:
                        try:
                            land_result = forum_api.resolve_land_trades(self.state)
                            if land_result["message"]:
                                print(land_result["message"])
                            for faction in self.state.factions.values():
                                members = faction.get_members(self.state)
                                faction.update_total_land(members)
                        except Exception as e:
                            logging.exception(f"交易市场结算异常: {e}")
                            print(f"⚠️ 交易市场结算出错（已跳过）", flush=True)
                        self._step = 5
                        return
                else:
                    print(i18n.get("error_unknown_command"), flush=True)
        else:
            # 有财务官
            while True:
                print(f"\n> 请输入操作(QUAESTOR {player_id}): ", end="", flush=True)
                cmd_input = input("").strip()
                self.state.log_event(f"[INPUT] {cmd_input}", level=logging.INFO)
                if not cmd_input:
                    continue
                parts = cmd_input.split()
                cmd = parts[0].lower()
                args = parts[1:]
                if cmd in ("next", "n"):
                    if self._switch_to_next_player():
                        continue
                    else:
                        try:
                            land_result = forum_api.resolve_land_trades(self.state)
                            if land_result["message"]:
                                print(land_result["message"])
                            for faction in self.state.factions.values():
                                members = faction.get_members(self.state)
                                faction.update_total_land(members)
                        except Exception as e:
                            print(f"!!! 交易市场结算异常: {e}", flush=True)
                            traceback.print_exc(file=sys.stdout)
                        self._step = 5
                        return
                elif cmd == "transact":
                    self._handle_transact(args)
                else:
                    print(i18n.get("error_unknown_command"), flush=True)

    # ==================== 核心执行函数 ====================

    def execute(self, args: List[str]) -> bool:
        auto = self.state.config.get("testing.auto_forum", False)
        self._auto_mode = auto
        # 无论自动还是手动，都走统一的状态机
        return self._execute_normal()

    def _execute_normal(self) -> bool:
        """正常/全人工测试/自动模式：使用状态机，根据配置自动跳过输入"""
        try:
            # 检查前置阶段
            if not self.state.is_phase_executed("revenue"):
                print("⚠️ 必须先执行收入阶段 (revenue)", flush=True)
                return False

            if self.state.is_phase_executed("forum"):
                print(i18n.get("error_phase_already_executed", phase="forum"), flush=True)
                return False

            self._step = 0
            self._players = self._get_step_players()
            self._current_player_index = 0

            # 将游戏状态中的当前玩家设置为人口阶段的第一个玩家
            if self._players:
                self.state.set_current_player(self._players[0])

            # 显示当前玩家信息（清屏+信息）
            self._show_current_player_overview()

            # 先更新战争系统
            self._update_war_system_silent()

            # 处理舰队建造完成
            if self.state.naval_system:
                completed = self.state.naval_system.process_fleet_construction(self.state.turn.turn_number)
                for fleet_num in completed:
                    print(f"      ⚓ 舰队 {fleet_num} 建造完成")
            self._generate_new_figures()
            self._generate_contracts()

            while self._step < 5:
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
            logging.exception("UNCAUGHT EXCEPTION in ForumCommand")
            return False

    # ==================== 辅助方法 ====================

    def _get_step_players(self) -> List[str]:
        if self._step == 1 or self._step == 2:
            # 返回所有玩家（包括AI和人类）
            return [p.player_id for p in self.state.get_all_players()]
        elif self._step == 4:
            return self._get_quaestor_players()
        return []

    def _next_player(self) -> Optional[str]:
        if not self._players:
            return None
        self._current_player_index += 1
        if self._current_player_index >= len(self._players):
            return None
        next_id = self._players[self._current_player_index]
        return next_id

    def _get_current_player_id(self) -> Optional[str]:
        if 0 <= self._current_player_index < len(self._players):
            pid = self._players[self._current_player_index]
            return pid
        return None
