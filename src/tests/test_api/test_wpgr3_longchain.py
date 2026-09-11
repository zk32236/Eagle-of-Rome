# src/tests/test_api/test_wpgr3_longchain.py
"""WP-G-R3 S5 — 三集成形态链（FC / LC / TA）+ V-04 T19 joined trace + SC09 跨实体 roundtrip。

冻结设计：SA-Design-WP-G-R3-2026-09-05.md v1.2 §8.2（三链实际 phase 顺序）+ §10
T-R3-19 + §5.4（V04）+ §7.2（SC-R3-01/02/03）+ §9.3（evidence：同 run join key：
run_id/candidate_sha/turn/phase/viewer_id/contract_id/package_id/target_war_id/fleet_ids；
禁跨 run 拼接）。

Chain FC（SC-R3-02，三年 producer 链）：Y1 Forum PENDING A280 → Senate B350 →
Y2 bid C300+D240 → award 7 BUILDING（package_id=contract.id）→ Revenue（Y3）付款
C300/cost240/gross60/paid → Y3 Forum maturity → 7 ON_MISSION（nominal21/base18）→
Y3 Combat 受控骰子消费 effective 18（naval VICTORY 判别：旧 Σ21 会给 TRIUMPH）→ RESOLVED。
每年断言 Commander valid / required 谓词 / phase-result guard；全部真实 API producer，
禁手写 BUDGETED/strength。

Chain LC（SC-R3-03）：自 FC 成舰态 → canonical VICTORY（forced naval + land，同 R1 s1
canonical forced 路径）→ recall AVAILABLE → Revenue charged 恰一次（7×trireme4=28，
局部 charged=before−after）→ Forum → Population DISBANDED 恰一次 → 次年 Revenue 零再费
→ 次年 Population 零新事件；legions 只作参与者（不参与海军断言）。

Chain TA（SC-R3-01）：commanderless ACTIVE naval_required war + eligible human Consul →
get_senate_view required=true → propose_many([]) 合法（resolve/advance 拒）→ live Store
doTakeoverWar → canonical mutation/provenance/decision complete → 空结算收敛（真实 phase
result）→ doAdvanceSenate → 下一合法 phase Combat → doCombatAction 真实 naval 门
（无舰队 auto-DEFEAT 阻断，land override 不跨过）→ war ACTIVE + 新 Commander + 征召绑定。

V-04 T19（SC-R3-02 joined）：contract→BUILDING→mature→DTO（combat_api._war_card /
gui_query_api 对照 / api_adapter）→ SessionStore property → CombatStage QML 绑定契约
（DATA-source；RENDER_AUTOMATED 截图归 SO Work Order）；AVAILABLE global built 与
per-war readiness 区分 + fresh/new Store 同值。

SC09：同一 run 内 contract + fleet serializer roundtrip（id/package/A/B/C/D/nominal/q 无损）。
"""
import unittest
from unittest import mock

from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.contract import ContractStatus
from src.core.entities.fleet import FleetStatus
from src.api import combat_api, forum_api, game_api, gui_query_api, resolution_api, senate_api
from src.core.game_state import GameState
from src.core.systems.political_system import PoliticalSystem

import test_wpgr3_s3_fleet_economics as s3
import test_wpgr3_s4_nominal_effective as s4
import test_wpgr3_s1_takeover_convergence as s1

P1, P2 = "player_opt", "player_pop"


def _naval_dto(rev):
    """设计 §2.3：权威 DTO = execute_revenue_phase(...).data.data.maintenance.naval。"""
    return rev["data"]["data"]["maintenance"]["naval"]


def _store(state, viewer):
    from src.ui.gui.session_store import GuiSessionStore
    store = GuiSessionStore(state)
    store.initialize(viewer)
    return store


def _war_card(store, war_id):
    for card in store.combatAllWarCards:
        if card.get("war_id") == war_id:
            return card
    for card in store.combatActiveWars:
        if card.get("war_id") == war_id:
            return card
    return None


