# src/tests/test_commands/test_phase_forum.py
"""
广场阶段命令单元测试 - 覆盖三种运行模式和所有功能
"""
import pytest
from unittest.mock import MagicMock, patch, call
from io import StringIO

from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarStatus
from src.core.systems.war_system import WarSystem
from src.ui.commands.phase_forum import ForumCommand
from src.core.i18n import i18n

i18n.load("zh-CN")


@pytest.fixture
def state_with_players():
    """创建一个包含三个玩家的 GameState 用于测试"""
    state = MagicMock(spec=GameState)
    state.config.get = MagicMock(return_value=False)  # 默认 auto_forum=False, bypass=False
    state.is_phase_executed.return_value = False
    state.turn = MagicMock()
    state.turn.turn_number = 1
    state.turn.year = -282

    # 创建玩家对象
    player1 = MagicMock()
    player1.player_id = "p1"
    player1.faction_id = "faction1"
    player1.player_type = PlayerType.HUMAN

    player2 = MagicMock()
    player2.player_id = "p2"
    player2.faction_id = "faction2"
    player2.player_type = PlayerType.HUMAN

    player3 = MagicMock()
    player3.player_id = "p3"
    player3.faction_id = "faction3"
    player3.player_type = PlayerType.HUMAN

    state.get_all_players.return_value = [player1, player2, player3]
    state.get_player.side_effect = lambda pid: {"p1": player1, "p2": player2, "p3": player3}.get(pid)

    # 派系
    faction1 = Faction(id="faction1", name="Faction1", treasury=100)
    faction2 = Faction(id="faction2", name="Faction2", treasury=100)
    faction3 = Faction(id="faction3", name="Faction3", treasury=100)
    state.get_faction.side_effect = lambda fid: {"faction1": faction1, "faction2": faction2, "faction3": faction3}.get(fid)
    state.factions = {"faction1": faction1, "faction2": faction2, "faction3": faction3}

    # 派系成员
    faction1.get_members = MagicMock(return_value=[])
    faction2.get_members = MagicMock(return_value=[])
    faction3.get_members = MagicMock(return_value=[])

    # 模拟意大利行省
    italy = MagicMock()
    italy.province_id = 0
    italy.grievance = 0
    italy._turns_since_last_land_distribution = 0
    italy.land_public = 1000
    italy.conquered = True
    italy.set_grievance = MagicMock()
    italy.event_flags = {}
    italy.set_event_flag = MagicMock()
    state.get_province.side_effect = lambda pid: italy if pid == 0 else None
    state.get_all_provinces.return_value = [italy]

    # 其他必要属性
    state.curia = MagicMock()
    state.curia.get_all_available.return_value = []
    state.get_economic_rule.return_value = 6  # 成员上限
    state._turn_order = ["p1", "p2", "p3"]  # 回合顺序
    state.get_current_player.return_value = player1
    state.mark_phase_executed = MagicMock()
    state.add_forum_action = MagicMock()
    state.get_forum_pending.return_value = {"recruitment_bids": [], "contract_bids": [], "land_purchases": [],
                                             "triumph_votes": [], "land_trades": []}
    state.clear_forum_pending = MagicMock()

    # 添加战争系统模拟
    war_system = MagicMock(spec=WarSystem)
    war_system.check_triggers = MagicMock()
    war_system.escalate_threats = MagicMock(return_value=[])
    war_system.get_active_wars = MagicMock(return_value=[])
    war_system.get_truce_wars_with_pending_treaty = MagicMock(return_value=[])
    war_system._war_discard = []  # 待凯旋战争列表
    war_system.create_rebellion_war = MagicMock()
    state.get_war_system.return_value = war_system

    # 添加海军系统模拟
    naval_system = MagicMock()
    naval_system.generate_construction_contracts = MagicMock(return_value=[])
    naval_system.generate_replacement_contracts = MagicMock(return_value=[])
    state.naval_system = naval_system

    return state


@pytest.fixture
def mock_deciders():
    """模拟自动决策器"""
    retirement = MagicMock()
    recruitment = MagicMock()
    bid = MagicMock()
    land_trade = MagicMock()
    triumph = MagicMock()
    return retirement, recruitment, bid, land_trade, triumph


