# src/tests/test_commands/test_phase_forum_triumph.py
"""
凯旋审批专项测试 - 广场阶段
"""
import pytest
from unittest.mock import MagicMock, patch, call
from io import StringIO

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.player import Player, PlayerType
from src.core.entities.province import Province
from src.core.systems.war_system import WarSystem
from src.core.systems.naval_system import NavalSystem
from src.core.entities.war import War, WarStatus
from src.ui.commands.phase_forum import ForumCommand
from src.core.i18n import i18n
from src.api import forum_api

i18n.load("zh-CN")


@pytest.fixture
def test_state():
    """创建测试用游戏状态"""
    config = {
        "testing": {
            "auto_forum": False,
            "bypass_player_check": False,
        },
        "economic_rules": {
            "land_price_per_unit": 10,
            "province_tax_rate": 0.1,
            "faction_initial_treasury": 10,
            "faction_member_limit": 6,
            "initial_national_public_land": 1000,
        },
        "political_rules": {
            "retirement_chance": 0.3,
        },
        "forum_rules": {
            "new_figures_count": 3,
            "class_probabilities": {"nobile": 0.5, "eques": 0.3, "plebeian": 0.2},
        },
        "combat_rules": {"triumph_veteran_duration": 5},
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)

    # 添加玩家
    player1 = Player("p1", "f1", PlayerType.HUMAN)
    player2 = Player("p2", "f2", PlayerType.AI)
    player3 = Player("p3", "f3", PlayerType.AI)
    state.add_player(player1)
    state.add_player(player2)
    state.add_player(player3)
    state.set_turn_order(["p1", "p2", "p3"])
    state.set_current_player("p1")

    # 添加派系
    faction1 = Faction("f1", "Faction1", treasury=100)
    faction2 = Faction("f2", "Faction2", treasury=100)
    faction3 = Faction("f3", "Faction3", treasury=100)
    state.add_faction(faction1)
    state.add_faction(faction2)
    state.add_faction(faction3)

    # 添加人物
    for i in range(1, 7):
        fig = Figure.create_nobile(i, "f1", 30 + i) if i <= 3 else Figure.create_eques(i, "f1", 25 + i)
        fig.is_faction_leader = (i == 1)
        fig._land_private = 2
        fig.wealth = 20
        fig.update_influence()
        state.add_member(fig)
        faction1.member_ids.append(i)

    for i in range(7, 13):
        fig = Figure.create_nobile(i, "f2", 30 + i) if i <= 9 else Figure.create_eques(i, "f2", 25 + i)
        fig.is_faction_leader = (i == 7)
        fig._land_private = 1
        fig.wealth = 20
        fig.update_influence()
        state.add_member(fig)
        faction2.member_ids.append(i)

    for i in range(13, 19):
        fig = Figure.create_nobile(i, "f3", 30 + i) if i <= 15 else Figure.create_eques(i, "f3", 25 + i)
        fig.is_faction_leader = (i == 13)
        fig._land_private = 1
        fig.wealth = 20
        fig.update_influence()
        state.add_member(fig)
        faction3.member_ids.append(i)

    # 添加行省（仅意大利，用于避免无行省错误）
    italy = Province(
        province_id=0,
        name="意大利",
        total_land=1000,
        land_public=500,
        land_private=500,
        conquered=True,
    )
    state.add_province(italy)

    # 添加战争系统
    war_system = WarSystem(state)
    state._war_system = war_system

    # 添加海军系统
    naval_system = NavalSystem(state)
    state._naval_system = naval_system

    return state


@pytest.fixture
def mock_deciders():
    """创建 mock 决策器"""
    retirement = MagicMock()
    recruitment = MagicMock()
    bid = MagicMock()
    land_trade = MagicMock()
    triumph = MagicMock()
    return retirement, recruitment, bid, land_trade, triumph