# ---------------------------------------------------------------------------
# Chain FC（SC-R3-02）
# ---------------------------------------------------------------------------

class TestLongChainFC(unittest.TestCase):
    """三年 producer 链：A280/B350/C300/D240/gross60 + maturity + combat 消费 18。"""

    def _drive_to_y3_maturity(self):
        state, ctx = s3._build_fleet_chain_state(enemy_naval=20)   # S3: valid commander martial 4
        war = ctx["war"]
        # Y1：Forum init → PENDING（A280, 7 trireme, target）→ Senate B350 → BUDGETED
        contract = s3.year1_approved_contract(state, ctx, modified_budget=350)
        assert contract._original_budget == 280 and contract.approved_budget == 350
        assert contract.status == ContractStatus.BUDGETED
        # Y2：bid C300 + D240 → award → 7 BUILDING（package_id = contract.id）
        s3._award_block(state, ctx, contract, amount=300, construction_cost=240)
        building = [f for f in state.naval_system.get_all_fleets() if f.is_building]
        assert len(building) == 7
        assert all(f._construction_package_id == contract.id for f in building)
        s3._finish_year_from_population(state, war.id)             # Y2 余段 → Y3
        # Y3：Revenue 付款（C300/cost240/gross60）→ Forum init → maturity 7 ON_MISSION
        rev = s3._mortality_revenue_round(state)
        rows = rev["data"]["data"]["contract_rows"]
        row = next(r for r in rows if r["contract_id"] == contract.id)
        assert row["payment"] == 300 and row["cost"] == 240 and (row["payment"] - row["cost"]) == 60
        assert contract.is_fleet_construction_paid
        g3 = s3._forum_init(state)
        assert len(g3["data"].get("completed_fleets", [])) == 7
        assert contract.status == ContractStatus.COMPLETED
        fleets = [f for f in state.naval_system.get_all_fleets() if f._target_war_id == war.id]
        assert all(f.status == FleetStatus.ON_MISSION for f in fleets)
        return state, ctx, contract, fleets

    def test_fc_chain_full_producer_and_combat_consumption(self):
        state, ctx, contract, fleets = self._drive_to_y3_maturity()
        war = ctx["war"]
        self.assertEqual(contract._original_budget, 280)   # A
        self.assertEqual(contract.approved_budget, 350)    # B
        self.assertEqual(contract.contract_price, 300)     # C
        self.assertEqual(contract._actual_cost, 240)       # D
        # 每年 Commander valid / required 谓词 / phase-result guard
        self.assertEqual(war.commander_id, 40)
        sv = senate_api.get_senate_view(state, P1)
        self.assertTrue(sv["success"])
        self.assertFalse(sv["data"]["takeover_required"]["required"])  # valid commander → 无强制接管
        self.assertTrue(state.get_phase_result("revenue"))

        # 读模型（combat 前）：assigned 7 / nominal21 / base18（martial→0 判别 modifiers 分列）
        state.get_member(40).martial = 0                   # §4.4 允许 modifier 变化（A/C 判别）
        view = combat_api.get_combat_view(state, P1)
        self.assertTrue(view["success"])
        card = next(w for w in view["data"]["active_wars"] if w["war_id"] == war.id)
        self.assertEqual(card["assigned_fleet_count"], 7)
        self.assertIs(card["naval_ready"], True)
        self.assertEqual(len(card["assigned_fleet_ids"]), 7)
        self.assertEqual(card["fleet_nominal_strength"], 21)
        self.assertEqual(card["fleet_quality_adjusted_base"], 18)
        self.assertEqual(card["fleet_effective_combat_strength"], 18)
        self.assertEqual(card["fleet_strength_packages"][0]["package_id"], contract.id)

        # Y3 余段（Forum advance → Population → Senate）→ Combat
        state.set_current_player(P1)
        s3._forum_resolve_advance(state)
        s3._population_round(state, 0)
        s3._senate_resolve_advance(state)
        state.set_current_player(P1)
        # 受控骰子（不 force 海战结果）：dice12 + 18 − 20 = 10 → naval VICTORY
        # （旧 per-fleet Σ21 → 13 → TRIUMPH，判别 effective 18 被 CRT 消费）
        with mock.patch("src.core.systems.naval_system.random.randint", return_value=12):
            state.config.testing.force_battle_result = "victory"   # land 仅结果控制（判别在 naval）
            act = combat_api.do_combat_action(state, P1, war.id, "attack")
        self.assertTrue(act["success"], act.get("message"))
        data = act["data"]
        self.assertEqual(data["naval"]["result"], "VICTORY", "18 消费判别失败（旧 Σ21 会 TRIUMPH）")
        self.assertTrue(data["naval"]["sea_control_acquired"])
        self.assertEqual(data["result"], "victory")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        # recall：survivors AVAILABLE + mission 清空（LC 链前置）
        for f in fleets:
            self.assertEqual(f.status, FleetStatus.AVAILABLE)
            self.assertIsNone(f.assigned_war_id)
        self.assertEqual(war.assigned_fleet_ids, [])


