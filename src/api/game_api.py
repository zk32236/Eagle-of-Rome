# src/api/game_api.py
import sys
import traceback
import io
import logging
from contextlib import redirect_stdout
from src.core.game_state import GameState
from src.api import api_response
from src.core.i18n import i18n

# 导入所有阶段命令类
from src.ui.commands.phase_mortality import MortalityCommand
from src.ui.commands.phase_revenue import RevenueCommand
from src.ui.commands.phase_forum import ForumCommand
from src.ui.commands.phase_population import PopulationCommand
from src.ui.commands.phase_senate import SenateCommand
from src.ui.commands.phase_combat import CombatCommand
from src.ui.commands.phase_resolution import ResolutionCommand

PHASE_COMMAND_MAP = {
    "mortality": MortalityCommand,
    "revenue": RevenueCommand,
    "forum": ForumCommand,
    "population": PopulationCommand,
    "senate": SenateCommand,
    "combat": CombatCommand,
    "resolution": ResolutionCommand,
}


def execute_phase(state: GameState, phase_name: str, player_id: str, args: list = None) -> dict:

    sys.stdout.flush()

    if not state.config.get("testing.bypass_player_check", False):
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    cmd_class = PHASE_COMMAND_MAP.get(phase_name)
    if not cmd_class:

        sys.stdout.flush()
        return api_response(False, i18n.get("error_phase_invalid", phase=phase_name))


    sys.stdout.flush()

    cmd = cmd_class(state)

    # 创建同时写入终端和 StringIO 的流
    f = io.StringIO()
    original_stdout = sys.stdout

    class TeeStdout:
        def write(self, s):
            original_stdout.write(s)
            original_stdout.flush()   # 立即刷新终端
            f.write(s)
        def flush(self):
            original_stdout.flush()
            f.flush()

    tee = TeeStdout()
    sys.stdout = tee

    try:
        success = cmd.execute(args or [])
    except Exception as e:
        sys.stdout = original_stdout

        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        return api_response(False, f"阶段执行异常: {e}", errors=[str(e)])

    sys.stdout = original_stdout
    output = f.getvalue().strip()

    sys.stdout.flush()
    return api_response(success, output, data={"phase": phase_name})


def execute_turn(state: GameState, player_id: str) -> dict:
    """
    按顺序执行所有未执行阶段，需要玩家权限。
    """
    if not state.config.get("testing.bypass_player_check", False):
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    phase_order = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]
    results = []
    all_success = True
    outputs = []
    for phase in phase_order:
        if state.is_phase_executed(phase):
            continue
        result = execute_phase(state, phase, player_id)
        results.append(result)
        outputs.append(result["message"])
        if not result["success"]:
            all_success = False
            break
    message = "\n\n".join(outputs) if outputs else i18n.get("info_turn_complete")
    return api_response(all_success, message, data={"phases": results})


