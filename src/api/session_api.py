"""
src/api/session_api.py
GUI 安全状态 API —— 按 viewer_player_id 过滤的只读 DTO 与阶段协调
"""
import logging
from typing import Any, Dict, List, Optional

from src.api import api_response
from src.api import session_access
from src.api import population_api
from src.api import player_api
from src.api import faction_api
from src.api import figure_api
from src.api import session_turn_service as turn_service
from src.core.game_state import GameState
from src.core.i18n import i18n
from src.core.scenario_loader import ScenarioLoader
from src.core import scenario_validation
from src.core.scenario_validation import ScenarioValidationError
from src.core.entities.figure import _compute_influence
from src.core.entities.player import PlayerType


logger = logging.getLogger("EOR-GUI")


#: W3 / PL-03: typed registration read failure. The hot-seat registration fact is
#: the EXISTING independent record (``session_access._record``); an exception or a
#: non-boolean answer is UNKNOWN -> fail closed with this code, never a silent CLI
#: downgrade and never a fabricated ``True``.
REGISTRATION_UNAVAILABLE = "REGISTRATION_UNAVAILABLE"


def _registration_state(state: GameState) -> Optional[bool]:
    """Read the existing registration fact as ``True``/``False``; ``None`` = UNKNOWN."""
    try:
        registered = session_access.is_hotseat_registered(state)
    except Exception:  # pragma: no cover - defensive
        return None
    return registered if isinstance(registered, bool) else None


def _registration_unavailable_response() -> dict:
    return api_response(False, "Hot-seat registration state unavailable", {
        "retryable": True,
    }, [{"code": REGISTRATION_UNAVAILABLE, "stage": "registration",
        "message": "the hot-seat registration fact could not be read"}])


# ---------------------------------------------------------------------------
# 1. 会话创建
# ---------------------------------------------------------------------------

def create_gui_prototype_session(
    config_path: Optional[str] = None,
    start_phase: str = "mortality",
    scenario_file: str = scenario_validation.DEFAULT_SCENARIO_FILE,
) -> dict:
    """
    创建 GUI 原型会话。

    `scenario_file` 是启动/配置参数（S-A / GR-F10）：`data/scenarios` 下的裸场景文件名。
    默认 `gui_prototype.json`，保留历史行为（1 HUMAN / 2 AI）。所选场景在任何
    GameState/session 创建之前 fail-closed 校验（GR-F11）——非法选择绝不产生半开会话，
    也绝不静默回退到默认场景。默认从真实天命阶段开始；测试可显式指定 start_phase。
    """
    # ---- R02: 单次捕获不可变快照（分离式；尚未创建任何对外 session）----
    # 快照在任何候选 GameState 创建之前准备好；失败 fail-closed，绝不替换默认场景。
    try:
        snapshot = scenario_validation.prepare_selected_scenario(
            scenario_file, config_path=config_path)
    except ScenarioValidationError as e:
        logger.warning("Scenario selection rejected", extra={"scenario_file": scenario_file})
        message = f"SCENARIO_INVALID: {e}"
        return api_response(False, message, errors=[message])
    except Exception as e:  # noqa: BLE001 - resolution/read/decode failure -> fail closed
        message = ("SCENARIO_INVALID: scenario preparation failed for "
                   f"{scenario_file}: {e}")
        logger.error(message)
        return api_response(False, message, errors=[message])

    # canonical 选择 = 快照已解析的 canonical 裸名（非原始入参）；报告与配置同出一源。
    canonical_scenario = snapshot.canonical_name
    scenario_report = snapshot.report_copy()

    # ---- W4-A1 / D7 (PM K-1 = C-α): 会话级 canonical market plan K ----
    # 唯一合法来源 = validator 已深度冻结、且已证明 faction<->player 双射的
    # ``snapshot.frozen_report["factions"]``（有序行）。锚 = 真实 faction id
    # ``optimates`` 映射的 actor；其余座位保留已验证场景的 controller 相对次序。
    # 不用 ``player_ids``（它被 sorted）、不用 dict 顺序、不用 HUMAN 列表，不按名称排序。
    # 缺/重复 O、重复 actor、未知 player → 整个会话 fail-closed（不伪造 O）。
    _faction_rows = snapshot.frozen_report["factions"]
    _anchor_rows = [row for row in _faction_rows if row.get("id") == "optimates"]
    _seat_ids = [row.get("player_id") for row in _faction_rows if row.get("player_id")]
    if len(_anchor_rows) != 1 or not _anchor_rows[0].get("player_id") \
            or len(set(_seat_ids)) != len(_seat_ids):
        message = ("SCENARIO_INVALID: canonical plan requires exactly one "
                   f"optimates anchor for {canonical_scenario}")
        logger.error(message)
        return api_response(False, message, errors=[message])
    _canonical_plan = (_anchor_rows[0]["player_id"],) + tuple(
        pid for pid in _seat_ids if pid != _anchor_rows[0]["player_id"])

    try:
        state = GameState(config_path)
        # 已选择场景：仅经由有界新入口消费快照；应用失败必须 fail-closed
        #（不得静默回退到内置默认，也绝不重试历史 filename loader）。
        try:
            ScenarioLoader.initialize_validated_scenario(state, snapshot)
        except Exception as load_exc:  # noqa: BLE001 - convert any application failure to SCENARIO_INVALID
            message = ("SCENARIO_INVALID: failed to apply selected scenario "
                       f"{canonical_scenario}: {load_exc}")
            logger.error(message)
            return api_response(False, message, errors=[message])

        # W4-A1: bind K ONCE, read-only. Stored as a SESSION-PRIVATE attribute on
        # the state (never a GameState/Core field, never the save game, never the
        # scenario JSON); a later re-bind only confirms the same value.
        _bound = turn_service.canonical_market_plan(state, bind=_canonical_plan)
        if not _bound.get("success"):
            message = ("SCENARIO_INVALID: canonical market plan rejected for "
                       f"{canonical_scenario} ({_bound.get('message', '')})")
            logger.error(message)
            return api_response(False, message, errors=[message])

        phase_order = _phase_order()
        if start_phase not in phase_order:
            start_phase = "mortality"
        for phase_id in phase_order:
            if phase_id == start_phase:
                break
            state.mark_phase_executed(phase_id)

        # 设置当前玩家为第一个 HUMAN 玩家
        human_players = [
            p.player_id for p in state.get_all_players()
            if p.player_type.value == "human"
        ]
        if human_players:
            state.set_current_player(human_players[0])
            state.set_turn_order(human_players)

        # ---- 创建后校验：玩家映射/基数须与预检一致（否则不发布半开会话）----
        loaded_players = {p.player_id for p in state.get_all_players()}
        if loaded_players != set(scenario_report["player_ids"]):
            message = ("SCENARIO_INVALID: initialized player map does not match "
                       f"validated preflight for {scenario_file}")
            logger.error(message)
            return api_response(False, message, errors=[message])
        if len(loaded_players) != scenario_report["faction_count"]:
            message = ("SCENARIO_INVALID: player/faction cardinality mismatch after "
                       f"initialization for {scenario_file}")
            logger.error(message)
            return api_response(False, message, errors=[message])

        # R02 (r2a/r2b): post-initialization CONSISTENCY checks — the ACTUAL
        # player->faction ownership edges (exact edge + bijection), controller
        # consistency and declared year/treasury equality. These are defence-in-depth
        # mapping checks, NOT a provenance proof: provenance is structural (the GUI
        # route only ever consumes the validated snapshot via the bounded new entry,
        # with no call edge to the historical loader or its built-in whole-scenario
        # default). Any mismatch still fails the caller closed.
        ok, reason = _loaded_state_matches_selection(state, scenario_report)
        if not ok:
            message = ("SCENARIO_INVALID: loaded session does not match validated "
                       f"selection {canonical_scenario} ({reason})")
            logger.error(message)
            return api_response(False, message, errors=[message])

        current_player = state.get_current_player()
        logger.info("GUI prototype session created", extra={
            "players": human_players,
            "current_player": current_player.player_id if current_player else None,
            "start_phase": start_phase,
            "scenario_file": scenario_file,
        })
        return api_response(True, "GUI prototype session created", {
            "state": state,
            "human_players": human_players,
            "start_phase": start_phase,
            "scenario": scenario_report,
            "canonical_market_plan": list(_canonical_plan),
        })
    except Exception as e:
        logger.exception("Session creation failed")
        return api_response(False, f"Session creation failed: {e}", errors=[str(e)])


def create_gui_hotseat_session(
    config_path: Optional[str] = None,
    start_phase: str = "mortality",
    scenario_file: str = scenario_validation.DEFAULT_SCENARIO_FILE,
) -> dict:
    """Create a GUI prototype session AND register it as a Hot-seat session (S-B).

    Additive to :func:`create_gui_prototype_session` (which is unchanged and keeps
    the historical CLI/1H2AI exemption): this entry binds the single access-policy
    handle so the Active-seat read/write guard is enforced fail-closed. The
    principal is the first HUMAN player (the first turn actor).

    No scenario/loader logic is duplicated here; the validated S-A chain runs
    verbatim inside the delegated call.
    """
    result = create_gui_prototype_session(
        config_path=config_path, start_phase=start_phase, scenario_file=scenario_file)
    if not result.get("success"):
        return result
    state = result["data"]["state"]
    human_players = result["data"].get("human_players", [])
    principal = human_players[0] if human_players else None
    if principal is None:
        current = state.get_current_player()
        principal = current.player_id if current else None
    if principal is None:
        message = "SCENARIO_INVALID: no HUMAN principal for hot-seat session"
        return api_response(False, message, errors=[message])
    ctx = session_access.register_hotseat_session(state, principal, epoch=0)
    result["data"]["hotseat_context"] = ctx
    return result