# ========== 原有通过的测试用例 ==========

def test_auto_mode_full_auto(state_with_players, mock_deciders):
    """测试全自动模式 (auto_forum=True)"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "testing.bypass_player_check": False
    }.get(key, default)

    retirement, recruitment, bid, land_trade, triumph = mock_deciders

    retirement.decide_whom_to_retire.return_value = None
    recruitment.decide_bids.return_value = {}
    bid.decide_tax_bid.return_value = None
    bid.decide_works_bid.return_value = None
    bid.decide_fleet_bid.return_value = None
    land_trade.decide_trade.return_value = None
    triumph.decide_triumph.return_value = False

    cmd = ForumCommand(state,
                       retirement_decider=retirement,
                       recruitment_decider=recruitment,
                       bid_decider=bid,
                       land_trade_decider=land_trade,
                       triumph_decider=triumph)

    with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
        result = cmd.execute([])

    assert result is True
    assert retirement.decide_whom_to_retire.call_count == 3
    assert recruitment.decide_bids.call_count == 3
    assert bid.decide_tax_bid.call_count == 0
    assert land_trade.decide_trade.call_count == 3
    assert triumph.decide_triumph.call_count == 0
    state.mark_phase_executed.assert_called_once_with("forum")


def test_auto_mode_with_actions(state_with_players, mock_deciders):
    """测试全自动模式，有具体操作"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "testing.bypass_player_check": False
    }.get(key, default)

    contract = Contract(id=1, contract_type=ContractType.PUBLIC_WORKS, name="Test Contract")
    contract.status = ContractStatus.BUDGETED
    state.contracts = [contract]

    figure = MagicMock(spec=Figure)
    figure.id = 101
    figure.name = "Test Figure"
    figure.get_formal_name.return_value = "Test Figure"
    state.curia.get_all_available.return_value = [figure]

    knight = MagicMock(spec=Figure)
    knight.id = 201
    knight.class_tier = ClassTier.EQUES
    knight.is_dead = False
    faction = state.get_faction("faction1")
    faction.get_members.return_value = [knight]

    retirement, recruitment, bid, land_trade, triumph = mock_deciders

    retirement.decide_whom_to_retire.side_effect = [101, None, None]
    recruitment.decide_bids.return_value = {101: 10}
    bid.decide_works_bid.return_value = (knight, 50, 0.1, 5, 10)
    land_trade.decide_trade.return_value = (1, 2, 3)
    triumph.decide_triumph.return_value = True

    # 模拟卖家（ID=1）和买家（ID=2）
    seller_mock = MagicMock(spec=Figure)
    seller_mock.id = 1
    seller_mock.popularity = 5
    seller_mock.influence = 10
    seller_mock.faction_id = "faction1"

    buyer_mock = MagicMock(spec=Figure)
    buyer_mock.id = 2
    buyer_mock.popularity = 8
    buyer_mock.influence = 6
    buyer_mock.faction_id = "faction2"

    def get_member_side_effect(fid):
        if fid == 1:
            return seller_mock
        elif fid == 2:
            return buyer_mock
        return None

    state.get_member.side_effect = get_member_side_effect

    war = MagicMock()
    commander = MagicMock()
    cmd = ForumCommand(state,
                       retirement_decider=retirement,
                       recruitment_decider=recruitment,
                       bid_decider=bid,
                       land_trade_decider=land_trade,
                       triumph_decider=triumph)
    cmd._get_war_triumph = MagicMock(return_value={"war": war, "commander": commander})

    with patch('src.api.forum_api.retire_figure') as mock_retire:
        result = cmd.execute([])

    assert result is True
    mock_retire.assert_called_once_with(state, "p1", 101)
    state.add_forum_action.assert_any_call("recruitment_bids", ("faction1", 101, 10))
    state.add_forum_action.assert_any_call("contract_bids", (1, "faction1", 50))
    # 根据 land_trading_service 逻辑计算预期价格
    # BASE_LAND_PRICE = 10, modifier = 1 + 0.10 (influence) = 1.10, unit_price = 11, total = 33
    state.add_forum_action.assert_any_call("land_trades", (1, 2, 3, 33))
    state.add_forum_action.assert_any_call("triumph_votes", ("faction1", True))
    state.mark_phase_executed.assert_called_once_with("forum")


