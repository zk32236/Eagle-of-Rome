# src/api/figure_api.py
from src.core.game_state import GameState
from src.core.entities.figure import ClassTier
from src.core.localization import TerminologyService
from src.api import api_response
from typing import Optional, List, Dict, Any

def _format_figure_summary(state: GameState, fig) -> str:
    """生成单行人物摘要（与原StatusFigureCommand._print_figure_summary一致）"""
    status = "👑" if fig.is_faction_leader else "🟢"
    tier_emoji = {
        ClassTier.NOBILE: "🏛️",
        ClassTier.EQUES: "💰",
        ClassTier.PLEBEIAN: "👤"
    }.get(fig.class_tier, "❓")
    faction = state.get_faction(fig.faction_id)
    faction_name = faction.name if faction else "无"
    office_display = fig.office if fig.office and not fig.office.startswith("ex-") else "无"
    return (f"{status}{tier_emoji} ID:{fig.id:<3} {fig.get_formal_name():<25} "
            f"派系:{faction_name:<12} 影响力:{fig.influence} 财富:{fig.wealth} "
            f"人气:{fig.popularity} 私地:{fig.land_private} 老兵:{fig.veterans} 官职:{office_display}")

def _format_figure_detail(state: GameState, fig) -> str:
    """生成人物详细信息（与原StatusFigureCommand._print_figure_detail一致）"""
    status = "👑" if fig.is_faction_leader else "🟢"
    tier_emoji = {
        ClassTier.NOBILE: "🏛️",
        ClassTier.EQUES: "💰",
        ClassTier.PLEBEIAN: "👤"
    }.get(fig.class_tier, "❓")
    faction = state.get_faction(fig.faction_id)
    faction_name = faction.name if faction else "无"

    current_turn = state.turn.turn_number
    current_year = state.turn.year
    start_year = current_year - (current_turn - 1)

    history_parts = []
    for term in fig.office_history:
        year = start_year + (term.start_turn - 1)
        bc_ad = "BC" if year < 0 else "AD"
        history_parts.append(f"{term.office_type}({bc_ad}{abs(year)})")

    lines = [
        "\n" + "=" * 50,
        f"   {status}{tier_emoji} 人物详细信息 (ID:{fig.id})",
        "=" * 50,
        f"姓名: {fig.get_formal_name()}",
        f"派系: {faction_name}",
        f"阶层: {fig.class_tier.value}",
        f"家族: {fig.nomen if fig.nomen else '无'} (声望: {fig.family_prestige})",
        f"年龄: {fig.age}",
    ]
    land_inf = fig.land_private * 10
    vet_inf = fig.veterans * 10
    fam_inf = fig.family_prestige * 10
    off_bonus = fig.get_office_influence_bonus()
    lines.append(f"影响力: {fig.influence} = 私地{land_inf} + 老兵{vet_inf} + 人气{fig.popularity} + 家族{fam_inf} + 公职{off_bonus}")
    lines.extend([
        f"官职等级: {fig.rank}",
        f"热忱: {fig.zeal}",
        f"魅力: {fig.charisma}",
        f"军略: {fig.martial}",
        f"智略: {fig.intelligence}",
        f"财富: {fig.wealth}",
        f"人气: {fig.popularity}",
        f"私地: {fig.land_private} C",
        f"老兵: {fig.veterans}",
    ])
    office_display = fig.office if fig.office and not fig.office.startswith("ex-") else "无"
    lines.append(f"担任公职: {office_display}")
    lines.append(f"公职历史: {', '.join(history_parts) if history_parts else '无'}")
    lines.append(f"持有合同: {fig.contract_ids if fig.contract_ids else '无'}")
    lines.append(f"是否派系领袖: {'是' if fig.is_faction_leader else '否'}")
    lines.append(f"是否死亡: {'是' if fig.is_dead else '否'}")
    lines.append(f"是否在罗马: {'否' if fig.is_absent else '是'}")
    lines.append("=" * 50)
    return "\n".join(lines)

def _extract_figure_data(fig) -> Dict[str, Any]:
    """提取人物结构化数据"""
    return {
        "id": fig.id,
        "name": fig.get_formal_name(),
        "faction_id": fig.faction_id,
        "class_tier": fig.class_tier.value,
        "age": fig.age,
        "influence": fig.influence,
        "wealth": fig.wealth,
        "popularity": fig.popularity,
        "land_private": fig.land_private,
        "veterans": fig.veterans,
        "office": fig.office,
        "is_faction_leader": fig.is_faction_leader,
        "is_dead": fig.is_dead,
        "is_absent": fig.is_absent,
        "office_history": [{"office_type": t.office_type, "start_turn": t.start_turn} for t in fig.office_history],
        "contract_ids": fig.contract_ids,
    }

def get_figure_info(state: GameState, figure_id: Optional[int] = None) -> dict:
    """获取人物信息，若figure_id为None则返回所有存活人物列表"""
    if figure_id is not None:
        fig = state.get_member(figure_id)
        if not fig or fig.is_dead:
            return api_response(False, f"❌ 人物 ID {figure_id} 不存在或已死亡")
        message = _format_figure_detail(state, fig)
        data = _extract_figure_data(fig)
        return api_response(True, message, data)
    else:
        living = state.get_living_members()
        if not living:
            return api_response(True, "   无存活人物", data=[])
        lines = ["\n" + "=" * 80, "   👥 存活人物列表", "=" * 80]
        data_list = []
        for fig in living:
            lines.append(_format_figure_summary(state, fig))
            data_list.append(_extract_figure_data(fig))
        message = "\n".join(lines)
        return api_response(True, message, data_list)

def get_private_land_info(state: GameState) -> dict:
    """返回所有人物私地信息"""
    terms = TerminologyService.get()
    land_price = state.get_economic_rule("land_price_per_unit", 10)
    income_rate = state.get_economic_rule("private_land_income_rate", 0.05)
    living = state.get_living_members()
    landowners = [fig for fig in living if fig.land_private > 0]
    if not landowners:
        return api_response(True, "   无拥有土地的人物", data=[])

    lines = [
        "\n" + "=" * 80,
        "   👤 有土地的人物私地信息",
        "=" * 80,
        f"{'ID':<5} {'姓名':<20} {'私地(C)':<8} {'价值(T)':<10} {'年收益(T)':<12} {'私库(T)'}",
        "-" * 80
    ]
    total_land = 0
    total_value = 0
    total_income = 0.0
    total_wealth = 0
    data_list = []

    for fig in landowners:
        name = fig.get_formal_name()
        land = fig.land_private
        value = land * land_price
        annual_income = value * income_rate
        wealth = fig.wealth

        total_land += land
        total_value += value
        total_income += annual_income
        total_wealth += wealth

        lines.append(f"{fig.id:<5} {name:<20} {land:<8} {value:<10} {annual_income:<12.1f} {wealth}")
        data_list.append({
            "id": fig.id,
            "name": name,
            "land_private": land,
            "value": value,
            "annual_income": annual_income,
            "wealth": wealth
        })

    lines.append("-" * 80)
    lines.append(f"{'总计':<5} {'':<20} {total_land:<8} {total_value:<10} {total_income:<12.1f} {total_wealth}")
    lines.append("=" * 80)
    message = "\n".join(lines)
    data = {
        "landowners": data_list,
        "totals": {
            "land": total_land,
            "value": total_value,
            "income": total_income,
            "wealth": total_wealth
        }
    }
    return api_response(True, message, data)