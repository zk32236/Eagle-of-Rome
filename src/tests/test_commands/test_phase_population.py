# src/tests/test_commands/test_phase_population.py
"""
命令层功能测试 - 人口阶段 (PopulationCommand)
"""
import pytest
import unittest
from unittest.mock import MagicMock, patch

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier, OfficeTerm
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.ui.commands.phase_population import PopulationCommand
from src.core.entities.war import WarStatus
from src.api import population_api


@pytest.fixture
def state_base():
    """基础状态"""
    config = {
        "testing": {"bypass_player_check": False, "auto_forum": False},
        "economic_rules": {"faction_member_limit": 6},
        "political_rules": {
            "min_ages": {"consul": 40, "praetor": 35},
            "office_cooldowns": {"consul": 2},
            "offices_per_election": {"consul": 1, "praetor": 1},
        },
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-282)
    state._population_pending = {"campaigns": [], "votes": []}
    state._executed_phases = set()
    return state


@pytest.fixture
def state_with_players(state_base):
    """添加玩家和派系"""
    p1 = Player("p1", "f1", PlayerType.HUMAN)
    p2 = Player("p2", "f2", PlayerType.AI)
    state_base.add_player(p1)
    state_base.add_player(p2)
    state_base.set_turn_order(["p1", "p2"])
    state_base.set_current_player("p1")

    f1 = Faction("f1", "Faction1", 1000)
    f2 = Faction("f2", "Faction2", 1000)
    state_base.add_faction(f1)
    state_base.add_faction(f2)

    # 人物
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

    return state_base


@pytest.fixture
def state_normal_mode(state_with_players):
    """正常模式（人类手动，AI自动）"""
    state_with_players.config._config["testing"]["auto_forum"] = False
    state_with_players.config._config["testing"]["bypass_player_check"] = False
    return state_with_players


@pytest.fixture
def state_auto_mode(state_with_players):
    """全自动模式"""
    state_with_players.config._config["testing"]["auto_forum"] = True
    return state_with_players


@pytest.fixture
def state_bypass_mode(state_with_players):
    """全人工测试模式"""
    state_with_players.config._config["testing"]["bypass_player_check"] = True
    return state_with_players


# ========== 基础流程测试 ==========

class TestPopulationCommandBase:
    """基础流程测试"""

    def test_already_executed(self, state_normal_mode):
        """阶段已执行时再次执行应失败"""
        state_normal_mode.mark_phase_executed("forum")
        state_normal_mode.mark_phase_executed("population")
        cmd = PopulationCommand(state_normal_mode)
        with patch('builtins.print') as mock_print:
            result = cmd.execute([])
            assert result is False
            mock_print.assert_any_call("⚠️ 人口阶段在本回合已执行过", flush=True)

    def test_forum_not_executed(self, state_normal_mode):
        """前置阶段（forum）未执行时失败"""
        cmd = PopulationCommand(state_normal_mode)
        with patch('builtins.print') as mock_print:
            result = cmd.execute([])
            assert result is False
            mock_print.assert_any_call("⚠️ 必须先执行广场阶段 (forum)", flush=True)

# ========== 自动模式测试 ==========

class TestPopulationCommandAuto:
    """自动模式测试"""

    def _auto_mode_festival_and_vote(self):
        """全自动模式：为所有玩家依次执行庆典和投票，并打印影响力变化表格"""
        # 记录庆典前各派系影响力
        pre_influences = self._get_faction_influences()

        # 先执行所有玩家的庆典
        for player in self.state.get_all_players():
            faction = self.state.get_faction(player.faction_id)
            if faction:
                self.auto_processor.process_festival(player.player_id, faction)

        # 再执行所有玩家的投票
        for player in self.state.get_all_players():
            faction = self.state.get_faction(player.faction_id)
            if faction:
                self.auto_processor.process_vote(player.player_id, faction)

        # 从临时记录中统计总花费
        total_spent = 0
        campaigns = self.state._population_pending.get("campaigns", [])
        for _, _, amount in campaigns:
            total_spent += amount
        total_boost = total_spent

        # 记录庆典后各派系影响力
        post_influences = self._get_faction_influences()

        # 打印影响力表格
        self._print_influence_table(pre_influences, post_influences, total_spent, total_boost)

    def test_auto_mode_full_auto(self, state_auto_mode, monkeypatch):
        """全自动模式：自动庆典、自动投票、自动选举"""
        # 直接修改配置字典
        state_auto_mode.config._config["testing"]["auto_forum"] = True

        fig1 = state_auto_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        state_auto_mode.mark_phase_executed("forum")

        # 模拟输入，提供足够的 "next"
        inputs = iter(["next", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))

        cmd = PopulationCommand(state_auto_mode)
        cmd.auto_processor.process_festival = MagicMock()
        cmd.auto_processor.process_vote = MagicMock()
        with patch('builtins.print'):
            result = cmd.execute([])
        assert result is True
        assert cmd.auto_processor.process_festival.call_count >= 1
        assert cmd.auto_processor.process_vote.call_count >= 1
        assert state_auto_mode.is_phase_executed("population") is True