# ---------------------------------------------------------------------------
# Chain LC（SC-R3-03）
# ---------------------------------------------------------------------------

class TestLongChainLC(unittest.TestCase):
    """SC02 成舰 → canonical VICTORY → recall → Revenue charged once → Population
    DISBANDED once → 次年零再费 / 零新事件。"""

    def test_lc_chain_charge_once_disband_once_zero_next_year(self):
        state, ctx, contract, fleets = s4._canonical_mature()   # Y3 forum init（martial0）
        war = ctx["war"]
        ns = state.naval_system
        fleet_ids = sorted(f.number for f in fleets)
        self.assertEqual(len(fleet_ids), 7)

        # 参与者 legions（production shape：land battle 有真实附着；不参与海军断言）
        ms = state._military_system
        for num in (1, 2):
            ok, _ = ms.recruit_legion(num)
            self.assertTrue(ok, f"recruit legion {num}")
        assigned, msg = ms.assign_to_war([1, 2], war.id, 40)
        self.assertEqual(assigned, 2, msg)

        # Y3 余段 → Combat（canonical forced VICTORY → RESOLVED；R1 s1 canonical forced 路径）
        s4._forum_resolve_advance(state)
        s4._population_round(state, 0)
        s4._senate_resolve_advance(state)
        state.set_current_player(P1)
        state.config.testing.force_naval_result = "VICTORY"
        state.config.testing.force_battle_result = "victory"
        act = combat_api.do_combat_action(state, P1, war.id, "attack")
        self.assertTrue(act["success"], act.get("message"))
        self.assertEqual(act["data"]["result"], "victory")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        # recall survivors → AVAILABLE + mission 清空；DESTROYED 不复活
        for f in fleets:
            self.assertEqual(f.status, FleetStatus.AVAILABLE)
            self.assertIsNone(f.assigned_war_id)
        self.assertEqual(war.assigned_fleet_ids, [])
        self.assertTrue(combat_api.confirm_battle_result(state, P1)["success"])
        self.assertTrue(combat_api.advance_combat(state, P1)["success"])
        res = resolution_api.execute_resolution(state)
        self.assertTrue(res["success"], res.get("message"))
        ay = game_api.advance_year(state, P1)
        self.assertTrue(ay["success"], ay.get("message"))

        # Y4 Revenue：naval charged 恰一次 = 7 × trireme4 = 28（局部 before−after 对账）
        rev = s4._mortality_revenue_round(state)
        naval = _naval_dto(rev)
        self.assertEqual(naval["total"], 28)
        self.assertEqual(naval["charged"], 28)
        self.assertEqual(naval["charged"], naval["treasury_before"] - naval["treasury_after"])
        self.assertEqual(naval["disbanded"], 0)

        # Y4 Forum → Population：同批 ids DISBANDED 恰一次
        s4._forum_init(state)
        s4._forum_resolve_advance(state)
        pop = s4._population_round(state, 0)
        disbanded = sorted(pop["disbandment"]["fleets"])
        self.assertEqual(disbanded, fleet_ids)
        for num in fleet_ids:
            self.assertEqual(ns.get_fleet(num).status, FleetStatus.DISBANDED)

        # Y4 Senate → Combat（无 ACTIVE war）→ advance_year → Y5
        s4._senate_resolve_advance(state)
        self.assertTrue(combat_api.advance_combat(state, P1)["success"])
        self.assertTrue(resolution_api.execute_resolution(state)["success"])
        self.assertTrue(game_api.advance_year(state, P1)["success"])

        # Y5 Revenue：DISBANDED 排除 → 零再费
        rev2 = s4._mortality_revenue_round(state)
        naval2 = _naval_dto(rev2)
        self.assertEqual(naval2["total"], 0)
        self.assertEqual(naval2["charged"], 0)
        self.assertEqual(naval2["disbanded_fleet_ids"], [])

        # Y5 Population：零新退役事件
        s4._forum_init(state)
        s4._forum_resolve_advance(state)
        pop2 = s4._population_round(state, 0)
        self.assertEqual(pop2["disbandment"]["fleets"], [])
        for num in fleet_ids:
            self.assertEqual(ns.get_fleet(num).status, FleetStatus.DISBANDED)