def test_normal_mode_human_manual(state_with_players):
    """测试正常模式：人类玩家手动"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": False,
        "testing.bypass_player_check": False
    }.get(key, default)

    cmd = ForumCommand(state)
    cmd._step = 1
    cmd._players = ["p1", "p2", "p3"]
    cmd._current_player_index = 0

    with patch.object(cmd, '_print_ui_03_1') as mock_print, \
         patch('builtins.input', side_effect=["investigate 1", "retire 1", "next"]) as mock_input, \
         patch.object(cmd, '_handle_investigate') as mock_investigate, \
         patch.object(cmd, '_handle_retire') as mock_retire, \
         patch.object(cmd, '_handle_next') as mock_next:

        cmd._handle_step_1()

        mock_print.assert_called_once_with("p1", "faction1")
        assert mock_input.call_count == 3
        mock_investigate.assert_called_once_with(["1"])
        mock_retire.assert_called_once_with(["1"])
        mock_next.assert_called_once_with([])


def test_normal_mode_ai_auto(state_with_players, mock_deciders):
    """测试正常模式：AI玩家自动执行"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": False,
        "testing.bypass_player_check": False
    }.get(key, default)

    players = state.get_all_players()
    players[0].player_type = PlayerType.HUMAN
    players[1].player_type = PlayerType.AI
    players[2].player_type = PlayerType.AI

    retirement, recruitment, bid, land_trade, triumph = mock_deciders
    retirement.decide_whom_to_retire.return_value = None
    recruitment.decide_bids.return_value = {}
    land_trade.decide_trade.return_value = None

    cmd = ForumCommand(state,
                       retirement_decider=retirement,
                       recruitment_decider=recruitment,
                       bid_decider=bid,
                       land_trade_decider=land_trade,
                       triumph_decider=triumph)

    cmd._step = 1
    cmd._players = ["p2"]
    cmd._current_player_index = 0

    with patch.object(cmd, '_handle_next') as mock_next:
        cmd._handle_step_1()
        retirement.decide_whom_to_retire.assert_called_once()
        mock_next.assert_called_once_with([])


def test_manual_bypass_mode(state_with_players):
    """测试全人工测试模式 (auto_forum=False, bypass_player_check=True)"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": False,
        "testing.bypass_player_check": True
    }.get(key, default)

    cmd = ForumCommand(state)
    cmd._step = 1
    cmd._players = ["p1", "p2"]
    cmd._current_player_index = 0

    with patch.object(cmd, '_print_ui_03_1') as mock_print, \
         patch('builtins.input', side_effect=["next"]) as mock_input, \
         patch.object(cmd, '_handle_next') as mock_next:

        cmd._handle_step_1()

        mock_print.assert_called_once_with("p1", "faction1")
        mock_input.assert_called_once()
        mock_next.assert_called_once_with([])


# ========== 新增测试：舰队合同生成 ==========

def test_fleet_contracts_generated_in_auto_mode(state_with_players):
    """测试自动模式下，海军系统生成舰队建造合同"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "testing.bypass_player_check": False
    }.get(key, default)

    cmd = ForumCommand(state)

    with patch('sys.stdout', new_callable=StringIO):
        result = cmd.execute([])

    assert result is True
    # 验证 generate_construction_contracts 被调用
    state.naval_system.generate_construction_contracts.assert_called_once_with(state.turn.turn_number)
    # 验证 generate_replacement_contracts 也被调用
    state.naval_system.generate_replacement_contracts.assert_called_once_with(state.turn.turn_number)


# ========== 新增测试：凯旋审批 ==========

