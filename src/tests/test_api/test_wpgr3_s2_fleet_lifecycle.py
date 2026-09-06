# src/tests/test_api/test_wpgr3_s2_fleet_lifecycle.py
"""WP-G-R3 S2（R3-G-02 + T-R3-04/05/06）— Fleet 维护、召回与退役（SC-R3-03/04，Evidence Class=DATA）。

冻结设计：SA-Design-WP-G-R3-2026-09-05.md v1.2 §2.1/§2.2/§2.3/§2.4 + §10 T04~T06。

覆盖（FIX-R3-LC / FIX-R3-SHORT）：
- T04  canonical VICTORY/TRIUMPH → recall survivors AVAILABLE 并清 mission（DESTROYED 不复活）
       → Revenue naval 实扣（charged=before−after 逐舰现场 type 复算；naval_maintenance 事件）
       → Population 行政解散（DISBANDED 恰一次）→ 次年 Revenue 零再费 → 次年 Population 零新事件
- T05  短款全变体（SC-R3-04）：恰差一舰/累计两舰/零国库/已负国库 failure/absent system；
       ON_MISSION 计费与解散（war assignment index 清理）；完整 DTO/event schema
- T06  A resolved + B live：A 的 released AVAILABLE survivor 在 Population 退役（窄修），
       B 的 live Fleet 仍 maintenance-bearing 不被连坐解散；Population exactly-once + 次年仍计费

红测基线（ac1d293）：apply_maintenance 正常路径无 log_event/结构化 summary；短款分支仅
AVAILABLE + break-before-add + 未累计节省（恰差一舰零解散失败）；naval DTO 缺
charged/shortfall/disbanded/…；RevenueStage 显示 naval.total（短款虚报）；decider 全局
「任何战争需海军即阻止退休」（A resolved 被 B 保留）。
"""
import logging
import unittest

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.service.economic_service import EconomicService
from src.api import combat_api, forum_api, game_api, mortality_api, population_api, revenue_api, senate_api, session_api

# 显式经济规则（确定性维护算术：trireme=4 / quinquereme=6；零军团池避免军团维护干扰 naval 断言）
_ECON_CONFIG = {
    "economic_rules": {
        "fleet_types": {
            "trireme": {"build_cost": 40, "build_time": 1, "maintenance_cost": 4, "strength_base": 3},
            "quinquereme": {"build_cost": 60, "build_time": 1, "maintenance_cost": 6, "strength_base": 5},
        },
        "default_fleet_type": "trireme",
        "legion_maintenance_base": 8,
        "legion_recruit_cost": 10,
        "faction_stipend": 0,
    },
    "mortality_rules": {"event_deck": [], "event_draw_count": 0, "death_count": 0},
    "testing": {"bypass_player_check": True},
}

_WAR_REWARDS = {"treasury": 100, "land": 0, "family_prestige": 0}


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _enable_capture(state):
    state._config._config["logging"] = {
        "enabled": True,
        "file_path": "/tmp/eor_wpgr3_b1_s2.log",
        "log_level": "INFO",
    }
    state._setup_logging()
    handler = _CaptureHandler()
    state._logger.addHandler(handler)
    return handler


def _captured_messages(handler):
    return [r.getMessage() for r in handler.records]


def _naval_maintenance_events(handler):
    return [m for m in _captured_messages(handler) if "type=naval_maintenance" in m]


def _fleet_disband_events(handler):
    return [m for m in _captured_messages(handler) if "type=naval_fleet_disbanded" in m]


