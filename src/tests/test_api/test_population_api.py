# src/tests/test_api/test_population_api.py
"""
API层单元测试 - 人口阶段相关API
"""
import pytest
from unittest.mock import MagicMock, patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.api import population_api
from src.core.i18n import i18n
from src.ui.processors.auto_player_processor import AutoPlayerProcessor

i18n.load("zh-CN")


@pytest.fixture
def state_base():
    """基础状态，无玩家，可添加派系和人物"""
    config = {
        "testing": {"bypass_player_check": False, "auto_forum": False},
        "economic_rules": {
            "land_price_per_unit": 10,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
        },
        "political_rules": {
            "min_festival_age": 30,
            "office_cooldowns": {
                "consul": 2,
                "censor": 2,
                "praetor": 2,
                "quaestor": 2,
                "tribune": 2
            },
            "offices_per_election": {
                "consul": 1,
                "censor": 1,
                "praetor": 1,
                "quaestor": 1,
                "tribune": 1
            },
            "min_ages": {
                "consul": 40,
                "censor": 42,
                "praetor": 35,
                "quaestor": 30,
                "tribune": 30
            },
            "office_rank": {
                "dictator": 6,
                "censor": 4,
                "consul": 5,
                "praetor": 3,
                "tribune": 1,
                "quaestor": 2
            },
            "office_influence_bonus": {
                "dictator": 60,
                "censor": 50,
                "consul": 40,
                "praetor": 30,
                "tribune": 20,
                "quaestor": 10,
                "proconsul": 0,
                "propraetor": 0
            },
            "ex_office_influence_bonus": {
                "ex-dictator": 30,
                "ex-censor": 25,
                "ex-consul": 20,
                "ex-praetor": 15,
                "ex-tribune": 10,
                "ex-quaestor": 5,
                "ex-proconsul": 20,
                "ex-propraetor": 15
            },
            "family_prestige": {
                "Julius": 4,
                "Cornelius": 4,
                "Claudius": 3,
                "Fabius": 3,
                "Aemilius": 2,
                "Servilius": 2
            }
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    state._population_pending = {"campaigns": [], "votes": []}
    return state


@pytest.fixture
def state_with_two_players(state_base):
    """包含两个玩家（p1人类，p2 AI）的状态"""
    player1 = Player(player_id="p1", faction_id="f1", player_type=PlayerType.HUMAN)
    player2 = Player(player_id="p2", faction_id="f2", player_type=PlayerType.AI)
    state_base.add_player(player1)
    state_base.add_player(player2)
    state_base.set_turn_order(["p1", "p2"])
    state_base.set_current_player("p1")

    faction1 = Faction(id="f1", name="Faction1", treasury=1000)
    faction2 = Faction(id="f2", name="Faction2", treasury=1000)
    state_base.add_faction(faction1)
    state_base.add_faction(faction2)

    # 添加人物
    fig1 = Figure.create_nobile(1, "f1", 45)
    fig1.wealth = 50
    fig1.popularity = 10
    fig1.update_influence()
    state_base.add_member(fig1)

    fig2 = Figure.create_nobile(2, "f2", 50)
    fig2.wealth = 60
    fig2.popularity = 12
    fig2.update_influence()
    state_base.add_member(fig2)

    fig3 = Figure.create_eques(3, "f1", 35)
    fig3.wealth = 40
    fig3.popularity = 5
    fig3.update_influence()
    state_base.add_member(fig3)

    fig4 = Figure.create_plebeian(4, "f2", 30)
    fig4.wealth = 20
    fig4.popularity = 3
    fig4.update_influence()
    state_base.add_member(fig4)

    return state_base


@pytest.fixture
def state_normal_mode(state_with_two_players):
    """正常模式（默认配置）"""
    return state_with_two_players


@pytest.fixture
def state_auto_mode(state_with_two_players):
    """全自动模式"""
    state_with_two_players.config._config["testing"]["auto_forum"] = True
    return state_with_two_players


@pytest.fixture
def state_bypass_mode(state_with_two_players):
    """全人工测试模式"""
    state_with_two_players.config._config["testing"]["bypass_player_check"] = True
    return state_with_two_players


# ========== TestCampaign ==========

class TestPopulationPending:
    def test_empty_record_copy_replace_and_clear(self, state_base):
        assert state_base.get_population_pending_snapshot() == {
            "campaigns": [],
            "votes": [],
        }

        state_base.record_population_campaign("p1", 1, 10)
        campaigns = state_base.get_population_campaigns()
        campaigns.append(("tamper", 9, 99))
        assert state_base.get_population_campaigns() == [("p1", 1, 10)]

        assert state_base.record_population_vote("p1", "consul", 1) is True
        assert state_base.record_population_vote("p1", "consul", 2) is False
        assert state_base.record_population_vote(
            "p1", "consul", 2, replace=True
        ) is True
        votes = state_base.get_population_votes()
        votes.clear()
        assert state_base.get_population_votes() == [("p1", "consul", 2)]

        state_base.clear_population_pending()
        assert state_base.get_population_pending_snapshot() == {
            "campaigns": [],
            "votes": [],
        }

class TestCampaign:
    """测试 campaign API"""

    def test_success(self, state_normal_mode):
        """正常举办庆典"""
        result = population_api.campaign(state_normal_mode, "p1", 1, 10)
        assert result["success"] is True
        assert "花费 10" in result["message"]

        fig = state_normal_mode.get_member(1)
        assert fig.wealth == 40  # 50 - 10
        assert fig.popularity == 20  # 10 + 10

        assert ("p1", 1, 10) in state_normal_mode._population_pending["campaigns"]

    def test_not_enough_wealth(self, state_normal_mode):
        """人物财富不足"""
        result = population_api.campaign(state_normal_mode, "p1", 1, 100)
        assert result["success"] is False
        assert "财富不足" in result["message"]

        fig = state_normal_mode.get_member(1)
        assert fig.wealth == 50  # 未变化

    def test_figure_not_in_faction(self, state_normal_mode):
        """人物不属于当前玩家派系"""
        result = population_api.campaign(state_normal_mode, "p1", 2, 10)
        assert result["success"] is False
        assert "不属于你的派系" in result["message"]

    def test_figure_dead(self, state_normal_mode):
        """人物已死亡"""
        fig = state_normal_mode.get_member(1)
        fig.is_dead = True
        result = population_api.campaign(state_normal_mode, "p1", 1, 10)
        assert result["success"] is False
        assert "不存在或已死亡" in result["message"]

    def test_not_current_player(self, state_normal_mode):
        """非当前玩家调用"""
        result = population_api.campaign(state_normal_mode, "p2", 1, 10)
        assert result["success"] is False
        assert "当前不是您的回合" in result["message"]

    def test_auto_mode_bypass(self, state_auto_mode):
        """自动模式下绕过权限检查"""
        # 自动模式通常 bypass_player_check=True，这里直接设置配置
        state_auto_mode.config._config["testing"]["bypass_player_check"] = True
        result = population_api.campaign(state_auto_mode, "p2", 1, 10)
        assert result["success"] is True
        fig = state_auto_mode.get_member(1)
        assert fig.wealth == 40

    def test_explicit_bypass_keeps_business_validation(self, state_normal_mode):
        result = population_api.campaign(
            state_normal_mode,
            "p2",
            1,
            100,
            bypass_permission=True
        )
        assert result["success"] is False
        assert state_normal_mode.get_member(1).wealth == 50

        result = population_api.campaign(
            state_normal_mode,
            "p2",
            999,
            10,
            bypass_permission=True
        )
        assert result["success"] is False


# ========== TestVote ==========

class TestVote:
    """测试 vote API"""

    def test_success(self, state_normal_mode):
        """正常投票"""
        # 为 fig1 添加资格
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))

        result = population_api.vote(state_normal_mode, "p1", "consul", 1)
        assert result["success"] is True
        assert "投票成功" in result["message"] or "投给" in result["message"]

        votes = state_normal_mode._population_pending["votes"]
        assert ("p1", "consul", 1) in votes

    def test_vote_for_invalid_candidate(self, state_normal_mode):
        """投票给非候选人"""
        # fig3 不符合 consul 资格
        result = population_api.vote(state_normal_mode, "p1", "consul", 3)
        assert result["success"] is False
        assert "不是此公职的合法候选人" in result["message"]

    def test_duplicate_vote_rejected(self, state_normal_mode):
        """同一玩家对同一公职重复投票应被拒绝"""
        fig1 = state_normal_mode.get_member(1)
        fig2 = state_normal_mode.get_member(2)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))

        # 第一次投票成功
        result1 = population_api.vote(state_normal_mode, "p1", "consul", 1)
        assert result1["success"] is True

        # 第二次投票应失败
        result2 = population_api.vote(state_normal_mode, "p1", "consul", 2)
        assert result2["success"] is False
        assert "已经为 CONSUL 投过票" in result2["message"]  # 根据 i18n 翻译

    def test_not_current_player(self, state_normal_mode):
        """非当前玩家调用"""
        result = population_api.vote(state_normal_mode, "p2", "consul", 1)
        assert result["success"] is False
        assert "当前不是您的回合" in result["message"]

    def test_auto_mode_bypass(self, state_auto_mode):
        """自动模式下绕过权限检查"""
        state_auto_mode.config._config["testing"]["bypass_player_check"] = True
        fig1 = state_auto_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        result = population_api.vote(state_auto_mode, "p2", "consul", 1)
        assert result["success"] is True

    def test_explicit_bypass_replaces_vote_but_keeps_candidate_validation(
        self,
        state_normal_mode
    ):
        fig1 = state_normal_mode.get_member(1)
        fig2 = state_normal_mode.get_member(2)
        fig1.office_history.append(OfficeTerm("praetor", -10, -9))
        fig2.office_history.append(OfficeTerm("praetor", -10, -9))

        assert population_api.vote(
            state_normal_mode,
            "p2",
            "consul",
            1,
            bypass_permission=True
        )["success"]
        assert population_api.vote(
            state_normal_mode,
            "p2",
            "consul",
            2,
            bypass_permission=True
        )["success"]
        assert state_normal_mode.get_population_votes() == [
            ("p2", "consul", 2)
        ]

        result = population_api.vote(
            state_normal_mode,
            "p2",
            "consul",
            3,
            bypass_permission=True
        )
        assert result["success"] is False


