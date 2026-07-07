import pytest
import sys
print("sys.path:", sys.path)
core_modules = [name for name in list(sys.modules) if name.startswith('src.core')]
for name in core_modules:
    del sys.modules[name]
import inspect
from src.core.game_state import GameState
print("GameState file:", inspect.getfile(GameState))
print("log_event signature:", inspect.signature(GameState.log_event))
from pathlib import Path
import pytest
from src.core.i18n import i18n
from src.core.entities.province import Province

# 将项目根目录加入 sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.core.entities.entities import Faction
from src.core.entities.province import Province
from src.core.entities.contract import Contract, ContractType
from src.core.entities.figure import Figure
from src.core.game_state import GameState

# ==================== 原有夹具 ====================
@pytest.fixture(scope="session", autouse=True)
def load_i18n():
    """自动加载 i18n 中文文本，所有测试共享"""
    i18n.load("zh-CN")

@pytest.fixture(autouse=True)
def reset_i18n():
    from src.core.i18n import i18n
    i18n._strings = {}
    i18n.load("zh-CN")
    yield

@pytest.fixture
def sample_province():
    """创建一个测试用行省"""
    return Province(province_id=1, name="西西里", total_land=1000)

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

# ==================== 新增夹具 ====================

@pytest.fixture
def sample_figure():
    """创建一个基础Figure对象（用于测试增量字段）"""
    fig = Figure(id=2001, name="测试人物")
    fig._wealth = 100
    return fig

@pytest.fixture
def sample_figure():
    return Figure(id=1, name="Test Figure", faction_id="test_faction")

@pytest.fixture
def sample_faction():
    return Faction(id="test_faction", name="Test Faction")

@pytest.fixture
def sample_knight_figure():
    """创建一个类型为骑士的Figure对象"""
    fig = Figure(id=2002, name="测试骑士")
    fig.class_tier = "eques"
    fig._wealth = 200
    return fig