def _build_state(treasury=500):
    """Base naval lifecycle fixture：senate faction + human player + 三系统。"""
    state = GameState.create_for_testing({k: dict(v) for k, v in _ECON_CONFIG.items()})
    state.turn = GameTurn(turn_number=10, year=-260)
    state._treasury = treasury
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)
    faction = Faction(id="senate", name="Senate", treasury=50)
    state.add_faction(faction)
    player = Player(player_id="player_opt", faction_id="senate", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")
    return state, faction


def _add_commander(state, faction, figure_id=101, martial=4):
    commander = Figure(id=figure_id, name="Test Commander", faction_id=faction.id, age=40)
    commander.martial = martial
    commander.influence = 10
    commander.is_absent = True
    commander.office = "consul"
    state.add_member(commander)
    faction.member_ids.append(figure_id)
    return commander


def _make_war(state, war_id, naval_required=True, commander_id=None,
              status=WarStatus.ACTIVE, enemy_naval=10):
    war = War(
        id=war_id, name=f"War {war_id}", strength=8, threat_level=3,
        rewards=dict(_WAR_REWARDS),
        naval_required=naval_required, enemy_naval_current=enemy_naval,
        enemy_naval_max=enemy_naval,
        disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.status = status
    war.commander_id = commander_id
    if status == WarStatus.ACTIVE:
        state._war_system._active_wars.append(war)
    elif status == WarStatus.RESOLVED:
        state._war_system._war_discard.append(war)
    return war


def _add_fleet(state, number, fleet_type="trireme", target_war_id=None):
    fleet = Fleet(number=number, fleet_type=fleet_type)
    fleet._strength_base = state.config.get("economic_rules.fleet_types", {}).get(fleet_type, {}).get("strength_base", 3)
    fleet._target_war_id = target_war_id
    fleet._status = FleetStatus.AVAILABLE
    state._naval_system._fleets[number] = fleet
    return fleet


def _assign_fleet(state, fleet, war, commander_id=None):
    ok = state._naval_system.assign_fleet_to_war(fleet.number, war.id, "naval", commander_id)
    assert ok, f"assign fleet {fleet.number} to {war.id}"
    return fleet


def _add_legions(state, numbers, war, commander_id):
    ms = state._military_system
    for num in numbers:
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num}"
    assigned, _msg = ms.assign_to_war(list(numbers), war.id, commander_id)
    assert assigned == len(numbers)


def _mortality_revenue_round(state):
    mor = mortality_api.execute_mortality_phase(state, "player_opt")
    assert mor["success"], f"mortality: {mor.get('message')}"
    assert mortality_api.advance_mortality_phase(state, "player_opt")["success"]
    rev = revenue_api.execute_revenue_phase(state, "player_opt")
    assert rev["success"], f"revenue: {rev.get('message')}"
    assert revenue_api.advance_revenue_phase(state, "player_opt")["success"]
    return rev


def _forum_round(state):
    init = forum_api.initialize_forum_turn(state)
    assert init["success"], f"forum init: {init.get('message')}"
    resolved = forum_api.resolve_forum(state)
    assert resolved["success"], f"forum resolve: {resolved.get('message')}"
    assert forum_api.advance_forum_phase(state, "player_opt")["success"]


def _population_votes_and_resolve(state):
    entries = [{"office": office, "figure_id": 0}
               for office in ["consul", "censor", "praetor", "quaestor", "tribune"]]
    voted = population_api.batch_vote(state, "player_opt", entries, bypass_permission=True)
    assert voted["success"], f"batch_vote: {voted.get('message')}"
    resolved = session_api.resolve_population_slice(state)
    assert resolved["success"], f"resolve_population_slice: {resolved.get('message')} {resolved.get('errors')}"
    adv = session_api.advance_population_phase(state, "player_opt")
    assert adv["success"], f"advance_population_phase: {adv.get('message')}"
    return resolved["data"]


def _senate_resolve_advance(state):
    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], f"resolve_senate: {resolved.get('message')}"
    adv = senate_api.advance_senate_phase(state, "player_opt")
    assert adv["success"], f"advance_senate_phase: {adv.get('message')}"


def _combat_resolution_advance_year(state):
    assert combat_api.advance_combat(state, "player_opt")["success"]
    res = __import__("src.api.resolution_api", fromlist=["execute_resolution"]).execute_resolution(state)
    assert res["success"], f"execute_resolution: {res.get('message')}"
    ay = game_api.advance_year(state, "player_opt")
    assert ay["success"], f"advance_year: {ay.get('message')}"


