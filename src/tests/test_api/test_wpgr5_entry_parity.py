# src/tests/test_api/test_wpgr5_entry_parity.py
"""WP-G-R5 DA-B3（DA-4 入口 parity 退役）—— C-M01~C-M10 无残留 + Human/AI/CLI 同源。

证据分类 = DATA / 静态扫描（RENDER 归 SO）。断言方向：
- 旧入口（takeover / continue / required / builder / AI direct）在 API/Core/Store/Adapter/CLI 面退役；
- DTO 不再暴露旧 Takeover/Continue 读模型键；
- AI 入口 = 一次整包（submit_proposal_package），不循环 propose（D-SC03）；
- QML 卡区不再使用旧绑定（E-01 :954 即时触发点退役），统一 War Card（D-SC02/D-SC15）。
"""
import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.core.systems.political_system import PoliticalSystem
from src.tests.fixtures.wpgr5_fixtures import build_r5_base, submit_request, command_draft


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestRetiredEntriesAbsent(unittest.TestCase):
    """C-M06/C-M07/C-M08/C-M09/C-M10：旧入口在 API/Core 面退役（无残留 entry point）。"""

    def test_senate_api_legacy_entries_removed(self):
        for name in ("takeover_war", "continue_war", "_resolve_takeover_required",
                     "_build_takeover_options", "_build_continue_options",
                     "_takeover_reserved_offset", "_deploy_pending_takeover",
                     "_snapshot_takeover_deploy", "_rollback_takeover_deploy",
                     "_takeover_pending_dto", "_war_has_valid_commander",
                     "process_war_takeover"):
            self.assertFalse(hasattr(senate_api, name), f"legacy entry still present: {name}")

    def test_political_system_ai_takeover_chain_removed(self):
        for name in ("plan_ai_takeovers", "execute_ai_takeover_direct_action",
                     "_ai_takeover_candidate_wars"):
            self.assertFalse(hasattr(PoliticalSystem, name), f"legacy AI chain present: {name}")

    def test_api_adapter_takeover_bindings_removed(self):
        from src.ui.gui.api_adapter import GuiApiAdapter
        self.assertFalse(hasattr(GuiApiAdapter, "takeover_war"))
        self.assertFalse(hasattr(GuiApiAdapter, "continue_war"))
        self.assertTrue(hasattr(GuiApiAdapter, "submit_senate_proposals"))
        self.assertTrue(hasattr(GuiApiAdapter, "advance_senate"))

    def test_session_store_takeover_readmodels_removed(self):
        from src.ui.gui.session_store import GuiSessionStore
        for name in ("canTakeoverSenateWar", "senateTakeoverOptions", "canContinueSenateWar",
                     "senatePendingTakeover", "senatePendingTakeoverLocked",
                     "senateCanDeployTakeover", "senateTakeoverRequired",
                     "senateContinueOptions", "doTakeoverWar", "doContinueWar"):
            self.assertFalse(hasattr(GuiSessionStore, name), f"legacy store member present: {name}")
        self.assertTrue(hasattr(GuiSessionStore, "senateWarCards"))
        self.assertTrue(hasattr(GuiSessionStore, "senateWarExecution"))

    def test_phase_senate_cli_retired(self):
        src = _read("src/ui/commands/phase_senate.py")
        self.assertNotIn("_handle_takeover_cli", src)
        self.assertNotIn("cancel_takeover", src)
        self.assertNotIn("_takeover_player_id", src)

    def test_get_senate_view_hides_legacy_keys(self):
        fx = build_r5_base()
        view = senate_api.get_senate_view(fx["state"], fx["player_id"])
        self.assertTrue(view["success"], view)
        data = view["data"]
        for key in ("takeover_options", "can_takeover", "takeover_required",
                    "pending_takeover", "can_deploy", "continue_options", "can_continue"):
            self.assertNotIn(key, data, f"legacy DTO key still exposed: {key}")
        self.assertIn("war_cards", data)
        self.assertGreaterEqual(len(data["war_cards"]), 1)


class TestEntryParity(unittest.TestCase):
    """C-AC16 / D-SC03：AI 与 Human 走同一 Package Submit（一次整包，不循环 propose）。"""

    def test_ai_submits_one_package_and_never_loops_propose(self):
        fx = build_r5_base()
        state = fx["state"]
        seen = []

        def _capture(actor, request, context=None):
            seen.append(request)
            return {"success": True, "message": "ok",
                    "data": {"created": [{"proposal_id": 1, "type": "war_proposal"}]}, "errors": []}

        with mock.patch.object(PoliticalSystem, "submit_proposal_package", side_effect=_capture):
            with mock.patch.object(PoliticalSystem, "create_proposal",
                                   side_effect=AssertionError("AI must not loop legacy propose")):
                with mock.patch.object(senate_api, "_legion_options_for_war",
                                       return_value={"min": 1, "max": 2, "default": 1}):
                    with mock.patch("src.api.senate_api.random.random", return_value=0.0):
                        result = senate_api.auto_submit_proposals(state)

        self.assertEqual(len(seen), 1, "AI must submit exactly one package")
        self.assertIn("war_drafts", seen[0])
        self.assertTrue(result.get("success"), result)

    def test_human_entry_routes_through_propose_many(self):
        from src.ui.gui.api_adapter import GuiApiAdapter
        fx = build_r5_base()
        adapter = GuiApiAdapter(fx["state"], None)
        calls = []

        def _capture(*args, **kwargs):
            calls.append(args)
            return {"success": True, "message": "ok", "data": {"created": []}, "errors": []}

        with mock.patch.object(senate_api, "propose_many", side_effect=_capture):
            adapter.submit_senate_proposals(fx["player_id"], [])
        self.assertEqual(len(calls), 1)


class TestQmlCardRegion(unittest.TestCase):
    """D-SC02 / D-SC15 / E-01：QML 旧卡区（接管选区 + Continue 块，含 :954）退役。"""

    def test_qml_no_legacy_takeover_bindings(self):
        qml = _read("src/ui/gui/qml/stages/SenateStage.qml")
        for token in ("sessionStore.doContinueWar", "sessionStore.doTakeoverWar",
                      "senateTakeoverOptions", "senateContinueOptions",
                      "canTakeoverSenateWar", "canContinueSenateWar",
                      "senatePendingTakeover", "senateTakeoverRequired",
                      "takeoverDraftWarId", "takeoverZoneContentHeight"):
            self.assertNotIn(token, qml, f"legacy QML binding still present: {token}")

    def test_qml_uses_unified_war_card(self):
        qml = _read("src/ui/gui/qml/stages/SenateStage.qml")
        self.assertIn("sessionStore.senateWarCards", qml)
        self.assertIn("WarProposalCard", qml)
        card = _read("src/ui/gui/qml/components/WarProposalCard.qml")
        self.assertIn("draftEdited", card)
        # QML 零推导：卡内不得据 status / commanderless / legion 数量猜分类
        for token in ("war_status", "commanderless", "surviving_legion_count", "threat_level"):
            self.assertNotIn(token, card, f"QML derives lifecycle from {token}")


if __name__ == "__main__":
    unittest.main()
