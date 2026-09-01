"""
WP-G GB 切片测试 — Legion / Land Combat / Veteran / Recovery（T-GB-01~13/15/16）

Parent Authority: WP-G v0.8 G3 DESIGN FROZEN
Gameplay Authority: G1-05 / G1-06 / G1-07 / G1-19 / G1-22 / G1-25（不可重开）
覆盖：live 实体战力权威（R-17）、DEFEAT 随机 ceil(N/2) DESTROYED、DISASTER 全灭、
Veteran 晋升/持久、recall→AVAILABLE、恢复生命周期、全 25 灭败北守护（G1-25）。
"""
import inspect
import unittest
from unittest.mock import patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.legion import LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.api import combat_api


def _make_war(war_id, strength=8, commander_id=None, disaster_numbers=None,
              standoff_numbers=None, rewards=None):
    """创建 ACTIVE 战争并注册到 ws._active_wars。"""
    war = War(
        id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
        strength=strength, threat_level=3,
        rewards=rewards or {"treasury": 100},
        disaster_numbers=disaster_numbers or [2, 3],
        standoff_numbers=standoff_numbers or [5, 6, 7, 8, 9],
    )
    war.status = WarStatus.ACTIVE
    war.commander_id = commander_id
    return war


class WPGGbLandCombatBase(unittest.TestCase):
    """共享 fixture：真实 GameState + WarSystem + MilitarySystem + live Legion 实体。"""

    def setUp(self):
        config = {"combat_rules": {"legion_recovery_interval": 5}}
        self.state = GameState.create_for_testing(config)
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for p in ["mortality", "revenue", "forum", "population", "senate"]:
            self.state.mark_phase_executed(p)
        self.state.treasury = 1000

        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)

        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)

        self.commander = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
        self.commander.martial = 6
        self.commander.influence = 50
        self.state.add_member(self.commander)
        self.faction.member_ids.append(1)

        self.player = Player(player_id="player_opt", faction_id="optimates",
                             player_type=PlayerType.HUMAN)
        self.state.add_player(self.player)
        self.state.set_current_player("player_opt")

    # ── helpers ──────────────────────────────────────────────
    def attach_legions(self, war_id, numbers, veteran=False, commander_id=None):
        """recruit + assign 真实 live 军团实体（numbers = 显式编号列表）；返回军团列表。"""
        ms = self.state._military_system
        for num in numbers:
            ok, msg = ms.recruit_legion(num)
            assert ok, f"recruit {num} failed: {msg}"
            if veteran:
                ms.get_legion_by_number(num).is_veteran = True
        assigned, msg = ms.assign_to_war(list(numbers), war_id, commander_id)
        assert assigned == len(numbers), f"assign failed: {msg}"
        return ms.get_legions_for_battle(war_id)

    def register_war(self, war):
        self.state._war_system._active_wars.append(war)
        return war

    def ms(self):
        return self.state._military_system

    def ws(self):
        return self.state._war_system


# ═══════════════════════════════════════════════════════════════
# T-GB-01 / T-GB-02 — 参战集/战力权威 = live 实体（R-17 / G2-C §2）
# ═══════════════════════════════════════════════════════════════
class TestGbLiveAuthority(WPGGbLandCombatBase):
    """T-GB-01/02：战力/计数源自 live 实体，镜像=0 仍正确，veteran +1 生效。"""

    def test_gb01_power_from_live_entities_ignores_mirror(self):
        """镜像 legions_assigned=0 时战力仍正确（3 个 live 军团 → Σ=6）。"""
        war = _make_war("w1", strength=10, commander_id=1)
        war.legions_assigned = 0  # 镜像清零——不得影响权威战力
        self.register_war(war)
        self.attach_legions("w1", [1, 2, 3], commander_id=1)

        card = combat_api._war_card(war, self.state)
        self.assertEqual(card["legion_count"], 3)
        self.assertEqual(card["total_power"], 6 + 6)  # martial 6 + Σ(2*3)

        result = combat_api._compute_combat_result(war, self.state, 10, "attack")
        self.assertEqual(result["legion_power"], 6)

    def test_gb02_veteran_plus_one_applies(self):
        """combat_power = martial + Σ get_combat_strength（veteran 军团 +1）。"""
        war = _make_war("w2", strength=10, commander_id=1)
        self.register_war(war)
        self.attach_legions("w2", [1, 2], veteran=True, commander_id=1)  # 2 个老兵 → 3+3

        card = combat_api._war_card(war, self.state)
        self.assertEqual(card["total_power"], 6 + 6)  # 6 + (3+3)

        result = combat_api._compute_combat_result(war, self.state, 10, "attack")
        self.assertEqual(result["legion_power"], 6)