class TestAutoPopulationApi:
    def _processor(self, state, festival_decider=None, vote_decider=None):
        return AutoPlayerProcessor(
            state,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            festival_decider=festival_decider,
            vote_decider=vote_decider,
        )

    def test_festival_uses_api_with_explicit_bypass(self, state_normal_mode):
        decider = MagicMock()
        decider.decide_festivals.return_value = {2: 10}
        processor = self._processor(state_normal_mode, festival_decider=decider)
        faction = state_normal_mode.get_faction("f2")

        with patch(
            "src.api.population_api.get_candidates",
            return_value={
                "success": True,
                "data": {"consul": [{"id": 2}]},
            }
        ), patch("src.api.population_api.campaign") as campaign_mock:
            campaign_mock.return_value = {"success": True, "message": "ok"}
            processor.process_festival("p2", faction, bypass_permission=True)

        campaign_mock.assert_called_once_with(
            state_normal_mode,
            "p2",
            2,
            10,
            bypass_permission=True
        )

    def test_vote_uses_api_with_explicit_bypass(self, state_normal_mode):
        decider = MagicMock()
        decider.decide_vote.return_value = 2
        processor = self._processor(state_normal_mode, vote_decider=decider)
        faction = state_normal_mode.get_faction("f2")

        with patch(
            "src.api.population_api.get_candidates",
            return_value={
                "success": True,
                "data": {"consul": [{"id": 2}]},
            }
        ), patch("src.api.population_api.vote") as vote_mock:
            vote_mock.return_value = {"success": True, "message": "ok"}
            processor.process_vote("p2", faction, bypass_permission=True)

        vote_mock.assert_called_once_with(
            state_normal_mode,
            "p2",
            "consul",
            2,
            bypass_permission=True
        )


