# src/api/contract_api.py
from src.core.game_state import GameState
from src.core.entities.contract import ContractStatus, ContractType
from src.core.localization import TerminologyService
from src.api import api_response
from typing import List, Dict, Any

def get_contracts_status(state: GameState) -> dict:
    """返回所有合同状态（分组）"""
    terms = TerminologyService.get()
    lines = [f"\n{'=' * 60}", f"   📜 {terms.assembly} Contracts", f"{'=' * 60}"]

    if not state.contracts:
        lines.append(f"\n   📭 No contracts")
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
        lines.append(f"\n   ⏳ PENDING (Awaiting Senate Budget Vote):")
        for c in pending:
            type_name = "📊 Tax" if c.contract_type == ContractType.TAX_FARMING else "🏗️ Works"
            lines.append(f"      ID:{c.id} {type_name}: {c.name}")
            lines.append(f"         Cost: {c.base_cost} | Profit: {c.expected_profit}")
            data["pending"].append({
                "id": c.id,
                "type": c.contract_type.value,
                "name": c.name,
                "cost": c.base_cost,
                "profit": c.expected_profit
            })

    if budgeted:
        lines.append(f"\n   💰 BUDGETED (Awaiting Forum Auction):")
        for c in budgeted:
            type_name = "📊 Tax" if c.contract_type == ContractType.TAX_FARMING else "🏗️ Works"
            lines.append(f"      ID:{c.id} {type_name}: {c.name}")
            lines.append(f"         Cost: {c.base_cost} | Profit: {c.expected_profit}")
            data["budgeted"].append({
                "id": c.id,
                "type": c.contract_type.value,
                "name": c.name,
                "cost": c.base_cost,
                "profit": c.expected_profit
            })

    if active:
        lines.append(f"\n   ▶️  ACTIVE:")
        for c in active:
            type_name = "📊 Tax" if c.contract_type == ContractType.TAX_FARMING else "🏗️ Works"
            figure = state.get_member(c.awarded_to)
            fname = figure.name if figure else "Unknown"
            faction = state.get_faction(c.awarded_faction)
            fact_name = faction.name if faction else "Unknown"
            extended = " (已延期)" if getattr(c, 'is_extended', False) else ""
            lines.append(f"      ID:{c.id} {type_name}: {c.name}{extended}")
            lines.append(f"         Contractor: {fname} ({fact_name})")
            lines.append(f"         Remaining: {c.remaining_years} years")
            if c.contract_type == ContractType.TAX_FARMING:
                lines.append(f"         Progress: {c.total_collected}/{c.expected_profit}")
            else:
                lines.append(f"         Progress: {c.total_spent}/{c.base_cost}")
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

    if completed:
        lines.append(f"\n   ✅ COMPLETED:")
        for c in completed:
            type_emoji = "📊" if c.contract_type == ContractType.TAX_FARMING else "🏗️"
            total = c.total_collected + c.total_spent
            warranty_info = ""
            if c.contract_type == ContractType.PUBLIC_WORKS and hasattr(c, 'warranty_remaining'):
                if getattr(c, '_is_fleet_construction', False):
                    pass
                elif c.warranty_remaining > 0:
                    warranty_info = f" (质保剩余 {c.warranty_remaining} 年)"
                else:
                    warranty_info = f" (已失修)"
            lines.append(f"      {type_emoji} {c.name} - Total: {total}{warranty_info}")
            data["completed"].append({
                "id": c.id,
                "type": c.contract_type.value,
                "name": c.name,
                "total": total,
                "warranty_remaining": getattr(c, 'warranty_remaining', 0)
            })

    if expired:
        lines.append(f"\n   ❌ EXPIRED:")
        for c in expired:
            lines.append(f"      {c.name}")
            data["expired"].append({"id": c.id, "name": c.name})

    lines.append(f"{'=' * 60}")
    message = "\n".join(lines)
    return api_response(True, message, data)