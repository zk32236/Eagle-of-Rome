# src/tests/test_api/test_wpgr1_s1_forced_combat.py
"""WP-G-R1 S1（R1-G-01）— Canonical Forced-Combat-Result Test Control 生产链测试。

冻结设计：SA-Design-WP-G-R1 v1.6 §2.1 / §3 T-R1-01 / T-R1-01n / T-R1-02（S1 独占）。

覆盖：
- T-R1-01  forced land 五结果参数化矩阵 via canonical GUI/API combat（do_combat_action
           attack → `_compute_combat_result` 消费 testing.force_battle_result → 真实
           post-result mutation 四分支：TRUCE+pending / RESOLVED / RESOLVED+triumph /
           ACTIVE+ceil(N/2) / ACTIVE+全灭）
- T-R1-01n forced Naval STALEMATE/DEFEAT/VICTORY/TRIUMPH via canonical naval gate
           （do_combat_action → resolve_naval_battle 消费 testing.force_naval_result；
           走真实 mutation path，禁 Mock/Monkeypatch 结果）
- T-R1-02  empty/absent/非法 override preserves normal random（land+naval，fail-closed）

红线核对：R1-01 单点 wiring / R1-03 Core 层（非 QML-only）/ R1-04 无第二 resolver /
R1-09 无生产默认 STALEMATE（空/非法 → 正常随机）。
"""
import unittest
from unittest.mock import patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.api import combat_api

_WAR_REWARDS = {"treasury": 100, "land": 0, "family_prestige": 0}