def _loaded_state_matches_selection(state: GameState, scenario_report: dict):
    """Post-initialization consistency check (defence-in-depth, NOT provenance).

    R02 r2a/r2b consistency guard (defence-in-depth; structural provenance is that
    the GUI snapshot route has no fallback edge at all). ``ScenarioLoader.load_scenario``
    historically swallows a file-read failure and substitutes its built-in default
    config, which can share the selected file's faction ids / cardinality / controller
    types (canonical ``gui_prototype.json`` vs the built-in default differ ONLY in
    year/treasury); a controller/composition comparison alone cannot detect that.
    This verifies, instead:

      * exact faction-id set and player-id set (cardinality included);
      * the ACTUAL player->faction ownership edge for every declared faction
        (``player_<faction>.faction_id == <faction>``), not merely ``player_type``;
      * ownership bijection: exactly one player per declared faction, no unowned
        faction and no player owning an undeclared/multiple faction;
      * controller consistency (``player_type`` AND ``faction.is_player``);
      * declared ``start_year`` / national ``treasury`` equality (a consistency check
        only — provenance is structural, not value-derived). Only enforced when the
        selected scenario declares the value.

    Returns ``(True, "")`` when the selection was honoured, else ``(False, reason)``.
    """
    expected_ids = {row["id"] for row in scenario_report["factions"]}
    if set(state.factions.keys()) != expected_ids:
        return False, "faction id set mismatch"

    players = state.get_all_players()
    if len(players) != scenario_report["faction_count"]:
        return False, "player/faction cardinality mismatch"
    if {p.player_id for p in players} != set(scenario_report["player_ids"]):
        return False, "player id set mismatch"

    # Ownership edges + bijection (the actual relationship, not player_type).
    owned = {}
    for row in scenario_report["factions"]:
        fid = row["id"]
        pid = row["player_id"]
        player = state.get_player(pid)
        if player is None:
            return False, f"missing player {pid}"
        if player.faction_id != fid:
            return False, (f"ownership edge mismatch: {pid} owns "
                           f"{player.faction_id!r}, expected {fid!r}")
        if fid in owned:
            return False, f"faction {fid!r} owned by more than one player"
        owned[fid] = pid
    if set(owned) != expected_ids:
        return False, "ownership full-coverage failure (unowned faction)"
    if len({p.faction_id for p in players}) != len(players):
        return False, "duplicate faction ownership across players"

    for row in scenario_report["factions"]:
        fid = row["id"]
        is_human = row["controller"] == scenario_validation.CONTROLLER_HUMAN
        expected_type = "human" if is_human else "ai"
        player = state.get_player(row["player_id"])
        if player.player_type.value != expected_type:
            return False, f"controller mismatch for {row['player_id']}"
        faction = state.get_faction(fid)
        if faction is None:
            return False, f"faction {fid!r} missing after load"
        if bool(getattr(faction, "is_player", None)) != is_human:
            return False, f"faction controller flag mismatch for {fid!r}"

    # Provenance: a silent built-in fallback publishes its own year/treasury.
    expected_year = scenario_report.get("start_year")
    if expected_year is not None:
        actual_year = state.turn.year if state.turn else None
        if actual_year != expected_year:
            return False, f"start year mismatch: {actual_year!r} != {expected_year!r}"
    expected_treasury = scenario_report.get("national_treasury")
    if expected_treasury is not None and state.treasury != expected_treasury:
        return False, (f"national treasury mismatch: {state.treasury!r} != "
                       f"{expected_treasury!r}")

    return True, ""


# ---------------------------------------------------------------------------
# 2. 按 viewer 过滤的快照
# ---------------------------------------------------------------------------

