# src/core/localization/term_mapping.py

from abc import ABC, abstractmethod
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.game_state import GameState


class GamePhase(Enum):
    """
    阶段枚举 - 内部使用抽象标识符，与显示名称完全解耦
    """
    MORTALITY = auto()
    REVENUE = auto()
    FORUM = auto()
    POPULATION = auto()
    SENATE = auto()
    COMBAT = auto()
    RESOLUTION = auto()

    @classmethod
    def get_sequence(cls) -> List['GamePhase']:
        """标准执行顺序"""
        return [
            cls.MORTALITY,
            cls.REVENUE,
            cls.FORUM,
            cls.POPULATION,
            cls.SENATE,
            cls.COMBAT,
            cls.RESOLUTION
        ]


@dataclass
class TermSet:
    """术语集合 - 可完整替换"""

    # 核心实体
    currency: str = "Talents"
    assembly: str = "Senate"
    nobles: str = "Senators"
    cavalry_class: str = "Equites"
    leader_title: str = "Consul"

    # 经济概念
    treasury: str = "Treasury"
    revenue: str = "Revenue"
    expense: str = "Expense"
    debt: str = "Debt"

    # 阶段名称
    phase_mortality: str = "Mortality"
    phase_revenue: str = "Revenue"
    phase_forum: str = "Forum"
    phase_population: str = "Population"
    phase_senate: str = "Senate"
    phase_combat: str = "Combat"
    phase_resolution: str = "Revolution"

    # 机制概念
    influence: str = "Influence"
    popularity: str = "Popularity"
    unrest: str = "Unrest"
    loyalty: str = "Loyalty"

    # 军事概念
    legion: str = "Legion"
    fleet: str = "Fleet"
    commander: str = "Commander"
    triumph: str = "Triumph"

    # 政治概念
    faction: str = "Faction"
    candidate: str = "Candidate"
    vote: str = "Vote"

    # 状态描述
    state_calm: str = "Calm"
    state_uneasy: str = "Uneasy"
    state_tense: str = "Tense"
    state_bad: str = "Bad"

    def get_phase_name(self, phase: GamePhase) -> str:
        """根据阶段获取对应名称"""
        mapping = {
            GamePhase.MORTALITY: self.phase_mortality,
            GamePhase.REVENUE: self.phase_revenue,
            GamePhase.FORUM: self.phase_forum,
            GamePhase.POPULATION: self.phase_population,
            GamePhase.SENATE: self.phase_senate,
            GamePhase.COMBAT: self.phase_combat,
            GamePhase.RESOLUTION: self.phase_resolution,
        }
        return mapping.get(phase, "Unknown")


class TerminologyService:
    """
    术语服务 - 运行时切换术语集
    """

    PRESETS: Dict[str, TermSet] = {
        "original": TermSet(),  # 默认当前风格

        "historical_roman": TermSet(
            currency="Denarii",
            assembly="Curia",
            nobles="Patricii",
            cavalry_class="Equites",
            leader_title="Consul",
            phase_mortality="Mortality",
            phase_revenue="Revenue",
            phase_forum="Comitium",
            phase_population="Census",
            phase_senate="Senatus",
            phase_combat="Bellum",
            phase_resolution="Tumultus",
            influence="Auctoritas",
            popularity="Gratia",
            unrest="Seditio",
            legion="Legio",
            fleet="Classis",
            commander="Imperator",
            triumph="Triumphus",
        ),

        "generic_latin": TermSet(
            currency="Pecunia",
            assembly="Concilium",
            nobles="Nobiles",
            cavalry_class="Equites",
            leader_title="Princeps",
            phase_mortality="Fatum",
            phase_revenue="Reditus",
            phase_forum="Forum",
            phase_population="Populus",
            phase_senate="Senatus",
            phase_combat="Proelium",
            phase_resolution="Exitium",
            influence="Potentia",
            popularity="Favor",
            unrest="Discordia",
            legion="Cohors",
            fleet="Navis",
            commander="Dux",
            triumph="Victoria",
        ),

        "chinese_historical": TermSet(
            currency="第纳尔",
            assembly="元老院",
            nobles="贵族",
            cavalry_class="骑士",
            leader_title="执政官",
            phase_mortality="天命",
            phase_revenue="税收",
            phase_forum="广场",
            phase_population="民查",
            phase_senate="院会",
            phase_combat="战事",
            phase_resolution="变局",
            influence="威望",
            popularity="民望",
            unrest="动乱",
            legion="军团",
            fleet="舰队",
            commander="统帅",
            triumph="凯旋",
        ),
    }

    _current: TermSet = PRESETS["original"]
    _custom: Optional[TermSet] = None

    @classmethod
    def set_preset(cls, preset_name: str) -> bool:
        """切换术语集"""
        if preset_name in cls.PRESETS:
            cls._current = cls.PRESETS[preset_name]
            cls._custom = None
            print(f"   📝 Terminology: {preset_name}")
            return True
        return False

    @classmethod
    def get(cls) -> TermSet:
        """获取当前术语集"""
        return cls._current

    @classmethod
    def customize(cls, **kwargs):
        """自定义当前术语"""
        if cls._custom is None:
            cls._custom = TermSet()
            # 复制当前设置
            for key, value in vars(cls._current).items():
                setattr(cls._custom, key, value)

        for key, value in kwargs.items():
            if hasattr(cls._custom, key):
                setattr(cls._custom, key, value)

        cls._current = cls._custom

    @classmethod
    def get_phase_display(cls, phase: GamePhase) -> str:
        """获取阶段显示名称"""
        return cls._current.get_phase_name(phase)


class PhaseExecutor(ABC):
    """阶段执行器抽象基类"""

    @property
    @abstractmethod
    def phase_id(self) -> GamePhase:
        pass

    @abstractmethod
    def execute(self, state: 'GameState') -> bool:
        pass

    def get_display_name(self) -> str:
        return TerminologyService.get_phase_display(self.phase_id)