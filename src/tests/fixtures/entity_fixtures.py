import pytest
from src.core.entities.entities import Province, Faction
from src.core.entities.contract import Contract, ContractType
from src.core.entities.figure import Figure
from src.core.game_state import GameState

# 原有夹具（保留）
@pytest.fixture
def sample_province():
    return Province(1, "西西里", 1000)

@pytest.fixture
def sample_knight():
    figure = Figure.create_eques(id=1001, faction_id="faction_1", age=30)
    figure.wealth = 1000
    figure.land = 100
    return figure

@pytest.fixture
def sample_faction():
    return Faction(id="faction_1", name="测试派系")

@pytest.fixture
def game_state():
    return GameState()

@pytest.fixture
def sample_tax_contract():
    return Contract.create_tax_farming(id=10, province="西西里", base_cost=90, expected_profit=150)

@pytest.fixture
def sample_project_contract():
    return Contract.create_public_works(id=11, project="道路", budget=1000, profit_margin=0.2)

# ========== 新增：T1-2 测试所需的夹具 ==========

@pytest.fixture
def sample_figure():
    """创建一个基础Figure对象（用于测试增量字段）"""
    fig = Figure(id=2001, name="测试人物")
    # 手动设置私有字段以模拟初始状态
    fig._wealth = 100
    # 增量字段默认值将由测试验证，这里不显式设置
    return fig

@pytest.fixture
def sample_knight_figure():
    """创建一个类型为骑士的Figure对象"""
    fig = Figure(id=2002, name="测试骑士")
    fig._figure_type = "knight"  # 直接设置私有属性
    fig._wealth = 200
    return fig