class TestForumTriumph:
    """凯旋审批专项测试"""

    def setup_for_triumph(self, test_state, soldier_share=50, commander_id=1):
        """设置一个待凯旋战争，返回 war 和 commander"""
        war = War(id="war1", name="Test War")
        war._status = WarStatus.RESOLVED
        war._soldier_share = soldier_share
        war._triumph_commander_id = commander_id
        war_system = test_state.get_war_system()
        war_system._war_discard = [war]
        commander = test_state.get_member(commander_id)
        commander.is_dead = False
        return war, commander

    def set_influence(self, test_state, totals):
        """R-01：按新口径（分母 = 全体注册派系）重定 fixture 影响力，保持断言强度。

        `totals` = {faction_id: 派系影响力总和}；均匀分配到该派系所有成员。
        """
        for faction_id, total in totals.items():
            members = [test_state.get_member(mid)
                       for mid in test_state.get_faction(faction_id).member_ids]
            assert members and total % len(members) == 0, (faction_id, total, len(members))
            per = total // len(members)
            for member in members:
                member.influence = per

    def test_triumph_approved(self, test_state, mock_deciders):
        """凯旋批准：支持率 > 50% 时批准，并添加临时影响力"""
        war, commander = self.setup_for_triumph(test_state, soldier_share=50, commander_id=1)
        # R-01：新口径分母 = 全体注册派系 f1+f2+f3=150；f1 支持 120 → 支持率 80.0% > 50%。
        # f3 未投 → 计入分母（未投=反对）；分母含 f3 由 80.0%（非 120/138≈87.0%）证明。
        self.set_influence(test_state, {"f1": 120, "f2": 18, "f3": 12})
        # 添加投票数据（支持率 > 50%）
        test_state._forum_pending["triumph_votes"] = [
            ("war1", "f1", True),  # 支持
            ("war1", "f2", False),  # 反对
        ]

        retirement, recruitment, bid, land_trade, triumph = mock_deciders
        cmd = ForumCommand(test_state,
                           retirement_decider=retirement,
                           recruitment_decider=recruitment,
                           bid_decider=bid,
                           land_trade_decider=land_trade,
                           triumph_decider=triumph)

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "凯旋仪式获得批准" in result["message"]
        # 分母含未投的 f3（分母全注册派系影响力之和）：120 / (120+18+12) = 80.0%
        assert "80.0%" in result["message"]
        # 验证临时影响力添加（50 // 5 = 10）
        assert len(commander._temp_influence_tasks) == 1
        # 临时任务以字典形式存储，键名为 per_turn
        assert commander._temp_influence_tasks[0]["per_turn"] == 10

    def test_triumph_rejected(self, test_state, mock_deciders):
        """凯旋否决：支持率 <= 50% 时否决，不添加临时影响力"""
        war, commander = self.setup_for_triumph(test_state, soldier_share=50, commander_id=1)
        # R-01：新口径分母 = f1+f2+f3=150；仅 f2 支持 18 → 支持率 12.0% ≤ 50% → 否决。
        self.set_influence(test_state, {"f1": 120, "f2": 18, "f3": 12})
        # 添加投票数据（支持率 ≤ 50%）
        test_state._forum_pending["triumph_votes"] = [
            ("war1", "f1", False),  # 反对
            ("war1", "f2", True),   # 支持（影响力较低）
        ]
        # 实际影响力分布：f1 120 / f2 18 / f3 12（f3 未投 → 计入分母=反对）

        retirement, recruitment, bid, land_trade, triumph = mock_deciders
        cmd = ForumCommand(test_state,
                           retirement_decider=retirement,
                           recruitment_decider=recruitment,
                           bid_decider=bid,
                           land_trade_decider=land_trade,
                           triumph_decider=triumph)

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "被否决" in result["message"]
        # 分母含未投的 f3：18 / (120+18+12) = 12.0%
        assert "12.0%" in result["message"]
        assert len(commander._temp_influence_tasks) == 0

    def test_commander_dead(self, test_state, mock_deciders):
        """指挥官死亡时跳过凯旋"""
        war, commander = self.setup_for_triumph(test_state, soldier_share=50, commander_id=1)
        commander.is_dead = True
        test_state._forum_pending["triumph_votes"] = [("war1", "f1", True)]

        retirement, recruitment, bid, land_trade, triumph = mock_deciders
        cmd = ForumCommand(test_state,
                           retirement_decider=retirement,
                           recruitment_decider=recruitment,
                           bid_decider=bid,
                           land_trade_decider=land_trade,
                           triumph_decider=triumph)

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "指挥官已死" in result["message"]
        # 验证 soldier_share 被清零
        assert war.soldier_share == 0

    def test_multiple_wars(self, test_state, mock_deciders):
        """多个战争同时审批"""
        war1, commander1 = self.setup_for_triumph(test_state, soldier_share=50, commander_id=1)
        war2 = War(id="war2", name="Test War 2")
        war2._status = WarStatus.RESOLVED
        war2._soldier_share = 30
        war2._triumph_commander_id = 2
        commander2 = test_state.get_member(2)
        commander2.is_dead = False
        war_system = test_state.get_war_system()
        war_system._war_discard = [war1, war2]

        self.set_influence(test_state, {"f1": 120, "f2": 18, "f3": 12})
        test_state._forum_pending["triumph_votes"] = [
            ("war1", "f1", True),
            ("war1", "f2", False),
            ("war2", "f1", True),
            ("war2", "f3", True),
        ]

        retirement, recruitment, bid, land_trade, triumph = mock_deciders
        cmd = ForumCommand(test_state,
                           retirement_decider=retirement,
                           recruitment_decider=recruitment,
                           bid_decider=bid,
                           land_trade_decider=land_trade,
                           triumph_decider=triumph)

        result = forum_api.resolve_forum(test_state)
        assert result["success"] is True
        assert "凯旋仪式获得批准" in result["message"]
        assert "被否决" not in result["message"]  # 假设两个都批准，可根据实际调整
        # 检查两个战争都处理
        assert len(commander1._temp_influence_tasks) == 1
        assert len(commander2._temp_influence_tasks) == 1
        # 检查 soldier_share 被清零
        assert war1.soldier_share == 0
        assert war2.soldier_share == 0