# ---------------------------------------------------------------------------
# Chain TA（SC-R3-01）
# ---------------------------------------------------------------------------

class TestLongChainTA(unittest.TestCase):
    """commanderless ACTIVE naval_required war → human Takeover → phase convergence →
    下一合法 phase Combat（真实 naval 门）。"""

    def _ta_state(self):
        state, consul, _old_war = s1._real_player_state()
        # 置换为 commanderless ACTIVE naval-required war（TA 链 Combat 面有真实 naval 门）
        state._war_system._active_wars = []
        war = War(
            id="war_naval_ta", name="Commanderless Naval War", war_type=WarType.FOREIGN,
            strength=5, threat_level=3, naval_required=True,
            enemy_naval_current=20, enemy_naval_max=20,
            disaster_numbers=[2, 3, 4], standoff_numbers=[99],
        )
        war.status = WarStatus.ACTIVE          # commanderless
        state._war_system._active_wars.append(war)
        return state, consul, war

    def test_ta_chain_takeover_converge_advance_to_combat(self):
        state, consul, war = self._ta_state()
        store = _store(state, s1.P1)
        view = store.senateView
        self.assertTrue(view["takeover_required"]["required"])

        # 空批合法但 resolve/advance 拒绝（mandatory 不可跳过）
        empty = senate_api.propose_many(state, s1.P1, [])
        self.assertTrue(empty["success"])
        refused = senate_api.resolve_senate(state)
        self.assertFalse(refused["success"])
        self.assertFalse(senate_api.advance_senate_phase(state, s1.P1)["success"])
        self.assertEqual(war.status, WarStatus.ACTIVE)

        # live Store doTakeoverWar（R4 supersede，OD-R4-05/06）：Submit/lock 锁 T 零部署
        calls = {"n": 0}
        original = PoliticalSystem.execute_war_takeover_deploy

        def counting(self_, war_, consul_, reinforcement_n=None):
            calls["n"] += 1
            return original(self_, war_, consul_, reinforcement_n=reinforcement_n)

        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting):
            fb = store.doTakeoverWar(war.id, 1)
        self.assertTrue(fb["success"], fb.get("message"))
        self.assertEqual(calls["n"], 0, "Submit 零部署")
        self.assertEqual(state.get_takeover_pending()["status"], "LOCKED")
        self.assertFalse(state.get_phase_result("senate"), "无隐式结算")
        self.assertIsNone(war.commander_id)
        self.assertFalse(consul.is_absent, "R4-17：执政官留城")

        # 重复 takeover 请求 no-op（LOCKED 后重复 submit 拒绝，零新增 mutation）
        repeat = store.doTakeoverWar(war.id, 1)
        self.assertFalse(repeat["success"])

        # 显式空结束 + settlement 恢复 → R 真实 → doAdvanceSenate 部署恰一次 → combat
        self.assertTrue(store.doSubmitSenateProposals([])["success"])
        recovery = store.doResolveSenateSettlement()
        self.assertTrue(recovery["success"], recovery.get("message"))
        self.assertTrue(state.get_phase_result("senate"))
        with mock.patch.object(PoliticalSystem, "execute_war_takeover_deploy", counting):
            adv = store.doAdvanceSenate()
        self.assertTrue(adv["success"], adv.get("message"))
        self.assertEqual(calls["n"], 1, "部署恰一次（advance 唯一 owner）")
        self.assertTrue(state.is_phase_executed("senate"))
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(consul.is_absent)

        # Combat 真实 naval 门（R4 supersede）：无 ready 舰队 = NAVAL_NOT_READY（非自动 DEFEAT）
        state.set_current_player(s1.P1)
        state.config.testing.force_battle_result = "victory"   # land override 不得跨过 readiness
        state.config.testing.force_naval_result = "TRIUMPH"     # naval override 也不穿透 readiness
        act = combat_api.do_combat_action(state, s1.P1, war.id, "attack")
        self.assertFalse(act["success"])
        self.assertEqual(act["data"]["code"], "NAVAL_NOT_READY")
        self.assertEqual(war.status, WarStatus.ACTIVE)         # war 保持 ACTIVE + 新 Commander
        self.assertEqual(war.commander_id, consul.id)
        self.assertTrue(consul.is_absent)


