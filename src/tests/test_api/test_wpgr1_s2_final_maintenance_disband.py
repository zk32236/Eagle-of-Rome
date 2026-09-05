# src/tests/test_api/test_wpgr1_s2_final_maintenance_disband.py
"""WP-G-R1 S2（R1-G-02 + R1-G-03）— 胜利后最后维护 + Population exactly-once 解散。

冻结设计：SA-Design-WP-G-R1 v1.6 §2.2/§2.3 + §3 T-R1-03/04/05 + §7.7.1 修正序列。

覆盖：
- T-R1-03  Victory/Triumph 经真实 Combat→Resolution→advance_year→Mortality→Revenue
           （released AVAILABLE Legion 权威最后维护 N×cost）→Forum→Population
           （admin DISBANDED exactly-once）→ 再跨年 Revenue（0 重复维护）→ 再 Population
           （0 重复 disband）——§7.7.1 S1~S18 修正序列（真实 API/阶段，禁 EconomicService
           直调/手工状态冒充）
- T-R1-04  Population 行政解散 exactly once + `legion_disbanded` 事件计数（frozen
           schema：legion_number/war_id/lifecycle_source/turn）；重入零新事件
- T-R1-05  re-recruit 同编号不被 stale queue 命中（新征召 ACTIVE；队列已清；不解散）

证据形态：权威状态 + Revenue 算术（calculate_maintenance breakdown + log_event
`legion_maintenance`/`legion_disbanded` structured 捕获）+ 队列状态。
"""
import logging
import unittest

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api, game_api, mortality_api, revenue_api, forum_api, session_api, senate_api, population_api

# 显式经济规则（确定性维护算术）：base=8 / veteran bonus=1 / recruit=10
_ECON_CONFIG = {
    "economic_rules": {
        "legion_maintenance_base": 8,
        "veteran_maintenance_bonus": 1,
        "legion_recruit_cost": 10,
        "faction_stipend": 0,
    },
    "mortality_rules": {
        "event_deck": [],
        "event_draw_count": 0,
        "death_count": 0,
    },
}

_WAR_REWARDS = {"treasury": 100, "land": 0, "family_prestige": 0}


class _CaptureHandler(logging.Handler):
    """捕获 state._logger 结构化记录（log_event extra 展平进 message，k=v 可断言）。"""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _enable_capture(state):
    """启用 state._logger 并挂载捕获 handler（file_path 指向 /tmp，防仓库污染）。"""
    state._config._config["logging"] = {
        "enabled": True,
        "file_path": "/tmp/eor_wpgr1_b1_s2.log",
        "log_level": "INFO",
    }
    state._setup_logging()
    handler = _CaptureHandler()
    state._logger.addHandler(handler)
    return handler


def _captured_messages(handler):
    return [r.getMessage() for r in handler.records]


def _disband_events(handler):
    return [m for m in _captured_messages(handler) if "type=legion_disbanded" in m]


def _maintenance_events(handler):
    return [m for m in _captured_messages(handler) if "type=legion_maintenance" in m]


def _build_chain_state(war_id="war1", n_legions=2, force="victory", turn_number=10):
    """§7.7.1 fixture：ACTIVE land war（naval_required=False）+ commander + N 幸存军团。"""
    state = GameState.create_for_testing(dict(_ECON_CONFIG))
    state.turn = GameTurn(turn_number=turn_number, year=-280)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)

    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="player_opt", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")

    commander = Figure(id=101, name="Test Commander", faction_id="senate", age=40)
    commander.martial = 4
    commander.influence = 10
    commander.is_absent = True
    commander.office = "consul"
    state.add_member(commander)
    faction.member_ids.append(101)

    war = War(
        id=war_id, name="Land War", strength=5, threat_level=3,
        rewards=dict(_WAR_REWARDS),
        naval_required=False, disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.commander_id = 101
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)

    ms = state._military_system
    for num in range(1, n_legions + 1):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num}"
    assigned, msg = ms.assign_to_war(list(range(1, n_legions + 1)), war_id, 101)
    assert assigned == n_legions, msg

    state.config.testing.force_battle_result = force
    return state, war, commander


def _population_human_votes(state, player_id="player_opt"):
    """人口阶段 FIX-C：human 对 5 offices 全部显式 ABSTAIN（真实 batch_vote 生产路径）。"""
    entries = [{"office": office, "figure_id": 0} for office in
               ["consul", "censor", "praetor", "quaestor", "tribune"]]
    result = population_api.batch_vote(state, player_id, entries, bypass_permission=True)
    assert result["success"], f"batch_vote failed: {result.get('message')}"
    return result


