# src/tests/test_api/test_senate_api.py
import unittest
from unittest.mock import MagicMock, patch
from src.core.game_state import GameState
from src.api import senate_api
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.war import War, WarType, WarStatus  # 确保导入 WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.entities.province import Province
from src.api.senate_api import get_eligible_governor_candidates, is_governor_position_occupied


class TestSenateAPI(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.state.mark_phase_executed("population")
        self.state._treasury = 500

        # 手动初始化战争、军事、海军系统（senate_api 测试需要）
        self.state._war_system = WarSystem(self.state)
        self.state._war_system.load_wars_from_json("wars.json")
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        # 创建派系
        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.faction2 = Faction(id="populares", name="Populares", treasury=30)
        self.state.add_faction(self.faction1)
        self.state.add_faction(self.faction2)

        # 创建人物
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

        # 为 populaires 派系也添加一个贵族元老（便于 resolve_senate 测试）
        self.populares_senator = Figure(id=4, name="平民派元老", faction_id="populares", age=45)
        self.populares_senator.class_tier = ClassTier.NOBILE
        self.populares_senator.influence = 80
        self.state.add_member(self.populares_senator)
        self.faction2.member_ids.append(4)

        # 设置当前玩家
        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
            "player2": MagicMock(player_id="player2", faction_id="populares", player_type="human")
        }
        self.state._current_player_id = "player1"
        self.state._turn_order = ["player1", "player2"]
        self.assertIsNotNone(self.state.get_war_system())

    def test_get_senate_initial_info(self):
        result = senate_api.get_senate_initial_info(self.state)
        self.assertTrue(result["success"])
        data = result["data"]
        self.assertIn("faction_leaders", data)
        self.assertIn("presiding_officer", data)
        self.assertEqual(data["presiding_officer"]["figure_id"], 1)  # 执政官

    def test_get_senate_view_readonly(self):
        result = senate_api.get_senate_view(self.state, "player1")

        self.assertTrue(result["success"])
        data = result["data"]
        self.assertEqual(data["phase_id"], "senate")
        self.assertEqual(data["viewer_player_id"], "player1")
        self.assertEqual(data["interaction_mode"], "readonly")
        self.assertFalse(data["actionable"])
        self.assertFalse(data["can_create_proposal"])
        self.assertFalse(data["can_vote"])
        self.assertFalse(data["can_resolve"])
        # WP-D AU-2：DTO capability 新字段存在（值由 authority 决定）
        self.assertIn("viewer_has_consul", data)
        self.assertIn("can_select_proposal", data)
        self.assertIn("can_propose", data)
        self.assertIn("can_trigger_ai_proposer", data)
        self.assertIn("direct_actions", data)
        self.assertIn("public_announcement", data)
        self.assertIn("summary", data)
        self.assertIn("faction_leaders", data)
        self.assertIn("presiding_officer", data)
        self.assertIn("active_foreign_wars", data)
        self.assertIn("war_threats", data)
        self.assertIn("pending_peace_treaties", data)
        self.assertIn("governor_vacancies", data)
        self.assertIn("pending_contracts", data)
        self.assertTrue(data["warnings"])

    def test_get_senate_view_rejects_invalid_viewer(self):
        result = senate_api.get_senate_view(self.state, "missing_player")

        self.assertFalse(result["success"])
        self.assertIn("Viewer player not found", result["message"])

    def test_get_senate_view_rejects_invalid_state(self):
        result = senate_api.get_senate_view(None, "player1")

        self.assertFalse(result["success"])
        self.assertIn("无效的游戏状态", result["message"])

    def test_propose_war(self):
        # 创建威胁战争，需要提供 war_type 和 strength
        war = War(id="war1", name="测试战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT  # 设置为威胁状态
        ws = self.state.get_war_system()
        ws._threats.append(war)  # 加入威胁列表

        result = senate_api.propose(self.state, "player1", "war", war_id="war1", legions=6)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["proposal_id"], 1)

        proposals = self.state.get_senate_proposals()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["type"], "war")
        self.assertEqual(proposals[0]["war_id"], "war1")
        self.assertEqual(proposals[0]["legions"], 6)

    def test_propose_not_consul(self):
        # 将当前玩家改为非执政官派系
        self.state._current_player_id = "player2"
        result = senate_api.propose(self.state, "player2", "war", war_id="war1", legions=6)
        self.assertFalse(result["success"])
        self.assertIn("只有执政官可以提出提案", result["message"])

    def test_vote(self):
        # 先添加一个提案
        proposal_id = self.state.add_senate_proposal({"type": "war", "war_id": "war1", "legions": 6})
        result = senate_api.vote(self.state, "player1", [proposal_id], [True])
        self.assertTrue(result["success"])
        # 检查投票记录
        self.assertIn("player1", self.state._senate_pending["votes"])
        self.assertIn(proposal_id, self.state._senate_pending["votes"]["player1"])
        self.assertTrue(self.state._senate_pending["votes"]["player1"][proposal_id])

    def test_vote_twice(self):
        proposal_id = self.state.add_senate_proposal({"type": "war"})
        senate_api.vote(self.state, "player1", [proposal_id], [True])
        result = senate_api.vote(self.state, "player1", [proposal_id], [False])
        self.assertFalse(result["success"])
        self.assertIn("均已投过票", result["message"])

    def test_veto(self):
        # 切换当前玩家为 player2（保民官所在派系）
        self.state._current_player_id = "player2"
        proposal_id = self.state.add_senate_proposal({"type": "war"})
        result = senate_api.veto(self.state, "player2", [proposal_id])
        self.assertTrue(result["success"])
        self.assertIn(proposal_id, self.state._senate_pending["vetoes"])

    def test_veto_not_tribune(self):
        # 当前玩家为 optimates，没有保民官
        proposal_id = self.state.add_senate_proposal({"type": "war"})
        result = senate_api.veto(self.state, "player1", [proposal_id])
        self.assertFalse(result["success"])
        self.assertIn("只有保民官可以行使否决权", result["message"])

    @patch("src.core.systems.political_system.PoliticalSystem.execute_war_declaration")
    @patch("src.core.systems.political_system.PoliticalSystem.execute_ai_takeover_direct_action")
    def test_resolve_senate(self, mock_takeover, mock_execute):
        war = War(id="war1", name="测试战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT
        self.state.get_war_system()._threats.append(war)

        # 添加提案、投票、否决
        war_proposal_id = self.state.add_senate_proposal(
            {"type": "war", "war_id": "war1", "legions": 6, "consul_id": 1})
        self.state.record_senate_vote("player1", war_proposal_id, True)  # 支持
        # 模拟另一个派系投票（通过决策器）
        # 使用 mock 决策器返回支持
        mock_decider = MagicMock()
        mock_decider.decide_vote.return_value = True
        result = senate_api.resolve_senate(self.state, vote_decider=mock_decider)
        self.assertTrue(result["success"])
        self.assertIn(war_proposal_id, result["data"]["passed_proposals"])
        # WP-D AU-5/AU-6：resolve 数据含 direct_actions 快照 + public_announcement（enacted 仅最终通过）
        self.assertIn("direct_actions", result["data"])
        self.assertIn("public_announcement", result["data"])
        enacted = result["data"]["public_announcement"]["enacted_proposals"]
        self.assertEqual(len(enacted), 1)
        self.assertEqual(enacted[0]["proposal_id"], war_proposal_id)
        self.assertEqual(enacted[0]["type"], "war")
        self.assertIn("key_parameters", enacted[0])
        mock_execute.assert_called_once()
        # AU-R1-05a（G3 C1，D-1 采纳）：resolve_senate 零 takeover mutation——AI 接管
        # 唯一触发点 = auto_submit_proposals 尾部，resolve 不得触发 execute_ai_takeover_direct_action
        mock_takeover.assert_not_called()

    def test_propose_peace_manually(self):
        """手动模式下停战提案应将草案状态设置为 submitted"""
        # 创建一个停战战争，并设置 pending 草案
        war = War(id="war_peace_test", name="停战测试战争", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        treaty = {"indemnity": 100, "duration": 3, "status": "pending"}
        war.set_peace_treaty(treaty)

        ws = self.state.get_war_system()
        ws._truce_wars.append(war)

        # 调用 propose 提交停战提案
        result = senate_api.propose(self.state, "player1", "peace", war_id="war_peace_test")

        self.assertTrue(result["success"])
        # 验证草案状态已变为 submitted
        self.assertEqual(war.peace_treaty["status"], "submitted")

class TestGovernorEligibility(unittest.TestCase):
    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state._provinces = {}  # 清空默认行省

        # 创建一些测试人物
        self.consul_history = Figure(id=1, name="卸任执政官", faction_id="test")
        self.consul_history.office_history.append(type('Term', (), {'office_type': 'consul', 'end_turn': 10})())
        self.consul_history.office = None

        self.praetor_history = Figure(id=2, name="卸任大法官", faction_id="test")
        self.praetor_history.office_history.append(type('Term', (), {'office_type': 'praetor', 'end_turn': 8})())
        self.praetor_history.office = None

        self.current_consul = Figure(id=3, name="现任执政官", faction_id="test")
        self.current_consul.office_history.append(type('Term', (), {'office_type': 'consul', 'end_turn': 10})())
        self.current_consul.office = "consul"

        self.absent = Figure(id=4, name="出征人物", faction_id="test")
        self.absent.is_absent = True

        self.no_history = Figure(id=5, name="无历史", faction_id="test")

        for fig in [self.consul_history, self.praetor_history, self.current_consul, self.absent, self.no_history]:
            self.state.add_member(fig)

    def test_get_eligible_proconsul(self):
        candidates = get_eligible_governor_candidates(self.state, "proconsul")
        ids = [c.id for c in candidates]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)
        self.assertNotIn(3, ids)
        self.assertNotIn(4, ids)
        self.assertNotIn(5, ids)

    def test_get_eligible_propraetor(self):
        candidates = get_eligible_governor_candidates(self.state, "propraetor")
        ids = [c.id for c in candidates]
        self.assertIn(2, ids)
        self.assertNotIn(1, ids)
        self.assertNotIn(3, ids)
        self.assertNotIn(4, ids)
        self.assertNotIn(5, ids)

    def test_sort_by_recent_turn(self):
        # 添加一个卸任更早的执政官
        older = Figure(id=6, name="更早卸任", faction_id="test")
        older.office_history.append(type('Term', (), {'office_type': 'consul', 'end_turn': 5})())
        older.office = None
        self.state.add_member(older)
        candidates = get_eligible_governor_candidates(self.state, "proconsul")
        ids = [c.id for c in candidates]
        # 卸任回合 10 的应在 5 之前
        self.assertEqual(ids, [1, 6])  # 按卸任回合倒序

    def test_is_governor_position_occupied(self):
        # 创建行省
        province1 = Province(1, "西西里", 1000)
        province1._governor_id = 1
        province2 = Province(2, "撒丁", 1000)
        province2._governor_designate_id = 2
        self.state.add_province(province1)
        self.state.add_province(province2)

        self.assertTrue(is_governor_position_occupied(self.state, 1))
        self.assertTrue(is_governor_position_occupied(self.state, 2))
        self.assertFalse(is_governor_position_occupied(self.state, 3))


class TestAutoSubmitProposals(unittest.TestCase):
    """测试 auto_submit_proposals 函数"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = type('MockTurn', (), {'turn_number': 1, 'year': -264, 'leader_ids': []})()
        self.state.mark_phase_executed("population")
        self.state._treasury = 500

        # 初始化系统
        self.state._war_system = WarSystem(self.state)
        self.state._war_system.load_wars_from_json("wars.json")
        self.state._military_system = MilitarySystem(self.state)
        self.state._naval_system = NavalSystem(self.state)

        # 创建派系
        self.faction1 = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction1)

        # 创建执政官
        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.consul.influence = 50
        self.state.add_member(self.consul)
        self.faction1.member_ids.append(1)

        # 设置玩家
        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        self.state._current_player_id = "player1"

    def test_auto_submit_proposals_no_consul(self):
        """无执政官时返回失败"""
        # 移除执政官官职
        for m in self.state.get_living_members():
            m.office = None
        result = senate_api.auto_submit_proposals(self.state)
        self.assertFalse(result["success"])
        self.assertIn("没有执政官", result["message"])

    def test_auto_submit_proposals_empty_state(self):
        """空状态（无战争/空缺/合同/公地）返回成功但空列表"""
        # 使用测试配置关闭所有提议
        self.state.config.testing.propose_war_chance = 0.0
        self.state.config.testing.always_declare = False
        # 同时关闭土地法案提案（默认 30% 概率）
        self.state.config.political_rules.land_proposal.sale_chance = 0.0
        self.state.config.political_rules.land_proposal.distribution_chance = 0.0
        result = senate_api.auto_submit_proposals(self.state)
        # 当没有提案生成时，如果无错误则 success=True，有 0 项提案
        self.assertTrue(result["success"])
        self.assertEqual(len(result["data"].get("proposals", [])), 0)

    def test_auto_submit_proposals_invalid_state(self):
        """None 状态返回失败"""
        result = senate_api.auto_submit_proposals(None)
        self.assertFalse(result["success"])

    def test_auto_submit_proposals_war_threat(self):
        """威胁战争：自动宣战提案（P1-a：legions 由 config 派生值域 [1..可用池] 生成）"""
        # 添加威胁战争
        war = War(id="war_test_threat", name="测试威胁战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT
        self.state.get_war_system()._threats.append(war)
        # 确保必定宣战
        self.state.config.testing.always_declare = True
        # P1-a: 权威值域 config（不再读 testing.min/max_legions）
        self.state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        proposals = result["data"].get("proposals", [])
        war_proposals = [p for p in proposals if p["type"] == "war"]
        self.assertGreaterEqual(len(war_proposals), 1)
        self.assertEqual(war_proposals[0]["war_id"], "war_test_threat")
        # 生成值 ∈ [1 .. 可用池]（MilitarySystem 默认 25 个 UNRAISED）
        legions = war_proposals[0]["legions"]
        self.assertGreaterEqual(legions, 1)
        self.assertLessEqual(legions, len(self.state.get_military_system().get_available_legions()))

    def test_auto_submit_proposals_war_bypass_turn_check(self):
        """确保 war 提案绕过回合检查（P1-a 值域 config 派生）"""
        war = War(id="war_bypass", name="绕过检查战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT
        self.state.get_war_system()._threats.append(war)
        self.state.config.testing.always_declare = True
        self.state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        # 验证提案已存入 state
        stored = self.state.get_senate_proposals()
        self.assertGreaterEqual(len(stored), 1)
        self.assertEqual(stored[0]["type"], "war")
        self.assertGreaterEqual(stored[0]["legions"], 1)
        self.assertLessEqual(stored[0]["legions"], len(self.state.get_military_system().get_available_legions()))

    def test_auto_submit_proposals_peace_treaty(self):
        """待决停战：自动和平提案"""
        ws = self.state.get_war_system()
        war = War(id="peace_test", name="停战测试战争", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        treaty = {"indemnity": 100, "duration": 3, "status": "pending"}
        war.set_peace_treaty(treaty)
        ws._truce_wars.append(war)

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        proposals = result["data"].get("proposals", [])
        peace_proposals = [p for p in proposals if p["type"] == "peace"]
        self.assertGreaterEqual(len(peace_proposals), 1)
        self.assertEqual(peace_proposals[0]["war_id"], "peace_test")

    def test_auto_submit_proposals_returns_valid_structure(self):
        """返回值结构符合 api_response 规范"""
        result = senate_api.auto_submit_proposals(self.state)
        self.assertIn("success", result)
        self.assertIn("message", result)
        self.assertIn("data", result)
        self.assertIn("errors", result)
        self.assertIn("proposals", result["data"])

    def test_auto_submit_proposals_custom_deciders(self):
        """传入自定义决策器"""
        from src.core.deciders.impl.auto_budget_decider import AutoBudgetDecider
        from src.core.deciders.impl.auto_land_proposal_decider import AutoLandProposalDecider

        budget = AutoBudgetDecider()
        land = [AutoLandProposalDecider("populares", "distribution")]
        result = senate_api.auto_submit_proposals(
            self.state, budget_decider=budget, land_proposal_deciders=land
        )
        self.assertIn("success", result)

    def test_auto_submit_proposals_all_types(self):
        """综合场景：所有 5 种提案类型"""
        ws = self.state.get_war_system()

        # 宣战：添加威胁战争
        war1 = War(id="w1", name="威胁战争W1", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war1.status = WarStatus.THREAT
        ws._threats.append(war1)
        self.state.config.testing.always_declare = True
        self.state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}

        # 和平：添加停战
        war2 = War(id="w2", name="停战战争W2", war_type=WarType.FOREIGN, strength=5)
        war2.status = WarStatus.TRUCE
        war2.set_peace_treaty({"indemnity": 100, "duration": 3, "status": "pending"})
        ws._truce_wars.append(war2)

        # 总督：添加行省和候选人
        old_consul = Figure(id=5, name="前执政官", faction_id="optimates", age=60)
        old_consul.office = "ex-consul"
        old_consul.class_tier = ClassTier.NOBILE
        old_consul.office_history.append(
            type('Term', (), {'office_type': 'consul', 'end_turn': 10})()
        )
        self.state.add_member(old_consul)
        self.faction1.member_ids.append(5)

        province = Province(province_id=10, name="西西里", total_land=1000, conquered=True, governor_type="proconsul")
        self.state.add_province(province)

        # 土地：设置公地（get_national_public_land 会遍历 provinces）
        # 测试默认 state 可能已有 provinces，不依赖 land 提案

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        proposals = result["data"].get("proposals", [])
        types_found = set(p["type"] for p in proposals)
        self.assertIn("war", types_found)
        self.assertIn("peace", types_found)
        # 总督任命依赖候选人选举逻辑，可能因随机性跳过行省
        # budget 和 land 依赖合同/公地数据，不强制断言

    def test_auto_submit_war_range_conservation(self):
        """T-AUTO-1：war 分支不再读 testing.min/max_legions；生成值 ∈ [1..可用池] 且多战争总和守恒。"""
        self.state.config.testing.always_declare = True
        # 即使 testing.min/max 被设为越界值，也不得影响生成值域
        self.state.config.testing.min_legions = 100
        self.state.config.testing.max_legions = 100
        self.state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}

        ws = self.state.get_war_system()
        war1 = War(id="w_auto_1", name="自动宣战1", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war1.status = WarStatus.THREAT
        ws._threats.append(war1)
        war2 = War(id="w_auto_2", name="自动宣战2", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war2.status = WarStatus.THREAT
        ws._threats.append(war2)

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        pool = len(self.state.get_military_system().get_available_legions())
        war_proposals = [p for p in result["data"].get("proposals", []) if p["type"] == "war"]
        self.assertGreaterEqual(len(war_proposals), 1)
        for p in war_proposals:
            self.assertGreaterEqual(p["legions"], 1)
            self.assertLessEqual(p["legions"], pool)
        # 多战争总和守恒（success 提案合计 ≤ 可用池）
        total = sum(p["legions"] for p in war_proposals)
        self.assertLessEqual(total, pool)
        # 未被谓词拒绝：errors 无「可用军团不足」
        for err in result["errors"]:
            self.assertNotIn("可用军团不足", err)

    def test_auto_submit_budget_in_range(self):
        """T-AUTO-2：budget 分支不再读 code-default margin；生成值 ∈ [min,max]（per-contract 派生）。"""
        self.state.config.economic_rules.senate_budget = {
            "public_works_min": 1, "public_works_max_ratio": 1.5,
            "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
        }
        contract = self.state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        contract.status = ContractStatus.PENDING

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        budget_proposals = [p for p in result["data"].get("proposals", []) if p["type"] == "budget"]
        self.assertGreaterEqual(len(budget_proposals), 1)
        for p in budget_proposals:
            # 值域 [1, 150]（base=100，PUBLIC_WORKS）
            self.assertGreaterEqual(p["modified_budget"], 1)
            self.assertLessEqual(p["modified_budget"], 150)

    def test_auto_submit_all_pass_predicate(self):
        """T-AUTO-3：auto_submit war/budget 经 propose→create_proposal→_populate_proposal 全部 success（零谓词拒绝）。"""
        self.state.config.testing.always_declare = True
        self.state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}
        self.state.config.economic_rules.senate_budget = {
            "public_works_min": 1, "public_works_max_ratio": 1.5,
            "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
        }
        ws = self.state.get_war_system()
        war = War(id="w_auto_3", name="自动宣战3", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT
        ws._threats.append(war)
        contract = self.state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        contract.status = ContractStatus.PENDING

        result = senate_api.auto_submit_proposals(self.state)
        self.assertTrue(result["success"])
        self.assertEqual(result["errors"], [])
        types = {p["type"] for p in result["data"].get("proposals", [])}
        self.assertIn("war", types)
        self.assertIn("budget", types)
        # 提案均已成功写入 state（即经 _populate_proposal 全 success）
        stored_types = {p["type"] for p in self.state.get_senate_proposals()}
        self.assertIn("war", stored_types)
        self.assertIn("budget", stored_types)


class TestWP05VWarDetail(unittest.TestCase):
    """WP-05V V1: DP-4 war 提案费用文案 + P1-1 economic_rules 缺参降级。"""

    def _make_state(self, economic_rules=None):
        config = {}
        if economic_rules is not None:
            config["economic_rules"] = economic_rules
        return GameState.create_for_testing(config)

    def _war_options(self, state, threat_level=3):
        info = {"war_threats": [{"war_id": "w1", "name": "测试战争", "threat_level": threat_level}]}
        options = senate_api._build_proposal_options(state, info)
        return [o for o in options if o["type"] == "war"]

    def test_war_option_detail_contains_cost_text(self):
        state = self._make_state({
            "legion_recruit_cost": 4,
            "legion_maintenance_base": 8,
            "veteran_maintenance_bonus": 1,
        })
        wars = self._war_options(state)
        self.assertEqual(len(wars), 1)
        detail = wars[0]["detail"]
        self.assertIn("招募费（一次性）4 T", detail)
        self.assertIn("新军团 8 T", detail)
        self.assertIn("老兵军团 9 T", detail)

    def test_war_option_detail_missing_economic_rules_degrades(self):
        state = self._make_state()  # economic_rules 整节缺失
        wars = self._war_options(state)
        self.assertEqual(len(wars), 1)
        detail = wars[0]["detail"]
        self.assertIn("招募费（一次性）4 T", detail)
        self.assertIn("新军团 8 T", detail)
        self.assertIn("老兵军团 9 T", detail)

    def test_war_option_detail_partial_economic_rules_degrades(self):
        # veteran_maintenance_bonus 缺失 → 默认 1（老兵 = 8 + 1 = 9）
        state = self._make_state({"legion_recruit_cost": 4, "legion_maintenance_base": 8})
        wars = self._war_options(state)
        self.assertEqual(len(wars), 1)
        detail = wars[0]["detail"]
        self.assertIn("招募费（一次性）4 T", detail)
        self.assertIn("新军团 8 T", detail)
        self.assertIn("老兵军团 9 T", detail)


class TestWP05VGovernorCandidateAttrs(unittest.TestCase):
    """WP-05V V1: DP-6 candidate DTO 四字段（class_tier/martial/intelligence/charisma）。"""

    def test_governor_appointments_candidate_has_4_attrs(self):
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)

        faction = Faction(id="optimates", name="Optimates", treasury=50)
        state.add_faction(faction)

        candidate = Figure(id=1, name="候选人", faction_id="optimates", age=50)
        candidate.class_tier = ClassTier.NOBILE
        candidate.martial = 7
        candidate.intelligence = 6
        candidate.charisma = 5
        candidate.office = None
        candidate.office_history.append(type('Term', (), {'office_type': 'consul', 'end_turn': 10})())
        state.add_member(candidate)
        faction.member_ids.append(1)

        province = Province(province_id=10, name="西西里", total_land=1000, conquered=True, governor_type="proconsul")
        state.add_province(province)

        result = senate_api._build_governor_appointments(state)
        pending = result["pending_provinces"]
        self.assertEqual(len(pending), 1)
        candidates = pending[0]["candidates"]
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c["class_tier"], "NOBILE")
        self.assertEqual(c["martial"], 7)
        self.assertEqual(c["intelligence"], 6)
        self.assertEqual(c["charisma"], 5)


class TestWP05VParamsPassthrough(unittest.TestCase):
    """WP-05V V2: propose_many params 透传 + budget/land 边界契约。"""

    def setUp(self):
        self.state = GameState.create_for_testing({})
        self.state.turn = GameTurn(turn_number=1, year=-264)
        self.faction = Faction(id="optimates", name="Optimates", treasury=50)
        self.state.add_faction(self.faction)
        self.consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        self.consul.office = "consul"
        self.consul.class_tier = ClassTier.NOBILE
        self.state.add_member(self.consul)
        self.faction.member_ids.append(1)
        self.state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        self.state._current_player_id = "player1"

    def test_propose_many_params_passthrough(self):
        # fixture：war w1 存在 + 可用池 ≥ 8；contract 存在且 120 ∈ [1, base×150%]（PUBLIC_WORKS base=100）
        ws = WarSystem(self.state)
        self.state._war_system = ws
        war = War(id="w1", name="威胁战争W1", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT
        ws._threats.append(war)
        self.state._military_system = MilitarySystem(self.state)
        contract = self.state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        contract.status = ContractStatus.PENDING
        self.state.config.economic_rules.senate_budget = {
            "public_works_min": 1, "public_works_max_ratio": 1.5,
            "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
        }
        self.state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}

        specs = [
            {"type": "war", "params": {"war_id": "w1", "legions": 8}},
            {"type": "budget", "params": {"contract_id": contract.id, "modified_budget": 120}},
            {"type": "land", "params": {"act_type": "sale", "amount_C": 300}},
        ]
        result = senate_api.propose_many(self.state, "player1", specs)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["data"]["created"]), 3)

        proposals = self.state.get_senate_proposals()
        by_type = {p["type"]: p for p in proposals}
        self.assertEqual(by_type["war"]["war_id"], "w1")
        self.assertEqual(by_type["war"]["legions"], 8)
        self.assertEqual(by_type["budget"]["contract_id"], contract.id)
        self.assertEqual(by_type["budget"]["modified_budget"], 120)
        # AU-7：land payload 主字段 amount_C（int）；percent 派生（默认公地 1000 → 300/1000 = 0.3）
        self.assertEqual(by_type["land"]["act_type"], "sale")
        self.assertEqual(by_type["land"]["amount_C"], 300)
        self.assertAlmostEqual(by_type["land"]["percent"], 0.3)

    def test_propose_budget_clamp(self):
        # D-3 处置（Test Matrix T014-5 语义）：越界值被权威谓词拒绝（前端 clamp 不能替代 Core 拒绝）；
        # 合法值仍透传存储（round-trip 保持）。
        contract = self.state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        contract.status = ContractStatus.PENDING
        self.state.config.economic_rules.senate_budget = {
            "public_works_min": 1, "public_works_max_ratio": 1.5,
            "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
        }
        # 建造合同值域 [1, 150]：0 < min → 权威拒绝（0 不再被真值判断静默替换为 base_cost）
        result = senate_api.propose(self.state, "player1", "budget", contract_id=contract.id, modified_budget=0)
        self.assertFalse(result["success"])
        self.assertEqual(len(self.state.get_senate_proposals()), 0)
        # 合法边界值 120 ∈ [1,150] → 成功透传
        result = senate_api.propose(self.state, "player1", "budget", contract_id=contract.id, modified_budget=120)
        self.assertTrue(result["success"])
        proposals = self.state.get_senate_proposals()
        self.assertEqual(proposals[0]["modified_budget"], 120)

    def test_propose_land_amount_c_zero_rejected(self):
        # AU-7：amount_C 主输入值域校验——0 违反 1≤amount_C → 权威拒绝
        result = senate_api.propose(self.state, "player1", "land", act_type="sale", amount_C=0)
        self.assertFalse(result["success"])
        self.assertEqual(len(self.state.get_senate_proposals()), 0)
        # percent 不再作为独立输入接受（D-01 canonical conversion，DA Plan P-5）
        result = senate_api.propose(self.state, "player1", "land", act_type="sale", percent=0.1)
        self.assertFalse(result["success"])
        self.assertIn("amount_C", result["message"])


class TestWP05VGovernorIA(unittest.TestCase):
    """WP-05V G6 Narrow: FC-14 governor 提案条件存在 + 提交/标签路径（AC-22/23/24 后端）。"""

    def _state_with_province_and_candidate(self):
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        faction = Faction(id="optimates", name="Optimates", treasury=50)
        state.add_faction(faction)

        consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        consul.office = "consul"
        consul.class_tier = ClassTier.NOBILE
        state.add_member(consul)
        faction.member_ids.append(1)

        candidate = Figure(id=5, name="前执政官", faction_id="optimates", age=60)
        candidate.office = None
        candidate.class_tier = ClassTier.NOBILE
        candidate.office_history.append(type('Term', (), {'office_type': 'consul', 'end_turn': 10})())
        state.add_member(candidate)
        faction.member_ids.append(5)

        province = Province(province_id=10, name="西西里", total_land=1000, conquered=True, governor_type="proconsul")
        state.add_province(province)

        state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        state._current_player_id = "player1"
        return state

    def test_no_vacancy_no_governor_option(self):
        # AC-22 后端：governor_vacancies 空 → 无 type="governor" proposal option
        state = GameState.create_for_testing({})
        info = {
            "war_threats": [],
            "pending_peace_treaties": [],
            "governor_vacancies": {},
            "pending_contracts": [],
        }
        options = senate_api._build_proposal_options(state, info)
        governor_options = [o for o in options if o["type"] == "governor"]
        self.assertEqual(len(governor_options), 0)

    def test_vacancy_generates_governor_option(self):
        # AC-23 后端：有 vacancy → 生成 type="governor" proposal（title 纯文本）
        state = self._state_with_province_and_candidate()
        info = {
            "war_threats": [],
            "pending_peace_treaties": [],
            "governor_vacancies": {
                "proconsul": [{"province_id": 10, "province_name": "西西里"}],
            },
            "pending_contracts": [],
        }
        options = senate_api._build_proposal_options(state, info)
        governor_options = [o for o in options if o["type"] == "governor"]
        self.assertEqual(len(governor_options), 1)
        self.assertEqual(governor_options[0]["title"], "总督任命 — 西西里")
        self.assertEqual(governor_options[0]["params"]["province_id"], 10)
        self.assertEqual(governor_options[0]["params"]["candidate_id"], 5)

    def test_propose_governor_and_label(self):
        # AC-24 后端：勾选 governor → propose("governor") 成功 + label 含行省/候选人
        state = self._state_with_province_and_candidate()
        result = senate_api.propose(state, "player1", "governor", province_id=10, candidate_id=5)
        self.assertTrue(result["success"])

        proposals = state.get_senate_proposals()
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["type"], "governor")
        self.assertEqual(proposals[0]["province_id"], 10)
        self.assertEqual(proposals[0]["candidate_id"], 5)

        label = senate_api._proposal_label(state, proposals[0])
        self.assertIn("总督任命", label)
        self.assertIn("西西里", label)


class TestBudgetRangeDerivation(unittest.TestCase):
    """NT-1: T014-3/4 — per-contract 权威 budget_range（ED-01）+ payload round-trip。"""

    def _make_state(self):
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        faction = Faction(id="optimates", name="Optimates", treasury=50)
        state.add_faction(faction)
        consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        consul.office = "consul"
        consul.class_tier = ClassTier.NOBILE
        state.add_member(consul)
        faction.member_ids.append(1)
        state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        state._current_player_id = "player1"
        state.config.economic_rules.senate_budget = {
            "public_works_min": 1, "public_works_max_ratio": 1.5,
            "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
        }
        return state

    def test_public_works_range_formula(self):
        # T014-3 建造：min=1T（绝对）/ max=base×150% / step=1 / default=base
        state = self._make_state()
        contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        r = senate_api._budget_range_for_contract(state, contract)
        self.assertEqual(r, {"min": 1, "max": 150, "step": 1, "default": 100})

    def test_tax_farming_range_formula(self):
        # T014-3 包税：min=base×75% / max=base×200% / step=1 / default=base
        state = self._make_state()
        contract = state.create_contract(ContractType.TAX_FARMING, province_id=1, base_cost=80, current_turn=1)
        r = senate_api._budget_range_for_contract(state, contract)
        self.assertEqual(r, {"min": 60, "max": 160, "step": 1, "default": 80})

    def test_budget_range_missing_config_returns_none(self):
        # 防御：config 缺 senate_budget → None（不伪造 20-200）
        state = GameState.create_for_testing({})
        contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        self.assertIsNone(senate_api._budget_range_for_contract(state, contract))

    def test_budget_option_carries_budget_range(self):
        # T014-3：option 携带 budget_range（QML Slider 值域来源），modified_budget 初始 = default
        state = self._make_state()
        contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        contract.status = ContractStatus.PENDING
        info = {"pending_contracts": [{
            "contract_id": contract.id, "name": contract.name,
            "type": contract.contract_type.value, "base_cost": contract.base_cost,
            "expected_profit": contract.expected_profit,
        }]}
        options = senate_api._build_proposal_options(state, info)
        budget_opts = [o for o in options if o["type"] == "budget"]
        self.assertEqual(len(budget_opts), 1)
        self.assertEqual(budget_opts[0]["params"]["modified_budget"], 100)
        self.assertEqual(budget_opts[0]["budget_range"], {"min": 1, "max": 150, "step": 1, "default": 100})

    def test_budget_payload_round_trip(self):
        # T014-4：提交值 = 用户选择值（120 ∈ [1,150]）透传存储
        state = self._make_state()
        contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
        contract.status = ContractStatus.PENDING
        result = senate_api.propose(state, "player1", "budget", contract_id=contract.id, modified_budget=120)
        self.assertTrue(result["success"])
        proposals = state.get_senate_proposals()
        self.assertEqual(proposals[0]["modified_budget"], 120)


class TestLegionOptionsDerivation(unittest.TestCase):
    """NT-3: T015-3/4/13 — legion_options 权威值域（ED-02）+ default=4 + round-trip。"""

    def _make_state(self):
        state = GameState.create_for_testing({})
        state.turn = GameTurn(turn_number=1, year=-264)
        faction = Faction(id="optimates", name="Optimates", treasury=50)
        state.add_faction(faction)
        consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
        consul.office = "consul"
        consul.class_tier = ClassTier.NOBILE
        state.add_member(consul)
        faction.member_ids.append(1)
        state._players = {
            "player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human"),
        }
        state._current_player_id = "player1"
        state._war_system = WarSystem(state)
        state._military_system = MilitarySystem(state)
        state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}
        return state

    def _add_threat(self, state, war_id="w1"):
        war = War(id=war_id, name="威胁战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
        war.status = WarStatus.THREAT
        state.get_war_system()._threats.append(war)
        return war

    def test_legion_options_equals_available_pool(self):
        # T015-3：allowed == [1 .. available_pool]，min=1，max=pool，default=4（T015-13）
        state = self._make_state()
        war = self._add_threat(state)
        pool = len(state.get_military_system().get_available_legions())
        opts = senate_api._legion_options_for_war(state, war)
        self.assertEqual(opts["min"], 1)
        self.assertEqual(opts["max"], pool)
        self.assertEqual(opts["default"], 4)
        self.assertEqual(opts["allowed"], list(range(1, pool + 1)))

    def test_legion_option_carries_default_4(self):
        # T015-13：war option params.legions 初始 = config 派生 default（=4），携带 legion_options
        state = self._make_state()
        self._add_threat(state)
        info = {"war_threats": [{"war_id": "w1", "name": "测试战争", "threat_level": 3}]}
        options = senate_api._build_proposal_options(state, info)
        war_opts = [o for o in options if o["type"] == "war"]
        self.assertEqual(len(war_opts), 1)
        self.assertEqual(war_opts[0]["params"]["legions"], 4)
        self.assertEqual(war_opts[0]["legion_options"]["default"], 4)
        pool = len(state.get_military_system().get_available_legions())
        self.assertEqual(war_opts[0]["legion_options"]["allowed"], list(range(1, pool + 1)))

    def test_legion_payload_round_trip(self):
        # T015-4：选中 N → payload legions == N（4 ∈ [1, pool]）
        state = self._make_state()
        self._add_threat(state)
        result = senate_api.propose(state, "player1", "war", war_id="w1", legions=4)
        self.assertTrue(result["success"])
        proposals = state.get_senate_proposals()
        self.assertEqual(proposals[0]["legions"], 4)

    def test_legion_options_missing_config_returns_none(self):
        # 防御：config 缺 senate_war_legions → None（不伪造 [2,4,6,8,10]）
        state = GameState.create_for_testing({})
        state._war_system = WarSystem(state)
        state._military_system = MilitarySystem(state)
        war = self._add_threat(state)
        self.assertIsNone(senate_api._legion_options_for_war(state, war))
