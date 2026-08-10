"""
T-B3-07: AI drain fail-closed / partial-state no-blind-retry (B3-AC09)
Design Amendment v1.1-final — Test Amendment
Test-First — run on OLD product baseline before first product write.

Tests (7 scenarios, TI-11 compliant — all monkeypatches at population_api boundary):
  T-B3-07a: vote success=False → postcondition blocks (AI_DRAIN_POSTCONDITION_FAILED)
  T-B3-07b: campaign success=False → documentation test (D-AMEND-01: best-effort, non-blocking)
  T-B3-07c-1: get_candidates success=False → S1 guard blocks (AI_DRAIN_CANDIDATE_RETRIEVAL_FAILED)
  T-B3-07c-2: get_candidates raise RuntimeError → S1 guard blocks (AI_DRAIN_CANDIDATE_RETRIEVAL_ERROR)
  T-B3-07c-3: get_candidates empty data → S1 guard blocks (AI_DRAIN_NO_CANDIDATES)
  T-B3-07d: vote raises RuntimeError → postcondition blocks (AI_DRAIN_POSTCONDITION_FAILED)
  T-B3-07e: partial-state reentry → preflight blocks (AI_DRAIN_PARTIAL_STATE)

Source AC: B3-AC09
Contract: B3-FC10, D-AMEND-01
Red Line: NO monkeypatch on AutoPlayerProcessor (TI-11); all injections at population_api boundary.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import pytest
from src.api import session_api, population_api
from src.ui.processors.auto_player_processor import AutoPlayerProcessor
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
from src.core.deciders.impl.auto_vote_decider import AutoVoteDecider


class TestBug3FailClosed:
    """T-B3-07: AI drain fail-closed validation (Amendment v1.1-final)."""

    # ── helpers ──────────────────────────────────────────────────────────

    def setup_session(self):
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"], f"Session creation failed: {result.get('message')}"
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)
        return state, viewer_id

    def complete_human_votes(self, state, viewer_id):
        cand_result = population_api.get_candidates(state)
        assert cand_result.get("success"), f"Candidate retrieval failed: {cand_result}"
        candidates = cand_result.get("data", {})
        voted = 0
        for office, rows in candidates.items():
            if rows:
                vresult = population_api.vote(state, viewer_id, office, rows[0]["id"])
                assert vresult.get("success"), (
                    f"HUMAN vote setup failed for {office}: {vresult.get('message')}"
                )
                voted += 1
        assert voted > 0, "T-B3-07 setup requires at least one required office"

    @staticmethod
    def _has_retryable_false(result):
        """True if any candidate dict in result has retryable=False."""
        candidates = []
        data = result.get("data")
        if isinstance(data, dict):
            candidates.append(data)
        errors = result.get("errors") or []
        if isinstance(errors, dict):
            candidates.append(errors)
        elif isinstance(errors, list):
            candidates.extend(e for e in errors if isinstance(e, dict))
        return any(item.get("retryable") is False for item in candidates)

    def _make_auto_processor(self, state):
        """Create AutoPlayerProcessor for direct _drain_ai_population_turns calls."""
        return AutoPlayerProcessor(
            state,
            retirement_decider=AutoRetirementDecider(state),
            recruitment_decider=AutoRecruitmentDecider(),
            bid_decider=AutoBidDecider(),
            triumph_decider=AutoTriumphDecider(),
            festival_decider=AutoFestivalDecider(),
            vote_decider=AutoVoteDecider(),
        )

    # ── T-B3-07a ─────────────────────────────────────────────────────────

    def test_vote_success_false_postcondition_blocks(self, monkeypatch):
        """T-B3-07a: vote returns success=False → postcondition detects missing offices.
        
        Injection: population_api.vote() → {"success": False} for all calls.
        Expected: FAIL-CLOSED → AI_DRAIN_POSTCONDITION_FAILED / retryable=False.
        """
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        # Inject vote failure at population_api boundary (TI-11 compliant)
        def failing_vote(s, pid, office, fid, bypass_permission=False):
            return {"success": False, "message": "T-B3-07a injected vote failure",
                    "data": {}, "errors": [{"code": "INJECTED_VOTE_FAILURE"}]}

        monkeypatch.setattr(population_api, "vote", failing_vote)

        result = session_api.resolve_population_slice(state)

        assert not result.get("success"), (
            f"T-B3-07a: vote success=False must block completion. "
            f"Actual: success={result.get('success')}, message={result.get('message')}"
        )
        assert self._has_retryable_false(result), (
            f"T-B3-07a: must return retryable=False. Actual: {result}"
        )
        assert "AI_DRAIN_POSTCONDITION_FAILED" in str(result), (
            f"T-B3-07a: must classify as AI_DRAIN_POSTCONDITION_FAILED. Actual: {result}"
        )
        assert state.get_phase_result("population") is None, (
            "T-B3-07a: no phase_result on postcondition failure"
        )

    # ── T-B3-07b ─────────────────────────────────────────────────────────

    def test_campaign_failure_non_blocking_documentation(self, monkeypatch):
        """T-B3-07b: D-AMEND-01 — campaign failure = best-effort, non-blocking.
        
        Injection: population_api.campaign() → {"success": False} for all calls.
        Expected: vote completes normally, election resolves successfully.
        Festival/campaign is best-effort per Contract Amendment D-AMEND-01.
        """
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        def failing_campaign(s, pid, fid, amount, bypass_permission=False):
            return {"success": False, "message": "T-B3-07b injected campaign failure",
                    "data": {}, "errors": [{"code": "INJECTED_CAMPAIGN_FAILURE"}]}

        monkeypatch.setattr(population_api, "campaign", failing_campaign)

        result = session_api.resolve_population_slice(state)

        assert result.get("success"), (
            f"T-B3-07b / D-AMEND-01: campaign failure must NOT block completion. "
            f"Actual: success={result.get('success')}, message={result.get('message')}"
        )
        election_results = result.get("data", {}).get("election_results", [])
        assert election_results, (
            "T-B3-07b: election must still resolve when campaign fails (festival=best-effort)"
        )
        # Verify no partial campaign records (campaign failed without writing)
        # Not strictly required but confirms expected behavior

    # ── T-B3-07c-1 ───────────────────────────────────────────────────────

    def test_candidate_retrieval_success_false_blocks_drain(self, monkeypatch):
        """T-B3-07c-1: S1 guard — get_candidates success=False → fail-closed.
        
        Injection: population_api.get_candidates() → {"success": False}.
        Expected: S1 direct guard → AI_DRAIN_CANDIDATE_RETRIEVAL_FAILED / retryable=False.
        """
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        def failing_get_candidates(s):
            return {"success": False, "message": "T-B3-07c-1 injected failure",
                    "data": {}, "errors": [{"code": "INJECTED_CANDIDATE_FAILURE"}]}

        monkeypatch.setattr(population_api, "get_candidates", failing_get_candidates)

        from src.api.session_api import _drain_ai_population_turns
        auto = self._make_auto_processor(state)

        result = _drain_ai_population_turns(state, auto)

        assert not result.get("success"), (
            f"T-B3-07c-1: get_candidates success=False must fail-closed. "
            f"Actual: success={result.get('success')}"
        )
        assert self._has_retryable_false(result), (
            f"T-B3-07c-1: must return retryable=False. Actual: {result}"
        )
        assert "AI_DRAIN_CANDIDATE_RETRIEVAL_FAILED" in str(result), (
            f"T-B3-07c-1: must classify as AI_DRAIN_CANDIDATE_RETRIEVAL_FAILED. "
            f"Actual: {result}"
        )

    # ── T-B3-07c-2 ───────────────────────────────────────────────────────

    def test_candidate_retrieval_exception_structured_fail_closed(self, monkeypatch):
        """T-B3-07c-2: S1 guard try/except — get_candidates raises → structured failure.
        
        FIX-2 (P1-01) closure: get_candidates() raise RuntimeError
        → S1 direct guard try/except catches it
        → AI_DRAIN_CANDIDATE_RETRIEVAL_ERROR / retryable=False
        → no completion leak.
        """
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        def raising_get_candidates(s):
            raise RuntimeError("T-B3-07c-2 injected candidate retrieval exception")

        monkeypatch.setattr(population_api, "get_candidates", raising_get_candidates)

        from src.api.session_api import _drain_ai_population_turns
        auto = self._make_auto_processor(state)

        result = _drain_ai_population_turns(state, auto)

        assert not result.get("success"), (
            f"T-B3-07c-2: get_candidates exception must fail-closed. "
            f"Actual: success={result.get('success')}"
        )
        assert self._has_retryable_false(result), (
            f"T-B3-07c-2: must return retryable=False. Actual: {result}"
        )
        assert "AI_DRAIN_CANDIDATE_RETRIEVAL_ERROR" in str(result), (
            f"T-B3-07c-2: must classify as AI_DRAIN_CANDIDATE_RETRIEVAL_ERROR "
            f"(exception path, not success=False). Actual: {result}"
        )
        # No completion leak
        ai_players = [p for p in state.get_all_players()
                      if p.player_type.value != "human"]
        assert all(not state.get_vote_completed(p.player_id) for p in ai_players), (
            "T-B3-07c-2: exception in candidate retrieval must NOT set vote_completed"
        )

    # ── T-B3-07c-3 ───────────────────────────────────────────────────────

    def test_candidate_retrieval_empty_data_blocks_drain(self, monkeypatch):
        """T-B3-07c-3: S1 guard — get_candidates empty data → fail-closed.
        
        Injection: population_api.get_candidates() → success=True, empty data.
        Expected: S1 direct guard → AI_DRAIN_NO_CANDIDATES / retryable=False.
        No vacuous PASS (required_offices empty → completion must not succeed).
        """
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        def empty_get_candidates(s):
            return {"success": True, "message": "T-B3-07c-3 injected empty",
                    "data": {}}

        monkeypatch.setattr(population_api, "get_candidates", empty_get_candidates)

        from src.api.session_api import _drain_ai_population_turns
        auto = self._make_auto_processor(state)

        result = _drain_ai_population_turns(state, auto)

        assert not result.get("success"), (
            f"T-B3-07c-3: empty candidates must fail-closed (no vacuous PASS). "
            f"Actual: success={result.get('success')}"
        )
        assert self._has_retryable_false(result), (
            f"T-B3-07c-3: must return retryable=False. Actual: {result}"
        )
        assert "AI_DRAIN_NO_CANDIDATES" in str(result), (
            f"T-B3-07c-3: must classify as AI_DRAIN_NO_CANDIDATES. Actual: {result}"
        )

    # ── T-B3-07d ─────────────────────────────────────────────────────────

    def test_vote_exception_postcondition_blocks(self, monkeypatch):
        """T-B3-07d: vote raises → processor eats → postcondition detects missing votes.
        
        Injection: population_api.vote() → raise RuntimeError.
        Processor's try/except catches the exception, logs it, returns None.
        No vote records created → postcondition detects all missing → fail-closed.
        """
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        def raising_vote(s, pid, office, fid, bypass_permission=False):
            raise RuntimeError("T-B3-07d injected vote exception")

        monkeypatch.setattr(population_api, "vote", raising_vote)

        result = session_api.resolve_population_slice(state)

        assert not result.get("success"), (
            f"T-B3-07d: vote exception must fail-closed via postcondition. "
            f"Actual: success={result.get('success')}, message={result.get('message')}"
        )
        assert self._has_retryable_false(result), (
            f"T-B3-07d: must return retryable=False. Actual: {result}"
        )
        assert "AI_DRAIN_POSTCONDITION_FAILED" in str(result), (
            f"T-B3-07d: must classify as AI_DRAIN_POSTCONDITION_FAILED. Actual: {result}"
        )
        assert state.get_phase_result("population") is None, (
            "T-B3-07d: no phase_result on failure"
        )

    # ── T-B3-07e ─────────────────────────────────────────────────────────

    def test_partial_state_second_call_blocked_no_duplicate_write(self, monkeypatch):
        """T-B3-07e: partial-state reentry → preflight blocks (AI_DRAIN_PARTIAL_STATE).
        
        First call: inject campaign write + vote failure → partial state.
        Second call: preflight detects existing campaign/vote records → blocks.
        Verify no duplicate writes on second call.
        """
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        call_counter = {"campaign": 0, "vote": 0}

        def campaign_with_write(s, pid, fid, amount, bypass_permission=False):
            call_counter["campaign"] += 1
            # Write a campaign record to create partial state
            state.record_population_campaign(pid, -9999, 1)
            return {"success": True}

        def failing_vote(s, pid, office, fid, bypass_permission=False):
            call_counter["vote"] += 1
            raise RuntimeError("T-B3-07e injected vote failure")

        monkeypatch.setattr(population_api, "campaign", campaign_with_write)
        monkeypatch.setattr(population_api, "vote", failing_vote)

        first = session_api.resolve_population_slice(state)
        assert not first.get("success"), (
            f"T-B3-07e: first call must fail (vote exception). "
            f"Actual: success={first.get('success')}"
        )
        self._has_retryable_false(first)

        # Verify partial state exists
        ai_players = [p for p in state.get_all_players()
                      if p.player_type.value != "human"]
        campaign_count_first = len([
            row for row in state.get_population_campaigns()
            if row[0] in [p.player_id for p in ai_players]
        ])
        assert campaign_count_first > 0, "T-B3-07e: partial campaign must exist after first call"
        assert call_counter["campaign"] >= 1 and call_counter["vote"] >= 1

        # Snapshot call counters after first call (preflight-block verification baseline)
        campaign_calls_after_first = call_counter["campaign"]
        vote_calls_after_first = call_counter["vote"]

        second = session_api.resolve_population_slice(state)
        assert not second.get("success"), (
            "T-B3-07e: second call must fail-closed (partial state detected)"
        )
        assert self._has_retryable_false(second), (
            f"T-B3-07e: second call must return retryable=False. Actual: {second}"
        )
        assert "AI_DRAIN_PARTIAL_STATE" in str(second), (
            f"T-B3-07e: must classify as AI_DRAIN_PARTIAL_STATE. Actual: {second}"
        )

        # No additional writes on second call
        campaign_count_second = len([
            row for row in state.get_population_campaigns()
            if row[0] in [p.player_id for p in ai_players]
        ])
        assert campaign_count_second == campaign_count_first, (
            "T-B3-07e: no duplicate campaign writes on second call"
        )
        # preflight must block before any new campaign/vote calls.
        # NOTE: first call may invoke campaign multiple times (process_festival
        # loops over all candidates decided by the decider), so compare against
        # a snapshot taken after the first call, not a hard-coded 1.
        assert call_counter["campaign"] == campaign_calls_after_first, (
            "T-B3-07e: preflight must block before processor calls "
            f"(no new campaign after first; got {call_counter['campaign']} vs snapshot {campaign_calls_after_first})"
        )
        assert call_counter["vote"] == vote_calls_after_first, (
            "T-B3-07e: preflight must block before processor calls "
            f"(no new vote after first; got {call_counter['vote']} vs snapshot {vote_calls_after_first})"
        )
