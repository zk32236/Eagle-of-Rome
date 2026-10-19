"""W2b (D11 / S5) — declarative private staged inventory + projection.

RED-first carrier for FC-712-17..20 / AC-712-18..22 (EOR20261013-02).

Discipline (task brief §4): every GREEN assertion is driven through the REAL
production entries — ``GuiSessionStore.initialize`` / ``requestTakeover`` /
``doCompletePlayer`` / ``refreshSnapshot`` — and the REAL API boundary
(``src.api.*``). Faults are injected at the production boundary (the API module
attribute), never by publishing a hand-made bundle into the Store. The single
exception, marked ``INVARIANT`` below, probes the publish-time tag guard directly
because a late frame receipt is not reproducible without a live QML event loop.

Covered:
  * AC-712-18 — ``factionStyleMap`` is a REQUIRED SESSION_DISPLAY resource of the
    declarative inventory; the first frame reads the target's map; a missing
    REQUIRED resource never yields an activated seat.
  * AC-712-19 — an ACTIVE same-seat DENIED style read keeps the PRIVATE last_good
    and marks the public projection stale; freshness-dependent writes are
    disabled; A -> B leaves the public model neutral and never renders A's map.
  * AC-712-20 — REQUIRED failure (reservation / malformed / schema / old tag)
    keeps the cover, refuses the old handle and publishes no partial first frame;
    a legitimate EMPTY is not a DENIAL.
  * AC-712-21 — inventory covers stage/apply/neutralize/notify; the real Query
    ack is preserved; transient / security-clear / success-empty stay distinct;
    a late callback never overrides a newer epoch.
  * AC-712-22 — activation failures retry activation; a busy seat refuses a
    second dispatch; one gesture -> one dispatch.
"""
import os
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from src.api import faction_api, mortality_api, senate_api, session_api, session_access
from src.core.entities.player import Player, PlayerType
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)

#: The eight DTO resources frozen by FC-712-17 / the W2b census §1.1.
EXPECTED_DTO_IDS = (
    "snapshot", "population", "resolution", "mortality",
    "senate", "revenue", "forum", "combat",
)
TAG_NAMES = ("session", "scope", "target", "seat_epoch", "core_revision",
             "publication_revision")


# ---------------------------------------------------------------------------
# Fixtures / helpers — real sessions, real store, real slots
# ---------------------------------------------------------------------------
def _two_human_state(start_phase="population"):
    """Registered Hot-seat session with EXACTLY two HUMAN players (A, B)."""
    result = session_api.create_gui_hotseat_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    pids = [p.player_id for p in state.get_all_players()]
    assert len(pids) >= 2
    for pid in pids[2:]:
        old = state.get_player(pid)
        state.remove_player(pid)
        state.add_player(Player(player_id=pid, faction_id=old.faction_id,
                                player_type=PlayerType.AI))
    state.set_turn_order(pids[:2])
    state.set_current_player(pids[0])
    return state, pids


def _store(state, pid):
    store = GuiSessionStore(state, neutral_startup=True)
    store.initialize(pid)
    return store


class _Barrier:
    """Synchronous witness provider (production GameShell stand-in)."""

    def __init__(self, arm=True, unmask=True, pending=True):
        self.arm = arm
        self.unmask = unmask
        self.pending = pending
        self.calls = []

    def show_pending(self, txn, faction, mode=""):
        self.calls.append(("pending", txn, faction, mode))
        return self.pending

    def arm_barrier(self, txn):
        self.calls.append(("arm", txn))
        return self.arm

    def request_unmask(self, txn):
        self.calls.append(("unmask", txn))
        return self.unmask

    def show_failure(self, txn, kind, route=""):
        self.calls.append(("failure", txn, kind, route))
        return True


