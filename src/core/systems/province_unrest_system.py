"""
Province Unrest System — Province civil unrest detection and rebellion creation (C-09c).

Extracted from CLI phase_forum._update_civil_unrest() to provide a single
source of truth for unrest detection, reusable by both CLI and future GUI.

Debug Logging Requirement (SA-Development-Task §A5):
  Every province gets a DBUG-level log_event() output.
  Rebellion creation gets an INFO-level log_event() output.
"""

import logging
from typing import Any, Dict, List, TYPE_CHECKING

from src.core.entities.contract import ContractType, ContractStatus

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.war import War


class ProvinceUnrestSystem:
    """行省民变检测系统。

    检测各省的民怨水平，达到阈值时创建 Rebellion 实体。
    独立 System，不挂载到 GameState。
    """

    def __init__(self, game_state: "GameState"):
        self._game_state = game_state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_and_trigger_unrest(self) -> Dict[str, Any]:
        """检测所有行省的民变状态。

        遍历各省 → 计算民怨阈值 → 达到阈值则创建起义。

        业务逻辑（从 CLI _update_civil_unrest 提取）:
          1. 意大利本土：长期未分地或民怨升级检查
          2. 行省：民怨自动升级 + 包税合同实际税率触发 + 起义检测

        Returns:
            dict: {
                "rebellions": List[War] — 新创建的起义列表,
                "province_updates": List[dict] — 每省民怨变化详情,
            }
        """
        if not self._game_state.config.get("enable_threats", True):
            return {"rebellions": [], "province_updates": []}

        base_tax_rate = self._game_state.get_economic_rule("province_tax_rate", 0.1)
        italy_unrest_trigger = self._game_state.config.get(
            "economic_rules.italy_unrest_trigger_turns", 3
        )
        land_price = self._game_state.get_economic_rule("land_price_per_unit", 10)
        private_income_rate = self._game_state.get_economic_rule(
            "private_land_income_rate", 0.05
        )

        provinces = self._game_state.get_all_provinces()
        if not provinces:
            return {"rebellions": [], "province_updates": []}

        # 索引活跃包税合同按行省
        active_contracts = [
            c
            for c in self._game_state.contracts
            if c.status == ContractStatus.ACTIVE
            and c.contract_type == ContractType.TAX_FARMING
        ]
        province_contracts: dict = {}
        for contract in active_contracts:
            pid = contract.province_id
            if pid == 0:
                continue
            province_contracts.setdefault(pid, []).append(contract)

        new_rebellions: List["War"] = []
        province_updates: List[Dict[str, Any]] = []

        # ---------- 意大利本土 ----------
        italy = self._game_state.get_province(0)
        war_system = self._game_state.get_war_system()

        if italy:
            old_grievance = italy.grievance
            italy_reason = "no_change"
            if old_grievance == 0:
                italy._turns_since_last_land_distribution += 1
                if italy._turns_since_last_land_distribution >= italy_unrest_trigger:
                    italy.set_grievance(1)
                    italy_reason = "italy_no_distribution"
                    self._game_state.log_event(
                        f"Province {italy.name}: unrest=1, threshold triggered "
                        f"(turns since distribution={italy._turns_since_last_land_distribution}), "
                        f"will_rebel=False",
                        level=logging.DEBUG,
                        extra={
                            "province_id": italy.province_id,
                            "grievance": 1,
                            "reason": "italy_no_land_distribution",
                        },
                    )
            elif 0 < old_grievance < 3:
                italy.set_grievance(old_grievance + 1)
                italy_reason = "auto_escalation"
                self._game_state.log_event(
                    f"Province {italy.name}: unrest={italy.grievance}, "
                    f"threshold=3, will_rebel={italy.grievance >= 3}",
                    level=logging.DEBUG,
                    extra={
                        "province_id": italy.province_id,
                        "grievance": italy.grievance,
                        "reason": italy_reason,
                    },
                )
                if italy.grievance == 3:
                    rebellion = self._create_rebellion(italy, war_system)
                    if rebellion:
                        new_rebellions.append(rebellion)

            # 即使未变化也记录DBUG
            if old_grievance == italy.grievance and old_grievance == 0:
                self._game_state.log_event(
                    f"Province {italy.name}: unrest={italy.grievance}, threshold=3, "
                    f"will_rebel=False",
                    level=logging.DEBUG,
                    extra={"province_id": italy.province_id, "grievance": 0},
                )

            province_updates.append({
                "province_id": italy.province_id,
                "name": italy.name,
                "old_grievance": old_grievance,
                "new_grievance": italy.grievance,
                "reason": italy_reason,
            })

        # ---------- 行省处理 ----------
        for province in provinces:
            if province.province_id == 0:
                continue

            old_grievance = province.grievance
            will_rebel = False
            province_reason = "no_change"

            # 起义检测（民怨>=3 且未爆发）
            if province.grievance >= 3 and not province.event_flags.get(
                "rebellion_active"
            ):
                will_rebel = True
                rebellion = self._create_rebellion(province, war_system)
                province_reason = "just_revolted"
                if rebellion:
                    new_rebellions.append(rebellion)

            # 自动升级
            if 0 < province.grievance < 3:
                province.set_grievance(province.grievance + 1)
                province_reason = "auto_escalation"

            # 包税合同实际税率触发
            contracts = province_contracts.get(province.province_id, [])
            for contract in contracts:
                land_value = province.land_private * land_price
                expected_income = int(land_value * private_income_rate)
                if expected_income <= 0:
                    continue
                total_collected = contract.contract_price * (
                    1 + contract.profit_rate
                )
                actual_tax_rate = total_collected / expected_income
                if actual_tax_rate > base_tax_rate:
                    if province.grievance < 1:
                        province.set_grievance(1)
                        province_reason = "tax_trigger"

            # 已起义标记检测（已有 rebellion_active 但未触发新创建）
            if old_grievance >= 3 and province.event_flags.get("rebellion_active") and not will_rebel:
                province_reason = "active_rebellion"

            # DBUG 日志：每省民怨
            self._game_state.log_event(
                f"Province {province.name}: unrest={province.grievance}, "
                f"threshold=3, will_rebel={will_rebel}",
                level=logging.DEBUG,
                extra={
                    "province_id": province.province_id,
                    "grievance": province.grievance,
                    "will_rebel": will_rebel,
                },
            )

            province_updates.append({
                "province_id": province.province_id,
                "name": province.name,
                "old_grievance": old_grievance,
                "new_grievance": province.grievance,
                "reason": province_reason,
            })

        return {
            "rebellions": new_rebellions,
            "province_updates": province_updates,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_rebellion(
        self, province, war_system
    ) -> "War":
        """为行省创建起义战争并注册，返回 War 对象。"""
        if not war_system:
            return None
        rebellion_war = war_system.create_rebellion_war(province)
        if war_system.register_rebellion_war(rebellion_war):
            province.set_event_flag("rebellion_active", True)
            self._game_state.log_event(
                f"Rebellion created: {rebellion_war.id} in province {province.name}",
                level=logging.INFO,
                extra={
                    "type": "rebellion",
                    "war_id": rebellion_war.id,
                    "province_id": province.province_id,
                    "province_name": province.name,
                },
            )
            return rebellion_war
        return None
