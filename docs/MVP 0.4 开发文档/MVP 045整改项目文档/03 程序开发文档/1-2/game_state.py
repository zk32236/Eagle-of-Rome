# src/core/game_state.py
"""
游戏状态单例容器 - 已移除单例模式，支持多实例独立创建
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.entities import Figure, Faction, GameTurn, Contract
    from core.systems.war_system import WarSystem
    from core.systems.military_system import MilitarySystem


class GameState:
    """游戏状态容器 - 多实例独立版本"""

    MAX_MEMBER_ID = 300

    # 已删除 _instance 和 __new__ 方法

    def __init__(self, config_path: Optional[str] = None):
        """
        显式实例化 - 每个调用创建独立实例

        Args:
            config_path: 配置文件路径，None时使用内置默认配置（暂未实现）
        """
        # 所有状态改为实例属性，确保实例隔离
        self._members: Dict[int, 'Figure'] = {}
        self._factions: Dict[str, 'Faction'] = {}
        self._treasury: int = 0
        self._turn: 'GameTurn' = None  # 将在 reset 中初始化
        self._event_log: List[str] = []
        self._used_ids: Set[int] = set()
        self._mortality_pool: List[int] = []
        self._config: Dict[str, Any] = {}  # 暂时为空，后续指令完善配置管理

        # 预留的系统引用
        self._war_system: Optional['WarSystem'] = None
        self._military_system: Optional['MilitarySystem'] = None
        self._curia: Optional[Any] = None  # 预留 Curia
        self._contracts: List[Any] = []    # 预留合同列表

        # 阶段执行跟踪
        self._executed_phases: Set[str] = set()

        # 初始化时调用 reset，确保状态一致性
        self.reset()

    def reset(self):
        """重置状态 - 实例方法，仅影响当前实例"""
        self._members.clear()
        self._factions.clear()
        self._treasury = 0
        # from core.entities import GameTurn  # 暂时注释，待后续完善
        self._turn = None  # 临时占位
        self._event_log.clear()
        self._used_ids.clear()
        self._initialize_mortality_pool()

        # 重置预留系统
        self._war_system = None
        self._military_system = None
        self._curia = None
        self._contracts.clear()
        self._executed_phases.clear()

    def _initialize_mortality_pool(self):
        """初始化天命池"""
        self._mortality_pool = list(range(1, self.MAX_MEMBER_ID + 1))
        random.shuffle(self._mortality_pool)

    @classmethod
    def create_for_testing(cls, test_config: Dict[str, Any]) -> 'GameState':
        """
        工厂方法: 创建测试专用实例

        绕过 __init__，直接注入测试配置，避免文件依赖
        """
        instance = cls.__new__(cls)          # 创建空实例，不调用 __init__
        instance._members = {}
        instance._factions = {}
        instance._treasury = 0
        instance._turn = None
        instance._event_log = []
        instance._used_ids = set()
        instance._mortality_pool = []
        instance._config = test_config        # 直接注入测试配置
        instance._war_system = None
        instance._military_system = None
        instance._curia = None
        instance._contracts = []
        instance._executed_phases = set()
        instance._initialize_mortality_pool()  # 依然初始化池，便于测试
        return instance

    # ========== 以下为保留的公共方法（占位实现，后续逐步完善）==========

    # ----- 成员管理 -----
    def add_member(self, member: 'Figure'):
        """添加人物（暂未实现）"""
        raise NotImplementedError("add_member 暂未实现")

    def get_member(self, member_id: int) -> Optional['Figure']:
        """获取人物（暂未实现）"""
        return None

    def get_living_members(self) -> List['Figure']:
        """获取所有存活人物（暂未实现）"""
        return []

    def get_living_member(self, member_id: int) -> Optional['Figure']:
        """获取存活人物（暂未实现）"""
        return None

    # ----- 派系管理 -----
    def add_faction(self, faction: 'Faction'):
        """添加派系（暂未实现）"""
        raise NotImplementedError("add_faction 暂未实现")

    def get_faction(self, faction_id: str) -> Optional['Faction']:
        """获取派系（暂未实现）"""
        return None

    def get_active_factions(self) -> List['Faction']:
        """获取活跃派系（暂未实现）"""
        return []

    # ----- 配置获取（占位）-----
    def get_cooldown_years(self) -> int:
        return 10  # 默认值

    def get_leaders_per_election(self) -> int:
        return 2

    def get_office_cooldown(self, office_type: str) -> int:
        return 2

    def get_offices_per_election(self, office_type: str) -> int:
        return 1

    # ----- 天命机制 -----
    def draw_mortality_number(self) -> int:
        """抽取天命号码（暂未实现）"""
        if not self._mortality_pool:
            self._initialize_mortality_pool()
        return self._mortality_pool.pop() if self._mortality_pool else 0

    # ----- 回合管理 -----
    def advance_year(self):
        """推进到下一年（暂未实现）"""
        if self._turn:
            self._turn.advance_year()
        self._executed_phases.clear()

    def is_phase_executed(self, phase_name: str) -> bool:
        return phase_name in self._executed_phases

    def mark_phase_executed(self, phase_name: str):
        self._executed_phases.add(phase_name)

    # ----- 战争/军事系统（占位）-----
    def get_war_system(self) -> Optional['WarSystem']:
        return self._war_system

    def get_active_wars(self) -> List[Any]:
        return []

    def get_military_system(self) -> Optional['MilitarySystem']:
        return self._military_system

    def is_military_prepared(self) -> bool:
        return True

    def get_military_preparation_status(self) -> tuple:
        return True, [], []

    # ----- 主持人（占位）-----
    def get_presiding_officer(self) -> Optional['Figure']:
        return None

    # ----- 日志（占位）-----
    def log_event(self, message: str):
        self._event_log.append(message)

    def get_status_summary(self) -> str:
        return "GameState stub"

    # ----- ID 分配（占位）-----
    def allocate_id(self, preferred_id: Optional[int] = None) -> int:
        return 1  # 临时

    # ----- 属性访问（供测试使用）-----
    @property
    def treasury(self):
        return self._treasury

    @treasury.setter
    def treasury(self, value):
        self._treasury = value

    @property
    def members(self):
        return self._members

    @property
    def factions(self):
        return self._factions

    @property
    def turn(self):
        return self._turn

    @property
    def event_log(self):
        return self._event_log

    @property
    def mortality_pool(self):
        return self._mortality_pool

    @property
    def config(self):
        return self._config

    @property
    def executed_phases(self):
        return self._executed_phases