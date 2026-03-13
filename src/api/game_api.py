# src/api/game_api.py
from src.core.game_state import GameState
from src.core.localization import TerminologyService
from src.api import api_response


def get_status_summary(state: GameState) -> dict:
    try:
        treasury = state.treasury
        living_count = len(state.get_living_members())
        faction_count = len(state.factions)

        # 安全处理 turn 对象
        if state.turn:
            turn_year = state.turn.year
            turn_num = state.turn.turn_number
            year_display = f"{abs(turn_year)} BC" if turn_year < 0 else f"{turn_year} AD"
        else:
            turn_num = "未知"
            year_display = "未知"

        lines = [
            "",
            "=" * 50,
            "   📊 游戏状态摘要",
            "=" * 50,
            f"   回合: 第 {turn_num} 年 ({year_display})",
            f"   国库: {treasury} 塔兰特",
            f"   存活人物: {living_count} 人",
            f"   派系数: {faction_count} 个",
            "=" * 50
        ]
        message = "\n".join(lines)
        data = {
            "treasury": treasury,
            "living_count": living_count,
            "faction_count": faction_count,
            "turn": turn_num,
            "year": turn_year if state.turn else None
        }
        return api_response(True, message, data)
    except Exception as e:
        return api_response(False, f"生成状态摘要时出错: {e}", errors=[str(e)])

def get_public_land_info(state: GameState) -> dict:
    """返回国家公地信息"""
    terms = TerminologyService.get()
    land_price = state.get_economic_rule("land_price_per_unit", 10)
    tax_rate = state.get_economic_rule("national_public_land_tax_rate", 0.02)
    national_land = state.get_national_public_land()
    value = national_land * land_price
    annual_income = int(value * tax_rate)
    treasury = state.treasury

    message = (
        "\n" + "=" * 50 + "\n"
        "   🏞️ 国家公地信息\n"
        "=" * 50 + "\n"
        f"   公地数量: {national_land} C\n"
        f"   土地单价: {land_price} Talents/C\n"
        f"   公地价值: {value} Talents\n"
        f"   年收益率: {tax_rate * 100:.1f}%\n"
        f"   年收益: {annual_income} Talents\n"
        f"   国库余额: {treasury} Talents\n"
        "=" * 50
    )
    data = {
        "national_land": national_land,
        "land_price": land_price,
        "value": value,
        "tax_rate": tax_rate,
        "annual_income": annual_income,
        "treasury": treasury
    }
    return api_response(True, message, data)