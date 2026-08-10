"""
T-B3-07: AI drain fail-closed / partial-state no-blind-retry (B3-AC09)
Test-First — run on OLD product baseline before first product write.

Expected on old product baseline:
  - once guard regression test: PASS (existing FC-09 behavior)
  - injected AI vote failure must expose missing retryable=False semantics: RED
  - second call after partial campaign write must expose blind replay: RED

Source AC: B3-AC09
Contract: B3-FC10
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from src.api import session_api, population_api
from src.ui.processors.auto_player_processor import AutoPlayerProcessor


class TestBug3FailClosed:
    """T-B3-07: 真正验证 FC10，而不是条件式 / vacuous PASS。"""

    def setup_session(self):
        result = session_api.create_gui_prototype_session(start_phase="population")
        assert result["success"]
        state = result["data"]["state"]
        viewer_id = result["data"]["human_players"][0]
        state.set_current_player(viewer_id)
        return state, viewer_id

    def complete_human_votes(self, state, viewer_id):
        cand_result = population_api.get_candidates(state)
        assert cand_result.get("success")
        candidates = cand_result.get("data", {})
        voted = 0
        for office, rows in candidates.items():
            if rows:
                result = population_api.vote(state, viewer_id, office, rows[0]["id"])
                assert result.get("success"), (
                    f"HUMAN vote setup failed for {office}: {result.get('message')}"
                )
                voted += 1
        assert voted > 0, "T-B3-07 setup requires at least one required office"

    @staticmethod
    def assert_retryable_false(result):
        """兼容 retryable 位于 data 或 structured errors 中的 api_response。"""
        candidates = []
        data = result.get("data")
        if isinstance(data, dict):
            candidates.append(data)
        errors = result.get("errors") or []
        if isinstance(errors, dict):
            candidates.append(errors)
        elif isinstance(errors, list):
            candidates.extend(e for e in errors if isinstance(e, dict))

        assert any(item.get("retryable") is False for item in candidates), (
            f"FC10 failure 必须显式 retryable=False，实际 result={result}"
        )

    def first_ai(self, state):
        ai_players = [
            p for p in state.get_all_players()
            if p.player_type.value != "human"
        ]
        assert ai_players, "scenario must contain AI players"
        return ai_players[0]

    def test_resolve_population_slice_once_guard_returns_existing(self):
        """FC-09 regression: resolved result exists → second resolve returns existing."""
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)

        first = session_api.resolve_population_slice(state)
        assert first.get("success"), f"首次 resolve 应成功: {first.get('message')}"

        second = session_api.resolve_population_slice(state)
        assert second.get("success"), "二次 resolve 应幂等成功"
        assert "already resolved" in second.get("message", "").lower(), (
            f"二次 resolve 应返回 already resolved: {second.get('message')}"
        )

    def test_injected_vote_failure_is_nonretryable_and_does_not_resolve(
        self, monkeypatch
    ):
        """festival 已产生 partial write、vote 抛异常 → fail-closed / non-retryable."""
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)
        ai = self.first_ai(state)

        # 让 recovery baseline 的旧 while drain 确实进入 AI；
        # 新 shared helper 不依赖 current_player，因此同样适用。
        state.set_current_player(ai.player_id)

        calls = {"festival": 0, "vote": 0}

        def fake_festival(_self, player_id, faction, bypass_permission=False):
            calls["festival"] += 1
            state.record_population_campaign(player_id, -9001, 1)
            return {"success": True}

        def failing_vote(_self, player_id, faction, bypass_permission=False):
            calls["vote"] += 1
            raise RuntimeError("T-B3-07 injected vote failure")

        monkeypatch.setattr(AutoPlayerProcessor, "process_festival", fake_festival)
        monkeypatch.setattr(AutoPlayerProcessor, "process_vote", failing_vote)

        result = session_api.resolve_population_slice(state)

        assert not result.get("success"), (
            f"注入 AI vote failure 后必须失败，实际 result={result}"
        )
        self.assert_retryable_false(result)
        assert state.get_phase_result("population") is None, (
            "AI drain failure 后不得 record population phase_result"
        )
        assert calls == {"festival": 1, "vote": 1}
        assert any(
            row[0] == ai.player_id for row in state.get_population_campaigns()
        ), "必须确认 partial campaign write 已真实发生"

    def test_partial_state_second_call_is_blocked_without_duplicate_write(
        self, monkeypatch
    ):
        """第一次留下 partial state 后，第二次 resolve 必须阻止盲重放。"""
        state, viewer_id = self.setup_session()
        self.complete_human_votes(state, viewer_id)
        ai = self.first_ai(state)
        state.set_current_player(ai.player_id)

        calls = {"festival": 0, "vote": 0}

        def fake_festival(_self, player_id, faction, bypass_permission=False):
            calls["festival"] += 1
            state.record_population_campaign(player_id, -9002, 1)
            return {"success": True}

        def failing_vote(_self, player_id, faction, bypass_permission=False):
            calls["vote"] += 1
            raise RuntimeError("T-B3-07 injected vote failure")

        monkeypatch.setattr(AutoPlayerProcessor, "process_festival", fake_festival)
        monkeypatch.setattr(AutoPlayerProcessor, "process_vote", failing_vote)

        first = session_api.resolve_population_slice(state)
        assert not first.get("success")
        self.assert_retryable_false(first)

        campaign_count_after_first = len([
            row for row in state.get_population_campaigns()
            if row[0] == ai.player_id
        ])
        assert campaign_count_after_first == 1
        assert calls == {"festival": 1, "vote": 1}

        second = session_api.resolve_population_slice(state)
        assert not second.get("success"), (
            "partial state 再进入必须 fail-closed，不得继续 resolution"
        )
        self.assert_retryable_false(second)
        assert "AI_DRAIN_PARTIAL_STATE" in str(second), (
            f"第二次调用必须明确分类 AI_DRAIN_PARTIAL_STATE，实际={second}"
        )

        campaign_count_after_second = len([
            row for row in state.get_population_campaigns()
            if row[0] == ai.player_id
        ])
        assert campaign_count_after_second == campaign_count_after_first, (
            "第二次调用不得新增 campaign partial write"
        )
        assert calls == {"festival": 1, "vote": 1}, (
            "partial-state preflight 必须在再次调用 festival/vote 前阻断"
        )
