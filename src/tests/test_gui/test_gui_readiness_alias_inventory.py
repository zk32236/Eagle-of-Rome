"""S-D-1 (R1) — GUI readiness semantic alias inventory (deterministic selectors).

EOR20261013-02 GUI Readiness · slice S-D · sub-task S-D-1 · rework round R1.

Frozen design basis (write face = Overlay §1.1 + §1.1.R):

  * ``G2-R5-Changed-Surface-UI-Contract.md`` §6 — ``gr*`` is a **runner semantic
    alias** ``{parent_surface, existing objectName OR unique assigned missing
    name, active_phase, role/substep, action_slot}``; selectors with an existing
    contractual ``objectName`` are **retained**; a unique missing name is added
    **only** where a mandatory matrix operation has no control; **shared**
    controls carry **multiple** semantic aliases (never seven changing
    objectNames).
  * ``G2-Seven-Phase-GUI-Action-Matrix.md`` — the seven-phase mandatory
    operation rows + the cross-cutting controls.

R1 (SD1-V02/V03/V04) — this file no longer proves *string declarations*. It now
asserts a **complete deterministic selector** for every matrix / cross-cutting
entry:

  * the contractual ``control_id`` is declared as a **static objectName literal**
    exactly once in its surface (instance multiplicity is handled by the
    Repeater model, so the *alias* additionally carries the **instance key**);
  * repeated controls declare their **instance key** (``modelData.id`` /
    ``modelData.war_id`` / ``_warData.war_id``) and their **model source**;
  * every actionable alias carries an **actionable gesture** anchor and the
    **exact Store slot dispatch** string, and the dispatched Store slot is proven
    to exist in ``session_store.py`` (``def <slot>(``);
  * dialog-based operations carry the **opening gesture** + the **confirm
    gesture** (the truly actionable subcontrol), not just the container;
  * the **Query** cross-cutting surface is covered (all 12 production controls);
  * ``grCombatSelectWar`` is reconciled to the accepted **attack-only** production
    workflow (FUNC-03) — it is superseded, and attack is **never** labelled
    ``doSelectWar`` (SD1-V03);
  * the population finish / resolve aliases are reconciled to the **single
    authoritative vote-submit dispatch** (completion/resolution are downstream of
    it, NOT independently selectable actions) and the resolution result panel is
    an **observer** with no dispatch (SD1-V04).

This remains a **static source scan** (no Qt runtime).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Product roots (derived from this file; never hard-coded to a machine)
#   .../Eagle of Rome/src/tests/test_gui/<this file>  ->  parents[3] = repo root
# ---------------------------------------------------------------------------
QML_ROOT = Path(__file__).resolve().parents[3] / "src" / "ui" / "gui" / "qml"
STORE_PY = QML_ROOT.parent / "session_store.py"      # .../src/ui/gui/session_store.py
STORE_TEXT = STORE_PY.read_text(encoding="utf-8")


# ===========================================================================
# The ONE authoritative semantic-alias inventory (machine-readable form).
#
# Each row is a complete deterministic selector:
#   alias          contractual semantic alias
#   surface        QML surface (relative to QML_ROOT)
#   control        existing contractual objectName of the actionable control
#   reach          "singleton" | "repeater"
#   key            Repeater instance key expression (repeater rows only)
#   model          Repeater model source (repeater rows only)
#   opener         opening gesture function (dialog rows only)
#   dialog         dialog container objectName (dialog rows only)
#   gesture        the actionable subcontrol/gesture anchor
#   dispatch       the EXACT Store slot call string reached by the gesture
#   phase          active phase
#   role           role / substep
#   slot           action_slot
# ===========================================================================
def _r(alias, surface, control, phase, role, slot, *, reach="singleton",
       key="", model="", opener="", dialog="", gesture="onClicked",
       dispatch="sessionStore.doAdvanceCurrentPhase()"):
    return {
        "alias": alias, "surface": surface, "control": control, "reach": reach,
        "key": key, "model": model, "opener": opener, "dialog": dialog,
        "gesture": gesture, "dispatch": dispatch, "phase": phase, "role": role,
        "slot": slot,
    }


ALIAS_INVENTORY = [
    # ---- cross-cutting: handoff overlay (PlayerHandoffOverlay.qml) ----
    _r("grHandoffStart", "shell/PlayerHandoffOverlay.qml", "grHandoffStart",
       "handoff", "activation", "start",
       dispatch="sessionStore.requestTakeover()"),
    _r("grHandoffRetry", "shell/PlayerHandoffOverlay.qml", "grHandoffRetry",
       "handoff", "activation-retry", "retry",
       dispatch="sessionStore.retryHandoff()"),
    _r("grHandoffExit", "shell/PlayerHandoffOverlay.qml", "grHandoffExit",
       "handoff", "safe-exit", "exit",
       dispatch="sessionStore.requestHandoffExit()"),
    _r("grContinuationRecover", "shell/PlayerHandoffOverlay.qml",
       "grContinuationRecover", "handoff", "continuation-recover", "recover",
       gesture="Keys.onReturnPressed",
       dispatch="sessionStore.doRecoverContinuation()"),

    # ---- shared common advance (ContextPanel.operationSection.advancePhaseButton) ----
    _r("grMortalityAdvance", "shell/ContextPanel.qml", "advancePhaseButton",
       "mortality", "confirm", "advance"),
    _r("grRevenueAdvance", "shell/ContextPanel.qml", "advancePhaseButton",
       "revenue", "confirm", "advance"),
    _r("grForumAdvance", "shell/ContextPanel.qml", "advancePhaseButton",
       "forum", "advance", "advance"),
    _r("grPopulationAdvance", "shell/ContextPanel.qml", "advancePhaseButton",
       "population", "advance", "advance"),
    _r("grSenateAdvance", "shell/ContextPanel.qml", "advancePhaseButton",
       "senate", "finalization-advance", "advance"),
    _r("grCombatAdvance", "shell/ContextPanel.qml", "advancePhaseButton",
       "combat", "advance", "advance"),
    _r("grResolutionAdvance", "shell/ContextPanel.qml", "advancePhaseButton",
       "resolution", "year-advance", "advance"),

    # ---- mortality / revenue execute (GameShell action slots) ----
    _r("grMortalityExecute", "shell/GameShell.qml", "mortalityPrimaryActionButton",
       "mortality", "execute", "execute",
       dispatch="sessionStore.doExecuteMortality()"),
    _r("grRevenueSettle", "shell/GameShell.qml", "revenuePrimaryActionButton",
       "revenue", "settle", "settle",
       dispatch="sessionStore.doExecuteRevenue()"),

    # ---- population (single combined vote-submit control; SD1-V04) ----
    _r("grPopulationCampaign", "stages/PopulationStage.qml",
       "populationCampaignSubmitButton", "population", "campaign", "campaign",
       dispatch="sessionStore.doBatchCampaign("),
    _r("grPopulationSubmitVotes", "stages/PopulationStage.qml",
       "populationResolveButton", "population", "vote", "submit-votes",
       dispatch="sessionStore.submitPopulationVotes("),
    # finish/resolve are DOWNSTREAM of the single authoritative submit dispatch
    # (the click always calls submitPopulationVotes; completion + automatic
    # resolution ride on that one command — never a separate doCompletePlayer /
    # doResolveElection control).
    _r("grPopulationFinish", "stages/PopulationStage.qml",
       "populationResolveButton", "population", "finish",
       "complete-player(downstream-of-submit)",
       dispatch="sessionStore.submitPopulationVotes("),
    _r("grPopulationResolve", "stages/PopulationStage.qml",
       "populationResolveButton", "population", "resolve",
       "resolve-election(downstream-of-submit)",
       dispatch="sessionStore.submitPopulationVotes("),

    # ---- senate ----
    _r("grSenateSubmitProposals", "stages/SenateStage.qml",
       "senateProposalSubmitButton", "senate", "proposal", "submit-proposals",
       dispatch="sessionStore.doSubmitSenateProposals("),
    _r("grSenateSubmitVotes", "stages/SenateStage.qml",
       "senateVoteSubmitButton", "senate", "vote", "submit-votes",
       dispatch="sessionStore.doSubmitSenateVotes("),
    _r("grSenateSubmitVetoes", "stages/SenateStage.qml",
       "senateVetoSubmitButton", "senate", "veto", "submit-vetoes",
       dispatch="sessionStore.doSubmitSenateVetoes("),

    # ---- forum (retire / finish-retirement are singletons; repeater rows carry
    #      the model key; dialog ops carry opener + confirm gesture) ----
    _r("grForumRetire", "stages/ForumStage.qml", "forumRetireButton",
       "forum", "retire", "retire-figure",
       reach="repeater", key="modelData.id", model="forumMyFigures",
       dispatch="sessionStore.doRetireFigure("),
    _r("grForumFinishRetirement", "stages/ForumStage.qml",
       "forumFinishRetirementButton", "forum", "retirement-finish",
       "complete-forum-step",
       dispatch="sessionStore.doCompleteForumStep("),
    _r("grForumRecruit", "stages/ForumStage.qml", "forumRecruitButton",
       "forum", "market-recruit", "recruit-figure",
       reach="repeater", key="modelData.id", model="forumAvailableFigures",
       opener="openRecruitDialog", dialog="recruitDialog",
       gesture="confirmRecruitDialog",
       dispatch="sessionStore.doRecruitFigure("),
    _r("grForumBid", "stages/ForumStage.qml", "forumContractBidRow",
       "forum", "market-bid", "place-bid",
       reach="repeater", key="modelData.id", model="forumPendingContracts",
       opener="openBidDialog", dialog="bidDialog",
       gesture="confirmBidDialog",
       dispatch="sessionStore.doPlaceBid("),
    _r("grForumFleetBid", "stages/ForumStage.qml", "forumContractBidRow",
       "forum", "market-fleet-bid", "place-fleet-bid",
       reach="repeater", key="modelData.id", model="forumPendingContracts",
       opener="openBidDialog", dialog="bidDialog",
       gesture="confirmBidDialog",
       dispatch="sessionStore.doPlaceFleetBid("),
    _r("grForumBuyLand", "stages/ForumStage.qml", "publicLandPurchaseRow",
       "forum", "market-land", "buy-land",
       opener="openLandDialog", dialog="landDialog",
       gesture="confirmLandDialog",
       dispatch="sessionStore.doBuyLand("),
    _r("grForumTriumphVote", "stages/ForumStage.qml", "forumTriumphVoteRow",
       "forum", "market-triumph", "vote-triumph",
       reach="repeater", key="modelData.war_id", model="forumTriumphWars",
       gesture="onTriggered",
       dispatch="sessionStore.doVoteTriumph("),
    _r("grForumFinishMarket", "stages/ForumStage.qml", "forumMarketSubmitButton",
       "forum", "market-finish", "complete-market",
       dispatch="sessionStore.doResolveForum("),
    _r("grForumResolve", "stages/ForumStage.qml", "forumMarketSubmitButton",
       "forum", "resolve", "resolve-forum",
       dispatch="sessionStore.doResolveForum("),

    # ---- combat (attack-only production workflow; SD1-V03) ----
    _r("grCombatAttack", "stages/CombatStage.qml", "warCard",
       "combat", "attack", "attack",
       reach="repeater", key="_warData.war_id", model="combatAllWarCards",
       gesture="onAttackRequested",
       dispatch="sessionStore.doCombatAction("),
    _r("grCombatConfirmResult", "stages/CombatStage.qml",
       "combatConfirmResultButton", "combat", "result", "confirm-result",
       gesture="onTriggered",
       dispatch="sessionStore.doConfirmBattleResult()"),
]

# ---------------------------------------------------------------------------
# SD1-V03 — combat select disposition (PM ruling §9.3, branch 1).
# The accepted production workflow is **attack-only** (Store ``doCombatAction``
# hard-rejects non-attack; the combat card sets ``selectable: false`` and the
# single card gesture dispatches ``attack``; FUNC-03 "single attack entry").
# Therefore selection is SUBSUMED by the attack-only gesture: ``grCombatSelectWar``
# is a SUPERSEDED alias with no distinct actionable production control. It is
# **never** bound to ``doSelectWar`` (attack must NOT be labelled doSelectWar).
# ---------------------------------------------------------------------------
SUPERSEDED_ALIASES = {
    "grCombatSelectWar": (
        "attack-only production workflow subsumes selection (FUNC-03); the sole "
        "card gesture dispatches sessionStore.doCombatAction(...,'attack'). No "
        "distinct selectable control exists (CombatStage warCard selectable:false)."
    ),
}

# ---------------------------------------------------------------------------
# SD1-V04 — resolution result alias is an OBSERVER (no actionable dispatch); the
# settlement itself is the Store's automatic internal execution.
# ---------------------------------------------------------------------------
OBSERVER_ALIASES = {
    "grResolutionResult": {
        "surface": "stages/ResolutionStage.qml",
        "control": "resolutionResultsPanel",
        "internal": "_executeResolution",
        "phase": "resolution", "role": "settle", "slot": "observe(auto-executed)",
    },
}

#: Combat automatic resolution is an internal production path (matrix explicitly
#: forbids a new HUMAN shortcut) — no clickable alias control is required.
AUTO_CONTROLS = {
    "combat_auto_resolution": "existing automatic Store chain -> auto_resolve_combat",
}

#: Bounded/conditional aliases are named explicitly and are NEVER silently bound
#: to a control that may not exist. SD1-V04: ``grResolutionRetrySettlement`` is a
#: G2-R5 §6 cross-cutting conditional whose bounded missing-control addition +
#: failure path are supplied by the S-D-2 real chain; PM disposition = keep it
#: explicitly DEFERRED (not inferred, not fabricated).
DEFERRED_ALIASES = {
    "grResolutionRetrySettlement":
        "resolution-entry-only bounded retry (S-D-2 real chain; not inferred)",
}

# ---------------------------------------------------------------------------
# Query cross-cutting surface — all 12 production controls (SD1-V04).
# ---------------------------------------------------------------------------
QUERY_IDS = (
    "faction_info", "figure_search", "game_status", "faction_treasury",
    "public_land", "private_land", "contract_status", "province_info",
    "war_list", "legion_status", "fleet_status", "help",
)
QUERY_SURFACE = "shell/BottomQueryBar.qml"

_OBJECTNAME_RE = re.compile(r'objectName\s*:\s*"([^"]*)"')
_DISPATCH_RE = re.compile(r"sessionStore\.([A-Za-z_][A-Za-z0-9_]*)")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _read(rel: str) -> str:
    path = QML_ROOT / rel
    assert path.is_file(), f"missing QML surface: {path}"
    return path.read_text(encoding="utf-8")


def _declared_objectnames(rel: str):
    """All statically-declared objectName string literals in a QML file."""
    return _OBJECTNAME_RE.findall(_read(rel))


def _slot_of(dispatch: str) -> str:
    m = _DISPATCH_RE.search(dispatch or "")
    return m.group(1) if m else ""


def _row_defects(row: dict) -> list:
    """Return the deterministic-selector defects for one inventory row.

    A row is valid iff: the contractual control is a static objectName literal
    declared exactly once; the actionable gesture anchor is present; the exact
    Store dispatch string is present AND the dispatched Store slot exists in
    ``session_store.py``; a repeater row declares an instance key + model source
    present in the surface; a dialog row declares its container + confirm gesture.
    """
    defects = []
    text = _read(row["surface"])
    declared = _declared_objectnames(row["surface"])

    if declared.count(row["control"]) != 1:
        defects.append(
            f"control {row['control']!r} declared "
            f"{declared.count(row['control'])}x (expected exactly 1)")
    if f'objectName: "{row["control"]}"' not in text:
        defects.append(f"{row['control']!r} is not a static objectName literal")

    if row["gesture"] and row["gesture"] not in text:
        defects.append(f"gesture {row['gesture']!r} absent from {row['surface']}")

    dispatch = row["dispatch"]
    if not dispatch:
        defects.append("no dispatch bound")
    else:
        if dispatch not in text:
            defects.append(f"dispatch {dispatch!r} absent from {row['surface']}")
        slot = _slot_of(dispatch)
        if not slot:
            defects.append(f"cannot derive Store slot from {dispatch!r}")
        elif f"def {slot}(" not in STORE_TEXT:
            defects.append(f"Store slot {slot!r} not defined in session_store.py")

    if row["reach"] == "repeater":
        if not row["key"]:
            defects.append("repeater row omits its instance key")
        elif row["key"] not in text:
            defects.append(
                f"instance key {row['key']!r} absent from {row['surface']}")
        if not row["model"]:
            defects.append("repeater row omits its model source")
        elif row["model"] not in text:
            defects.append(
                f"model source {row['model']!r} absent from {row['surface']}")

    if row["dialog"]:
        if declared.count(row["dialog"]) != 1:
            defects.append(
                f"dialog {row['dialog']!r} not declared exactly once")
        if not row["opener"]:
            defects.append("dialog row omits its opening gesture")
        elif row["opener"] not in text:
            defects.append(
                f"opening gesture {row['opener']!r} absent from {row['surface']}")

    return defects


def _resolve(alias: str):
    return [row for row in ALIAS_INVENTORY if row["alias"] == alias]


# ===========================================================================
# 1. Inventory integrity — each alias resolves to exactly ONE real unique control
# ===========================================================================
def test_inventory_aliases_are_unique():
    aliases = [row["alias"] for row in ALIAS_INVENTORY]
    assert len(aliases) == len(set(aliases)), "duplicate alias in inventory"


def test_every_alias_resolves_to_exactly_one_real_unique_control():
    failures = []
    for row in ALIAS_INVENTORY:
        declared = _declared_objectnames(row["surface"])
        n = declared.count(row["control"])
        if n != 1:
            failures.append(
                f"{row['alias']}: control {row['control']!r} declared {n}x in "
                f"{row['surface']} (expected exactly 1)")
    assert not failures, "alias->control resolution failed:\n" + "\n".join(failures)


def test_no_alias_without_control_sd_n1():
    """SD-N1: an alias whose control is absent is a FAIL (never silently bound)."""
    declared = {}
    for surface in {row["surface"] for row in ALIAS_INVENTORY}:
        declared.setdefault(surface, set()).update(_declared_objectnames(surface))
    missing = [(row["alias"], row["surface"], row["control"])
               for row in ALIAS_INVENTORY
               if row["control"] not in declared.get(row["surface"], set())]
    assert not missing, f"aliases without a control (SD-N1 FAIL): {missing}"


def test_control_ids_are_unique_across_surfaces():
    """No control_id may be owned by two different surfaces (ambiguous alias)."""
    seen = {}
    problems = []
    for row in ALIAS_INVENTORY:
        owner = seen.setdefault(row["control"], row["surface"])
        if owner != row["surface"]:
            problems.append(f"{row['control']!r} in {owner} and {row['surface']}")
    assert not problems, f"control_id not unique across surfaces: {problems}"


def test_shared_advance_control_carries_multiple_aliases():
    """The sole ContextPanel advance control carries multiple semantic aliases
    (never seven dynamic objectNames)."""
    adv = [row["alias"] for row in ALIAS_INVENTORY
           if row["control"] == "advancePhaseButton"]
    assert len(adv) == 7, f"expected 7 advance aliases, got {adv}"
    assert _declared_objectnames("shell/ContextPanel.qml").count(
        "advancePhaseButton") == 1


def test_no_dynamic_objectname_for_aliased_controls():
    """No aliased control may be declared with a dynamic (binding) objectName."""
    for row in ALIAS_INVENTORY:
        text = _read(row["surface"])
        control = re.escape(row["control"])
        assert f'objectName: "{row["control"]}"' in text, (
            f"{row['control']} not declared as a static literal in {row['surface']}")
        assert not re.search(
            rf'objectName\s*:\s*[^\n"]*"[^"]*"\s*\+[^\n]*{control}',
            text), f"{row['control']} appears in a dynamic objectName expression"


# ===========================================================================
# 2. Deterministic selectors — every row resolves to a real actionable control
# ===========================================================================
def test_every_alias_row_is_a_complete_deterministic_selector():
    failures = {}
    for row in ALIAS_INVENTORY:
        defects = _row_defects(row)
        if defects:
            failures[row["alias"]] = defects
    assert not failures, "incomplete selectors:\n" + "\n".join(
        f"{a}: {d}" for a, d in failures.items())


def test_repeater_rows_declare_instance_key_and_model():
    repeaters = [row for row in ALIAS_INVENTORY if row["reach"] == "repeater"]
    assert repeaters, "expected at least one repeater alias"
    for row in repeaters:
        assert row["key"], f"{row['alias']} must declare an instance key"
        assert row["model"], f"{row['alias']} must declare a model source"


def test_dialog_rows_bind_the_confirm_gesture_not_the_container():
    dialogs = [row for row in ALIAS_INVENTORY if row["dialog"]]
    assert dialogs, "expected at least one dialog alias"
    for row in dialogs:
        assert row["opener"], f"{row['alias']} must declare its opening gesture"
        assert row["gesture"] not in ("onClicked", "onTriggered"), (
            f"{row['alias']} must bind the confirm gesture, not the container")


# ===========================================================================
# 3. Query cross-cutting surface — all 12 production controls (SD1-V04)
# ===========================================================================
def test_query_surface_covers_all_twelve_controls():
    text = _read(QUERY_SURFACE)
    for qid in QUERY_IDS:
        assert f'"id": "{qid}"' in text, f"query model missing id {qid!r}"
    found = re.findall(r'"id":\s*"([^"]+)"', text)
    assert sorted(found) == sorted(QUERY_IDS), f"query id set mismatch: {found}"
    assert len(set(QUERY_IDS)) == 12
    # The per-query selector is an existing per-QUERY name (NOT a per-phase rewrite).
    assert 'objectName: "queryButton_" + modelData.id' in text
    assert "onClicked: root.queryRequested(modelData.id)" in text


def test_query_route_reaches_the_store_slot():
    shell = _read("shell/GameShell.qml")
    assert "onQueryRequested" in shell
    assert "handleQueryRequest" in shell
    assert "sessionStore.doGlobalQuery(" in shell
    assert "def doGlobalQuery(" in STORE_TEXT


# ===========================================================================
# 4. Observer / superseded / deferred registries
# ===========================================================================
def test_resolution_result_is_observer_only_readonly_panel():
    """SD1-V04: ``grResolutionResult`` is a read-only result OBSERVER. The panel
    must not dispatch any command; the settlement is the Store's automatic
    internal execution."""
    spec = OBSERVER_ALIASES["grResolutionResult"]
    text = _read(spec["surface"])
    assert _declared_objectnames(spec["surface"]).count(spec["control"]) == 1
    # read-only: no pointer gesture, no mutating Store dispatch anywhere here.
    assert "MouseArea" not in text, f"{spec['surface']} must not carry a gesture"
    assert "sessionStore.do" not in text
    # the automatic internal execution exists in the Store.
    assert f"def {spec['internal']}(" in STORE_TEXT


def test_combat_select_is_superseded_not_bound_to_doSelectWar():
    """SD1-V03: attack-only subsumes selection. The superseded alias must not be
    in the actionable inventory, must not be a live static objectName anywhere,
    and the combat card must dispatch attack (never doSelectWar)."""
    for alias in SUPERSEDED_ALIASES:
        assert _resolve(alias) == [], f"{alias} must not claim an actionable control"
        for surface in {row["surface"] for row in ALIAS_INVENTORY}:
            assert alias not in _declared_objectnames(surface)
    text = _read("stages/CombatStage.qml")
    # the production card is attack-only (selection disabled).
    assert "selectable: false" in text
    assert "parent.attackRequested(parent.warData.war_id)" in text
    assert "sessionStore.doCombatAction(" in text
    # attack is NEVER labelled as select; the select slot exists but is unbound.
    assert "sessionStore.doSelectWar(" not in [
        row["dispatch"] for row in ALIAS_INVENTORY]
    assert "def doSelectWar(" in STORE_TEXT


def test_attack_alias_never_mislabelled_as_select():
    attack = _resolve("grCombatAttack")
    assert len(attack) == 1
    assert attack[0]["slot"] == "attack"
    assert "doSelectWar" not in attack[0]["dispatch"]
    assert "doCombatAction" in attack[0]["dispatch"]


def test_deferred_aliases_are_explicitly_registered_not_inferred():
    """Bounded/conditional aliases are named explicitly and never silently bound."""
    for alias in DEFERRED_ALIASES:
        assert _resolve(alias) == [], f"{alias} must not claim a current control"
        for surface in {row["surface"] for row in ALIAS_INVENTORY}:
            assert alias not in _declared_objectnames(surface)


def test_population_finish_resolve_reconciled_to_submit_dispatch():
    """SD1-V04: finish/resolve are downstream of the single authoritative submit;
    the click must NOT dispatch doCompletePlayer / doResolveElection."""
    for alias in ("grPopulationFinish", "grPopulationResolve",
                  "grPopulationSubmitVotes"):
        rows = _resolve(alias)
        assert len(rows) == 1
        assert rows[0]["control"] == "populationResolveButton"
        assert rows[0]["dispatch"] == "sessionStore.submitPopulationVotes("
    text = _read("stages/PopulationStage.qml")
    assert "sessionStore.submitPopulationVotes(" in text
    assert "sessionStore.doCompletePlayer(" not in text
    assert "sessionStore.doResolveElection(" not in text


# ===========================================================================
# 5. §1.1.R bounded continuation recovery control invariants (static, preserved)
# ===========================================================================
OVERLAY = "shell/PlayerHandoffOverlay.qml"


def test_recover_control_present_and_unique():
    assert _declared_objectnames(OVERLAY).count("grContinuationRecover") == 1


def test_explicit_key_activation_no_appbutton_default_assumption():
    """SD-R02.1: Enter/Space activation is wired EXPLICITLY on the recover
    control; the shared AppButton component has no default Keys handler."""
    text = _read(OVERLAY)
    for key in ("Keys.onReturnPressed", "Keys.onEnterPressed", "Keys.onSpacePressed"):
        assert key in text, f"missing explicit {key} on the recover control"
    assert "_activateRecovery" in text
    appbutton = (QML_ROOT / "components/AppButton.qml").read_text(encoding="utf-8")
    assert "Keys." not in appbutton, "AppButton gained a default key handler"


def test_auto_repeat_rejected_and_single_dispatch():
    text = _read(OVERLAY)
    assert "isAutoRepeat" in text, "auto-repeat is not rejected"
    assert "onClicked: root._activateRecovery()" in text


def test_mutual_exclusion_single_exclusive_route():
    """SD-R02.2: a SINGLE exclusive failureRoute drives both visibility booleans
    so the two failure actions can never co-appear."""
    text = _read(OVERLAY)
    assert 'failureRoute === "activation"' in text
    assert 'failureRoute === "continuation"' in text
    assert "visible: root.activationRetryEligible" in text
    assert "visible: root.continuationRecoverEligible" in text
    retry_block = text.split("id: retryButton", 1)[1].split(
        "sessionStore.retryHandoff()", 1)[0]
    assert "visible: root.activationRetryEligible" in retry_block
    assert "visible: root.maskedMode && root.failureVisible" not in retry_block


def test_busy_disables_both_failure_actions():
    text = _read(OVERLAY)
    assert text.count("enabled: !root.busy") >= 2, (
        "both grHandoffRetry and grContinuationRecover need explicit busy-enable")
    assert "!root.busy" in text


def test_recover_control_in_focus_enumeration():
    text = _read(OVERLAY)
    assert "recoverButton.visible && recoverButton.enabled" in text


# ===========================================================================
# 6. Negative controls — the deterministic selectors reject the OLD/shape-only
#    forms (this is the RED witness for SD1-V02/V03/V04).
# ===========================================================================
def test_negative_declaration_only_row_is_rejected():
    """A declaration-only row (no instance key / no dispatch) — the OLD tuple
    shape — must be flagged by the deterministic selector validator."""
    bad = _r("grForumRetire", "stages/ForumStage.qml", "forumRetireButton",
             "forum", "retire", "retire-figure", reach="repeater",
             dispatch="sessionStore.doRetireFigure(")  # key/model omitted
    defects = _row_defects(bad)
    assert any("instance key" in d for d in defects)
    assert any("model source" in d for d in defects)


def test_negative_dispatch_not_present_is_rejected():
    bad = _r("grForumRetire", "stages/ForumStage.qml", "forumRetireButton",
             "forum", "retire", "retire-figure", reach="repeater",
             key="modelData.id", model="forumMyFigures",
             dispatch="sessionStore.doRetireFigureNOPE(")
    defects = _row_defects(bad)
    assert any("doRetireFigureNOPE" in d for d in defects)


def test_negative_unknown_store_slot_is_rejected():
    bad = _r("grForumRetire", "stages/ForumStage.qml", "forumRetireButton",
             "forum", "retire", "retire-figure",
             dispatch="sessionStore.__no_such_slot__(")
    defects = _row_defects(bad)
    assert any("__no_such_slot__" in d and "not defined" in d for d in defects)


def test_negative_dynamic_objectname_is_rejected():
    """A dynamically-built objectName is NOT a static contractual literal; the
    query bar intentionally builds its per-query name, and the static-literal
    requirement must reject that form for an aliased control."""
    text = _read(QUERY_SURFACE)
    assert 'objectName: "queryButton_faction_info"' not in text
    assert 'objectName: "queryButton_" + modelData.id' in text


def test_negative_alias_without_control():
    assert _resolve("grDoesNotExist") == []
    declared = {row["control"] for row in ALIAS_INVENTORY}
    assert "grDoesNotExist" not in declared


def test_negative_superseded_alias_not_in_actionable_inventory():
    assert _resolve("grCombatSelectWar") == []
    assert "grCombatSelectWar" in SUPERSEDED_ALIASES


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