def test_triumph_approved_in_auto_mode(state_with_players, mock_deciders):
    """测试自动模式下，凯旋批准时添加临时影响力"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "testing.bypass_player_check": False
    }.get(key, default)

    # 准备待凯旋战争
    war = MagicMock(spec=War)
    war.id = "war1"
    war.name = "Test War"
    war.status = WarStatus.RESOLVED
    war.soldier_share = 50
    war.commander_id = 101
    war.triumph_commander_id = None
    war.set_triumph_approved = MagicMock()
    war.set_soldier_share = MagicMock()

    # 指挥官
    commander = MagicMock(spec=Figure)
    commander.id = 101
    commander.name = "Test Commander"
    commander.is_dead = False
    commander.add_temp_influence_task = MagicMock()

    # 将战争添加到 war_discard
    ws = state.get_war_system()
    ws._war_discard = [war]
    state.get_member.side_effect = lambda fid: commander if fid == 101 else None

    # 设置凯旋决策器返回 True（批准）
    retirement, recruitment, bid, land_trade, triumph = mock_deciders
    triumph.decide_triumph.return_value = True
    land_trade.decide_trade.return_value = None  # 关键修复：避免土地交易解包错误
    retirement.decide_whom_to_retire.return_value = None
    recruitment.decide_bids.return_value = {}
    bid.decide_tax_bid.return_value = None
    bid.decide_works_bid.return_value = None
    bid.decide_fleet_bid.return_value = None


    # 配置凯旋持续时间
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "combat_rules.triumph_veteran_duration": 5,
        "testing.bypass_player_check": False
    }.get(key, default)

    cmd = ForumCommand(state,
                       retirement_decider=retirement,
                       recruitment_decider=recruitment,
                       bid_decider=bid,
                       land_trade_decider=land_trade,
                       triumph_decider=triumph)

    with patch('sys.stdout', new_callable=StringIO):
        result = cmd.execute([])

    assert result is True
    # 验证临时影响力任务添加 (soldier_share // duration = 50 // 5 = 10)
    commander.add_temp_influence_task.assert_called_once_with(10, 5)
    war.set_triumph_approved.assert_called_once_with(True)
    war.set_soldier_share.assert_called_once_with(0)


def test_triumph_rejected_in_auto_mode(state_with_players, mock_deciders):
    """测试自动模式下，凯旋否决时不添加临时影响力"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "testing.bypass_player_check": False
    }.get(key, default)

    war = MagicMock(spec=War)
    war.id = "war1"
    war.status = WarStatus.RESOLVED
    war.soldier_share = 50
    war.commander_id = 101
    war.triumph_commander_id = None
    war.set_triumph_approved = MagicMock()
    war.set_soldier_share = MagicMock()

    commander = MagicMock(spec=Figure)
    commander.id = 101
    commander.is_dead = False
    commander.add_temp_influence_task = MagicMock()

    ws = state.get_war_system()
    ws._war_discard = [war]
    state.get_member.side_effect = lambda fid: commander if fid == 101 else None

    retirement, recruitment, bid, land_trade, triumph = mock_deciders
    triumph.decide_triumph.return_value = False  # 否决
    land_trade.decide_trade.return_value = None
    retirement.decide_whom_to_retire.return_value = None
    recruitment.decide_bids.return_value = {}
    bid.decide_tax_bid.return_value = None
    bid.decide_works_bid.return_value = None
    bid.decide_fleet_bid.return_value = None

    cmd = ForumCommand(state,
                       retirement_decider=retirement,
                       recruitment_decider=recruitment,
                       bid_decider=bid,
                       land_trade_decider=land_trade,
                       triumph_decider=triumph)

    with patch('sys.stdout', new_callable=StringIO):
        result = cmd.execute([])

    assert result is True
    commander.add_temp_influence_task.assert_not_called()
    war.set_triumph_approved.assert_not_called()
    war.set_soldier_share.assert_called_once_with(0)


