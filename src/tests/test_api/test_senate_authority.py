# src/tests/test_api/test_senate_authority.py
"""WP-D AU-1/AU-4: Consul Proposal Authority 四层 + Tribune Veto Authority 四层（ODR-WP-D-01 方案 B，CLOSED 2026-08-23）。

覆盖 Grill-Lite §16 场景：
- A（执政官多提案 authority 正向）/ C（非执政官 → AI proposer）/ P（未授权 API 提案 mutation fail-closed）
- Q（人类持 eligible Tribune → 手动否决权）/ R（人类无 Tribune → 锁定 + AI）/ S（未授权 veto mutation fail-closed）
  / T（AI Tribune 路径）

⚠️ Tribune eligible 语义按 ODR-WP-D-01 方案 B（Owner 裁决 2026-08-23）：在职 + 未死亡，is_absent 不参与判定
（法律上保民官不存在缺席）。原 absent 用例已改为防线用例：防线 1（派遣/任命路径拒绝在职 tribune，fail-closed）
+ 防线 2（_set_absent / 模块级 guard 拒绝置位 absent）。
"""
import unittest
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.province import Province
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem


class TestSenateAuthorityBase(unittest.TestCase):
    """共享配方：optimates 拥有 consul（player1），populares 拥有 tribune（player2）。"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        for phase in ["mortality", "revenue", "forum", "population"]:
            self.state.mark_phase_executed(phase)
        self.state._war_system = WarSystem(self.state)
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.faction2 = Faction(id="populares", name="Populares", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.consul.influence = 50
        self.state.add_member(self.consul)
        self.faction1.member_ids.append(1)

        self.senator = Figure(id=2, name="元老", faction_id="optimates", age=50)
        self.senator.class_tier = ClassTier.NOBILE
        self.senator.influence = 100
        self.state.add_member(self.senator)
        self.faction1.member_ids.append(2)

        self.tribune = Figure(id=3, name="保民官", faction_id="populares", age=35)
        self.tribune.office = "tribune"
        self.tribune.class_tier = ClassTier.PLEBEIAN
        self.state.add_member(self.tribune)
        self.faction2.member_ids.append(3)

        self.populares_senator = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
        self.populares_senator.class_tier = ClassTier.NOBILE
        self.populares_senator.influence = 80
        self.state.add_member(self.populares_senator)
        self.faction2.member_ids.append(4)

        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
            "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human"),
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1", "player2"]


class TestConsulAuthority(TestSenateAuthorityBase):
    """AU-1: Consul Proposal Authority 四层（Core guard / DTO / QML guard 由 G5 RENDER 覆盖 / AI routing）。"""

    def test_consul_dto_authority_full(self):
        """场景 A：player1 拥有 eligible consul → 手动提案权四字段齐备。"""
        view = senate_api.get_senate_view(self.state, "player1")
        self.assertTrue(view["success"])
        data = view["data"]
        self.assertEqual(data["current_step"], "proposal")
        self.assertIs(data["actionable"], True)
        self.assertIs(data["viewer_has_consul"], True)
        self.assertIs(data["can_select_proposal"], True)
        self.assertIs(data["can_propose"], True)
        self.assertIs(data["can_create_proposal"], True)
        self.assertIs(data["can_trigger_ai_proposer"], False)

    def test_non_consul_dto_ai_trigger(self):
        """场景 C：player2（无 consul）为当前玩家 → 手动权锁定 + can_trigger_ai_proposer=True。"""
        self.state._current_player_id = "player2"
        view = senate_api.get_senate_view(self.state, "player2")
        self.assertTrue(view["success"])
        data = view["data"]
        self.assertIs(data["actionable"], True)
        self.assertIs(data["viewer_has_consul"], False)
        self.assertIs(data["can_select_proposal"], False)
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_trigger_ai_proposer"], True)

    def test_absent_consul_boundary(self):
        """AU-1：执政官 absent → 不 eligible → 该派系手动权消失、AI proposer 接管。"""
        self.consul.is_absent = True
        view = senate_api.get_senate_view(self.state, "player1")
        data = view["data"]
        self.assertIs(data["viewer_has_consul"], False)
        self.assertIs(data["can_select_proposal"], False)
        self.assertIs(data["can_create_proposal"], False)
        self.assertIs(data["can_trigger_ai_proposer"], True)

    def test_dead_consul_not_eligible(self):
        """AU-1：执政官死亡 → 不 eligible。"""
        self.consul.is_dead = True
        view = senate_api.get_senate_view(self.state, "player1")
        self.assertIs(view["data"]["viewer_has_consul"], False)

    def test_non_consul_api_propose_fail_closed(self):
        """场景 P：非执政官派系直调 propose/propose_many → fail-closed（fallback 修正后不再误判）。"""
        self.state._current_player_id = "player2"
        self.state.turn.leader_ids = [1]  # consul 属 optimates（player1），非 player2 派系
        result = senate_api.propose(self.state, "player2", "land", act_type="sale", amount_C=50)
        self.assertFalse(result["success"])
        self.assertIn("只有执政官", result["message"])

        result2 = senate_api.propose_many(
            self.state, "player2",
            [{"type": "land", "params": {"act_type": "sale", "amount_C": 50}}],
        )
        self.assertFalse(result2["success"])
        self.assertEqual(len(self.state.get_senate_proposals()), 0)
        self.assertEqual(len(self.state.get_senate_votes_copy()), 0)


class TestTribuneAuthority(TestSenateAuthorityBase):
    """AU-4: Tribune Veto Authority 四层（ODR-WP-D-01 方案 B，CLOSED 2026-08-23）。"""

    def _enter_veto_step(self, current_player="player2"):
        """进入 tribune_veto 步：1 提案 + 决策完成 + 双方已投票。"""
        self.state.senate_proposal_decision_complete = True
        pid = self.state.add_senate_proposal({"type": "war", "war_id": "w1", "legions": 4, "consul_id": 1})
        self.state.record_senate_vote("player1", pid, True)
        self.state.record_senate_vote("player2", pid, True)
        self.state._current_player_id = current_player
        return pid

    def test_human_owns_eligible_tribune_manual_veto(self):
        """场景 Q：player2 拥有 eligible Tribune → can_veto=True / can_auto_veto=False（AI 不 override 人类）。"""
        pid = self._enter_veto_step(current_player="player2")
        view = senate_api.get_senate_view(self.state, "player2")
        data = view["data"]
        self.assertEqual(data["current_step"], "tribune_veto")
        self.assertIs(data["viewer_has_tribune"], True)
        self.assertIs(data["can_veto"], True)
        self.assertIs(data["can_auto_veto"], False)
        self.assertIs(data["can_resolve"], True)

        result = senate_api.veto(self.state, "player2", [pid])
        self.assertTrue(result["success"])
        self.assertIn(pid, self.state.get_senate_vetoes_copy())

    def test_human_without_tribune_locked_routes_ai(self):
        """场景 R：人类派系无 Tribune → can_veto=False / can_auto_veto=True（锁定 + AI 路由）。"""
        pid = self._enter_veto_step(current_player="player1")  # optimates 无 tribune
        view = senate_api.get_senate_view(self.state, "player1")
        data = view["data"]
        self.assertIs(data["viewer_has_tribune"], False)
        self.assertIs(data["can_veto"], False)
        self.assertIs(data["can_auto_veto"], True)

        result = senate_api.veto(self.state, "player1", [pid])
        self.assertFalse(result["success"])
        self.assertIn("只有保民官", result["message"])

    def test_takeover_war_rejects_faction_with_only_tribune(self):
        """防线 1（ODR-WP-D-01）：出征指挥官必须为 eligible consul——仅持 tribune 的派系被拒（fail-closed）。"""
        self.state._current_player_id = "player2"  # populares 仅有 tribune，无 consul
        result = senate_api.takeover_war(self.state, "player2", "w1")
        self.assertFalse(result["success"])
        self.assertIn("没有存活且在罗马的执政官", result["message"])

    def test_current_tribune_returns_eligible(self):
        """AU-4：_current_tribune 全局首查 eligible Tribune。"""
        self.assertEqual(senate_api._current_tribune(self.state).id, 3)

    def test_current_tribune_eligible_ignores_absent_flag(self):
        """方案 B（ODR-WP-D-01 CLOSED）：is_absent 不参与 eligible 判定——异常置位标记不剥夺资格（防线 2 保证正常路径不可达此态）。"""
        self.tribune.is_absent = True
        self.assertEqual(senate_api._current_tribune(self.state).id, 3)

    def test_ai_tribune_path_dead_tribune_skips(self):
        """场景 T（方案 B）：唯一 eligible 条件不满足（tribune 死亡）→ apply_auto_tribune_vetoes 走 skipped（不崩、不伪造否决）。"""
        self.tribune.is_dead = True
        pid = self._enter_veto_step(current_player="player2")
        result = senate_api.apply_auto_tribune_vetoes(self.state)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["vetoed"], [])
        self.assertEqual(len(self.state.get_senate_vetoes_copy()), 0)

    def test_ai_tribune_path_with_eligible_decides(self):
        """场景 T 正向：AI Tribune 权威决策（decider 注入）。"""
        from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
        pid = self._enter_veto_step(current_player="player2")
        mock_decider = MagicMock(spec=TribuneVetoDecider)
        mock_decider.decide_veto.return_value = True
        result = senate_api.apply_auto_tribune_vetoes(self.state, veto_decider=mock_decider)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["vetoed"], [pid])
        self.assertIn(pid, self.state.get_senate_vetoes_copy())

    def test_governor_proposal_rejects_tribune_candidate(self):
        """防线 1（ODR-WP-D-01）：总督任命提案拒绝在职 tribune 候选人（fail-closed，API 级）。"""
        province = Province(10, "Sicily", 1000, conquered=True, governor_type="proconsul")
        self.state.add_province(province)
        result = senate_api.propose(self.state, "player1", "governor", province_id=10, candidate_id=3)
        self.assertFalse(result["success"])
        self.assertIn("任职资格", result["message"])


if __name__ == "__main__":
    unittest.main()
