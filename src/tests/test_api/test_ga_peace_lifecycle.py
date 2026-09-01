# src/tests/test_api/test_ga_peace_lifecycle.py
"""WP-G GA：treaty 生命周期（S17/S18）测试（G3C 修正）。

覆盖：
- approved = TEMPORARY TRUCE（非战争结束）：indemnity 记赔、幸存军团召回 AVAILABLE、
  指挥官返回罗马、truce_end_turn 写入、War 保持 TRUCE 驻留 _truce_wars（G3C / ODR-CAND-01）
- rejected → ACTIVE：保留 commander/legion、条约清除（W2 对齐 E 件 T6 断言）
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem


class TestGaPeaceLifecycle(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state._treasury = 500
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)
        self.commander = Figure(id=1, name="指挥官", faction_id="optimates", age=50)
        self.commander.office = "proconsul"
        self.commander.is_absent = True
        self.state.add_member(self.commander)
        self.faction.member_ids.append(1)

    def _make_submitted_truce_war(self, war_id="w_peace", legion_number=1):
        war = War(id=war_id, name="Peace War", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 100, "duration": 3, "status": "submitted", "generated_turn": 1})
        war.commander_id = 1
        self.state._war_system._truce_wars.append(war)
        ms = self.state._military_system
        ok, _ = ms.recruit_legion(legion_number)
        assert ok
        ms.assign_to_war([legion_number], war.id, 1)
        return war

    def test_approved_keeps_truce_releases_force(self):
        """S17（G3C）：approved → War 保持 TRUCE + 召回 + 指挥官返回 + 记赔 + enqueue-then-clear。"""
        war = self._make_submitted_truce_war()
        PoliticalSystem(self.state).execute_passed_peace_treaty(war)

        # approved = temporary truce：War 保持 TRUCE、驻留 _truce_wars、不入弃牌堆
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIn(war, self.state._war_system._truce_wars)
        self.assertNotIn(war, self.state._war_system._war_discard)
        self.assertEqual(war.peace_treaty["status"], "approved")
        self.assertEqual(war.indemnity_due, 100)
        # truce_end_turn 写入（turn=1 + duration=3 → 4）
        self.assertEqual(war.truce_end_turn, 4)
        # 幸存军团召回 → AVAILABLE；war.legion_numbers 立即清空（ODR-CAND-01 方向①）
        legion = self.state._military_system.get_legion_by_number(1)
        self.assertEqual(legion.status.value, "available")
        self.assertIsNone(legion.war_id)
        self.assertIsNone(legion.commander_id)
        self.assertEqual(war.legion_numbers, [])
        self.assertEqual(self.state._war_system._legions_to_disband, [1])
        # 指挥官返回罗马（absent 解除 + proconsul → ex-consul）
        self.assertFalse(self.commander.is_absent)
        self.assertEqual(self.commander.office, "ex-consul")
        self.assertIsNone(war.commander_id)
        # 到期机制已恢复（G3C：approved TRUCE → 到期 → THREAT）
        self.assertTrue(hasattr(self.state, "process_truce_expiry"))
        self.assertTrue(hasattr(war, "is_truce_expired"))

    def test_approved_requires_submitted_status(self):
        """approved 路径前置：条约非 submitted → 无 mutation。"""
        war = self._make_submitted_truce_war(war_id="w_pending")
        war.set_peace_treaty_status("pending")
        PoliticalSystem(self.state).execute_passed_peace_treaty(war)
        self.assertEqual(war.status, WarStatus.TRUCE)  # 未处理
        self.assertIn(war, self.state._war_system._truce_wars)

    def test_rejected_restores_active_preserves_commander(self):
        """S18：rejected → TRUCE→ACTIVE + 保留 commander/legion + 条约清除（W2）。"""
        war = self._make_submitted_truce_war(war_id="w_reject")
        ws = self.state._war_system
        self.assertTrue(ws.restore_rejected_peace_treaty(war.id, preserve_commander=True))
        self.assertEqual(war.status, WarStatus.ACTIVE)
        self.assertIn(war, ws.get_active_wars())
        self.assertNotIn(war, ws._truce_wars)
        self.assertEqual(war.commander_id, 1)  # commander 保留
        self.assertIsNone(war.peace_treaty)  # 条约清除
        legion = self.state._military_system.get_legion_by_number(1)
        self.assertEqual(legion.war_id, war.id)  # legion 保留 assigned
        self.assertEqual(legion.commander_id, 1)

    def test_restore_rejected_via_political_system_batch(self):
        """restore_rejected_peace_wars 批路径（E 件 T6）：多战争恢复。"""
        war1 = self._make_submitted_truce_war(war_id="w_r1", legion_number=1)
        war2 = self._make_submitted_truce_war(war_id="w_r2", legion_number=2)
        war2.set_peace_treaty_status("pending")
        restored = PoliticalSystem(self.state).restore_rejected_peace_wars([war1, war2, war1])
        self.assertEqual(len(restored), 2)  # 去重
        self.assertEqual(war1.status, WarStatus.ACTIVE)
        self.assertEqual(war2.status, WarStatus.ACTIVE)


if __name__ == "__main__":
    unittest.main()