def _revenue_naval_dto(rev):
    """设计 §2.3：execute_revenue_phase(...).data 是 service response；权威 DTO =
    .data.maintenance.naval（顶层 .maintenance 是错误取法）。"""
    return rev["data"]["data"]["maintenance"]["naval"]


class TestTr104NavalVictoryRecallLifecycle(unittest.TestCase):
    """T-R3-04：canonical naval VICTORY → recall survivors AVAILABLE → Revenue 实扣一次 →
    Population DISBANDED 恰一次 → 次年 Revenue 0 → 次年 Population 0 新事件。"""

    def _naval_chain_state(self, force_naval="VICTORY", force_land="victory"):
        state, faction = _build_state(treasury=500)
        commander = _add_commander(state, faction)
        war = _make_war(state, "naval_war", naval_required=True, commander_id=commander.id, enemy_naval=10)
        for num in (1, 2):
            fleet = _add_fleet(state, num, fleet_type="trireme", target_war_id=war.id)
            _assign_fleet(state, fleet, war, commander_id=commander.id)
        # 一艘 DESTROYED（不得复活、不得计费）
        dead = _add_fleet(state, 9, fleet_type="trireme", target_war_id=war.id)
        dead.mark_destroyed(state.turn.turn_number)
        _add_legions(state, (1, 2), war, commander.id)
        state.config.testing.force_naval_result = force_naval
        state.config.testing.force_battle_result = force_land
        return state, war, commander

    def test_naval_victory_full_chain_charged_once_disbanded_once(self):
        state, war, _commander = self._naval_chain_state()
        ns = state._naval_system
        handler = _enable_capture(state)
        try:
            # ── S1 canonical combat：naval VICTORY（获控）→ land victory → RESOLVED ──
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
            self.assertTrue(result["success"], result.get("message"))
            self.assertEqual(war.status, WarStatus.RESOLVED)
            # recall survivors → AVAILABLE + 清 mission（ON_MISSION 集空、war assignment 空）
            for num in (1, 2):
                fleet = ns.get_fleet(num)
                self.assertEqual(fleet.status, FleetStatus.AVAILABLE)
                self.assertIsNone(fleet.assigned_war_id)
            self.assertEqual(war.assigned_fleet_ids, [])
            # DESTROYED 不复活
            self.assertEqual(ns.get_fleet(9).status, FleetStatus.DESTROYED)

            # ── S2/S3 confirm + advance combat ──
            self.assertTrue(combat_api.confirm_battle_result(state, "player_opt")["success"])
            self.assertTrue(combat_api.advance_combat(state, "player_opt")["success"])
            # ── S4/S5 resolution + advance_year ──
            _combat_resolution_advance_year(state)

            # ── S6~S9 Mortality → Revenue：2 幸存 AVAILABLE trireme × 4 = 8 实扣一次 ──
            rev = _mortality_revenue_round(state)
            naval = _revenue_naval_dto(rev)
            self.assertEqual(naval["available"], True)
            self.assertEqual(naval["total"], 8)
            self.assertEqual(naval["charged"], 8)
            self.assertEqual(naval["disbanded"], 0)
            self.assertEqual(naval["shortfall"], 0)
            # charged = treasury_before − treasury_after（DTO 局部快照对账）
            self.assertEqual(naval["charged"], naval["treasury_before"] - naval["treasury_after"])
            # naval_maintenance 结构化事件（type=naval_maintenance）
            maint_msgs = _naval_maintenance_events(handler)
            self.assertTrue(maint_msgs, "naval_maintenance event missing")

            # ── S10 Forum ──
            _forum_round(state)
            # ── S11/S12 Population：resolved war → decider 行政解散 2 艘（exactly once）──
            pop_data = _population_votes_and_resolve(state)
            disbanded_fleets = pop_data["disbandment"]["fleets"]
            self.assertEqual(sorted(disbanded_fleets), [1, 2])
            for num in (1, 2):
                self.assertEqual(ns.get_fleet(num).status, FleetStatus.DISBANDED)
            events = _fleet_disband_events(handler)
            # 舰队解散事件（reason=decider 由 population 入口产生）——每艘解散恰一条
            disband_msgs = [m for m in events if "type=naval_fleet_disbanded" in m]
            self.assertTrue(any("fleet_number=1" in m for m in disband_msgs))
            self.assertTrue(any("fleet_number=2" in m for m in disband_msgs))

            # ── S13/S14 Senate → S15/S16 combat/resolution/advance_year ──
            _senate_resolve_advance(state)
            _combat_resolution_advance_year(state)

            # ── S17 次年 Revenue：DISBANDED 排除 → 0 再费 ──
            rev2 = _mortality_revenue_round(state)
            naval2 = _revenue_naval_dto(rev2)
            self.assertEqual(naval2["total"], 0)
            self.assertEqual(naval2["charged"], 0)

            # ── S18 次年 Population：0 新退役事件 ──
            _forum_round(state)
            before_events = len(_fleet_disband_events(handler))
            pop2 = _population_votes_and_resolve(state)
            self.assertEqual(pop2["disbandment"]["fleets"], [])
            self.assertEqual(len(_fleet_disband_events(handler)), before_events)
            for num in (1, 2):
                self.assertEqual(ns.get_fleet(num).status, FleetStatus.DISBANDED)
        finally:
            handler.close()
            state.close_logging()

    def test_triumph_variant_fleets_available_and_maintenance_bearing(self):
        """T04 triumph 变体：recall 后 AVAILABLE 幸存者仍计费（战后 AVAILABLE 非免费状态）。"""
        state, war, _ = self._naval_chain_state(force_naval="TRIUMPH", force_land="triumph")
        ns = state._naval_system
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "triumph")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        for num in (1, 2):
            self.assertEqual(ns.get_fleet(num).status, FleetStatus.AVAILABLE)
        self.assertEqual(ns.calculate_maintenance(), 8)  # 2 × trireme 4（现场 type 复算）