def get_session_snapshot(state: GameState, viewer_player_id: str, *,
                         caller_context: Optional[session_access.HotseatContext] = None) -> dict:
    """
    返回 GUI 需要的安全快照。只包含 viewer_player_id 有权查看的信息。
    """
    # S-B Group 1: single active-seat read guard BEFORE building any private DTO.
    # S-B-R3a (DG-01): the explicitly presented service handle is required; the
    # boundary never fetches it off ``state`` (omission DENIES a registered seat).
    denied = session_access.denied_or_none(
        state, session_access.OP_READ_SNAPSHOT, viewer=viewer_player_id,
        caller_context=caller_context)
    if denied is not None:
        return denied
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        current_player = state.get_current_player()
        faction = state.get_faction(viewer.faction_id) if viewer.faction_id else None

        # 当前玩家可见的人物（仅本派系 + 公开信息）
        my_figures = []
        for fig in state.get_living_members():
            if fig.faction_id == viewer.faction_id:
                my_figures.append({
                    "id": fig.id,
                    "name": fig.get_formal_name(),
                    "faction_id": fig.faction_id,
                    "wealth": fig.wealth,
                    "popularity": fig.popularity,
                    "influence": fig.influence,
                    "office": fig.office,
                    "is_faction_leader": fig.is_faction_leader,
                    "is_absent": fig.is_absent,
                    "class_tier": fig.class_tier.value if hasattr(fig.class_tier, 'value') else str(fig.class_tier),
                    "age": fig.age,
                })

        # 国家资源（公开）
        public_resources = {
            "treasury": state.treasury,
            "turn_number": state.turn.turn_number if state.turn else 0,
            "year": state.turn.year if state.turn else 0,
            "year_display": _format_year(state.turn.year if state.turn else 0),
            "living_members": len(state.get_living_members()),
        }

        # 派系资源（仅本派系）
        faction_resources = None
        if faction:
            members = [m for m in state.get_living_members() if m.faction_id == faction.id]
            faction_resources = {
                "id": faction.id,
                "name": faction.name,
                "treasury": faction.treasury,
                "member_count": len(members),
                "total_influence": sum(m.influence for m in members),
            }

        current_phase_id = _infer_current_phase_id(state)
        phase_nav = _build_phase_navigation(state, current_phase_id, viewer_player_id)
        selected_phase_summary = _build_phase_summary(current_phase_id, state, viewer_player_id)
        global_warnings = _build_global_warnings(state, viewer_player_id)

        # 当前可执行动作
        actions = _build_available_actions(state, viewer_player_id)

        # 人口阶段进度
        population_progress = _build_population_progress(state, viewer_player_id)

        data = {
            "current_player_id": current_player.player_id if current_player else None,
            "viewer_player_id": viewer_player_id,
            "viewer_faction_id": viewer.faction_id,
            "is_current_player": state.is_current_player(viewer_player_id),
            "current_phase_id": current_phase_id,
            "selected_phase_id": current_phase_id,
            "public_resources": public_resources,
            "faction_resources": faction_resources,
            "my_figures": my_figures,
            "phase_navigation": phase_nav,
            "selected_phase_summary": selected_phase_summary,
            "global_warnings": global_warnings,
            "available_actions": actions,
            "population_progress": population_progress,
        }
        return api_response(True, "Snapshot refreshed", data)
    except Exception as e:
        logger.exception("Snapshot failed")
        return api_response(False, f"Snapshot failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 3. 人口阶段视图
# ---------------------------------------------------------------------------

# WP-J Group C-1 (J-AC-05a / BL-G7-07) — 权威 featured 只读投影（FC-C01 单一 owner = 本模块）。
# 资格属性映射与 `figure.get_qualification_attribute` 逐字一致（tribune/aedile/dictator 未配置=0）。
_OFFICE_QUALIFICATION_ATTR = {
    "consul": "charisma",
    "censor": "zeal",
    "praetor": "intelligence",
    "quaestor": "martial",
}


def _featured_row_key(state: GameState, office: str, row: dict):
    """featured 排序键：(-资格属性, first_name, figure_id) 升序（最小者即 featured）。

    资格属性 = 权威 `figure.get_qualification_attribute(office)`；first_name = `praenomen`。
    无法解析 Figure 时退化为行 DTO 字段（只读、确定性），不改提名集。
    """
    fid = row.get("id")
    fig = state.get_member(fid) if fid is not None else None
    if fig is not None:
        attr = fig.get_qualification_attribute(office)
        first_name = fig.praenomen or ""
    else:
        attr_key = _OFFICE_QUALIFICATION_ATTR.get(office)
        try:
            attr = int(row.get(attr_key, 0) or 0) if attr_key else 0
        except (TypeError, ValueError):
            attr = 0
        name = row.get("name") or ""
        first_name = name.split(" · ")[0] if name else ""
    return (-attr, first_name, fid if fid is not None else 0)


def _derive_featured_candidate_id(state: GameState, office: str, rows, election_results):
    """FC-C02 featured 谓词（只读投影）。

    ① resolved 且 `election_results` 含该 office → 当选者 `figure_id`（winner 永不隐藏）；
    ② 否则该 office 提名后候选集内 `qualification_attribute(office)` 最大者；
       平局 → first_name 字典序升序（A-Z）；再平局 → figure_id 升序（最终确定性）；
    ③ office 空 → None。**不改提名集/提名顺序**。
    """
    if not rows:
        return None
    for entry in election_results or []:
        if isinstance(entry, dict) and entry.get("office") == office \
                and entry.get("figure_id") is not None:
            return entry["figure_id"]
    best = min(rows, key=lambda row: _featured_row_key(state, office, row))
    return best.get("id")


# WP-J Group D-Aftermath（FC-D01/FC-D02）：战后反馈只读投影（单一 owner = 本读模型装配点）。
def _empty_population_outcome() -> dict:
    return {
        "triumphs": [],
        "legions": {"resolved_wars": {"total": 0}, "deescalated": {"total": 0}},
        "fleets": [],
    }


def _project_population_outcome(state: GameState, result_data: dict) -> dict:
    """逐字投影权威战后解散 payload → ``population_outcome``（FC-D02；零重算；空态不造行 FC-D07）。

    数据源：``state.get_phase_result("population_disbandment")``（回退 ``population`` phase
    result 的 ``data.disbandment``）。仅只读；不新增写语义；QML 零业务重建（FC-D08）。
    """
    disbandment = state.get_phase_result("population_disbandment")
    if not isinstance(disbandment, dict):
        if isinstance(result_data, dict) and isinstance(result_data.get("disbandment"), dict):
            disbandment = result_data.get("disbandment")
        else:
            disbandment = None
    if not isinstance(disbandment, dict):
        return _empty_population_outcome()

    legions = disbandment.get("legions") if isinstance(disbandment.get("legions"), dict) else {}
    resolved = legions.get("resolved_wars") if isinstance(legions.get("resolved_wars"), dict) else {}
    deescalated = legions.get("deescalated") if isinstance(legions.get("deescalated"), dict) else {}

    triumphs = []
    for row in (disbandment.get("triumphs") or []):
        if isinstance(row, dict):
            triumphs.append({
                "war_id": row.get("war_id"),
                "war_name": row.get("war_name"),
                "commander_id": row.get("commander_id"),
                "commander_name": row.get("commander_name"),
            })

    return {
        "triumphs": triumphs,
        "legions": {
            "resolved_wars": {"total": resolved.get("total", 0)},
            "deescalated": {"total": deescalated.get("total", 0)},
        },
        "fleets": list(disbandment.get("fleets") or []),
    }


def get_population_view(state: GameState, viewer_player_id: str, *,
                        caller_context: Optional[session_access.HotseatContext] = None) -> dict:
    """
    返回人口阶段的详细视图，包含候选人、已投票状态、可执行操作。
    """
    # S-B Group 1: active-seat read guard before any public/private DTO build.
    denied = session_access.denied_or_none(
        state, session_access.OP_READ_PHASE_VIEW, viewer=viewer_player_id,
        caller_context=caller_context)
    if denied is not None:
        return denied
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        # GUI 人口阶段首个读模型刷新处：归档必须先于任何 get_candidates
        # （设计 02 §2.2；G3 Q3）。阶段门：仅当当前阶段为 population 才执行
        # （session_store.initialize 会在非人口阶段预刷新本视图，见偏离 D-6）。
        if _infer_current_phase_id(state) == "population":
            # ESC-WPJ-G7Q1-01 / ESC-S1：Step-0 战后处理（凯旋举行 + 军团/舰队解散）
            # 前移至人口阶段入口（对齐规格 §2.2 / CLI phase_population._handle_step_0），
            # 使反馈在进入人口阶段的一瞬间即可见（FC-ESC-01）。canonical 幂等
            # （marker "population_disbandment"）⇒ 结算侧 resolve_population_slice 恒为
            # 幂等命中（安全网保留，FC-ESC-06）⇒ exactly-once、零二次 mutation。
            population_api.process_population_disbandments(state, caller_context=caller_context)
            population_api.begin_population_phase(state, caller_context=caller_context)

        # 本派系可操作人物
        my_figures = []
        for fig in state.get_living_members():
            if fig.faction_id == viewer.faction_id:
                my_figures.append({
                    "id": fig.id,
                    "name": fig.get_formal_name(),
                    "faction_id": fig.faction_id,
                    "wealth": fig.wealth,
                    "popularity": fig.popularity,
                    "influence": fig.influence,
                    "office": fig.office,
                    "is_faction_leader": fig.is_faction_leader,
                    "is_absent": fig.is_absent,
                    "class_tier": fig.class_tier.value if hasattr(fig.class_tier, 'value') else str(fig.class_tier),
                    "age": fig.age,
                })

        # 候选人（所有人可见，但只含公开信息）
        # D5 (Rework-D3D6 · FC-RW-01/02/12)：候选读 MUST 在**外层授权之后**组合
        # 服务私有 validated read（``_get_candidates_impl``）——**不得**再调用无 viewer 的
        # PUBLIC guarded ``get_candidates``（staging 时其 bound viewer=None 被 staging target
        # predicate 拒绝 → 内部失败被静默降为 ``{}`` 成功 → 空候选被当作合法空缺发布）。
        # 读失败 / 缺键 / 坏形状 = **显式失败**（稳定内部 code，绝不冒充合法空缺）；
        # 合法「五职全空」mapping 仍是成功空缺。历史结果 fallback **不得**吞当前读失败。
        try:
            cand_result = population_api._get_candidates_impl(state)
        except Exception:
            # Rework-D3D6 D3/D5 R1 (R02 · FC-RW-02/12): a candidate RETRIEVAL
            # EXCEPTION maps to the STABLE ``CANDIDATES_UNAVAILABLE`` code — never
            # the outermost generic ``errors=[str(e)]`` (which did not carry the
            # promised structured contract). Fail-closed and explicit.
            logger.exception("Population candidate retrieval failed")
            return api_response(False, "Failed to load population candidates", {}, [{
                "code": "CANDIDATES_UNAVAILABLE",
                "message": "Unable to load candidate list for the population view",
            }])
        if not isinstance(cand_result, dict) or not cand_result.get("success"):
            return api_response(False, "Failed to load population candidates", {}, [{
                "code": "CANDIDATES_UNAVAILABLE",
                "message": "Unable to load candidate list for the population view",
            }])
        cand_data = cand_result.get("data")
        if (not isinstance(cand_data, dict)
                or set(cand_data) != set(_POPULATION_OFFICES)
                or any(not isinstance(cand_data[o], list)
                       for o in _POPULATION_OFFICES)):
            return api_response(False, "Invalid population candidate payload", {}, [{
                "code": "CANDIDATES_SHAPE_INVALID",
                "message": "candidate payload must be the complete five-office map",
            }])
        candidates = cand_data
        result = state.get_phase_result("population")
        result_data = result.get("data", {}) if isinstance(result, dict) else {}
        resolved = bool(result) or state.is_phase_executed("population")
        if resolved and isinstance(result_data, dict) and result_data.get("candidates"):
            candidates = result_data["candidates"]

        # WP-J Group C-1（FC-C01/C02）：权威 featured 只读投影（单一 owner = 此处）。
        # office 级 `featured_candidate_id` + 行级 `is_featured`（additive；零写语义；不改提名集）。
        _election_results = result_data.get("election_results", []) if isinstance(result_data, dict) else []
        featured_candidate_ids = {}
        featured_candidates = {}
        for _office, _rows in candidates.items():
            _fid = _derive_featured_candidate_id(state, _office, _rows, _election_results)
            featured_candidate_ids[_office] = _fid
            featured_candidates[_office] = [
                dict(_r, is_featured=(_r.get("id") == _fid)) for _r in _rows
            ]

        # 当前 viewer 已投票的官职
        my_votes = {}
        for vote in state.get_population_votes():
            if vote[0] == viewer_player_id:
                my_votes[vote[1]] = vote[2]

        # 当前 viewer 已完成的庆典
        my_campaigns = []
        for camp in state.get_population_campaigns():
            if camp[0] == viewer_player_id:
                my_campaigns.append({"figure_id": camp[1], "amount": camp[2]})

        # 是否允许操作
        is_current = state.is_current_player(viewer_player_id)
        current_phase_id = _infer_current_phase_id(state)
        is_population_phase = current_phase_id == "population"
        office_count = len([office for office, rows in candidates.items() if rows])
        vacant_offices = [office for office, rows in candidates.items() if not rows]
        my_candidate_count = sum(
            1 for office, rows in candidates.items()
            for c in rows if c.get("faction_id") == viewer.faction_id
        )
        # WP-02a v3: campaign_done 按 player_id 隔离 (D-12)
        # WP-03 L2: 无本派系候选人 → campaign 平凡完成（读模型，不写 backend）
        campaign_done = state.get_batch_completed(viewer_player_id) or (my_candidate_count == 0)
        # WP-03 L3: 无 office 需投票 → HUMAN 平凡完成
        vote_done = (office_count == 0) or (len(my_votes) >= office_count)
        current_step = "results" if resolved else ("vote" if campaign_done else "campaign")
        can_campaign = is_current and is_population_phase and not resolved
        can_vote = is_current and is_population_phase and campaign_done and not resolved
        can_complete = is_current and is_population_phase and vote_done and not resolved
        # Standard 4-condition pattern matching Mortality/Revenue/Forum/Senate/Combat
        can_advance = (
            current_phase_id == "population"
            and state.is_current_player(viewer_player_id)
            and not state.is_phase_executed("population")
            and bool(state.get_phase_result("population"))
        )

        # 字段级错误/禁用原因
        field_errors = {}
        if not is_current:
            field_errors["global"] = "不是你的回合"

        # WP-J J-AC-10 / FC-01..FC-06: authoritative intra-phase step read model.
        # Population has exactly two sub-steps [campaign, vote]; 「公示区」is not a sub-step (FC-06).
        steps = [
            {
                "key": "campaign",
                "label": "🎉 庆典赞助",
                "state": "current" if current_step == "campaign"
                else ("complete" if campaign_done else "todo"),
            },
            {
                "key": "vote",
                "label": "🗳️ 投票选举",
                "state": "current" if current_step == "vote"
                else ("complete" if current_step == "results" else "todo"),
            },
        ]

        data = {
            "steps": steps,
            # WP-J Group D-Aftermath（J-AC-04a / FC-D01/FC-D02）：战后反馈 additive 只读投影
            "population_outcome": _project_population_outcome(state, result_data),
            "my_figures": my_figures,
            "candidates": featured_candidates,
            "featured_candidate_ids": featured_candidate_ids,
            "my_votes": my_votes,
            "my_campaigns": my_campaigns,
            "current_step": current_step,
            "resolved": resolved,
            "office_count": office_count,
            "vacant_offices": vacant_offices,
            "my_candidate_count": my_candidate_count,
            "campaign_done": campaign_done,
            "vote_done": vote_done,
            "election_results": _election_results,
            "faction_influence_before": (
                result_data.get("faction_influence_before", _faction_influence_rows(state))
                if isinstance(result_data, dict) else _faction_influence_rows(state)
            ),
            "faction_influence_after": (
                result_data.get("faction_influence_after", _faction_influence_rows(state))
                if isinstance(result_data, dict) else _faction_influence_rows(state)
            ),
            "is_current_player": is_current,
            "current_phase_id": current_phase_id,
            "can_campaign": can_campaign,
            "can_vote": can_vote,
            "can_complete": can_complete,
            "can_advance": can_advance,
            "field_errors": field_errors,
            "battlefield_commander_conversion": (
                state.get_phase_result("battlefield_commander_conversion") or {"converted": [], "total": 0}
            ) if isinstance(result_data, dict) else {"converted": [], "total": 0},
        }
        return api_response(True, "Population view", data)
    except Exception as e:
        logger.exception("Population view failed")
        return api_response(False, f"Population view failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 4. 完成当前玩家操作
# ---------------------------------------------------------------------------

def complete_population_player(state: GameState, player_id: str, *,
                               caller_context: Optional[session_access.HotseatContext] = None) -> dict:
    """
    标记当前玩家完成人口阶段操作，切换到下一个玩家。
    """
    # S-B Group 1 (SB-V01): public mutation boundary guard (direct-call coverage).
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="complete_population_player",
        target_player_id=player_id, caller_context=caller_context)
    if not decision.allowed:
        return decision.denial()
    try:
        # S-C (R1 §4.1 / delta §3.3#1): record the checked completion via the
        # coordinator's ledger (owner-recorded explicit finish), then keep the
        # historical cursor rotation for the non-coordinated pass.
        scope = turn_service.mint_scope(state, "population")
        substep = turn_service._population_substep(state)
        # R11-F03: CHECK every completion result — a rejected/unrecorded owner
        # completion must NOT proceed to the cursor rotation (never a false
        # completion; the swallowed result is the defect being closed).
        completion = turn_service.complete_actor(
            state, None, scope.scope_id, "complete_population_player",
            actor_player_id=player_id, phase="population", substep=substep,
            satisfied_kind=turn_service.KIND_EXPLICIT_FINISH,
            owner_declared=True)
        if not completion.get("success"):
            reason = completion.get("reason", "COMPLETION_REJECTED")
            return api_response(False, "Player completion was not recorded", {
                "reason": reason,
            }, [{"code": reason,
                "message": "the owner completion was not recorded"}])
        # FC-D1-02 / RULE-SINGLE-APPLIER (W4): on a coordinated Hot-seat session the
        # coordinator's SOLE automatic continuation
        # (``session_turn_service.continue_after_command`` in
        # ``submit_population_votes``) selects the next actor through
        # ``turn_service.select_actor`` (the only cursor writer).
        # ``complete_population_player`` MUST NOT pre-move the cursor: a bare
        # pre-rotation left the Core cursor on the scheduler's next actor (e.g. the
        # first outstanding AI) while the Store's seat authority / viewer stayed on
        # the completing HUMAN — the exact "cursor moved without a paired seat
        # handoff" desync the masked settle then rejects. The completion therefore
        # records truth only; the sole automatic continuation performs the single
        # cursor move. A never-registered CLI/legacy state keeps the historical
        # public ``player_api.next_player`` rotation unchanged.
        if session_access.is_hotseat_registered(state):
            return api_response(True, "Player completion recorded", {
                "new_player_id": None,
            })
        return player_api.next_player(state, player_id, caller_context=caller_context)
    except Exception as e:
        logger.exception("Player completion failed")
        return api_response(False, f"Player completion failed: {e}", errors=[str(e)])


_POPULATION_OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")


def submit_population_votes(
    state: GameState,
    player_id: str,
    selection_map: Dict[str, int],
    *,
    caller_context: Optional[session_access.HotseatContext] = None,
) -> dict:
    """Submit the WP-02b fixed-five selection map and orchestrate handoff/resolve."""
    # S-B Group 1 (SB-V01): public mutation boundary guard (direct-call coverage).
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="submit_population_votes",
        target_player_id=player_id, caller_context=caller_context)
    if not decision.allowed:
        return decision.denial()
    if not isinstance(selection_map, dict):
        return api_response(False, "Invalid population vote selection", {}, [{
            "code": "INVALID_SELECTION_MAP",
            "message": "selection_map must be a dictionary",
        }])

    invalid = []
    for office, figure_id in selection_map.items():
        if office not in _POPULATION_OFFICES:
            invalid.append(office)
        elif isinstance(figure_id, bool) or not isinstance(figure_id, int) or figure_id <= 0:
            invalid.append(office)
    if invalid:
        return api_response(False, "Invalid population vote selection", {}, [{
            "code": "INVALID_SELECTION_MAP",
            "message": "Explicit selections must use a known office and positive figure id",
            "fields": invalid,
        }])

    # EOR-DEFECT-20260817-01 Fix B (P1): 零候选人 office → 强制 figure_id=0（No-Candidate Contract）。
    # P1-①: get_candidates success 守卫（对齐 population_api.batch_vote:505 模式）——
    # 若候选数据获取失败，直接返回错误，不继续（防未来退化时全量静默 ABSTAIN）。
    # GUI 人口阶段投票入口：归档必须先于 get_candidates（设计 02 §2.2；G3 Q3）。
    # 阶段门：仅当当前阶段为 population 才执行（防 session_store 预刷新误触发，D-6）。
    if _infer_current_phase_id(state) == "population":
        population_api.begin_population_phase(state, caller_context=caller_context)
    # FC-D1-01: this read runs INSIDE the owning handoff transaction, so it must
    # use the service-private validated-read boundary (the SAME internal read the
    # coordinator / batch_vote already use) — never the PUBLIC guarded boundary
    # (which has no continuation ``command`` label and is therefore denied under
    # the transaction-local continuation scope). The public ``get_candidates``
    # boundary is unchanged and stays fail-closed for ordinary public reads.
    cand_result = population_api._get_candidates_impl(state)
    if not cand_result.get("success"):
        return api_response(False, "Failed to load population candidates", {}, [{
            "code": "CANDIDATES_UNAVAILABLE",
            "message": "Unable to load candidate list for vote normalization",
        }])
    cand_data = cand_result.get("data", {})
    entries = [
        {"office": office,
         "figure_id": selection_map.get(office, 0) if cand_data.get(office) else 0}
        for office in _POPULATION_OFFICES
    ]

    # ── G1 (PC02-WITHDRAWAL, Owner 2026-10-23) ─────────────────────────────
    # canonical = 本座位「庆典 → 投票 → 切席」；per-actor only，NO global barrier。
    # 谓词与视图 get_population_view 的 campaign_done 同义（session_api.py:593），
    # 不新造真相源；拒绝时零投票/obligation/receipt/impact 写入（batch_vote 之前）。
    # AI 不得经此入口（AI 的庆典→投票是代码顺序事实，见 _drain_ai_population_turns）。
    _actor = state.get_player(player_id)
    if _actor is not None:
        _own_candidates = sum(
            1 for _rows in cand_data.values()
            for _cand in _rows if _cand.get("faction_id") == _actor.faction_id
        )
        if not (state.get_batch_completed(player_id) or _own_candidates == 0):
            return api_response(False, "Campaign must be completed before voting", {
                "campaign_done": False,
                "retryable": True,
            }, [{
                "code": "CAMPAIGN_REQUIRED",
                "message": "请先完成本席位庆典，再提交投票",
            }])
    # ───────────────────────────────────────────────────────────────────────

    batch_result = population_api.batch_vote(state, player_id, entries, caller_context=caller_context)
    if not batch_result.get("success"):
        return batch_result

    completion = complete_population_player(state, player_id, caller_context=caller_context)
    if not completion.get("success"):
        return completion

    # S-C: the SOLE automatic continuation decides next actor / resolution. It is
    # NOT a rotation on ``incomplete_humans == []`` (R1 §4.1 / delta §3.3#1).
    cont = turn_service.continue_after_command(
        state, ai_executor=_population_ai_executor)
    if cont.masked_failure:
        return api_response(False, "AI continuation failed", {
            "status": "masked_failure",
            "resolved": False,
            "retryable": True,
            "reason": cont.reason,
            "election_results": [],
        }, [{"code": "AI_DRAIN_MASKED_FAILURE", "message": cont.reason}])
    if cont.status == turn_service.STATUS_RESOLVED:
        resolved = resolve_population_slice(state, caller_context=caller_context)
        if not resolved.get("success"):
            return resolved
        current = state.get_current_player()
        receipt_ref = "submit_population_votes"
        if session_access.is_hotseat_registered(state):
            receipt_ref = turn_service.delivery_command_ref(
                state, "population", "submit_population_votes",
                actor=getattr(current, "player_id", None))
        delivery = turn_service.delivery_for_actor(
            state, "population",
            getattr(current, "player_id", None),
            outcome=turn_service.DELIVERY_OUTCOME_RESOLVED,
            viewer_id=player_id,
            command_receipt_ref=receipt_ref)
        return api_response(True, "Population votes submitted and resolved", {
            "status": "resolved",
            "awaiting_player_id": None,
            "resolved": True,
            "election_results": resolved.get("data", {}).get("election_results", []),
            "delivery": delivery,
        })
    awaiting = state.get_current_player()
    receipt_ref = "submit_population_votes"
    if session_access.is_hotseat_registered(state):
        receipt_ref = turn_service.delivery_command_ref(
            state, "population", "submit_population_votes",
            actor=getattr(awaiting, "player_id", None))
    delivery = turn_service.delivery_for_actor(
        state, "population",
        getattr(awaiting, "player_id", None),
        viewer_id=player_id,
        command_receipt_ref=receipt_ref,
        substep=turn_service._population_substep(state))
    return api_response(True, "Awaiting remaining players", {
        "status": "awaiting_players",
        "awaiting_player_id": awaiting.player_id if awaiting else None,
        "resolved": False,
        "election_results": [],
        "delivery": delivery,
    })