def _resolve_and_advance_population(state, player_id="player_opt"):
    """S11/S12：resolve_population_slice（含 disband + election + record result）→ advance。"""
    resolve = session_api.resolve_population_slice(state)
    assert resolve["success"], f"resolve_population_slice failed: {resolve.get('message')} {resolve.get('errors')}"
    adv = session_api.advance_population_phase(state, player_id)
    assert adv["success"], f"advance_population_phase failed: {adv.get('message')}"
    return resolve["data"]


def _senate_resolve_advance(state, player_id="player_opt"):
    """S13/S14：Senate 空提案 resolve（record result）→ advance（Path A，D-09）。"""
    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], f"resolve_senate failed: {resolved.get('message')}"
    adv = senate_api.advance_senate_phase(state, player_id)
    assert adv["success"], f"advance_senate_phase failed: {adv.get('message')}"


def _forum_round(state, player_id="player_opt"):
    """S10（forum init → resolve → advance；year N+1 的 forum 段）。"""
    init = forum_api.initialize_forum_turn(state)
    assert init["success"], f"initialize_forum_turn failed: {init.get('message')}"
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"], f"resolve_forum failed: {resolved.get('message')}"
    adv = forum_api.advance_forum_phase(state, player_id)
    assert adv["success"], f"advance_forum_phase failed: {adv.get('message')}"


def _mortality_revenue_round(state, player_id="player_opt"):
    """S6~S9（year N+1）：mortality execute/advance → revenue execute/advance。"""
    mor = mortality_api.execute_mortality_phase(state, player_id)
    assert mor["success"], f"mortality execute failed: {mor.get('message')}"
    adv_mor = mortality_api.advance_mortality_phase(state, player_id)
    assert adv_mor["success"], f"mortality advance failed: {adv_mor.get('message')}"
    rev = revenue_api.execute_revenue_phase(state, player_id)
    assert rev["success"], f"revenue execute failed: {rev.get('message')}"
    adv_rev = revenue_api.advance_revenue_phase(state, player_id)
    assert adv_rev["success"], f"revenue advance failed: {adv_rev.get('message')}"
    return rev