class TestTr105NavalShortfallVariants(unittest.TestCase):
    """T-R3-05：短款解散累计算法 + 全变体 + DTO/event schema（SC-R3-04，FIX-R3-SHORT）。"""

    def _shortfall_state(self, fleet_specs, treasury):
        """fleet_specs: [(number, fleet_type, 'AVAILABLE'|'ON_MISSION'), ...]；
        维护费用 = 现场 fleet type 配置（trireme 4 / quinquereme 6），禁 hard-code 总额。
        已 mark mortality executed → revenue 为当前 phase（fixture bootstrap，同 R1 s3 先例）。"""
        state, faction = _build_state(treasury=treasury)
        state.mark_phase_executed("mortality")
        war = None
        commander = None
        if any(status == "ON_MISSION" for _n, _t, status in fleet_specs):
            commander = _add_commander(state, faction)
            war = _make_war(state, "naval_war", naval_required=True,
                            commander_id=commander.id, enemy_naval=10)
        for number, fleet_type, status in fleet_specs:
            fleet = _add_fleet(state, number, fleet_type=fleet_type,
                               target_war_id=war.id if war else None)
            if status == "ON_MISSION":
                assert war is not None
                _assign_fleet(state, fleet, war, commander_id=commander.id)
        return state, war

    def _due(self, state):
        return sum(
            f.get_maintenance_cost(state)
            for f in state._naval_system.get_all_fleets()
            if f.status not in (FleetStatus.DESTROYED, FleetStatus.BUILDING, FleetStatus.DISBANDED)
        )

    def test_exact_one_ship_short_disbands_one_and_pays_rest(self):
        """恰差一舰费用（旧 break-before-add 缺陷）：treasury = due − 1×trireme(4) →
        退役 1 艘（AVAILABLE 优先）→ 余费实扣；success（旧代码零解散 + 失败）。"""
        state, _war = self._shortfall_state(
            [(1, "trireme", "AVAILABLE"), (2, "trireme", "ON_MISSION"),
             (3, "quinquereme", "ON_MISSION")],
            treasury=14 - 4,  # due 14，差 1 艘 trireme 费用
        )
        ns = state._naval_system
        before = state.treasury
        handler = _enable_capture(state)
        try:
            service = EconomicService(state)
            dto = service.apply_naval_maintenance()
            after = state.treasury
            self.assertTrue(dto["success"], dto["message"])
            self.assertEqual(dto["available"], True)
            self.assertEqual(dto["total"], 14)
            self.assertEqual(dto["disbanded"], 1)
            self.assertEqual(dto["disbanded_fleet_ids"], [1])     # AVAILABLE 优先退役
            self.assertEqual(dto["required_after_disband"], 10)
            self.assertEqual(dto["charged"], before - after)
            self.assertEqual(dto["charged"], 10)
            self.assertEqual(dto["charged"], dto["treasury_before"] - dto["treasury_after"])
            self.assertEqual(dto["shortfall"], 0)
            self.assertEqual(dto["initial_shortfall"], 4)
            self.assertEqual(dto["unpaid"], 0)
            self.assertEqual(ns.get_fleet(1).status, FleetStatus.DISBANDED)
            self.assertEqual(ns.get_fleet(2).status, FleetStatus.ON_MISSION)
            self.assertEqual(ns.get_fleet(3).status, FleetStatus.ON_MISSION)
            self.assertEqual(self._due(state), 10)
            # fleet_costs 证据（status_before/unit_cost/target_war）
            self.assertEqual(dto["fleet_costs"][0]["fleet_number"], 1)
            self.assertEqual(dto["fleet_costs"][0]["unit_cost"], 4)
            self.assertEqual(dto["fleet_costs"][0]["status_before"], "available")
            # naval_maintenance event + naval_fleet_disbanded event（reason=treasury_shortfall）
            maint = _naval_maintenance_events(handler)
            self.assertTrue(maint)
            disbands = _fleet_disband_events(handler)
            self.assertEqual(len(disbands), 1)
            self.assertIn("fleet_number=1", disbands[0])
            self.assertIn("reason=treasury_shortfall", disbands[0])
            self.assertIn("fleet_status=disbanded", disbands[0])
        finally:
            handler.close()
            state.close_logging()

    def test_two_ships_accumulated_disband_and_war_index_cleared(self):
        """累计两舰才够付：due 14（4/4/6）、treasury 6 → 退役 AVAILABLE F1 + ON_MISSION F2，
        余 F3(6) 实扣；ON_MISSION 退役清 War assignment index + entity binding。"""
        state, war = self._shortfall_state(
            [(1, "trireme", "AVAILABLE"), (2, "trireme", "ON_MISSION"),
             (3, "quinquereme", "ON_MISSION")],
            treasury=6,
        )
        assert war is not None
        ns = state._naval_system
        before = state.treasury
        dto = EconomicService(state).apply_naval_maintenance()
        self.assertTrue(dto["success"], dto["message"])
        self.assertEqual(dto["disbanded"], 2)
        self.assertEqual(dto["disbanded_fleet_ids"], [1, 2])
        self.assertEqual(dto["required_after_disband"], 6)
        self.assertEqual(dto["charged"], before - state.treasury)
        self.assertEqual(dto["charged"], 6)
        self.assertEqual(ns.get_fleet(1).status, FleetStatus.DISBANDED)
        self.assertEqual(ns.get_fleet(2).status, FleetStatus.DISBANDED)
        self.assertEqual(ns.get_fleet(3).status, FleetStatus.ON_MISSION)
        self.assertEqual(war.assigned_fleet_ids, [3], "ON_MISSION 解散必须清 War assignment index")
        self.assertEqual(self._due(state), 6)

    def test_zero_treasury_disbands_all_pays_zero(self):
        """零国库：退役全部计费舰队 → 余费 0 → 支付 0 成功（不误报失败）。"""
        state, _war = self._shortfall_state(
            [(1, "trireme", "AVAILABLE"), (2, "quinquereme", "AVAILABLE")],
            treasury=0,
        )
        dto = EconomicService(state).apply_naval_maintenance()
        self.assertTrue(dto["success"], dto["message"])
        self.assertEqual(dto["disbanded"], 2)
        self.assertEqual(dto["required_after_disband"], 0)
        self.assertEqual(dto["charged"], 0)
        self.assertEqual(state.treasury, 0)

    def test_negative_treasury_failure_charge_zero(self):
        """已负国库（−3 < recompute 0）：退役全部后仍不足 → 既有失败策略（MVP0.5-04 §5.6）
        charge 0、国库不变、失败证据（不移植 military 可负国库强扣）。"""
        state, _war = self._shortfall_state(
            [(1, "trireme", "AVAILABLE"), (2, "quinquereme", "AVAILABLE")],
            treasury=-3,
        )
        before = state.treasury
        dto = EconomicService(state).apply_naval_maintenance()
        self.assertFalse(dto["success"])
        self.assertEqual(dto["disbanded"], 2)
        self.assertEqual(dto["charged"], 0)
        self.assertEqual(state.treasury, before)
        self.assertEqual(dto["required_after_disband"], 0)
        self.assertEqual(dto["unpaid"], 0)

    def test_on_mission_only_shortfall_now_disbands(self):
        """ON_MISSION-only 短款（旧候选仅 AVAILABLE → 零解散失败）：due 8（2×trireme ON_MISSION）、
        treasury 5 → 退役 F1（ON_MISSION，war index 清理）→ 余 F2 3 实扣 → success。"""
        state, war = self._shortfall_state(
            [(1, "trireme", "ON_MISSION"), (2, "trireme", "ON_MISSION")],
            treasury=5,
        )
        assert war is not None
        ns = state._naval_system
        before = state.treasury
        dto = EconomicService(state).apply_naval_maintenance()
        self.assertTrue(dto["success"], dto["message"])
        self.assertEqual(dto["disbanded"], 1)
        self.assertEqual(dto["disbanded_fleet_ids"], [1])
        self.assertEqual(dto["charged"], before - state.treasury)
        self.assertEqual(dto["charged"], 4)
        self.assertEqual(war.assigned_fleet_ids, [2])
        self.assertEqual(ns.get_fleet(1).status, FleetStatus.DISBANDED)
        self.assertEqual(ns.get_fleet(2).status, FleetStatus.ON_MISSION)

    def test_absent_naval_system_zero_shape(self):
        """naval system absent：完整零值 shape（available=False，全字段在位）。"""
        state, _faction = _build_state()
        state._naval_system = None
        dto = EconomicService(state).apply_naval_maintenance()
        self.assertFalse(dto["available"])
        for key in ("total", "charged", "shortfall", "initial_shortfall", "unpaid",
                    "disbanded", "required_after_disband", "treasury_before", "treasury_after"):
            self.assertEqual(dto[key], 0)
        self.assertEqual(dto["disbanded_fleet_ids"], [])
        self.assertEqual(dto["fleet_costs"], [])
        self.assertTrue(dto["success"])

    def test_normal_path_full_dto_via_revenue_api_and_qml_source(self):
        """足额支付路径：revenue_api 嵌套权威 DTO 位置 + charged 与国库局部变化一致；
        RevenueStage.qml naval 行窄改读 charged（源码绑定契约 DATA-source）。"""
        state, _war = self._shortfall_state(
            [(1, "trireme", "AVAILABLE"), (2, "quinquereme", "AVAILABLE")],
            treasury=500,
        )
        rev = revenue_api.execute_revenue_phase(state, "player_opt")
        self.assertTrue(rev["success"], rev.get("message"))
        naval = _revenue_naval_dto(rev)
        self.assertEqual(naval["available"], True)
        self.assertEqual(naval["total"], 10)          # 4 + 6
        self.assertEqual(naval["charged"], 10)
        self.assertEqual(naval["charged"], naval["treasury_before"] - naval["treasury_after"])
        self.assertEqual(naval["disbanded"], 0)
        self.assertEqual(naval["shortfall"], 0)
        # phase-result 镜像同值（RevenueStage 经 state.get_phase_result 读）
        phase_naval = state.get_phase_result("revenue")["data"]["maintenance"]["naval"]
        self.assertEqual(phase_naval["charged"], 10)
        # RevenueStage.qml 源码绑定契约（DATA-source）：显示值读 charged（禁虚报原应付 total）
        import os
        qml_path = os.path.join(os.path.dirname(__file__), "..", "..", "ui", "gui", "qml", "stages", "RevenueStage.qml")
        with open(qml_path, encoding="utf-8") as fh:
            qml_src = fh.read()
        naval_row_start = qml_src.find("舰队维护费")
        self.assertGreater(naval_row_start, 0)
        naval_row = qml_src[naval_row_start:naval_row_start + 900]
        self.assertIn("maintenance.naval.charged", naval_row)
        self.assertNotIn("maintenance.naval.total", naval_row.replace("naval.total_", ""))