# ═══════════════════════════════════════════════════════════════
# T-GB-03 / T-GB-04 / T-GB-05 / T-GB-07 — DEFEAT 伤亡数学与状态（G1-05/06/07）
# ═══════════════════════════════════════════════════════════════
class TestGbDefeatCasualties(WPGGbLandCombatBase):
    """T-GB-03~05/07：ceil(N/2) 随机无放回 → DESTROYED；幸存保持；war ACTIVE。"""

    def test_gb03_defeat_math_full_table(self):
        """G1-06 全表：N=1..6 → loss = N - N//2。"""
        expected = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}
        offset = 0
        for n, loss in expected.items():
            numbers = list(range(offset + 1, offset + n + 1))
            offset += n
            war = _make_war(f"defeat_n{n}", strength=100)
            self.register_war(war)
            self.attach_legions(f"defeat_n{n}", numbers)
            destroyed = self.ms().apply_land_casualties(f"defeat_n{n}", "DEFEAT")
            self.assertEqual(len(destroyed), loss, f"N={n} 应伤亡 {loss}")
            destroyed_set = set(destroyed)
            self.assertEqual(len(destroyed_set), loss)  # 无重复（无放回）

    def test_gb04_defeat_random_without_replacement(self):
        """随机性集合性质：30 轮 seed 下伤亡集非固定（禁前缀序确定性）。"""
        import random
        war = _make_war("defeat_rnd", strength=100)
        self.register_war(war)
        numbers = [1, 2, 3, 4, 5]
        self.attach_legions("defeat_rnd", numbers)
        distinct = set()
        for seed in range(30):
            random.seed(seed)
            destroyed = set(self.ms().apply_land_casualties("defeat_rnd", "DEFEAT"))
            self.assertEqual(len(destroyed), 3)
            self.assertLessEqual(destroyed, set(numbers))
            distinct.add(frozenset(destroyed))
            # 复元（测试脚手架：仅复用池，不改采样语义）
            for n in numbers:
                l = self.ms().get_legion_by_number(n)
                l.status = LegionStatus.ACTIVE
                l.war_id = "defeat_rnd"
                l._destroyed_turn = 0
        # 30 轮 seed 下出现 ≥2 种不同伤亡集 → 非固定前缀序
        self.assertGreaterEqual(len(distinct), 2)

    def test_gb05_defeat_state_transitions(self):
        """伤亡 → DESTROYED + war_id/commander_id=None + is_veteran=False；幸存保持 ACTIVE+assigned。"""
        war = _make_war("defeat_state", strength=100, commander_id=1)
        self.register_war(war)
        legions = self.attach_legions("defeat_state", [1, 2, 3, 4], veteran=True, commander_id=1)

        destroyed = self.ms().apply_land_casualties("defeat_state", "DEFEAT")
        self.assertEqual(len(destroyed), 2)  # ceil(4/2)

        destroyed_set = set(destroyed)
        for legion in legions:
            if legion.number in destroyed_set:
                self.assertEqual(legion.status, LegionStatus.DESTROYED)
                self.assertIsNone(legion.war_id)
                self.assertIsNone(legion.commander_id)
                self.assertFalse(legion.is_veteran)  # 摧毁清 Veteran（G1-07）
            else:
                self.assertEqual(legion.status, LegionStatus.ACTIVE)
                self.assertEqual(legion.war_id, war.id)
                self.assertEqual(legion.commander_id, 1)
                self.assertTrue(legion.is_veteran)  # 幸存保留 Veteran

    def test_gb07_defeat_war_stays_active_commander_consequence(self):
        """生产链 DEFEAT：war ACTIVE + commander 后果（fled/captured/wounded）+ commander_id=None。"""
        war = _make_war("defeat_chain", strength=50, commander_id=1,
                        disaster_numbers=[11, 12])  # dice=3 非 disaster
        self.register_war(war)
        self.attach_legions("defeat_chain", [1, 2, 3, 4], commander_id=1)

        with patch.object(combat_api.random, "randint", return_value=3), \
             patch.object(combat_api.random, "random", return_value=0.1):
            result = combat_api.do_combat_action(self.state, "player_opt", "defeat_chain", "attack")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "defeat")
        self.assertEqual(result["data"]["losses"], 2)
        self.assertEqual(len(result["data"]["casualty_numbers"]), 2)
        # war 保持 ACTIVE（T11），不 resolve 不 discard
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertNotIn(war, self.ws()._war_discard)
        self.assertIsNone(war.commander_id)
        self.assertIn(war.commander_status, ("fled", "captured", "wounded"))