# ---------------------------------------------------------------------------
# Recovery (R-02 / S-D-2 Disposition §2.3): the owner-layer continuation-recovery
# entry. It supplies the SAME phase-specific AI executor the forward route uses
# (``submit_population_votes`` L724 -> ``_population_ai_executor``; senate -> the
# mirrored senate executor F1), so a real ``grContinuationRecover`` -> Store
# ``doRecoverContinuation`` -> Adapter ``recover_continuation`` resumes ONLY the
# outstanding scheduled-AI work instead of failing closed with ``NO_EXECUTOR``.
# The committed HUMAN command is never resubmitted (same-revision ``DK`` replay
# denied). No authorization is relaxed: the public mutation guard is the same one
# the forward route presents.
# ---------------------------------------------------------------------------
def _phase_ai_executor(state: GameState):
    """Select the phase-specific scheduled-AI drain for the CURRENT phase.

    Mirrors the forward wiring (``submit_population_votes`` ->
    ``_population_ai_executor``); senate uses the mirrored senate executor (F1).
    An unknown phase fails closed (``None`` -> the coordinator's ``NO_EXECUTOR``
    masked safe failure). The phase-specific knowledge stays in the phase owner;
    the generic coordinator is never asked to carry it.
    """
    try:
        phase = turn_service._current_phase(state)
    except Exception:  # pragma: no cover - defensive
        return None
    if phase == "population":
        return _population_ai_executor
    if phase == "senate":
        from src.api import senate_api
        return senate_api._senate_ai_executor
    return None


def recover_continuation(
    state: GameState,
    lease: Any = None,
    fresh_receipt: Any = None,
    *,
    caller_context: Optional[session_access.HotseatContext] = None,
) -> dict:
    """Owner-layer continuation-recovery entry (R-02 / disposition §2.3).

    Adds the MISSING phase-AI-executor wiring to the recovery route (the forward
    route already supplies it in ``submit_population_votes``). A real
    ``grContinuationRecover`` -> Store ``doRecoverContinuation`` -> Adapter
    ``recover_continuation`` therefore actually makes progress on outstanding AI
    work (``continue_after_command(ai_executor=...)``) rather than returning a
    dict that stays ``MASKED_FAILURE`` via ``NO_EXECUTOR``. The committed HUMAN
    command is not resubmitted (same-revision ``DK`` replay denied).
    """
    # S-B Group 1: public mutation boundary guard (same policy as the forward route).
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="recover_continuation",
        target_player_id=None, caller_context=caller_context)
    if not decision.allowed:
        return decision.denial()
    cont = turn_service.recover_continuation(
        state, lease, fresh_receipt, ai_executor=_phase_ai_executor(state))
    if cont.masked_failure:
        return api_response(False, "AI continuation failed", {
            "status": "masked_failure",
            "resolved": False,
            "retryable": True,
            "reason": cont.reason,
        }, [{"code": "AI_DRAIN_MASKED_FAILURE", "message": cont.reason}])
    data = {
        "status": cont.status,
        "actor": cont.actor,
        "resolved": cont.status == turn_service.STATUS_RESOLVED,
    }
    # D4/D6 I2-R1 item3 (FC-D46-05 §4.3.4): a real senate terminal carries the
    # frozen envelope (actor/controller/current_player_id/finalization_id/
    # cursor_restored/awaiting_player_id) so the Store can drive the SAME masked
    # activation; the ordinary (non-terminal) recovery data stays unchanged.
    if getattr(cont, "terminal", None) is not None:
        data.update(cont.terminal)
    return api_response(True, "Continuation recovered", data)


# ---------------------------------------------------------------------------
# 5. 人口阶段结算（选举结果）
# ---------------------------------------------------------------------------

def _all_human_population_votes_complete(state: GameState) -> bool:
    """Return True when every human player has voted for all required offices."""
    cand_result = population_api._get_candidates_impl(state)
    candidates = cand_result.get("data", {}) if cand_result.get("success") else {}
    required_offices = {office for office, rows in candidates.items() if rows}
    if not required_offices:
        # WP-03 L3: 无 office 需投票 → HUMAN 平凡完成（不阻塞 resolve）
        return True

    votes_by_player: dict = {}
    for player_id, office, _figure_id in state.get_population_votes():
        votes_by_player.setdefault(player_id, set()).add(office)

    humans = [p for p in state.get_all_players() if p.player_type.value == "human"]
    return bool(humans) and all(
        required_offices.issubset(votes_by_player.get(p.player_id, set()))
        for p in humans
    )


