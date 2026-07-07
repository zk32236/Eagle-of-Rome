# src/api/province_api.py
from src.core.game_state import GameState
from src.core.entities.contract import ContractType
from src.api import api_response
from src.core.i18n import i18n
from typing import Optional, List, Dict, Any

def _get_display_governor_type(province) -> str:
    """获取用于显示的行省类型"""
    if province.governor_type:
        return province.governor_type
    if province.province_id == 1:
        return "proconsul"
    elif province.province_id == 2:
        return "propraetor"
    return "未知"

def _get_controlling_faction(state: GameState, province_id: int) -> Optional[str]:
    """返回控制该行省的派系名称"""
    for faction in state.factions.values():
        if province_id in faction.province_owned:
            return faction.name
    return None

def _format_contract_info(state: GameState, contract_id: Optional[int]) -> str:
    """返回合同简要信息"""
    if contract_id is None:
        return i18n.get("province_no_contract", default="无")
    contract = state.get_contract(contract_id)
    if not contract:
        return i18n.get("province_invalid_contract", default="无效")
    if contract.contract_type == ContractType.TAX_FARMING:
        tax_rate = getattr(contract, 'tax_rate', 0.0)
        return i18n.get("province_tax_contract_summary", rate=tax_rate*100)
    else:
        return i18n.get("province_works_contract_summary", budget=contract.base_cost)

def _get_governor_name(state: GameState, governor_id: Optional[int]) -> str:
    if governor_id is None:
        return i18n.get("province_no_governor", default="无")
    fig = state.get_member(governor_id)
    return fig.get_formal_name() if fig else i18n.get("province_governor_missing", default="缺失(数据异常)")

def get_province_info(state: GameState, province_id: Optional[int] = None) -> dict:
    """获取行省信息，无参数时返回所有已征服行省概要"""
    if province_id is None:
        provinces = [p for p in state.get_all_provinces() if p.conquered]
        if not provinces:
            return api_response(True, i18n.get("province_summary_no_provinces"), data=[])

        header_line = i18n.get("province_summary_header_line")
        separator = i18n.get("province_summary_separator")
        rows = []
        data_list = []
        for p in provinces:
            name = i18n.get("province_italy_name", default="意大利(本土)") if p.province_id == 0 else p.name
            gov_name = _get_governor_name(state, p.governor_id)
            gov_type = _get_display_governor_type(p)
            tax_info = _format_contract_info(state, p.tax_contract_id)
            proj_info = _format_contract_info(state, p.project_contract_id)
            controller = _get_controlling_faction(state, p.province_id) or i18n.get("province_no_controller", default="无")
            rows.append(i18n.get("province_summary_row",
                                 id=p.province_id,
                                 name=name,
                                 gov_type=gov_type,
                                 governor=gov_name,
                                 grievance=p.grievance,
                                 tax_contract=tax_info,
                                 project_contract=proj_info,
                                 controller=controller))
            data_list.append({
                "province_id": p.province_id,
                "name": name,
                "governor_type": gov_type,
                "governor": gov_name,
                "grievance": p.grievance,
                "tax_contract": tax_info,
                "project_contract": proj_info,
                "controller": controller
            })
        message = i18n.get("province_summary_header",
                           header_line=header_line,
                           separator=separator,
                           rows="\n".join(rows))
        return api_response(True, message, data_list)

    # 单个行省详情
    province = state.get_province(province_id)
    if not province:
        return api_response(False, i18n.get("province_not_found", id=province_id))
    if not province.conquered:
        return api_response(False, i18n.get("province_not_conquered", id=province_id))

    lines = []
    name = i18n.get("province_italy_name", default="意大利(本土)") if province_id == 0 else province.name
    lines.append(i18n.get("province_detail_header", name=name, id=province_id))
    lines.append(i18n.get("province_detail_total_land", total_land=province.total_land))
    lines.append(i18n.get("province_detail_public_land", public_land=province.land_public))
    lines.append(i18n.get("province_detail_private_land", private_land=province.land_private))
    lines.append(i18n.get("province_detail_governor_type", gov_type=_get_display_governor_type(province)))

    if province.governor_designate_id:
        designate = state.get_member(province.governor_designate_id)
        designate_name = designate.get_formal_name() if designate else "?"
        lines.append(i18n.get("province_detail_designate", name=designate_name))

    if province.governor_id:
        gov = state.get_member(province.governor_id)
        gov_name = gov.get_formal_name() if gov else "?"
        if hasattr(province, 'governor_since') and province.governor_since and state.turn:
            since_year = state.turn.year + (province.governor_since - state.turn.turn_number)
            since_display = f"{abs(since_year)} BC" if since_year < 0 else f"{since_year} AD"
        else:
            since_display = i18n.get("figure_unknown", default="未知")
        lines.append(i18n.get("province_detail_governor", name=gov_name, since=since_display))
    else:
        lines.append(i18n.get("province_detail_no_governor"))

    lines.append(i18n.get("province_detail_grievance", grievance=province.grievance))

    # 包税合同
    if province.tax_contract_id:
        contract = state.get_contract(province.tax_contract_id)
        if contract:
            tax_rate = getattr(contract, 'tax_rate', 0.0)
            winner = state.get_member(contract.awarded_to)
            winner_name = winner.get_formal_name() if winner else i18n.get("contract_unknown")
            faction = state.get_faction(contract.awarded_faction)
            faction_name = faction.name if faction else i18n.get("contract_unknown")
            lines.append(i18n.get("province_detail_tax_contract_header"))
            lines.append(i18n.get("province_detail_tax_contract_line",
                                  id=contract.id,
                                  winner=winner_name,
                                  faction=faction_name,
                                  rate=tax_rate*100,
                                  remaining=contract.remaining_years,
                                  profit=getattr(contract, '_annual_profit', 0)))
        else:
            lines.append(i18n.get("province_detail_tax_contract_none"))
    else:
        lines.append(i18n.get("province_detail_tax_contract_none"))

    # 工程合同
    if province.project_contract_id:
        contract = state.get_contract(province.project_contract_id)
        if contract:
            contractor = state.get_member(contract.awarded_to)
            contractor_name = contractor.get_formal_name() if contractor else i18n.get("contract_unknown")
            faction = state.get_faction(contract.awarded_faction)
            faction_name = faction.name if faction else i18n.get("contract_unknown")
            lines.append(i18n.get("province_detail_project_contract_header"))
            lines.append(i18n.get("province_detail_project_contract_line",
                                  id=contract.id,
                                  contractor=contractor_name,
                                  faction=faction_name,
                                  budget=contract.base_cost,
                                  remaining=contract.remaining_years,
                                  warranty=getattr(contract, 'warranty_remaining', 0)))
        else:
            lines.append(i18n.get("province_detail_project_contract_none"))
    else:
        lines.append(i18n.get("province_detail_project_contract_none"))

    controller = _get_controlling_faction(state, province_id)
    if controller:
        lines.append(i18n.get("province_detail_controller", controller=controller))
    else:
        lines.append(i18n.get("province_detail_no_controller"))

    lines.append("=" * 60)
    message = "\n".join(lines)
    data = {
        "province_id": province.province_id,
        "name": province.name,
        "total_land": province.total_land,
        "land_public": province.land_public,
        "land_private": province.land_private,
        "governor_type": _get_display_governor_type(province),
        "governor_id": province.governor_id,
        "governor_designate_id": province.governor_designate_id,
        "grievance": province.grievance,
        "tax_contract_id": province.tax_contract_id,
        "project_contract_id": province.project_contract_id,
        "controller": controller
    }
    return api_response(True, message, data)