# ═══════════════════════════════════════════════════════════════
# T-GB-06 — DISASTER 全灭（G1-05/06/07）
# ═══════════════════════════════════════════════════════════════
class TestGbDisaster(WPGGbLandCombatBase):
    """T-GB-06：DISASTER → 全部参战 DESTROYED；war 保持 ACTIVE（不 resolve/不条约）。"""

    def test_gb06_disaster_destroys_all_war_active(self):
        war = _make_war("disaster_chain", strength=5, commander_id=1,
                        disaster_numbers=[2, 3])
        self.register_war(war)
        legions = self.attach_legions("disaster_chain", [1, 2, 3], commander_id=1)

        with patch.object(combat_api.random, "randint", return_value=2):
            result = combat_api.do_combat_action(self.state, "player_opt", "disaster_chain", "attack")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "disaster")
        self.assertEqual(result["data"]["losses"], 3)
        self.assertEqual(len(result["data"]["casualty_numbers"]), 3)
        for legion in legions:
            self.assertEqual(legion.status, LegionStatus.DESTROYED)
            self.assertIsNone(legion.war_id)
        # war 保持 ACTIVE（T12），不 resolve 不 discard；指挥官阵亡
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertNotIn(war, self.ws()._war_discard)
        self.assertTrue(self.state.get_member(1).is_dead)


# ═══════════════════════════════════════════════════════════════
# T-GB-08 — TRIUMPH/VICTORY → 全晋升 + RESOLVED + recall→AVAILABLE（G1-22）
# ═══════════════════════════════════════════════════════════════
class TestGbVictoryLifecycle(WPGGbLandCombatBase):
    """T-GB-08：胜利两档均 → 全部幸存参战者 Veteran → RESOLVED → recall → AVAILABLE。"""

    def _assert_victory_chain(self, war, legions, result_word):
        with patch.object(combat_api.random, "randint", return_value=10 if result_word == "victory" else 12):
            result = combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], result_word)
        self.assertEqual(war.status, WarStatus.RESOLVED)
        for legion in legions:
            self.assertTrue(legion.is_veteran)
            self.assertEqual(legion.status, LegionStatus.AVAILABLE)  # recall → AVAILABLE
            self.assertIsNone(legion.war_id)

    def test_gb08_triumph(self):
        war = _make_war("tri", strength=5, commander_id=1,
                        disaster_numbers=[11], standoff_numbers=[2, 3])
        self.register_war(war)
        legions = self.attach_legions("tri", [1, 2, 3, 4], commander_id=1)
        self._assert_victory_chain(war, legions, "triumph")

    def test_gb08_victory(self):
        # dice=10, 敌 18 → score = 10+6+8-18 = 6 → VICTORY（非 standoff、非 disaster）
        war = _make_war("vic", strength=18, commander_id=1,
                        disaster_numbers=[11], standoff_numbers=[2, 3])
        self.register_war(war)
        legions = self.attach_legions("vic", [1, 2, 3, 4], commander_id=1)
        self._assert_victory_chain(war, legions, "victory")


