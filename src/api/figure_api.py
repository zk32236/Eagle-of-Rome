# src/api/figure_api.py
from src.core.game_state import GameState
from src.core.entities.figure import ClassTier
from src.core.localization import TerminologyService
from src.api import api_response
from src.core.i18n import i18n
from typing import Optional, List, Dict, Any

def _format_figure_summary(state: GameState, fig) -> str:
    """生成单行人物摘要"""
    status = "👑" if fig.is_faction_leader else "🟢"
    tier_emoji = {
        ClassTier.NOBILE: "🏛️",
        ClassTier.EQUES: "💰",
        ClassTier.PLEBEIAN: "👤"
    }.get(fig.class_tier, "❓")
    faction = state.get_faction(fig.faction_id)
    faction_name = faction.name if faction else "无"
    office_display = fig.office if fig.office and not fig.office.startswith("ex-") else "无"
    return i18n.get("figure_summary_line",
                    status=status,
                    tier=tier_emoji,
                    id=fig.id,
                    name=fig.get_formal_name(),
                    faction=faction_name,
                    influence=fig.influence,
                    wealth=fig.wealth,
                    popularity=fig.popularity,
                    land=fig.land_private,
                    veterans=fig.veterans,
                    office=office_display)

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
            return api_response(False, i18n.get("figure_not_found", id=figure_id))

        # 构建详细信息
        lines = []
        status = "👑" if fig.is_faction_leader else "🟢"
        tier_emoji = {
            ClassTier.NOBILE: "🏛️",
            ClassTier.EQUES: "💰",
            ClassTier.PLEBEIAN: "👤"
        }.get(fig.class_tier, "❓")
        lines.append(i18n.get("figure_detail_header", status=status, tier=tier_emoji, id=fig.id))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_name"), value=fig.get_formal_name()))
        faction = state.get_faction(fig.faction_id)
        faction_name = faction.name if faction else i18n.get("figure_none")
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_faction"), value=faction_name))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_class"), value=fig.class_tier.value))
        family = fig.nomen if fig.nomen else i18n.get("figure_none")
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_family"), value=f"{family} (声望: {fig.family_prestige})"))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_age"), value=fig.age))

        # 影响力计算
        land_inf = fig.land_private * 10
        vet_inf = fig.veterans * 10
        fam_inf = fig.family_prestige * 10
        off_bonus = fig.get_office_influence_bonus()
        influence_detail = f"{fig.influence} = 私地{land_inf} + 老兵{vet_inf} + 人气{fig.popularity} + 家族{fam_inf} + 公职{off_bonus}"
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_influence"), value=influence_detail))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_rank"), value=fig.rank))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_zeal"), value=fig.zeal))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_charisma"), value=fig.charisma))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_martial"), value=fig.martial))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_intelligence"), value=fig.intelligence))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_wealth"), value=fig.wealth))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_popularity"), value=fig.popularity))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_land"), value=f"{fig.land_private} C"))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_veterans"), value=fig.veterans))

        office_display = fig.office if fig.office and not fig.office.startswith("ex-") else i18n.get("figure_none")
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_office"), value=office_display))

        # 公职历史
        current_turn = state.turn.turn_number
        current_year = state.turn.year
        start_year = current_year - (current_turn - 1)
        history_parts = []
        for term in fig.office_history:
            year = start_year + (term.start_turn - 1)
            bc_ad = "BC" if year < 0 else "AD"
            history_parts.append(f"{term.office_type}({bc_ad}{abs(year)})")
        history_str = i18n.get("figure_history_sep").join(history_parts) if history_parts else i18n.get("figure_none")
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_history"), value=history_str))

        contracts_str = ", ".join(str(cid) for cid in fig.contract_ids) if fig.contract_ids else i18n.get("figure_none")
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_contracts"), value=contracts_str))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_leader"), value=i18n.get("figure_yes") if fig.is_faction_leader else i18n.get("figure_no")))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_dead"), value=i18n.get("figure_yes") if fig.is_dead else i18n.get("figure_no")))
        lines.append(i18n.get("figure_detail_line", label=i18n.get("figure_detail_absent"), value=i18n.get("figure_no") if fig.is_absent else i18n.get("figure_yes")))
        lines.append("=" * 50)

        message = "\n".join(lines)
        data = _extract_figure_data(fig)
        return api_response(True, message, data)

    else:
        living = state.get_living_members()
        if not living:
            return api_response(True, i18n.get("no_living_figures", default="   无存活人物"), data=[])
        rows = []
        data_list = []
        for fig in living:
            rows.append(_format_figure_summary(state, fig))
            data_list.append(_extract_figure_data(fig))
        message = i18n.get("figure_list_header", rows="\n".join(rows))
        return api_response(True, message, data_list)

def get_private_land_info(state: GameState) -> dict:
    """返回所有人物私地信息"""
    terms = TerminologyService.get()
    land_price = state.get_economic_rule("land_price_per_unit", 10)
    income_rate = state.get_economic_rule("private_land_income_rate", 0.05)
    living = state.get_living_members()
    landowners = [fig for fig in living if fig.land_private > 0]
    if not landowners:
        return api_response(True, i18n.get("no_landowners", default="   无拥有土地的人物"), data=[])

    header_line = f"{'ID':<5} {'姓名':<20} {'私地(C)':<8} {'价值(T)':<10} {'年收益(T)':<12} {'私库(T)'}"
    separator = "-" * 80
    rows = []
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

        rows.append(i18n.get("private_land_row",
                             id=fig.id,
                             name=name,
                             land=land,
                             value=value,
                             income=annual_income,
                             wealth=wealth))
        data_list.append({
            "id": fig.id,
            "name": name,
            "land_private": land,
            "value": value,
            "annual_income": annual_income,
            "wealth": wealth
        })

    total_line = i18n.get("private_land_total",
                          total_land=total_land,
                          total_value=total_value,
                          total_income=total_income,
                          total_wealth=total_wealth)

    message = i18n.get("private_land_info_header",
                       header_line=header_line,
                       rows="\n".join(rows),
                       separator=separator,
                       total_line=total_line)
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