class TestTr103VictoryFinalMaintenanceChain(unittest.TestCase):
    """T-R1-03：Victory 跨 phase 生产链（§7.7.1 S1~S18）。"""

    def test_victory_full_chain_final_maintenance_exactly_once(self):
        state, war, _commander = _build_chain_state(force="victory")
        ms = state._military_system
        ws = state._war_system
        handler = _enable_capture(state)
        try:
            # ── S1 Combat action（forced victory → canonical resolve_war）──
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
            self.assertTrue(result["success"], result.get("message"))
            self.assertEqual(war.status, WarStatus.RESOLVED)
            # 幸存者 recall → AVAILABLE + Veteran（G1-22；晋升先于召回）
            for num in (1, 2):
                leg = ms.get_legion_by_number(num)
                self.assertEqual(leg.status, LegionStatus.AVAILABLE)
                self.assertTrue(leg.is_veteran)
            phase_data = state.get_phase_result("combat") or {}
            self.assertIn(war.id, phase_data.get("resolved_wars", []))

            # ── S2/S3 Combat confirm + advance ──
            self.assertTrue(combat_api.confirm_battle_result(state, "player_opt")["success"])
            self.assertTrue(combat_api.advance_combat(state, "player_opt")["success"])
            self.assertTrue(state.is_phase_executed("combat"))

            # ── S4 Resolution ──
            res = __import__("src.api.resolution_api", fromlist=["execute_resolution"]).execute_resolution(state)
            self.assertTrue(res["success"], res.get("message"))
            self.assertFalse(res["data"]["victory"]["game_over"])
            self.assertTrue(state.is_phase_executed("resolution"))

            # ── S5 advance_year（清 _executed_phases/_phase_results）──
            ay = game_api.advance_year(state, "player_opt")
            self.assertTrue(ay["success"], ay.get("message"))
            self.assertFalse(state.is_phase_executed("mortality"))

            # ── S6~S9 Mortality → Revenue（released AVAILABLE 最后维护 N×cost）──
            rev = _mortality_revenue_round(state, "player_opt")
            maint = rev["data"]["data"]["maintenance"]["military"]  # revenue_api data 嵌套
            # 2 幸存 veteran（8+1）×2 = 18（权威维护算术）
            total, breakdown = ms.calculate_maintenance()
            self.assertEqual(total, 18)
            self.assertEqual(maint["total"], 18)
            self.assertEqual(maint["charged"], 18)
            # log_event legion_maintenance（structured）
            maint_msgs = _maintenance_events(handler)
            self.assertTrue(maint_msgs, "legion_maintenance event missing")
            self.assertTrue(any("应扣 18" in m for m in maint_msgs))

            # ── S10 Forum ──
            _forum_round(state, "player_opt")

            # ── S11/S12 Population（exactly-once 解散）──
            _population_human_votes(state, "player_opt")
            pop_data = _resolve_and_advance_population(state, "player_opt")
            disband = pop_data["disbandment"]["legions"]
            self.assertEqual(disband["resolved_wars"]["total"], 2)  # legion_numbers [1,2]
            self.assertEqual(disband["deescalated"]["total"], 0)
            for num in (1, 2):
                self.assertEqual(ms.get_legion_by_number(num).status, LegionStatus.DISBANDED)
            self.assertEqual(ws._legions_to_disband, [])
            # legion_disbanded 事件数 == 成功解散数（resolved_wars 面），frozen schema 字段在位
            events = _disband_events(handler)
            self.assertEqual(len(events), 2)
            for ev in events:
                self.assertIn("legion_number=", ev)
                self.assertIn("war_id=war1", ev)
                self.assertIn("lifecycle_source=resolved_war", ev)
                self.assertIn("turn=", ev)

            # ── S13/S14 Senate（空提案 Path A）──
            _senate_resolve_advance(state, "player_opt")

            # ── S15/S16 Combat advance + Resolution + advance_year ──
            self.assertTrue(combat_api.advance_combat(state, "player_opt")["success"])
            res2 = __import__("src.api.resolution_api", fromlist=["execute_resolution"]).execute_resolution(state)
            self.assertTrue(res2["success"], res2.get("message"))
            ay2 = game_api.advance_year(state, "player_opt")
            self.assertTrue(ay2["success"], ay2.get("message"))

            # ── S17 再 Mortality → Revenue：DISBANDED 排除 → 0 重复维护 ──
            rev2 = _mortality_revenue_round(state, "player_opt")
            self.assertEqual(ms.calculate_maintenance()[0], 0)
            self.assertEqual(rev2["data"]["data"]["maintenance"]["military"]["total"], 0)
            self.assertEqual(rev2["data"]["data"]["maintenance"]["military"]["charged"], 0)

            # ── S18 Revenue advance → Forum → Population：0 重复 disband、事件计数不增 ──
            _forum_round(state, "player_opt")
            events_before = len(_disband_events(handler))
            _population_human_votes(state, "player_opt")
            pop2 = _resolve_and_advance_population(state, "player_opt")
            d2 = pop2["disbandment"]["legions"]
            self.assertEqual(d2["resolved_wars"]["total"], 0)
            self.assertEqual(d2["deescalated"]["total"], 0)
            self.assertEqual(len(_disband_events(handler)), events_before)  # 重入零新事件
            for num in (1, 2):
                self.assertEqual(ms.get_legion_by_number(num).status, LegionStatus.DISBANDED)
        finally:
            handler.close()
            state.close_logging()

    def test_triumph_variant_also_pays_final_maintenance(self):
        """T-R1-03 triumph 变体：forced triumph → 同一生命周期（RESOLVED → 最后维护）。"""
        state, war, _ = _build_chain_state(force="triumph")
        ms = state._military_system
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "triumph")
        self.assertTrue(result["data"]["triumph"])
        self.assertEqual(war.status, WarStatus.RESOLVED)
        for num in (1, 2):
            self.assertEqual(ms.get_legion_by_number(num).status, LegionStatus.AVAILABLE)
        # 最后一维护回合前：AVAILABLE 幸存者计费（R1-G-02 修复核心）
        total, _ = ms.calculate_maintenance()
        self.assertEqual(total, 18)  # 2 veteran × 9