# ═══════════════════════════════════════════════════════════════
# T-GB-09 / T-GB-10 — Veteran 持久（G1-19 / R-13）
# ═══════════════════════════════════════════════════════════════
class TestGbVeteranPersistence(WPGGbLandCombatBase):
    """T-GB-09/10：正常解散/重募保留 Veteran；唯一清除点 = mark_destroyed。"""

    def test_gb09_recruit_disband_preserve_veteran(self):
        ms = self.ms()
        # ACTIVE → disband（行政解散）→ DISBANDED → recruit（正常重募）全程保留
        l1 = ms.get_legion_by_number(1)
        ok, _ = ms.recruit_legion(1)  # UNRAISED → ACTIVE
        self.assertTrue(ok)
        l1.promote_to_veteran()
        ok, _ = ms.disband_legion(1)
        self.assertTrue(ok)
        self.assertEqual(l1.status, LegionStatus.DISBANDED)
        self.assertTrue(l1.is_veteran)
        ok, _ = ms.recruit_legion(1)
        self.assertTrue(ok)
        self.assertTrue(l1.is_veteran)  # 重募不清 Veteran（G1-19）
        self.assertEqual(l1.status, LegionStatus.ACTIVE)

        # UNRAISED → recruit 保留（持久恢复场景）
        l2 = ms.get_legion_by_number(2)
        l2.is_veteran = True
        ok, _ = ms.recruit_legion(2)
        self.assertTrue(ok)
        self.assertTrue(l2.is_veteran)

    def test_gb10_mark_destroyed_is_only_clear_point(self):
        ms = self.ms()
        l = ms.get_legion_by_number(3)
        l.promote_to_veteran()
        self.assertTrue(l.is_veteran)
        l.mark_destroyed(7)
        self.assertFalse(l.is_veteran)  # 唯一清除点
        self.assertEqual(l.status, LegionStatus.DESTROYED)
        # 摧毁后无法直接重募（必须先恢复）
        ok, _ = ms.recruit_legion(3)
        self.assertFalse(ok)


# ═══════════════════════════════════════════════════════════════
# T-GB-11 — 恢复生命周期（G2-I §5）
# ═══════════════════════════════════════════════════════════════
class TestGbRecoveryLifecycle(WPGGbLandCombatBase):
    """T-GB-11：DESTROYED → interval 满（每 Resolution 一个最老）→ DISBANDED → 可再募。"""

    def test_gb11_recovery_round_trip(self):
        ms = self.ms()
        l1 = ms.get_legion_by_number(1)
        l2 = ms.get_legion_by_number(2)
        l1.promote_to_veteran()
        l1.mark_destroyed(1)  # 摧毁清 Veteran
        l2.mark_destroyed(2)
        self.assertFalse(l1.is_veteran)

        # 回合 10，interval 5：1 号满足（10-1>=5）、2 号满足（10-2>=5）→ 每 Resolution 恢复最老一个
        self.assertEqual(ms.process_legion_recovery(10), [1])
        self.assertEqual(l1.status, LegionStatus.DISBANDED)
        self.assertEqual(l1.destroyed_turn, 0)
        self.assertEqual(ms.process_legion_recovery(10), [2])

        # 恢复后可再募（Veteran 保持 False——摧毁已清）
        ok, _ = ms.recruit_legion(1)
        self.assertTrue(ok)
        self.assertFalse(l1.is_veteran)


