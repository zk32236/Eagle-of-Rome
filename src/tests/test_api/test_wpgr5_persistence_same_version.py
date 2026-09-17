# src/tests/test_api/test_wpgr5_persistence_same_version.py
"""WP-G-R5 DA-B5（DA-5 §5.4 持久化同版）——snapshot/context/decision + 会期身份同版往返。

断言方向（DATA）：
- Submit 成功后 to_dict → load_from_dict 往返保留 package 账本 / war snapshot / 会期身份；
- Vote→Results 后 decision 同版往返；
- 旧存档缺新键 → 空账本（不残留旧对象），不崩溃。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.core.game_state import GameState
from src.tests.fixtures.wpgr5_fixtures import build_r5_base, submit_request, command_draft, _base_config


class TestSameVersionPersistence(unittest.TestCase):

    def _roundtrip(self, state):
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(state.to_dict())
        return clone

    def test_package_ledger_and_session_roundtrip(self):
        fx = build_r5_base()
        state = fx["state"]
        res = senate_api.propose_many(state, fx["player_id"], submit_request(
            war_drafts=[command_draft("threat_war", fx["consul_id"], 0)]))
        self.assertTrue(res.get("success"), res)

        session_id = state.get_senate_session()
        self.assertTrue(session_id)

        clone = self._roundtrip(state)
        self.assertEqual(clone.get_senate_session(), session_id)
        registry = clone.get_senate_package_registry()
        self.assertEqual(len(registry["war_snapshots"]), len(state.get_senate_package_registry()["war_snapshots"]))
        self.assertTrue(len(registry["war_snapshots"]) >= 1)

    def test_war_decision_roundtrip(self):
        fx = build_r5_base()
        state = fx["state"]
        res = senate_api.propose_many(state, fx["player_id"], submit_request(
            war_drafts=[command_draft("threat_war", fx["consul_id"], 0)]))
        self.assertTrue(res.get("success"), res)
        proposals = state.get_senate_proposals()
        self.assertTrue(proposals)
        pid = proposals[0]["id"]
        vote = senate_api.vote(state, fx["player_id"], [pid], [True])
        self.assertTrue(vote.get("success"), vote)
        resolve = senate_api.resolve_senate(state)
        self.assertTrue(resolve.get("success"), resolve)

        decisions = state.get_war_decisions()
        self.assertTrue(decisions, "resolve must record war decisions")

        clone = self._roundtrip(state)
        self.assertEqual(set(clone.get_war_decisions().keys()), set(decisions.keys()))

    def test_legacy_save_without_new_keys_is_safe(self):
        fx = build_r5_base()
        state = fx["state"]
        legacy = state.to_dict()
        legacy.pop("_senate_package_ledger", None)
        legacy.pop("_war_execution_ledger", None)
        legacy.pop("_senate_session_id", None)
        clone = GameState.create_for_testing(_base_config())
        clone.load_from_dict(legacy)
        self.assertIsNone(clone.get_senate_session())
        self.assertEqual(clone.get_senate_package_registry()["war_snapshots"], {})
        self.assertEqual(clone.get_war_decisions(), {})


if __name__ == "__main__":
    unittest.main()
