# src/api/province_api.py
from src.core.game_state import GameState
from src.core.entities.contract import ContractType
from src.api import api_response
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
        return "无"
    contract = state.get_contract(contract_id)
    if not contract:
        return "无效"
    if contract.contract_type == ContractType.TAX_FARMING:
        tax_rate = getattr(contract, 'tax_rate', 0.0)
        return f"包税(税率 {tax_rate*100:.0f}%)"
    else:
        return f"工程(预算 {contract.base_cost})"

def _get_governor_name(state: GameState, governor_id: Optional[int]) -> str:
    if governor_id is None:
        return "无"
    fig = state.get_member(governor_id)
    return fig.get_formal_name() if fig else "缺失(数据异常)"

def get_province_info(state: GameState, province_id: Optional[int] = None) -> dict:
    """获取行省信息，无参数时返回所有已征服行省概要"""
    if province_id is None:
        provinces = [p for p in state.get_all_provinces() if p.conquered]
        if not provinces:
            return api_response(True, "   📭 没有已征服的行省数据", data=[])

        lines = [
            "\n" + "=" * 80,
            "   🏛️ 已征服行省状态一览",
            "=" * 80,
            f"{'ID':<4} {'名称':<12} {'类型':<10} {'总督':<16} {'民怨':<4} {'包税合同':<16} {'工程合同':<16} {'控制派系':<12}",
            "-" * 80
        ]
        data_list = []
        for p in provinces:
            name = "意大利(本土)" if p.province_id == 0 else p.name
            gov_name = _get_governor_name(state, p.governor_id)
            gov_type = _get_display_governor_type(p)
            tax_info = _format_contract_info(state, p.tax_contract_id)
            proj_info = _format_contract_info(state, p.project_contract_id)
            controller = _get_controlling_faction(state, p.province_id) or "无"
            lines.append(f"{p.province_id:<4} {name:<12} {gov_type:<10} {gov_name:<16} {p.grievance:<4} {tax_info:<16} {proj_info:<16} {controller:<12}")
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
        lines.append("=" * 80)
        message = "\n".join(lines)
        return api_response(True, message, data_list)

    # 单个行省详情
    province = state.get_province(province_id)
    if not province:
        return api_response(False, f"❌ 行省ID {province_id} 不存在")
    if not province.conquered:
        return api_response(False, f"❌ 行省ID {province_id} 尚未征服")

    lines = ["\n" + "=" * 60]
    if province_id == 0:
        lines.append(f"   🏛️ 行省详情：意大利 (本土)")
    else:
        lines.append(f"   🏛️ 行省详情：{province.name} (ID:{province_id})")
    lines.append("=" * 60)
    lines.extend([
        f"   总土地: {province.total_land} C",
        f"   公地: {province.land_public} C",
        f"   私地: {province.land_private} C",
        f"   行省类型: {_get_display_governor_type(province)}",
    ])
    if province.governor_designate_id:
        designate = state.get_member(province.governor_designate_id)
        designate_name = designate.get_formal_name() if designate else "?"
        lines.append(f"   候任总督: {designate_name} (将在决算阶段上任)")
    if province.governor_id:
        gov = state.get_member(province.governor_id)
        gov_name = gov.get_formal_name() if gov else "?"
        if hasattr(province, 'governor_since') and province.governor_since and state.turn:
            since_year = state.turn.year + (province.governor_since - state.turn.turn_number)
            since_display = f"{abs(since_year)} BC" if since_year < 0 else f"{since_year} AD"
        else:
            since_display = "未知"
        lines.append(f"   现任总督: {gov_name} (上任于 {since_display})")
    else:
        lines.append(f"   现任总督: 无")
    lines.append(f"   民怨等级: {province.grievance} (0=安居乐业,1=怨声载道,2=民不聊生,3=平民起义)")

    # 包税合同
    if province.tax_contract_id:
        contract = state.get_contract(province.tax_contract_id)
        if contract:
            tax_rate = getattr(contract, 'tax_rate', 0.0)
            winner = state.get_member(contract.awarded_to)
            winner_name = winner.get_formal_name() if winner else "未知"
            faction = state.get_faction(contract.awarded_faction)
            faction_name = faction.name if faction else "无"
            lines.append(f"\n   📊 包税合同:")
            lines.append(f"      ID: {contract.id}")
            lines.append(f"      中标者: {winner_name} ({faction_name})")
            lines.append(f"      实际税率: {tax_rate*100:.1f}%")
            lines.append(f"      剩余年限: {contract.remaining_years} 年")
            lines.append(f"      年净收入: {getattr(contract, '_annual_profit', 0)}")
        else:
            lines.append(f"\n   ⚠️ 包税合同数据异常")
    else:
        lines.append(f"\n   📭 无包税合同")

    # 工程合同
    if province.project_contract_id:
        contract = state.get_contract(province.project_contract_id)
        if contract:
            contractor = state.get_member(contract.awarded_to)
            contractor_name = contractor.get_formal_name() if contractor else "未知"
            faction = state.get_faction(contract.awarded_faction)
            faction_name = faction.name if faction else "无"
            lines.append(f"\n   🏗️ 公共工程合同:")
            lines.append(f"      ID: {contract.id}")
            lines.append(f"      承建者: {contractor_name} ({faction_name})")
            lines.append(f"      预算: {contract.base_cost}")
            lines.append(f"      剩余年限: {contract.remaining_years} 年")
            lines.append(f"      质保剩余: {getattr(contract, 'warranty_remaining', 0)} 年")
        else:
            lines.append(f"\n   ⚠️ 工程合同数据异常")
    else:
        lines.append(f"\n   🏗️ 无公共工程合同")

    controller = _get_controlling_faction(state, province_id)
    if controller:
        lines.append(f"\n   🏛️ 控制派系: {controller}")
    else:
        lines.append(f"\n   🏛️ 无派系控制")

    lines.append("=" * 60)
    message = "\n".join(lines)
    # 结构化数据
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