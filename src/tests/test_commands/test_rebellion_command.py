# src/tests/test_commands/test_rebellion_command.py

import pytest
from unittest.mock import Mock, patch
from src.core.game_state import GameState
from src.core.entities.province import Province
from src.core.entities.war import War, WarStatus, WarType
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction, GameTurn
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.ui.commands.phase_senate import SenateCommand
from src.ui.commands.phase_forum import ForumCommand
from src.core.deciders.war_takeover_decider import WarTakeoverDecider
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.entities.legion import Legion, LegionStatus

@pytest.fixture
def setup_game_state():
    """创建基础游戏状态"""
    state = GameState.create_for_testing({})
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state.turn = GameTurn(turn_number=10, year=-270)
    state.treasury = 1000

    # 预先创建一些可征召的军团（UNRAISED状态）
    ms = state._military_system
    for i in range(1, 11):
        ms._legions[i] = Legion(number=i, status=LegionStatus.UNRAISED)
    return state

@pytest.fixture
def create_rebellion_war(setup_game_state):
    """创建起义战争的辅助函数"""
    def _create(province):
        war_system = setup_game_state.get_war_system()
        war = war_system.create_rebellion_war(province)
        war_system._active_wars.append(war)
        return war
    return _create


@pytest.fixture
def create_province_with_governor(setup_game_state):
    """创建有总督的行省"""
    def _create(province_id, governor_id, designate_id=None):
        province = Province(
            province_id=province_id,
            name=f"Test Province {province_id}",
            total_land=1000,
            conquered=True,
            governor_id=governor_id,
            governor_designate_id=designate_id
        )
        setup_game_state.add_province(province)
        return province
    return _create


@pytest.fixture
def add_figure(setup_game_state):
    """添加人物到游戏状态"""
    def _add(figure_id, name, faction_id=None):
        fig = Figure(id=figure_id, name=name, faction_id=faction_id)
        setup_game_state.add_member(fig)
        return fig
    return _add


@pytest.fixture
def add_faction(setup_game_state):
    """添加派系"""
    def _add(faction_id, name):
        faction = Faction(id=faction_id, name=name, treasury=1000)
        setup_game_state.add_faction(faction)
        return faction
    return _add


def test_assign_rebellion_commander_with_designate_governor(
    setup_game_state, create_rebellion_war, create_province_with_governor,
    add_figure, add_faction
):
    """测试行省有候任总督时，在元老院阶段指派其为指挥官"""
    state = setup_game_state
    faction = add_faction("test", "Test Faction")
    governor = add_figure(101, "Governor", faction.id)
    designate = add_figure(102, "Designate Governor", faction.id)

    province = create_province_with_governor(1, governor.id, designate.id)
    war = create_rebellion_war(province)
    assert war.commander_id is None  # 初始无指挥官

    # 模拟元老院阶段
    cmd = SenateCommand(state)
    # 直接调用指派方法
    cmd._assign_rebellion_commanders()

    # 验证战争有了指挥官（应为候任总督）
    assert war.commander_id == designate.id
    # 验证候任总督出征状态
    assert designate.is_absent is True
    # 验证军团被征召并指派
    ms = state.get_military_system()
    legions = ms.get_legions_for_battle(war.id)
    assert len(legions) > 0
    for legion in legions:
        assert legion.commander_id == designate.id
        assert legion.war_id == war.id


def test_assign_rebellion_commander_with_current_governor(
    setup_game_state, create_rebellion_war, create_province_with_governor,
    add_figure, add_faction
):
    """测试行省有现任总督（无候任）时，指派现任总督"""
    state = setup_game_state
    faction = add_faction("test", "Test Faction")
    governor = add_figure(101, "Governor", faction.id)

    province = create_province_with_governor(1, governor.id, designate_id=None)
    war = create_rebellion_war(province)
    assert war.commander_id is None

    cmd = SenateCommand(state)
    cmd._assign_rebellion_commanders()

    assert war.commander_id == governor.id
    assert governor.is_absent is True
    ms = state.get_military_system()
    legions = ms.get_legions_for_battle(war.id)
    assert len(legions) > 0


def test_no_governor_no_assignment(
    setup_game_state, create_rebellion_war, create_province_with_governor
):
    """测试行省无总督时，战争保持无指挥官"""
    state = setup_game_state
    province = create_province_with_governor(1, governor_id=None, designate_id=None)
    war = create_rebellion_war(province)
    assert war.commander_id is None

    cmd = SenateCommand(state)
    cmd._assign_rebellion_commanders()

    assert war.commander_id is None
    ms = state.get_military_system()
    legions = ms.get_legions_for_battle(war.id)
    assert len(legions) == 0


def test_war_takeover_decider_ignores_rebellion_war(
    setup_game_state, create_rebellion_war, create_province_with_governor,
    add_figure, add_faction
):
    """测试执政官接管决策器对起义战争返回 False"""
    state = setup_game_state
    faction = add_faction("test", "Test Faction")
    consul = add_figure(201, "Consul", faction.id)
    governor = add_figure(101, "Governor", faction.id)

    province = create_province_with_governor(1, governor.id, designate_id=None)
    war = create_rebellion_war(province)
    # 暂不指派，测试接管决策器

    decider = AutoWarTakeoverDecider()
    result = decider.decide_takeover(war, consul, None, state)
    assert result is False

    # 再测试常规战争（非起义）应返回 True
    normal_war = War(id="normal", name="Normal War", naval_required=False)
    normal_war.status = WarStatus.ACTIVE
    result = decider.decide_takeover(normal_war, consul, None, state)
    assert result is True  # 假设默认概率1.0


def test_rebellion_war_timeline(
    setup_game_state, create_province_with_governor,
    add_figure, add_faction
):
    """完整流程测试：广场阶段触发起义 -> 元老院指派 -> 战斗阶段镇压"""
    state = setup_game_state
    faction = add_faction("test", "Test Faction")
    governor = add_figure(101, "Governor", faction.id)
    province = create_province_with_governor(1, governor.id, designate_id=None)
    province.set_grievance(3)

    forum_cmd = ForumCommand(state)
    forum_cmd._update_civil_unrest()

    war_system = state.get_war_system()
    active_wars = war_system.get_active_wars()
    assert len(active_wars) == 1
    war = active_wars[0]
    assert war.rebellion_province_id == 1
    assert war.commander_id is None

    senate_cmd = SenateCommand(state)
    senate_cmd._assign_rebellion_commanders()

    assert war.commander_id == governor.id
    assert governor.is_absent is True

    # 直接调用战争结算（胜利），模拟战斗阶段镇压成功
    war_system.resolve_war(war.id, victory=True)

    # 验证战争已解决
    assert war.status == WarStatus.RESOLVED
    assert province.grievance == 0
    assert governor.family_prestige == 1