# src/ui/commands/phase_mortality.py
"""
天命阶段命令 - 处理事件卡和人物死亡
"""

import random
import logging
import json
from pathlib import Path
from typing import List, TYPE_CHECKING, Dict
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.contract import ContractStatus, ContractType
from src.ui.utils import get_progress_bar

if TYPE_CHECKING:
    from src.core.game_state import GameState


class MortalityCommand(Command):
    """天命阶段命令"""

    name = "mortality"
    aliases = ["m"]
    description = "执行天命阶段 (Mortality Phase) - 抽取事件卡"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        if self.state.is_phase_executed("mortality"):
            print("⚠️ 天命阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_mortality} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 从配置获取事件卡池
        rules = self.state.config.get("mortality_rules", {})
        deck = rules.get("event_deck", [])
        draw_count = rules.get("event_draw_count", 1)

        if not deck:
            print("   ⚠️ 未配置事件卡")
            self.state.mark_phase_executed("mortality")

            return True

        # 按权重抽取事件卡
        weights = [e.get("weight", 1) for e in deck]
        if sum(weights) == 0:
            # 所有权重为0时回退到等概率
            weights = [1] * len(deck)

        drawn_events = random.choices(deck, weights=weights, k=draw_count)

        for event in drawn_events:
            event_name = event["name"]
            effect = event["effect"]

            print(f"   🎴 事件卡: {event_name}")

            if effect == "death":
                self._handle_death_event()
            elif effect == "bountiful_harvest":
                self._handle_bountiful_harvest()
            elif effect == "peace":
                self._handle_peace_event()
            elif effect == "mighty_man":
                self._handle_mighty_man_event()
            elif effect == "disaster":
                self._handle_disaster_event()
            else:
                # 其他事件暂不实现，仅打印
                print(f"      (效果暂未实现)")
                self.state.log_event(f"{event_name}")

        self.state.mark_phase_executed("mortality")

        return True

    def _load_disasters(self) -> List[Dict]:
        """从 disasters.json 加载灾害数据，如果文件不存在或解析失败则返回空列表"""
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / "disasters.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("disasters", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.state.log_event(f"灾害数据加载失败: {e}", level=logging.WARNING)
            return []

    def _handle_disaster_event(self):
        """无妄天灾：随机一个行省受灾，影响该行省所有收入"""
        print(f"      🌪️ 无妄天灾！一场灾难降临罗马")

        # 获取所有已征服行省（包括意大利）
        provinces = [p for p in self.state.get_all_provinces() if p.conquered]
        if not provinces:
            print(f"         没有已征服行省，天灾无处降临")
            return

        # 随机选择一个行省
        province = random.choice(provinces)

        # 加载灾害配置
        disasters = self._load_disasters()
        if not disasters:
            # 如果没有灾害配置，使用默认值
            base_loss = self.state.config.get("mortality_rules.disaster_base_loss", 0.5)
            mitigation_factor = self.state.config.get("mortality_rules.disaster_mitigation_factor", 0.1)
            loss = base_loss
            # 简化：不使用基建减免
            print(f"         行省 {province.name} 受灾，损失比例 {loss*100:.0f}%")
            self.state._active_events["disaster"] = {
                "province_id": province.province_id,
                "loss_ratio": loss
            }
            self.state.log_event(
                f"无妄天灾: {province.name} 受灾，损失 {loss*100:.0f}%",
                extra={"type": "disaster", "province_id": province.province_id, "loss": loss}
            )
            return

        # 随机选择一种灾害（P0只有一种）
        disaster = random.choice(disasters)
        base_loss = disaster["base_loss"]
        mitigation_infra = disaster["mitigation_infra"]
        mitigation_factor = disaster["mitigation_factor"]

        # 获取行省基建等级
        infra_level = province.infrastructure.get(mitigation_infra, 0)
        # 计算实际损失比例
        loss = base_loss * (1 - infra_level * mitigation_factor)
        loss = max(0.0, min(1.0, loss))  # 限制在0~1之间

        print(f"         行省 {province.name} 遭受 {disaster['name']}，损失比例 {loss*100:.0f}%")
        if infra_level > 0:
            print(f"         基建 {mitigation_infra} 等级 {infra_level} 减免 {mitigation_factor*infra_level*100:.0f}%")

        # 存入 active_events
        self.state._active_events["disaster"] = {
            "province_id": province.province_id,
            "loss_ratio": loss
        }

        self.state.log_event(
            f"无妄天灾: {province.name} 受灾，损失 {loss*100:.0f}%",
            extra={"type": "disaster", "province_id": province.province_id, "loss": loss}
        )

    def _handle_mighty_man_event(self):
        """天降猛男：在广场阶段生成一位历史强力人物（或随机猛人）"""
        print(f"      🌟 天降猛男！一位非凡人物即将降临罗马")

        current_year = self.state.turn.year
        heroes = self._load_heroes()

        # 筛选符合当前年份且未出现过的历史人物
        available = []
        for hero in heroes:
            birth = hero["birth_year"]
            death = hero["death_year"]
            # 公元前年份为负数，例如 -236 表示公元前236年
            if birth + 16 <= current_year <= death:
                if hero["id"] not in self.state.spawned_hero_ids:
                    available.append(hero)

        if available:
            # 有历史人物可用，随机选择一个
            chosen = random.choice(available)
            self.state.hero_to_spawn = {
                "type": "historical",
                "data": chosen
            }
            print(f"         历史英雄 {chosen['name']} 将在广场阶段登场")
            self.state.log_event(
                f"天降猛男: 历史英雄 {chosen['name']} 选中",
                extra={"type": "mighty_man", "hero_id": chosen["id"], "name": chosen["name"]}
            )
        else:
            # 无历史人物，准备生成随机猛人
            self.state.hero_to_spawn = {"type": "random"}
            print(f"         无历史英雄可用，将生成一位随机猛人")
            self.state.log_event(
                "天降猛男: 无历史英雄，将生成随机猛人",
                extra={"type": "mighty_man", "subtype": "random"}
            )

        self.state.hero_spawned_this_turn = True

    def _load_heroes(self) -> List[Dict]:
        """从 heroes.json 加载英雄数据，如果文件不存在或解析失败则返回空列表"""
        import json
        from pathlib import Path
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / "heroes.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("heroes", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.state.log_event(f"英雄数据加载失败: {e}", level=logging.WARNING)
            return []

    def _handle_death_event(self):
        """死神来了：随机抽取死亡人数，财产归公，同时终止死亡人物的合同"""

        rules = self.state.config.get("mortality_rules", {})
        death_count = rules.get("death_count", 1)

        self.state.log_event(f"[DEBUG] death_count = {death_count}", level=logging.DEBUG)

        living = self.state.get_living_members()
        if not living:
            print("   😇 无存活人物，死神空手而归")
            return

        victims = random.sample(living, min(death_count, len(living)))

        for victim in victims:
            # 获取派系名称
            faction = self.state.get_faction(victim.faction_id)
            faction_name = faction.name if faction else "无派系"
            print(f"   💀 死神选中了 {victim.name} ({faction_name}) (阶级: {victim.class_tier.value})")

            # 终止该人物持有的所有活跃合同
            if victim.has_active_contract:
                for contract_id in victim.contract_ids:
                    contract = self.state.get_contract(contract_id)
                    if contract and contract.status == ContractStatus.ACTIVE:
                        contract.terminate()
                        province = self.state.get_province(contract.province_id)
                        if province:
                            if contract.contract_type == ContractType.TAX_FARMING:
                                province.unbind_tax_contract()
                            elif contract.contract_type == ContractType.PUBLIC_WORKS:
                                province.unbind_project_contract()
                        print(f"      📜 {victim.name} 的合同 {contract.name} 已终止")

            # 调用 mark_member_dead 统一处理资产回收
            self.state.mark_member_dead(victim.id, transfer_land=True, transfer_wealth=True)

            # ===== 新增日志 =====
            self.state.log_event(
                f"人物死亡: {victim.name} (ID:{victim.id})",
                extra={"type": "figure_death", "figure_id": victim.id, "name": victim.name}
            )

        self.state.log_event(f"💀 死神来了：{len(victims)} 人死亡，财产归公")

    def _handle_bountiful_harvest(self):
        """风调雨顺：本回合全国土地产出 +50%"""
        multiplier = self.state.config.get("mortality_rules.bumper_harvest_multiplier", 1.5)
        self.state._active_events["bumper_harvest"] = {"multiplier": multiplier}
        print(f"      🌾 风调雨顺！本回合全国土地产出 +{int((multiplier-1)*100)}%")
        self.state.log_event(
            "风调雨顺触发",
            extra={"type": "event", "event": "bountiful_harvest", "multiplier": multiplier}
        )

    def _handle_peace_event(self):
        """国泰民安：全国民变和战争威胁等级降为1（通过先置0，再经后续升级变为1）"""
        print(f"      🕊️ 国泰民安！全国民怨和战争威胁得到平息")

        # 1. 处理行省民怨：所有已征服行省 >0 的降为 0
        provinces = self.state.get_all_provinces()
        for province in provinces:
            if province.conquered and province.grievance > 0:
                old = province.grievance
                province.set_grievance(0)
                print(f"         行省 {province.name} 民怨从 {old} 降至 0")
                self.state.log_event(
                    f"国泰民安: {province.name} 民怨 {old}→0",
                    extra={"type": "peace_event", "province_id": province.province_id, "old": old, "new": 0}
                )

        # 2. 处理战争威胁：所有威胁战争等级 >0 的降为 0
        war_system = self.state.get_war_system()
        if war_system:
            # 通过公共方法获取威胁列表（需确保 WarSystem 有 get_threat_wars 方法）
            threat_wars = war_system.get_threat_wars() if hasattr(war_system, 'get_threat_wars') else []
            for war in threat_wars:
                if war.threat_level > 0:
                    old = war.threat_level
                    war.threat_level = 0
                    print(f"         战争 {war.name} 威胁等级从 {old} 降至 0")
                    self.state.log_event(
                        f"国泰民安: {war.name} 威胁等级 {old}→0",
                        extra={"type": "peace_event", "war_id": war.id, "old": old, "new": 0}
                    )

        self.state.log_event(
            "国泰民安触发",
            extra={"type": "event", "event": "peace"}
        )