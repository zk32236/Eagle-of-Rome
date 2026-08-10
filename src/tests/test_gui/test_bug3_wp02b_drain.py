"""
T-B3-04: WP-02b 同一 drain → 三派计票 (B3-AC04)
Design Amendment v1.1-final — TA-F2 Dual Strategy
Test-First — Run on OLD product baseline.

TA-F2 Dual Strategy (Amendment v1.1-final):
  Track 1 (deterministic): handcrafted state fixture for stable semantic tests
  Track 2 (production-path): ≥1 test uses create_gui_prototype_session() real path

Root Cause: UNVERIFIED / likely isolation or scenario-state dependency.
  Historical SKIP behavior (targeted PASS, full suite SKIP) cannot be reliably
  reproduced in isolation; root cause remains unconfirmed.

Source AC: B3-AC04 | Contract: B3-FC05, B3-FC08
Red Line: NO monkeypatch on AutoPlayerProcessor (TI-11).
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, population_api


class TestBug3Wp02bDrain:
    """T-B3-04 / TA-F2: WP-02b drain dual strategy."""

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_selection_map(candidates):
        """Build office→candidate_id map from available candidates (dynamic)."""
        sm = {}
        for office in ["consul", "censor", "praetor", "quaestor", "tribune"]:
            rows = candidates.get(office, [])
            if rows:
                sm[office] = rows[0]["id"]
        return sm

    def setup_population_session(self):
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"], f"Session creation failed: {result.get('message')}"
        state = result["data"]["state"]
        human_players = result["data"]["human_players"]
        viewer_id = human_players[0]
        state.set_current_player(viewer_id)
        return state, viewer_id

    # ── Production-path tests (Track 2) ──────────────────────────────────

    def test_wp02b_submit_triggers_drain_via_resolve_population_slice(self):
        """TA-F2 Track 2: WP-02b submit → AI drain via resolve_population_slice.
        
        使用真实 create_gui_prototype_session() production path。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = self._build_selection_map(candidates)
        assert len(selection_map) > 0, "Need at least one office with candidates"

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        ai_players = [p for p in state.get_all_players()
                      if p.player_type.value != "human"]
        for ai in ai_players:
            completed = state.get_vote_completed(ai.player_id)
            assert completed, (
                f"TA-F2: AI {ai.player_id} vote_completed=False after submit. "
                f"submit result: status={result.get('data', {}).get('status')}"
            )

    def test_wp02b_submit_produces_three_faction_votes(self):
        """TA-F2 Track 2: submit 后三派系均应有投票记录。
        
        使用真实 create_gui_prototype_session() production path。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = self._build_selection_map(candidates)
        assert len(selection_map) > 0, "Need at least one office with candidates"

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        all_players = state.get_all_players()
        all_votes = state.get_population_votes()
        voted_ids = set(v[0] for v in all_votes)
        for p in all_players:
            assert p.player_id in voted_ids, (
                f"TA-F2: player {p.player_id} (type={p.player_type.value}) "
                f"has no vote records. submit status={result.get('data', {}).get('status')}"
            )

    def test_wp02b_submit_resolves_population(self):
        """TA-F2 Track 2: submit 后 population 应已 resolve。
        
        使用真实 create_gui_prototype_session() production path。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = self._build_selection_map(candidates)
        assert len(selection_map) > 0, "Need at least one office with candidates"

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        resolved = state.is_phase_executed("population") or (
            state.get_phase_result("population") is not None
        )
        assert resolved, (
            f"TA-F2: population not resolved after submit. "
            f"status={result.get('data', {}).get('status')}"
        )

    def test_wp02b_election_results_present(self):
        """TA-F2 Track 2: submit 后 election_results 应存在。
        
        使用真实 create_gui_prototype_session() production path。
        """
        state, viewer_id = self.setup_population_session()

        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = self._build_selection_map(candidates)
        assert len(selection_map) > 0, "Need at least one office with candidates"

        result = session_api.submit_population_votes(state, viewer_id, selection_map)

        pop_result = state.get_phase_result("population")
        assert pop_result is not None, (
            f"TA-F2: population phase_result is None. "
            f"submit status={result.get('data', {}).get('status')}"
        )

        election_results = pop_result.get("data", {}).get("election_results", [])
        assert len(election_results) > 0, "TA-F2: no election results recorded"

    # ── Deterministic fixture test (Track 1) ─────────────────────────────

    def test_drain_direct_call_produces_ai_votes_deterministic(self):
        """TA-F2 Track 1: deterministic — direct _drain_ai_population_turns produces AI votes.
        
        使用真实 session setup 但直接调用 drain helper（绕过 submit route），
        验证 drain 本身产生 AI 投票记录。此测试不依赖 submit_population_votes 路径。
        """
        state, viewer_id = self.setup_population_session()

        # Complete HUMAN votes
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {})
        selection_map = self._build_selection_map(candidates)
        assert len(selection_map) > 0, "Need at least one office with candidates"
        for office, fid in selection_map.items():
            vresult = population_api.vote(state, viewer_id, office, fid)
            assert vresult.get("success"), f"HUMAN vote failed for {office}: {vresult}"

        # Direct drain call
        from src.api.session_api import _drain_ai_population_turns
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

        drain_result = _drain_ai_population_turns(state, auto)
        assert drain_result.get("success"), (
            f"TA-F2 Track 1: drain must succeed. Actual: {drain_result}"
        )

        # Verify AI votes exist
        ai_players = [p for p in state.get_all_players()
                      if p.player_type.value != "human"]
        all_votes = state.get_population_votes()
        voted_ids = set(v[0] for v in all_votes)
        for ai in ai_players:
            assert ai.player_id in voted_ids, (
                f"TA-F2 Track 1: AI {ai.player_id} has no votes after drain"
            )
            assert state.get_vote_completed(ai.player_id), (
                f"TA-F2 Track 1: AI {ai.player_id} not marked complete"
            )