def advance_year(state: GameState, player_id: str, force: bool = False) -> dict:
    """
    推进到下一年，需要玩家权限。

    产品面唯一年度推进用例（FC-01）：
    - GUI: ContextPanel.advancePhaseButton → doAdvanceResolution → adapter.advance_year → 本函数
    - CLI: next → 本函数（force=True 为调试逃生门）
    - debug: debug_cli → 本函数（同一 use-case）

    语义（FC-02~FC-06 冻结顺序）：
    ① 权限检查（force 不跳过）
    ② 重入 guard（fail-closed；force 不跳过）
    ③ resolution 前置（fail-closed；force 可跳过，见下方）
    ④ 置 state._year_advance_in_progress = True
    ⑤ try: state.advance_year()（原子原语，Slice 4 重构后）
    ⑥ except: 结构化失败 advance_failed（年份未推进，无半推进）
    ⑦ finally: state._year_advance_in_progress = False
    ⑧ 成功：返回 year_display

    force=True 语义（FC-02 force 分支，调试逃生门）：跳过 resolution 前置检查，
    但不跳过权限检查、不跳过重入 guard、不跳过原子 commit；审计日志记录 force 使用。
    force 可连续推进多年，属调试语义，不构成产品幂等保证（产品 GUI 面不暴露 force）。
    """
    # ① 权限检查（保留，force 不跳过）
    if not state.config.get("testing.bypass_player_check", False):
        if not state.is_current_player(player_id):
            return api_response(False, i18n.get("error_not_your_turn"))

    # ② 重入 guard（fail-closed，FC-04；force 不跳过）
    if getattr(state, "_year_advance_in_progress", False):
        state.log_event("advance_year 重入拒绝（advance_in_progress）", level=logging.DEBUG)
        return api_response(False, "年度推进正在进行中，请稍候", errors=["advance_in_progress"])

    # ③ resolution 前置（fail-closed，FC-02/FC-03；force 可跳过）
    if not force and not state.is_phase_executed("resolution"):
        state.log_event("advance_year resolution 前置拒绝（resolution_not_executed）", level=logging.DEBUG)
        return api_response(
            False,
            "必须先执行决议阶段 (resolution) 才能进入下一年",
            errors=["resolution_not_executed"],
        )

    if force:
        state.log_event("advance_year force=True（调试逃生门，跳过 resolution 前置）", level=logging.DEBUG)

    if not state.turn:
        return api_response(False, "游戏回合未初始化")

    # ④ 置位
    state._year_advance_in_progress = True
    try:
        # ⑤ 原子原语
        state.advance_year()
    except Exception as e:
        state.log_event(f"advance_year 异常: {e}", level=logging.ERROR)
        return api_response(False, f"年度推进异常: {e}", errors=["advance_failed", str(e)])
    finally:
        # ⑥ 复位
        state._year_advance_in_progress = False

    # ⑦ 成功
    year_display = state.turn.get_year_display() if hasattr(state.turn, 'get_year_display') else str(state.turn.year)
    state.log_event(f"advance_year 成功: {year_display}", level=logging.DEBUG)
    return api_response(True, i18n.get("info_advance_year", year=year_display), data={"year_display": year_display})


# ---------- 以下为阶段0已有的查询函数，无需权限检查，保持原样 ----------

def get_status_summary(state: GameState) -> dict:
    try:
        treasury = state.treasury
        living_count = len(state.get_living_members())
        faction_count = len(state.factions)
        if state.turn:
            turn_num = state.turn.turn_number
            year_display = f"{abs(state.turn.year)} BC" if state.turn.year < 0 else f"{state.turn.year} AD"
        else:
            turn_num = "未知"
            year_display = "未知"
        message = i18n.get("status_summary",
                           turn_num=turn_num,
                           year_display=year_display,
                           treasury=treasury,
                           living_count=living_count,
                           faction_count=faction_count)
        data = {
            "treasury": treasury,
            "living_count": living_count,
            "faction_count": faction_count,
            "turn": turn_num,
            "year": state.turn.year if state.turn else None
        }
        return api_response(True, message, data)
    except Exception as e:
        return api_response(False, f"生成状态摘要时出错: {e}", errors=[str(e)])


def get_public_land_info(state: GameState) -> dict:
    land_price = state.get_economic_rule("land_price_per_unit", 10)
    tax_rate = state.get_economic_rule("national_public_land_tax_rate", 0.02)
    national_land = state.get_national_public_land()
    value = national_land * land_price
    annual_income = int(value * tax_rate)
    treasury = state.treasury
    message = i18n.get("public_land_info",
                       national_land=national_land,
                       land_price=land_price,
                       value=value,
                       tax_rate=tax_rate * 100,
                       annual_income=annual_income,
                       treasury=treasury)
    data = {
        "national_land": national_land,
        "land_price": land_price,
        "value": value,
        "tax_rate": tax_rate,
        "annual_income": annual_income,
        "treasury": treasury
    }
    return api_response(True, message, data)