# ---------------------------------------------------------------------------
# V-04 T19：joined trace（Core→DTO→Store→CombatStage）+ AVAILABLE/per-war 区分
# ---------------------------------------------------------------------------

class TestR3V04JoinedTrace(unittest.TestCase):
    """contract→BUILDING→mature→API/DTO→Adapter→Store property→QML 绑定契约（DATA）；同 ID
    join：contract_id/package_id/target_war_id/fleet_ids。GUI 可见层 = 源码绑定契约（DATA-
    source），RENDER_AUTOMATED 截图归 SO Work Order。"""

    def _building_state(self):
        state, ctx = s4._build_fleet_chain_state()
        contract = s4.year1_approved_contract(state, ctx, modified_budget=350)
        s4._award_building(state, ctx, contract, amount=300, construction_cost=240)
        fleets = [f for f in state.naval_system.get_all_fleets() if f.is_building]
        assert len(fleets) == 7
        return state, ctx, contract, fleets

    def test_t19_building_to_visible_joined_identity(self):
        """BUILDING：global built=0 / per-war assigned=0 / ready=false；DTO+Store 同源。"""
        state, ctx, contract, fleets = self._building_state()
        war = ctx["war"]
        state.set_current_player(P1)
        view = combat_api.get_combat_view(state, P1)
        card = next(w for w in view["data"]["active_wars"] if w["war_id"] == war.id)
        self.assertEqual(card["assigned_fleet_count"], 0)
        self.assertIs(card["naval_ready"], False)
        self.assertEqual(card["assigned_fleet_ids"], [])
        self.assertEqual(view["data"]["built_fleet_count"], 0)   # BUILDING 排除（R1-G-08 语义）
        store = _store(state, P1)
        self.assertEqual(store.combatFleetCount, 0)
        scard = _war_card(store, war.id)
        self.assertIsNotNone(scard, store.combatAllWarCards)
        self.assertEqual(scard["assigned_fleet_count"], 0)
        self.assertIs(scard["naval_ready"], False)
        # join：BUILDING fleets 持 contract_id/package_id/target（物化中）
        f0 = fleets[0]
        self.assertEqual(f0._construction_package_id, contract.id)
        self.assertEqual(f0._target_war_id, war.id)

    def test_t19_mature_dto_adapter_store_and_qml_binding(self):
        """mature：Core→DTO→Adapter→Store→QML 绑定契约同 ID join；nominal21/base18；
        fresh/new Store 同值。"""
        state, ctx, contract, fleets = s4._canonical_mature()
        war = ctx["war"]
        state.set_current_player(P1)
        fleet_ids = sorted(f.number for f in fleets)
        self.assertEqual(len(fleet_ids), 7)
        self.assertTrue(all(f.status == FleetStatus.ON_MISSION for f in fleets))

        # Core join：package_id 保留（complete_building 清 _contract_id 但 package 身份保留）
        f0 = fleets[0]
        self.assertIsNone(f0.contract_id)
        self.assertEqual(f0._construction_package_id, contract.id)
        self.assertEqual(f0._construction_quality_numerator, 240)
        self.assertEqual(f0._construction_quality_denominator, 280)

        # DTO（combat_api）→ gui_query 对照
        view = combat_api.get_combat_view(state, P1)
        card = next(w for w in view["data"]["active_wars"] if w["war_id"] == war.id)
        self.assertEqual(sorted(card["assigned_fleet_ids"]), fleet_ids)
        self.assertEqual(card["assigned_fleet_count"], 7)
        self.assertIs(card["naval_ready"], True)
        self.assertEqual(card["fleet_nominal_strength"], 21)
        self.assertEqual(card["fleet_quality_adjusted_base"], 18)
        self.assertEqual(card["fleet_effective_combat_strength"], 18)
        self.assertEqual(card["fleet_strength_packages"][0]["package_id"], contract.id)
        q = gui_query_api.get_global_query_result(state, P1, "war_list")
        qentry = next(e for e in q["data"]["summary"]["wars"] if e["id"] == war.id)
        self.assertEqual(sorted(qentry.get("assigned_fleet_ids", [])), fleet_ids)

        # Adapter
        from src.ui.gui.api_adapter import GuiApiAdapter
        adapter = GuiApiAdapter(state)
        acard = next(w for w in adapter.get_combat_view(P1).get("active_wars", [])
                     if w["war_id"] == war.id)
        self.assertEqual(sorted(acard["assigned_fleet_ids"]), fleet_ids)
        self.assertEqual(acard["fleet_effective_combat_strength"], 18)

        # Store property（同一实例 fresh refresh）
        store = _store(state, P1)
        self.assertEqual(store.combatFleetCount, 7)
        scard = _war_card(store, war.id)
        self.assertIsNotNone(scard)
        self.assertEqual(sorted(scard["assigned_fleet_ids"]), fleet_ids)
        self.assertEqual(scard["fleet_nominal_strength"], 21)
        self.assertEqual(scard["fleet_quality_adjusted_base"], 18)
        self.assertEqual(scard["fleet_effective_combat_strength"], 18)
        # new Store 同值
        store2 = _store(state, P1)
        self.assertEqual(store2.combatFleetCount, 7)
        self.assertEqual(sorted(_war_card(store2, war.id)["assigned_fleet_ids"]), fleet_ids)

        # CombatStage.qml 绑定契约（DATA-source：visible 层 join 断言点；渲染归 SO）
        import os
        qml_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "src", "ui", "gui", "qml", "stages", "CombatStage.qml",
        )
        with open(qml_path, "r", encoding="utf-8") as _f:
            qml_src = _f.read()
        self.assertIn("assigned_fleet_count", qml_src)
        self.assertIn("naval_ready", qml_src)
        self.assertIn("fleet_nominal_strength", qml_src)
        self.assertIn("fleet_quality_adjusted_base", qml_src)
        self.assertIn("fleet_effective_combat_strength", qml_src)

    def test_t19_available_global_vs_per_war_readiness(self):
        """AVAILABLE（已结束战召回）≠ per-war ready：global built 7、无 ACTIVE war 声称
        ready；resolved war card assigned 0/ready false；Store 两实例同值。"""
        state, ctx, contract, fleets = s4._canonical_mature()
        war = ctx["war"]
        state.set_current_player(P1)
        state.config.testing.force_naval_result = "VICTORY"
        state.config.testing.force_battle_result = "victory"
        act = combat_api.do_combat_action(state, P1, war.id, "attack")
        self.assertTrue(act["success"])
        self.assertEqual(war.status, WarStatus.RESOLVED)
        for f in fleets:
            self.assertEqual(f.status, FleetStatus.AVAILABLE)   # recall 后 AVAILABLE
        view = combat_api.get_combat_view(state, P1)
        self.assertEqual(view["data"]["built_fleet_count"], 7)  # AVAILABLE 计入全局
        self.assertEqual([w for w in view["data"]["active_wars"] if w["war_id"] == war.id], [])
        store = _store(state, P1)
        self.assertEqual(store.combatFleetCount, 7)
        # resolved war card：per-war assigned 0 / ready false（AVAILABLE global 不解读为 ready）
        rcard = _war_card(store, war.id)
        if rcard is not None:
            self.assertEqual(rcard.get("assigned_fleet_count", 0), 0)
            self.assertIsNot(rcard.get("naval_ready"), True)
        store2 = _store(state, P1)
        self.assertEqual(store2.combatFleetCount, 7)