def test_triumph_commander_dead_in_auto_mode(state_with_players, mock_deciders):
    """测试自动模式下，指挥官死亡时不进行凯旋"""
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "testing.bypass_player_check": False
    }.get(key, default)

    war = MagicMock(spec=War)
    war.id = "war1"
    war.status = WarStatus.RESOLVED
    war.soldier_share = 50
    war.commander_id = 101
    war.triumph_commander_id = None
    war.set_soldier_share = MagicMock()

    commander = MagicMock(spec=Figure)
    commander.id = 101
    commander.is_dead = True  # 已死亡
    commander.add_temp_influence_task = MagicMock()

    ws = state.get_war_system()
    ws._war_discard = [war]
    state.get_member.side_effect = lambda fid: commander if fid == 101 else None

    retirement, recruitment, bid, land_trade, triumph = mock_deciders
    triumph.decide_triumph.return_value = True  # 即使决策器返回True，也不应执行
    land_trade.decide_trade.return_value = None
    retirement.decide_whom_to_retire.return_value = None
    recruitment.decide_bids.return_value = {}
    bid.decide_tax_bid.return_value = None
    bid.decide_works_bid.return_value = None
    bid.decide_fleet_bid.return_value = None

    cmd = ForumCommand(state,
                       retirement_decider=retirement,
                       recruitment_decider=recruitment,
                       bid_decider=bid,
                       land_trade_decider=land_trade,
                       triumph_decider=triumph)

    with patch('sys.stdout', new_callable=StringIO):
        result = cmd.execute([])

    assert result is True
    commander.add_temp_influence_task.assert_not_called()
    triumph.decide_triumph.assert_not_called()  # 不应该调用决策器
    war.set_soldier_share.assert_called_once_with(0)


def test_multiple_triumph_wars_in_auto_mode(state_with_players, mock_deciders):
    state = state_with_players
    state.config.get.side_effect = lambda key, default=None: {
        "testing.auto_forum": True,
        "combat_rules.triumph_veteran_duration": 5,
        "testing.bypass_player_check": False
    }.get(key, default)

    # 创建战争1
    war1 = MagicMock(spec=War)
    war1.id = "war1"
    war1.status = WarStatus.RESOLVED
    war1.soldier_share = 50
    war1.commander_id = 101
    war1.triumph_commander_id = None
    war1.set_triumph_approved = MagicMock()
    war1.set_soldier_share = MagicMock()
    def set_soldier_share1(value):
        war1.soldier_share = value
    war1.set_soldier_share.side_effect = set_soldier_share1

    # 创建战争2
    war2 = MagicMock(spec=War)
    war2.id = "war2"
    war2.status = WarStatus.RESOLVED
    war2.soldier_share = 30
    war2.commander_id = 102
    war2.triumph_commander_id = None
    war2.set_triumph_approved = MagicMock()
    war2.set_soldier_share = MagicMock()
    def set_soldier_share2(value):
        war2.soldier_share = value
    war2.set_soldier_share.side_effect = set_soldier_share2

    # 创建指挥官
    commander1 = MagicMock(spec=Figure)
    commander1.id = 101
    commander1.is_dead = False
    commander1.add_temp_influence_task = MagicMock()
    commander1.name = "Commander1"

    commander2 = MagicMock(spec=Figure)
    commander2.id = 102
    commander2.is_dead = False
    commander2.add_temp_influence_task = MagicMock()
    commander2.name = "Commander2"

    # 设置战争系统
    ws = state.get_war_system()
    ws._war_discard = [war1, war2]

    def get_member_side_effect(fid):
        if fid == 101:
            return commander1
        elif fid == 102:
            return commander2
        return None
    state.get_member.side_effect = get_member_side_effect

    retirement, recruitment, bid, land_trade, triumph = mock_deciders
    triumph.decide_triumph.side_effect = [True, False]  # 第一个批准，第二个否决
    land_trade.decide_trade.return_value = None
    retirement.decide_whom_to_retire.return_value = None
    recruitment.decide_bids.return_value = {}
    bid.decide_tax_bid.return_value = None
    bid.decide_works_bid.return_value = None
    bid.decide_fleet_bid.return_value = None

    cmd = ForumCommand(state,
                       retirement_decider=retirement,
                       recruitment_decider=recruitment,
                       bid_decider=bid,
                       land_trade_decider=land_trade,
                       triumph_decider=triumph)

    with patch('sys.stdout', new_callable=StringIO):
        result = cmd.execute([])

    assert result is True
    # 验证两个战争都被处理
    assert triumph.decide_triumph.call_count == 2
    commander1.add_temp_influence_task.assert_called_once_with(10, 5)  # 50//5=10
    commander2.add_temp_influence_task.assert_not_called()
    war1.set_triumph_approved.assert_called_once_with(True)
    war2.set_triumph_approved.assert_not_called()
    war1.set_soldier_share.assert_called_with(0)
    war2.set_soldier_share.assert_called_with(0)