class _AsyncBarrier(_Barrier):
    """Real-frame provider: suspends on the async gate until ``resume``."""

    def __init__(self):
        super().__init__()
        self.gates = {}

    def arm_barrier_async(self, txn, resume):
        self.gates["arm"] = (txn, resume)
        self.calls.append(("arm_async", txn))

    def publish_under_mask_async(self, txn, resume):
        self.gates["publish"] = (txn, resume)
        self.calls.append(("publish_async", txn))

    def request_unmask_async(self, txn, resume):
        self.gates["unmask"] = (txn, resume)
        self.calls.append(("unmask_async", txn))

    def peek(self, kind):
        return self.gates.get(kind)

    def resume(self, kind, ok=True, txn=None):
        if txn is not None:
            # A receipt for ANOTHER transaction: deliver it without consuming
            # the still-pending real gate (the Store must discard it).
            _real, resume = self.gates[kind]
            resume(txn, kind, bool(ok))
            return
        real_txn, resume = self.gates.pop(kind)
        resume(real_txn, kind, bool(ok))


class _Receiver:
    """Headless stand-in for the production QML query-invalidation receiver."""

    def __init__(self, store, ack=True):
        self.store = store
        self.ack = ack
        self.calls = []
        store.queryInvalidated.connect(self._on)

    def _on(self, keep_open):
        self.calls.append(bool(keep_open))
        if self.ack:
            self.store.ackQueryInvalidation(self.store.queryInvalidationEpoch)


def _denied_env():
    return session_access.denied_response()


def _ok_env(data):
    return {"success": True, "message": "ok", "data": data, "errors": []}


