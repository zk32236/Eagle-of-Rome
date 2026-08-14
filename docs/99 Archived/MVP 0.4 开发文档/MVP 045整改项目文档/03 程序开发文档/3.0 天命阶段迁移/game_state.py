# src/core/game_state.py
"""
游戏状态容器 - 已移除单例模式，支持多实例独立创建
集成 Config 配置管理
"""

import random
from typing import Dict, List, Optional, Set, Any
from typing import TYPE_CHECKING

from src.core.config import Config

if TYPE_CHECKING:
    from src.core.entities import Figure, Faction, GameTurn, Contract
    from src.core.systems.war_system import WarSystem
    from src.core.systems.military_system import MilitarySystem


class GameState:
    """游戏状态容器 - 多实例独立版本"""

    MAX_MEMBER_ID = 300

    def __init__(self, config_path: Optional[str] = None):
        """
        显式实例化 - 每个调用创建独立实例

        Args:
            config_path: 配置文件路径，None时使用内置默认配置
        """
        # 创建配置实例
        self._config = Config(config_path)

        # 所有状态改为实例属性，确保实例隔离
        self._members: Dict[int, 'Figure'] = {}
        self._factions: Dict[str, 'Faction'] = {}
        self._treasury: int = 0
        self._turn: 'GameTurn' = None
        self._event_log: List[str] = []
        self._used_ids: Set[int] = set()
        self._mortality_pool: List[int] = []

        # 预留的系统引用
        self._war_system: Optional['WarSystem'] = None
        self._military_system: Optional['MilitarySystem'] = None
        self._curia: Optional[Any] = None
        self._contracts: List[Any] = []

        # 阶段执行跟踪
        self._executed_phases: Set[str] = set()

        # 初始化时调用 reset，确保状态一致性
        self.reset()

    def reset(self):
        """重置状态 - 实例方法，仅影响当前实例"""
        self._members.clear()
        self._factions.clear()
        self._treasury = 0
        self._turn = None
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
        instance = cls.__new__(cls)
        instance._members = {}
        instance._factions = {}
        instance._treasury = 0
        instance._turn = None
        instance._event_log = []
        instance._used_ids = set()
        instance._mortality_pool = []
        instance._config = Config()  # 创建临时配置实例
        instance._config._config = test_config  # 直接注入测试配置
        instance._war_system = None
        instance._military_system = None
        instance._curia = None
        instance._contracts = []
        instance._executed_phases = set()
        instance._initialize_mortality_pool()
        return instance

    # ========== 成员管理 ==========

    def add_member(self, member: 'Figure'):
        """添加人物"""
        self._used_ids.add(member.id)
        self._members[member.id] = member

    def get_member(self, member_id: int) -> Optional['Figure']:
        """获取人物"""
        return self._members.get(member_id)

    def get_living_members(self) -> List['Figure']:
        """获取所有存活人物"""
        return [m for m in self._members.values() if hasattr(m, 'is_dead') and not m.is_dead]

    def get_living_member(self, member_id: int) -> Optional['Figure']:
        """获取存活人物"""
        member = self._members.get(member_id)
        return member if (member and not member.is_dead) else None

    # ========== 派系管理 ==========

    def add_faction(self, faction: 'Faction'):
        """添加派系"""
        self._factions[faction.id] = faction

    def get_faction(self, faction_id: str) -> Optional['Faction']:
        """获取派系"""
        return self._factions.get(faction_id)

    def get_active_factions(self) -> List['Faction']:
        """获取活跃派系"""
        active = []
        for faction in self._factions.values():
            living = [m for m in faction.get_members(self) if not m.is_dead]
            if living:
                active.append(faction)
        return active

    # ========== 配置获取（通过 Config 实例）==========

    def get_cooldown_years(self) -> int:
        """获取执政官冷却期"""
        return self._config.get("political_rules.leader_cooldown_years", 10)

    def get_leaders_per_election(self) -> int:
        """获取执政官选举人数"""
        return self._config.get("political_rules.leaders_per_election", 2)

    def get_office_cooldown(self, office_type: str) -> int:
        """获取指定公职的冷却期"""
        return self._config.get(f"political_rules.office_cooldowns.{office_type}", 2)

    def get_offices_per_election(self, office_type: str) -> int:
        """获取每次选举该公职的名额"""
        return self._config.get(f"political_rules.offices_per_election.{office_type}", 1)

    def get_min_age(self, office_type: str) -> int:
        """获取指定公职的最低年龄"""
        return self._config.get(f"political_rules.min_ages.{office_type}", 30)

    # ========== 天命机制 ==========

    def draw_mortality_number(self) -> int:
        """抽取天命号码"""
        if not self._mortality_pool:
            self._initialize_mortality_pool()
        return self._mortality_pool.pop() if self._mortality_pool else 0

    # ========== 回合管理 ==========

    def advance_year(self):
        """推进到下一年"""
        if self._turn:
            self._turn.advance_year()
        self._executed_phases.clear()

    def is_phase_executed(self, phase_name: str) -> bool:
        """检查阶段是否已执行"""
        return phase_name in self._executed_phases

    def mark_phase_executed(self, phase_name: str):
        """标记阶段已执行"""
        self._executed_phases.add(phase_name)

    # ========== 战争/军事系统 ==========

    def get_war_system(self) -> Optional['WarSystem']:
        """获取战争系统"""
        return self._war_system

    def get_active_wars(self) -> List[Any]:
        """获取活跃战争列表"""
        return []

    def get_military_system(self) -> Optional['MilitarySystem']:
        """获取军事系统"""
        return self._military_system

    def is_military_prepared(self) -> bool:
        """检查军事准备状态"""
        return True

    def get_military_preparation_status(self) -> tuple:
        """获取军事准备详细状态"""
        return True, [], []

    # ========== 主持人 ==========

    def get_presiding_officer(self) -> Optional['Figure']:
        """获取主持人"""
        candidates = [
            m for m in self._members.values()
            if not m.is_dead and hasattr(m, 'is_present') and m.is_present
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: getattr(m, 'power', 0))

    # ========== 日志 ==========

    def log_event(self, message: str):
        """记录事件"""
        self._event_log.append(message)

    def get_status_summary(self) -> str:
        """生成状态摘要"""
        return f"GameState [国库:{self._treasury}, 人物:{len(self.get_living_members())}]"

    # ========== ID 分配 ==========

    def allocate_id(self, preferred_id: Optional[int] = None) -> int:
        """分配成员ID"""
        if preferred_id and preferred_id not in self._used_ids:
            if 1 <= preferred_id <= self.MAX_MEMBER_ID:
                self._used_ids.add(preferred_id)
                return preferred_id

        available = set(range(1, self.MAX_MEMBER_ID + 1)) - self._used_ids
        if not available:
            raise ValueError("No available IDs!")

        new_id = random.choice(list(available))
        self._used_ids.add(new_id)
        return new_id

    # ========== 属性访问 ==========

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

    @turn.setter
    def turn(self, value):
        self._turn = value

    @property
    def event_log(self):
        return self._event_log

    @property
    def mortality_pool(self):
        return self._mortality_pool

    @property
    def config(self):
        """获取配置实例"""
        return self._config

    @property
    def executed_phases(self):
        return self._executed_phases

    def mark_member_dead(self, member_id: int) -> bool:
        """
        标记指定ID的人物为死亡

        Args:
            member_id: 要标记死亡的人物ID

        Returns:
            bool: 操作成功返回 True，人物不存在或已死亡返回 False
        """
        member = self._members.get(member_id)
        if not member:
            return False
        if member.is_dead:
            return False

        # 标记死亡
        member.is_dead = True

        # 如果该人物是派系领袖，清除领袖标记
        if member.is_faction_leader:
            member.is_faction_leader = False

        # 从回合领导者列表中移除（如果存在）
        if self._turn and hasattr(self._turn, 'leader_ids'):
            if member_id in self._turn.leader_ids:
                self._turn.leader_ids.remove(member_id)

        # 注意：不在这里记录事件，由调用方处理
        return True