def _drain_ai_population_turns(state: GameState, auto, *,
                               caller_context: Optional[session_access.HotseatContext] = None) -> dict:
    """唯一 AI drain 实现。遍历所有非 human 玩家，执行 festival → vote →
    set_vote_completed。completed-AI skip + partial-state preflight fail-closed（FC10）。
    """
    processed = []

    for player in state.get_all_players():
        # S-C (delta §1.2): explicit AI-only filter. OBSERVER and other HUMAN seats
        # are NEVER processed as AI (the old non-human filter admitted OBSERVER).
        if player.player_type is not PlayerType.AI:
            continue
        if state.get_vote_completed(player.player_id):
            continue

        existing_campaign = any(
            row[0] == player.player_id for row in state.get_population_campaigns()
        )
        existing_vote = any(
            row[0] == player.player_id for row in state.get_population_votes()
        )
        if existing_campaign or existing_vote:
            return api_response(False, "AI population partial state detected", {
                "processed_players": processed,
                "failed_player": player.player_id,
                "retryable": False,
                "reason_code": "AI_DRAIN_PARTIAL_STATE",
            })

        faction = state.get_faction(player.faction_id)
        if not faction:
            return api_response(False, "AI faction not found", {
                "failed_player": player.player_id,
                "retryable": False,
                "reason_code": "AI_DRAIN_INVALID_STATE",
            })

        # === S1 GUARD: candidate retrieval（FIX-A + FIX-2）===
        # FC-D1-01: the AI drain is an internal continuation of the owning masked
        # transaction -> the service-private validated-read boundary (never the
        # public guarded read boundary).
        try:
            cand_result = population_api._get_candidates_impl(state)
        except Exception as exc:
            return api_response(False, "AI drain: candidate retrieval error", {
                "processed_players": processed,
                "failed_player": player.player_id,
                "retryable": False,
                "reason_code": "AI_DRAIN_CANDIDATE_RETRIEVAL_ERROR",
            })
        if not cand_result.get("success"):
            return api_response(False, "AI drain: candidate retrieval failed", {
                "processed_players": processed,
                "failed_player": player.player_id,
                "retryable": False,
                "reason_code": "AI_DRAIN_CANDIDATE_RETRIEVAL_FAILED",
            })
        required_offices = {
            office for office, rows in cand_result.get("data", {}).items() if rows
        }
        # B3-AC09 S1 guard（fail-closed，保留）：候选数据本身为空/畸形（无 office 键）
        # → 保持 AI_DRAIN_NO_CANDIDATES terminal，防 vacuous PASS。
        if not cand_result.get("data"):
            return api_response(False, "AI drain: no required offices (empty candidates)", {
                "processed_players": processed,
                "failed_player": player.player_id,
                "retryable": False,
                "reason_code": "AI_DRAIN_NO_CANDIDATES",
            })
        if not required_offices:
            # WP-03 L4: 合法全空候选人（office 键齐备但均无候选人）→ AI 平凡完成（no-op，非 terminal）
            state.set_vote_completed(player.player_id, True)
            processed.append(player.player_id)
            continue
        # === END S1 GUARD ===

        try:
            auto.process_festival(player.player_id, faction, bypass_permission=True,
                                  caller_context=caller_context)
            auto.process_vote(player.player_id, faction, bypass_permission=True,
                              caller_context=caller_context)

            # === POSTCONDITION VALIDATION (Option C) ===
            votes_after = {
                office for vid, office, _fid in state.get_population_votes()
                if vid == player.player_id
            }
            missing = required_offices - votes_after
            if missing:
                return api_response(False, "AI drain postcondition: votes not recorded", {
                    "processed_players": processed,
                    "failed_player": player.player_id,
                    "retryable": False,
                    "reason_code": "AI_DRAIN_POSTCONDITION_FAILED",
                    "missing_offices": sorted(missing),
                })
            # === END POSTCONDITION ===

            state.set_vote_completed(player.player_id, True)
            processed.append(player.player_id)
        except Exception as exc:
            return api_response(False, f"AI drain failed: {exc}", {
                "processed_players": processed,
                "failed_player": player.player_id,
                "retryable": False,
                "reason_code": "AI_DRAIN_ERROR",
            })

    return api_response(True, "AI drain complete", {
        "processed_players": processed,
    })


def _build_population_auto_processor(state: GameState) -> "AutoPlayerProcessor":
    """Build the narrow scheduled-AI capability for the population drain."""
    from src.ui.processors.auto_player_processor import AutoPlayerProcessor
    from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
    from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
    from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
    from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
    from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
    from src.core.deciders.impl.auto_vote_decider import AutoVoteDecider
    return AutoPlayerProcessor(
        state,
        retirement_decider=AutoRetirementDecider(state),
        recruitment_decider=AutoRecruitmentDecider(),
        bid_decider=AutoBidDecider(),
        triumph_decider=AutoTriumphDecider(),
        festival_decider=AutoFestivalDecider(),
        vote_decider=AutoVoteDecider(),
    )


def _population_ai_executor(state: GameState, target) -> "turn_service.ExecutionOutcome":
    """Bridge the population AI owner into the coordinator's narrow structured
    outcome, mapping the drain's typed result codes truthfully (no swallowing)."""
    try:
        auto = _build_population_auto_processor(state)
        res = _drain_ai_population_turns(state, auto)
    except Exception as exc:  # decider-retrieval throw at the precommit seam
        return turn_service.ExecutionOutcome(
            turn_service.OUTCOME_FAILURE, detail=f"AI_DRAIN_EXCEPTION: {exc}")
    if res.get("success"):
        return turn_service.ExecutionOutcome(turn_service.OUTCOME_ACCEPTED,
                                             command_id="ai-drain")
    code = (res.get("data") or {}).get("reason_code", "")
    if code == "AI_DRAIN_NO_CANDIDATES":
        return turn_service.ExecutionOutcome(
            turn_service.OUTCOME_STRUCTURAL_EMPTY, detail=code)
    return turn_service.ExecutionOutcome(
        turn_service.OUTCOME_FAILURE, detail=code or res.get("message", "AI_DRAIN_FAILED"))