class TestTr106ResolvedTargetWarRetire(unittest.TestCase):
    """T-R3-06：A resolved + B live 的多战退役窄修（AutoFleetDisbandDecider）——
    A 的 released AVAILABLE survivor 在 Population 退役，B 的 live Fleet 不被连坐。"""

    def _multi_war_state(self):
        state, faction = _build_state(treasury=300)
        state.mark_phase_executed("mortality")
        commander = _add_commander(state, faction, figure_id=102)
        # A：已 RESOLVED（discard），其专属 survivor 舰队 AVAILABLE
        war_a = _make_war(state, "war_a", naval_required=True, commander_id=commander.id,
                          status=WarStatus.RESOLVED, enemy_naval=10)
        fa = _add_fleet(state, 1, fleet_type="trireme", target_war_id=war_a.id)   # AVAILABLE
        # B：live ACTIVE naval war + 专属舰队 ON_MISSION
        war_b = _make_war(state, "war_b", naval_required=True, commander_id=commander.id, enemy_naval=10)
        fb = _add_fleet(state, 2, fleet_type="quinquereme", target_war_id=war_b.id)
        _assign_fleet(state, fb, war_b, commander_id=commander.id)
        return state, war_a, war_b, fa, fb

    def test_resolved_dedicated_fleet_retired_other_war_fleet_retained(self):
        state, war_a, war_b, fa, fb = self._multi_war_state()
        ns = state._naval_system
        # 旧行为：B 需海军 → 全局阻止退休 → A 舰被 B 保留（违规）；窄修后 A 舰先退役
        result = population_api.process_population_disbandments(state)
        self.assertIn(1, result["fleets"], "A(resolved) 专属 released AVAILABLE 必须退役")
        self.assertNotIn(2, result["fleets"], "B(live) 专属舰队不得连坐解散")
        self.assertEqual(ns.get_fleet(1).status, FleetStatus.DISBANDED)
        self.assertEqual(ns.get_fleet(2).status, FleetStatus.ON_MISSION)

        # Population exactly-once：重入返回缓存、零新 mutation
        again = population_api.process_population_disbandments(state)
        self.assertEqual(again["fleets"], result["fleets"])
        self.assertEqual(ns.get_fleet(1).status, FleetStatus.DISBANDED)
        self.assertEqual(ns.get_fleet(2).status, FleetStatus.ON_MISSION)

        # B 的 live Fleet 仍 maintenance-bearing（不能为总额归零连坐解散 A 之外舰队）
        self.assertEqual(ns.calculate_maintenance(), 6)   # 仅 FB quinquereme 6

    def test_revenue_after_retire_charges_only_b_fleet(self):
        """A 舰退役后 Revenue：A ids 零再费、B 舰仍计费恰一次。"""
        state, war_a, war_b, fa, fb = self._multi_war_state()
        population_api.process_population_disbandments(state)
        rev = revenue_api.execute_revenue_phase(state, "player_opt")
        self.assertTrue(rev["success"], rev.get("message"))
        naval = _revenue_naval_dto(rev)
        self.assertEqual(naval["total"], 6)               # 仅 B quinquereme
        self.assertEqual(naval["charged"], 6)
        self.assertEqual(naval["disbanded_fleet_ids"], [])
        # A ids 零再费（DISBANDED 排除）；B 仍计费
        self.assertEqual(state._naval_system.get_fleet(1).status, FleetStatus.DISBANDED)
        self.assertEqual(state._naval_system.get_fleet(2).status, FleetStatus.ON_MISSION)


if __name__ == "__main__":
    unittest.main()
