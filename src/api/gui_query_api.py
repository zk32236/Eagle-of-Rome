"""Read-only GUI global query API.

This module is intentionally thin and read-only. It builds typed, safe DTOs for
the GUI bottom query bar. It never imports CLI commands, never mutates game
state and never triggers RNG.

EOR20261011-01 S1 (frozen design v1.2 / v1.1):
- single compatible seam ``get_global_query_result(state, viewer_player_id,
  query_id, filter_text="", record_id="")`` (A05-01);
- the per-viewer record/field allowlist is projected **before** any DTO is
  constructed/searched/formatted, recursively across every DTO layer
  (items / summary / meta / detail / errors / message_params) (A05-03, FC-04);
- typed ``result_state in {"OK","EMPTY"}`` on success, ``success=False`` for
  DENIED/ERROR typed shells — **never** placeholder-as-success (A05-02, A05-07);
- exhaustive failure taxonomy (A05-07 / v1.1 §5.1);
- ``figure_search`` list / single-dimension substring filter / record detail
  (FC-06); no ID authorization bypass.
"""

import logging
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from src.api import api_response
from src.api import session_access
from src.core.game_state import GameState
from src.core.entities.player import PlayerType

logger = logging.getLogger("EOR-GUI")

# ---------------------------------------------------------------------------
# Canonical twelve query ids (canonical left->right order)
# ---------------------------------------------------------------------------
CANONICAL_QUERY_IDS: List[str] = [
    "faction_info",
    "figure_search",
    "game_status",
    "faction_treasury",
    "public_land",
    "private_land",
    "contract_status",
    "province_info",
    "war_list",
    "legion_status",
    "fleet_status",
    "help",
]

_QUERY_TITLE_KEYS = {
    "game_status": "query.game_status.title",
    "faction_info": "query.faction_info.title",
    "war_list": "query.war_list.title",
    "legion_status": "query.legion_status.title",
    "figure_search": "query.figure_search.title",
    "faction_treasury": "query.faction_treasury.title",
    "public_land": "query.public_land.title",
    "private_land": "query.private_land.title",
    "contract_status": "query.contract_status.title",
    "province_info": "query.province_info.title",
    "fleet_status": "query.fleet_status.title",
    "help": "query.help.title",
}

_QUERY_TITLES = {
    "game_status": "游戏状态",
    "faction_info": "派系信息",
    "war_list": "战争列表",
    "legion_status": "军团状态",
    "figure_search": "人物查询",
    "faction_treasury": "派系金库",
    "public_land": "公地信息",
    "private_land": "私地信息",
    "contract_status": "合同状态",
    "province_info": "行省信息",
    "fleet_status": "舰队状态",
    "help": "帮助",
}

# ---------------------------------------------------------------------------
# Fixed safe failure enums (never raw exception strings / uncontrolled text)
# ---------------------------------------------------------------------------
ERR_STATE_UNAVAILABLE = "state_unavailable"
ERR_VIEWER_UNAVAILABLE = "viewer_unavailable"
ERR_UNKNOWN_QUERY = "unknown_query"
ERR_INVALID_REQUEST = "invalid_request"
ERR_SYSTEM_UNAVAILABLE = "system_unavailable"
ERR_RECORD_UNAVAILABLE = "record_unavailable"
ERR_QUERY_FAILED = "query_failed"
ERR_QUERY_UNAVAILABLE = "query_unavailable"
ERR_NOT_IMPLEMENTED = "not_implemented"

_ERROR_MESSAGE_KEYS = {
    ERR_STATE_UNAVAILABLE: "query.error.state_unavailable",
    ERR_VIEWER_UNAVAILABLE: "query.error.viewer_unavailable",
    ERR_UNKNOWN_QUERY: "query.error.unknown_query",
    ERR_INVALID_REQUEST: "query.error.invalid_request",
    ERR_SYSTEM_UNAVAILABLE: "query.error.system_unavailable",
    ERR_RECORD_UNAVAILABLE: "query.error.record_unavailable",
    ERR_QUERY_FAILED: "query.error.query_failed",
    ERR_QUERY_UNAVAILABLE: "query.error.query_unavailable",
    ERR_NOT_IMPLEMENTED: "query.error.not_implemented",
}

# Safe, fixed zh-CN copy mirroring ``data/i18n/zh-CN.json`` query.error.* keys.
# The DTO also carries ``message_key`` so the shell localises independently.
_ERROR_MESSAGES_ZH = {
    ERR_STATE_UNAVAILABLE: "无效的游戏状态",
    ERR_VIEWER_UNAVAILABLE: "当前查看者不可用",
    ERR_UNKNOWN_QUERY: "未知查询",
    ERR_INVALID_REQUEST: "查询参数无效",
    ERR_SYSTEM_UNAVAILABLE: "所需系统暂不可用",
    ERR_RECORD_UNAVAILABLE: "该记录不可用",
    ERR_QUERY_FAILED: "查询失败",
    ERR_QUERY_UNAVAILABLE: "查询处理中，请稍后再试",
    ERR_NOT_IMPLEMENTED: "该查询将在后续版本接入",
}

# Per-query capabilities (exact §5.3 / v1.2 §4 table). ``selector`` is the wire
# grammar of the list selector: None / "string" / "decimal".
_QUERY_SPECS: Dict[str, Dict[str, Any]] = {
    "faction_info": {"can_filter": True, "can_detail": True, "selector": "string"},
    "figure_search": {"can_filter": True, "can_detail": True, "selector": "decimal"},
    "game_status": {"can_filter": False, "can_detail": False, "selector": None},
    "faction_treasury": {"can_filter": False, "can_detail": False, "selector": None},
    "public_land": {"can_filter": False, "can_detail": False, "selector": None},
    "private_land": {"can_filter": True, "can_detail": True, "selector": "decimal"},
    "contract_status": {"can_filter": True, "can_detail": True, "selector": "decimal"},
    "province_info": {"can_filter": True, "can_detail": True, "selector": "decimal"},
    "war_list": {"can_filter": True, "can_detail": True, "selector": "string"},
    "legion_status": {"can_filter": True, "can_detail": True, "selector": "decimal"},
    "fleet_status": {"can_filter": True, "can_detail": True, "selector": "decimal"},
    "help": {"can_filter": False, "can_detail": False, "selector": None},
}

# Canonical decimal wire grammar (v1.1 §5.3): no signs, whitespace, leading
# zeroes or fractional forms; exact equality with ``str(canonical_integer)``.
# ``fullmatch`` anchors the WHOLE string, so a trailing newline (which ``$``
# would otherwise accept before a final "\n") is rejected (F1).
_DECIMAL_RE = re.compile(r"[1-9][0-9]*")

# ---------------------------------------------------------------------------
# S3 — help read-only operation guidance (FC-10 / SA v1.1 §6.2 help)
# ---------------------------------------------------------------------------
# Fixed guidance ids. Each renders as topic label key ``query.help.guide.<id>``
# + instruction value key ``query.help.guide.<id>.value``. Never a CLI
# debug/force/executable command (help U fields absent).
_HELP_GUIDE_IDS: List[str] = ["usage", "filter", "detail", "back", "close", "readonly"]

# Safe zh-CN fallback copy (display authority = the ``data/i18n/*.json`` key).
_HELP_GUIDE_ZH = {
    "usage": "使用方式",
    "filter": "筛选",
    "detail": "详情",
    "back": "返回",
    "close": "关闭",
    "readonly": "只读说明",
}


# ===========================================================================
# Public seam (A05-01)
# ===========================================================================
def get_global_query_result(
    state: GameState,
    viewer_player_id: str,
    query_id: str,
    filter_text: str = "",
    record_id: str = "",
    *,
    caller_context=None,
) -> dict:
    """Return one safe read-only typed DTO for the GUI global query bar.

    Backwards compatible: the original three positional callers remain legal.
    Never raises; every failure is a typed ``success=False`` shell.
    """
    # -- 1. state boundary --------------------------------------------------
    if state is None:
        return api_response(
            False, _ERROR_MESSAGES_ZH[ERR_STATE_UNAVAILABLE],
            build_failure_dto("", "ERROR", ERR_STATE_UNAVAILABLE),
        )

    # -- 1b. active-seat access guard (S-B Group 1) -------------------------
    # Registered Hot-seat session: a non-current / unauthorized viewer is denied
    # BEFORE any query/existence lookup, with the CLOSED typed safe shell
    # (result_state=DENIED, whitelisted viewer_unavailable) — no raw backend
    # reason, no record-existence leak. Un-registered (CLI/historical) states are
    # exempt and behave exactly as before. The CLOSED DTO redaction/receiver ack
    # contract is unchanged.
    if not session_access.present_decision(
            state, session_access.OP_READ_QUERY, viewer=viewer_player_id,
            caller_context=caller_context).allowed:
        return api_response(
            False, _ERROR_MESSAGES_ZH[ERR_VIEWER_UNAVAILABLE],
            build_failure_dto(query_id, "DENIED", ERR_VIEWER_UNAVAILABLE),
        )

    # -- 2. viewer eligibility (A05-04) ------------------------------------
    if not isinstance(viewer_player_id, str) or not viewer_player_id:
        return api_response(
            False, "Viewer player not found",
            build_failure_dto(query_id, "DENIED", ERR_VIEWER_UNAVAILABLE),
        )
    viewer = state.get_player(viewer_player_id)
    if viewer is None:
        return api_response(
            False, "Viewer player not found",
            build_failure_dto(query_id, "DENIED", ERR_VIEWER_UNAVAILABLE),
        )
    if getattr(viewer, "player_type", None) not in (PlayerType.HUMAN, PlayerType.AI):
        return api_response(
            False, "Viewer player not eligible",
            build_failure_dto(query_id, "DENIED", ERR_VIEWER_UNAVAILABLE),
        )
    faction_id = getattr(viewer, "faction_id", None)
    if not faction_id or state.get_faction(faction_id) is None:
        return api_response(
            False, "Viewer faction unavailable",
            build_failure_dto(query_id, "DENIED", ERR_VIEWER_UNAVAILABLE),
        )

    # -- 3. known query (A05-07) -------------------------------------------
    if not isinstance(query_id, str) or query_id not in _QUERY_SPECS:
        return api_response(
            False, "Unknown query",
            build_failure_dto("", "ERROR", ERR_UNKNOWN_QUERY),
        )

    spec = _QUERY_SPECS[query_id]

    # -- 4. argument / capability validation -------------------------------
    if not isinstance(filter_text, str) or not isinstance(record_id, str):
        return api_response(
            False, _ERROR_MESSAGES_ZH[ERR_INVALID_REQUEST],
            build_failure_dto(query_id, "ERROR", ERR_INVALID_REQUEST),
        )
    if record_id and not spec["can_detail"]:
        return api_response(
            False, _ERROR_MESSAGES_ZH[ERR_INVALID_REQUEST],
            build_failure_dto(query_id, "ERROR", ERR_INVALID_REQUEST),
        )
    if filter_text and not spec["can_filter"]:
        return api_response(
            False, _ERROR_MESSAGES_ZH[ERR_INVALID_REQUEST],
            build_failure_dto(query_id, "ERROR", ERR_INVALID_REQUEST),
        )

    # -- 5. handler (required subsystem / selector / records) ---------------
    handler = _HANDLERS.get(query_id)
    if handler is None:
        # Known canonical query with no slice handler yet. Fail closed: never a
        # placeholder-as-success (A05-07 / FC-02).
        return api_response(
            False, _ERROR_MESSAGES_ZH[ERR_NOT_IMPLEMENTED],
            build_failure_dto(query_id, "ERROR", ERR_NOT_IMPLEMENTED),
        )

    try:
        dto = handler(state, viewer, filter_text, record_id)
    except Exception:  # pragma: no cover - defensive fail-closed
        logger.exception("global query handler failed: %s", query_id)
        return api_response(
            False, _ERROR_MESSAGES_ZH[ERR_QUERY_FAILED],
            build_failure_dto(query_id, "ERROR", ERR_QUERY_FAILED),
        )

    success = dto.get("result_state") in ("OK", "EMPTY")
    return api_response(success, dto.get("message", ""), dto)


