# src/tests/test_api/test_wpj_groupd_rebellion_events.py
"""WP-J Group-D-Rebellion (J-AC-04b) — DATA(PRODUCTION_CHAIN) 投影/谓词/空态测试。

冻结设计 v1.1（`02-sa-design/GroupD/`）：
- FC-D09：起义警示读模型 `rebellion_events` 单一 owner = `forum_api.get_forum_view()`；
          载体 = 只读 `GameState._forum_rebellion_events`（镜像 `_forum_war_events`）。
- FC-D10：shape = [{id:str,name:int,province_id:int,province_name:str}]（逐字 = producer 映射）；
          仅新触发起义（不含 war_threats / 军团池变化）。
- FC-D11：警示仅消费权威事件产出（`initialize_forum_turn` 内 `check_province_unrest`），
          不自造生命周期时点 / 不依 grievance 现值推断未来。
- FC-D12：不含军团池变化 / 不重开起义创建·招募规则。
- FC-D07：rebellion_events 空 → 不追加起义行。

No-Test-Assisted-Transition：目标态经真实生产动作
`forum_api.initialize_forum_turn()`（经 `open_market` 触发）到达。
"""
from src.api import session_api, forum_api


def _session(start_phase="forum"):
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    return state, viewer


def _view(state, viewer):
    resp = forum_api.get_forum_view(state, viewer)
    assert resp["success"], resp.get("message")
    return resp["data"]


def _province(state, province_id=1):
    p = state.get_province(province_id)
    assert p is not None, f"province {province_id} 缺失"
    return p


# ---------------------------------------------------------------------------
# 投影（FC-D09/FC-D10）
# ---------------------------------------------------------------------------

def test_rebellion_events_key_present_and_empty_by_default():
    state, viewer = _session()
    data = _view(state, viewer)
    assert "rebellion_events" in data, "get_forum_view 必须 additive 暴露 rebellion_events（FC-D09）"
    assert data["rebellion_events"] == [], "未触发起义 → 空（FC-D07）"


def test_projection_reads_carrier_verbatim():
    state, viewer = _session()
    rows = [{"id": "reb-3", "name": 3, "province_id": 1, "province_name": "西西里"}]
    state.set_forum_rebellion_events(rows)
    assert _view(state, viewer)["rebellion_events"] == rows, "逐字透传载体（FC-D10）"


# ---------------------------------------------------------------------------
# 集成：真实生产链（initialize_forum_turn → check_province_unrest）
# ---------------------------------------------------------------------------

def test_initialize_forum_turn_captures_authoritative_rebellion():
    state, viewer = _session()
    province = _province(state, 1)
    province.set_event_flag("rebellion_active", False)
    province.set_grievance(3)

    resp = forum_api.open_market(state, viewer)   # 触发 initialize_forum_turn（含 check_province_unrest）
    assert resp["success"], resp.get("message")

    carrier = state.get_forum_rebellion_events()
    assert carrier, "initialize_forum_turn 之后载体必须捕获权威起义事件（FC-D09）"
    row = carrier[0]
    assert row["province_id"] == 1 and row["province_name"] == province.name, "权威 actor（FC-D10）"
    assert set(row) == {"id", "name", "province_id", "province_name"}, "shape 逐字（FC-D10）"

    view_rows = _view(state, viewer)["rebellion_events"]
    assert view_rows == carrier, "get_forum_view 投影一致"


def test_no_rebellion_when_no_province_qualifies():
    state, viewer = _session()
    for p in state.get_all_provinces():
        p.set_event_flag("rebellion_active", False)
        p.set_grievance(0)
    assert forum_api.open_market(state, viewer)["success"]
    assert state.get_forum_rebellion_events() == [], "无省达标 → 空（FC-D07）"


def test_active_rebellion_not_retriggered():
    """FC-D10：已激活起义（active_rebellion）不新增「爆发」行。"""
    state, viewer = _session()
    province = _province(state, 1)
    province.set_grievance(3)
    province.set_event_flag("rebellion_active", True)
    assert forum_api.open_market(state, viewer)["success"]
    assert state.get_forum_rebellion_events() == [], "active_rebellion 不再触发新起义（FC-D10）"


def test_enable_threats_false_returns_empty():
    """FC-D09/FC-D10：enable_threats=False → producer 返回空 → 不追加行。"""
    state, viewer = _session()
    state.config.enable_threats = False   # Config.__setattr__ → 顶层键
    assert state.config.get("enable_threats", True) is False
    province = _province(state, 1)
    province.set_event_flag("rebellion_active", False)
    province.set_grievance(3)
    assert forum_api.open_market(state, viewer)["success"]
    assert state.get_forum_rebellion_events() == []


# ---------------------------------------------------------------------------
# 生命周期（FC-D09：结算同区清理；re-entry 幂等）
# ---------------------------------------------------------------------------

def test_accessor_clear_and_annual_settlement_clears_carrier():
    state, viewer = _session()
    state.set_forum_rebellion_events([{"id": "x", "name": 1, "province_id": 1, "province_name": "p"}])
    state.clear_forum_rebellion_events()
    assert state.get_forum_rebellion_events() == []

    state.set_forum_rebellion_events([{"id": "y", "name": 2, "province_id": 2, "province_name": "q"}])
    state.advance_year()   # _commit_settlement 与 _forum_war_events 同区清空
    assert state.get_forum_rebellion_events() == [], "跨年结算清理载体（FC-D09）"


def test_reentry_idempotent_projection():
    state, viewer = _session()
    province = _province(state, 1)
    province.set_event_flag("rebellion_active", False)
    province.set_grievance(3)
    assert forum_api.open_market(state, viewer)["success"]
    first = _view(state, viewer)["rebellion_events"]
    second = _view(state, viewer)["rebellion_events"]
    assert first == second and first, "刷新幂等（FC-D09）"
