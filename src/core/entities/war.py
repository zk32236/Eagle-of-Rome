# src/core/entities/war.py

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum, auto


class WarStatus(Enum):
    """战争状态"""
    INACTIVE = auto()      # 未激活（在牌堆中）
    THREAT = auto()        # 威胁中（未爆发，但已触发）
    ACTIVE = auto()        # 活跃（正在进行）
    RESOLVED = auto()      # 已解决（胜利）
    DEFEATED = auto()      # 失败
    STALEMATE = auto()     # 僵持（未分胜负）


class WarType(Enum):
    """战争类型"""
    FOREIGN = auto()  # 外敌入侵
    CIVIL = auto()  # 内战
    BARBARIAN = auto()  # 蛮族入侵
    PROVINCIAL = auto()  # 行省叛乱


@dataclass
class War:
    """
    战争实体 - 对应战争卡

    属性设计基于《罗马共和》桌游战争卡机制：
    - 强度：决定战斗难度
    - 海军需求：是否需要舰队
    - 奖励：胜利后的收益
    - 惩罚：拖延的代价
    """

    # 基础信息
    id: str
    name: str
    description: str = ""

    # 战争类型与状态
    war_type: WarType = WarType.FOREIGN
    status: WarStatus = WarStatus.INACTIVE
    start_year: int = 0  # 预设开始年份（例如 -280）
    threat_level: int = 0  # 1=外交冲突,2=大军压境,3=战争爆发
    auto_escalate: bool = True  # 是否自动升级
    escalate_rate: int = 1  # 每回合升级点数

    _triggered_this_turn: bool = False  # 标记是否在本回合刚触发

    # 军事属性
    strength: int = 5  # 基础强度（战斗难度）
    naval_support_required: bool = False  # 是否需要海军支援
    naval_strength: int = 0  # 海军战斗强度（如需要）
    proposed_legions: int = 0  # 元老院批准的最大军团数
    declared_by: Optional[int] = None  # 宣战的执政官 ID

    # 土地战斗属性
    land_battle: bool = True  # 是否进行陆战
    disaster_numbers: List[int] = field(default_factory=list)  # CRT灾难骰点
    standoff_numbers: List[int] = field(default_factory=list)  # CRT僵持骰点

    # 🆕 指挥官状态追踪（新增）
    commander_status: str = "active"  # active/killed/fled/captured/wounded
    commander_casualty_turn: int = 0

    # 奖励（胜利时）
    rewards: Dict[str, Any] = field(default_factory=dict)

    # 包含：treasury（国库）, influence（影响力）, popularity（声望）,
    #       unrest_reduction（动乱减少）, land_bill（土地法案）等
    _soldier_share: int = 0  # 待凯旋的士兵份额


    # 惩罚（拖延时）
    penalties: Dict[str, Any] = field(default_factory=dict)
    # 包含：unrest_per_turn（每回合动乱）, treasury_cost（国库消耗）,
    #       drought（干旱）, famine（饥荒）等

    # 特殊属性
    is_imminent: bool = False  # 是否即将爆发（预警状态）
    matched_war_id: Optional[str] = None  # 配对的战争（如布匿战争分多个阶段）

    # 游戏状态
    activation_turn: int = 0  # 激活回合
    duration: int = 0  # 已持续回合数
    commander_id: Optional[int] = None  # 指派将领ID
    legions_assigned: int = 0  # 指派军团数
    fleets_assigned: int = 0  # 指派舰队数

    # 历史记录
    battle_history: List[Dict] = field(default_factory=list)  # 战斗历史
    commander_status: str = "active"  # active/fled/killed/captured
    commander_casualty_turn: int = 0  # 伤亡回合

    def __post_init__(self):
        """初始化后处理"""
        if not self.disaster_numbers:
            # 默认灾难骰点：2-4（低骰点灾难）
            self.disaster_numbers = [2, 3, 4]
        if not self.standoff_numbers:
            # 默认僵持骰点：5-9（中等骰点僵持）
            self.standoff_numbers = [5, 6, 7, 8, 9]

    def get_total_strength(self) -> int:
        """计算总强度（基础+持续时间加成）"""
        # 拖延越久，敌人越强
        duration_bonus = self.duration // 3  # 每3回合+1强度
        return self.strength + duration_bonus

    def get_naval_strength_required(self) -> int:
        """获取所需海军强度"""
        if not self.naval_support_required:
            return 0
        return self.naval_strength or (self.strength // 2)

    def is_disaster_roll(self, roll: int) -> bool:
        """检查是否为灾难骰点"""
        return roll in self.disaster_numbers

    def is_standoff_roll(self, roll: int) -> bool:
        """检查是否为僵持骰点"""
        return roll in self.standoff_numbers

    def apply_penalties(self, state: 'GameState') -> List[str]:
        """应用拖延惩罚，返回事件日志"""
        from src.core.localization import TerminologyService
        terms = TerminologyService.get()

        events = []

        # 动乱增加
        unrest = self.penalties.get('unrest_per_turn', 0)
        if unrest:
            events.append(f"{terms.unrest} +{unrest} from prolonged war")

        # 国库消耗
        cost = self.penalties.get('treasury_cost', 0)
        if cost:
            events.append(f"{terms.treasury} -{cost} {terms.currency} war expense")

        # 特殊事件
        if 'drought' in self.penalties:
            events.append("Drought strikes the countryside!")
        if 'famine' in self.penalties:
            events.append("Famine spreads through the provinces!")

        return events

    def calculate_rewards(self) -> Dict[str, int]:
        """计算胜利奖励"""
        base_rewards = dict(self.rewards)

        # 根据持续时间调整奖励（拖延太久奖励减少）
        if self.duration > 5:
            base_rewards['treasury'] = base_rewards.get('treasury', 0) // 2

        return base_rewards

    def to_display_dict(self) -> Dict[str, Any]:
        """转换为显示用字典"""
        from src.core.localization import TerminologyService
        terms = TerminologyService.get()

        return {
            'name': self.name,
            'strength': self.get_total_strength(),
            'base_strength': self.strength,
            'duration': self.duration,
            'naval_required': self.naval_support_required,
            'naval_strength': self.get_naval_strength_required(),
            'status': self.status.name,
            'rewards': self.calculate_rewards(),
            'penalties': self.penalties,
            'commander': self.commander_id,
            'forces': f"{self.legions_assigned}{terms.legion}+{self.fleets_assigned}{terms.fleet}",
        }

    def __repr__(self) -> str:
        status_emoji = {
            WarStatus.INACTIVE: "⚪",
            WarStatus.ACTIVE: "🔴",
            WarStatus.RESOLVED: "✅",
            WarStatus.DEFEATED: "❌",
            WarStatus.STALEMATE: "⏸️",
        }.get(self.status, "❓")

        naval = "⚓" if self.naval_support_required else ""
        return f"{status_emoji} {self.name}{naval}[Str:{self.get_total_strength()}]"

    def is_commander_available(self) -> bool:
        """检查指挥官是否可用"""
        if self.commander_id is None:
            return False
        return self.commander_status == "active"

    def report_commander_casualty(self, status: str, turn: int):
        """报告指挥官伤亡"""
        self.commander_status = status
        self.commander_casualty_turn = turn
        # 注意：不立即清除 commander_id，用于显示历史

    def is_commander_available(self) -> bool:
        """检查指挥官是否可用"""
        return self.commander_status == "active" and self.commander_id is not None

    def report_commander_casualty(self, status: str, turn: int):
        """报告指挥官伤亡"""
        self.commander_status = status
        self.commander_casualty_turn = turn

    @property
    def soldier_share(self) -> int:
        """返回待凯旋的士兵份额"""
        return self._soldier_share

    def set_soldier_share(self, value: int):
        """设置士兵份额（通常在战斗结算时调用）"""
        self._soldier_share = value

    def clear_soldier_share(self):
        """清零士兵份额（凯旋处理后调用）"""
        self._soldier_share = 0