# ===========================================================================
# DTO construction (typed, allowlist-projected BEFORE construction)
# ===========================================================================
def build_failure_dto(
    query_id: str,
    result_state: str,
    code: str,
    message: Optional[str] = None,
    message_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the fixed safe failure shell (items/summary/detail empty)."""
    message_key = _ERROR_MESSAGE_KEYS.get(code, "query.error.query_failed")
    text = message if message is not None else _ERROR_MESSAGES_ZH.get(code, "")
    error = {"code": code, "scope": "package", "field": None, "details": {}, "message": text}
    return _dto(
        query_id,
        result_state,
        message_key=message_key,
        message=text,
        message_params=message_params,
        errors=[error],
    )


def _dto(
    query_id: str,
    result_state: str,
    *,
    status: Optional[str] = None,
    message_key: str = "",
    message: str = "",
    message_params: Optional[Dict[str, Any]] = None,
    title_key: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    columns: Optional[List[Dict[str, Any]]] = None,
    filters: Optional[Dict[str, Any]] = None,
    detail: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    spec = _QUERY_SPECS.get(query_id)
    if result_state in ("OK", "EMPTY") and spec is not None:
        capabilities = {
            "can_filter": bool(spec["can_filter"]),
            "can_detail": bool(spec["can_detail"]),
        }
    else:
        capabilities = {"can_filter": False, "can_detail": False}
    return {
        "id": query_id if query_id in _QUERY_SPECS else "",
        "title": _QUERY_TITLES.get(query_id, ""),
        "title_key": title_key or _QUERY_TITLE_KEYS.get(query_id, "query.result.title"),
        "status": status or _status_for(result_state, query_id),
        "result_state": result_state,
        "message": message,
        "message_key": message_key,
        "message_params": message_params or {},
        "summary": summary or {},
        "items": items or [],
        # PT-01 (v1.4): the ordered LIST header schema (localized labels only, no
        # values) — the union of columns at least one visible row can populate.
        # Empty for DETAIL/EMPTY/DENIED and for non-tabular lists.
        "columns": columns or [],
        "capabilities": capabilities,
        "filters": filters,
        "detail": detail,
        "errors": errors or [],
    }


def _status_for(result_state: str, query_id: str) -> str:
    if result_state == "OK":
        return "connected" if query_id == "game_status" else "readonly"
    if result_state == "EMPTY":
        return "empty"
    if result_state == "DENIED":
        return "denied"
    return "error"


def _item(
    label_key: str,
    label: str,
    value: Any,
    meta: Optional[Dict[str, Any]] = None,
    record_id: str = "",
    value_key: str = "",
    value_params: Optional[Dict[str, Any]] = None,
    columns: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "record_id": record_id,
        "label": label,
        "label_key": label_key,
        "value": "" if value is None else str(value),
        # i18n value binding (F7): the shell resolves ``value_key`` (with safe
        # ``value_params``) so locale switches relabel enum/bool displays; the
        # raw ``value`` is only a safe legacy fallback.
        "value_key": value_key,
        "value_params": value_params or {},
        "meta": meta or {},
        # PT-01: an ordered, viewer-projected column schema for this record
        # (OWN = full CLI ``status_figure`` columns; FOREIGN = public identity
        # only). Absent columns are omitted, never blank.
        "columns": columns or [],
    }


def _column(
    col_key: str,
    label_key: str,
    label: str,
    value: Any = "",
    value_key: str = "",
    value_params: Optional[Dict[str, Any]] = None,
    min_width_px: int = 56,
    align: str = "left",
) -> Dict[str, Any]:
    """One PT-01 list cell: localized label + value with a minimum width.

    ``value`` is only a safe legacy fallback; ``value_key``/``value_params``
    drive the localized render so no raw enum / hardcoded copy is shown.
    """
    return {
        "col_key": col_key,
        "label_key": label_key,
        "label": label,
        "value": "" if value is None else str(value),
        "value_key": value_key,
        "value_params": value_params or {},
        "min_width_px": int(min_width_px),
        "align": align,
    }


def _detail_field(
    label_key: str,
    label: str,
    value: Any,
    value_key: str = "",
    value_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "label_key": label_key,
        "label": label,
        "value": "" if value is None else str(value),
        "value_key": value_key,
        "value_params": value_params or {},
    }


def _bool_value(flag: bool):
    """Return ``(safe_text, i18n_key)`` for a boolean display value (F7)."""
    return ("是" if flag else "否", "query.bool.yes" if flag else "query.bool.no")


def _phase_key(phase_id: Any) -> str:
    return f"query.phase.{phase_id}" if phase_id else ""


def _war_status_key(status: Any) -> str:
    return f"query.war.status.{status}" if status else ""


def _legion_status_key(status: Any) -> str:
    return f"query.legion.status.{status}" if status else ""


def _fleet_status_key(status: Any) -> str:
    return f"query.fleet.status.{status}" if status else ""


def _class_tier_key(tier: Any) -> str:
    return f"query.figure.class_tier.{tier}" if tier else ""


def _office_key(office: Any) -> str:
    """i18n key for a canonical office / office_history enum value (F7).

    Offices are canonical enums (consul/censor/praetor/quaestor/tribune/
    proconsul/propraetor/dictator), never player-entered proper names; the shell
    resolves ``query.office.<enum>`` so the display relabels on locale switch and
    never shows the raw enum.
    """
    return f"query.office.{office}" if office else ""


# ===========================================================================
# Normalisation helpers
# ===========================================================================
def _normalize_filter(text: str) -> str:
    """Unicode NFKC + trim + casefold (no tokenisation / regex)."""
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text).strip().casefold()


def _parse_decimal(selector: str) -> Optional[int]:
    if not isinstance(selector, str) or _DECIMAL_RE.fullmatch(selector) is None:
        return None
    return int(selector)


def _is_canonical_decimal(value: Any) -> bool:
    """True iff ``value`` is a positive int and equals its own canonical wire
    form ``str(value)`` (rejects bool, non-int, nonpositive)."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return False
    return str(value) == str(value).strip() and str(value) != ""


def _decimal_ids_valid(ids: List[Any]) -> bool:
    """Canonical decimal source IDs must each be valid AND unique (F1)."""
    seen = set()
    for i in ids:
        if not _is_canonical_decimal(i):
            return False
        if i in seen:
            return False
        seen.add(i)
    return True


def _string_ids_valid(ids: List[Any]) -> bool:
    """Canonical string source IDs must each be nonempty AND unique (F1)."""
    seen = set()
    for i in ids:
        if not isinstance(i, str) or i == "":
            return False
        if i in seen:
            return False
        seen.add(i)
    return True


def _match(name: str, normalized_filter: str) -> bool:
    if normalized_filter == "":
        return True
    return normalized_filter in _normalize_filter(name)


# ===========================================================================
# Handlers
# ===========================================================================
def _build_game_status(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    # F1 (SA v1.1 §6.2): a missing canonical required source (turn / year /
    # turn_number) is a typed ``system_unavailable`` failure — NEVER a fabricated
    # zero and never a success shell. Validate the required sources BEFORE
    # building ANY presentation field. ``is None`` (not truthiness) keeps a
    # legitimate numeric 0 distinguishable from a missing source.
    turn = getattr(state, "turn", None)
    if turn is None:
        return build_failure_dto("game_status", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    year = getattr(turn, "year", None)
    turn_number = getattr(turn, "turn_number", None)
    if year is None or turn_number is None:
        return build_failure_dto("game_status", "ERROR", ERR_SYSTEM_UNAVAILABLE)

    current_player = state.get_current_player()
    current_phase_id = _infer_current_phase_id(state)
    year_display = (
        turn.get_year_display()
        if hasattr(turn, "get_year_display")
        else _format_year(year)
    )
    living_count = len(state.get_living_members())
    faction_count = len(state.get_active_factions())
    players_overview = [
        {
            "player_id": player.player_id,
            "faction_id": player.faction_id,
            "player_type": player.player_type.value,
            "is_current": bool(current_player and player.player_id == current_player.player_id),
        }
        for player in state.get_all_players()
    ]
    items = [
        _item("query.item.year", "年份", year_display),
        _item("query.item.turn", "回合", str(turn_number)),
        _item("query.item.current_phase", "当前阶段", current_phase_id,
              value_key=_phase_key(current_phase_id)),
        _item("query.item.current_player", "当前玩家",
              current_player.player_id if current_player else ""),
        _item("query.item.treasury", "国库", f"{state.treasury} T"),
        _item("query.item.living_members", "在世人物", str(living_count)),
        _item("query.item.factions", "派系数", str(faction_count)),
    ]
    summary = {
        "year": year,
        "turn": turn_number,
        "current_phase": current_phase_id,
        "current_phase_id": current_phase_id,
        "current_player_id": current_player.player_id if current_player else None,
        "treasury": state.treasury,
        "living_count": living_count,
        "faction_count": faction_count,
        "players_overview": players_overview,
    }
    return _dto(
        "game_status", "OK",
        status="connected",
        message_key="query.game_status.message",
        message="共和国公开状态摘要。",
        summary=summary,
        items=items,
    )


def _build_public_land(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    """Canonical national public-land snapshot (SA v1.1 §6.2 public_land).

    Scalar read (can_filter=False / can_detail=False): the national public-land
    snapshot taken from the canonical read model
    ``game_api.get_public_land_info`` — no per-faction/national private aggregate
    and no trading capability. Reading the existing snapshot price does NOT
    constitute the separately OUT/DEFER standalone price query. A missing
    canonical source fails closed (never a fabricated zero).
    """
    from src.api import game_api

    result = game_api.get_public_land_info(
        state, caller_context=session_access.current_caller_context(state))
    # N1 (defense hardening): a canonical producer result marked ``success=False``
    # must fail closed even if it still carries a well-formed ``data`` dict — a
    # failed producer is NEVER recast as success.
    if not isinstance(result, dict) or not result.get("success"):
        return build_failure_dto("public_land", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    data = result.get("data")
    if not isinstance(data, dict):
        return build_failure_dto("public_land", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    national_land = data.get("national_land")
    land_price = data.get("land_price")
    value = data.get("value")
    tax_rate = data.get("tax_rate")
    annual_income = data.get("annual_income")
    treasury = data.get("treasury")
    if any(v is None for v in (national_land, land_price, value, tax_rate,
                               annual_income, treasury)):
        # Missing canonical required source -> system_unavailable (SA v1.1 §6.2).
        return build_failure_dto("public_land", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    items = [
        _item("query.public_land.national_land", "国家公地", f"{national_land} C"),
        _item("query.public_land.land_price", "土地单价", f"{land_price} T/C"),
        _item("query.public_land.value", "公地价值", f"{value} T"),
        _item("query.public_land.tax_rate", "年收益率",
              f"{float(tax_rate) * 100:.1f}%"),
        _item("query.public_land.annual_income", "年收益", f"{annual_income} T"),
        _item("query.public_land.treasury", "国库", f"{treasury} T"),
    ]
    summary = {
        "national_land": national_land,
        "land_price": land_price,
        "value": value,
        "tax_rate": tax_rate,
        "annual_income": annual_income,
        "treasury": treasury,
    }
    return _dto(
        "public_land", "OK",
        message_key="query.public_land.message",
        message="国家公地为公开只读快照，不提供交易或单价查询。",
        summary=summary,
        items=items,
    )


def _build_help(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    """GUI help (SA v1.1 §6.2 help / FC-10).

    Read-only operation guidance plus the canonical query categories. Contain NO
    CLI debug/force/executable command (help U fields absent). Scalar read
    (can_filter=False / can_detail=False).
    """
    items: List[Dict[str, Any]] = []
    # Query categories (the canonical twelve entries) — label = localized title.
    for qid in CANONICAL_QUERY_IDS:
        items.append(_item(
            "query." + qid + ".title",
            _QUERY_TITLES.get(qid, ""),
            "",
            {"kind": "category", "query_id": qid},
        ))
    # Read-only operation guidance (topic label + instruction value).
    for gid in _HELP_GUIDE_IDS:
        items.append(_item(
            "query.help.guide." + gid,
            _HELP_GUIDE_ZH.get(gid, ""),
            "",
            {"kind": "guide", "id": gid},
            value_key="query.help.guide." + gid + ".value",
        ))
    summary = {
        "categories": list(CANONICAL_QUERY_IDS),
        "guide_count": len(_HELP_GUIDE_IDS),
    }
    return _dto(
        "help", "OK",
        message_key="query.help.message",
        message="所有查询均为只读，不改变游戏状态。",
        summary=summary,
        items=items,
    )


def _build_faction_info(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    viewer_faction_id = viewer.faction_id
    factions = state.get_active_factions()
    if not _string_ids_valid([getattr(faction, "id", None) for faction in factions]):
        # Nonpositive/empty/duplicate canonical source id -> query_failed (F1),
        # never first-match selection.
        return build_failure_dto("faction_info", "ERROR", ERR_QUERY_FAILED)
    records = [_project_faction(state, faction, viewer_faction_id)
               for faction in factions]
    # Frozen (SA v1.2 §4 / SA11 §5.3): exact faction.id ascending (codepoint) —
    # no owner-first bias.
    records.sort(key=lambda r: r["id"])

    if record_id:
        rec = next((r for r in records if r["id"] == record_id), None)
        if rec is None:
            return build_failure_dto("faction_info", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _faction_detail_dto(rec)

    normalized = _normalize_filter(filter_text)
    visible = [r for r in records if _match(r["name"], normalized)]

    items: List[Dict[str, Any]] = []
    for r in visible:
        is_own = r["is_viewer_faction"]
        # F2: the faction IDENTITY row is the selectable record — a nonempty
        # ``record_id`` = the exact ``faction.id`` string drives the production
        # QML click predicate (``root.canDetail && modelData.record_id !== ""``),
        # so the frozen ``(id, "", record_id)`` selection chain opens this
        # faction's detail. Ancillary legacy rows (treasury / member count /
        # influence) stay non-selectable (record_id == "").
        items.append(_item(
            "query.item.faction" if is_own else "query.item.public_faction",
            "派系" if is_own else "公开派系",
            r["name"],
            {"faction_id": r["id"], "treasury_visible": is_own},
            record_id=r["id"],
        ))
        if is_own:
            # OWN-only scalar treasury (SA v1.2 §4 V-own-only addition).
            items.append(_item("query.item.treasury", "派系金库", f"{r['treasury']} T",
                               {"scope": "viewer_faction"}))
        # Public per-faction aggregates for ALL active factions (SA v1.2 §4
        # V-public): member_count and total_influence.
        items.append(_item("query.item.members", "人物数", str(r["member_count"]),
                           {"faction_id": r["id"]}))
        items.append(_item("query.item.influence", "影响力", str(r["total_influence"]),
                           {"faction_id": r["id"]}))

    summary = {
        "viewer_faction_id": viewer_faction_id,
        "factions": [
            {
                "id": r["id"],
                "name": r["name"],
                "is_viewer_faction": r["is_viewer_faction"],
                # Public aggregates for ALL active factions (SA v1.2 §4
                # V-public); treasury stays OWN-only.
                "member_count": r["member_count"],
                "total_influence": r["total_influence"],
                **({"treasury": r["treasury"]} if r["is_viewer_faction"] else {}),
            }
            for r in visible
        ],
    }
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "faction_info", result_state,
        message_key="query.faction_info.message",
        message="当前派系显示金库；其他派系仅显示公开概览。",
        summary=summary,
        items=items,
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _project_faction(state: GameState, faction, viewer_faction_id: str) -> Dict[str, Any]:
    members = faction.get_members(state)
    record = {
        "id": faction.id,
        "name": faction.name,
        "is_viewer_faction": faction.id == viewer_faction_id,
        # Public aggregates for ALL active factions (SA v1.2 §4 / §107). Same
        # living member set as the canonical faction aggregate source
        # (``faction_api.get_factions_status``); member_count and total_influence
        # are derived from the SAME list so they stay in parity.
        "member_count": len(members),
        "total_influence": sum(m.influence for m in members),
    }
    if record["is_viewer_faction"]:
        record["treasury"] = faction.treasury
        record["members"] = [
            {
                "id": member.id,
                "name": member.get_formal_name() or member.name,
                "office": member.office,
                "is_leader": bool(member.is_faction_leader),
            }
            for member in members
        ]
    return record


def _faction_detail_dto(record: Dict[str, Any]) -> Dict[str, Any]:
    is_viewer_value, is_viewer_key = _bool_value(record["is_viewer_faction"])
    fields = [
        _detail_field("query.faction.id", "ID", record["id"]),
        _detail_field("query.faction.name", "派系", record["name"]),
        _detail_field("query.faction.is_viewer", "本方派系", is_viewer_value,
                      value_key=is_viewer_key),
        # Public aggregates for ALL active factions (SA v1.2 §4 V-public).
        _detail_field("query.faction.member_count", "人物数", record["member_count"]),
        _detail_field("query.faction.total_influence", "影响力",
                      record["total_influence"]),
    ]
    if record["is_viewer_faction"]:
        # OWN-only rows (SA v1.2 §4 V-own-only additions): treasury + roster.
        fields.append(_detail_field("query.faction.treasury", "派系金库",
                                    f"{record['treasury']} T"))
        for member in record.get("members", []):
            office = member.get("office")
            is_leader = bool(member.get("is_leader"))
            if office and is_leader:
                vkey = "query.value.faction_member_leader"
                vparams = {"office": {"key": _office_key(office)},
                           "leader": {"key": "query.value.leader"}}
            elif office:
                vkey = _office_key(office)
                vparams = {}
            elif is_leader:
                vkey = "query.value.leader"
                vparams = {}
            else:
                vkey = ""
                vparams = {}
            # No raw enum / hardcoded Chinese in the DTO: the member office and
            # the leader tag are resolved from i18n keys by the shell (F7).
            fields.append(_detail_field("query.faction.member", member["name"],
                                        "", value_key=vkey, value_params=vparams))
    return _dto(
        "faction_info", "OK",
        message_key="query.faction_info.message",
        message="派系详情为只读。",
        summary={},
        items=[],
        detail={"record_id": record["id"], "fields": fields, "meta": {}},
    )


def _build_faction_treasury(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    """Viewer-own faction treasury ONLY (v1.1 §6.2 faction_treasury).

    Scalar read (can_filter=False / can_detail=False): the viewer's own faction
    id / name / treasury — never an account snapshot.
    """
    faction_id = viewer.faction_id
    faction = state.get_faction(faction_id)
    if faction is None:
        return build_failure_dto("faction_treasury", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    name = faction.name
    treasury = faction.treasury
    items = [
        _item("query.faction.name", "派系", name, {"faction_id": faction_id}),
        _item("query.faction.treasury", "派系金库", f"{treasury} T",
              {"scope": "viewer_faction"}),
    ]
    summary = {
        "viewer_faction_id": faction_id,
        "viewer_faction_name": name,
        "treasury": treasury,
    }
    return _dto(
        "faction_treasury", "OK",
        message_key="query.faction_treasury.message",
        message="仅显示本派系金库金额，不提供账目明细。",
        summary=summary,
        items=items,
    )


# PT-01 (v1.4/v1.5) private_land list schema — CLI ``status_private_land``
# column order (ID / 姓名 / 私地 / 价值 / 年收益 / 私库), LEFT alignment (CLI parity).
_PRIVATE_LAND_LIST_COLUMNS: List[Dict[str, Any]] = [
    {"col_key": "col_id", "label_key": "query.private_land.id", "label": "ID",
     "min_width_px": 48, "align": "left"},
    {"col_key": "col_name", "label_key": "query.private_land.name", "label": "姓名",
     "min_width_px": 160, "align": "left"},
    {"col_key": "col_land", "label_key": "query.private_land.land", "label": "私地",
     "min_width_px": 64, "align": "left"},
    {"col_key": "col_value", "label_key": "query.private_land.value", "label": "价值",
     "min_width_px": 80, "align": "left"},
    {"col_key": "col_income", "label_key": "query.private_land.annual_income", "label": "年收益",
     "min_width_px": 88, "align": "left"},
    {"col_key": "col_wealth", "label_key": "query.private_land.wealth", "label": "私库",
     "min_width_px": 80, "align": "left"},
]


def _format_amount(value: Any) -> str:
    """Compact numeric display: integral → int text; else 2-dp stripped."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _private_land_columns(rec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-record PT-01 column cells (OWN-only fields, v1.1 §6.2)."""
    return [
        _column("col_id", "query.private_land.id", "ID",
                value=str(rec["id"]), min_width_px=48),
        _column("col_name", "query.private_land.name", "姓名",
                value=rec["name"], min_width_px=160),
        _column("col_land", "query.private_land.land", "私地",
                value=str(rec["land_private"]), min_width_px=64),
        _column("col_value", "query.private_land.value", "价值",
                value=_format_amount(rec["value"]), min_width_px=80),
        _column("col_income", "query.private_land.annual_income", "年收益",
                value=_format_amount(rec["annual_income"]), min_width_px=88),
        _column("col_wealth", "query.private_land.wealth", "私库",
                value=_format_amount(rec["wealth"]), min_width_px=80),
    ]


def _build_private_land(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    """Viewer-own faction private-land list/detail (v1.1 §6.2 private_land).

    Only the viewer's own faction's living landowners are visible; national
    totals are absent for EVERY viewer (``own_faction_totals`` is viewer-scoped).
    Per-record value/income come from the canonical read model
    (``figure_api.get_private_land_info``) — no new economic formula.
    """
    from src.api import figure_api

    viewer_faction_id = viewer.faction_id
    land_result = figure_api.get_private_land_info(
        state, caller_context=session_access.current_caller_context(state))
    land_data = land_result.get("data") if isinstance(land_result, dict) else None
    if not isinstance(land_data, dict):
        return build_failure_dto("private_land", "ERROR", ERR_SYSTEM_UNAVAILABLE)

    landowners = land_data.get("landowners") or []
    own: List[Dict[str, Any]] = []
    for rec in landowners:
        fig = state.get_member(rec.get("id"))
        if fig is None or fig.faction_id != viewer_faction_id:
            continue
        own.append(rec)
    if not _decimal_ids_valid([rec.get("id") for rec in own]):
        return build_failure_dto("private_land", "ERROR", ERR_QUERY_FAILED)
    own.sort(key=lambda r: r["id"])

    if record_id:
        number = _parse_decimal(record_id)
        rec = next((r for r in own if r["id"] == number), None) if number is not None else None
        if rec is None:
            return build_failure_dto("private_land", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _private_land_detail_dto(rec)

    normalized = _normalize_filter(filter_text)
    visible = [r for r in own if _match(r["name"], normalized)]

    totals = {
        "scope": "viewer_faction",
        "faction_id": viewer_faction_id,
        "land": sum(r["land_private"] for r in own),
        "value": sum(r["value"] for r in own),
        "annual_income": sum(r["annual_income"] for r in own),
        "wealth": sum(r["wealth"] for r in own),
    }
    items = [
        _item("query.figure.land_private", "私地", r["name"],
              {"faction_id": viewer_faction_id}, record_id=str(r["id"]),
              columns=_private_land_columns(r))
        for r in visible
    ]
    summary = {"viewer_faction_id": viewer_faction_id, "own_faction_totals": totals}
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "private_land", result_state,
        message_key="query.private_land.message",
        message="仅显示本派系人物的私地信息。",
        summary=summary,
        items=items,
        columns=[dict(spec) for spec in _PRIVATE_LAND_LIST_COLUMNS],
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _private_land_detail_dto(rec: Dict[str, Any]) -> Dict[str, Any]:
    fields = [
        _detail_field("query.private_land.id", "ID", rec["id"]),
        _detail_field("query.private_land.name", "姓名", rec["name"]),
        _detail_field("query.private_land.land", "私地", rec["land_private"]),
        _detail_field("query.private_land.value", "价值", _format_amount(rec["value"])),
        _detail_field("query.private_land.annual_income", "年收益",
                      _format_amount(rec["annual_income"])),
        _detail_field("query.private_land.wealth", "私库", _format_amount(rec["wealth"])),
    ]
    return _dto(
        "private_land", "OK",
        message_key="query.private_land.message",
        message="私地详情为只读。",
        summary={},
        items=[],
        detail={"record_id": str(rec["id"]), "fields": fields, "meta": {}},
    )


def _build_war_list(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    war_system = state.get_war_system()
    if not war_system:
        return build_failure_dto("war_list", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    # F1 (SA v1.1 §6.2): the military and naval read sources are REQUIRED for the
    # war projection. Validate them BEFORE building ANY presentation field — a
    # genuinely missing source is a typed ``system_unavailable`` failure, NEVER a
    # fabricated zero/empty summary. A real present source that legitimately
    # reports zero assigned legions/fleets keeps its numeric 0 (``is None``, not
    # truthiness, distinguishes missing from a real 0).
    if state.get_military_system() is None or _get_naval_system(state) is None:
        return build_failure_dto("war_list", "ERROR", ERR_SYSTEM_UNAVAILABLE)

    grouped = (
        ("active", war_system.get_active_wars()),
        ("threat", war_system.get_threat_wars()),
        ("truce", war_system.get_truce_wars()),
        ("resolved", war_system.get_resolved_wars()),
    )
    raw_wars = [(group_name, war) for group_name, group in grouped for war in group]
    if not _string_ids_valid([getattr(war, "id", None) for _, war in raw_wars]):
        # Empty/duplicate canonical war id -> query_failed (F1), no first-match.
        return build_failure_dto("war_list", "ERROR", ERR_QUERY_FAILED)

    wars: List[Dict[str, Any]] = []
    for group_name, war in raw_wars:
        wars.append(_war_summary(state, war, group_name))

    if record_id:
        rec = next((w for w in wars if str(w["id"]) == record_id), None)
        if rec is None:
            return build_failure_dto("war_list", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _war_detail_dto(rec)

    normalized = _normalize_filter(filter_text)
    visible = [w for w in wars if _match(str(w["name"]), normalized)]
    # F2 (SA v1.1 §5.3): the war ``id`` is a string selector — publish the list
    # items and summary in exact codepoint id ascending order, stable and
    # independent of language/search (never grouped/source order).
    visible.sort(key=lambda w: str(w["id"]))
    counts = {
        "active": len([w for w in visible if w["status"] == "active"]),
        "threat": len([w for w in visible if w["status"] == "threat"]),
        "truce": len([w for w in visible if w["status"] == "truce"]),
        "resolved": len([w for w in visible if w["status"] == "resolved"]),
    }
    items = [
        _item("query.item.war", "战争", _war_item_value(w),
              {"war_id": w["id"], "status": w["status"]}, record_id=str(w["id"]),
              value_key="query.value.war",
              value_params={"name": str(w["name"]),
                            "status": {"key": _war_status_key(w["status"])}})
        for w in visible
    ]
    summary = {"wars": visible, "counts": counts}
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "war_list", result_state,
        message_key="query.war_list.message",
        message="战争列表展示公开状态摘要，不执行战斗。",
        summary=summary,
        items=items,
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _war_detail_dto(war: Dict[str, Any]) -> Dict[str, Any]:
    naval_value, naval_key = _bool_value(war["naval_required"])
    ready_value, ready_key = _bool_value(war["naval_ready"])
    fields = [
        _detail_field("query.war.id", "ID", war["id"]),
        _detail_field("query.war.name", "战争", war["name"]),
        _detail_field("query.war.status", "状态", war["status"],
                      value_key=_war_status_key(war["status"])),
        _detail_field("query.war.threat_level", "威胁", war["threat_level"]),
        _detail_field("query.war.naval_required", "需要海战", naval_value,
                      value_key=naval_key),
        _detail_field("query.war.commander_name", "指挥官", war["commander_name"]),
        _detail_field("query.war.legions_assigned", "指派军团", war["legions_assigned"]),
        _detail_field("query.war.assigned_fleet_count", "指派舰队",
                      war["assigned_fleet_count"]),
        _detail_field("query.war.naval_ready", "海战就绪", ready_value,
                      value_key=ready_key),
        _detail_field("query.war.fleet_effective_combat_strength", "舰队战力",
                      war["fleet_effective_combat_strength"]),
    ]
    return _dto(
        "war_list", "OK",
        message_key="query.war_list.message",
        message="战争详情为只读。",
        summary={},
        items=[],
        detail={"record_id": str(war["id"]), "fields": fields, "meta": {}},
    )


def _build_legion_status(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    military_system = state.get_military_system()
    if not military_system:
        return build_failure_dto("legion_status", "ERROR", ERR_SYSTEM_UNAVAILABLE)

    raw_legions = military_system.get_all_legions()
    if not _decimal_ids_valid([getattr(legion, "number", None) for legion in raw_legions]):
        # Nonpositive/duplicate canonical legion number -> query_failed (F1).
        return build_failure_dto("legion_status", "ERROR", ERR_QUERY_FAILED)

    legions: List[Dict[str, Any]] = []
    for legion in raw_legions:
        record = _legion_summary(legion, state)
        if record is None:
            # A missing required canonical deployment/strength source fails
            # closed (LEGION-S5-01) — never an identity-only record.
            return build_failure_dto("legion_status", "ERROR", ERR_SYSTEM_UNAVAILABLE)
        legions.append(record)
    legions.sort(key=lambda l: l["number"])

    if record_id:
        number = _parse_decimal(record_id)
        rec = next((l for l in legions if l["number"] == number), None) \
            if number is not None else None
        if rec is None:
            return build_failure_dto("legion_status", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _legion_detail_dto(rec)

    normalized = _normalize_filter(filter_text)
    visible = [l for l in legions if _match(str(l["name"]), normalized)]
    # Frozen canonical legion grouping (SA v1.2 §§3–5 / LEGION-S5-01): total,
    # active (status==active), available (status in {available, unraised,
    # disbanded}), assigned (war_id is not None), destroyed (status==destroyed).
    # The available/assigned distinction is preserved — NOT a generic
    # count-by-status rewrite.
    counts = {"total": 0, "active": 0, "available": 0, "assigned": 0, "destroyed": 0}
    for legion in visible:
        counts["total"] += 1
        status = legion["status"]
        if status == "active":
            counts["active"] += 1
        if status in {"available", "unraised", "disbanded"}:
            counts["available"] += 1
        if legion.get("assigned"):
            counts["assigned"] += 1
        if status == "destroyed":
            counts["destroyed"] += 1

    items = [
        _item("query.item.legion", "军团", _legion_item_value(l),
              {"legion_number": l["number"]}, record_id=str(l["number"]),
              value_key="query.value.legion",
              value_params={"name": str(l["name"]),
                            "status": {"key": _legion_status_key(l["status"])}})
        for l in visible
    ]
    summary = {"counts": counts, "legions": visible}
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "legion_status", result_state,
        message_key="query.legion_status.message",
        message="军团状态为只读摘要，不征召、不解散、不分配。",
        summary=summary,
        items=items,
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _legion_detail_dto(legion: Dict[str, Any]) -> Dict[str, Any]:
    veteran_value, veteran_key = _bool_value(legion["is_veteran"])
    assigned_value, assigned_key = _bool_value(legion["assigned"])
    war_id = legion["war_id"]
    fields = [
        _detail_field("query.legion.number", "编号", legion["number"]),
        _detail_field("query.legion.name", "军团", legion["name"]),
        _detail_field("query.legion.status", "状态", "",
                      value_key=_legion_status_key(legion["status"])),
        _detail_field("query.legion.is_veteran", "老兵", veteran_value,
                      value_key=veteran_key),
        # Restored frozen public deployment/strength observables (LEGION-S5-01):
        # a genuinely unset war target localizes as "none"; the raw value stays
        # typed in the safe summary and empty here for the localized display.
        _detail_field("query.legion.war_id", "指派战争",
                      "" if war_id is None else str(war_id),
                      value_key="query.value.none" if war_id is None else ""),
        _detail_field("query.legion.assigned", "已指派", assigned_value,
                      value_key=assigned_key),
        _detail_field("query.legion.strength", "战力", legion["strength"]),
    ]
    return _dto(
        "legion_status", "OK",
        message_key="query.legion_status.message",
        message="军团详情为只读。",
        summary={},
        items=[],
        detail={"record_id": str(legion["number"]), "fields": fields, "meta": {}},
    )


def _build_fleet_status(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    """Player-level fleet read model (SA v1.1 §6.2 fleet_status; AC-11).

    Public fleet identity ONLY — number/name/fleet_type/status/is_veteran. The
    UNVERIFIED strength/commander/assigned_war_id/mission fields are ABSENT for
    EVERY relation. Built from the canonical NavalSystem fleet registry — never
    the debug ``show_fleets`` endpoint. A missing canonical source fails closed.
    """
    naval_system = _get_naval_system(state)
    if naval_system is None:
        return build_failure_dto("fleet_status", "ERROR", ERR_SYSTEM_UNAVAILABLE)

    raw_fleets = naval_system.get_all_fleets()
    if not _decimal_ids_valid([getattr(fleet, "number", None) for fleet in raw_fleets]):
        # Nonpositive/duplicate canonical fleet number -> query_failed (F1).
        return build_failure_dto("fleet_status", "ERROR", ERR_QUERY_FAILED)

    fleets: List[Dict[str, Any]] = [_fleet_summary(fleet) for fleet in raw_fleets]
    fleets.sort(key=lambda f: f["number"])

    if record_id:
        number = _parse_decimal(record_id)
        rec = next((f for f in fleets if f["number"] == number), None) \
            if number is not None else None
        if rec is None:
            return build_failure_dto("fleet_status", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _fleet_detail_dto(rec)

    normalized = _normalize_filter(filter_text)
    visible = [f for f in fleets if _match(str(f["name"]), normalized)]
    counts = {"total": 0, "building": 0, "available": 0, "on_mission": 0,
              "in_combat": 0, "destroyed": 0, "disbanded": 0}
    for fleet in visible:
        counts["total"] += 1
        status = fleet["status"]
        if status in counts and status != "total":
            counts[status] += 1

    items = [
        _item("query.item.fleet", "舰队", _fleet_item_value(f),
              {"fleet_number": f["number"]}, record_id=str(f["number"]),
              value_key="query.value.fleet",
              value_params={"name": str(f["name"]),
                            "status": {"key": _fleet_status_key(f["status"])}})
        for f in visible
    ]
    summary = {"counts": counts, "fleets": visible}
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "fleet_status", result_state,
        message_key="query.fleet_status.message",
        message="舰队状态为只读摘要，不建造、不指派、不解散。",
        summary=summary,
        items=items,
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _fleet_detail_dto(fleet: Dict[str, Any]) -> Dict[str, Any]:
    veteran_value, veteran_key = _bool_value(fleet["is_veteran"])
    ftype = fleet["fleet_type"]
    fields = [
        _detail_field("query.fleet.number", "编号", fleet["number"]),
        _detail_field("query.fleet.name", "舰队", fleet["name"]),
        _detail_field("query.fleet.fleet_type", "舰种", ftype,
                      value_key="" if ftype else "query.value.none"),
        _detail_field("query.fleet.status", "状态", "",
                      value_key=_fleet_status_key(fleet["status"])),
        _detail_field("query.fleet.is_veteran", "老兵", veteran_value,
                      value_key=veteran_key),
    ]
    return _dto(
        "fleet_status", "OK",
        message_key="query.fleet_status.message",
        message="舰队详情为只读。",
        summary={},
        items=[],
        detail={"record_id": str(fleet["number"]), "fields": fields, "meta": {}},
    )


def _build_figure_search(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    viewer_faction_id = viewer.faction_id
    figures = state.get_living_members()
    if not _decimal_ids_valid([getattr(figure, "id", None) for figure in figures]):
        # Nonpositive/duplicate canonical figure id -> query_failed (F1).
        return build_failure_dto("figure_search", "ERROR", ERR_QUERY_FAILED)
    records = [_project_figure(state, figure, viewer_faction_id) for figure in figures]

    if record_id:
        number = _parse_decimal(record_id)
        rec = next((r for r in records if r["id"] == number), None) if number is not None else None
        if rec is None:
            # absent / malformed / dead / unauthorized selector -> identical shell
            return build_failure_dto("figure_search", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _figure_detail_dto(rec)

    normalized = _normalize_filter(filter_text)
    visible = [r for r in records if _match(r["name"], normalized)]
    visible.sort(key=lambda r: r["id"])

    items = [
        _item("query.item.figure", "人物", _figure_item_value(r), {},
              record_id=str(r["id"]),
              value_key="query.value.figure",
              value_params={"name": str(r["name"]),
                            "class_tier": {"key": _class_tier_key(r["class_tier"])}},
              columns=_figure_columns(r))
        for r in visible
    ]
    summary = {
        "count": len(visible),
        "living_total": len(records),
        "scope": "public",
    }
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "figure_search", result_state,
        message_key="query.figure_search.message",
        # Legacy (non-display) zh copy kept consistent with the i18n key value;
        # the display authority is the catalog key resolved by the shell (FC-23).
        message="仅显示当前玩家派系的人物详细信息",
        summary=summary,
        items=items,
        # PT-01 (v1.4): the LIST table header — one row of localized column
        # captions (CLI order), the union of columns the visible rows populate.
        columns=_figure_list_columns(visible),
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _project_figure(state: GameState, figure, viewer_faction_id: str) -> Dict[str, Any]:
    owner = figure.faction_id
    if owner and owner == viewer_faction_id:
        relation = "OWN"
    elif owner:
        relation = "OTHER"
    else:
        relation = "UNOWNED"
    class_tier = figure.class_tier.value if hasattr(figure.class_tier, "value") \
        else str(figure.class_tier)
    faction = state.get_faction(owner) if owner else None
    record = {
        "id": int(figure.id),
        "name": figure.get_formal_name(),
        "faction": owner or "",
        # Public identity: the faction NAME (CLI ``派系:{faction}``), never a raw id.
        "faction_name": faction.name if faction else "",
        "class_tier": class_tier,
        "office": figure.office,
        "is_leader": bool(figure.is_faction_leader),
        "is_dead": bool(figure.is_dead),
        "relation": relation,
    }
    if relation == "OWN":
        # OWN-private detail block (viewer-projected; never built for FOREIGN).
        record["own"] = {
            "influence": figure.influence,
            "wealth": figure.wealth,
            "popularity": figure.popularity,
            "land_private": figure.land_private,
            "veterans": figure.veterans,
            "age": figure.age,
            "rank": figure.rank,
            "zeal": figure.zeal,
            "charisma": figure.charisma,
            "martial": figure.martial,
            "intelligence": figure.intelligence,
            "family": figure.nomen or figure.family or "",
            "family_prestige": figure.family_prestige,
            "war_reward_influence": getattr(figure, "_war_reward_influence", 0),
            "office_bonus": figure.get_office_influence_bonus(),
            "office_history": _figure_office_history(state, figure),
            "contract_ids": list(figure.contract_ids),
            "is_present": not bool(figure.is_absent),
        }
    return record


def _figure_office_history(state: GameState, figure) -> List[Dict[str, Any]]:
    """CLI ``figure_api.get_figure_info`` office-history form (year per term).

    ``quaestor(BC287), consul(BC280)`` — the term year is derived from the
    current turn/year exactly as the CLI does.
    """
    turn = getattr(state, "turn", None)
    current_turn = turn.turn_number if turn else 1
    current_year = turn.year if turn else 0
    start_year = current_year - (current_turn - 1)
    terms: List[Dict[str, Any]] = []
    for term in figure.office_history:
        year = start_year + (term.start_turn - 1)
        era = "BC" if year < 0 else "AD"
        terms.append({
            "office_type": term.office_type,
            "year": f"{era}{abs(year)}",
        })
    return terms


def _figure_columns(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """PT-01 ordered list column schema (CLI ``status_figure`` alignment).

    Columns 1–5 and 11 are PUBLIC_IDENTITY; columns 6–10 are OWN_PRIVATE and are
    **absent** (not blank) for a FOREIGN record. Cell width = natural content
    width floored at ``min_width_px``; no column is truncated.
    """
    own = record.get("own")
    cols: List[Dict[str, Any]] = []
    # 1 status / faction-leader badge
    cols.append(_column(
        "col_status", "query.figure.status", "状态", value="",
        value_key=("query.value.leader" if record["is_leader"] else ""),
        min_width_px=24,
    ))
    # 2 class tier
    cols.append(_column(
        "col_class", "query.figure.class_tier", "阶层", value="",
        value_key=_class_tier_key(record["class_tier"]), min_width_px=56,
    ))
    # 3 id
    cols.append(_column("col_id", "query.figure.id", "ID",
                        value=str(record["id"]), min_width_px=48))
    # 4 name
    cols.append(_column("col_name", "query.figure.name", "姓名",
                        value=record["name"], min_width_px=180))
    # 5 faction (public name)
    faction_name = record.get("faction_name") or ""
    if faction_name:
        cols.append(_column("col_faction", "query.figure.faction", "派系",
                            value=faction_name, min_width_px=110))
    else:
        cols.append(_column("col_faction", "query.figure.faction", "派系", value="",
                            value_key="query.value.none", min_width_px=110))
    # 6-10 OWN-private columns (absent for FOREIGN)
    if own is not None:
        cols.append(_column("col_influence", "query.figure.influence", "影响力",
                            value=str(own["influence"]), min_width_px=64))
        cols.append(_column("col_wealth", "query.figure.wealth", "财富",
                            value=str(own["wealth"]), min_width_px=56))
        cols.append(_column("col_popularity", "query.figure.popularity", "人气",
                            value=str(own["popularity"]), min_width_px=56))
        cols.append(_column("col_land", "query.figure.land_private", "私地",
                            value=str(own["land_private"]), min_width_px=56))
        cols.append(_column("col_veterans", "query.figure.veterans", "老兵",
                            value=str(own["veterans"]), min_width_px=56))
    # 11 current office (public; 无 when none / ex-)
    office = record.get("office")
    if office and not str(office).startswith("ex-"):
        cols.append(_column("col_office", "query.figure.office", "担任公职", value="",
                            value_key=_office_key(office), min_width_px=96))
    else:
        cols.append(_column("col_office", "query.figure.office", "担任公职", value="",
                            value_key="query.value.none", min_width_px=96))
    return cols


# PT-01 (v1.4) LIST table header schema — the ordered CLI ``status_figure``
# column captions (status/class/ID/name/faction/influence/wealth/popularity/
# land/veterans/office). Col 11 uses the short Office caption
# ``query.figure.office_short`` (官职/Office) for the LIST header; the DETAIL
# table keeps ``query.figure.office`` (担任公职/Current Office). Alignment is
# LEFT for every column (CLI tabular parity).
_FIGURE_LIST_COLUMN_ORDER: List[Dict[str, Any]] = [
    {"col_key": "col_status", "label_key": "query.figure.status",
     "label": "状态", "min_width_px": 24, "align": "left"},
    {"col_key": "col_class", "label_key": "query.figure.class_tier",
     "label": "阶层", "min_width_px": 56, "align": "left"},
    {"col_key": "col_id", "label_key": "query.figure.id",
     "label": "ID", "min_width_px": 48, "align": "left"},
    {"col_key": "col_name", "label_key": "query.figure.name",
     "label": "姓名", "min_width_px": 180, "align": "left"},
    {"col_key": "col_faction", "label_key": "query.figure.faction",
     "label": "派系", "min_width_px": 110, "align": "left"},
    {"col_key": "col_influence", "label_key": "query.figure.influence",
     "label": "影响力", "min_width_px": 64, "align": "left"},
    {"col_key": "col_wealth", "label_key": "query.figure.wealth",
     "label": "财富", "min_width_px": 56, "align": "left"},
    {"col_key": "col_popularity", "label_key": "query.figure.popularity",
     "label": "人气", "min_width_px": 56, "align": "left"},
    {"col_key": "col_land", "label_key": "query.figure.land_private",
     "label": "私地", "min_width_px": 56, "align": "left"},
    {"col_key": "col_veterans", "label_key": "query.figure.veterans",
     "label": "老兵", "min_width_px": 56, "align": "left"},
    {"col_key": "col_office", "label_key": "query.figure.office_short",
     "label": "官职", "min_width_px": 96, "align": "left"},
]


def _figure_list_columns(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """PT-01 (v1.4) header schema: the ordered union of columns that at least one
    visible record can populate (labels only, no values).

    An OWN record carries all 11 CLI columns; a FOREIGN record carries only the
    public-identity columns, so an all-FOREIGN result set exposes just the public
    column headers (no phantom private columns). Placement by column track index
    keeps the public columns aligned under their header across ALL rows.
    """
    present: set = set()
    for record in records:
        for col in _figure_columns(record):
            present.add(col["col_key"])
    return [dict(spec) for spec in _FIGURE_LIST_COLUMN_ORDER if spec["col_key"] in present]


def _figure_item_value(record: Dict[str, Any]) -> str:
    parts = [record["name"]]
    if record["faction"]:
        parts.append(record["faction"])
    parts.append(record["class_tier"])
    if record["office"]:
        parts.append(str(record["office"]))
    if record["is_leader"]:
        parts.append("leader")
    return " / ".join(parts)


def _figure_detail_dto(record: Dict[str, Any]) -> Dict[str, Any]:
    """Owner-ordered field→value table (PT-02 / SA13 §5).

    OWN records render all 21 rows in the Owner order; a FOREIGN record renders
    only the PUBLIC_IDENTITY rows (姓名/派系/阶层/担任公职/是否派系领袖/是否死亡)
    in the same relative order — every OWN_PRIVATE row is **absent** (omitted,
    never blank).
    """
    own = record.get("own")
    fields: List[Dict[str, Any]] = []

    # 1 姓名
    fields.append(_detail_field("query.figure.name", "姓名", record["name"]))
    # 2 派系 (public faction name)
    faction_name = record.get("faction_name") or ""
    fields.append(_detail_field("query.figure.faction", "派系", faction_name,
                                value_key="" if faction_name else "query.value.none"))
    # 3 阶层
    fields.append(_detail_field("query.figure.class_tier", "阶层", "",
                                value_key=_class_tier_key(record["class_tier"])))

    if own is not None:
        # 4 家族(声望)
        family = own.get("family") or ""
        family_params: Dict[str, Any] = {"prestige": str(own["family_prestige"])}
        family_params["family"] = family if family else {"key": "query.value.none"}
        fields.append(_detail_field("query.figure.family", "家族", "",
                                    value_key="query.figure.family_value",
                                    value_params=family_params))
        # 5 年龄
        fields.append(_detail_field("query.figure.age", "年龄", str(own["age"])))
        # 6 影响力 (CLI verbatim display form; transient term intentionally absent)
        fields.append(_detail_field(
            "query.figure.influence", "影响力", "",
            value_key="query.figure.influence_value",
            value_params={
                "total": str(own["influence"]),
                "war": str(own["war_reward_influence"]),
                "land": str(own["land_private"] * 10),
                "vet": str(own["veterans"] * 10),
                "pop": str(own["popularity"]),
                "fam": str(own["family_prestige"] * 10),
                "office": str(own["office_bonus"]),
            },
        ))
        # 7 官职等级
        fields.append(_detail_field("query.figure.rank", "官职等级", str(own["rank"])))
        # 8-11 attributes
        fields.append(_detail_field("query.figure.zeal", "热忱", str(own["zeal"])))
        fields.append(_detail_field("query.figure.charisma", "魅力", str(own["charisma"])))
        fields.append(_detail_field("query.figure.martial", "军略", str(own["martial"])))
        fields.append(_detail_field("query.figure.intelligence", "智略",
                                    str(own["intelligence"])))
        # 12 财富
        fields.append(_detail_field("query.figure.wealth", "财富", str(own["wealth"])))
        # 13 人气
        fields.append(_detail_field("query.figure.popularity", "人气",
                                    str(own["popularity"])))
        # 14 私地
        fields.append(_detail_field("query.figure.land_private", "私地",
                                    f"{own['land_private']} C"))
        # 15 老兵
        fields.append(_detail_field("query.figure.veterans", "老兵", str(own["veterans"])))

    # 16 担任公职
    office = record.get("office")
    if office and not str(office).startswith("ex-"):
        fields.append(_detail_field("query.figure.office", "担任公职", "",
                                    value_key=_office_key(office)))
    else:
        fields.append(_detail_field("query.figure.office", "担任公职", "",
                                    value_key="query.value.none"))

    if own is not None:
        # 17 公职历史 (CLI formula: office(year) per term)
        history = own.get("office_history") or []
        if history:
            offices = [
                {"key": "query.value.office_term",
                 "office": {"key": _office_key(term["office_type"])},
                 "year": term["year"]}
                for term in history
            ]
            fields.append(_detail_field("query.figure.office_history", "公职历史", "",
                                        value_key="query.figure.office_history_value",
                                        value_params={"offices": offices}))
        else:
            fields.append(_detail_field("query.figure.office_history", "公职历史", "",
                                        value_key="query.value.none"))
        # 18 持有合同
        contracts = own.get("contract_ids") or []
        if contracts:
            fields.append(_detail_field("query.figure.contracts", "持有合同",
                                        ", ".join(str(cid) for cid in contracts)))
        else:
            fields.append(_detail_field("query.figure.contracts", "持有合同", "",
                                        value_key="query.value.none"))

    # 19 是否派系领袖
    leader_value, leader_key = _bool_value(record["is_leader"])
    fields.append(_detail_field("query.figure.is_leader", "是否派系领袖", leader_value,
                                value_key=leader_key))
    # 20 是否死亡
    dead_value, dead_key = _bool_value(record["is_dead"])
    fields.append(_detail_field("query.figure.is_dead", "是否死亡", dead_value,
                                value_key=dead_key))

    if own is not None:
        # 21 是否在罗马 (= not is_absent)
        present_value, present_key = _bool_value(own["is_present"])
        fields.append(_detail_field("query.figure.is_present", "是否在罗马", present_value,
                                    value_key=present_key))

    return _dto(
        "figure_search", "OK",
        message_key="query.figure_search.message",
        message="人物详情为只读。",
        summary={},
        items=[],
        detail={"record_id": str(record["id"]), "fields": fields, "meta": {}},
    )


# ===========================================================================
# Shared war/legion presentation helpers
# ===========================================================================
def _get_naval_system(state: GameState):
    """Resolve the canonical NavalSystem (S5 fleet / war fleet-strength source).

    ``_naval_system`` is always constructed in ``GameState.__init__``; the getter
    is checked first for forward compatibility, then the private attribute.
    Returns ``None`` when genuinely unavailable (callers fail closed).
    """
    getter = getattr(state, "get_naval_system", None)
    if callable(getter):
        system = getter()
        if system is not None:
            return system
    return getattr(state, "_naval_system", None) or getattr(state, "naval_system", None)


def _war_summary(state: GameState, war, status: str) -> Dict[str, Any]:
    """Public war read model (the established/authoritative war summary shape).

    NOTE (EOR20261011-01 S5): the frozen S5 §6.2 war_list field list
    (``id,name,status,threat_level,naval_required,commander_name,
    legions_assigned,assigned_fleet_count,fleet_strength_read_model``; "raw war/
    debug/deck/assignment mirror fields absent") is INCOMPATIBLE with the
    pre-existing frozen war read-model contracts (WP-O R03 / WP-G-R1 S3 SC-04 /
    WP-G-R3 S4 §4.5 / WP-G-R3 S5 T19), which mandate ``commander_id``,
    ``fleets_assigned``, ``naval_ready``, ``assigned_fleet_ids`` and the layered
    ``fleet_*`` strength fields on this very summary. That is a
    DESIGN_REALITY_MISMATCH -> routed to PM/SA; the authoritative shape is
    preserved unchanged (no narrowing applied) so no frozen contract breaks.
    """
    commander_name = ""
    live_commander_id = None
    if getattr(war, "commander_id", None) is not None:
        commander = state.get_living_member(war.commander_id)
        if commander is not None:
            live_commander_id = war.commander_id
            commander_name = commander.get_formal_name()
    # F1 (SA v1.1 §6.2): ``_build_war_list`` validates both canonical read
    # sources as present BEFORE any projection, so a missing source fails closed
    # there and a fabricated zero/empty model is never built here. A real present
    # source that legitimately reports a zero (no assigned legions/fleets) stays 0.
    military_system = state.get_military_system()
    naval_system = _get_naval_system(state)
    legions_assigned = len(military_system.get_legions_for_battle(war.id))
    fleet_read_model: Dict[str, Any] = naval_system.get_war_fleet_strength_read_model(war)
    assigned_fleet_count = len(fleet_read_model["assigned_fleet_ids"])
    naval_ready = assigned_fleet_count >= 1
    packages = [
        {
            "package_id": pkg.get("package_id"),
            "fleet_ids": list(pkg.get("fleet_ids", [])),
            "nominal": pkg.get("nominal"),
            "q_numerator": pkg.get("q_numerator"),
            "q_denominator": pkg.get("q_denominator"),
            "raw": pkg.get("raw"),
            "capped": pkg.get("capped"),
            "rounded": pkg.get("rounded"),
        }
        for pkg in fleet_read_model["fleet_strength_packages"]
    ]
    return {
        "id": war.id,
        "name": war.name,
        "status": status,
        "threat_level": getattr(war, "threat_level", 0),
        "naval_required": getattr(war, "naval_required", False),
        "commander_id": live_commander_id,
        "commander_name": commander_name,
        "legions_assigned": legions_assigned,
        "assigned_fleet_count": assigned_fleet_count,
        "fleets_assigned": assigned_fleet_count,
        "naval_ready": naval_ready,
        "assigned_fleet_ids": list(fleet_read_model["assigned_fleet_ids"]),
        "fleet_nominal_strength": fleet_read_model["fleet_nominal_strength"],
        "fleet_quality_adjusted_base": fleet_read_model["fleet_quality_adjusted_base"],
        "fleet_experience_bonus": fleet_read_model["fleet_experience_bonus"],
        "fleet_commander_bonus": fleet_read_model["fleet_commander_bonus"],
        "fleet_effective_combat_strength": fleet_read_model["fleet_effective_combat_strength"],
        "fleet_strength_packages": packages,
    }


def _war_item_value(war: Dict[str, Any]) -> str:
    parts = [war["name"], war["status"]]
    if war.get("threat_level"):
        parts.append(f"threat {war['threat_level']}")
    if war.get("naval_required"):
        parts.append("naval")
    if war.get("commander_name"):
        parts.append(war["commander_name"])
    return " / ".join(parts)


# Frozen public legion projection (SA v1.2 §§4–5, LEGION-S5-01): the exact
# ordered nine-field current-public set, copied present-when-present from the
# canonical ``Legion.to_display_dict`` display read model. Typed
# null/boolean/numeric values are preserved (never truthiness-dropped, never
# fabricated defaults). Unlisted/private legion fields are never copied.
_LEGION_PUBLIC_FIELDS: tuple = (
    "number", "name", "status", "is_veteran", "war_id",
    "assigned", "strength", "cost", "destroyed_turn",
)
# Required canonical deployment/strength sources: ``present-when-present`` is not
# permission to omit them — a missing source fails closed (never identity-only,
# fabricated zero or status inference).
_LEGION_REQUIRED_FIELDS: frozenset = frozenset({
    "number", "name", "status", "is_veteran", "war_id", "assigned", "strength",
})


def _legion_summary(legion, state):
    """Public legion record — the frozen current-public projection (LEGION-S5-01).

    ``project(Legion.to_display_dict(state))`` = an ordered copy of the nine
    authorized keys actually present in the same-state canonical display read
    model. Returns ``None`` when a required deployment/strength source is missing
    so the caller fails closed. ``commander_id``/``experience``/``status_emoji``/
    ``legion_type``/history/``battles_*`` and every unlisted legion field are
    never copied (and never passed through as the raw display dictionary).
    """
    display = legion.to_display_dict(state)
    if not isinstance(display, dict):
        return None
    if not _LEGION_REQUIRED_FIELDS.issubset(display):
        return None
    return {field: display[field] for field in _LEGION_PUBLIC_FIELDS if field in display}


def _legion_item_value(legion: Dict[str, Any]) -> str:
    parts = [legion["name"], legion["status"]]
    if legion.get("is_veteran"):
        parts.append("veteran")
    return " / ".join(parts)


def _fleet_summary(fleet) -> Dict[str, Any]:
    """Public fleet record (SA v1.1 §6.2 fleet_status V fields ONLY).

    EXACTLY number/name/fleet_type/status/is_veteran. The strength/commander/
    assigned_war_id/mission fields are ABSENT for EVERY relation — built from the
    canonical NavalSystem registry, never the debug ``show_fleets`` endpoint.
    """
    status = fleet.status.value if hasattr(fleet.status, "value") else str(fleet.status)
    return {
        "number": int(fleet.number),
        "name": fleet.name,
        "fleet_type": fleet.fleet_type,
        "status": status,
        "is_veteran": bool(fleet.is_veteran),
    }


def _fleet_item_value(fleet: Dict[str, Any]) -> str:
    parts = [fleet["name"], fleet["status"]]
    if fleet.get("is_veteran"):
        parts.append("veteran")
    return " / ".join(parts)


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


def _format_year(year: int) -> str:
    if year < 0:
        return f"{abs(year)} BC"
    return f"{year} AD"


# ===========================================================================
# S4 — contract_status / province_info
# ===========================================================================
# Canonical terminal contract statuses (never "awarded" -> OWN private fields
# absent even if an awarded_faction were (spuriously) set).
_CONTRACT_TERMINAL_STATUSES = {"pending", "budgeted"}

# Canonical province governor types (office enum) -> localized via query.office.*.
_OFFICE_TYPES = {
    "consul", "censor", "praetor", "quaestor", "tribune", "proconsul",
    "propraetor", "dictator",
}


def _contract_type_key(ctype: Any) -> str:
    return f"query.contract.type.{ctype}" if ctype else ""


def _contract_status_key(status: Any) -> str:
    return f"query.contract.status.{status}" if status else ""


def _project_contract(state: GameState, contract, viewer_faction_id: str) -> Dict[str, Any]:
    """Viewer projection for one contract (SA v1.1 §6.1/§6.2).

    Ownership = ``contract.awarded_faction`` ONLY (``awarded_to`` is a public
    official reference, never an ownership grant). Missing ``awarded_faction``
    -> UNOWNED. OWN private economics are built ONLY for an OWN, awarded,
    data-consistent contract; otherwise they are absent (never blank).
    """
    ctype = contract.contract_type.value if hasattr(contract.contract_type, "value") \
        else str(contract.contract_type)
    status = contract.status.value if hasattr(contract.status, "value") \
        else str(contract.status)
    awarded_faction = contract.awarded_faction
    awarded_to = contract.awarded_to

    if not awarded_faction:
        relation = "UNOWNED"
    elif awarded_faction == viewer_faction_id:
        relation = "OWN"
    else:
        relation = "OTHER"

    # Data integrity: when both are present, ``awarded_to`` must belong to
    # ``awarded_faction``; otherwise the pair is UNVERIFIED -> public only.
    consistent = True
    if awarded_faction and awarded_to is not None:
        figure = state.get_member(awarded_to)
        if figure is None or getattr(figure, "faction_id", None) != awarded_faction:
            consistent = False

    faction = state.get_faction(awarded_faction) if awarded_faction else None
    awarded_to_name = ""
    if awarded_to is not None:
        figure = state.get_member(awarded_to)
        if figure is not None:
            awarded_to_name = figure.get_formal_name()

    awarded = status not in _CONTRACT_TERMINAL_STATUSES
    record = {
        "id": int(contract.id),
        "name": contract.name,
        "type": ctype,
        "status": status,
        "awarded_faction": awarded_faction or "",
        "awarded_faction_name": faction.name if faction else "",
        "awarded_to": awarded_to,
        "awarded_to_name": awarded_to_name,
        "relation": relation,
    }
    if relation == "OWN" and awarded and consistent:
        record["own"] = {
            "cost": contract.base_cost,
            "expected_profit": contract.expected_profit,
            "progress_collected": contract.total_collected,
            "progress_spent": contract.total_spent,
            "remaining_years": contract.remaining_years,
            "warranty": getattr(contract, "warranty_remaining", 0),
        }
    return record


def _build_contract_status(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    """Contract lifecycle list/detail (SA v1.1 §6.1/§6.2 / AC-07).

    Reads the canonical contract registry; public fields for every relation,
    OWN private economics only for an OWN + awarded + consistent contract.
    All bid/debug internals are absent. Missing canonical required source fails
    closed (never a fabricated success).
    """
    contracts = state.get_all_contracts()
    if contracts is None:
        return build_failure_dto("contract_status", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    if not _decimal_ids_valid([getattr(c, "id", None) for c in contracts]):
        # Nonpositive / duplicate canonical contract id -> query_failed (F1).
        return build_failure_dto("contract_status", "ERROR", ERR_QUERY_FAILED)
    for contract in contracts:
        if getattr(contract, "contract_type", None) is None \
                or getattr(contract, "status", None) is None:
            # Missing canonical required source -> system_unavailable (§6.2).
            return build_failure_dto("contract_status", "ERROR", ERR_SYSTEM_UNAVAILABLE)

    viewer_faction_id = viewer.faction_id
    records = [_project_contract(state, c, viewer_faction_id) for c in contracts]
    records.sort(key=lambda r: r["id"])

    if record_id:
        number = _parse_decimal(record_id)
        rec = next((r for r in records if r["id"] == number), None) \
            if number is not None else None
        if rec is None:
            return build_failure_dto("contract_status", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _contract_detail_dto(rec)

    normalized = _normalize_filter(filter_text)
    visible = [r for r in records if _match(r["name"], normalized)]
    items = [
        _item("query.item.contract", "合同", r["name"],
              {"contract_id": r["id"], "status": r["status"]}, record_id=str(r["id"]))
        for r in visible
    ]
    summary = {"count": len(visible)}
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "contract_status", result_state,
        message_key="query.contract_status.message",
        message="合同状态为只读，仅显示公开信息，未授权明细不返回。",
        summary=summary,
        items=items,
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _contract_detail_dto(record: Dict[str, Any]) -> Dict[str, Any]:
    """PT-02 field->value table: public rows always; OWN rows only when built."""
    fields = [
        _detail_field("query.contract.id", "ID", record["id"]),
        _detail_field("query.contract.type", "类型", "",
                      value_key=_contract_type_key(record["type"])),
        _detail_field("query.contract.name", "名称", record["name"]),
        _detail_field("query.contract.status", "状态", "",
                      value_key=_contract_status_key(record["status"])),
        _detail_field("query.contract.awarded_faction", "中标派系",
                      record["awarded_faction_name"],
                      value_key="" if record["awarded_faction_name"] else "query.value.none"),
        _detail_field("query.contract.awarded_to", "中标者", record["awarded_to_name"],
                      value_key="" if record["awarded_to_name"] else "query.value.none"),
    ]
    own = record.get("own")
    if own is not None:
        fields.extend([
            _detail_field("query.contract.cost", "成本", str(own["cost"])),
            _detail_field("query.contract.expected_profit", "预期收益",
                          str(own["expected_profit"])),
            _detail_field("query.contract.progress_collected", "已收进度",
                          str(own["progress_collected"])),
            _detail_field("query.contract.progress_spent", "已支出",
                          str(own["progress_spent"])),
            _detail_field("query.contract.remaining_years", "剩余年限",
                          str(own["remaining_years"])),
            _detail_field("query.contract.warranty", "质保剩余", str(own["warranty"])),
        ])
    return _dto(
        "contract_status", "OK",
        message_key="query.contract_status.message",
        message="合同详情为只读。",
        summary={},
        items=[],
        detail={"record_id": str(record["id"]), "fields": fields, "meta": {}},
    )


# --- province_info ----------------------------------------------------------
def _province_id_valid(value: Any) -> bool:
    """Canonical province id: non-bool int >= 0 (Italy id 0 is a legitimate id)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _province_ids_valid(ids: List[Any]) -> bool:
    seen = set()
    for i in ids:
        if not _province_id_valid(i):
            return False
        if i in seen:
            return False
        seen.add(i)
    return True


def _parse_province_selector(selector: str) -> Optional[int]:
    """Canonical province-id wire form: ``"0"`` or ``[1-9][0-9]*`` (no signs,
    whitespace, leading zeroes or fractions). Extends the §5.3 decimal grammar to
    the province domain's legitimate zero id (Italy); all other decimal selectors
    keep the strict :data:`_DECIMAL_RE`."""
    if not isinstance(selector, str):
        return None
    if selector == "0":
        return 0
    if _DECIMAL_RE.fullmatch(selector) is None:
        return None
    return int(selector)


def _province_controller_name(state: GameState, province_id: int) -> str:
    for faction in state.factions.values():
        if province_id in faction.province_owned:
            return faction.name
    return ""


def _project_province(state: GameState, province) -> Dict[str, Any]:
    """Viewer projection for one province (SA v1.1 §6.2): public fields + public
    contract summaries only; ``land_private`` / financial / internal fields absent."""
    governor_name = ""
    if province.governor_id is not None:
        figure = state.get_member(province.governor_id)
        if figure is not None:
            governor_name = figure.get_formal_name()

    tax_name = ""
    if province.tax_contract_id:
        contract = state.get_contract(province.tax_contract_id)
        if contract is not None:
            tax_name = contract.name
    project_name = ""
    if province.project_contract_id:
        contract = state.get_contract(province.project_contract_id)
        if contract is not None:
            project_name = contract.name

    return {
        "province_id": province.province_id,
        "name": province.name,
        "total_land": province.total_land,
        "land_public": province.land_public,
        "governor_name": governor_name,
        "governor_type": province.governor_type or "",
        "controller": _province_controller_name(state, province.province_id),
        "grievance": province.grievance,
        "tax_contract_name": tax_name,
        "project_contract_name": project_name,
    }


def _build_province_info(state: GameState, viewer, filter_text: str, record_id: str) -> Dict[str, Any]:
    """Conquered-province list/detail (SA v1.1 §6.1/§6.2 / AC-08).

    Visibility = ``conquered == True``; unconquered / absent ids -> typed
    ``record_unavailable`` (DENIED). ``land_private`` and financial/internal
    fields are absent for EVERY viewer. Missing canonical required source fails
    closed.
    """
    provinces = state.get_all_provinces()
    if provinces is None:
        return build_failure_dto("province_info", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    conquered = [p for p in provinces if getattr(p, "conquered", False)]
    if not _province_ids_valid([getattr(p, "province_id", None) for p in conquered]):
        return build_failure_dto("province_info", "ERROR", ERR_QUERY_FAILED)
    for province in conquered:
        if province.province_id is None or province.name is None \
                or province.total_land is None or province.land_public is None \
                or province.grievance is None:
            return build_failure_dto("province_info", "ERROR", ERR_SYSTEM_UNAVAILABLE)
    conquered.sort(key=lambda p: p.province_id)

    if record_id:
        pid = _parse_province_selector(record_id)
        rec = next((p for p in conquered if p.province_id == pid), None) \
            if pid is not None else None
        if rec is None:
            return build_failure_dto("province_info", "DENIED", ERR_RECORD_UNAVAILABLE)
        return _province_detail_dto(state, rec)

    normalized = _normalize_filter(filter_text)
    visible = [p for p in conquered if _match(p.name, normalized)]
    items = [
        _item("query.item.province", "行省", p.name, {"province_id": p.province_id},
              record_id=str(p.province_id))
        for p in visible
    ]
    summary = {"count": len(visible)}
    result_state = "OK" if items else "EMPTY"
    return _dto(
        "province_info", result_state,
        message_key="query.province_info.message",
        message="行省信息为只读，仅显示已征服行省的公开摘要。",
        summary=summary,
        items=items,
        filters={"field": "name", "options": [], "applied": normalized},
    )


def _province_detail_dto(state: GameState, province) -> Dict[str, Any]:
    rec = _project_province(state, province)
    governor_name = rec["governor_name"]
    controller = rec["controller"]
    gtype = rec["governor_type"]
    fields = [
        _detail_field("query.province.id", "行省ID", rec["province_id"]),
        _detail_field("query.province.name", "名称", rec["name"]),
        _detail_field("query.province.total_land", "总土地", f"{rec['total_land']} C"),
        _detail_field("query.province.land_public", "公地", f"{rec['land_public']} C"),
        _detail_field("query.province.governor", "总督", governor_name,
                      value_key="" if governor_name else "query.value.none"),
        _detail_field("query.province.governor_type", "行省类型", "",
                      value_key=(f"query.office.{gtype}" if gtype in _OFFICE_TYPES else "")),
        _detail_field("query.province.controller", "控制派系", controller,
                      value_key="" if controller else "query.value.none"),
        _detail_field("query.province.grievance", "民怨", rec["grievance"]),
        _detail_field("query.province.tax_contract", "包税合同", rec["tax_contract_name"],
                      value_key="" if rec["tax_contract_name"] else "query.value.none"),
        _detail_field("query.province.project_contract", "工程合同",
                      rec["project_contract_name"],
                      value_key="" if rec["project_contract_name"] else "query.value.none"),
    ]
    return _dto(
        "province_info", "OK",
        message_key="query.province_info.message",
        message="行省详情为只读。",
        summary={},
        items=[],
        detail={"record_id": str(rec["province_id"]), "fields": fields, "meta": {}},
    )


# ---------------------------------------------------------------------------
# Handler registry (a known canonical id absent here fails closed as
# ``not_implemented``; slices S2–S5 register the remaining domains).
# ---------------------------------------------------------------------------
_HANDLERS: Dict[str, Callable[[GameState, Any, str, str], Dict[str, Any]]] = {
    "game_status": _build_game_status,
    "faction_info": _build_faction_info,
    "faction_treasury": _build_faction_treasury,
    "public_land": _build_public_land,
    "private_land": _build_private_land,
    "war_list": _build_war_list,
    "legion_status": _build_legion_status,
    "fleet_status": _build_fleet_status,
    "figure_search": _build_figure_search,
    "help": _build_help,
    "contract_status": _build_contract_status,
    "province_info": _build_province_info,
}
