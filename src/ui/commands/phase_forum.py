# src/ui/commands/phase_forum.py
"""
广场阶段命令 - 完整功能版，严格遵循 UI 设计师流程
"""
import sys
import traceback
import random
import logging
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.api import forum_api, figure_api, player_api, game_api
from src.core.i18n import i18n
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.localization import TerminologyService
from src.core.systems.war_system import War, WarStatus

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ForumCommand(Command):
    """广场阶段命令 - 支持多步骤玩家交互，包含完整功能"""

    name = "forum"
    aliases = ["f"]
    description = "执行广场阶段 (Forum Phase) - 包含裁员、招募、竞标、土地交易"

    def __init__(self, state: "GameState"):
        super().__init__(state)
        self._step = 0  # 0: 公告, 1: 裁员, 2: 市场, 3: 公示, 4: 交易市场, 5: 完成
        self._current_player_index = 0
        self._players = []
        self.terms = TerminologyService.get()
        self._resolution_done = False  # 控制公示只执行一次

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
            print(f"\n   📢 {len(new_figures)} new figure(s) arrive in the Rome:", file=sys.stderr)

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
                    # 仅当行省已征服时才续约（未征服的行省不应有活跃合同，但以防万一）
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
                print(f"\n   ⚓ 检测到海战威胁，生成 {len(construction_contracts)} 个舰队建造合同", file=sys.stderr)
            replacement_contracts = self.state.naval_system.generate_replacement_contracts(
                self.state.turn.turn_number)
            if replacement_contracts:
                print(f"\n   ⚓ 罗马舰队不足，生成 {len(replacement_contracts)} 个补充舰队建造合同", file=sys.stderr)

        return contracts  # 返回生成的合同列表（可选）

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

    # ==================== 步骤展示函数 ====================

    def _print_ui_03_0(self):
        """打印 UI_03-0 公告环节"""
        print("\n############################################################", file=sys.stderr)
        print(f" UI_03-0 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]", file=sys.stderr)
        print("############################################################", file=sys.stderr)
        print("--- 阶段预览---", file=sys.stderr)
        print("广场阶段为玩家交互核心环节，包含人才招募、合同拍卖、土地交易三大核心玩法。", file=sys.stderr)
        print("你可出价招募人物、竞标工程/舰队合同、手动促成土地交易，结果直接影响派系", file=sys.stderr)
        print("实力、个人财富及后续元老院的议程和利益分配，请务必谨慎使用你的资源争取最", file=sys.stderr)
        print("大的利益！", file=sys.stderr)
        # 安民告示
        print("\n	====================== 安民告示 ====================", file=sys.stderr)

        # 战争威胁
        war_system = self.state.get_war_system()
        if war_system:
            threats = war_system.get_threat_wars()
            if threats:
                print("   ⚔️ 战争威胁：", file=sys.stderr)
                for war in threats:
                    threat_emoji = "⚠️" if war.threat_level <= 2 else "⚡"
                    print(f"   {threat_emoji} {war.name} 开始威胁罗马", file=sys.stderr)
                    if war.naval_required:
                        print(f"      ⚓ 检测到海战威胁，生成 1 个舰队建造合同", file=sys.stderr)
            else:
                print("   ⚔️ 当前无战争威胁", file=sys.stderr)

        # 行省民变
        provinces = self.state.get_all_provinces()
        revolting = [p for p in provinces if p.grievance == 3]
        if revolting:
            print("   📊 民变威胁：", file=sys.stderr)
            for p in revolting:
                print(f"      ⚠️ {p.name} 爆发起义！", file=sys.stderr)
        else:
            print("   📊 行省民变状态：", file=sys.stderr)
            print("      所有行省安居乐业，无民变威胁。", file=sys.stderr)

        # 凯旋信息
        triumph = self._get_war_triumph()
        if triumph:
            commander = triumph["commander"]
            print(f"\n   🏆 {commander.get_formal_name()} 取得了 {triumph['war'].name} 的胜利正返回罗马。", file=sys.stderr)
            print(f"      元老院正在讨论是否要授予他凯旋仪式。", file=sys.stderr)

        print("\n🔧 本阶段可操作(ANY)：", file=sys.stderr)
        print("   1. next/n → 进入裁员环节", file=sys.stderr)
        sys.stderr.flush()

    def _print_ui_03_1(self, player_id: str, faction_id: str):
        """打印 UI_03-1 裁员环节"""
        player = self.state.get_player(player_id)
        faction = self.state.get_faction(faction_id)
        faction_name = faction.name if faction else "未知"
        print("\n############################################################", file=sys.stderr)
        print(f" UI_03-1 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]", file=sys.stderr)
        print("############################################################", file=sys.stderr)
        print("\n--- 步骤说明 ---", file=sys.stderr)
        print("新鲜血液是保持组织活力的重要源泉，裁汰掉对组织没有贡献的成员，才能腾出空", file=sys.stderr)
        print("间招募更优秀的人才。请从你的成员列表中挑选需要淘汰的成员，让他们去广场上", file=sys.stderr)
        print("自谋生路吧。", file=sys.stderr)

        # 显示派系成员列表
        result = figure_api.get_figure_info(self.state)
        if result["success"]:
            members = [f for f in result["data"] if f["faction_id"] == faction_id]
            if members:
                print("\n================================================================================", file=sys.stderr)
                print(f"   👥 {faction_name} 存活派系人物列表", file=sys.stderr)
                print("================================================================================", file=sys.stderr)
                for m in members:
                    status = "👑" if m["is_faction_leader"] else "🟢"
                    tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(m["class_tier"], "❓")
                    print(f"{status}{tier_emoji} ID:{m['id']:<3} {m['name']:<25} 派系:{m['faction_id']:<12} 影响力:{m['influence']} 财富:{m['wealth']} 人气:{m['popularity']} 私地:{m['land_private']} 老兵:{m['veterans']} 官职:{m['office']}", file=sys.stderr)

        print(f"\n🔧 本阶段可操作 (PLAYER {player_id} {faction_name})：", file=sys.stderr)
        print("   1. investigate → 查询人物详情；", file=sys.stderr)
        print("   2. retire → 驱逐不需要的派系成员；", file=sys.stderr)
        print("   3. next/n → 下一个玩家；", file=sys.stderr)
        sys.stderr.flush()

    def _print_ui_03_2(self, player_id: str, faction_id: str):
        """打印 UI_03-2 市场环节"""
        player = self.state.get_player(player_id)
        faction = self.state.get_faction(faction_id)
        faction_name = faction.name if faction else "未知"
        print("\n############################################################", file=sys.stderr)
        print(f" UI_03-2 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]", file=sys.stderr)
        print("############################################################", file=sys.stderr)
        print("\n--- 步骤说明 ---", file=sys.stderr)
        print("罗马广场藏龙卧虎，物欲横流。是你利用金钱的力量扩张你的实力，招揽人才，竞标", file=sys.stderr)
        print("合同，兼并土地，结交权贵的最佳场所。当然，这一切都是在罗马法律的统治下公平", file=sys.stderr)
        print("竞争的结果。现在请你下注吧！", file=sys.stderr)

        # 人才市场

        print("\n====================== 人才市场 ====================", file=sys.stderr)
        # 生成新人物、新合同
        curia = self.state.curia.get_all_available()
        if curia:
            for fig in curia:
                tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(fig.class_tier.value, "❓")
                print(f"      {tier_emoji} ID:{fig.id} {fig.get_formal_name()} ({fig.class_tier.value})(军略 {fig.martial}, 智略 {fig.intelligence}, 魅力 {fig.charisma}, 热诚 {fig.zeal})", file=sys.stderr)
        else:
            print("   📭 广场无人物", file=sys.stderr)

        # 可竞标合同
        print("\n====================== 交易市场 ====================", file=sys.stderr)
        contracts = self._get_available_contracts()
        if contracts:
            for c in contracts:
                type_emoji = "📊" if c.contract_type == ContractType.TAX_FARMING else "🏗️"
                print(f"      🔔 标的 {c.id} {type_emoji} {c.name} 预算 {c.base_cost}", file=sys.stderr)
        else:
            print("   📭 没有待竞标的预算合同", file=sys.stderr)

        # 待决合同（仅显示）
        pending = [c for c in self.state.contracts if c.status == ContractStatus.PENDING]
        if pending:
            print("\n   📋 Pending Contracts (等待元老院预算表决):", file=sys.stderr)
            for c in pending:
                type_emoji = "📊" if c.contract_type == ContractType.TAX_FARMING else "🏗️"
                if c.contract_type == ContractType.TAX_FARMING:
                    print(f"      {type_emoji} ID:{c.id} {c.name}	预付:{c.base_cost} 预期利润:{c.expected_profit}", file=sys.stderr)
                else:
                    print(f"      {type_emoji} ID:{c.id} {c.name}	预算:{c.base_cost}", file=sys.stderr)

        # 土地法案
        acts = self.state.get_pending_land_acts()
        if acts:
            print("\n   🏞️ 执行土地法案：", file=sys.stderr)
            for act in acts:
                if act['type'] == 'distribution':
                    print(f"      ✅ 平民分地 {act['amount']} C 土地（占国家公地 {act['percent']*100:.1f}%），转入意大利私地，民怨重置。", file=sys.stderr)
                elif act['type'] == 'sale':
                    print(f"      🏛️ 贵族买地：出售 {act['amount']} C 国家公地。", file=sys.stderr)

        # 凯旋信息
        triumph = self._get_war_triumph()
        if triumph:
            commander = triumph["commander"]
            print(f"\n   🏆 {commander.get_formal_name()} 的凯旋等待投票", file=sys.stderr)

        print(f"\n🔧 本阶段可操作(PLAYER {player_id} {faction_name})：", file=sys.stderr)
        print("   1. investigate → 查看人才详情", file=sys.stderr)
        print("   2. recruit <人物ID> <金额> → 招募新人", file=sys.stderr)
        print("   3. bid <合同ID> <金额> → 竞标合同", file=sys.stderr)
        print("   4. buy <数量> → 认购公地", file=sys.stderr)
        print("   5. vote yes/no → 投票授予凯旋", file=sys.stderr)
        print("   6. balance → 查询派系金库；", file=sys.stderr)
        print("   7. next → 下一个玩家；", file=sys.stderr)
        sys.stderr.flush()

    def _print_ui_03_4(self, player_id: Optional[str], faction_id: Optional[str]):
        """打印 UI_03-4 交易市场环节（财务官）"""
        # 获取派系名称（用于显示）
        faction_name = "未知"
        if player_id and faction_id:
            faction = self.state.get_faction(faction_id)
            faction_name = faction.name if faction else "未知"

        print("\n############################################################", file=sys.stderr)
        print(f" UI_03-4 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]",
              file=sys.stderr)
        print("############################################################", file=sys.stderr)
        print("\n--- 步骤说明 ---", file=sys.stderr)
        print("贵族有土地，骑士有金钱，土地是地位的象征，而金钱是权力的保证，没有比土地", file=sys.stderr)
        print("交易更适合罗马城里权钱交易的游戏了。所有的土地交易都必须通过政府注册，因此", file=sys.stderr)
        print("这将成为有据可查的反腐利器！", file=sys.stderr)

        if not self._has_quaestor():
            print("\n⚠️ 罗马城里没有财务官，无法进行土地交易。", file=sys.stderr)
            print("\n🔧 本阶段可操作(ANY)：", file=sys.stderr)
            print("   1. next/n → 下一阶段；", file=sys.stderr)
        else:
            print(f"\n🔧 本阶段可操作(QUAESTOR {player_id} {faction_name})：", file=sys.stderr)
            print("   1. transact <卖家ID> <买家ID> <土地数量> <价格> → 交易土地", file=sys.stderr)
            print("   2. next → 下一阶段；", file=sys.stderr)
        sys.stderr.flush()

    def _print_ui_03_3(self):
        """打印 UI_03-3 公示环节"""
        print("\n############################################################", file=sys.stderr)
        print(f" UI_03-3 回合 {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC) - 广场阶段 [3/7]", file=sys.stderr)
        print("############################################################", file=sys.stderr)
        print("\n喧嚣散去，尘埃落下。", file=sys.stderr)

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
        print(result["message"], file=sys.stderr)
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

        # 检查人物是否在 Curia 中
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

        faction = self.state.get_faction(player.faction_id)  # <--- 必须在此处定义 faction
        if not faction:
            return False

        # ===== 新增：派系成员上限检查 =====
        num_factions = len(self.state.factions)
        if num_factions == 3:
            max_members = 6
        elif num_factions == 4:
            max_members = 5
        elif num_factions == 6:
            max_members = 4
        else:
            max_members = 5  # 默认值

        current_members = len(faction.get_members(self.state))
        vacancies = max_members - current_members
        if vacancies <= 0:
            print(i18n.get("error_no_vacancies", faction=faction.name), file=sys.stderr)
            sys.stderr.flush()
            return False
        # =================================

        result = forum_api.recruit_figure(self.state, player_id, fig_id, amount)
        print(result["message"], file=sys.stderr)
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
        # 检查合同是否存在且可竞标
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
        print(result["message"], file=sys.stderr)
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
        # 检查是否有公地可出售
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
        print(result["message"], file=sys.stderr)
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
        # 检查是否有凯旋需要投票
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
        print(result["message"], file=sys.stderr)
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
        print(result["message"], file=sys.stderr)
        sys.stderr.flush()
        return result["success"]

    def _handle_investigate(self, args: List[str]) -> bool:
        """处理 investigate 命令：
           无参：
             步骤1（裁员）：显示本派系所有存活人物
             步骤2（市场）：显示本派系所有存活人物 + 广场所有可招募人物
           有参：显示指定人物的详细信息
        """
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

            # 获取所有存活人物数据（用于派系成员）
            result = figure_api.get_figure_info(self.state)
            if not result["success"]:
                print(result["message"], file=sys.stderr)
                sys.stderr.flush()
                return False
            all_figures = result["data"]

            # 筛选本派系存活人物
            faction_members = [fig for fig in all_figures if
                               fig["faction_id"] == faction.id and not fig.get("is_dead", False)]

            # 打印派系成员列表
            if faction_members:
                print("\n================================================================================",
                      file=sys.stderr)
                print(f"   👥 {faction.name} 存活派系人物列表", file=sys.stderr)
                print("================================================================================",
                      file=sys.stderr)
                for m in faction_members:
                    status = "👑" if m.get("is_faction_leader", False) else "🟢"
                    tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(m["class_tier"], "❓")
                    office_display = m["office"] if m.get("office") and not m["office"].startswith("ex-") else "无"
                    print(
                        f"{status}{tier_emoji} ID:{m['id']:<3} {m['name']:<25} 派系:{m['faction_id']:<12} 影响力:{m['influence']} 财富:{m['wealth']} 人气:{m['popularity']} 私地:{m['land_private']} 老兵:{m['veterans']} 官职:{office_display}",
                        file=sys.stderr)
            else:
                print(i18n.get("no_members_in_faction", faction=faction.name), file=sys.stderr)

            # 如果是市场环节，显示广场人物
            if self._step == 2:
                curia_figures = self.state.curia.get_all_available()
                if curia_figures:
                    print("\n================================================================================",
                          file=sys.stderr)
                    print("   📢 广场可招募人物列表", file=sys.stderr)
                    print("================================================================================",
                          file=sys.stderr)
                    for fig in curia_figures:
                        tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(fig.class_tier.value, "❓")
                        print(
                            f"   {tier_emoji} ID:{fig.id} {fig.get_formal_name()} ({fig.class_tier.value})(军略 {fig.martial}, 智略 {fig.intelligence}, 魅力 {fig.charisma}, 热诚 {fig.zeal})",
                            file=sys.stderr)
                else:
                    print("\n   📭 广场无人物", file=sys.stderr)

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
            print(result["message"], file=sys.stderr)
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
        print(i18n.get("info_balance", faction=faction.name, treasury=faction.treasury), file=sys.stderr)
        sys.stderr.flush()
        return True

    def _handle_next(self, args: List[str]) -> bool:
        if self._step == 0:
            self._step = 1
            self._players = self._get_step_players()
            self._current_player_index = 0
            print("\n--- 进入裁员环节 ---", file=sys.stderr)
            sys.stderr.flush()
        elif self._step == 3:
            # 公示环节结束，进入交易市场
            self._step = 4
            self._players = self._get_step_players()
            self._current_player_index = 0
            print("\n--- 进入私地交易环节 ---", file=sys.stderr)
            sys.stderr.flush()
        elif self._step in (1, 2, 4):
            next_player_id = self._next_player()
            if next_player_id:
                player = self.state.get_player(next_player_id)
                faction = self.state.get_faction(player.faction_id) if player else None
                print(i18n.get("info_next_player", player=next_player_id, faction=faction.name if faction else "无"),
                      file=sys.stderr)
                sys.stderr.flush()
            else:
                self._step += 1
                self._players = self._get_step_players()
                self._current_player_index = 0
                if self._step == 2:
                    print("\n--- 进入市场环节 ---", file=sys.stderr)
                elif self._step == 3:
                    print("\n--- 进入公示环节 ---", file=sys.stderr)
                elif self._step == 5:
                    print("\n--- 广场阶段完成 ---", file=sys.stderr)
                sys.stderr.flush()
        sys.stderr.flush()
        return True

    def _do_resolution(self):
        """执行公示结算（只打印结果，不改变步骤）"""
        result = forum_api.resolve_forum(self.state)
        self._print_ui_03_3()
        print(result["message"], file=sys.stderr)
        sys.stderr.flush()

    # ==================== 步骤处理函数 ====================

    def _handle_step_0(self):
        """处理公告环节"""
        self._print_ui_03_0()
        while True:
            print("\n> 请输入操作(ANY): ", file=sys.stderr, end="")
            sys.stderr.flush()
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
        self._print_ui_03_1(player_id, player.faction_id)

        while True:
            print(f"\n> 请输入操作(PLAYER {player_id}): ", file=sys.stderr, end="")
            sys.stderr.flush()
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
        self._print_ui_03_2(player_id, player.faction_id)

        while True:
            print(f"\n> 请输入操作(PLAYER {player_id}): ", file=sys.stderr, end="")
            sys.stderr.flush()
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

    def _handle_step_3(self):
        """公示环节：显示结果后等待玩家输入next"""
        if not self._resolution_done:
            self._do_resolution()
            self._resolution_done = True

        while True:
            print("\n🔧 本阶段可操作(ANY):", file=sys.stderr)
            print("   1. next/n → 进入私地交易环节", file=sys.stderr)
            print("\n> 请输入操作(ANY): ", file=sys.stderr, end="")
            sys.stderr.flush()
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

    def _handle_step_4(self):
        """处理交易市场环节"""
        has_quaestor = self._has_quaestor()

        if not has_quaestor:
            # 无财务官：打印界面，然后等待玩家输入next
            self._print_ui_03_4(None, None)
            while True:
                print("\n> 请输入操作(ANY): ", file=sys.stderr, end="")
                sys.stderr.flush()
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
            return

        # 有财务官：正常流程
        player_id = self._get_current_player_id()
        if not player_id:
            self._step = 5
            return
        player = self.state.get_player(player_id)
        if not player:
            self._step = 5
            return

        self._print_ui_03_4(player_id, player.faction_id)

        while True:
            print(f"\n> 请输入操作(QUAESTOR {player_id}): ", file=sys.stderr, end="")
            sys.stderr.flush()
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
                print(i18n.get("error_unknown_command"), file=sys.stderr)
                sys.stderr.flush()


    # ==================== 核心执行函数 ====================

    def execute(self, args: List[str]) -> bool:
        sys.stderr.flush()
        try:
            if self.state.is_phase_executed("forum"):
                print(i18n.get("error_phase_already_executed", phase="forum"), file=sys.stderr)
                sys.stderr.flush()
                return False

            # 初始化状态机
            self._step = 0
            self._players = self._get_step_players()
            self._current_player_index = 0

            # 新人加入，合同生成
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
                    # 交易市场环节可能直接设置 _step = 5，循环自然结束

            # 所有环节完成，标记阶段
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
            # 裁员、市场环节：所有人类玩家
            return [p.player_id for p in self.state.get_all_players() if p.player_type.value == "human"]
        elif self._step == 4:
            # 交易市场环节：财务官所属玩家
            return self._get_quaestor_players()
        return []  # 公告(0)、公示(3) 无玩家操作

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