def resolve_population_slice(state: GameState, *,
                             caller_context: Optional[session_access.HotseatContext] = None) -> dict:
    """
    结算人口阶段选举。所有玩家完成后调用。
    返回结构化选举结果，供 GUI 消费。
    """
    # S-B Group 1 (SB-V01): public mutation boundary guard (direct-call coverage).
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="resolve_population_slice",
        caller_context=caller_context)
    if not decision.allowed:
        return decision.denial()
    # W3 / PL-03: registration fact resolved before any business write.
    registered = _registration_state(state)
    if registered is None:
        return _registration_unavailable_response()
    principal = (getattr(caller_context, "principal_player_id", None)
                 if caller_context is not None else None)

    def _resolved_delivery() -> Optional[dict]:
        """W3-ISSUER-03: viewer-bound RESOLVED envelope (SAME_HUMAN)."""
        if not principal:
            return None
        return turn_service.delivery_for_actor(
            state, "population", principal, outcome=turn_service.DELIVERY_OUTCOME_RESOLVED,
            viewer_id=principal,
            command_receipt_ref=turn_service.delivery_command_ref(
                state, "population", "resolve_population_slice", actor=principal))

    if registered and not principal:
        # §2.3-5: no presenting principal -> typed failure, never a forged SAME_HUMAN.
        return api_response(False, "Population resolution requires a presenting principal", {
            "retryable": False,
        }, [{"code": turn_service.DELIVERY_MISSING_RECEIVER, "stage": "receiver",
            "message": "resolution needs its presenting principal"}])
    # S-C (R1 §4.1 / delta §3.3#1): phase_ready is checked at the election-mutation
    # boundary (after the AI drain and the human-completion guard below) — a public
    # resolver denial MUST precede its business mutation.
    if state.get_phase_result("population") is not None:
        existing = state.get_phase_result("population")
        idempotent = {
            "phase_executed": state.is_phase_executed("population"),
            "election_results": existing.get("election_results", []) if existing else [],
        }
        if registered:
            # An already-resolved slice still delivers the SAME viewer-bound
            # confirmation (idempotent repeat, never a second business effect).
            delivery = _resolved_delivery()
            if delivery is not None:
                idempotent["delivery"] = delivery
        return api_response(True, "Population phase already resolved", idempotent)
    # S-C F5 / R-2 / R-4: the readiness gate MUST precede every denied operation's
    # BUSINESS work. A REGISTERED Hot-seat session is checked BEFORE any
    # begin_population_phase / AI drain / disbandment mutation, so a denied
    # resolver commits nothing. Book presence alone is NOT the boundary — the
    # registered Hot-seat record is. A never-registered CLI/legacy state keeps the
    # historical FIX-C ordering + all-human guard below.
    if session_access.is_hotseat_registered(state) \
            and not turn_service.phase_ready(state, "population"):
        return api_response(False, "Population phase not ready", {
            "retryable": True,
        }, [{"code": "PHASE_NOT_READY",
            "message": "All required population ballots must be in before resolution"}])
    try:
        # GUI 人口阶段结算入口：归档必须先于 AI drain（其内部即 get_candidates）
        # （设计 02 §2.2；G3 Q3）。阶段门：仅当当前阶段为 population 才执行（D-6）。
        if _infer_current_phase_id(state) == "population":
            population_api.begin_population_phase(state, caller_context=caller_context)
        influence_before = _faction_influence_rows(state)
        # 先让 AI 自动完成（如果还有未完成的玩家）
        from src.ui.processors.auto_player_processor import AutoPlayerProcessor
        from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
        from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
        from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
        from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
        from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
        from src.core.deciders.impl.auto_vote_decider import AutoVoteDecider
        auto = AutoPlayerProcessor(
            state,
            retirement_decider=AutoRetirementDecider(state),
            recruitment_decider=AutoRecruitmentDecider(),
            bid_decider=AutoBidDecider(),
            triumph_decider=AutoTriumphDecider(),
            festival_decider=AutoFestivalDecider(),
            vote_decider=AutoVoteDecider(),
        )
        ai_drain_result = _drain_ai_population_turns(state, auto, caller_context=caller_context)
        if not ai_drain_result.get("success"):
            return ai_drain_result

        # === FIX-C: Fresh HUMAN completion guard（Amendment v1.1-final）===
        # AI drain 完成后，按当前 state 重新判断 HUMAN 是否全部完成。
        # 使用 Frozen predicate（投票记录覆盖 required offices），
        # 非 AI drain completion marker（stale）。
        if not _all_human_population_votes_complete(state):
            # Per-player 精确判定：用 per-player required.issubset，非全局 predicate
            # FC-D1-01: internal read under the owning masked transaction -> the
            # service-private validated-read boundary (never the public boundary).
            cand_r = population_api._get_candidates_impl(state)
            required = {
                o for o, rows in (cand_r.get("data", {}) if cand_r.get("success") else {}).items() if rows
            }
            votes_by_human = {}
            for pid, office, _fid in state.get_population_votes():
                votes_by_human.setdefault(pid, set()).add(office)
            truly_incomplete = [
                p.player_id for p in state.get_all_players()
                if p.player_type.value == "human"
                and not required.issubset(votes_by_human.get(p.player_id, set()))
            ]
            return api_response(False, "Not all human population votes are complete", {
                "incomplete_players": truly_incomplete,
                "retryable": False,
            }, [
                "VOTE_NOT_ALL_COMPLETE: All human players must complete voting before resolution"
            ])
        # === END FIX-C ===

        # FC-D1-01: internal read under the owning masked transaction -> private impl.
        cand_result = population_api._get_candidates_impl(state)
        candidates_before_resolve = cand_result.get("data", {}) if cand_result.get("success") else {}

        # R2-A-1（AU-R2-2a）：结算尾段以幂等 begin_population_phase 替代独立
        # convert_battlefield_commanders —— archive→convert 全序（P1-1b）无条件先于
        # resolve_election，消除「resolve 前未清档」的间歇 stale office 窗口（R2-04 根因）。
        # 幂等：population_entry marker 守卫——已 archive（顶部 :523 门控已执行）→ 返回
        # cached no-op；未执行 → 此刻归档→转换全序。顶部阶段门控保留，二者互补无双重归档。
        entry = population_api.begin_population_phase(state, caller_context=caller_context)
        conversion_result = {
            "converted": entry.get("converted", []),
            "total": len(entry.get("converted", [])),
        }

        # G1-14 / §11.5（WP-G G4-GD G2）：战后军团/舰队解散生命周期（canonical，幂等
        # marker "population_disbandment"；CLI phase_population._handle_step_0 同一
        # canonical → GUI/CLI 同 mutation 集，S28/S29/S30）。业务事实供 DTO/证据，
        # 不做展示吸收（R-20）。
        disbandment = population_api.process_population_disbandments(state, caller_context=caller_context)

        # 结算选举（archive 已无条件先于 resolve）
        # S-C F5: the readiness gate already ran BEFORE all business work (top of the
        # function); the election mutation is now reached directly.
        resolve_result = population_api.resolve_election(state, caller_context=caller_context)
        if not resolve_result:
            return api_response(False, "Election resolve returned None")

        raw_result = resolve_result.get("data", {}) or {}
        structured = raw_result.get("election_results") or _population_election_results_from_state(state)
        influence_after = _faction_influence_rows(state)
        data = {
            "election_results": structured,
            "candidates": candidates_before_resolve,
            "faction_influence_before": influence_before,
            "faction_influence_after": influence_after,
            "raw_result": raw_result,
            "battlefield_commander_conversion": conversion_result,
            "disbandment": disbandment,
        }

        # Two-step pattern: resolve records result, does NOT mark phase executed
        state.record_phase_result("population", {
            "success": True,
            "message": "Election resolved",
            "data": data,
        })
        logger.info("Population phase resolved", extra={"results": structured})
        if registered:
            delivery = _resolved_delivery()
            if delivery is not None:
                data["delivery"] = delivery
        return api_response(True, "Election resolved", data)
    except Exception as e:
        logger.exception("Population resolution failed")
        return api_response(False, f"Population resolution failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 6. 人口阶段推进
# ---------------------------------------------------------------------------

def advance_population_phase(state: GameState, viewer_player_id: str, *,
                             caller_context: Optional[session_access.HotseatContext] = None) -> dict:
    """Confirm population result and advance to Senate phase.

    Failure semantics:
    - If phase not yet resolved (no result) -> return failure, no state change
    - If not current player -> return failure, no state change
    - If already executed -> return failure, no duplicate state change
    - If current phase is not population -> return failure
    """
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    # W3 / PL-03: resolve the registration fact BEFORE any business write. An
    # UNKNOWN (raised / non-bool) read is a typed fail-closed refusal.
    registered = _registration_state(state)
    if registered is None:
        return _registration_unavailable_response()

    # S-B Group 1 (SB-V01): public mutation boundary guard (direct-call coverage).
    decision = session_access.authorize_public(
        state, session_access.OP_MUTATE, command="advance_population_phase",
        target_player_id=viewer_player_id, caller_context=caller_context)
    if not decision.allowed:
        return decision.denial()

    # Guard: phase not yet executed (prevents double-advance)
    if state.is_phase_executed("population"):
        return api_response(False, "Population phase already executed")

    # Guard: correct current phase
    current_phase_id = _infer_current_phase_id(state)
    if current_phase_id != "population":
        return api_response(False, f"Current phase is {current_phase_id}, not population")

    # Guard: active player check
    if not state.is_current_player(viewer_player_id):
        return api_response(False, "Viewer is not the active player")

    # Guard: result must exist (cannot advance unresolved phase)
    result = state.get_phase_result("population")
    if not result:
        return api_response(False, "Population phase has not been resolved")

    # Perform the advance (single state mutation point)
    state.mark_phase_executed("population")
    # D4/D6 I2 item2 (FC-D46-04): the phase-advance OWING command's commit hook
    # ISSUES the committed entry receipt AFTER the real mark and BEFORE returning
    # to the adapter (the ONLY issuer of a service-private committed receipt).
    entry_receipt = turn_service.issue_committed_phase_entry_receipt(
        state, command_id="advance_population_phase", phase="senate",
        payload_digest=str(viewer_player_id))
    data = {
        "phase_executed": True,
        "next_phase_id": "senate",
        "result": result,
        "entry_receipt": entry_receipt,
    }
    if not registered:
        # D-W3-D16 / AC-W3-21: a never-registered CLI/legacy state keeps the
        # historical response byte-for-byte (no new keys, no continuation).
        return api_response(True, "Population phase advanced", data)

    # W3-ISSUER-01 / §4.2: consume the committed entry EXACTLY ONCE (new senate
    # scope) BEFORE the single continuation. Order is not exchangeable.
    entered = turn_service.enter_phase(state, entry_receipt)
    if not entered.get("success"):
        reason = str(entered.get("reason") or "ENTRY_FAILED")
        error = turn_service.delivery_error(
            "COMMITTED_ENTRY_FAILED", stage="phase_entry", committed=True,
            retry_class=turn_service.DELIVERY_RETRY_NONE, detail=reason)
        failure_data = dict(data)
        failure_data["delivery_error"] = error
        return api_response(False, "Senate phase entry failed", failure_data, [{
            "code": "COMMITTED_ENTRY_FAILED", "stage": "phase_entry",
            "message": reason,
        }])
    from src.api import senate_api
    cont = turn_service.continue_after_command(
        state, ai_executor=senate_api._senate_ai_executor)
    if cont.masked_failure:
        error = turn_service.delivery_error(
            "COMMITTED_CONTINUATION_FAILED", stage="continuation", committed=True,
            retry_class=turn_service.DELIVERY_RETRY_NONE,
            detail=str(cont.reason or "CONTINUATION_FAILED"))
        failure_data = dict(data)
        failure_data["delivery_error"] = error
        failure_data["retryable"] = True
        return api_response(False, "Senate continuation failed", failure_data, [{
            "code": "COMMITTED_CONTINUATION_FAILED", "stage": "continuation",
            "message": str(cont.reason or "CONTINUATION_FAILED"),
        }])
    delivery = turn_service.delivery_from_continuation(
        state, "senate", cont, viewer_id=viewer_player_id,
        command_receipt_ref=turn_service.delivery_command_ref(
            state, "senate", "advance_population_phase", actor=viewer_player_id))
    data["delivery"] = delivery
    if delivery.get("next"):
        nxt = delivery["next"]
        data["awaiting_player_id"] = (
            nxt.get("actor_player_id")
            if nxt.get("controller") == turn_service.CONTROLLER_HUMAN else None)
    return api_response(True, "Population phase advanced", data)


# ---------------------------------------------------------------------------
# 7. 决算阶段视图
# ---------------------------------------------------------------------------

def get_resolution_view(state: GameState, viewer_player_id: str, *,
                        caller_context: Optional[session_access.HotseatContext] = None) -> dict:
    # S-B Group 1: active-seat read guard before any public/private DTO build.
    """
    返回决算阶段的只读视图 DTO。

    仅包含业务事实，不包含 Store 私有状态。
    can_advance / is_advancing 由 Store 组合，API 不返回。

    WP-E-G7R（D2 §4.2）：resolved 单源化 = is_phase_executed("resolution")——
    advance 后 executed_phases 已清空 → resolved=False → 新年入口自动结算可靠触发
    （消除跨年毒化）；settlement read-model 仅保留为 EC-10 parity 源，不再参与门控。
    preview = _build_resolution_preview 只读投影（直连 _plan_*，R-23，零变异 EC-01），
    四信息类目（总督返回/合同到期/和约到期/派系聚合衰减），不再提供 step_statuses 顺序工作流。
    """
    # S-B Group 1: active-seat read guard before any public/private DTO build.
    denied = session_access.denied_or_none(
        state, session_access.OP_READ_PHASE_VIEW, viewer=viewer_player_id,
        caller_context=caller_context)
    if denied is not None:
        return denied
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        # resolved 单源化（D2 §4.2）：仅 is_phase_executed；settlement 不再参与门控
        resolved = state.is_phase_executed("resolution")

        # 只读年度预览投影（每次重算，确定性、零变异）
        preview = _build_resolution_preview(state)

        # 结算结果（read-model 事实；treasury_before/after 降为内部 parity/审计字段，无可见消费者）
        if resolved:
            results = _build_resolution_results(state)
        else:
            results = _empty_resolution_results()

        # 风险警告（F4：权威现状扫描，不进 read-model；结算后展示）
        warnings = _build_resolution_warnings(state) if resolved else []

        # 年度总结
        if resolved:
            summary = _build_resolution_summary(state)
        else:
            summary = _empty_resolution_summary()

        data = {
            "resolved": resolved,
            "preview": preview,
            "results": results,
            "warnings": warnings,
            "summary": summary,
            "is_current_player": state.is_current_player(viewer_player_id),
        }
        return api_response(True, "Resolution view", data)
    except Exception as e:
        logger.exception("Resolution view failed")
        return api_response(False, f"Resolution view failed: {e}", errors=[str(e)])


def _build_resolution_preview(state: GameState) -> dict:
    """只读 year-end 投影（D3 §1/§2 + ODR-C1）。

    - 直连 state._plan_settlement()（共享规划语义，R-23：无第二套实现）；
      只读字段读取 + 命名富化，零变异（EC-01，测试锁定等价快照）。
    - 唯一判定谓词 governor return guard = old_fig is not None and not old_fig.is_dead
      （1 行布尔，与 _apply_governor_transitions 同语义，注释锁定 + parity EC-10）。
    - faction_influence = decay-only 聚合（ODR-C1）：before/after/delta 仅反映衰减分量
      （veterans/popularity/temp_tasks 衰减后的影响力重算）；office/land/family 恒定，
      不叠加总督交接影响（交接归「总督返回」类目）。
    """
    plan = state._plan_settlement()

    # 1. 总督返回（A6 规划；guard 对齐 _apply_governor_transitions :1621-1666）
    governor_returns = []
    for t in plan["governor_transitions"]:
        old_fig = t["old_fig"]
        if old_fig is None or old_fig.is_dead:
            continue
        province = t["province"]
        designate = t["designate"]
        governor_returns.append({
            "province_id": province.province_id,
            "province_name": province.name,
            "governor_name": old_fig.get_formal_name(),
            "successor_name": (
                designate.get_formal_name()
                if (t["promote"] and designate is not None) else None
            ),
        })

    # 2. 合同到期（A5 规划，身份行——禁仅计数 005-03）
    contract_expiries = [
        {
            "contract_id": c.id,
            "name": c.name,
            "contract_type": c.contract_type.name,
        }
        for c in plan["contracts_to_expire"]
    ]

    # 3. 和约到期（A7 和约到期恢复（G3C）：plan 含 "truce_expiries" 键，到期 → THREAT；
    #    类目供 DTO 稳定）
    truce_expiries = [{"war_name": w.name} for w in plan.get("truce_expiries", [])]

    # 4. 派系聚合影响力（decay-only，ODR-C1；每派系恒一行）
    member_updates = plan["member_updates"]
    faction_influence = []
    for faction in state.factions.values():
        members = [m for m in state.get_living_members() if m.faction_id == faction.id]
        before_total = 0
        after_total = 0
        for m in members:
            before_total += getattr(m, "influence", 0) or 0
            target = member_updates.get(m.id)
            if target is None:
                veterans_after = m.veterans
                popularity_after = m.popularity
                temp_tasks = m._temp_influence_tasks
                temp_after = m.get_temp_influence()
            else:
                veterans_after = target["veterans"]
                popularity_after = target["popularity"]
                temp_tasks = target["temp_influence_tasks"]
                temp_after = sum(t["per_turn"] for t in temp_tasks)
            after_total += _compute_influence(
                m.land_private,
                veterans_after,
                popularity_after,
                m.family_prestige,
                m.get_office_influence_bonus(),
                temp_after,
                getattr(m, "_war_reward_influence", 0),
            )
        delta = after_total - before_total
        faction_influence.append({
            "faction_id": faction.id,
            "faction_name": faction.name,
            "influence_before": before_total,
            "influence_after": after_total,
            "influence_delta": delta,
        })

    return {
        "governor_returns": governor_returns,
        "contract_expiries": contract_expiries,
        "truce_expiries": truce_expiries,
        "faction_influence": faction_influence,
    }


def _build_resolution_results(state: GameState) -> dict:
    """从 read-model 提取结算结果（WP-E R-2/F2）。

    四步骤事件行全部有 read-model 源（governor_returns / contract_expiries /
    truce_expiries / decay + treasury_before/after）；预结算（无 read-model）→
    四步骤字段全空，但 S2（victory/legion_recovery/key_events）仍由
    execute_resolution phase result 提供（预结算即权威已发生事实）。
    """
    settlement = state.get_resolution_settlement()

    if settlement:
        governor_transitions = [
            {
                "province": row.get("province_name"),
                "old_governor": row.get("old_governor_name"),
                "governor": row.get("new_governor_name"),
                "promoted": row.get("new_governor_id") is not None,
            }
            for row in settlement.get("governor_returns", [])
        ]
        contract_expiries = settlement.get("contract_expiries", [])
        truce_expired = settlement.get("truce_expiries", [])
        decay = settlement.get("decay", [])
    else:
        governor_transitions = []
        contract_expiries = []
        truce_expired = []
        decay = []

    # 元老院主导派系
    total_influence = 0
    faction_infos = []
    for faction in state.factions.values():
        inf = 0
        for mid in faction.member_ids:
            member = state.get_member(mid)
            if member:
                inf += getattr(member, "influence", 0)
        total_influence += inf
        faction_infos.append({"id": faction.id, "name": faction.name, "influence": inf})

    dominant_faction = None
    if total_influence > 0 and faction_infos:
        top = max(faction_infos, key=lambda x: x["influence"])
        dominant_faction = {
            "id": top["id"],
            "name": top["name"],
            "influence_share": round(top["influence"] / total_influence, 4),
        }

    # 军团状态
    legion_status = "active"
    ms = state.get_military_system()
    if ms:
        all_legions = ms.get_all_legions()
        if all_legions and all(
            getattr(l, "status", None) is not None
            and getattr(l.status, "name", str(l.status)) == "DESTROYED"
            for l in all_legions
        ):
            legion_status = "destroyed"

    result = {
        # D10 §3 disposition：settled 键移除（无可见消费者；resolved 单源化后不复需要）
        "settled_year": settlement.get("settled_year") if settlement else None,
        "next_year": settlement.get("next_year") if settlement else None,
        # treasury_before/after：内部 parity/审计字段（EC-10 比对源），非可见消费者，不做展示
        "treasury_before": settlement.get("treasury_before") if settlement else None,
        "treasury_after": settlement.get("treasury_after") if settlement else None,
        # 四步 read-model 行：内部 parity 源（EC-10 比对对象），不删除（D2 §4.2）
        "governor_transitions": governor_transitions,
        "contract_expiries": contract_expiries,
        "contracts_expired": len(contract_expiries),
        "truce_expired": truce_expired,
        "decay": decay,
        "dominant_faction": dominant_faction,
        "treasury": state.treasury,
        "legion_status": legion_status,
    }

    # S2: 决算结果 DTO（来自 execute_resolution 存储的 phase result）
    resolution_dto = state.get_phase_result("resolution")
    if resolution_dto:
        result["victory"] = resolution_dto.get("victory", {})
        result["legion_recovery"] = resolution_dto.get("legion_recovery", {})
        result["key_events"] = resolution_dto.get("key_events", [])
        result["events_cleared"] = resolution_dto.get("events_cleared", False)

    return result


def _empty_resolution_results() -> dict:
    return {
        "settled_year": None,
        "next_year": None,
        "treasury_before": None,
        "treasury_after": None,
        "governor_transitions": [],
        "contract_expiries": [],
        "contracts_expired": 0,
        "truce_expired": [],
        "decay": [],
        "dominant_faction": None,
        "treasury": 0,
        "legion_status": "unknown",
        "victory": {"game_over": False, "conditions": [], "summary": {}},
        "legion_recovery": {"recovered": 0, "recovered_ids": [], "details": ""},
        "key_events": [],
        "events_cleared": False,
    }


def _build_resolution_warnings(state: GameState) -> list:
    """从当前游戏状态提取风险警告。"""
    warnings = []

    # 国库赤字检查
    if state.treasury < 0:
        level = "critical" if state.treasury <= -50 else "warning"
        warnings.append({
            "level": level,
            "message": f"国库赤字：{state.treasury} 第纳尔",
        })

    # 派系独裁风险检查
    total_inf = 0
    faction_infos = []
    for faction in state.factions.values():
        inf = 0
        for mid in faction.member_ids:
            member = state.get_member(mid)
            if member:
                inf += getattr(member, "influence", 0)
        total_inf += inf
        faction_infos.append({"name": faction.name, "influence": inf})

    if total_inf > 0:
        for fi in faction_infos:
            share = fi["influence"] / total_inf
            if share >= 0.7:
                warnings.append({
                    "level": "critical",
                    "message": f"{fi['name']} 影响力 {share:.1%}，独裁风险！",
                })
            elif share >= 0.5:
                warnings.append({
                    "level": "warning",
                    "message": f"{fi['name']} 影响力 {share:.1%}，接近绝对多数",
                })

    return warnings


def _build_resolution_summary(state: GameState) -> dict:
    """从游戏状态提取年度总结（WP-E R-2：next_year / decay_details 由 read-model 驱动）。"""
    settlement = state.get_resolution_settlement()

    # 元老院主导派系
    total_influence = 0
    faction_infos = []
    for faction in state.factions.values():
        inf = 0
        for mid in faction.member_ids:
            member = state.get_member(mid)
            if member:
                inf += getattr(member, "influence", 0)
        total_influence += inf
        faction_infos.append({"id": faction.id, "name": faction.name, "influence": inf})

    dominant = None
    if total_influence > 0 and faction_infos:
        top = max(faction_infos, key=lambda x: x["influence"])
        dominant = {
            "id": top["id"],
            "name": top["name"],
            "influence_share": round(top["influence"] / total_influence, 4),
        }

    # 年份显示（next_year 优先 read-model）
    current_year = state.turn.year if state.turn else 0
    next_year = settlement.get("next_year") if settlement else (current_year + 1)
    next_year_display = _format_year(next_year)

    # 衰减状态（decay_applied = read-model 存在；decay_details = 派系聚合描述，R-21 禁 per-figure dump）
    decay_applied = settlement is not None
    preview = _build_resolution_preview(state)
    changed_factions = [
        f for f in preview["faction_influence"]
        if f["influence_delta"] != 0
    ]
    decay_details = (
        f"{len(changed_factions)} 个派系受到年度衰减"
        if changed_factions else "无派系影响力变化"
    )

    return {
        "dominant_faction": dominant,
        "treasury": state.treasury,
        "next_year": next_year_display,
        "decay_applied": decay_applied,
        "decay_details": decay_details,
        "current_year": _format_year(current_year),
    }


def _empty_resolution_summary() -> dict:
    return {
        "dominant_faction": None,
        "treasury": 0,
        "next_year": "",
        "decay_applied": False,
        "decay_details": "",
        "current_year": "",
    }


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _format_year(year: int) -> str:
    if year < 0:
        return f"{abs(year)} BC"
    return f"{year} AD"


def _phase_name(phase_id: str) -> str:
    return _phase_definition_map().get(phase_id, {}).get("name", phase_id)


def _phase_order() -> List[str]:
    return ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]