# ========== TestGetCandidates ==========

class TestGetCandidates:
    """测试 get_candidates API"""

    def test_candidates_sorted_by_qualification(self, state_normal_mode):
        """验证候选人按资格属性降序排序"""
        # 准备：让 fig1 和 fig2 都成为 consul 候选人
        fig1 = state_normal_mode.get_member(1)
        fig2 = state_normal_mode.get_member(2)
        # 添加资格历史
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        # 设置不同的资格属性（魅力）
        fig1.charisma = 10
        fig2.charisma = 5
        fig1.update_influence()
        fig2.update_influence()

        result = population_api.get_candidates(state_normal_mode)
        consul_cands = result["data"]["consul"]
        # 应至少有两个候选人
        assert len(consul_cands) >= 2
        # 验证排序：第一个的资格属性 >= 第二个
        attr1 = consul_cands[0]["charisma"]
        attr2 = consul_cands[1]["charisma"]
        assert attr1 >= attr2


    def test_candidates_message_format(self, state_normal_mode):
        """验证候选人列表的字符串格式与设计文档基本一致"""
        # 先让至少有一个候选人
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        result = population_api.get_candidates(state_normal_mode)
        msg = result["message"]

        # 检查包含各官职标题图标
        assert "🏛️ CONSUL" in msg
        assert "📜 CENSOR" in msg
        assert "⚖ PRAETOR" in msg
        assert "💰 QUAESTOR" in msg
        assert "🛡️ TRIBUNE" in msg

        # 检查候选人行的缩进（以6空格开头）和包含必要字段
        lines = msg.split('\n')
        for line in lines:
            if line.strip().startswith("ID:"):
                # 应该是缩进行，检查是否以6空格开头
                assert line.startswith("      ")
                # 检查包含属性字段
                assert "军略" in line
                assert "智略" in line
                assert "魅力" in line
                assert "热忱" in line

    def test_returns_dict_with_all_offices(self, state_normal_mode):
        """返回字典包含所有公职键"""
        result = population_api.get_candidates(state_normal_mode)
        assert result["success"] is True
        data = result["data"]
        expected_keys = ["consul", "censor", "praetor", "quaestor", "tribune"]
        for key in expected_keys:
            assert key in data
            assert isinstance(data[key], list)

    def test_candidates_list_structure(self, state_normal_mode):
        """每个候选人包含必要字段"""
        # 先让 fig1 成为 consul 候选人
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        result = population_api.get_candidates(state_normal_mode)
        consul_cands = result["data"]["consul"]
        assert len(consul_cands) > 0
        for cand in consul_cands:
            assert "id" in cand
            assert "name" in cand
            assert "faction_id" in cand
            assert "faction_name" in cand
            # 移除 influence 检查，改为检查四维属性
            assert "martial" in cand
            assert "intelligence" in cand
            assert "charisma" in cand
            assert "zeal" in cand

    def test_only_eligible_figures(self, state_normal_mode):
        """只返回符合资格的候选人"""
        # fig1 添加资格，fig2 不加资格（年龄足够但无历史）
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2 = state_normal_mode.get_member(2)  # 无历史，不符合 consul
        fig2.age = 50  # 年龄够，但缺少 praetor 历史

        result = population_api.get_candidates(state_normal_mode)
        consul_ids = [c["id"] for c in result["data"]["consul"]]
        assert 1 in consul_ids
        assert 2 not in consul_ids

    def test_exclude_absent_figures(self, state_normal_mode):
        """缺席人物不出现"""
        fig1 = state_normal_mode.get_member(1)
        fig1.is_absent = True
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        result = population_api.get_candidates(state_normal_mode)
        consul_ids = [c["id"] for c in result["data"]["consul"]]
        assert 1 not in consul_ids


