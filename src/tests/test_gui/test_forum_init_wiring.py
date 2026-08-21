"""
src/tests/test_gui/test_forum_init_wiring.py

GUI wiring tests for canonical forum initialization (GUI-BETA-R1 WP-C).

Covers AU-2 open_market -> initialize_forum_turn wiring through the GUI
adapter / session store (T-W-01..06): core wiring blind-spot break
(pre-fix FAIL / post-fix PASS), session_store step wiring, AI parity,
re-enter exactly-once, ODR-05 DTO compatibility, and three-path parity.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.session_store import GuiSessionStore
from src.api import forum_api
from src.api import session_api
from src.core.entities.contract import ContractType

DTO_ROW_KEYS = (
    "id", "name", "martial", "intellect", "charisma", "zeal",
    "influence", "wealth", "class_tier", "class_label", "cost",
)


def _setup():
    result = session_api.create_gui_prototype_session(start_phase="forum")
    assert result["success"]
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    adapter = GuiApiAdapter(state)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    return state, viewer, adapter, store


def _pyrrhic_threat(state):
    ws = state.get_war_system()
    if not ws:
        return None
    return next((w for w in ws.get_threat_wars() if w.id == "pyrrhic_war"), None)


def _italy_works_contracts(state):
    return [
        c for c in state.get_all_contracts()
        if c.contract_type == ContractType.PUBLIC_WORKS and c.province_id == 0
    ]


def test_open_market_triggers_canonical_init():
    """T-W-01 core wiring blind-spot break (009/014/015):
    open_forum_market must run the canonical init side effects.
    修复前 FAIL（open_market 只生成 market figures，不触发 war/contracts）。
    """
    state, viewer, adapter, _ = _setup()
    feedback = adapter.open_forum_market(viewer)
    assert feedback["success"]

    # 015: war trigger
    pyrrhic = _pyrrhic_threat(state)
    assert pyrrhic is not None, "pyrrhic_war must be a THREAT after open_market"
    assert pyrrhic.threat_level >= 1

    # 014: contract generation
    assert _italy_works_contracts(state), "Italy PUBLIC_WORKS contract expected after open_market"

    # 009: hero markers consumed/consistent (prototype: no mortality -> no markers)
    assert state.hero_spawned_this_turn is False
    assert state.hero_to_spawn is None

    # exactly-once guard set
    assert state.get_forum_pending().get("forum_initialized")


def test_do_complete_forum_step_wiring():
    """T-W-02: session_store.doCompleteForumStep() (retirement step) triggers init."""
    state, viewer, adapter, store = _setup()
    assert store.forumCurrentStep == "retirement"
    feedback = store.doCompleteForumStep()
    assert feedback["success"]
    assert store.forumCurrentStep == "market"
    assert _pyrrhic_threat(state) is not None
    assert _italy_works_contracts(state)


def test_ai_path_uses_same_init():
    """T-W-03: AI path post-conditions match human path and do not duplicate."""
    state, viewer, adapter, store = _setup()
    store.doCompleteForumStep()  # human open + AI processing
    threats_after = len(state.get_war_system().get_threat_wars())
    italy_works_after = len(_italy_works_contracts(state))

    # Re-invoking the AI processing is a no-op (runtime guard)
    store._process_ai_factions_forum()
    assert len(state.get_war_system().get_threat_wars()) == threats_after
    assert len(_italy_works_contracts(state)) == italy_works_after
    assert store._forum_ai_processed is True


def test_re_enter_no_duplicate():
    """T-W-04: re-enter / refresh never duplicates init side effects."""
    state, viewer, adapter, store = _setup()
    f1 = store.doCompleteForumStep()
    assert f1["success"]
    threats_1 = sorted(w.id for w in state.get_war_system().get_threat_wars())
    contracts_1 = len(state.get_all_contracts())
    figures_1 = len(state.curia.get_all_available())

    # Refresh re-reads the DTO only — no side effects
    store._refresh_forum_view()
    assert sorted(w.id for w in state.get_war_system().get_threat_wars()) == threats_1
    assert len(state.get_all_contracts()) == contracts_1
    assert len(state.curia.get_all_available()) == figures_1

    # Same-turn re-open -> market_opened early exit, nothing re-generated
    f3 = adapter.open_forum_market(viewer)
    assert f3["success"]
    assert f3["data"]["generated_figures"] == []
    assert sorted(w.id for w in state.get_war_system().get_threat_wars()) == threats_1
    assert len(state.get_all_contracts()) == contracts_1
    assert len(state.curia.get_all_available()) == figures_1


def test_open_market_generated_figures_dto_compat():
    """T-W-05 (ODR-05): generated_figures row shape unchanged; early-exit returns []."""
    state, viewer, adapter, _ = _setup()
    f1 = adapter.open_forum_market(viewer)
    assert f1["success"]
    rows = f1["data"]["generated_figures"]
    assert len(rows) == 3, f"prototype (no mortality) yields 3 figures, got {len(rows)}"
    for row in rows:
        for key in DTO_ROW_KEYS:
            assert key in row, f"missing DTO key {key} in {row}"

    f2 = adapter.open_forum_market(viewer)
    assert f2["success"]
    assert f2["data"]["generated_figures"] == []


def test_three_paths_init_parity():
    """T-W-06: GUI open_market / CLI canonical entry / direct API produce same post-conditions."""
    # GUI path
    state_g, viewer_g, adapter_g, _ = _setup()
    assert adapter_g.open_forum_market(viewer_g)["success"]
    gui_threats = sorted(w.id for w in state_g.get_war_system().get_threat_wars())
    gui_italy_works = bool(_italy_works_contracts(state_g))

    # CLI path (canonical entry used by ForumCommand._execute_normal after AU-7)
    state_c, _, _, _ = _setup()
    assert forum_api.initialize_forum_turn(state_c)["success"]
    cli_threats = sorted(w.id for w in state_c.get_war_system().get_threat_wars())
    cli_italy_works = bool(_italy_works_contracts(state_c))

    # Direct API entry
    state_d, _, _, _ = _setup()
    assert forum_api.initialize_forum_turn(state_d)["success"]
    dir_threats = sorted(w.id for w in state_d.get_war_system().get_threat_wars())

    assert gui_threats == cli_threats == dir_threats
    assert gui_italy_works is True
    assert cli_italy_works is True
    # hero consumption state parity
    assert state_g.hero_spawned_this_turn is False
    assert state_c.hero_spawned_this_turn is False
    assert state_g.get_forum_pending().get("forum_initialized")
    assert state_c.get_forum_pending().get("forum_initialized")