class TestTr104DisbandExactlyOnceEvents(unittest.TestCase):
    """T-R1-04：Population 行政解散 exactly once + legion_disbanded 事件计数。"""

    def test_disband_events_exactly_once_and_no_reentry(self):
        state, war, _ = _build_chain_state(force="victory")
        ms = state._military_system
        ws = state._war_system
        handler = _enable_capture(state)
        try:
            # 直接走 canonical 解散入口前的真实生命周期：combat victory + confirm + advance
            self.assertTrue(combat_api.do_combat_action(state, "player_opt", war.id, "attack")["success"])
            self.assertTrue(combat_api.confirm_battle_result(state, "player_opt")["success"])
            self.assertTrue(combat_api.advance_combat(state, "player_opt")["success"])
            # 年度推进到 Population（经 resolution → advance_year → mortality → revenue → forum）
            res = __import__("src.api.resolution_api", fromlist=["execute_resolution"]).execute_resolution(state)
            self.assertTrue(res["success"])
            self.assertTrue(game_api.advance_year(state, "player_opt")["success"])
            _mortality_revenue_round(state, "player_opt")
            _forum_round(state, "player_opt")

            # Population：resolve_population_slice（canonical，含 process_population_disbandments）
            _population_human_votes(state, "player_opt")
            pop_data = _resolve_and_advance_population(state, "player_opt")
            disband = pop_data["disbandment"]["legions"]
            self.assertEqual(disband["resolved_wars"]["total"], 2)
            self.assertEqual(disband["deescalated"]["total"], 0)
            self.assertEqual(disband["resolved_wars"]["errors"], [])
            for num in (1, 2):
                self.assertEqual(ms.get_legion_by_number(num).status, LegionStatus.DISBANDED)
            self.assertEqual(ws._legions_to_disband, [])

            # 事件计数 == 成功解散数（每成功 disband 恰一条，frozen schema）
            events = _disband_events(handler)
            self.assertEqual(len(events), 2)
            for ev in events:
                for field in ("type=legion_disbanded", "legion_number=", "war_id=",
                              "lifecycle_source=", "turn="):
                    self.assertIn(field, ev)
            # resolved_wars 面事件带 war 上下文 + legion_number 一一对应
            numbers = [m.split("legion_number=")[1].split(" ")[0] for m in events]
            self.assertEqual(sorted(numbers), ["1", "2"])
            for ev in events:
                self.assertIn("lifecycle_source=resolved_war", ev)
                self.assertIn("war_id=war1", ev)

            # 重入（同年度第二次）：phase-marker 幂等 → 零新事件、零二次解散。
            # （marker 回放返回首次快照，非重算——exactly-once 证据 = 事件计数不增 +
            #  队列/legion_numbers 清空 + 权威状态不变；底层原语重算为零）
            events_before = len(events)
            again = population_api.process_population_disbandments(state)
            self.assertEqual(again, state.get_phase_result("population_disbandment"))
            self.assertEqual(len(_disband_events(handler)), events_before)
            for num in (1, 2):
                self.assertEqual(ms.get_legion_by_number(num).status, LegionStatus.DISBANDED)
            self.assertEqual(ws._legions_to_disband, [])
            self.assertEqual(war.legion_numbers, [])
            # 底层原语重入（重算权威态）亦零重复
            empty = ws.process_triumph_and_disbandment()
            self.assertEqual(empty["disbanded"]["resolved_wars"]["total"], 0)
            self.assertEqual(empty["disbanded"]["deescalated"]["total"], 0)
        finally:
            handler.close()
            state.close_logging()

    def test_deescalated_face_events_use_nullable_war_id(self):
        """deescalated 面（和约批准队列，无 war 上下文）→ war_id=None + lifecycle_source=deescalated。"""
        from src.core.systems.political_system import PoliticalSystem
        state = GameState.create_for_testing(dict(_ECON_CONFIG))
        state.turn = GameTurn(turn_number=3, year=-264)
        state._treasury = 500
        state._war_system = WarSystem(state)
        state._military_system = MilitarySystem(state)
        faction = Faction(id="senate", name="Senate", treasury=50)
        state.add_faction(faction)
        commander = Figure(id=1, name="Cmd", faction_id="senate", age=40)
        commander.office = "consul"
        state.add_member(commander)
        faction.member_ids.append(1)
        handler = _enable_capture(state)
        try:
            war = War(id="w_treaty", name="Treaty War", war_type=WarType.FOREIGN, strength=5)
            war.status = WarStatus.TRUCE
            war.set_peace_treaty({"indemnity": 50, "duration": 3, "status": "submitted", "generated_turn": 1})
            war.commander_id = 1
            # 先注册进 truce_wars（ms.assign_to_war 需经 war_system.get_war_by_id 解析战争）
            state._war_system._truce_wars.append(war)
            ms = state._military_system
            for num in (1, 2):
                ok, _ = ms.recruit_legion(num)
                assert ok
            assigned, msg = ms.assign_to_war([1, 2], war.id, 1)
            assert assigned == 2, msg
            # 批准 → 释放入队（enqueue-then-clear，ODR-CAND-01）
            PoliticalSystem(state).execute_passed_peace_treaty(war)
            self.assertEqual(sorted(state._war_system._legions_to_disband), [1, 2])

            disband = population_api.process_population_disbandments(state)
            self.assertEqual(disband["legions"]["deescalated"]["total"], 2)
            events = _disband_events(handler)
            self.assertEqual(len(events), 2)
            for ev in events:
                self.assertIn("war_id=None", ev)
                self.assertIn("lifecycle_source=deescalated", ev)
                self.assertIn("turn=3", ev)
        finally:
            handler.close()
            state.close_logging()