# ========== TestResolveElection ==========

class TestResolveElection:
    """测试 resolve_election API"""

    def test_no_votes(self, state_normal_mode):
        """无投票记录"""
        result = population_api.resolve_election(state_normal_mode)
        assert result["success"] is True
        assert "无投票记录" in result["message"] or "无有效选举结果" in result["message"]

    def test_single_candidate_wins(self, state_normal_mode):
        """单个候选人自动当选"""
        # 准备：fig1 是 consul 唯一候选人
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2 = state_normal_mode.get_member(2)
        fig2.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))

        # 投票：只有 p1 投给 fig1
        state_normal_mode._population_pending["votes"] = [("p1", "consul", 1)]

        result = population_api.resolve_election(state_normal_mode)
        assert result["success"] is True
        assert fig1.office == "consul"
        assert fig2.office is None
        assert fig1.name in result["message"]

    def test_vote_weighted_by_faction_influence(self, state_normal_mode):
        """按派系影响力加权计票"""
        fig1 = state_normal_mode.get_member(1)  # f1
        fig2 = state_normal_mode.get_member(2)  # f2
        # 两人都有资格
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))

        # 调整影响力：f1 影响力高，f2 低
        fig1.popularity = 90  # +90 影响力
        fig1.update_influence()
        fig2.popularity = 10
        fig2.update_influence()

        # 投票：p1 投 fig1, p2 投 fig2
        state_normal_mode._population_pending["votes"] = [("p1", "consul", 1), ("p2", "consul", 2)]

        result = population_api.resolve_election(state_normal_mode)
        # f1 影响力高，fig1 当选
        assert fig1.office == "consul"
        assert fig2.office is None

    def test_tie_break_random(self, state_normal_mode):
        """平局时随机选择"""
        fig1 = state_normal_mode.get_member(1)
        fig2 = state_normal_mode.get_member(2)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))

        # 使两个人物影响力相等（直接设置 _influence 确保相等）
        fig1._influence = 100
        fig2._influence = 100
        # 其他成员影响力设为0，避免干扰派系总影响力
        fig3 = state_normal_mode.get_member(3)
        fig4 = state_normal_mode.get_member(4)
        fig3._influence = 0
        fig4._influence = 0

        state_normal_mode._population_pending["votes"] = [("p1", "consul", 1), ("p2", "consul", 2)]

        with patch('random.choice') as mock_choice:
            mock_choice.return_value = 1
            result = population_api.resolve_election(state_normal_mode)
            assert fig1.office == "consul"
            mock_choice.assert_called_once_with([1, 2])

    def test_office_assigned_and_influence_updated(self, state_normal_mode):
        """当选者设置官职并更新影响力"""
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        old_influence = fig1.influence
        state_normal_mode._population_pending["votes"] = [("p1", "consul", 1)]

        result = population_api.resolve_election(state_normal_mode)
        assert fig1.office == "consul"
        assert fig1.influence > old_influence  # 应有官职加成

    def test_faction_leader_updated(self, state_normal_mode):
        """当选者若为派系成员，派系领袖更新（至少触发）"""
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        state_normal_mode._population_pending["votes"] = [("p1", "consul", 1)]

        # mock faction.update_faction_leader 以验证被调用
        faction = state_normal_mode.get_faction("f1")
        with patch.object(faction, 'update_faction_leader') as mock_update:
            result = population_api.resolve_election(state_normal_mode)
            mock_update.assert_called_once_with(state_normal_mode)

    def test_multiple_offices(self, state_normal_mode):
        """多个公职同时选举"""
        fig1 = state_normal_mode.get_member(1)  # consul
        fig2 = state_normal_mode.get_member(2)  # consul
        fig3 = state_normal_mode.get_member(3)  # praetor

        # 资格
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig3.office_history.append(OfficeTerm(office_type="quaestor", start_turn=-10, end_turn=-9))
        fig3.class_tier = ClassTier.NOBILE  # 裁判官需贵族

        # 调整影响力使 fig1 > fig2
        fig1.popularity = 100
        fig2.popularity = 50
        fig1.update_influence()
        fig2.update_influence()

        state_normal_mode._population_pending["votes"] = [
            ("p1", "consul", 1),
            ("p2", "consul", 2),
            ("p1", "praetor", 3),
            ("p2", "praetor", 3)
        ]

        result = population_api.resolve_election(state_normal_mode)
        assert fig1.office == "consul"
        assert fig3.office == "praetor"
        assert fig2.office is None