# ---------------------------------------------------------------------------
# SC09：跨实体 roundtrip（contract + fleet，同 run id join）
# ---------------------------------------------------------------------------

class TestR3SC09JoinedRoundtrip(unittest.TestCase):
    def test_contract_and_fleet_roundtrip_same_ids(self):
        """contract A/B/C/D + fleet nominal/q/package 跨实体 roundtrip 完全相等（同一
        contract/package/target/fleet ids 贯穿）。"""
        from src.core.entities.contract import Contract as ContractEntity
        from src.core.entities.fleet import Fleet as FleetEntity
        state, ctx, contract, fleets = s4._canonical_mature()
        # contract side
        d = contract.to_dict()
        rt_c = ContractEntity.from_dict(d)
        self.assertEqual(rt_c.id, contract.id)
        self.assertEqual(rt_c._original_budget, 280)
        self.assertEqual(rt_c.approved_budget, 350)
        self.assertEqual(rt_c.contract_price, 300)
        self.assertEqual(rt_c._actual_cost, 240)
        self.assertEqual(rt_c._target_war_id, contract._target_war_id)
        self.assertEqual(rt_c._fleet_nominal_snapshot, contract._fleet_nominal_snapshot)
        # fleet side（fleet_configs 上下文提供 nominal 快照来源）
        fleet_configs = state.config.get("economic_rules.fleet_types", {})
        for f in fleets[:3]:
            fd = f.to_dict()
            rt_f = FleetEntity.from_dict(fd, fleet_configs=fleet_configs)
            self.assertEqual(rt_f.number, f.number)
            self.assertEqual(rt_f._construction_package_id, f._construction_package_id)
            self.assertEqual(rt_f._construction_package_id, contract.id)
            self.assertEqual(rt_f._construction_quality_numerator, f._construction_quality_numerator)
            self.assertEqual(rt_f._construction_quality_denominator, f._construction_quality_denominator)
            self.assertEqual(rt_f._nominal_strength_base, f._nominal_strength_base)
            self.assertEqual(rt_f._target_war_id, f._target_war_id)


if __name__ == "__main__":
    unittest.main(module=__name__, argv=["__main__", "-v"], exit=False)