class TestTr105RerecruitNotHitByStaleQueue(unittest.TestCase):
    """T-R1-05：解散后同编号 re-recruit 不被 stale queue / 旧 legion_numbers 命中。"""

    def test_rerecruit_same_number_clean_lifecycle(self):
        state, war, _ = _build_chain_state(force="victory")
        ms = state._military_system
        ws = state._war_system
        # 真实生命周期：victory → revenue（最后维护）→ population（解散）
        self.assertTrue(combat_api.do_combat_action(state, "player_opt", war.id, "attack")["success"])
        self.assertTrue(combat_api.confirm_battle_result(state, "player_opt")["success"])
        self.assertTrue(combat_api.advance_combat(state, "player_opt")["success"])
        res = __import__("src.api.resolution_api", fromlist=["execute_resolution"]).execute_resolution(state)
        self.assertTrue(res["success"])
        self.assertTrue(game_api.advance_year(state, "player_opt")["success"])
        _mortality_revenue_round(state, "player_opt")
        _forum_round(state, "player_opt")
        _population_human_votes(state, "player_opt")
        _resolve_and_advance_population(state, "player_opt")

        # 解散完成：队列已清空、旧 war.legion_numbers 已 clear
        self.assertEqual(ws._legions_to_disband, [])
        self.assertEqual(war.legion_numbers, [])
        self.assertEqual(ms.get_legion_by_number(1).status, LegionStatus.DISBANDED)

        # canonical re-recruit 同编号 → 直接 ACTIVE（非 AVAILABLE 中间态，provenance 不变量）
        ok, _ = ms.recruit_legion(1)
        self.assertTrue(ok)
        legion1 = ms.get_legion_by_number(1)
        self.assertEqual(legion1.status, LegionStatus.ACTIVE)

        # 指派新战争（新生命周期）
        war2 = War(id="w_new", name="New War", war_type=WarType.FOREIGN, strength=5)
        war2.status = WarStatus.ACTIVE
        ws._active_wars.append(war2)
        assigned, msg = ms.assign_to_war([1], war2.id, 101)
        self.assertEqual(assigned, 1, msg)
        self.assertEqual(legion1.war_id, "w_new")

        # 新年度推进：Senate resolve/advance → Combat advance → Resolution → advance_year
        # （advance_year 前置 = resolution 已执行；war2 commanderless 非 actionable）
        _senate_resolve_advance(state, "player_opt")
        self.assertTrue(combat_api.advance_combat(state, "player_opt")["success"])
        res2 = __import__("src.api.resolution_api", fromlist=["execute_resolution"]).execute_resolution(state)
        self.assertTrue(res2["success"])
        self.assertTrue(game_api.advance_year(state, "player_opt")["success"])
        _mortality_revenue_round(state, "player_opt")
        _forum_round(state, "player_opt")
        _population_human_votes(state, "player_opt")
        pop2 = _resolve_and_advance_population(state, "player_opt")
        d2 = pop2["disbandment"]["legions"]
        self.assertEqual(d2["resolved_wars"]["total"], 0)
        self.assertEqual(d2["deescalated"]["total"], 0)
        self.assertEqual(legion1.status, LegionStatus.ACTIVE)
        self.assertEqual(legion1.war_id, "w_new")
        self.assertEqual(ws._legions_to_disband, [])


if __name__ == "__main__":
    unittest.main()
