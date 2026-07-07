# src/api/contract_api.py
from src.core.game_state import GameState
from src.core.entities.contract import ContractStatus, ContractType
from src.core.localization import TerminologyService
from src.api import api_response
from src.core.i18n import i18n
from typing import List, Dict, Any

def get_contracts_status(state: GameState) -> dict:
    """返回所有合同状态（分组）"""
    lines = [i18n.get("contracts_header")]

    if not state.contracts:
        lines.append(i18n.get("contract_no_contracts"))
        message = "\n".join(lines)
        return api_response(True, message, data=[])

    pending = [c for c in state.contracts if c.status == ContractStatus.PENDING]
    budgeted = [c for c in state.contracts if c.status == ContractStatus.BUDGETED]
    active = [c for c in state.contracts if c.status == ContractStatus.ACTIVE]
    completed = [c for c in state.contracts if c.status == ContractStatus.COMPLETED]
    expired = [c for c in state.contracts if c.status == ContractStatus.EXPIRED]

    data = {
        "pending": [],
        "budgeted": [],
        "active": [],
        "completed": [],
        "expired": []
    }

    if pending:
        items = []
        for c in pending:
            type_emoji = i18n.get("contract_type_tax") if c.contract_type == ContractType.TAX_FARMING else i18n.get("contract_type_works")
            items.append(i18n.get("contract_item",
                                  id=c.id,
                                  type_emoji=type_emoji,
                                  name=c.name,
                                  cost=c.base_cost,
                                  profit=c.expected_profit))
            data["pending"].append({
                "id": c.id,
                "type": c.contract_type.value,
                "name": c.name,
                "cost": c.base_cost,
                "profit": c.expected_profit
            })
        lines.append(i18n.get("contracts_pending", items="\n".join(items)))

    if budgeted:
        items = []
        for c in budgeted:
            type_emoji = i18n.get("contract_type_tax") if c.contract_type == ContractType.TAX_FARMING else i18n.get("contract_type_works")
            items.append(i18n.get("contract_item",
                                  id=c.id,
                                  type_emoji=type_emoji,
                                  name=c.name,
                                  cost=c.base_cost,
                                  profit=c.expected_profit))
            data["budgeted"].append({
                "id": c.id,
                "type": c.contract_type.value,
                "name": c.name,
                "cost": c.base_cost,
                "profit": c.expected_profit
            })
        lines.append(i18n.get("contracts_budgeted", items="\n".join(items)))

    if active:
        items = []
        for c in active:
            type_emoji = i18n.get("contract_type_tax") if c.contract_type == ContractType.TAX_FARMING else i18n.get("contract_type_works")
            figure = state.get_member(c.awarded_to)
            fname = figure.name if figure else i18n.get("contract_unknown")
            faction = state.get_faction(c.awarded_faction)
            fact_name = faction.name if faction else i18n.get("contract_unknown")
            extended = i18n.get("contract_extended") if getattr(c, 'is_extended', False) else ""
            if c.contract_type == ContractType.TAX_FARMING:
                progress = f"{c.total_collected}/{c.expected_profit}"
            else:
                progress = f"{c.total_spent}/{c.base_cost}"
            items.append(i18n.get("contract_active_item",
                                  id=c.id,
                                  type_emoji=type_emoji,
                                  name=c.name,
                                  extended=extended,
                                  contractor=f"{fname} ({fact_name})",
                                  remaining=c.remaining_years,
                                  progress=progress,
                                  expected=c.expected_profit))
            data["active"].append({
                "id": c.id,
                "type": c.contract_type.value,
                "name": c.name,
                "contractor_id": c.awarded_to,
                "contractor_name": fname,
                "faction": c.awarded_faction,
                "remaining_years": c.remaining_years,
                "progress_collected": c.total_collected,
                "progress_spent": c.total_spent,
                "expected_profit": c.expected_profit,
                "base_cost": c.base_cost,
                "is_extended": getattr(c, 'is_extended', False)
            })
        lines.append(i18n.get("contracts_active", items="\n".join(items)))

    if completed:
        items = []
        for c in completed:
            type_emoji = i18n.get("contract_type_tax") if c.contract_type == ContractType.TAX_FARMING else i18n.get("contract_type_works")
            total = c.total_collected + c.total_spent
            warranty_info = ""
            if c.contract_type == ContractType.PUBLIC_WORKS and hasattr(c, 'warranty_remaining'):
                if getattr(c, '_is_fleet_construction', False):
                    pass
                elif c.warranty_remaining > 0:
                    warranty_info = i18n.get("contract_warranty_info", remaining=c.warranty_remaining)
                else:
                    warranty_info = i18n.get("contract_warranty_expired")
            items.append(i18n.get("contract_completed_item",
                                  type_emoji=type_emoji,
                                  name=c.name,
                                  total=total,
                                  warranty_info=warranty_info))
            data["completed"].append({
                "id": c.id,
                "type": c.contract_type.value,
                "name": c.name,
                "total": total,
                "warranty_remaining": getattr(c, 'warranty_remaining', 0)
            })
        lines.append(i18n.get("contracts_completed", items="\n".join(items)))

    if expired:
        items = []
        for c in expired:
            items.append(f"      {c.name}")
            data["expired"].append({"id": c.id, "name": c.name})
        lines.append(i18n.get("contracts_expired", items="\n".join(items)))

    lines.append("=" * 60)
    message = "\n".join(lines)
    return api_response(True, message, data)