# src/tests/test_api/test_wpfr2_combat.py
"""WP-F-R2 T-R2-12~19：TRUCE 军团动员数权威投影 + Revenue 同集 + 无生命周期 mutation。

真实生命周期链（禁手搓 DTO mock 替代）：
  N 军团 ACTIVE/指派 → do_combat_action(dice=7 → draw → STALEMATE) → TRUCE
  → 军团 status/war_id 保持权威 ACTIVE/attached（T-R2-12）
  → TRUCE 卡 legion_count / mobilized_legion_count 含 N（T-R2-13/14/16）
  → ACTIVE+TRUCE 混合无重复（T-R2-15）
  → Revenue 维护费含同批 ACTIVE（T-R2-17）
  → canonical 释放（execute_passed_peace_treaty → recall_from_war）→ 计数下降（T-R2-18）
  → war_system/military_system 零 mutation 审计（T-R2-19）
"""
import os
import unittest
from unittest.mock import patch

from src.api import combat_api
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.legion import LegionStatus
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.game_state import GameState
from src.core.systems.military_system import MilitarySystem
from src.core.systems.war_system import WarSystem


class TestWpFr2TruceLegionMobilized(unittest.TestCase):
    """STALEMATE→TRUCE 生命周期链（真实战斗产生，dice=7 → draw → STALEMATE → TRUCE）。"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for ph in ["mortality", "revenue", "forum", "population", "senate"]:
            self.state.mark_phase_executed(ph)
        self.state._treasury = 500
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)

        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)

        self.commander = Figure(id=1, name="Marcus", faction_id="optimates", age=40)
        self.commander.martial = 6
        self.state.add_member(self.commander)
        self.faction.member_ids.append(1)

        self.player = Player(player_id="player_opt", faction_id="optimates",
                             player_type=PlayerType.HUMAN)
        self.state.add_player(self.player)
        self.state.set_current_player("player_opt")

    def _make_war(self, war_id="war1", strength=14):
        """dice=7 + martial=6 → draw（standoff_numbers 命中）→ STALEMATE → TRUCE。"""
        war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN,
                  strength=strength, threat_level=3, disaster_numbers=[12])
        war.commander_id = 1
        war.legions_assigned = 1
        war.status = WarStatus.ACTIVE
        self.state._war_system._active_wars.append(war)
        return war

    def _recruit_and_assign(self, numbers, war_id):
        ms = self.state.get_military_system()
        for num in numbers:
            ok, msg = ms.recruit_legion(num)
            self.assertTrue(ok, msg)
        assigned, msg = ms.assign_to_war(numbers, war_id, 1)
        self.assertEqual(assigned, len(numbers), msg)

    def _view(self):
        result = combat_api.get_combat_view(self.state, "player_opt")
        self.assertTrue(result["success"], result.get("message"))
        return result["data"]

    @patch.object(combat_api.random, "randint", return_value=7)
    def test_r2_12_stalemate_truce_preserves_active_attached(self, mock_randint):
        """T-R2-12：STALEMATE→TRUCE → 军团 status/war_id 保持权威 ACTIVE/attached。"""
        war = self._make_war()
        self._recruit_and_assign([1, 2, 3], war.id)
        result = combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        self.assertTrue(result["success"], result.get("message"))
        self.assertEqual(war.status, WarStatus.TRUCE)
        self.assertIn(war, self.state._war_system._truce_wars)
        ms = self.state.get_military_system()
        for num in (1, 2, 3):
            legion = ms.get_legion_by_number(num)
            self.assertEqual(legion.status, LegionStatus.ACTIVE, f"legion {num} 保持 ACTIVE")
            self.assertEqual(legion.war_id, war.id, f"legion {num} 保持 attached")

    @patch.object(combat_api.random, "randint", return_value=7)
    def test_r2_13_truce_card_returns_attached_legion_count(self, mock_randint):
        """T-R2-13：TRUCE _war_card 返回附着 legion_count。"""
        war = self._make_war()
        self._recruit_and_assign([1, 2, 3], war.id)
        combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        data = self._view()
        self.assertEqual(len(data["truce_wars"]), 1)
        card = data["truce_wars"][0]
        self.assertEqual(card["war_id"], war.id)
        self.assertEqual(card["legion_count"], 3)
        self.assertEqual(card["presentation_state"], "TRUCE_LOCKED")

    @patch.object(combat_api.random, "randint", return_value=7)
    def test_r2_14_mobilized_count_includes_truce_active(self, mock_randint):
        """T-R2-14：mobilized_legion_count 含 TRUCE ACTIVE 军团（= get_active_legions()）。"""
        war = self._make_war()
        self._recruit_and_assign([1, 2, 3], war.id)
        combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        data = self._view()
        ms = self.state.get_military_system()
        self.assertEqual(data["mobilized_legion_count"], 3)
        self.assertEqual(data["mobilized_legion_count"], len(ms.get_active_legions()))
        # 顶部概览语义：TRUCE 附着 ACTIVE 计入，非 0（R2-02 缺陷闭合）
        self.assertNotEqual(data["mobilized_legion_count"], 0)

    @patch.object(combat_api.random, "randint", return_value=7)
    def test_r2_15_mixed_active_truce_no_double_count(self, mock_randint):
        """T-R2-15：ACTIVE + TRUCE 混合无重复（get_active_legions() 单次遍历）。"""
        war1 = self._make_war("war_active")
        war2 = self._make_war("war_truce")
        self._recruit_and_assign([1, 2], war1.id)
        self._recruit_and_assign([3, 4, 5], war2.id)
        # war2 战斗 → draw → TRUCE；war1 保持 ACTIVE 未战
        combat_api.do_combat_action(self.state, "player_opt", war2.id, "attack")
        data = self._view()
        active_cards = data["active_wars"]
        truce_cards = data["truce_wars"]
        self.assertEqual(len(active_cards), 1)
        self.assertEqual(len(truce_cards), 1)
        active_sum = sum(c["legion_count"] for c in active_cards)
        truce_sum = sum(c["legion_count"] for c in truce_cards)
        ms = self.state.get_military_system()
        self.assertEqual(active_sum, 2)
        self.assertEqual(truce_sum, 3)
        # 无重复：权威计数 = 各卡之和 = get_active_legions() 单次遍历
        self.assertEqual(data["mobilized_legion_count"], active_sum + truce_sum)
        self.assertEqual(data["mobilized_legion_count"], len(ms.get_active_legions()))

    @patch.object(combat_api.random, "randint", return_value=7)
    def test_r2_16_combat_view_store_consistency(self, mock_randint):
        """T-R2-16：get_combat_view 的 mobilized_legion_count 与 Store 消费一致。"""
        war = self._make_war()
        self._recruit_and_assign([1, 2, 3], war.id)
        combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        data = self._view()
        from src.ui.gui.session_store import GuiSessionStore
        store = GuiSessionStore(self.state)
        store.initialize("player_opt")
        ms = self.state.get_military_system()
        self.assertEqual(store.combatMobilizedLegions, data["mobilized_legion_count"])
        self.assertEqual(store.combatMobilizedLegions, len(ms.get_active_legions()))
        # 语义区分：可征召池属性保持既有语义（不动）
        self.assertEqual(
            store.combatAvailableLegions,
            len(ms.get_available_legions()),
        )

    @patch.object(combat_api.random, "randint", return_value=7)
    def test_r2_17_revenue_maintenance_same_truce_active_set(self, mock_randint):
        """T-R2-17：下回合 Revenue 维护费含同批 TRUCE ACTIVE 军团（calculate_maintenance 同集）。"""
        war = self._make_war()
        self._recruit_and_assign([1, 2, 3], war.id)
        combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        ms = self.state.get_military_system()
        total, breakdown = ms.calculate_maintenance()
        expected = sum(
            ms.get_legion_by_number(n).get_maintenance_cost(self.state)
            for n in (1, 2, 3)
        )
        self.assertEqual(total, expected)
        for n in (1, 2, 3):
            self.assertIn(ms.get_legion_by_number(n).name, breakdown)
        # Revenue 入口同源（EconomicService.apply_military_maintenance → calculate_maintenance）
        from src.core.service.economic_service import EconomicService
        res = EconomicService(self.state).apply_military_maintenance()
        self.assertTrue(res["available"])
        self.assertEqual(res["total"], expected)

    @patch.object(combat_api.random, "randint", return_value=7)
    def test_r2_18_canonical_release_updates_count(self, mock_randint):
        """T-R2-18：execute_passed_peace_treaty→recall_from_war 后 mobilized_legion_count 下降。"""
        war = self._make_war()
        self._recruit_and_assign([1, 2, 3], war.id)
        combat_api.do_combat_action(self.state, "player_opt", war.id, "attack")
        data = self._view()
        self.assertEqual(data["mobilized_legion_count"], 3)
        # canonical 释放：停战批准 → recall_from_war（political_system.py:566-577 唯一释放点）
        war.set_peace_treaty_status("submitted")
        from src.core.systems.political_system import PoliticalSystem
        PoliticalSystem(self.state).execute_passed_peace_treaty(war)
        ms = self.state.get_military_system()
        self.assertEqual(len(ms.get_active_legions()), 0, "释放后 ACTIVE 集清空")
        data2 = self._view()
        self.assertEqual(data2["mobilized_legion_count"], 0, "GUI 概览自动跟随权威状态")

    def test_r2_19_no_lifecycle_mutation_introduced(self):
        """T-R2-19：无 War/Legion 生命周期 mutation 被 R2 引入（源审计 + 行为双证）。"""
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        war_path = os.path.join(base, "src", "core", "systems", "war_system.py")
        mil_path = os.path.join(base, "src", "core", "systems", "military_system.py")
        with open(war_path, encoding="utf-8") as f:
            war_src = f.read()
        with open(mil_path, encoding="utf-8") as f:
            mil_src = f.read()
        # R2 未触碰这两个 Core 文件（无 R2 新字段/符号）
        self.assertNotIn("mobilized_legion_count", war_src)
        self.assertNotIn("mobilized_legion_count", mil_src)
        # enter_truce 零 recall（TRUCE 不自动释放军团，war_system.py:103-133）
        start = war_src.index("def enter_truce")
        end = war_src.index("def _move_to_truce", start)
        self.assertNotIn("recall", war_src[start:end])
        # apply_battle_results 收敛（D-2，WP-G GB）：DEFEAT/DISASTER 委托 apply_land_casualties
        # （S2 唯一伤亡 mutation owner——随机 ceil-half DESTROYED / 全灭；无前缀 DISBANDED/recall 循环）
        start = mil_src.index("def apply_battle_results")
        end = mil_src.index("# ========== 显示", start)
        non_decisive = mil_src[start:end]
        self.assertIn("apply_land_casualties", non_decisive)
        self.assertNotIn("LegionStatus.DISBANDED", non_decisive)
        # 行为双证：STALEMATE→TRUCE 后军团仍 ACTIVE（见 T-R2-12）；war_system 的
        # recall_from_war 调用点（:487/:700）均位于 canonical 释放流程（treaty 批准/解散处理），
        # 不在 enter_truce —— 释放点唯一性由 T-R2-18 行为断言承载。


if __name__ == "__main__":
    unittest.main()