# ═══════════════════════════════════════════════════════════════
# T-GB-12 / T-GB-13 — 全 25 灭败北（G1-25）
# ═══════════════════════════════════════════════════════════════
class TestGbAllDestroyedDefeat(WPGGbLandCombatBase):
    """T-GB-12/13：Resolution 先判胜负后恢复；全 25 DESTROYED 可经 GB 伤亡链触发。"""

    def test_gb12_resolution_victory_before_recovery(self):
        """全 25 DESTROYED（间隔已满可恢复）→ 仍判败北（game_over），恢复随后执行。"""
        ms = self.ms()
        for i in range(1, 26):
            l = ms.get_legion_by_number(i)
            l.mark_destroyed(1)  # 摧毁于回合 1，回合 10 间隔已满

        self.state.turn = GameTurn(turn_number=10, year=-255)
        self.state.mark_phase_executed("combat")

        from src.api import resolution_api
        resp = resolution_api.execute_resolution(self.state, "player_opt")
        self.assertTrue(resp["success"])
        data = resp["data"]
        # 先判胜负：全 25 灭 → game_over（即使本 Resolution 有可恢复军团）
        self.assertTrue(data["victory"]["game_over"])
        self.assertTrue(any(
            c["type"] == "legions_destroyed" and c["triggered"]
            for c in data["victory"]["conditions"]
        ))
        # 恢复随后执行（间隔已满）——败北判定先于恢复（G1-25 顺序）
        self.assertGreaterEqual(data["legion_recovery"]["recovered"], 1)

    def test_gb13_all_destroyed_via_casualty_chain(self):
        """全 25 DESTROYED 可经 GB 生产伤亡链触发（DISASTER → 全灭 → Resolution 败北）。"""
        ms = self.ms()
        for i in range(1, 26):
            ok, _ = ms.recruit_legion(i)
            assert ok
        war = _make_war("total_war", strength=5, commander_id=1,
                        disaster_numbers=[2, 3])
        self.register_war(war)
        assigned, msg = ms.assign_to_war(list(range(1, 26)), "total_war", 1)
        self.assertEqual(assigned, 25)

        with patch.object(combat_api.random, "randint", return_value=2):
            result = combat_api.do_combat_action(self.state, "player_opt", "total_war", "attack")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["result"], "disaster")
        self.assertEqual(result["data"]["losses"], 25)
        self.assertTrue(all(l.status == LegionStatus.DESTROYED for l in ms.get_all_legions()))

        self.state.mark_phase_executed("combat")
        from src.api import resolution_api
        resp = resolution_api.execute_resolution(self.state, "player_opt")
        self.assertTrue(resp["success"])
        self.assertTrue(resp["data"]["victory"]["game_over"])
        self.assertTrue(any(
            c["type"] == "legions_destroyed" and c["triggered"]
            for c in resp["data"]["victory"]["conditions"]
        ))


# ═══════════════════════════════════════════════════════════════
# T-GB-15 — 重复战斗调用不重复 destroy（resolved_wars 幂等 guard）
# ═══════════════════════════════════════════════════════════════
class TestGbBattleIdempotency(WPGGbLandCombatBase):
    """T-GB-15：单次 mark；重复 attack 被 resolved_wars guard 拒绝，伤亡不重复。"""

    def test_gb15_second_attack_rejected_no_double_destroy(self):
        war = _make_war("idem", strength=50, commander_id=1,
                        disaster_numbers=[11, 12])  # dice=3 非 disaster
        self.register_war(war)
        self.attach_legions("idem", [1, 2, 3, 4], commander_id=1)

        with patch.object(combat_api.random, "randint", return_value=3), \
             patch.object(combat_api.random, "random", return_value=0.9):
            first = combat_api.do_combat_action(self.state, "player_opt", "idem", "attack")
        self.assertTrue(first["success"])
        destroyed_after_first = len([l for l in self.ms().get_all_legions()
                                     if l.status == LegionStatus.DESTROYED])
        self.assertEqual(destroyed_after_first, 2)  # ceil(4/2)，单次

        second = combat_api.do_combat_action(self.state, "player_opt", "idem", "attack")
        self.assertFalse(second["success"])
        destroyed_after_second = len([l for l in self.ms().get_all_legions()
                                      if l.status == LegionStatus.DESTROYED])
        self.assertEqual(destroyed_after_second, 2)  # 不重复 destroy


# ═══════════════════════════════════════════════════════════════
# T-GB-16 — diff 审计：镜像字段不作战斗权威（R-17 / N 件）
# ═══════════════════════════════════════════════════════════════
class TestGbMirrorAudit(WPGGbLandCombatBase):
    """T-GB-16：战斗权威函数无 war.legions_assigned / war.legion_numbers 残留。"""

    def test_gb16_no_stale_mirror_as_combat_authority(self):
        src = "".join([
            inspect.getsource(combat_api._compute_combat_result),
            inspect.getsource(combat_api._war_card),
            inspect.getsource(combat_api.do_combat_action),
        ])
        self.assertNotIn("war.legions_assigned", src)
        self.assertNotIn("war.legion_numbers", src)
        self.assertNotIn("legions_assigned *", src)
        self.assertNotIn("legion_numbers[", src)


if __name__ == "__main__":
    unittest.main()