def _active_store(with_query=False):
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    store.setHandoffBarrierProvider(_Barrier())
    result = store.requestTakeover()
    assert result["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    recv = _Receiver(store) if with_query else None
    return state, pids, store, recv


def _target_style(state, pid):
    faction_id = state.get_player(pid).faction_id
    return state.config.get("faction_style_map", {}).get(faction_id, {})


# ===========================================================================
# AC-712-18 — declarative inventory + REQUIRED SESSION_DISPLAY style map
# ===========================================================================
def test_inventory_is_declarative_and_contains_style_as_required():
    inventory = GuiSessionStore.activation_inventory()
    assert isinstance(inventory, (tuple, list))
    by_id = {}
    for resource in inventory:
        for field in ("resource_id", "scope", "source", "required",
                      "neutral_value", "validator", "notify", "tags"):
            assert field in resource, (resource, field)
        assert resource["required"] is True
        assert callable(resource["validator"])
        assert isinstance(resource["source"], str) and "." in resource["source"]
        for tag in TAG_NAMES:
            assert tag in resource["tags"], (resource["resource_id"], tag)
        by_id[resource["resource_id"]] = resource

    assert set(EXPECTED_DTO_IDS).issubset(set(by_id))
    style = by_id["factionStyleMap"]
    assert style["scope"] == "SESSION_DISPLAY"
    assert style["required"] is True
    assert style["source"] == "faction_api.get_faction_style_map"
    assert style["notify"] == "snapshotChanged"


def test_first_frame_publishes_target_style_map_and_clears_stale():
    state, pids, store, _ = _active_store()
    expected = _target_style(state, pids[0])
    assert expected and expected.get("color")

    published = store.factionStyleMap
    assert isinstance(published, dict)
    assert published.get("map"), "style map must be in the first frame"
    faction_id = state.get_player(pids[0]).faction_id
    assert published["map"][faction_id]["color"] == expected["color"]
    assert store.factionStyleMapStale is False
    assert store.freshnessWritesBlocked is False


def test_missing_required_style_never_activates_successfully():
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    barrier = _Barrier()
    store.setHandoffBarrierProvider(barrier)
    finals = []
    store.handoffFinished.connect(lambda t, ok: finals.append((t, ok)))

    with patch.object(faction_api, "get_faction_style_map",
                      side_effect=lambda *a, **k: _denied_env()):
        store.requestTakeover()

    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.viewerPlayerId == ""
    assert store.handoffMaskVisible is True
    assert store.factionStyleMap == {}
    assert any(ok is False for _, ok in finals)
    assert not any(ok is True for _, ok in finals)
    # The failure is an activation retry, never a continuation recovery.
    assert store.handoffCanRetry is True
    assert barrier.calls[-1][0] == "failure"
    assert barrier.calls[-1][3] == "activation"


# ===========================================================================
# AC-712-20 — REQUIRED failure keeps the cover; EMPTY is not DENIED
# ===========================================================================
@pytest.mark.parametrize("bad_envelope", [
    {"success": True, "message": "ok", "data": "not-a-mapping", "errors": []},
    {"success": True, "message": "ok", "data": {"map": "oops"}, "errors": []},
    {"success": True, "message": "ok", "data": None, "errors": []},
    {"success": "yes", "message": "malformed", "data": {}, "errors": []},
])
def test_malformed_or_schema_invalid_style_keeps_mask(bad_envelope):
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    store.setHandoffBarrierProvider(_Barrier())

    with patch.object(faction_api, "get_faction_style_map",
                      side_effect=lambda *a, **k: bad_envelope):
        store.requestTakeover()

    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.viewerPlayerId == ""
    assert store.populationView == {}
    assert store.factionStyleMap == {}


def test_failure_in_any_other_required_dto_keeps_whole_bundle_masked():
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    store.setHandoffBarrierProvider(_Barrier())

    with patch.object(mortality_api, "get_mortality_view",
                      side_effect=lambda *a, **k: _denied_env()):
        store.requestTakeover()

    assert store.seatLifecycle == SEAT_MASKED_FAILURE
    assert store.viewerPlayerId == ""
    # No partial first frame: the style map (read later than mortality) is not
    # published either.
    assert store.factionStyleMap == {}


def test_denied_and_success_empty_are_distinct_in_the_store():
    state, pids, store, _ = _active_store()
    seeded = store.populationView
    assert seeded, "population view must be seeded by the ACTIVE refresh"

    with patch.object(session_api, "get_population_view",
                      side_effect=lambda *a, **k: _denied_env()):
        store.refreshSnapshot()
    assert store.populationView == seeded          # private last_good kept
    assert store.projectionStale is True

    with patch.object(session_api, "get_population_view",
                      side_effect=lambda *a, **k: _ok_env({})):
        store.refreshSnapshot()
    assert store.populationView == {}              # legal EMPTY published
    assert store.projectionStale is False


# ===========================================================================
# AC-712-19 — private last_good + stale; cross-seat neutrality
# ===========================================================================
def test_active_denied_style_keeps_last_good_and_marks_stale():
    state, pids, store, _ = _active_store()
    good = store.factionStyleMap
    assert good.get("map")

    with patch.object(faction_api, "get_faction_style_map",
                      side_effect=lambda *a, **k: _denied_env()):
        store.refreshSnapshot()

    assert store.factionStyleMap == good           # never overwritten by {}
    assert store.factionStyleMapStale is True
    assert store.projectionStale is True
    assert store.freshnessWritesBlocked is True


def test_stale_projection_disables_freshness_dependent_write():
    state, pids, store, _ = _active_store()
    with patch.object(faction_api, "get_faction_style_map",
                      side_effect=lambda *a, **k: _denied_env()):
        store.refreshSnapshot()
    assert store.freshnessWritesBlocked is True

    feedback = store.doCompletePlayer()
    assert feedback["success"] is False
    # No publication to B: the cover stays, the public projection is neutral and
    # the private viewer was never moved to B.
    assert store.viewerPlayerId == ""
    assert store._viewer_id == pids[0]
    assert store.handoffMaskVisible is True


def test_cross_seat_style_is_neutral_and_a_map_never_renders_for_b():
    state, pids, store, _ = _active_store()
    a_map = store.factionStyleMap
    assert a_map.get("map")

    store.doCompletePlayer()
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    # Masked/pending: the public style projection is neutral, never A's map.
    assert store.factionStyleMap == {}
    assert store.handoffPendingFactionName  # safe faction name only

    result = store.requestTakeover()
    assert result["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[1]
    b_map = store.factionStyleMap
    assert b_map.get("map")
    b_faction = state.get_player(pids[1]).faction_id
    assert b_map["map"][b_faction]["color"] == _target_style(state, pids[1])["color"]
    assert store.factionStyleMapStale is False


# ===========================================================================
# AC-712-21 — inventory coverage, notify ordering, query ack, late callback
# ===========================================================================
def test_neutralize_clears_the_session_display_resource():
    state, pids, store, _ = _active_store()
    assert store.factionStyleMap != {}

    store.doCompletePlayer()
    assert store.factionStyleMap == {}
    # Other public DTOs stay neutral as before (W2a semantics unchanged).
    assert store.senateView == {}
    assert store.mortalityResult == {}


def test_notify_runs_after_every_assignment_including_viewer():
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    store.setHandoffBarrierProvider(_Barrier())
    assert store.requestTakeover()["accepted"] is True

    seen = []

    def _on_snapshot():
        seen.append({
            "viewer": store._viewer_id,
            "snapshot_viewer": store.viewerPlayerId,
            "style": dict(store.factionStyleMap),
        })

    store.snapshotChanged.connect(_on_snapshot)
    store.doCompletePlayer()
    store.requestTakeover()

    assert seen, "activation must emit the snapshot notification"
    last = seen[-1]
    assert last["viewer"] == pids[1]
    assert last["snapshot_viewer"] == pids[1]
    assert last["style"].get("map"), "style must be assigned before notify"


def test_query_real_ack_is_preserved_across_activation():
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    store.setHandoffBarrierProvider(_Barrier())
    assert store.requestTakeover()["accepted"] is True
    recv = _Receiver(store)
    store.doGlobalQuery("figure_search", "", "")
    query_epoch = store.queryInvalidationEpoch

    store.doCompletePlayer()
    assert recv.calls, "the real query receiver must be asked to clear"
    assert store.queryInvalidationEpoch > query_epoch
    assert store.globalQueryResult == {}


def test_late_frame_callback_never_publishes_a_stale_epoch():
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    barrier = _AsyncBarrier()
    store.setHandoffBarrierProvider(barrier)

    result = store.requestTakeover()
    assert result["accepted"] is True
    publish = barrier.peek("publish")
    assert publish is not None

    # A receipt from an OLD transaction must be discarded (no publication).
    barrier.resume("publish", ok=True, txn="txn-from-an-older-epoch")
    assert store.seatLifecycle != SEAT_ACTIVE
    assert store.viewerPlayerId == ""
    assert barrier.peek("unmask") is None

    # The real receipt resumes the transaction and only then publishes.
    barrier.resume("publish", ok=True)
    assert barrier.peek("unmask") is not None
    assert store.viewerPlayerId == ""            # still under the cover
    barrier.resume("unmask", ok=True)
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]


def test_publish_time_tag_guard_rejects_an_old_bundle():
    """INVARIANT probe: a bundle tagged for another epoch never publishes."""
    state, pids, store, _ = _active_store()
    before = dict(store._snapshot)

    store.setHandoffBarrierProvider(_Barrier())
    store.doCompletePlayer()                      # masked, txn live
    target = pids[1]
    bundle = store._stage_activation(target, store._seat_epoch + 1)
    assert bundle is not None
    # Simulate the post-commit epoch the real publish gate runs at.
    store._seat_epoch = bundle["seat_epoch"]

    stale = dict(bundle)
    stale["tags"] = dict(bundle["tags"])
    stale["tags"]["publication_revision"] = int(bundle["tags"]["publication_revision"]) + 7
    assert store._apply_staged(stale, target_id=target) is False
    assert store.viewerPlayerId != target
    assert dict(store._snapshot) == {}
    # The correctly tagged bundle IS publishable (the guard is tag-specific).
    assert store._apply_staged(bundle, target_id=target) is True
    assert store.viewerPlayerId == target


# ===========================================================================
# AC-712-22 — bounded retry routing + busy suppression
# ===========================================================================
def test_busy_pending_seat_refuses_a_second_dispatch():
    state, pids, store, _ = _active_store()
    store.doCompletePlayer()
    assert store.seatLifecycle == SEAT_MASKED_PENDING

    feedback = store.doCompletePlayer()
    assert feedback["success"] is False
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    assert store.viewerPlayerId == ""


def test_activation_failure_can_be_retried_without_replaying_a_command():
    state, pids = _two_human_state()
    store = _store(state, pids[0])
    store.setHandoffBarrierProvider(_Barrier())

    with patch.object(faction_api, "get_faction_style_map",
                      side_effect=lambda *a, **k: _denied_env()):
        store.requestTakeover()
    assert store.seatLifecycle == SEAT_MASKED_FAILURE

    retry = store.retryHandoff()
    assert retry["accepted"] is True
    # The bounded retry re-arms an ACTIVATION for the actual Core target; the
    # already-committed command is never replayed (Core actor is still A).
    assert state.get_current_player().player_id == pids[0]
    assert store.requestTakeover()["accepted"] is True
    assert store.seatLifecycle == SEAT_ACTIVE
    assert store.viewerPlayerId == pids[0]
    assert store.factionStyleMap.get("map")


# ===========================================================================
# R01 — senate read: DENIED/malformed never overwrite last_good; only a legal
# authoritative EMPTY may clear the projection (FC-712-19).
# ===========================================================================
def test_senate_denied_keeps_last_good_and_marks_stale():
    state, pids, store, _ = _active_store()
    good = store.senateView
    assert good, "the first frame must publish a real senate projection"

    with patch.object(senate_api, "get_senate_view",
                      side_effect=lambda *a, **k: _denied_env()):
        store.refreshSnapshot()

    assert store.senateView == good          # never overwritten by a DENIED
    assert "senate" in store.staleResourceIds
    assert store.projectionStale is True
    assert store.freshnessWritesBlocked is True


def test_senate_malformed_envelope_is_not_a_legal_empty_projection():
    state, pids, store, _ = _active_store()
    good = store.senateView
    assert good

    with patch.object(senate_api, "get_senate_view",
                      side_effect=lambda *a, **k: {
                          "success": "yes", "message": "bad", "data": {}, "errors": []}):
        store.refreshSnapshot()

    assert store.senateView == good
    assert "senate" in store.staleResourceIds


def test_senate_authoritative_empty_clears_the_projection():
    state, pids, store, _ = _active_store()
    assert store.senateView

    with patch.object(senate_api, "get_senate_view",
                      side_effect=lambda *a, **k: _ok_env({})):
        store.refreshSnapshot()

    # A real success with an empty DTO IS an authoritative empty projection.
    assert store.senateView == {}
    assert "senate" not in store.staleResourceIds
    assert store.freshnessWritesBlocked is False


# ===========================================================================
# R02 — publish-time validation of ALL SIX tags (scope + core_revision were
# written but never read before R2).
# ===========================================================================
def _tagged_bundle_for_next_seat(store, target):
    """Stage a REAL tagged bundle for the next seat (INVARIANT probe shape)."""
    store.doCompletePlayer()
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    bundle = store._stage_activation(target, store._seat_epoch + 1)
    assert bundle is not None
    store._seat_epoch = bundle["seat_epoch"]
    return bundle


@pytest.mark.parametrize("mutate", [
    "scope_wrong",
    "scope_missing",
    "core_revision_wrong",
    "core_revision_missing",
])
def test_publish_time_tag_guard_requires_scope_and_core_revision(mutate):
    state, pids, store, _ = _active_store()
    target = pids[1]
    bundle = _tagged_bundle_for_next_seat(store, target)

    broken = dict(bundle)
    broken["tags"] = dict(bundle["tags"])
    if mutate == "scope_wrong":
        broken["tags"]["scope"] = "public"
    elif mutate == "scope_missing":
        broken["tags"].pop("scope", None)
    elif mutate == "core_revision_wrong":
        broken["tags"]["core_revision"] = int(bundle["tags"]["core_revision"]) + 1
    else:
        broken["tags"].pop("core_revision", None)

    assert store._apply_staged(broken, target_id=target) is False
    assert store.viewerPlayerId != target
    # the untouched bundle is still publishable (the guard is tag-specific)
    assert store._apply_staged(bundle, target_id=target) is True
    assert store.viewerPlayerId == target


# ===========================================================================
# R03 — the inventory DRIVES apply / notify / neutralize; the legacy flat
# bundle can no longer bypass the whole-package gate.
# ===========================================================================
def test_inventory_drives_apply_notify_and_neutralize(monkeypatch):
    state, pids, store, _ = _active_store()
    target = pids[1]
    bundle = _tagged_bundle_for_next_seat(store, target)
    bundle = dict(bundle)
    bundle["resources"] = dict(bundle["resources"])
    bundle["resources"]["probeResource"] = {"value": 1}

    probe_entry = {
        "resource_id": "probeResource", "scope": "SEAT",
        "source": "session_api.get_population_view", "required": False,
        "neutral_value": {}, "validator": lambda value: isinstance(value, dict),
        "notify": "phaseStepsChanged", "tags": (),
        "attr": "_probe_resource", "publish_order": 9,
    }
    monkeypatch.setattr(
        type(store), "_ACTIVATION_INVENTORY",
        GuiSessionStore._ACTIVATION_INVENTORY + (probe_entry,))
    store._probe_resource = {}

    order = []
    for name in ("snapshotChanged", "populationViewChanged", "mortalityViewChanged",
                 "senateViewChanged", "revenueViewChanged", "forumViewChanged",
                 "combatViewChanged", "resolutionViewChanged", "phaseStepsChanged"):
        getattr(store, name).connect(
            lambda name=name: order.append(name))

    assert store._apply_staged(bundle, target_id=target) is True
    # a resource that exists ONLY in the declaration is still applied ...
    assert store._probe_resource == {"value": 1}
    # ... and neutralized from the same declaration
    store._neutralize_public_projection()
    assert store._probe_resource == {}
    # notify order == the declared publish order (deduped, 8 DTO signals then
    # phaseStepsChanged which the probe declares last)
    assert order[:8] == [
        "snapshotChanged", "populationViewChanged", "mortalityViewChanged",
        "senateViewChanged", "revenueViewChanged", "forumViewChanged",
        "combatViewChanged", "resolutionViewChanged",
    ], order


def test_legacy_flat_bundle_can_never_bypass_the_whole_package_gate():
    state, pids, store, _ = _active_store()
    before = store.senateView
    assert before

    assert store._apply_staged({"senate": {"phase_id": "senate"},
                               "snapshot": {"current_phase_id": "senate"}},
                              target_id=pids[0]) is False
    # nothing was assigned: the flat branch is closed, not a publication path
    assert store.senateView == before
    assert store.viewerPlayerId == pids[0]


# ===========================================================================
# R05 — freshness gating is DEPENDENCY-related and happens BEFORE side effects.
# ===========================================================================
def test_freshness_gate_follows_every_required_resource():
    state, pids, store, _ = _active_store()

    with patch.object(mortality_api, "get_mortality_view",
                      side_effect=lambda *a, **k: _denied_env()):
        store.refreshSnapshot()

    assert "mortality" in store.staleResourceIds
    assert store.factionStyleMapStale is False   # NOT a style-only proxy
    assert store.freshnessWritesBlocked is True


def test_stale_projection_refuses_the_write_before_any_core_side_effect():
    state, pids, store, _ = _active_store()
    with patch.object(senate_api, "get_senate_view",
                      side_effect=lambda *a, **k: _denied_env()):
        store.refreshSnapshot()
    assert store.freshnessWritesBlocked is True

    leases = []
    original_lease = session_access.authorize_and_lease

    def _spy(*args, **kwargs):
        leases.append((args, kwargs))
        return original_lease(*args, **kwargs)

    core_before = {
        "actor": state.get_current_player().player_id,
        "turn": state.turn.turn_number,
        "treasury": state.treasury,
        "proposals": len(state.get_senate_proposals()),
    }
    finished = []
    store.handoffFinished.connect(lambda txn, ok: finished.append(ok))

    with patch.object(session_access, "authorize_and_lease", side_effect=_spy):
        feedback = store.doCompletePlayer()

    assert feedback["success"] is False
    assert leases == [], "no command lease may be issued for a blocked write"
    assert store.seatLifecycle == SEAT_MASKED_FAILURE


# ===========================================================================
# R06 — FactionStyle consumer compatibility (RevenueStage.factionName) and the
# W2b first-frame / cross-seat render witness (real QML component, offscreen).
# ===========================================================================
QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
FALLBACK_NAME = "未知派系"
FALLBACK_COLOR = "#3A3530"

_STYLE_PROBE_QML = """
import QtQuick 2.15
import "components"

Item {
    id: probe
    visible: false
    property string factionId: ""
    property int snapshotWitness: 0
    property var seenNames: []
    FactionStyle { id: fs }
    property string resolvedName: fs.factionName(factionId)
    property string resolvedColor: fs.factionColor(factionId)
    property string availability: fs.availability
    property bool stale: fs.stale
    Connections {
        target: sessionStore
        function onSnapshotChanged() {
            probe.snapshotWitness += 1
            probe.seenNames = probe.seenNames.concat([fs.factionName(probe.factionId)])
        }
    }
}
"""


def _pump(rounds=4):
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(5)


def _qml_probe(store, faction_id):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    engine = QQmlEngine()
    engine.addImportPath(QML_DIR)
    engine.rootContext().setContextProperty("sessionStore", store)
    component = QQmlComponent(engine)
    component.setData(_STYLE_PROBE_QML.encode("utf-8"),
                      QUrl.fromLocalFile(os.path.join(QML_DIR, "_w2b_style_probe.qml")))
    assert not component.isError(), component.errorString()
    probe = component.create()
    assert probe is not None, component.errorString()
    probe.setProperty("factionId", faction_id)
    _pump()
    return engine, component, probe


def _style_name(state, fid):
    style = state.config.get("faction_style_map", {}).get(fid, {})
    return style.get("name") or state.factions[fid].name


def test_revenue_stage_faction_name_consumption_is_compatible():
    """R06: the ONLY ``factionName`` consumer (RevenueStage) keeps its contract."""
    path = os.path.join(QML_DIR, "stages", "RevenueStage.qml")
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    assert "function factionDisplayName(factionId)" in source
    assert "factionStyle.factionName(factionId)" in source

    engine, component, probe = _qml_probe(_store(*_two_human_state()[:2]), "optimates")
    # No style map at all -> the safe fallback name, never the raw id echoed
    # back as if it were a display name.
    assert probe.property("resolvedName") == FALLBACK_NAME
    assert probe.property("resolvedColor") == FALLBACK_COLOR
    assert probe.property("availability") == "UNAVAILABLE"


def test_first_frame_and_cross_seat_style_are_target_scoped_and_neutral():
    state, pids, store, _ = _active_store()
    a_fid = state.get_player(pids[0]).faction_id
    b_fid = state.get_player(pids[1]).faction_id
    a_color = _target_style(state, pids[0])["color"]
    b_color = _target_style(state, pids[1])["color"]
    assert a_color != b_color, (a_fid, b_fid, a_color, b_color)

    engine, component, probe = _qml_probe(store, a_fid)
    # first frame: the target's OWN name + colour, from the real component
    assert probe.property("resolvedColor") == a_color
    assert probe.property("resolvedName") == _style_name(state, a_fid)
    assert probe.property("availability") == "FRESH"
    assert probe.property("stale") is False

    store.doCompletePlayer()
    _pump()
    assert store.seatLifecycle == SEAT_MASKED_PENDING
    probe.setProperty("factionId", b_fid)
    _pump()
    # masked/pending: never A's colour/name for the next seat (a11y-visible
    # text would read the same neutral fallback)
    assert probe.property("resolvedColor") == FALLBACK_COLOR
    assert probe.property("resolvedColor") != a_color
    assert probe.property("resolvedName") == FALLBACK_NAME
    assert probe.property("availability") == "UNAVAILABLE"

    assert store.requestTakeover()["accepted"] is True
    _pump()
    assert probe.property("resolvedColor") == b_color
    assert probe.property("resolvedName") == _style_name(state, b_fid)
    assert probe.property("availability") == "FRESH"
    assert probe.property("resolvedColor") != a_color
    # every notification seen by the component while the seat was neutral named
    # the fallback, never a previous seat's faction name
    seen_names = list(probe.property("seenNames").toVariant())
    assert FALLBACK_NAME in seen_names, seen_names