def _implemented_phase_ids() -> set:
    return {"mortality", "revenue", "forum", "population", "senate", "combat", "resolution"}


def _phase_interaction_mode(phase_id: str) -> str:
    if phase_id in {"mortality", "revenue", "forum", "population", "senate", "combat", "resolution"}:
        return "interactive"
    return "placeholder"


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in _phase_order():
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


def _faction_influence_rows(state: GameState) -> List[Dict[str, Any]]:
    rows = []
    for faction in state.factions.values():
        members = [m for m in state.get_living_members() if m.faction_id == faction.id]
        rows.append({
            "id": faction.id,
            "name": faction.name,
            "short_name": _faction_short_name(faction.name),
            "total_influence": sum(m.influence for m in members),
        })
    return rows


def _faction_short_name(name: str) -> str:
    mapping = {
        "Optimates": "Opt",
        "Populares": "Pop",
        "Equites": "Equ",
    }
    return mapping.get(name, name[:3])


def _population_election_results_from_state(state: GameState) -> List[Dict[str, Any]]:
    office_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
    results: List[Dict[str, Any]] = []
    for office in office_order:
        winners = [
            fig for fig in state.get_living_members()
            if getattr(fig, "office", "") == office
        ]
        for winner in winners:
            faction = state.get_faction(winner.faction_id) if winner.faction_id else None
            results.append({
                "office": office,
                "office_name": _office_name(office),
                "figure_id": winner.id,
                "figure_name": winner.get_formal_name(),
                "faction_id": winner.faction_id,
                "faction_name": faction.name if faction else "",
                "faction_short_name": _faction_short_name(faction.name) if faction else "",
            })
    return results


