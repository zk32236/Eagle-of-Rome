"""收入阶段经济结算服务。"""
import logging
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

from src.core.entities.contract import ContractStatus, ContractType

if TYPE_CHECKING:
    from src.core.game_state import GameState


class EconomicService:
    """承接收入阶段核心经济规则，UI 层只负责展示服务返回的结算单。"""

    def __init__(self, state: "GameState"):
        self.state = state

    def settle_revenue_phase(self) -> Dict[str, Any]:
        starting_treasury = self.state.treasury
        errors: List[str] = []
        debug_events: List[Dict[str, Any]] = []
        faction_tax_collected, faction_stipend = self._init_faction_income_maps()
        tax_rate = self.state.get_economic_rule("faction_tax_rate", 0.1)

        try:
            data = {
                "starting_treasury": starting_treasury,
                "ending_treasury": starting_treasury,
                "treasury_delta": 0,
                "indemnities": self.settle_indemnities(),
                "national_opex": self.deduct_national_opex(),
                "public_land_income": self.collect_public_land_income(),
                "private_land_rows": self.collect_private_land_income(faction_tax_collected, tax_rate),
                "contract_rows": self.collect_contract_revenues(faction_tax_collected, tax_rate),
                "warranty_rows": self.process_contract_warranty(),
                "maintenance": {
                    "military": self.apply_military_maintenance(),
                    "naval": self.apply_naval_maintenance(),
                },
                "faction_rows": self.apply_faction_income(faction_tax_collected, faction_stipend),
                "debug_events": debug_events,
            }
            data["ending_treasury"] = self.state.treasury
            data["treasury_delta"] = data["ending_treasury"] - starting_treasury
            return {"success": True, "message": "revenue phase settled", "data": data, "errors": errors}
        except Exception as exc:
            errors.append(str(exc))
            if hasattr(self.state, "log_exception"):
                self.state.log_exception(exc, context="收入阶段经济结算失败")
            return {
                "success": False,
                "message": "revenue phase settlement failed",
                "data": {
                    "starting_treasury": starting_treasury,
                    "ending_treasury": self.state.treasury,
                    "treasury_delta": self.state.treasury - starting_treasury,
                    "indemnities": [],
                    "national_opex": {},
                    "public_land_income": {},
                    "private_land_rows": [],
                    "contract_rows": [],
                    "warranty_rows": [],
                    "maintenance": {"military": {}, "naval": {}},
                    "faction_rows": {},
                    "debug_events": debug_events,
                },
                "errors": errors,
            }

    def settle_indemnities(self) -> List[Dict[str, Any]]:
        rows = []
        war_system = self.state.get_war_system()
        if not war_system:
            return rows

        for war in self._get_wars_with_indemnity(war_system):
            amount = getattr(war, "indemnity_due", 0)
            if amount == 0:
                continue

            if amount > 0:
                self.state.add_treasury(amount)
                self.state.log_event(
                    f"战争赔款收入: {war.name} +{amount}",
                    extra={"type": "indemnity_income", "war_id": war.id, "amount": amount}
                )
                war.set_indemnity_due(0)
                rows.append({
                    "war_id": war.id,
                    "name": war.name,
                    "amount": amount,
                    "kind": "income",
                    "cleared": True,
                    "treasury_after": self.state.treasury,
                })
                continue

            due = -amount
            if self.state.treasury < due:
                self.state.log_event(
                    "国库不足支付赔款，共和覆灭",
                    extra={"type": "game_over", "reason": "indemnity", "war_id": war.id, "amount": due},
                    level=logging.CRITICAL
                )
                rows.append({
                    "war_id": war.id,
                    "name": war.name,
                    "amount": amount,
                    "kind": "insufficient",
                    "cleared": False,
                    "treasury_after": self.state.treasury,
                })
            else:
                self.state.add_treasury(amount)
                self.state.log_event(
                    f"战争赔款支出: {war.name} {due}",
                    extra={"type": "indemnity_expense", "war_id": war.id, "amount": due}
                )
                war.set_indemnity_due(0)
                rows.append({
                    "war_id": war.id,
                    "name": war.name,
                    "amount": amount,
                    "kind": "expense",
                    "cleared": True,
                    "treasury_after": self.state.treasury,
                })
        return rows

    def deduct_national_opex(self) -> Dict[str, Any]:
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        rate = self.state.get_economic_rule("national_opex_rate", 0.003)
        conquered = [p for p in self.state.get_all_provinces() if p.conquered]
        total_land = sum(p.total_land for p in conquered)
        opex = int(total_land * land_price * rate)

        if opex > 0:
            self.state.add_treasury(-opex)
            self.state.log_event(
                f"国家运营费扣除: {opex} Talents",
                extra={
                    "type": "national_opex",
                    "amount": opex,
                    "treasury_after": self.state.treasury,
                    "total_land": total_land,
                    "land_price": land_price,
                    "rate": rate,
                }
            )
        else:
            # 无行省/无运营费变体日志
            self.state.log_event(
                f"国家运营费: 无需扣除（无行省）",
                extra={
                    "type": "national_opex_no_provinces",
                    "total_land": total_land,
                    "amount": 0,
                }
            )

        return {
            "amount": opex,
            "total_land": total_land,
            "land_price": land_price,
            "rate": rate,
            "treasury_after": self.state.treasury,
            "provinces": [{"id": p.province_id, "name": p.name, "total_land": p.total_land} for p in conquered],
        }

    def collect_public_land_income(self) -> Dict[str, Any]:
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        public_income_rate = self.state.get_economic_rule("public_land_income_rate", 0.01)
        national_tax_rate = self.state.get_economic_rule("national_public_land_tax_rate", 0.02)
        national_land = self.state.get_national_public_land()
        tax_income = int(round(national_land * land_price * public_income_rate * national_tax_rate))
        modifiers = []
        events = self._active_events()

        if "bumper_harvest" in events:
            multiplier = events["bumper_harvest"]["multiplier"]
            tax_income = int(round(tax_income * multiplier))
            modifiers.append({"type": "bumper_harvest", "multiplier": multiplier})

        if "disaster" in events:
            disaster_info = events["disaster"]
            if disaster_info["province_id"] == 0:
                loss_ratio = disaster_info["loss_ratio"]
                tax_income = int(round(tax_income * (1 - loss_ratio)))
                modifiers.append({"type": "disaster", "loss_ratio": loss_ratio})

        self.state.add_treasury(tax_income)
        self.state.log_event(
            f"国家公地收益: +{tax_income}",
            extra={"type": "public_land_income", "amount": tax_income, "treasury_after": self.state.treasury}
        )
        return {
            "amount": tax_income,
            "national_land": national_land,
            "land_price": land_price,
            "public_income_rate": public_income_rate,
            "national_tax_rate": national_tax_rate,
            "modifiers": modifiers,
            "treasury_after": self.state.treasury,
        }

    def collect_private_land_income(
            self,
            faction_tax_collected: Dict[str, float],
            tax_rate: float
    ) -> List[Dict[str, Any]]:
        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
        rate = self.state.get_economic_rule("private_land_income_rate", 0.05)
        events = self._active_events()
        multiplier = events.get("bumper_harvest", {}).get("multiplier", 1.0)
        disaster_loss = 1.0
        if "disaster" in events and events["disaster"].get("province_id") == 0:
            disaster_loss = 1.0 - events["disaster"].get("loss_ratio", 0)

        rows = []
        for fig in self.state.get_living_members():
            try:
                if fig.land_private <= 0:
                    continue
                income_float = fig.land_private * land_price * rate * multiplier * disaster_loss
                if income_float <= 0:
                    continue

                tax_float = income_float * tax_rate
                net_income_int = int(round(income_float - tax_float))
                if net_income_int > 0:
                    fig.add_wealth(net_income_int)
                    if fig.faction_id and fig.faction_id in faction_tax_collected:
                        faction_tax_collected[fig.faction_id] += tax_float
                    rows.append({
                        "figure_id": fig.id,
                        "name": fig.get_formal_name(),
                        "income": net_income_int,
                        "wealth": fig.wealth,
                    })
            except Exception as exc:
                self.state.log_exception(
                    exc,
                    context=f"私地收益处理失败: 人物 {fig.id} {fig.name}",
                    extra={"figure_id": fig.id, "land_private": fig.land_private}
                )
        return rows

    def collect_contract_revenues(
            self,
            faction_tax_collected: Dict[str, float],
            tax_rate: float
    ) -> List[Dict[str, Any]]:
        rows = []
        active_contracts = [c for c in self._get_contracts() if c.status == ContractStatus.ACTIVE]
        for contract in active_contracts:
            try:
                if contract.contract_type == ContractType.TAX_FARMING:
                    row = self._settle_tax_farming_contract(contract, faction_tax_collected, tax_rate)
                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    row = self._settle_public_works_contract(contract, faction_tax_collected, tax_rate)
                else:
                    row = None
                if row:
                    rows.append(row)
            except Exception as exc:
                self.state.log_exception(
                    exc,
                    context=f"合同收益处理失败: 合同 {contract.id}",
                    extra={"contract_id": contract.id, "contract_type": contract.contract_type.value}
                )
        return rows

    def process_contract_warranty(self) -> List[Dict[str, Any]]:
        rows = []
        for contract in self._get_contracts():
            if contract.status != ContractStatus.COMPLETED or contract.warranty_remaining <= 0:
                continue
            before = contract.warranty_remaining
            after = contract.advance_warranty()
            expired = after <= 0
            if expired:
                self.state.log_event(
                    f"工程合同质保期结束: {contract.name}",
                    extra={"type": "warranty_expired", "contract_id": contract.id}
                )
            rows.append({"contract_id": contract.id, "name": contract.name, "before": before, "after": after, "expired": expired})
        return rows

    def apply_military_maintenance(self) -> Dict[str, Any]:
        military_system = self.state.get_military_system()
        if not military_system:
            return {"available": False, "total": 0, "success": True, "message": ""}
        total_maintenance, _ = military_system.calculate_maintenance()
        success, msg = military_system.apply_maintenance(verbose=False)
        return {"available": True, "total": total_maintenance, "success": success, "message": msg}

    def apply_naval_maintenance(self) -> Dict[str, Any]:
        naval_system = getattr(self.state, "naval_system", None)
        if not naval_system:
            return {"available": False, "total": 0, "success": True, "message": "警告：naval_system 为 None，跳过舰队维护费"}
        total = naval_system.calculate_maintenance() if hasattr(naval_system, "calculate_maintenance") else 0
        success, msg = naval_system.apply_maintenance()
        return {"available": True, "total": total, "success": success, "message": msg}

    def apply_faction_income(
            self,
            faction_tax_collected: Dict[str, float],
            faction_stipend: Dict[str, int]
    ) -> Dict[str, Dict[str, int]]:
        faction_rows = {}
        for faction_id, total_tax_float in faction_tax_collected.items():
            tax_int = int(round(total_tax_float))
            stipend = faction_stipend.get(faction_id, 0)
            faction = self.state.get_faction(faction_id)
            if not faction:
                continue
            self.state.add_faction_treasury(faction_id, stipend + tax_int)
            if tax_int > 0:
                self.state.log_event(
                    f"派系抽成: {faction.name} +{tax_int}",
                    extra={"type": "faction_tax", "faction_id": faction_id, "amount": tax_int}
                )
            if stipend > 0:
                self.state.log_event(
                    f"派系津贴: {faction.name} +{stipend}",
                    extra={"type": "faction_stipend", "faction_id": faction_id, "amount": stipend}
                )
            faction_rows[faction_id] = {"stipend": stipend, "tax": tax_int, "final": faction.treasury}
        return faction_rows

    def _settle_tax_farming_contract(
            self,
            contract,
            faction_tax_collected: Dict[str, float],
            tax_rate: float
    ) -> Dict[str, Any]:
        winning_bid = contract.winning_bid
        if not winning_bid:
            return {}
        figure = self.state.get_member(winning_bid["bidder_id"])
        if not figure or figure.is_dead:
            contract.terminate()
            province = self.state.get_province(contract.province_id)
            if province:
                province.unbind_tax_contract()
            return {"contract_id": contract.id, "type": "tax_farming", "terminated": True}

        contract_price = contract.contract_price
        gross_profit = int(contract_price * contract.profit_rate)
        tax_float = gross_profit * tax_rate
        tax_int = int(round(tax_float))
        net_profit = gross_profit - tax_int

        self.state.add_treasury(contract_price)
        figure.add_wealth(net_profit)
        contract.record_tax_collection(contract_price)
        if figure.faction_id and figure.faction_id in faction_tax_collected:
            faction_tax_collected[figure.faction_id] += tax_float

        completed = False
        if contract.remaining_years > 0:
            contract.remaining_years -= 1
            if contract.remaining_years == 0:
                contract.mark_complete(self.state.turn.turn_number)
                province = self.state.get_province(contract.province_id)
                if province:
                    province.unbind_tax_contract()
                completed = True

        self.state.log_event(
            f"包税合同收益: {figure.name} 净得 {net_profit}，国库 +{contract_price}",
            extra={
                "type": "tax_contract_revenue",
                "contract_id": contract.id,
                "figure_id": figure.id,
                "net_profit": net_profit,
                "treasury_gain": contract_price,
            }
        )
        return {
            "contract_id": contract.id,
            "type": "tax_farming",
            "figure_id": figure.id,
            "net_profit": net_profit,
            "treasury_gain": contract_price,
            "completed": completed,
        }

    def _settle_public_works_contract(
            self,
            contract,
            faction_tax_collected: Dict[str, float],
            tax_rate: float
    ) -> Dict[str, Any]:
        figure = self.state.get_member(contract.awarded_to)
        if not figure or figure.is_dead:
            contract.terminate()
            province = self.state.get_province(contract.province_id)
            if province:
                province.unbind_project_contract()
            return {"contract_id": contract.id, "type": "public_works", "terminated": True}

        if contract.remaining_years <= 0:
            return {}

        payment = contract.base_cost - contract.total_spent if contract.remaining_years == 1 else contract.annual_income
        cost = contract.annual_cost
        profit_float = float(payment - cost)
        tax_float = profit_float * tax_rate if profit_float > 0 else 0.0
        tax_int = int(round(tax_float))
        knight_net_gain = int(round(profit_float - tax_float))

        self.state.add_treasury(-payment)
        figure.add_wealth(knight_net_gain)
        contract.record_works_payment(payment)
        contract.remaining_years -= 1
        if figure.faction_id and figure.faction_id in faction_tax_collected:
            faction_tax_collected[figure.faction_id] += tax_float

        self.state.log_event(
            f"工程合同 {contract.id} 收益: 支付 {payment}, 成本 {cost}, 利润 {profit_float}, 税收 {tax_int}, 骑士净得 {knight_net_gain}",
            level=logging.DEBUG
        )

        completed = False
        fleet_payment_done = False
        if contract.remaining_years <= 0:
            if contract.is_fleet_construction:
                contract.mark_fleet_construction_paid()
                fleet_payment_done = True
            else:
                contract.mark_complete(self.state.turn.turn_number)
                province = self.state.get_province(contract.province_id)
                if province:
                    province.unbind_project_contract()
                self.state.log_event(
                    f"工程合同竣工: {contract.name}",
                    extra={"type": "works_contract_complete", "contract_id": contract.id}
                )
                completed = True

        return {
            "contract_id": contract.id,
            "type": "public_works",
            "figure_id": figure.id,
            "payment": payment,
            "cost": cost,
            "tax": tax_int,
            "net_profit": knight_net_gain,
            "completed": completed,
            "fleet_payment_done": fleet_payment_done,
        }

    def _init_faction_income_maps(self) -> Tuple[Dict[str, float], Dict[str, int]]:
        stipend = self.state.get_economic_rule("faction_stipend", 10)
        faction_tax_collected: Dict[str, float] = {}
        faction_stipend: Dict[str, int] = {}
        for faction in self.state.factions.values():
            faction_tax_collected[faction.id] = 0.0
            faction_stipend[faction.id] = stipend
        return faction_tax_collected, faction_stipend

    def _active_events(self) -> Dict[str, Any]:
        events = getattr(self.state, "active_events", None)
        if isinstance(events, dict):
            return events
        fallback = getattr(self.state, "_active_events", {})
        return fallback if isinstance(fallback, dict) else {}

    def _get_contracts(self):
        if hasattr(self.state, "get_all_contracts"):
            return self.state.get_all_contracts()
        return list(getattr(self.state, "contracts", []))

    def _get_wars_with_indemnity(self, war_system) -> List[Any]:
        for method_name in ("get_wars_with_indemnity_due", "get_all_wars"):
            method = getattr(war_system, method_name, None)
            if not callable(method):
                continue
            try:
                wars = list(method())
            except TypeError:
                wars = []
            if wars:
                return [war for war in self._dedupe_wars(wars) if getattr(war, "indemnity_due", 0) != 0]
        return []

    def _dedupe_wars(self, wars: List[Any]) -> List[Any]:
        seen = set()
        result = []
        for war in wars:
            key = getattr(war, "id", id(war))
            if key in seen:
                continue
            seen.add(key)
            result.append(war)
        return result