class TestTvasTallyAcceptance:
    """EOR20261012-01 ATTEMPT-3 — mandatory acceptance AC-04 / AC-06 / AC-11 / AC-12.

    Independent oracle over the PUBLIC chain (``vote_triumph`` -> ``get_forum_view`` ->
    ``resolve_forum``). Adds coverage; does NOT weaken existing assertions; does NOT change
    the frozen threshold (FC-04 ``> 0.5``) or any frozen value/number.
    """

    def _zero_influence(self, state):
        for faction in state.factions.values():
            for mid in faction.member_ids:
                member = state.get_member(mid)
                if member is not None:
                    member.influence = 0

    def _set(self, state, mapping):
        """Exact per-member influence oracle: ``mapping = {member_id: influence}``."""
        self._zero_influence(state)
        for mid, value in mapping.items():
            state.get_member(mid).influence = value

    def _war(self, state, war_id="war1", name="Test War", soldier_share=100, commander_id=1):
        war = War(id=war_id, name=name)
        war._status = WarStatus.RESOLVED
        war._soldier_share = soldier_share
        war._triumph_commander_id = commander_id
        commander = state.get_member(commander_id)
        if commander is not None:
            commander.is_dead = False
        return war

    def _viewer_vote(self, state, player_id="p1", war_id="war1"):
        view = forum_api.get_forum_view(state, player_id)
        assert view["success"], view.get("message")
        rows = {r["war_id"]: r for r in view["data"]["triumph_wars"]}
        assert war_id in rows, (war_id, list(rows))
        return rows[war_id]["viewer_vote"]

    # -------- AC-04: threshold boundary (exactly 0.5 reject; > 0.5 approve) --------

    def test_ac04_exactly_half_is_rejected(self, test_state):
        war = self._war(test_state)
        test_state.get_war_system()._war_discard = [war]
        self._set(test_state, {1: 50, 7: 50})   # denom=100; f1 True=50 -> 50.0%
        assert forum_api.vote_triumph(test_state, "p1", "war1", True)["success"]
        before = test_state.treasury
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "❌ 战争 Test War 的凯旋仪式被否决（支持率 50.0%）", result["message"]
        assert war.triumph_approved is False
        assert war.soldier_share == 0
        assert test_state.treasury == before + 100     # full pool refund

    def test_ac04_just_above_half_is_approved(self, test_state):
        war = self._war(test_state)
        test_state.get_war_system()._war_discard = [war]
        self._set(test_state, {1: 51, 7: 49})   # denom=100; f1 True=51 -> 51.0%
        assert forum_api.vote_triumph(test_state, "p1", "war1", True)["success"]
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "✅ 战争 Test War 的凯旋仪式获得批准（支持率 51.0%）", result["message"]
        assert war.triumph_approved is True
        commander = test_state.get_member(1)
        assert len(commander._temp_influence_tasks) == 1
        assert commander._temp_influence_tasks[0]["per_turn"] == 20   # 100 // 5

    # -------- AC-06: deterministic fallback + four complete messages --------

    def test_ac06_positive_denominator_zero_records_is_zero_percent_reject(self, test_state):
        war = self._war(test_state)
        test_state.get_war_system()._war_discard = [war]
        self._set(test_state, {1: 120, 7: 18, 13: 12})   # denom=150; zero records
        before = test_state.treasury
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "❌ 战争 Test War 的凯旋仪式被否决（支持率 0.0%）", result["message"]
        assert war.triumph_approved is False
        assert war.soldier_share == 0
        assert test_state.treasury == before + 100

    def test_ac06_all_false_is_zero_percent_reject(self, test_state):
        war = self._war(test_state)
        test_state.get_war_system()._war_discard = [war]
        self._set(test_state, {1: 120, 7: 18, 13: 12})
        test_state._forum_pending["triumph_votes"] = [
            ("war1", "f1", False), ("war1", "f2", False), ("war1", "f3", False)]
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "❌ 战争 Test War 的凯旋仪式被否决（支持率 0.0%）", result["message"]
        assert war.soldier_share == 0

    def test_ac06_zero_denominator_no_valid_vote(self, test_state):
        war = self._war(test_state)
        test_state.get_war_system()._war_discard = [war]
        self._zero_influence(test_state)        # every faction 0 influence -> denom=0
        before = test_state.treasury
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "⚠️ 战争 Test War 无有效投票", result["message"]
        assert war.soldier_share == 0
        assert test_state.treasury == before + 100

    def test_ac06_commander_dead_message_and_refund(self, test_state):
        war = self._war(test_state)
        test_state.get_war_system()._war_discard = [war]
        self._set(test_state, {1: 120, 7: 18, 13: 12})
        test_state.get_member(1).is_dead = True
        before = test_state.treasury
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "⚠️ 战争 Test War 指挥官已死，凯旋失效", result["message"]
        assert war.soldier_share == 0
        assert test_state.treasury == before + 100

    def test_ac06_commander_missing_message_and_refund(self, test_state):
        war = self._war(test_state, commander_id=999999)   # no such member -> commander_missing
        test_state.get_war_system()._war_discard = [war]
        self._set(test_state, {1: 120, 7: 18, 13: 12})
        before = test_state.treasury
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "⚠️ 战争 Test War 指挥官已死，凯旋失效", result["message"]
        assert war.soldier_share == 0
        assert test_state.treasury == before + 100

    # -------- AC-11: candidate neutrality (no-candidate faction still in denominator) --------

    def test_ac11_no_candidate_faction_still_counts_in_denominator(self, test_state):
        war = self._war(test_state, commander_id=1)     # candidate = f1 (member 1)
        test_state.get_war_system()._war_discard = [war]
        # A = candidate faction f1, weight 40, votes True; B = f2, NO candidate, weight 60,
        # does not vote -> denominator 100, numerator 40 -> 40.0% (B must NOT be zeroed).
        self._set(test_state, {1: 40, 7: 60})
        assert forum_api.vote_triumph(test_state, "p1", "war1", True)["success"]
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "❌ 战争 Test War 的凯旋仪式被否决（支持率 40.0%）", result["message"]
        assert war.triumph_approved is False

    # -------- AC-12: latest-ballot merge via public API + cross-war/faction isolation --------

    def _ac12_setup(self, test_state):
        war = self._war(test_state)
        test_state.get_war_system()._war_discard = [war]
        self._set(test_state, {1: 60, 7: 40})   # A(f1)=60 votes; B(f2)=40 unvoted
        return war

    def test_ac12_true_then_false_zero_reject(self, test_state):
        self._ac12_setup(test_state)
        assert forum_api.vote_triumph(test_state, "p1", "war1", True)["success"]
        assert forum_api.vote_triumph(test_state, "p1", "war1", False)["success"]
        assert self._viewer_vote(test_state) is False
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "❌ 战争 Test War 的凯旋仪式被否决（支持率 0.0%）", result["message"]

    def test_ac12_false_then_true_60_approve(self, test_state):
        self._ac12_setup(test_state)
        assert forum_api.vote_triumph(test_state, "p1", "war1", False)["success"]
        assert forum_api.vote_triumph(test_state, "p1", "war1", True)["success"]
        assert self._viewer_vote(test_state) is True
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "✅ 战争 Test War 的凯旋仪式获得批准（支持率 60.0%）", result["message"]

    def test_ac12_true_then_true_counts_faction_once(self, test_state):
        self._ac12_setup(test_state)
        assert forum_api.vote_triumph(test_state, "p1", "war1", True)["success"]
        assert forum_api.vote_triumph(test_state, "p1", "war1", True)["success"]
        assert self._viewer_vote(test_state) is True
        result = forum_api.resolve_forum(test_state)
        # 60.0% (not 120%): latest-ballot merge counts each faction once
        assert result["message"] == "✅ 战争 Test War 的凯旋仪式获得批准（支持率 60.0%）", result["message"]

    def test_ac12_false_then_false_zero_reject(self, test_state):
        self._ac12_setup(test_state)
        assert forum_api.vote_triumph(test_state, "p1", "war1", False)["success"]
        assert forum_api.vote_triumph(test_state, "p1", "war1", False)["success"]
        assert self._viewer_vote(test_state) is False
        result = forum_api.resolve_forum(test_state)
        assert result["message"] == "❌ 战争 Test War 的凯旋仪式被否决（支持率 0.0%）", result["message"]

    def test_ac12_no_cross_war_or_faction_leakage(self, test_state):
        war1 = self._war(test_state, war_id="war1", name="War One", commander_id=1)
        war2 = self._war(test_state, war_id="war2", name="War Two", commander_id=7)
        test_state.get_war_system()._war_discard = [war1, war2]
        self._set(test_state, {1: 60, 7: 40})
        # f1 (viewer) votes ONLY on war2 -> war1 no votes (0%); war2 = 60%.
        assert forum_api.vote_triumph(test_state, "p1", "war2", True)["success"]
        assert self._viewer_vote(test_state, war_id="war2") is True
        assert self._viewer_vote(test_state, war_id="war1") is None
        result = forum_api.resolve_forum(test_state)
        msg = result["message"]
        assert "❌ 战争 War One 的凯旋仪式被否决（支持率 0.0%）" in msg, msg
        assert "✅ 战争 War Two 的凯旋仪式获得批准（支持率 60.0%）" in msg, msg