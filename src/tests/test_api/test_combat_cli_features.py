"""
Feature Freeze Test — CLI CombatCommand 当前行为基线 (S1 冻结)

捕获 CLI CombatCommand 的战斗结算逻辑，作为改造前的行为快照。
改造后这些测试断言应与共享用例输出一致。
"""
import unittest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.entities.legion import Legion, LegionStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.ui.commands.phase_combat import CombatCommand


# 辅助：创建带司令官的测试战争
def _make_war(war_id, name, strength, commander_id=None,
              legions_assigned=0, disaster_numbers=None,
              standoff_numbers=None, rewards=None):
    w = War(
        id=war_id, name=name, war_type=WarType.FOREIGN,
        strength=strength, threat_level=3,
        rewards=rewards or {"treasury": 100},
        disaster_numbers=disaster_numbers or [2, 3],
        standoff_numbers=standoff_numbers or [5, 6, 7, 8, 9],
    )
    w.commander_id = commander_id
    w.legions_assigned = legions_assigned
    w.status = WarStatus.ACTIVE
    w._commander_assigned_turn = 1
    return w


class TestCLICombatFeatures(unittest.TestCase):
    """CLI CombatCommand 特征冻结——捕获当前行为基线"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("mortality")
        self.state.mark_phase_executed("revenue")
        self.state.mark_phase_executed("forum")
        self.state.mark_phase_executed("population")
        self.state.mark_phase_executed("senate")
        self.state._treasury = 500

        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)

        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction1)

        self.commander = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
        self.commander.martial = 6
        self.commander.influence = 50
        self.state.add_member(self.commander)
        self.faction1.member_ids.append(1)

        self.player = Player(player_id="player_opt", faction_id="optimates",
                             player_type=PlayerType.HUMAN)
        self.state.add_player(self.player)
        self.state.set_current_player("player_opt")

        # 创建测试战争
        self.war1 = _make_war("test_war_1", "Test War 1", strength=8,
                              commander_id=1, legions_assigned=4)
        self.state._war_system._active_wars.append(self.war1)

        # 创建军团指派到 war1（必须设置 AVAILABLE 才能 assign_to_war）
        for num in range(1, 5):
            legion = Legion(number=num, name=f"Legio {num}")
            legion.status = LegionStatus.AVAILABLE
            legion.assign_to_war("test_war_1", self.commander.id)
            self.state._military_system._legions.append(legion)

        # 第二场战争（无指挥官）
        self.war2 = _make_war("test_war_2", "Test War 2", strength=5,
                              legions_assigned=2)
        self.state._war_system._active_wars.append(self.war2)

        self.cmd = CombatCommand(self.state)
        # Mock peace treaty decider to not auto-generate for freeze tests
        self.cmd.peace_treaty_decider = MagicMock()
        self.cmd.peace_treaty_decider.decide_treaty.return_value = None

    # ════════════════════════════════════════════════════════════════════
    # CLI 特征 1: _simplified_crt 结果分类冻结
    # ════════════════════════════════════════════════════════════════════
    def test_cli_crt_triumph_high_score(self):
        """combat_total >= 12 → TRIUMPH"""
        result = self.cmd._simplified_crt(10, 14, self.war1)
        self.assertEqual(result, "TRIUMPH")  # CLI uppercase naming

    def test_cli_crt_victory_moderate_score(self):
        """12 > combat_total >= 6 → VICTORY"""
        result = self.cmd._simplified_crt(8, 8, self.war1)
        self.assertEqual(result, "VICTORY")

    def test_cli_crt_stalemate_low_positive(self):
        """combat_total in [-3, 6) or standoff_roll → STALEMATE"""
        result = self.cmd._simplified_crt(6, 2, self.war1)  # standoff roll
        self.assertEqual(result, "STALEMATE")

    def test_cli_crt_stalemate_negative_to_mid(self):
        """combat_total in [-3, 6) with non-standoff dice → STALEMATE"""
        result = self.cmd._simplified_crt(4, 0, self.war1)  # non-standoff, low score
        self.assertEqual(result, "STALEMATE")

    def test_cli_crt_defeat_low_score(self):
        """combat_total < -3 (non-standoff dice) → DEFEAT"""
        # dice=4 (not in standoff_numbers=[5..9]), combat_total=-5 (< -3)
        result = self.cmd._simplified_crt(4, -5, self.war1)
        self.assertEqual(result, "DEFEAT")

    def test_cli_crt_disaster_roll(self):
        """disaster_roll dice → DISASTER, regardless of score"""
        result = self.cmd._simplified_crt(2, 14, self.war1)  # disaster_numbers=[2,3]
        self.assertEqual(result, "DISASTER")

    # ════════════════════════════════════════════════════════════════════
    # CLI 特征 2: 军团战力计算（使用 get_combat_strength()）
    # ════════════════════════════════════════════════════════════════════
    def test_cli_legion_strength_basic(self):
        """基础军团战力 = 2"""
        legion = Legion(number=10, name="Legio X")
        self.assertEqual(legion.get_combat_strength(), 2)

    def test_cli_legion_strength_veteran(self):
        """老兵军团战力 = 3（+1）"""
        legion = Legion(number=10, name="Legio X")
        legion.promote_to_veteran()
        self.assertEqual(legion.get_combat_strength(), 3)

    # ════════════════════════════════════════════════════════════════════
    # CLI 特征 3: 战斗结果应用（TRIUMPH → 军团晋升 + 撤军）
    # ════════════════════════════════════════════════════════════════════
    def test_cli_apply_triumph_promotes_legions(self):
        """TRIUMPH → 所有军团晋升为老兵并撤回"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        for legion in legions:
            self.assertFalse(legion.is_veteran)
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "TRIUMPH", MagicMock(), self.state._military_system, legions, 8
        )
        for legion in legions:
            self.assertTrue(legion.is_veteran)
            self.assertEqual(legion.status, LegionStatus.AVAILABLE)  # recalled

    def test_cli_apply_triumph_resolves_war(self):
        """TRIUMPH → 战争标记为 RESOLVED"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "TRIUMPH", MagicMock(), self.state._military_system, legions, 8
        )
        self.assertEqual(self.war1.status, WarStatus.RESOLVED)

    def test_cli_apply_triumph_increases_commander_influence(self):
        """TRIUMPH → 指挥官影响力 +10"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        initial = self.commander.influence
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "TRIUMPH", MagicMock(), self.state._military_system, legions, 8
        )
        self.assertEqual(self.commander.influence, initial + 10)

    def test_cli_apply_victory_promotes_legions(self):
        """VICTORY → 全部幸存参战者晋升老兵 + 召回（AVAILABLE，Veteran 保留；G1-22，S5 收敛）"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "VICTORY", MagicMock(), self.state._military_system, legions, 8
        )
        for legion in legions:
            self.assertTrue(legion.is_veteran)
            self.assertEqual(legion.status, LegionStatus.AVAILABLE)  # recall → AVAILABLE

    def test_cli_apply_victory_resolves_war(self):
        """VICTORY → 战争结束（RESOLVED；S5 收敛 G1-22，不再「不结束战争」）"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "VICTORY", MagicMock(), self.state._military_system, legions, 8
        )
        self.assertEqual(self.war1.status, WarStatus.RESOLVED)

    def test_cli_apply_victory_increases_commander_influence(self):
        """VICTORY → 指挥官影响力 +5"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        initial = self.commander.influence
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "VICTORY", MagicMock(), self.state._military_system, legions, 8
        )
        self.assertEqual(self.commander.influence, initial + 5)

    def test_cli_apply_defeat_causes_legion_losses(self):
        """DEFEAT → ceil(N/2)=2 随机 DESTROYED；幸存保持 ACTIVE+assigned（G1-05/06/07，S5 收敛）"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "DEFEAT", MagicMock(), self.state._military_system, legions, 8
        )
        destroyed = [l for l in legions if l.status == LegionStatus.DESTROYED]
        survivors = [l for l in legions if l.status == LegionStatus.ACTIVE]
        self.assertEqual(len(destroyed), 2)  # ceil(4/2)
        self.assertEqual(len(survivors), 2)
        for legion in destroyed:
            self.assertIsNone(legion.war_id)
            self.assertIsNone(legion.commander_id)
            self.assertFalse(legion.is_veteran)
        for legion in survivors:
            self.assertEqual(legion.war_id, "test_war_1")

    def test_cli_apply_defeat_may_casualty_commander(self):
        """DEFEAT → 指挥官可能伤亡（commander_id 被清除）"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        self.assertTrue(self.war1.commander_id is not None)
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "DEFEAT", MagicMock(), self.state._military_system, legions, 8
        )
        self.assertIsNone(self.war1.commander_id)
        self.assertIn(self.war1._commander_status, ("fled", "captured", "wounded"))

    def test_cli_apply_disaster_destroys_all_legions(self):
        """DISASTER → 所有军团标记为 DESTROYED"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "DISASTER", MagicMock(), self.state._military_system, legions, 8
        )
        for legion in legions:
            self.assertEqual(legion.status, LegionStatus.DESTROYED)

    def test_cli_apply_disaster_kills_commander(self):
        """DISASTER → 指挥官阵亡"""
        legions = self.state._military_system.get_legions_for_battle("test_war_1")
        self.cmd._apply_battle_result(
            self.state._war_system, self.war1, self.commander,
            "DISASTER", MagicMock(), self.state._military_system, legions, 8
        )
        self.assertTrue(self.state.get_member(1).is_dead)

    # ════════════════════════════════════════════════════════════════════
    # CLI 特征 4: 停战条约生成条件（通过 _maybe_generate_treaty）
    # ════════════════════════════════════════════════════════════════════
    def test_cli_treaty_not_generated_on_triumph(self):
        """TRIUMPH → 不生成停战条约"""
        ws = self.state._war_system
        self.cmd._maybe_generate_treaty(ws, self.war1, "TRIUMPH", MagicMock())
        self.cmd.peace_treaty_decider.decide_treaty.assert_not_called()

    def test_cli_treaty_not_generated_on_disaster(self):
        """DISASTER → 不生成停战条约"""
        ws = self.state._war_system
        self.cmd._maybe_generate_treaty(ws, self.war1, "DISASTER", MagicMock())
        self.cmd.peace_treaty_decider.decide_treaty.assert_not_called()

    def _setup_treaty_mock(self):
        self.cmd.peace_treaty_decider = MagicMock()
        self.cmd.peace_treaty_decider.decide_treaty.return_value = {
            "indemnity": 50, "duration": 3, "generated_turn": 1
        }

    def test_cli_treaty_not_generated_on_victory(self):
        """VICTORY → 不生成停战条约（G1-08：仅 STALEMATE 生成；VICTORY=战争结束归 GB）"""
        self._setup_treaty_mock()
        ws = self.state._war_system
        self.cmd._maybe_generate_treaty(ws, self.war1, "VICTORY", MagicMock())
        self.cmd.peace_treaty_decider.decide_treaty.assert_not_called()

    def test_cli_treaty_generated_on_stalemate(self):
        """STALEMATE → 尝试生成停战条约"""
        self._setup_treaty_mock()
        ws = self.state._war_system
        self.cmd._maybe_generate_treaty(ws, self.war1, "STALEMATE", MagicMock())
        self.cmd.peace_treaty_decider.decide_treaty.assert_called_once()

    def test_cli_treaty_not_generated_on_defeat(self):
        """DEFEAT → 不生成停战条约（G1-08：战败/灾难不求和，战争继续）"""
        self._setup_treaty_mock()
        ws = self.state._war_system
        self.cmd._maybe_generate_treaty(ws, self.war1, "DEFEAT", MagicMock())
        self.cmd.peace_treaty_decider.decide_treaty.assert_not_called()

    # ════════════════════════════════════════════════════════════════════
    # CLI 特征 5: execute 整体行为
    # ════════════════════════════════════════════════════════════════════
    def test_cli_execute_skips_if_senate_not_executed(self):
        """senate 未执行 → 返回 False"""
        self.state._executed_phases.discard("senate")
        result = self.cmd.execute([])
        self.assertFalse(result)

    def test_cli_execute_skips_if_already_executed(self):
        """combat 已执行 → 返回 False"""
        self.state.mark_phase_executed("combat")
        result = self.cmd.execute([])
        self.assertFalse(result)

    def test_cli_execute_marks_phase_executed(self):
        """execute 后 combat 标记为已执行"""
        self._setup_treaty_mock()
        result = self.cmd.execute([])
        self.assertTrue(result)
        self.assertTrue(self.state.is_phase_executed("combat"))


if __name__ == "__main__":
    unittest.main()
