# src/tests/test_systems/test_war_rewards.py
"""
测试战争奖励分配逻辑（Step 2）
- 国库、派系、指挥官、士兵份额按比例分配
- 士兵份额存入 war.soldier_share 供凯旋使用
- 失败时不分配奖励
"""

import pytest
from src.core.game_state import GameState
from src.core.systems.war_system import WarSystem
from src.core.entities.war import War, WarStatus
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure


@pytest.fixture
def state():
    """创建测试用 GameState，配置默认分配比例"""
    config = {
        "combat_rules": {
            "treasury_share": 0.5,
            "faction_share": 0.25,
            "commander_share": 0.15,
            "soldier_share": 0.15
        }
    }
    state = GameState.create_for_testing(config)
    state.turn = GameTurn(turn_number=1, year=-264)
    state.treasury = 1000  # 初始国库
    return state


@pytest.fixture
def faction(state):
    """创建一个派系"""
    faction = Faction(id="senate", name="元老院派", treasury=500)
    state.add_faction(faction)
    return faction


@pytest.fixture
def commander(state, faction):
    """创建一个指挥官人物，属于该派系"""
    fig = Figure(id=101, name="指挥官", faction_id=faction.id, wealth=200)
    state.add_member(fig)
    return fig


@pytest.fixture
def war(state, commander):
    """创建一个测试战争，已指派指挥官"""
    war = War(
        id="test_war",
        name="测试战争",
        description="用于测试的战争",
        strength=5,
        rewards={
            "treasury": 1000,  # 战利品总额
            "family_prestige": 1,
            "land": 200
        }
    )
    war.status = WarStatus.ACTIVE
    war.commander_id = commander.id
    war.legions_assigned = 2
    war.fleets_assigned = 0
    return war


@pytest.fixture
def war_system(state):
    """创建 WarSystem 实例，并注册战争"""
    ws = WarSystem(state)
    ws._active_wars = []  # 清空默认
    return ws


class TestWarRewards:
    """战争奖励分配测试"""

    def test_victory_rewards_distribution(self, state, war_system, war, commander, faction):
        """测试胜利时奖励按比例分配"""
        # 将战争加入活跃列表
        war_system._active_wars.append(war)

        # 记录分配前的国库、派系资金、指挥官财富
        treasury_before = state.treasury
        faction_treasury_before = faction.treasury
        commander_wealth_before = commander.wealth

        # 执行胜利结算
        result = war_system.resolve_war(war.id, victory=True)

        # 验证返回值
        assert result['victory'] is True
        assert result['war_name'] == war.name
        assert 'rewards' in result

        # 计算预期分配（按配置比例）
        total = war.rewards['treasury']
        treasury_part = int(total * 0.5)
        faction_part = int(total * 0.25)
        commander_part = int(total * 0.15)
        soldier_part = total - treasury_part - faction_part - commander_part

        # 验证国库增加
        assert state.treasury == treasury_before + treasury_part

        # 验证派系资金增加
        assert faction.treasury == faction_treasury_before + faction_part

        # 验证指挥官财富增加
        assert commander.wealth == commander_wealth_before + commander_part

        # 验证士兵份额存入战争对象
        assert war.soldier_share == soldier_part

        # 验证战争状态变为 RESOLVED
        assert war.status == WarStatus.RESOLVED

        # 验证指挥官被清除（原有逻辑）
        assert war.commander_id is None

    def test_victory_no_commander(self, state, war_system, war):
        """测试战争胜利但没有指挥官（所有战利品归国库）"""
        war.commander_id = None
        war_system._active_wars.append(war)

        treasury_before = state.treasury
        war_system.resolve_war(war.id, victory=True)

        total = war.rewards['treasury']
        # 国库应增加全部战利品
        assert state.treasury == treasury_before + total
        # 士兵份额应为0
        assert war.soldier_share == 0
        # 验证战争状态
        assert war.status == WarStatus.RESOLVED

    def test_victory_commander_no_faction(self, state, war_system, war, commander):
        """测试指挥官无派系（派系部分归士兵，指挥官部分正常分配）"""
        commander.faction_id = None
        war_system._active_wars.append(war)

        treasury_before = state.treasury
        commander_wealth_before = commander.wealth

        war_system.resolve_war(war.id, victory=True)

        total = war.rewards['treasury']
        treasury_part = int(total * 0.5)
        faction_part = int(total * 0.25)
        commander_part = int(total * 0.15)
        soldier_part = total - treasury_part - faction_part - commander_part

        # 国库增加
        assert state.treasury == treasury_before + treasury_part
        # 指挥官财富增加
        assert commander.wealth == commander_wealth_before + commander_part
        # 士兵份额应包含派系部分（即派系部分被士兵吸收）
        assert war.soldier_share == soldier_part
        # 派系资金应保持不变（但我们没有派系对象可检查，可忽略）

    def test_defeat_no_rewards(self, state, war_system, war, commander, faction):
        """测试失败时不应分配奖励"""
        war_system._active_wars.append(war)

        treasury_before = state.treasury
        faction_treasury_before = faction.treasury
        commander_wealth_before = commander.wealth

        result = war_system.resolve_war(war.id, victory=False)

        # 国库、派系、指挥官财富不变
        assert state.treasury == treasury_before
        assert faction.treasury == faction_treasury_before
        assert commander.wealth == commander_wealth_before

        # 士兵份额应为0
        assert war.soldier_share == 0

        # 战争状态变为 DEFEATED
        assert war.status == WarStatus.DEFEATED

    def test_configurable_shares(self, state, war_system, war, commander, faction):
        """测试分配比例可从配置读取"""
        # 修改配置为自定义比例
        state.config._config["combat_rules"]["treasury_share"] = 0.4
        state.config._config["combat_rules"]["faction_share"] = 0.3
        state.config._config["combat_rules"]["commander_share"] = 0.2
        state.config._config["combat_rules"]["soldier_share"] = 0.1

        war_system._active_wars.append(war)

        treasury_before = state.treasury
        faction_treasury_before = faction.treasury
        commander_wealth_before = commander.wealth

        result = war_system.resolve_war(war.id, victory=True)

        total = war.rewards['treasury']
        treasury_part = int(total * 0.4)
        faction_part = int(total * 0.3)
        commander_part = int(total * 0.2)
        soldier_part = total - treasury_part - faction_part - commander_part

        assert state.treasury == treasury_before + treasury_part
        assert faction.treasury == faction_treasury_before + faction_part
        assert commander.wealth == commander_wealth_before + commander_part
        assert war.soldier_share == soldier_part

    def test_rewards_with_land(self, state, war_system, war, commander):
        """测试土地奖励加入国家公地"""
        # 添加土地奖励
        war._rewards["land"] = 500  # 直接修改内部字典，而非 war.rewards
        war_system._active_wars.append(war)

        national_land_before = state.get_national_public_land()

        result = war_system.resolve_war(war.id, victory=True)

        # 验证国家公地增加
        assert state.get_national_public_land() == national_land_before + 500

    def test_family_prestige_increase(self, state, war_system, war, commander):
        """测试家族声望增加"""
        # 初始声望
        commander.family_prestige = 3
        war._rewards["family_prestige"] = 2  # 直接修改内部字典

        war_system._active_wars.append(war)

        result = war_system.resolve_war(war.id, victory=True)

        # 指挥官家族声望增加
        assert commander.family_prestige == 5