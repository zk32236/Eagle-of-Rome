"""
MortalityService - 天命阶段核心规则服务。

服务层承载天命事件抽取和效果应用；CLI/API/GUI 只消费结构化结果。
"""
import json
import logging
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.core.entities.contract import ContractStatus, ContractType


DataLoader = Callable[[], List[Dict[str, Any]]]


class MortalityService:
    """执行天命阶段规则并返回结构化结果。"""

    PHASE_ID = "mortality"
    NEXT_PHASE_ID = "revenue"

    def __init__(
        self,
        state,
        disaster_loader: Optional[DataLoader] = None,
        hero_loader: Optional[DataLoader] = None,
    ):
        self.state = state
        self._disaster_loader = disaster_loader or self._load_disasters
        self._hero_loader = hero_loader or self._load_heroes

    def execute(self, mark_phase: bool = True) -> Dict[str, Any]:
        rules = self.state.config.get("mortality_rules", {})
        deck = rules.get("event_deck", [])
        draw_count = rules.get("event_draw_count", 1)
        events: List[Dict[str, Any]] = []

        if not deck:
            if mark_phase:
                self.state.mark_phase_executed(self.PHASE_ID)
            return {
                "events": [{
                    "name": "未配置事件卡",
                    "effect": "none",
                    "summary": "未配置事件卡，天命阶段直接完成。",
                    "impacts": [],
                    "logs": ["   ⚠️ 未配置事件卡"],
                }],
                "phase_executed": self.state.is_phase_executed(self.PHASE_ID),
                "next_phase_id": self.NEXT_PHASE_ID,
            }

        weights = [e.get("weight", 1) for e in deck]
        if sum(weights) == 0:
            weights = [1] * len(deck)

        drawn_events = random.choices(deck, weights=weights, k=draw_count)
        for event in drawn_events:
            name = event.get("name", "未知事件")
            effect = event.get("effect", "unknown")
            result = self._apply_event(name, effect)
            events.append(result)

        if mark_phase:
            self.state.mark_phase_executed(self.PHASE_ID)

        return {
            "events": events,
            "phase_executed": self.state.is_phase_executed(self.PHASE_ID),
            "next_phase_id": self.NEXT_PHASE_ID,
        }

    def apply_death_event(self) -> Dict[str, Any]:
        return self._handle_death_event("死神来了")

    def apply_bountiful_harvest(self) -> Dict[str, Any]:
        return self._handle_bountiful_harvest("风调雨顺")

    def apply_peace_event(self) -> Dict[str, Any]:
        return self._handle_peace_event("国泰民安")

    def apply_mighty_man_event(self) -> Dict[str, Any]:
        return self._handle_mighty_man_event("天降猛男")

    def apply_disaster_event(self) -> Dict[str, Any]:
        return self._handle_disaster_event("无妄天灾")

    def _apply_event(self, event_name: str, effect: str) -> Dict[str, Any]:
        if effect == "death":
            return self._handle_death_event(event_name)
        if effect == "bountiful_harvest":
            return self._handle_bountiful_harvest(event_name)
        if effect == "peace":
            return self._handle_peace_event(event_name)
        if effect == "mighty_man":
            return self._handle_mighty_man_event(event_name)
        if effect == "disaster":
            return self._handle_disaster_event(event_name)

        self.state.log_event(f"{event_name}")
        return {
            "name": event_name,
            "effect": effect or "unknown",
            "summary": "效果暂未实现。",
            "impacts": [],
            "logs": ["      (效果暂未实现)"],
        }

    def _handle_death_event(self, event_name: str) -> Dict[str, Any]:
        rules = self.state.config.get("mortality_rules", {})
        death_count = rules.get("death_count", 1)
        logs: List[str] = []
        impacts: List[Dict[str, Any]] = []

        self.state.log_event(f"[DEBUG] death_count = {death_count}", level=logging.DEBUG)
        living = self.state.get_living_members()
        if not living:
            logs.append("   😇 无存活人物，死神空手而归")
            self.state.log_event(
                f"死神来了: 无存活人物",
                extra={
                    "type": "figure_death_no_victims",
                    "event_name": event_name,
                    "death_count": death_count,
                }
            )
            return {
                "name": event_name,
                "effect": "death",
                "summary": "无存活人物，死神空手而归。",
                "impacts": impacts,
                "logs": logs,
            }

        victims = random.sample(living, min(death_count, len(living)))
        for victim in victims:
            faction = self.state.get_faction(victim.faction_id)
            faction_name = faction.name if faction else "无派系"
            logs.append(
                f"   💀 死神选中了 {victim.name} ({faction_name}) "
                f"(阶级: {victim.class_tier.value})"
            )

            terminated_contracts = []
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
                        terminated_contracts.append({
                            "contract_id": contract.id,
                            "contract_name": contract.name,
                        })
                        logs.append(f"      📜 {victim.name} 的合同 {contract.name} 已终止")

            self.state.mark_member_dead(victim.id, transfer_land=True, transfer_wealth=True)
            faction = self.state.get_faction(victim.faction_id)
            faction_name = faction.name if faction else "无派系"
            self.state.log_event(
                f"人物死亡: {victim.name} (ID:{victim.id})",
                extra={
                    "type": "figure_death",
                    "figure_id": victim.id,
                    "name": victim.name,
                    "faction_id": victim.faction_id,
                    "faction_name": faction_name,
                    "class_tier": victim.class_tier.value,
                    "terminated_contracts_count": len(terminated_contracts),
                }
            )
            impacts.append({
                "type": "figure_death",
                "figure_id": victim.id,
                "figure_name": victim.name,
                "faction_id": victim.faction_id,
                "faction_name": faction_name,
                "terminated_contracts": terminated_contracts,
            })

        self.state.log_event(f"💀 死神来了：{len(victims)} 人死亡，财产归公")
        return {
            "name": event_name,
            "effect": "death",
            "summary": f"{len(victims)} 人死亡，财产归公。",
            "impacts": impacts,
            "logs": logs,
        }

    def _handle_bountiful_harvest(self, event_name: str) -> Dict[str, Any]:
        multiplier = self.state.config.get("mortality_rules.bumper_harvest_multiplier", 1.5)
        self.state.record_active_event("bumper_harvest", {"multiplier": multiplier})
        bonus = int((multiplier - 1) * 100)
        self.state.log_event(
            "风调雨顺触发",
            extra={
                "type": "bumper_harvest_triggered",
                "multiplier": multiplier,
                "bonus_percent": bonus,
                "turn": self.state.turn.turn_number,
            }
        )
        return {
            "name": event_name,
            "effect": "bountiful_harvest",
            "summary": f"本回合全国土地产出 +{bonus}%。",
            "impacts": [{"type": "active_event", "key": "bumper_harvest", "multiplier": multiplier}],
            "logs": [f"      🌾 风调雨顺！本回合全国土地产出 +{bonus}%"],
        }

    def _handle_peace_event(self, event_name: str) -> Dict[str, Any]:
        logs = ["      🕊️ 国泰民安！全国民怨和战争威胁得到平息"]
        impacts: List[Dict[str, Any]] = []

        for province in self.state.get_all_provinces():
            if province.conquered and province.grievance > 0:
                old = province.grievance
                province.set_grievance(0)
                logs.append(f"         行省 {province.name} 民怨从 {old} 降至 0")
                impacts.append({
                    "type": "province_grievance",
                    "province_id": province.province_id,
                    "province_name": province.name,
                    "old": old,
                    "new": 0,
                })
                self.state.log_event(
                    f"国泰民安: {province.name} 民怨 {old}→0",
                    extra={
                        "type": "peace_event_grievance_cleared",
                        "province_id": province.province_id,
                        "province_name": province.name,
                        "old": old,
                        "new": 0,
                    }
                )

        war_system = self.state.get_war_system()
        if war_system:
            threat_wars = war_system.get_threat_wars() if hasattr(war_system, "get_threat_wars") else []
            for war in threat_wars:
                if war.threat_level > 0:
                    old = war.threat_level
                    war.threat_level = 0
                    logs.append(f"         战争 {war.name} 威胁等级从 {old} 降至 0")
                    impacts.append({
                        "type": "war_threat",
                        "war_id": war.id,
                        "war_name": war.name,
                        "old": old,
                        "new": 0,
                    })
                    self.state.log_event(
                        f"国泰民安: {war.name} 威胁等级 {old}→0",
                        extra={
                            "type": "peace_event_threat_cleared",
                            "war_id": war.id,
                            "war_name": war.name,
                            "old": old,
                            "new": 0,
                        }
                    )

        self.state.log_event("国泰民安触发", extra={"type": "event", "event": "peace"})
        return {
            "name": event_name,
            "effect": "peace",
            "summary": "已平息已征服行省民怨与战争威胁。",
            "impacts": impacts,
            "logs": logs,
        }

    def _handle_mighty_man_event(self, event_name: str) -> Dict[str, Any]:
        logs = ["      🌟 天降猛男！一位非凡人物即将降临罗马"]
        current_year = self.state.turn.year
        heroes = self._hero_loader()
        available = []
        for hero in heroes:
            birth = hero["birth_year"]
            death = hero["death_year"]
            if birth + 16 <= current_year <= death:
                if hero["id"] not in self.state.spawned_hero_ids:
                    available.append(hero)

        if available:
            chosen = random.choice(available)
            self.state.hero_to_spawn = {"type": "historical", "data": chosen}
            logs.append(f"         历史英雄 {chosen['name']} 将在广场阶段登场")
            summary = f"历史英雄 {chosen['name']} 将在广场阶段登场。"
            impact = {"type": "hero_spawn", "subtype": "historical", "hero_id": chosen["id"], "name": chosen["name"]}
            self.state.log_event(
                f"天降猛男: 历史英雄 {chosen['name']} 选中",
                extra={
                    "type": "hero_historical_spawned",
                    "hero_id": chosen["id"],
                    "hero_name": chosen["name"],
                    "birth_year": chosen.get("birth_year"),
                    "death_year": chosen.get("death_year"),
                    "current_year": current_year,
                }
            )
        else:
            self.state.hero_to_spawn = {"type": "random"}
            logs.append("         无历史英雄可用，将生成一位随机猛人")
            summary = "无历史英雄可用，将在广场阶段生成一位随机猛人。"
            impact = {"type": "hero_spawn", "subtype": "random"}
            self.state.log_event(
                "天降猛男: 无历史英雄，将生成随机猛人",
                extra={
                    "type": "hero_random_fallback",
                    "current_year": current_year,
                    "available_hero_count": len(available),
                }
            )

        self.state.hero_spawned_this_turn = True
        return {
            "name": event_name,
            "effect": "mighty_man",
            "summary": summary,
            "impacts": [impact],
            "logs": logs,
        }

    def _handle_disaster_event(self, event_name: str) -> Dict[str, Any]:
        logs = ["      🌪️ 无妄天灾！一场灾难降临罗马"]
        provinces = [p for p in self.state.get_all_provinces() if p.conquered]
        if not provinces:
            logs.append("         没有已征服行省，天灾无处降临")
            return {
                "name": event_name,
                "effect": "disaster",
                "summary": "没有已征服行省，天灾无处降临。",
                "impacts": [],
                "logs": logs,
            }

        province = random.choice(provinces)
        disasters = self._disaster_loader()
        if not disasters:
            loss = self.state.config.get("mortality_rules.disaster_base_loss", 0.5)
            logs.append(f"         行省 {province.name} 受灾，损失比例 {loss*100:.0f}%")
            self.state.record_active_event(
                "disaster",
                {"province_id": province.province_id, "loss_ratio": loss}
            )
            self.state.log_event(
                f"无妄天灾: {province.name} 受灾，损失 {loss*100:.0f}%",
                extra={
                    "type": "disaster_triggered",
                    "province_id": province.province_id,
                    "province_name": province.name,
                    "loss_ratio": loss,
                    "disaster_name": disaster['name'] if disasters else None,
                }
            )
            return {
                "name": event_name,
                "effect": "disaster",
                "summary": f"{province.name} 受灾，收入损失 {loss*100:.0f}%。",
                "impacts": [{
                    "type": "disaster",
                    "province_id": province.province_id,
                    "province_name": province.name,
                    "loss_ratio": loss,
                }],
                "logs": logs,
            }

        disaster = random.choice(disasters)
        base_loss = disaster["base_loss"]
        mitigation_infra = disaster["mitigation_infra"]
        mitigation_factor = disaster["mitigation_factor"]
        infra_level = province.infrastructure.get(mitigation_infra, 0)
        loss = base_loss * (1 - infra_level * mitigation_factor)
        loss = max(0.0, min(1.0, loss))

        logs.append(f"         行省 {province.name} 遭受 {disaster['name']}，损失比例 {loss*100:.0f}%")
        if infra_level > 0:
            logs.append(
                f"         基建 {mitigation_infra} 等级 {infra_level} "
                f"减免 {mitigation_factor*infra_level*100:.0f}%"
            )

        self.state.record_active_event(
            "disaster",
            {"province_id": province.province_id, "loss_ratio": loss}
        )
        self.state.log_event(
            f"无妄天灾: {province.name} 受灾，损失 {loss*100:.0f}%",
            extra={"type": "disaster", "province_id": province.province_id, "loss": loss}
        )
        return {
            "name": event_name,
            "effect": "disaster",
            "summary": f"{province.name} 遭受 {disaster['name']}，收入损失 {loss*100:.0f}%。",
            "impacts": [{
                "type": "disaster",
                "province_id": province.province_id,
                "province_name": province.name,
                "disaster_name": disaster["name"],
                "loss_ratio": loss,
            }],
            "logs": logs,
        }

    def _load_disasters(self) -> List[Dict[str, Any]]:
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / "disasters.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("disasters", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.state.log_event(f"灾害数据加载失败: {e}", level=logging.WARNING)
            return []

    def _load_heroes(self) -> List[Dict[str, Any]]:
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / "heroes.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("heroes", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.state.log_event(f"英雄数据加载失败: {e}", level=logging.WARNING)
            return []
