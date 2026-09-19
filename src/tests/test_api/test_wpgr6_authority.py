# src/tests/test_api/test_wpgr6_authority.py
"""WP-G-R6 DA-1（SA §A.1/A.2；AC-01…05）— 唯一 authority route producer + CardDTO + 消费面。

证据分类 = DATA / 静态扫描（RENDER 归 SO）。断言方向：
- Core 唯一 route producer `classify_war_authority(facts)`（纯 helper）；返回值严格
  ∈ {senate_vote, consul_direct}，keys ⊆ 真正可执行 allowed_modes；
- CardDTO 增 `schema_version: 2` + `authority_by_mode`（senate_api 只读透传）；
- AC-01…05 route 源级：active→senate_vote；Peace→senate_vote；passive/ongoing/pending-command→consul_direct；
- 负测：恶意客户端附 authority=consul_direct 被忽略；vote/veto 候选集 ⊆ 真实 Senate proposal；
  QML 不从 classification/status/名字/将领有无推导 route（只读 authority_by_mode）。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.api import senate_api
from src.core.systems.political_system import (
    PoliticalSystem, classify_war_authority,
    AUTHORITY_SENATE_VOTE, AUTHORITY_CONSUL_DIRECT,
)
from src.tests.fixtures.wpgr5_fixtures import (
    build_r5_base, FIXED, card_by_war, submit_request, command_draft, peace_draft,
)


def _read(rel_path: str) -> str:
    with open(os.path.join(PROJECT_ROOT, rel_path), "r", encoding="utf-8") as fh:
        return fh.read()


class TestClassifyWarAuthority(unittest.TestCase):
    """SA §A.1：纯分类表逐行可判（source-level）。"""

    def test_active_declaration_is_senate_vote(self):
        self.assertEqual(
            classify_war_authority({"classification": "active_declaration",
                                    "allowed_modes": ["command"]}),
            {"command": AUTHORITY_SENATE_VOTE})

    def test_passive_declaration_is_consul_direct(self):
        self.assertEqual(
            classify_war_authority({"classification": "passive_declaration",
                                    "allowed_modes": ["command"]}),
            {"command": AUTHORITY_CONSUL_DIRECT})

    def test_ongoing_is_consul_direct(self):
        self.assertEqual(
            classify_war_authority({"classification": "ongoing",
                                    "allowed_modes": ["command"]}),
            {"command": AUTHORITY_CONSUL_DIRECT})

    def test_pending_peace_split_route(self):
        facts = {"classification": "pending_peace", "allowed_modes": ["command", "peace"]}
        self.assertEqual(classify_war_authority(facts),
                         {"command": AUTHORITY_CONSUL_DIRECT, "peace": AUTHORITY_SENATE_VOTE})

    def test_other_existing_has_no_route(self):
        self.assertEqual(
            classify_war_authority({"classification": "other_existing",
                                    "allowed_modes": ["command"]}), {})

    def test_keys_subset_of_allowed_modes(self):
        # 只产 allowed_modes 内的 route（pending_peace 但 allowed 仅 command → 不产 peace）
        self.assertEqual(
            classify_war_authority({"classification": "pending_peace",
                                    "allowed_modes": ["command"]}),
            {"command": AUTHORITY_CONSUL_DIRECT})

    def test_unknown_classification_and_bad_input_fail_closed(self):
        self.assertEqual(classify_war_authority({"classification": "weird"}), {})
        self.assertEqual(classify_war_authority(None), {})

    def test_no_derivation_from_label_or_commander(self):
        # 名字/将领有无不得改变 route：仅 classification+allowed_modes 决定
        base = {"classification": "ongoing", "allowed_modes": ["command"]}
        extra = dict(base, war_name="XXXX", current_commander_id=None, is_real_war=True)
        self.assertEqual(classify_war_authority(base), classify_war_authority(extra))


class TestWarCardDtoAuthority(unittest.TestCase):
    """SA §A.2：CardDTO schema_version:2 + authority_by_mode（经 senate_api 只读透传）。"""

    def setUp(self):
        self.ctx = build_r5_base(turn_number=1)
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def _cards(self):
        return self.ps.build_war_card_views({"current_turn": 1, "consul_id": self.ctx["consul_id"]})

    def test_schema_version_and_field_present(self):
        view = senate_api.get_senate_view(self.state, self.ctx["player_id"])
        self.assertTrue(view["success"], view.get("message"))
        for card in view["data"]["war_cards"]:
            self.assertEqual(card["schema_version"], 2, card["war_id"])
            self.assertIn("authority_by_mode", card)

    def test_authority_values_and_keys_consistent(self):
        for card in self._cards():
            routes = card["authority_by_mode"]
            allowed = card["allowed_modes"]
            self.assertTrue(set(routes.keys()).issubset(set(allowed)), card["war_id"])
            for value in routes.values():
                self.assertIn(value, (AUTHORITY_SENATE_VOTE, AUTHORITY_CONSUL_DIRECT))

    # ---- AC-01 active declaration ----
    def test_ac01_active_declaration_senate_vote(self):
        card = card_by_war(self._cards(), FIXED["war_threat"])
        self.assertEqual(card["classification"], "active_declaration")
        self.assertEqual(card["authority_by_mode"], {"command": AUTHORITY_SENATE_VOTE})

    # ---- AC-02 pending peace ----
    def test_ac02_peace_senate_vote(self):
        card = card_by_war(self._cards(), FIXED["war_peace"])
        self.assertEqual(card["classification"], "pending_peace")
        self.assertEqual(card["authority_by_mode"]["peace"], AUTHORITY_SENATE_VOTE)

    # ---- AC-03 passive declaration ----
    def test_ac03_passive_declaration_consul_direct(self):
        card = card_by_war(self._cards(), FIXED["war_passive"])
        self.assertEqual(card["classification"], "passive_declaration")
        self.assertEqual(card["authority_by_mode"], {"command": AUTHORITY_CONSUL_DIRECT})

    # ---- AC-04 ongoing (incl. same-general N=0) ----
    def test_ac04_ongoing_consul_direct_route_independent_of_n(self):
        card = card_by_war(self._cards(), FIXED["war_ongoing"])
        self.assertEqual(card["classification"], "ongoing")
        self.assertEqual(card["authority_by_mode"], {"command": AUTHORITY_CONSUL_DIRECT})
        # 同将 N=0：route 不随 N/将领有无变化
        draft = command_draft(FIXED["war_ongoing"], self.ctx["cmd_a"].id, reinforcement_n=0)
        self.assertEqual(draft["reinforcement_n"], 0)
        self.assertEqual(card_by_war(self._cards(), FIXED["war_ongoing"])["authority_by_mode"],
                         {"command": AUTHORITY_CONSUL_DIRECT})

    # ---- AC-05 pending peace command ----
    def test_ac05_pending_peace_command_consul_direct(self):
        card = card_by_war(self._cards(), FIXED["war_peace"])
        self.assertEqual(card["authority_by_mode"]["command"], AUTHORITY_CONSUL_DIRECT)


class TestAuthorityRouteEndToEnd(unittest.TestCase):
    """AC-01…05 源级端到端（Submit 仍按 R5 机制发布真 Senate proposal，DA-1 不改发布）。"""

    def setUp(self):
        self.ctx = build_r5_base(turn_number=1)
        self.state = self.ctx["state"]
        self.ps = PoliticalSystem(self.state)

    def _vote_all_factions(self, proposal_id):
        for faction in self.state.get_active_factions():
            player = self.state.get_player_by_faction(faction.id)
            if player:
                self.state.record_senate_vote(player.player_id, proposal_id, True)

    def test_ac01_active_declaration_exactly_one_real_proposal_and_legal_veto(self):
        draft = command_draft(FIXED["war_threat"], self.ctx["consul_id"], reinforcement_n=0)
        res = senate_api.propose_many(self.state, self.ctx["player_id"],
                                      submit_request([draft], session="S-AC01", request_id="r-ac01"))
        self.assertTrue(res["success"], res)
        proposals = self.state.get_senate_proposals()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["type"], "war_proposal")
        self.assertEqual(proposals[0]["source"], "active_declaration")
        self.assertEqual(proposals[0]["mode"], "command")
        # 合法 Veto 路径：投票完成后该真 Senate proposal 进入否决候选集
        self._vote_all_factions(proposals[0]["id"])
        candidates = self.ps.build_vote_results_and_candidates()["veto_candidate_ids"]
        self.assertIn(proposals[0]["id"], candidates)

    def test_ac02_peace_exactly_one_proposal_and_veto_retained(self):
        draft = peace_draft(FIXED["war_peace"])
        res = senate_api.propose_many(self.state, self.ctx["player_id"],
                                      submit_request([draft], session="S-AC02", request_id="r-ac02"))
        self.assertTrue(res["success"], res)
        proposals = self.state.get_senate_proposals()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["type"], "war_proposal")
        self.assertEqual(proposals[0]["mode"], "peace")
        self._vote_all_factions(proposals[0]["id"])
        candidates = self.ps.build_vote_results_and_candidates()["veto_candidate_ids"]
        self.assertIn(proposals[0]["id"], candidates)

    def test_ac03_vote_veto_candidate_set_only_real_senate_proposals(self):
        # passive (direct route) 若被提交仍产生真 proposal（R5 机制）；断言候选集 ⊆ 真 proposal id，
        # 即 vote/veto 集合内不存在任何非 proposal / direct 身份 id。
        draft = command_draft(FIXED["war_passive"], self.ctx["consul_id"], reinforcement_n=0)
        res = senate_api.propose_many(self.state, self.ctx["player_id"],
                                      submit_request([draft], session="S-AC03", request_id="r-ac03"))
        self.assertTrue(res["success"], res)
        proposal_ids = {p["id"] for p in self.state.get_senate_proposals()}
        for p in self.state.get_senate_proposals():
            self._vote_all_factions(p["id"])
        candidates = set(self.ps.build_vote_results_and_candidates()["veto_candidate_ids"])
        self.assertTrue(candidates.issubset(proposal_ids))


class TestNegativeAuthority(unittest.TestCase):
    """负测：恶意客户端 route 声称被忽略；QML 只读 authority_by_mode、零推导。"""

    def setUp(self):
        self.ctx = build_r5_base(turn_number=1)
        self.state = self.ctx["state"]

    def test_malicious_client_authority_claim_ignored(self):
        draft = command_draft(FIXED["war_threat"], self.ctx["consul_id"], reinforcement_n=0)
        draft["authority"] = "consul_direct"
        draft["authority_by_mode"] = {"command": "consul_direct"}
        res = senate_api.propose_many(self.state, self.ctx["player_id"],
                                      submit_request([draft], session="S-EVIL", request_id="r-evil"))
        self.assertTrue(res["success"], res)
        snap = self.state.get_senate_proposals()[0]
        # Core 忽略客户端声称：source 由事实重取（active_declaration），无客户端 authority 键泄漏
        self.assertEqual(snap["source"], "active_declaration")
        self.assertEqual(snap["mode"], "command")
        # R6（§A.3，DA-2 B2）：快照 authority 由事实重取（active_declaration → senate_vote）；
        # 客户端声称的 consul_direct 被忽略（不得当作权限凭据）。
        self.assertEqual(snap["authority"], "senate_vote")
        self.assertNotEqual(snap["authority"], "consul_direct")
        self.assertNotIn("authority_by_mode", snap)

    def test_war_type_smuggled_in_proposals_rejected(self):
        # 普通 proposals 数组偷偷塞 War 类型 → 拒绝（不得绕过 claims）
        bad = {"war_drafts": [], "proposals": [{"type": "war", "params": {"war_id": FIXED["war_threat"],
                                                                          "legions": 1}}]}
        res = senate_api.propose_many(self.state, self.ctx["player_id"], bad)
        self.assertFalse(res["success"])
        codes = [e.get("code") for e in (res.get("errors") or [])]
        self.assertIn("SUBMIT_REQUEST_INVALID", codes)
        self.assertEqual(self.state.get_senate_proposals(), [])

    def test_qml_reads_authority_by_mode_and_never_derives(self):
        card_qml = _read("src/ui/gui/qml/components/WarProposalCard.qml")
        stage_qml = _read("src/ui/gui/qml/stages/SenateStage.qml")
        self.assertIn("authority_by_mode", card_qml)
        self.assertIn("routeReady", card_qml)
        self.assertIn("authority_by_mode", stage_qml)
        # 零推导：不得据 status / commanderless / legion 数 / threat level 推 route
        for token in ("war_status", "commanderless", "surviving_legion_count", "threat_level"):
            self.assertNotIn(token, card_qml, f"QML derives route from {token}")


class TestVoteSenateSetValidation(unittest.TestCase):
    """DA-4 B4 窄项 R-B3-2：vote 路径补齐 Senate 集合校验。

    与 veto 侧已实现语义一致（DA-Plan DA-3：「`vote`/`veto` 基于 Senate 集合校验每个 ID
    （unknown/direct ID **整次拒绝**）」）：
    - unknown ID → 整次拒绝 + 零票账写入；
    - direct decision ID（FROZEN ConsulWarDecision，无 `proposal_id`）→ 不得被当作可投票项；
    - 混合（合法 + 非法）→ 整批拒绝（不部分记录）；
    - 合法真 Senate proposal 仍正常记录（回归守护）。
    """

    def setUp(self):
        self.ctx = build_r5_base(turn_number=1)
        self.state = self.ctx["state"]
        self.player = self.ctx["player_id"]

    def _submit_senate_proposal(self):
        draft = command_draft(FIXED["war_threat"], self.ctx["consul_id"], reinforcement_n=0)
        res = senate_api.propose_many(
            self.state, self.player,
            submit_request([draft], session="S-VOTE-SET", request_id="r-vote-set"))
        self.assertTrue(res["success"], res)
        proposals = self.state.get_senate_proposals()
        self.assertEqual(len(proposals), 1)
        return proposals[0]["id"]

    def _votes_ledger(self):
        return self.state.get_senate_votes_copy().get(self.player, {})

    def test_vote_valid_senate_proposal_still_recorded(self):
        pid = self._submit_senate_proposal()
        res = senate_api.vote(self.state, self.player, [pid], [True])
        self.assertTrue(res["success"], res)
        self.assertEqual(res["data"]["recorded"], 1)
        self.assertIs(self.state.get_senate_votes_copy()[self.player][pid], True)

    def test_vote_unknown_id_rejected_whole_batch_zero_ledger(self):
        self._submit_senate_proposal()
        before = dict(self._votes_ledger())
        res = senate_api.vote(self.state, self.player, [999999], [True])
        self.assertFalse(res["success"])
        self.assertEqual(res["data"].get("recorded"), 0)
        self.assertEqual(res["data"]["rejected_ids"][0]["reason"], "not_submitted")
        self.assertEqual(self._votes_ledger(), before)          # 零票账写入

    def test_vote_direct_decision_id_rejected_zero_ledger(self):
        # passive → consul_direct：只产出 FROZEN ConsulWarDecision，**无 Senate proposal**
        draft = command_draft(FIXED["war_passive"], self.ctx["consul_id"], reinforcement_n=0)
        res = senate_api.propose_many(
            self.state, self.player,
            submit_request([draft], session="S-VOTE-DIRECT", request_id="r-vote-direct"))
        self.assertTrue(res["success"], res)
        self.assertEqual(self.state.get_senate_proposals(), [])   # direct 身份空间独立
        session = self.state.get_senate_session()
        direct_id = next(iter(self.state.get_consul_war_decisions(session)))
        before = self._votes_ledger()
        result = senate_api.vote(self.state, self.player, [direct_id], [True])
        self.assertFalse(result["success"])
        self.assertEqual(result["data"]["rejected_ids"][0]["reason"], "not_submitted")
        self.assertEqual(self._votes_ledger(), before)           # 零票账写入

    def test_vote_mixed_valid_and_unknown_rejects_entire_batch(self):
        pid = self._submit_senate_proposal()
        before = dict(self._votes_ledger())
        res = senate_api.vote(self.state, self.player, [pid, 999999], [True, True])
        self.assertFalse(res["success"])
        self.assertEqual(res["data"].get("recorded"), 0)
        self.assertNotIn(pid, self._votes_ledger())              # 整次拒绝：合法项也不落账
        self.assertEqual(self._votes_ledger(), before)


class TestWarCardCommanderReadabilitySource(unittest.TestCase):
    """SA §D.2（DA-4 B4）：指挥官完整身份可读——**源码/绑定面**。

    RENDER（最小窗口宽度真实渲染 + 键盘焦点）归 SO 帧 `r6-war-card-long-commander`〔r〕；
    本类只关闭源码/绑定面，不以字符串断言替代渲染证明。
    """

    @classmethod
    def setUpClass(cls):
        cls.qml = _read("src/ui/gui/qml/components/WarProposalCard.qml")

    def test_identity_text_bound_to_candidate_label_wrap_no_elide(self):
        self.assertIn("warCardCommanderIdentity", self.qml)
        self.assertIn("cardRoot.identityText", self.qml)
        self.assertIn("visible: cardRoot.commandSelected", self.qml)
        self.assertIn("candidateIdentityLabel", self.qml)      # 绑定当前 candidate label
        self.assertIn("wrapMode: Text.Wrap", self.qml)
        self.assertIn("elide: Text.ElideNone", self.qml)       # 禁 elide
        self.assertNotIn("elide: Text.ElideRight", self.qml.split("warCardCommanderIdentity")[1])

    def test_non_candidate_id_uses_core_label_and_unselectable_hint(self):
        # 当前 ID 不在候选 → Core current/冻结 label（current_commander_label）+ 不可选提示
        self.assertIn("current_commander_label", self.qml)
        self.assertIn("不在候选，不可选", self.qml)
        self.assertIn("identityIsCandidate", self.qml)

    def test_candidate_delegate_and_hover_focus_tooltip(self):
        self.assertIn("delegate: ItemDelegate", self.qml)
        self.assertIn("ToolTip.text", self.qml)
        self.assertIn("ToolTip.visible", self.qml)
        self.assertIn("commanderCombo.hovered", self.qml)
        self.assertIn("commanderIdentity.activeFocus", self.qml)

    def test_frozen_readonly_summary_shows_full_frozen_label(self):
        self.assertIn("warCardFrozenCommanderLabel", self.qml)
        self.assertIn("frozenIdentityLabel", self.qml)
        self.assertIn("target_commander_label", self.qml)      # 冻结快照完整身份
        self.assertIn("visible: !cardRoot.editable", self.qml)  # 只读态（提交后）


if __name__ == "__main__":
    unittest.main()