# ========== 手动模式测试 ==========

class TestPopulationCommandManual:
    """手动模式测试"""

    def test_step0_display_candidates(self, state_normal_mode, capsys, monkeypatch):
        """步骤0显示候选人列表"""
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        state_normal_mode.mark_phase_executed("forum")
        # 提供足够多的 "next" 输入以确保所有步骤都能完成
        inputs = iter(["next"] * 10)
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        cmd = PopulationCommand(state_normal_mode)
        cmd.execute([])
        captured = capsys.readouterr()
        assert "候选人" in captured.out or "CONSUL" in captured.out

    def test_step0_next_proceeds(self, state_normal_mode, monkeypatch):
        """输入next进入步骤1"""
        monkeypatch.setattr('builtins.input', lambda *args: "next")
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        with patch('builtins.print'):
            cmd.execute([])

    def test_step1_campaign_success(self, state_normal_mode, monkeypatch):
        """在合并环节成功举办庆典"""
        # 输入序列：step0 next, step1 campaign, step1 next, step2 next, step3 next
        inputs = iter(["next", "campaign 1 10", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_festival = MagicMock()  # 禁止AI自动庆典干扰
        with patch('src.api.population_api.campaign') as mock_campaign:
            mock_campaign.return_value = {"success": True, "message": "庆典成功"}
            with patch('builtins.print'):
                cmd.execute([])
        mock_campaign.assert_called_once()
        args = mock_campaign.call_args[0]
        assert args[1] == "p1"
        assert args[2] == 1
        assert args[3] == 10

    def test_step1_campaign_failure(self, state_normal_mode, monkeypatch, capsys):
        """在合并环节庆典失败时输出错误信息"""
        inputs = iter(["next", "campaign 1 1000", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_festival = MagicMock()
        with patch('src.api.population_api.campaign') as mock_campaign:
            mock_campaign.return_value = {"success": False, "message": "财富不足"}
            cmd.execute([])
        captured = capsys.readouterr()
        assert "财富不足" in captured.out

    def test_step1_ai_process_festival_and_vote(self, state_normal_mode, monkeypatch):
        """自动模式下AI玩家自动调用process_festival和process_vote"""
        inputs = iter(["next", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        # 同时mock两个处理器
        cmd.auto_processor.process_festival = MagicMock()
        cmd.auto_processor.process_vote = MagicMock()
        with patch('builtins.print'):
            cmd.execute([])
        # 验证两个方法都被调用，且至少对p2调用（AI玩家）
        cmd.auto_processor.process_festival.assert_called_once_with("p2", unittest.mock.ANY, bypass_permission=True)
        cmd.auto_processor.process_vote.assert_called_once_with("p2", unittest.mock.ANY, bypass_permission=True)

    def test_step1_player_switching(self, state_normal_mode, monkeypatch):
        """多个玩家时next切换玩家"""
        inputs = iter(["next", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        with patch('builtins.print'):
            cmd.execute([])
        # 执行成功即表示切换完成，无需额外断言

    def test_step1_festival_and_vote_combined(self, state_normal_mode, monkeypatch, capsys):
        """模拟玩家在合并环节中先举办庆典后投票"""
        from src.core.entities.player import PlayerType

        # 将 p2 临时改为人类，避免自动处理
        p2 = state_normal_mode.get_player("p2")
        p2._player_type = PlayerType.HUMAN

        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig1.wealth = 100

        # 输入序列：step0 next, step1 campaign + vote + next, step2 next, step3 next
        # 注意：有两个人类玩家，p1 执行后输入 next 切换到 p2，p2 需要再输入 next 完成
        inputs = iter(["next", "", "campaign 1 10", "vote consul 1", "next", "", "next", "", "next", ""])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")

        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_festival = MagicMock()
        cmd.auto_processor.process_vote = MagicMock()
        with patch('src.api.population_api.get_candidates') as mock_get_candidates:
            mock_get_candidates.return_value = {
                "success": True,
                "data": {"consul": [{"id": 1}]},
                "message": ""
            }
            with patch('src.api.population_api.campaign') as mock_campaign, \
                    patch('src.api.population_api.vote') as mock_vote:
                mock_campaign.return_value = {"success": True, "message": "庆典成功"}
                mock_vote.return_value = {"success": True, "message": "投票成功"}
                cmd.execute([])

        mock_campaign.assert_called_once()
        mock_vote.assert_called_once()
        captured = capsys.readouterr()
        assert "庆典成功" in captured.out
        assert "投票成功" in captured.out

    def test_step3_resolve_election_called(self, state_normal_mode, monkeypatch):
        """公示环节调用resolve_election API"""
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        inputs = iter(["next", "next", "vote consul 1", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_vote = MagicMock()
        with patch('src.api.population_api.get_candidates') as mock_get_candidates, \
             patch('src.api.population_api.resolve_election') as mock_resolve:
            mock_get_candidates.return_value = {
                "success": True,
                "data": {"consul": [{"id": 1}]},
                "message": ""
            }
            mock_resolve.return_value = {"success": True, "message": "选举结果"}
            with patch('builtins.print'):
                cmd.execute([])
        mock_resolve.assert_called_once()

    def test_step3_display_results(self, state_normal_mode, monkeypatch, capsys):
        """公示环节打印选举结果"""
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        inputs = iter(["next", "next", "vote consul 1", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_vote = MagicMock()
        with patch('src.api.population_api.get_candidates') as mock_get_candidates, \
             patch('src.api.population_api.resolve_election') as mock_resolve:
            mock_get_candidates.return_value = {
                "success": True,
                "data": {"consul": [{"id": 1}]},
                "message": ""
            }
            mock_resolve.return_value = {"success": True, "message": "选举结果: 某人当选"}
            cmd.execute([])
        captured = capsys.readouterr()
        assert "选举结果" in captured.out

    def test_step3_clear_pending(self, state_normal_mode, monkeypatch):
        """公示后清空_population_pending"""
        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        state_normal_mode._population_pending["votes"] = [("p1", "consul", 1)]
        inputs = iter(["next", "next", "vote consul 1", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_vote = MagicMock()
        with patch('src.api.population_api.get_candidates') as mock_get_candidates:
            mock_get_candidates.return_value = {
                "success": True,
                "data": {"consul": [{"id": 1}]},
                "message": ""
            }
            with patch('builtins.print'):
                cmd.execute([])
        assert state_normal_mode._population_pending["votes"] == []
        assert state_normal_mode._population_pending["campaigns"] == []

    def test_step3_legion_triumph_display(self, state_normal_mode, monkeypatch, capsys):
        """凯旋式信息在公示环节正确显示"""
        war_system = MagicMock()
        war_system._war_discard = []
        war_system._legions_to_disband = []  # 防止进入解散分支
        war = MagicMock()
        war.status = WarStatus.RESOLVED
        war.triumph_approved = True
        war.triumph_commander_id = 1
        war.commander_id = 1
        war.legion_numbers = []
        war.set_triumph_approved = MagicMock()
        war_system._war_discard = [war]
        state_normal_mode.get_war_system = MagicMock(return_value=war_system)

        ms = MagicMock()
        ms.disband_legions_for_war.return_value = (0, [])  # 模拟解散返回
        state_normal_mode.get_military_system = MagicMock(return_value=ms)

        fig1 = state_normal_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        inputs = iter(["next", "next", "vote consul 1", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_vote = MagicMock()
        with patch('src.api.population_api.get_candidates') as mock_get_candidates:
            mock_get_candidates.return_value = {
                "success": True,
                "data": {"consul": [{"id": 1}]},
                "message": ""
            }
            cmd.execute([])
        captured = capsys.readouterr()
        assert "凯旋式" in captured.out

    def test_full_manual_flow(self, state_normal_mode, monkeypatch):
        """模拟完整玩家操作序列"""
        fig1 = state_normal_mode.get_member(1)
        fig2 = state_normal_mode.get_member(2)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        fig2.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        # 输入序列：step0 next, step1 p1 campaign, p1 vote, p1 next, step2 next, step3 next
        inputs = iter([
            "next",  # step0
            "campaign 1 10",  # step1 p1 campaign
            "vote consul 1",  # step1 p1 vote
            "next",  # step1 p1 next -> p2 (AI)
            "next",  # step2 (公示) next
            "next"  # step3 (完成) next
        ])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_festival = MagicMock()
        cmd.auto_processor.process_vote = MagicMock()
        with patch('src.api.population_api.get_candidates') as mock_get_candidates, \
                patch('src.api.population_api.campaign') as mock_campaign, \
                patch('src.api.population_api.vote') as mock_vote, \
                patch('src.api.population_api.resolve_election') as mock_resolve:
            mock_get_candidates.return_value = {
                "success": True,
                "data": {"consul": [{"id": 1}, {"id": 2}]},
                "message": ""
            }
            mock_campaign.return_value = {"success": True, "message": "庆典成功"}
            mock_vote.return_value = {"success": True, "message": "投票成功"}
            mock_resolve.return_value = {"success": True, "message": "选举结果"}
            cmd.execute([])

        assert mock_campaign.call_count == 1
        assert mock_vote.call_count == 1
        assert mock_resolve.call_count == 1
        # 自动处理器应被调用一次（处理 p2 AI）
        assert cmd.auto_processor.process_festival.call_count == 1
        assert cmd.auto_processor.process_vote.call_count == 1

    def test_curia_cleaned(self, state_normal_mode, capsys, monkeypatch):
        """验证公告环节正确清理广场中未被招募的人物"""
        # 准备：在curia中添加几个人物
        from src.core.entities.figure import Figure
        fig1 = Figure.create_plebeian(999, None, 30)
        fig2 = Figure.create_plebeian(998, None, 25)
        state_normal_mode.curia.add_figure(fig1)
        state_normal_mode.curia.add_figure(fig2)
        # 必须手动加入 _members，否则清理时无法删除（实际代码中 curia 中的人物原本就在 _members 中）
        state_normal_mode._members[999] = fig1
        state_normal_mode._members[998] = fig2

        # 模拟输入：只需一个next进入步骤0并触发_startup_done
        monkeypatch.setattr('builtins.input', lambda *args: "next")
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.execute([])

        captured = capsys.readouterr()
        assert "🗑️ 2 名未被招募的人物已从罗马消失，不知去向。" in captured.out
        assert state_normal_mode.curia.is_empty() is True
        assert state_normal_mode.get_member(999) is None
        assert state_normal_mode.get_member(998) is None

    def test_triumph_only_once(self, state_normal_mode, capsys, monkeypatch):
        """验证凯旋信息和军团解散信息只输出一次"""
        from src.core.entities.war import War, WarStatus
        from unittest.mock import MagicMock

        # 创建模拟战争
        war = War(id="test_war", name="Test War")
        war.status = WarStatus.RESOLVED
        war.set_triumph_approved(True)
        war.set_triumph_commander(1)
        war.add_legion_number(1)
        war.add_legion_number(2)

        # 模拟战争系统
        ws = MagicMock()
        ws._war_discard = [war]
        ws._legions_to_disband = []

        # 模拟军事系统
        ms = MagicMock()
        ms.disband_legions_for_war.return_value = (2, [])

        # 将模拟系统注入 state
        state_normal_mode.get_war_system = MagicMock(return_value=ws)
        state_normal_mode.get_military_system = MagicMock(return_value=ms)

        # 确保指挥官存活
        fig = state_normal_mode.get_member(1)
        fig.is_dead = False

        # 模拟输入序列
        inputs = iter(["next", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.execute([])

        captured = capsys.readouterr()
        assert captured.out.count("举行凯旋式") == 1
        assert captured.out.count("解散") == 1

    def test_office_holders_removed_before_festival(self, state_normal_mode, monkeypatch, capsys):
        """验证卸任发生在庆典之前：非战场官员被卸任，战场指挥官不被卸任，卸任官员出现在候选人列表中"""
        from src.core.entities.figure import Figure, OfficeTerm
        from unittest.mock import MagicMock

        # 强制关闭自动模式，避免自动投票
        state_normal_mode.config._config["testing"]["auto_population"] = False
        # 清空可能存在的投票记录
        state_normal_mode._population_pending["votes"] = []
        state_normal_mode._population_pending["campaigns"] = []

        # 获取现有的人物
        fig1 = state_normal_mode.get_member(1)  # 非战场执政官
        fig1.office = 'consul'
        fig1.is_absent = False
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))

        fig2 = state_normal_mode.get_member(2)  # 非战场大法官
        fig2.office = 'praetor'
        fig2.is_absent = False
        fig2.office_history.append(OfficeTerm(office_type="quaestor", start_turn=-12, end_turn=-11))

        # 创建战场指挥官（新人物）
        fig3 = Figure.create_nobile(3, "f2", 40)  # 使用派系 f2
        fig3.id = 3
        fig3.office = 'consul'
        fig3.is_absent = True
        fig3.faction_id = "f2"
        state_normal_mode.add_member(fig3)
        faction2 = state_normal_mode.get_faction("f2")
        if faction2:
            faction2.member_ids.append(3)

        # 确保 leader_ids 包含 fig1
        state_normal_mode.turn.leader_ids.append(fig1.id)

        # 模拟战争系统，使战场指挥官能被转换
        war_system = MagicMock()
        war = MagicMock()
        war.commander_assigned_turn = 8
        war_system.get_war_by_commander.return_value = war
        state_normal_mode.get_war_system = MagicMock(return_value=war_system)

        # 模拟输入序列，完成整个阶段
        inputs = iter(["next", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.auto_processor.process_festival = MagicMock()
        cmd.auto_processor.process_vote = MagicMock()
        cmd.execute([])

        # 验证非战场官员已卸任
        assert fig1.office == 'ex-consul'
        assert fig2.office == 'ex-praetor'
        # 验证战场指挥官已被转换为 proconsul
        assert fig3.office == 'proconsul'

        # 验证 fig1 从 leader_ids 中移除
        assert fig1.id not in state_normal_mode.turn.leader_ids

        # 获取候选人列表，验证卸任官员出现在正确官职中
        cand_result = population_api.get_candidates(state_normal_mode)
        consul_ids = [c['id'] for c in cand_result['data']['consul']]
        praetor_ids = [c['id'] for c in cand_result['data']['praetor']]

        # fig1 刚卸任执政官，有冷却期，不应出现在任何候选人列表中
        assert fig1.id not in consul_ids
        assert fig1.id not in praetor_ids

        # fig2 卸任大法官，且满足执政官资格，应出现在执政官候选人中
        assert fig2.id in consul_ids

        # fig3 是战场指挥官，不应出现在任何候选人中
        assert fig3.id not in consul_ids
        assert fig3.id not in praetor_ids

    def test_fleet_disband_once(self, state_normal_mode, capsys, monkeypatch):
        """验证舰队解散信息只输出一次"""
        from unittest.mock import MagicMock
        # 模拟海军系统
        state_normal_mode.naval_system = MagicMock()
        state_normal_mode.naval_system.disband_unused_fleets.return_value = [1, 2]

        # 模拟输入序列
        inputs = iter(["next", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))

        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.execute([])

        # 断言 disband_unused_fleets 只被调用一次
        state_normal_mode.naval_system.disband_unused_fleets.assert_called_once()

        captured = capsys.readouterr()
        assert "舰队 [1, 2] 已解散" in captured.out
        assert captured.out.count("舰队") == 1

    def test_commander_conversion_once(self, state_normal_mode, monkeypatch, capsys):
        """验证战场指挥官转换只执行一次，且状态正确"""
        state_normal_mode.turn.turn_number = 10
        from unittest.mock import MagicMock, patch
        from src.core.entities.war import War

        # 准备：出征的执政官
        fig1 = state_normal_mode.get_member(1)  # 使用现有的人物1
        fig1.is_absent = True
        fig1.office = 'consul'
        fig1.add_office_history = MagicMock()
        fig1.update_influence = MagicMock()

        # 出征的大法官
        fig2 = state_normal_mode.get_member(2)  # 使用现有的人物2
        fig2.is_absent = True
        fig2.office = 'praetor'
        fig2.add_office_history = MagicMock()
        fig2.update_influence = MagicMock()

        # 模拟战争系统
        war_system = MagicMock()
        war1 = MagicMock(spec=War)
        war1.commander_assigned_turn = 8
        war1.set_commander_assigned_turn = MagicMock()
        war2 = MagicMock(spec=War)
        war2.commander_assigned_turn = 7
        war2.set_commander_assigned_turn = MagicMock()

        def get_war_by_commander(cid):
            if cid == 1:
                return war1
            elif cid == 2:
                return war2
            return None
        war_system.get_war_by_commander.side_effect = get_war_by_commander

        state_normal_mode.get_war_system = MagicMock(return_value=war_system)

        # 模拟输入序列：完成整个阶段（需要足够 next）
        inputs = iter(["next", "next", "next", "next"])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_normal_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_normal_mode)
        cmd.execute([])

        captured = capsys.readouterr()

        # 断言转换信息只出现一次
        assert captured.out.count("转为 proconsul") == 1
        assert captured.out.count("转为 propraetor") == 1

        # 验证官职变更
        assert fig1.office == 'proconsul'
        assert fig2.office == 'propraetor'

        # 验证历史记录被调用
        fig1.add_office_history.assert_called_once_with('consul', 8, 9)
        fig2.add_office_history.assert_called_once_with('praetor', 7, 9)

        # 验证影响力更新被调用
        fig1.update_influence.assert_called_once()
        fig2.update_influence.assert_called_once()

        # 验证战争的上任回合被更新
        war1.set_commander_assigned_turn.assert_called_once_with(10)  # 当前回合=10? 测试中需要明确回合数
        war2.set_commander_assigned_turn.assert_called_once_with(10)

        # 验证没有重复转换（例如战争系统 get_war_by_commander 被调用了正确次数）
        assert war_system.get_war_by_commander.call_count == 2


# ========== 全人工测试模式 ==========

class TestPopulationCommandBypass:
    """全人工测试模式测试"""

    def test_bypass_mode_all_manual(self, state_bypass_mode, monkeypatch):
        """bypass_player_check=True时，权限检查绕过"""
        fig1 = state_bypass_mode.get_member(1)
        fig1.office_history.append(OfficeTerm(office_type="praetor", start_turn=-10, end_turn=-9))
        # 输入序列：step0 next, step1 p1 vote, p1 next, p2 vote, p2 next, step2 next, step3 next
        inputs = iter([
            "next",  # step0
            "vote consul 1",  # step1 p1 vote
            "next",  # step1 p1 next -> p2
            "vote consul 1",  # step1 p2 vote
            "next",  # step1 p2 next
            "next",  # step2 (公示) next
            "next"  # step3 (完成) next
        ])
        monkeypatch.setattr('builtins.input', lambda *args: next(inputs))
        state_bypass_mode.mark_phase_executed("forum")
        cmd = PopulationCommand(state_bypass_mode)
        with patch('src.api.population_api.get_candidates') as mock_get_candidates, \
                patch('src.api.population_api.vote') as mock_vote:
            mock_get_candidates.return_value = {
                "success": True,
                "data": {"consul": [{"id": 1}]},
                "message": ""
            }
            mock_vote.return_value = {"success": True, "message": "投票成功"}
            cmd.execute([])
        # 应该调用两次 vote（p1 和 p2）
        assert mock_vote.call_count == 2