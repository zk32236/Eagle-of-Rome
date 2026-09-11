# src/tests/test_api/test_wpgr4_s3_result_identity.py
"""WP-G-R4 S2（R4-G-04，SA v1.7 §8.1 C 初建：T08/T09 core + T10 core + T15 core legacy）—
CRT 身份经 API+WarSystem explicit carrier 到 event/DTO；legacy bool unknown 中性事件。

Authority: SA-Design-WP-G-R4 v1.7 §4；R4 任务包 v1.1 §8。E/F 的 Store/CLI 消费段 = S3/S4 追加。
"""
import logging
import unittest
from io import StringIO

from src.api import combat_api
from src.core.systems.war_system import WarSystem
from src.core.entities.war import WarStatus
from src.tests.fixtures import wpgr4_fixtures as F

P1 = F.P1


class _LogCapture:
    """capture GameState.log_event（需先挂 logger——create_for_testing 默认无 logger）。"""
    def __init__(self, state):
        self.records = []
        self.logger = logging.Logger(name=f"r4cap-{id(self)}", level=logging.INFO)
        self.handler = _Handler(self.records)
        self.logger.addHandler(self.handler)
        self._prev = state._logger
        state._logger = self.logger

    def close(self, state):
        state._logger = self._prev
        self.logger.removeHandler(self.handler)
        self.handler.close()


class _Handler(logging.Handler):
    def __init__(self, records):
        super().__init__()
        self._records = records

    def emit(self, record):
        self._records.append(record.getMessage())


def _event_types(records):
    import re
    types = []
    for msg in records:
        m = re.search(r"type=(\w+)", msg)
        if m:
            types.append(m.group(1))
    return types


class TestT08ForcedVictoryIdentity(unittest.TestCase):
    def test_t08_victory_identity_end_to_end(self):
        ctx = F.build_fix08(land_force="VICTORY")
        state, war = ctx["state"], ctx["war"]
        cap = _LogCapture(state)
        try:
            result = combat_api.do_combat_action(state, P1, war.id, "attack")
        finally:
            cap.close(state)
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(result["data"]["result"], "victory")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        types = _event_types(cap.records)
        self.assertIn("combat_victory", types)
        self.assertNotIn("combat_triumph", types, "VICTORY 不冒充 TRIUMPH（R4-06）")


class TestT09ForcedTriumphIdentity(unittest.TestCase):
    def test_t09_triumph_identity_end_to_end(self):
        ctx = F.build_fix08(land_force="TRIUMPH")
        state, war = ctx["state"], ctx["war"]
        cap = _LogCapture(state)
        try:
            result = combat_api.do_combat_action(state, P1, war.id, "attack")
        finally:
            cap.close(state)
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(result["data"]["result"], "triumph")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        types = _event_types(cap.records)
        self.assertIn("combat_triumph", types)
        self.assertNotIn("combat_victory", types)


class TestT10VictoryTriumphCeremonyEligibilityCore(unittest.TestCase):
    """core 段（S2）：真实 producer 产 RESOLVED + soldier_share>0 + living candidate；
    Forum 公开 vote/resolve 一次（同源公开 seam，完整 J 链 = S5）。"""

    def test_t10_ordinary_victory_keeps_ceremony_eligibility(self):
        ctx = F.build_fix09(land_force="VICTORY")
        state, war, commander = ctx["state"], ctx["war"], ctx["commander"]
        result = combat_api.do_combat_action(state, P1, war.id, "attack")
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(war.status, WarStatus.RESOLVED)
        self.assertTrue(commander.is_dead is False, "living candidate")
        self.assertGreater(war.soldier_share, 0)
        self.assertEqual(war.triumph_commander_id, commander.id)
        # 公开 seam：Forum view/vote/resolve 一次（eligibility 谓词与 R1 s5 同源）
        from src.api import forum_api
        elig = forum_api._triumph_eligibility(state, war)
        self.assertEqual(elig["eligible"], True)
        # 三 layer 一致：view row → vote 接受
        view = forum_api.get_forum_view(state, P1)
        self.assertTrue(view["success"])
        ids = [row["war_id"] for row in (view["data"].get("triumph_wars") or [])]
        self.assertIn(war.id, ids)
        vote = forum_api.vote_triumph(state, P1, war.id, True)
        self.assertTrue(vote["success"], vote.get("message"))