def _base_state(with_naval=False):
    """WP-G-R1 S1 fixture：ACTIVE land war + commander + live 军团（canonical 战力源）。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    for ph in ["mortality", "revenue", "forum", "population", "senate"]:
        state.mark_phase_executed(ph)
    state._treasury = 500
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    if with_naval:
        state._naval_system = NavalSystem(state)

    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)
    commander = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
    commander.martial = 6
    commander.influence = 10
    commander.office = "consul"
    commander.is_absent = True
    state.add_member(commander)
    faction.member_ids.append(1)

    player = Player(player_id="player_opt", faction_id="optimates", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")
    return state, faction, commander


def _make_land_war(state, war_id="war_land", strength=5, n_legions=2):
    war = War(
        id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
        strength=strength, threat_level=3, rewards=dict(_WAR_REWARDS),
        naval_required=False, disaster_numbers=[2, 3], standoff_numbers=[99],
    )
    war.commander_id = 1
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)
    ms = state._military_system
    for num in range(1, n_legions + 1):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num}"
    assigned, msg = ms.assign_to_war(list(range(1, n_legions + 1)), war_id, 1)
    assert assigned == n_legions, msg
    return war


def _make_naval_war(state, war_id="war_naval", enemy_naval=0, n_fleets=2, strength=5):
    war = War(
        id=war_id, name=f"Naval {war_id}", war_type=WarType.FOREIGN,
        strength=strength, threat_level=3, rewards=dict(_WAR_REWARDS),
        naval_required=True, enemy_naval_current=enemy_naval,
        disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.commander_id = 1
    war.status = WarStatus.ACTIVE
    state._war_system._active_wars.append(war)
    ns = state._naval_system
    for n in range(1, n_fleets + 1):
        fleet = Fleet(number=n, fleet_type="trireme")
        fleet._strength_base = 3
        fleet._target_war_id = war.id
        fleet._status = FleetStatus.AVAILABLE
        ns._fleets[n] = fleet
        ok = ns.assign_fleet_to_war(n, war.id, "naval")
        assert ok, f"assign fleet {n}"
    ms = state._military_system
    for num in (1, 2):
        ok, _ = ms.recruit_legion(num)
        assert ok, f"recruit legion {num}"
    assigned, msg = ms.assign_to_war([1, 2], war_id, 1)
    assert assigned == 2, msg
    return war


def _naval_state(enemy_naval=0, n_fleets=2):
    """ACTIVE naval_required war + 可用舰队（ON_MISSION 已指派）+ land legions。"""
    state, _faction, _commander = _base_state(with_naval=True)
    war = _make_naval_war(state, enemy_naval=enemy_naval, n_fleets=n_fleets)
    return state, war


class TestTr101ForcedLandMatrix(unittest.TestCase):
    """T-R1-01：forced land 五结果参数化矩阵（canonical do_combat_action 生产链）。"""

    def _run(self, forced, n_legions=2):
        state, _faction, _commander = _base_state()
        state.config.testing.force_battle_result = forced
        war = _make_land_war(state, n_legions=n_legions)
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"], result.get("message"))
        return state, war, result["data"]

    def test_stalemate_draw_goes_truce_pending_treaty(self):
        """stalemate → draw → TRUCE + pending treaty；commander 保留；无伤亡。"""
        state, war, data = self._run("stalemate")
        self.assertEqual(data["result"], "draw")
        self.assertFalse(data["triumph"])
        self.assertEqual(data["losses"], 0)
        # post-result mutation：_generate_peace_treaty → TRUCE + pending（四分支 draw）
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIn(war, state._war_system._truce_wars)
        self.assertNotIn(war, state._war_system._war_discard)
        self.assertIsNotNone(war.peace_treaty)
        self.assertEqual(war.peace_treaty.get("status"), "pending")
        self.assertEqual(war.commander_id, 1)  # commander 保留

    def test_victory_resolves_war(self):
        """victory → RESOLVED + discard；幸存者 recall → AVAILABLE。"""
        state, war, data = self._run("victory")
        self.assertEqual(data["result"], "victory")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        self.assertIn(war, state._war_system._war_discard)
        self.assertNotIn(war, state._war_system._truce_wars)
        for num in (1, 2):
            self.assertEqual(
                state._military_system.get_legion_by_number(num).status,
                LegionStatus.AVAILABLE,
            )

    def test_triumph_resolves_with_bonus_loot(self):
        """triumph → RESOLVED；triumph=True；loot == int(rewards.treasury * 1.5)。"""
        state, war, data = self._run("triumph")
        self.assertEqual(data["result"], "triumph")
        self.assertTrue(data["triumph"])
        self.assertEqual(data["loot"], int(100 * 1.5))
        self.assertEqual(war.status, WarStatus.RESOLVED)

    def test_defeat_keeps_active_ceil_half_casualties(self):
        """defeat → ACTIVE 保持；伤亡 == ceil(N/2)（N=2 → 1 个 DESTROYED）；duration+1。"""
        state, war, data = self._run("defeat")
        self.assertEqual(data["result"], "defeat")
        self.assertEqual(data["losses"], 1)  # ceil(2/2)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertNotIn(war, state._war_system._war_discard)
        self.assertNotIn(war, state._war_system._truce_wars)
        destroyed = [l for l in state._military_system.get_all_legions()
                     if l.status == LegionStatus.DESTROYED]
        self.assertEqual(len(destroyed), 1)
        self.assertEqual(war.duration, 1)
        self.assertIsNone(war.commander_id)  # consequence：指挥官离开战场

    def test_disaster_keeps_active_total_annihilation(self):
        """disaster → ACTIVE 保持；全灭（N=2 → 2 个 DESTROYED）；指挥官阵亡。"""
        state, war, data = self._run("disaster")
        self.assertEqual(data["result"], "disaster")
        self.assertEqual(data["losses"], 2)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        destroyed = [l for l in state._military_system.get_all_legions()
                     if l.status == LegionStatus.DESTROYED]
        self.assertEqual(len(destroyed), 2)
        self.assertEqual(war.duration, 1)
        self.assertIsNone(war.commander_id)
        self.assertTrue(state.get_member(1).is_dead)

    def test_case_and_space_tolerance(self):
        """大小写/空格容忍：'STALEMATE' / ' Victory ' 均可命中词表。"""
        for raw, expected in (("STALEMATE", "draw"), (" Victory ", "victory"),
                              ("TRIUMPH", "triumph"), ("  defeat", "defeat")):
            state, war, data = self._run(raw)
            self.assertEqual(data["result"], expected, raw)
            if expected == "draw":
                self.assertEqual(war.status, WarStatus.TRUCE)
            elif expected in ("victory", "triumph"):
                self.assertEqual(war.status, WarStatus.RESOLVED)


class TestTr101nForcedNavalMatrix(unittest.TestCase):
    """T-R1-01n：forced Naval STALEMATE/DEFEAT/VICTORY/TRIUMPH via canonical naval gate。"""

    def _state_with_naval(self, enemy_naval=0, n_fleets=2):
        return _naval_state(enemy_naval=enemy_naval, n_fleets=n_fleets)

    def test_naval_stalemate_blocks_land(self):
        """STALEMATE → naval block DTO（land 未执行）；war ACTIVE；duration+1；零海损。"""
        state, war = self._state_with_naval()
        state.config.testing.force_naval_result = "STALEMATE"
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["land_battle"], "blocked")
        self.assertEqual(data["naval"]["result"], "STALEMATE")
        self.assertEqual(data["naval"]["roman_losses"], 0)
        self.assertFalse(war.sea_control_acquired)
        self.assertEqual(war.status, WarStatus.ACTIVE)  # land 未执行 → 不结束
        self.assertEqual(war.duration, 1)
        # 本回合已处理 → resolved_wars 标记（不阻塞 advance）
        phase = state.get_phase_result("combat") or {}
        self.assertIn(war.id, phase.get("resolved_wars", []))

    def test_naval_defeat_blocks_land_with_losses(self):
        """DEFEAT → 阻断陆战 + roman_losses>0（ceil(N/2) = 1/2 艘 DESTROYED）。"""
        state, war = self._state_with_naval(n_fleets=2)
        state.config.testing.force_naval_result = "DEFEAT"
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["land_battle"], "blocked")
        self.assertEqual(data["naval"]["result"], "DEFEAT")
        self.assertEqual(data["naval"]["roman_losses"], 1)  # ceil(2/2)
        self.assertEqual(war.status, WarStatus.ACTIVE)
        destroyed = [f for f in state._naval_system.get_all_fleets()
                     if f.status == FleetStatus.DESTROYED]
        self.assertEqual(len(destroyed), 1)

    def test_naval_victory_continues_land(self):
        """VICTORY → 获控 → 同场继续陆战（forced land victory → RESOLVED）。

        注：战争正式结束（resolve_war）会清理制海权（K 件 §3 / D-1）——获控证据读
        同场 battle DTO 的 naval.sea_control_acquired（True），非战后 war 字段。
        """
        state, war = self._state_with_naval()
        state.config.testing.force_naval_result = "VICTORY"
        state.config.testing.force_battle_result = "victory"
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["naval"]["result"], "VICTORY")
        self.assertTrue(data["naval"]["sea_control_acquired"])  # 获控发生在同场（未清前）
        self.assertEqual(data["land_battle"], "allowed")
        self.assertEqual(war.status, WarStatus.RESOLVED)  # land victory → war ends
        self.assertFalse(war.sea_control_acquired)  # resolve_war 清理（K 件 §3 / D-1）

    def test_naval_triumph_continues_land(self):
        """TRIUMPH → 获控 → 同场继续陆战。"""
        state, war = self._state_with_naval()
        state.config.testing.force_naval_result = "TRIUMPH"
        state.config.testing.force_battle_result = "victory"
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["naval"]["result"], "TRIUMPH")
        self.assertTrue(data["naval"]["sea_control_acquired"])
        self.assertEqual(data["land_battle"], "allowed")
        self.assertEqual(war.status, WarStatus.RESOLVED)
        self.assertFalse(war.sea_control_acquired)

    def test_no_fleet_auto_defeat_not_overridden(self):
        """无可用舰队 → 既有「自动 DEFEAT」分支强制生效（override 不覆盖「无舰队必败」）。"""
        state, _faction, _commander = _base_state(with_naval=True)
        # 不指派任何舰队 → roman_fleets 为空
        war = War(
            id="war_nofleet", name="No Fleet War", war_type=WarType.FOREIGN,
            strength=5, threat_level=3, rewards=dict(_WAR_REWARDS),
            naval_required=True, enemy_naval_current=20,
            disaster_numbers=[2, 3, 4], standoff_numbers=[99],
        )
        war.commander_id = 1
        war.status = WarStatus.ACTIVE
        state._war_system._active_wars.append(war)
        state.config.testing.force_naval_result = "TRIUMPH"  # override 不覆盖
        result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["naval"]["result"], "DEFEAT")
        self.assertEqual(data["naval"]["roman_losses"], 0)
        self.assertEqual(data["land_battle"], "blocked")


class TestTr102EmptyPreservesRandom(unittest.TestCase):
    """T-R1-02：empty/absent/非法 override → 正常 2d6 CRT 分类（fail-closed，无 forced 分支副作用）。"""

    def test_land_empty_override_preserves_crt(self):
        """land：force_battle_result=''（默认空）→ dice 受控时结果由 CRT 决定。"""
        state, _faction, _commander = _base_state()
        state.config.testing.force_battle_result = ""
        war = _make_land_war(state, strength=30)  # 高敌力：即便 dice 高仍 defeat/disaster
        # dice=2 ∈ disaster_numbers[2,3] → disaster（CRT 灾难判定，与 forced 无关）
        with unittest.mock.patch.object(combat_api.random, "randint", return_value=2):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "disaster")
        self.assertEqual(war.status, WarStatus.ACTIVE)
        # dice=2 → all attached destroyed（disaster 全灭）
        destroyed = [l for l in state._military_system.get_all_legions()
                     if l.status == LegionStatus.DESTROYED]
        self.assertEqual(len(destroyed), 2)

    def test_land_absent_key_preserves_crt(self):
        """land：配置键缺省（默认 ""）→ 与空串同语义。"""
        state, _faction, _commander = _base_state()
        war = _make_land_war(state, strength=0)  # 低敌力 → victory 可达
        with unittest.mock.patch.object(combat_api.random, "randint", return_value=7):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        # 无 override：7+martial6+legion4 = 17 → score>=12 → triumph（CRT，非恒 forced）
        self.assertEqual(result["data"]["result"], "triumph")
        self.assertEqual(war.status, WarStatus.RESOLVED)

    def test_land_invalid_value_preserves_crt(self):
        """land：非法值（'banana'）→ None → 正常随机，不报错、不落 STALEMATE 默认。"""
        state, _faction, _commander = _base_state()
        state.config.testing.force_battle_result = "banana"
        war = _make_land_war(state, strength=30)
        with unittest.mock.patch.object(combat_api.random, "randint", return_value=5):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        # dice=5 非 standoff(99) 且 score = 5+6+4-30 = -15 < -3 → defeat（CRT，非 forced）
        self.assertEqual(result["data"]["result"], "defeat")
        self.assertEqual(war.status, WarStatus.ACTIVE)

    def test_naval_empty_override_preserves_crt(self):
        """naval：force_naval_result='' → 真实骰子路径；受控 dice=12 → 强舰队 TRIUMPH 获控。"""
        state, war = _naval_state(enemy_naval=0, n_fleets=3)
        state.config.testing.force_naval_result = ""
        state.config.testing.force_battle_result = "victory"
        with unittest.mock.patch.object(combat_api.random, "randint", side_effect=[12, 7]):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        data = result["data"]
        # CRT：dice12 + 3×3 − 0 = 21 ≥ 12 → TRIUMPH（naval 未 forced 也能达 TRIUMPH）
        self.assertEqual(data["naval"]["result"], "TRIUMPH")
        # 获控证据读同场 battle DTO（战后 resolve_war 清理制海权，K 件 §3 / D-1）
        self.assertTrue(data["naval"]["sea_control_acquired"])
        self.assertEqual(war.status, WarStatus.RESOLVED)

    def test_naval_absent_key_preserves_crt(self):
        """naval：force_naval_result 缺省 → 同空串（naval gate 走正常随机路径）。"""
        state, war = _naval_state(enemy_naval=0, n_fleets=1)
        state.config.testing.force_battle_result = "victory"
        with unittest.mock.patch.object(combat_api.random, "randint", side_effect=[2, 7]):
            result = combat_api.do_combat_action(state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        # dice=2 ∈ disaster_numbers → naval DISASTER → 阻断陆战（land 未执行 → war ACTIVE）
        data = result["data"]
        self.assertEqual(data["naval"]["result"], "DISASTER")
        self.assertEqual(data["land_battle"], "blocked")
        self.assertEqual(war.status, WarStatus.ACTIVE)


if __name__ == "__main__":
    unittest.main()