def _office_name(office: str) -> str:
    names = {
        "consul": "执政官",
        "censor": "监察官",
        "praetor": "大法官",
        "quaestor": "财务官",
        "tribune": "保民官",
    }
    return names.get(office, office)


def _phase_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "id": "mortality",
            "name_key": "phase.mortality.name",
            "subtitle_key": "phase.mortality.subtitle",
            "description_key": "phase.mortality.description",
            "name": "天命",
            "subtitle": "死亡、继承与年度开端",
            "description": "抽取天命事件并应用死亡、丰收、和平、猛男或灾害等年度影响。",
            "handoff_task": "GUI-P0-02B",
        },
        {
            "id": "revenue",
            "name_key": "phase.revenue.name",
            "subtitle_key": "phase.revenue.subtitle",
            "description_key": "phase.revenue.description",
            "name": "收入",
            "subtitle": "国家收入、维护费与派系分配",
            "description": "GUI-P0-03 已实现收入结算切片。结算国家收入与支出，整理派系财政，确认国库变动。",
            "handoff_task": "GUI-P0-03",
        },
        {
            "id": "forum",
            "name_key": "phase.forum.name",
            "subtitle_key": "phase.forum.subtitle",
            "description_key": "phase.forum.description",
            "name": "广场",
            "subtitle": "招募、裁员、土地与公共行动",
            "description": "广场阶段将在 GUI-P0-02D 承接。本轮不执行广场业务操作。",
            "handoff_task": "GUI-P0-03",
        },
        {
            "id": "population",
            "name_key": "phase.population.name",
            "subtitle_key": "phase.population.subtitle",
            "description_key": "phase.population.description",
            "name": "人口",
            "subtitle": "庆典、公职投票与选举",
            "description": "GUI-P0-01 已实现的人口阶段真实切片，可继续举办庆典、投票并完成玩家操作。",
            "handoff_task": "GUI-P0-02B",
        },
        {
            "id": "senate",
            "name_key": "phase.senate.name",
            "subtitle_key": "phase.senate.subtitle",
            "description_key": "phase.senate.description",
            "name": "元老院",
            "subtitle": "执政官提案 → 元老院表决 → 保民官否决",
            "description": "执政官提案 → 元老院表决 → 保民官否决 → 法案公示与政府运作。",
            "handoff_task": "GUI-P0-02C",
        },
        {
            "id": "combat",
            "name_key": "phase.combat.name",
            "subtitle_key": "phase.combat.subtitle",
            "description_key": "phase.combat.description",
            "name": "战争",
            "subtitle": "陆战、海战与战役结果",
            "description": "战争阶段将在 GUI-P0-02E 承接。海战信息将在该阶段后续切片中呈现，本轮不执行战争结算。",
            "handoff_task": "GUI-P0-02E",
        },
        {
            "id": "resolution",
            "name_key": "phase.resolution.name",
            "subtitle_key": "phase.resolution.subtitle",
            "description_key": "phase.resolution.description",
            "name": "决算",
            "subtitle": "革命检查、年度决算与回合推进",
            "description": "决算阶段将在 GUI-P0-02F 承接。革命检查保留为后续决算切片内容，本轮不推进回合。",
            "handoff_task": "GUI-P0-02F",
        },
    ]


def _phase_definition_map() -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in _phase_definitions()}


def _build_phase_navigation(state: GameState, current_phase_id: str, viewer_player_id: str) -> List[Dict[str, Any]]:
    phase_nav = []
    for index, definition in enumerate(_phase_definitions(), start=1):
        phase_id = definition["id"]
        implemented = phase_id in _implemented_phase_ids()
        interaction_mode = _phase_interaction_mode(phase_id)
        current = phase_id == current_phase_id
        actionable = interaction_mode == "interactive" and current and state.is_current_player(viewer_player_id)
        disabled_reason = ""
        disabled_reason_key = ""
        if not implemented:
            disabled_reason_key = "phase.disabled.placeholder"
            disabled_reason = f"{definition['handoff_task']} 后续任务承接，当前暂不可操作"
        elif interaction_mode == "readonly":
            disabled_reason_key = "phase.disabled.readonly"
            disabled_reason = "当前不是元老院阶段或当前行动玩家，暂不可操作"
        elif not current:
            disabled_reason_key = "phase.disabled.not_current"
            disabled_reason = "该阶段不是当前阶段，暂不可操作"
        elif not state.is_current_player(viewer_player_id):
            disabled_reason_key = "phase.disabled.not_player"
            disabled_reason = "当前 viewer 不是行动玩家，暂不可操作"
        phase_nav.append({
            "id": phase_id,
            "index": index,
            "name_key": definition["name_key"],
            "subtitle_key": definition["subtitle_key"],
            "description_key": definition["description_key"],
            "status_key": "phase.status.current" if current else ("phase.status.completed" if state.is_phase_executed(phase_id) else "phase.status.placeholder"),
            "name": definition["name"],
            "subtitle": definition["subtitle"],
            "description": definition["description"],
            "status": "current" if current else ("completed" if state.is_phase_executed(phase_id) else "placeholder"),
            "implemented": implemented,
            "interaction_mode": interaction_mode,
            "enabled": True,
            "actionable": actionable,
            "handoff_task": definition["handoff_task"],
            "disabled_reason_key": disabled_reason_key,
            "disabled_reason": disabled_reason,
            "locked_reason": "" if implemented else f"{definition['name']}阶段尚未迁移到 GUI",
            "executed": state.is_phase_executed(phase_id),
            "current": current,
            "locked": False,
        })
    return phase_nav


def _build_phase_summary(phase_id: str, state: Optional[GameState] = None, viewer_player_id: str = "") -> Dict[str, Any]:
    definition = _phase_definition_map().get(phase_id, {})
    implemented = phase_id in _implemented_phase_ids()
    interaction_mode = _phase_interaction_mode(phase_id)
    current = state is not None and phase_id == _infer_current_phase_id(state)
    actionable = bool(
        interaction_mode == "interactive"
        and current
        and viewer_player_id
        and state
        and state.is_current_player(viewer_player_id)
    )
    disabled_reason = ""
    disabled_reason_key = ""
    if not implemented:
        disabled_reason_key = "phase.disabled.placeholder"
        disabled_reason = f"{definition.get('handoff_task', '后续任务')} 承接，本轮不会改变游戏状态"
    elif interaction_mode == "readonly":
        disabled_reason_key = "phase.disabled.readonly"
        disabled_reason = "当前不是元老院阶段或当前行动玩家，暂不可操作"
    elif not current:
        disabled_reason_key = "phase.disabled.not_current"
        disabled_reason = "该阶段不是当前阶段，暂不可操作"
    elif state and viewer_player_id and not state.is_current_player(viewer_player_id):
        disabled_reason_key = "phase.disabled.not_player"
        disabled_reason = "当前 viewer 不是行动玩家，暂不可操作"
    return {
            "id": phase_id,
            "name_key": definition.get("name_key", ""),
            "subtitle_key": definition.get("subtitle_key", ""),
            "description_key": definition.get("description_key", ""),
            "status_key": "phase.status.actionable" if actionable else (
                "phase.status.readonly" if interaction_mode == "readonly" else (
                    "phase.status.ready" if implemented else "phase.status.placeholder"
                )
            ),
            "disabled_reason_key": disabled_reason_key,
            "name": definition.get("name", phase_id),
            "subtitle": definition.get("subtitle", ""),
            "description": definition.get("description", ""),
        "implemented": implemented,
        "interaction_mode": interaction_mode,
        "actionable": actionable,
        "handoff_task": definition.get("handoff_task", ""),
        "status_text": "可操作真实切片" if actionable else (
            "已接入只读 / 后续子任务接入操作" if interaction_mode == "readonly" else (
                "已接入 / 等待正确阶段或玩家" if implemented else "后续任务承接 / 暂不可操作"
            )
        ),
        "disabled_reason": disabled_reason,
    }


def _build_global_warnings(state: GameState, viewer_player_id: str) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = [{
        "type": "info",
        "key": "warning.gui_p0_05.senate_phase5a",
        "message": "GUI-P0-05 已开放元老院 Phase 5A 执政官提案；表决、否决与结算按子环节逐步验收。",
    }]
    if not state.is_current_player(viewer_player_id):
        warnings.append({
            "type": "warning",
            "key": "warning.viewer.not_current_player",
            "message": "当前 viewer 不是行动玩家，操作入口将保持受限。",
        })
    return warnings


def _build_available_actions(state: GameState, viewer_player_id: str) -> List[str]:
    """当前玩家可执行的动作列表"""
    if not state.is_current_player(viewer_player_id):
        return []
    actions = []
    current_phase_id = _infer_current_phase_id(state)
    if current_phase_id == "mortality" and not state.is_phase_executed("mortality"):
        actions.append("execute_mortality")
    if current_phase_id == "population" and not state.is_phase_executed("population"):
        actions.append("campaign")
        actions.append("vote")
        actions.append("complete_player")
    if current_phase_id == "forum" and not state.is_phase_executed("forum"):
        actions.append("retire_figure")
        actions.append("recruit_figure")
        actions.append("place_bid")
        actions.append("buy_land")
        actions.append("vote_triumph")
        actions.append("resolve_forum")
    return actions


def _build_population_progress(state: GameState, viewer_player_id: str) -> dict:
    """人口阶段进度"""
    votes = state.get_population_votes()
    my_votes = [v for v in votes if v[0] == viewer_player_id]
    campaigns = state.get_population_campaigns()
    my_campaigns = [c for c in campaigns if c[0] == viewer_player_id]
    return {
        "campaigns_done": len(my_campaigns),
        "votes_done": len(my_votes),
        "total_offices": 5,
    }