class TestT15LegacyBoolCompatibility(unittest.TestCase):
    """core 段（S2）：legacy bool-only 调用明确 unknown；坏值零 mutation。"""

    def test_t15_legacy_bool_true_unknown_neutral_event(self):
        state = F.make_base_state(turn_number=10, year=-280)
        for phase in ["senate"]:
            state.mark_phase_executed(phase)
        state.pyrrhic_war_won = True
        state._treasury = 500
        faction = F.add_faction(state)
        F.add_player(state)
        from src.core.entities.figure import Figure
        fig = Figure(id=101, name="Legacy Cmd", faction_id="optimates", age=40)
        fig.martial = 4
        fig.office = "proconsul"
        fig.is_absent = True
        state.add_member(fig)
        faction.member_ids.append(101)
        war = F.make_war("legacy_war", "Legacy War", status=WarStatus.ACTIVE,
                         naval_required=False, commander_id=101, enemy_land=2)
        F.attach_active(state, war)
        F.recruit_legions_for_war(state, war, 101, count=1)
        ws = state.get_war_system()
        cap = _LogCapture(state)
        try:
            resolved = ws.resolve_war(war.id, True)  # legacy bool-only
        finally:
            cap.close(state)
        self.assertEqual(war.status, WarStatus.RESOLVED)
        self.assertIsNone(resolved["combat_result"], "legacy unknown 不猜 CRT")
        self.assertEqual(resolved["result_identity_source"], "legacy_unspecified")
        types = _event_types(cap.records)
        self.assertIn("war_resolved", types)
        self.assertNotIn("combat_triumph", types)
        self.assertNotIn("combat_victory", types)

    def test_t15_bad_combat_result_zero_mutation(self):
        state = F.make_base_state(turn_number=10, year=-280)
        for phase in ["senate"]:
            state.mark_phase_executed(phase)
        F.add_faction(state)
        F.add_player(state)
        war = F.make_war("bad_war", "Bad War", status=WarStatus.ACTIVE, naval_required=False)
        F.attach_active(state, war)
        ws = state.get_war_system()
        with self.assertRaises(ValueError):
            ws.resolve_war(war.id, True, combat_result="defeat")
        with self.assertRaises(ValueError):
            ws.resolve_war(war.id, False, combat_result="victory")
        self.assertEqual(war.status, WarStatus.ACTIVE, "坏值零 mutation")
        self.assertIsNone(war.commander_id)



# ---------------------------------------------------------------------------
# S3 追加（SA v1.7 §8.1 C 段：T08/09 的 Store/phase_data 段 + T15 legacy DTO 面）
# ---------------------------------------------------------------------------

_TOP_ALIAS_KEYS = [
    "dice", "total_attack", "enemy_defence", "total_score",
    "losses", "casualty_numbers", "triumph", "loot",
    "treasury_share", "faction_share", "commander_share", "soldier_share",
]


def _phase(state):
    return state.get_phase_result("combat") or {}


def _store(state):
    from src.ui.gui.session_store import GuiSessionStore
    store = GuiSessionStore(state)
    store.initialize(P1)
    return store


class TestT08T09StorePhaseDataSegments(unittest.TestCase):
    """S3 追加：forced victory/triumph 的 phase_data/pending/view/Store 四层同值
    （SA v1.7 §5.4：同一完整 v2 envelope 持久，不透传丢字段）。"""

    def _act(self, land_force):
        ctx = F.build_fix08(land_force=land_force)
        state, war = ctx["state"], ctx["war"]
        result = combat_api.do_combat_action(state, P1, war.id, "attack")
        self.assertTrue(result["success"], result.get("message"))
        return state, war, result["data"]

    def test_t08_victory_phase_data_and_store_segment(self):
        state, war, data = self._act("VICTORY")
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(data["land"]["result"], "victory")
        phase = _phase(state)
        self.assertEqual(phase["pending_result"], data)
        self.assertEqual(phase["war_results"][war.id], data)
        view = combat_api.get_combat_view(state, P1)["data"]
        self.assertEqual(view["battle_results"], [data])
        # Store 层（combatBattleResultDetail 透传值与 API DTO 逐项相同）
        store = _store(state)
        self.assertEqual(store.combatBattleResultDetail, data)
        self.assertEqual(store.combatBattleResultDetail.get("land", {}).get("result"), "victory")

    def test_t09_triumph_phase_data_and_store_segment(self):
        state, war, data = self._act("TRIUMPH")
        self.assertEqual(data["land"]["result"], "triumph")
        phase = _phase(state)
        self.assertEqual(phase["pending_result"], data)
        self.assertEqual(phase["war_results"][war.id], data)
        store = _store(state)
        self.assertEqual(store.combatBattleResultDetail, data)
        self.assertEqual(store.combatBattleResultDetail.get("land", {}).get("result"), "triumph")


class TestT15LegacyDtoFace(unittest.TestCase):
    """S3 追加（SA v1.7 §5.1 兼容窗口 / §8.1 T15）：land.executed=true 保留旧顶层字段
    为 land 纯 alias（值逐项相同）；deprecated scout 预览不生成新双阶段 ATTACK 证据。"""

    def test_t15_land_alias_identical_to_nested(self):
        ctx = F.build_fix08(land_force="VICTORY")
        state, war = ctx["state"], ctx["war"]
        result = combat_api.do_combat_action(state, P1, war.id, "attack")
        self.assertTrue(result["success"], result.get("message"))
        data = result["data"]
        self.assertTrue(data["land"]["executed"])
        for key in _TOP_ALIAS_KEYS:
            self.assertEqual(data[key], data["land"][key], f"顶层 alias {key} != land.{key}")
        self.assertEqual(data["result"], data["land"]["result"])
        self.assertEqual(data["result_label"], data["land"]["result_label"])

    def test_t15_scout_preview_not_dual_stage_attack_evidence(self):
        """deprecated scout = preview-only：无 dual-stage envelope、不持久（B-19 兼容边界）。"""
        ctx = F.build_fix08(land_force="VICTORY")
        state, war = ctx["state"], ctx["war"]
        result = combat_api.do_combat_action(state, P1, war.id, "scout")
        self.assertTrue(result["success"], result.get("message"))
        data = result["data"]
        self.assertTrue(data.get("deprecated"), "scout 保留 deprecated preview 语义")
        self.assertNotEqual(data.get("schema_version"), 2, "scout 预览非 dual-stage ATTACK envelope")
        phase = _phase(state)
        self.assertNotIn("pending_result", phase)
        self.assertNotIn(war.id, phase.get("resolved_wars", []))


if __name__ == "__main__":
    unittest.main()
