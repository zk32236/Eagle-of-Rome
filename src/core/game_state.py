# src/core/game_state.py
"""
游戏状态容器 - 已移除单例模式，支持多实例独立创建
集成 Config 配置管理
"""

import random
from typing import Dict, List, Optional, Set, Any
from typing import TYPE_CHECKING

from src.core.config import Config
from src.core.entities.curia import Curia
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.entities import Province
from src.core.entities.figure import Figure


if TYPE_CHECKING:
    from src.core.entities import Faction, GameTurn
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
        Figure.load_config(self._config)

        # 所有状态改为实例属性，确保实例隔离
        self._members: Dict[int, 'Figure'] = {}
        self._factions: Dict[str, 'Faction'] = {}
        self._treasury: int = 0
        self._national_public_land = 0
        self._turn: 'GameTurn' = None
        self._event_log: List[str] = []
        self._used_ids: Set[int] = set()
        self._mortality_pool: List[int] = []


        # 预留的系统引用
        self._war_system: Optional['WarSystem'] = None
        self._military_system: Optional['MilitarySystem'] = None
        self._curia: Optional[Curia] = None          # 将初始化为 Curia 实例
        self._contracts: List[Any] = []               # 原有合同列表（可能为旧版，但我们将用字典替换）

        # 阶段执行跟踪
        self._executed_phases: Set[str] = set()

        # ==================== MVP 0.5 新增字段 ====================
        self._provinces: Dict[int, Province] = {}      # 行省注册表
        self._contracts_dict: Dict[int, Contract] = {} # 合同注册表（字典，替代原有列表）
        self._public_land_total: int = 0                # 全局公地总数
        self._contract_id_counter: int = 1              # 合同ID自增计数器


        # 初始化时调用 reset，确保状态一致性
        self.reset()

    def reset(self):
        """重置状态 - 实例方法，仅影响当前实例"""
        self._members.clear()
        self._factions.clear()
        self._treasury = 0
        self._national_public_land = 0
        self._turn = None
        self._event_log.clear()
        self._used_ids.clear()
        self._initialize_mortality_pool()

        # 重置预留系统
        self._war_system = None
        self._military_system = None
        self._curia = Curia()  # 改为创建新 Curia 实例
        self._contracts.clear()
        self._executed_phases.clear()

        # ==================== MVP 0.5 重置新增字段 ====================
        self._provinces.clear()
        self._contracts_dict.clear()
        self._public_land_total = 0
        self._contract_id_counter = 1

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
        instance._curia = Curia()  # 必须初始化 Curia
        instance._contracts = []
        instance._executed_phases = set()
        instance._initialize_mortality_pool()

        # ==================== MVP 0.5 初始化新增字段 ====================
        instance._provinces = {}
        instance._contracts_dict = {}
        instance._public_land_total = 0
        instance._contract_id_counter = 1
        instance._national_public_land = test_config.get("economic_rules", {}).get("initial_national_public_land", 1000)

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

    # ========== 新增：人物财富管理 ==========
    def add_figure_wealth(self, figure_id: int, amount: int) -> bool:
        """
        增加/减少人物财富

        Args:
            figure_id: 人物ID
            amount: 增加金额（可为负）

        Returns:
            bool: 操作成功返回 True，人物不存在或已死亡返回 False
        """
        figure = self.get_member(figure_id)
        if not figure or figure.is_dead:
            return False
        figure.wealth += amount
        return True

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

    # ========== 新增：派系资金管理 ==========
    def add_faction_treasury(self, faction_id: str, amount: int) -> bool:
        """
        增加/减少派系资金

        Args:
            faction_id: 派系ID
            amount: 增加金额（可为负）

        Returns:
            bool: 操作成功返回 True，派系不存在返回 False
        """
        faction = self.get_faction(faction_id)
        if not faction:
            return False
        faction.treasury += amount
        return True

    # ========== 国库管理 ==========

    @property
    def treasury(self):
        return self._treasury

    @treasury.setter
    def treasury(self, value):
        self._treasury = value

    # ========== 新增：国库增减方法 ==========
    def add_treasury(self, amount: int) -> int:
        """
        增加/减少国库

        Args:
            amount: 增加金额（可为负）

        Returns:
            int: 修改后的国库金额
        """
        self._treasury += amount
        return self._treasury

    # ========== 新增：公地增减方法 ==========
    def add_national_public_land(self, amount: int) -> None:
        self._national_public_land += amount
        self.sync_italy_public_land()

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

    # ========== 新增：经济规则配置获取 ==========
    def get_economic_rule(self, key: str, default: Any = None) -> Any:
        """
        获取经济规则配置值

        Args:
            key: 配置键，如 "base_tax"
            default: 默认值

        Returns:
            配置值
        """
        return self._config.get(f"economic_rules.{key}", default)

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
        """获取元老院主持人（官职等级最高者，同等级则选影响力高者）"""
        candidates = [
            m for m in self._members.values()
            if not m.is_dead and m.is_present
        ]
        if not candidates:
            return None
        # 按 rank 降序，rank 相同时按 influence 降序
        return max(candidates, key=lambda m: (m.rank, m.influence))

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

    # ========== 死亡标记（之前添加）==========
    def mark_member_dead(self, member_id: int, transfer_land: bool = True) -> bool:
        """
        标记指定ID的人物为死亡

        Args:
            member_id: 要标记死亡的人物ID
            transfer_land: 是否将私地转为国家公地

        Returns:
            bool: 操作成功返回 True，人物不存在或已死亡返回 False
        """
        member = self._members.get(member_id)
        if not member:
            return False
        if member.is_dead:
            return False

        # 土地回收：将私地转为国家公地
        if transfer_land:
            land = member._land_private  # 获取私地数量
            if land > 0:
                self.add_national_public_land(land)
                member._land_private = 0  # 清零人物私地
                # 可在此记录日志，但暂时省略

        member.is_dead = True

        if member.is_faction_leader:
            member.is_faction_leader = False

        if self._turn and hasattr(self._turn, 'leader_ids'):
            if member_id in self._turn.leader_ids:
                self._turn.leader_ids.remove(member_id)

        return True

    # ========== 属性访问 ==========

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

    @property
    def contracts(self):
        """获取合同列表（从 _contracts_dict 获取）"""
        return list(self._contracts_dict.values())

    @property
    def curia(self) -> Curia:
        """获取广场等待区实例"""
        return self._curia

    @contracts.setter
    def contracts(self, value):
        """兼容旧版设置"""
        self._contracts = value

    # ==================== MVP 0.5 新增接口 ====================

    # ----------公地管理----------
    def get_national_public_land(self) -> int:
        """获取国家公地总量"""
        return self._national_public_land

    # ---------- 行省管理 ----------
    def add_province(self, province: Province) -> None:
        """
        向行省注册表添加行省对象，并更新全局公地总数。

        Args:
            province: 要添加的行省对象。
        """
        self._provinces[province.province_id] = province
        self._update_global_public_land()

    def get_province(self, province_id: int) -> Optional[Province]:
        """
        根据ID获取行省对象，不存在则返回None。

        Args:
            province_id: 行省ID。

        Returns:
            行省对象或None。
        """
        return self._provinces.get(province_id)

    def get_all_provinces(self) -> List[Province]:
        """
        返回所有行省对象的列表（副本，防止外部修改）。

        Returns:
            行省列表。
        """
        return list(self._provinces.values())

    def _update_global_public_land(self) -> None:
        """
        私有方法：遍历行省注册表，更新全局公地总数。
        """
        self._public_land_total = sum(p.land_public for p in self._provinces.values())

    # ---------- 合同管理 ----------
    def create_contract(self, contract_type: ContractType, province_id: int,
                        base_cost: int, current_turn: int) -> Contract:
        """
        创建并添加合同对象，自动分配唯一ID。

        Args:
            contract_type: 合同类型（ContractType.TAX_FARMING 或 ContractType.PUBLIC_WORKS）
            province_id: 关联的行省ID。
            base_cost: 基础成本/预算。
            current_turn: 当前回合数。

        Returns:
            新建的 Contract 对象。
        """
        contract = Contract(
            id=self._contract_id_counter,
            contract_type=contract_type,
            _province_id=province_id,
            _create_turn=current_turn,
            base_cost=base_cost
        )
        self._contracts_dict[self._contract_id_counter] = contract
        self._contract_id_counter += 1
        return contract

    def get_contract(self, contract_id: int) -> Optional[Contract]:
        return self._contracts_dict.get(contract_id)

    def get_all_contracts(self) -> List[Contract]:
        return list(self._contracts_dict.values())

    def get_province_contract(self, province_id: int, contract_type: ContractType) -> Optional[Contract]:
        province = self.get_province(province_id)
        if not province:
            return None

        # 使用正确的枚举成员进行比较
        if contract_type == ContractType.TAX_FARMING:
            contract_id = province.tax_contract_id
        elif contract_type == ContractType.PUBLIC_WORKS:
            contract_id = province.project_contract_id
        else:
            return None

        if contract_id is None:
            return None
        return self.get_contract(contract_id)

    def place_bid(self, contract_id: int, bidder_id: int, amount: int, **kwargs) -> bool:
        """
        为指定合同记录一个出价。
        返回是否成功（合同存在且处于 PENDING 状态）。
        kwargs 用于存储工程合同的额外字段（如 r, construction, warranty, annual_income 等）。
        """
        contract = self.get_contract(contract_id)
        if not contract or contract.status != ContractStatus.PENDING:
            return False
        bid = {"bidder_id": bidder_id, "amount": amount}
        bid.update(kwargs)  # 合并额外参数
        contract._bids.append(bid)
        return True

    def sync_italy_public_land(self):
        """将国家公地同步到意大利行省"""
        italy = self.get_province(0)
        if italy:
            italy._land_public = self._national_public_land

    def resolve_auction(self, contract_id: int) -> bool:
        contract = self.get_contract(contract_id)
        if not contract or contract.status != ContractStatus.PENDING:
            return False
        if not contract._bids:
            contract.status = ContractStatus.EXPIRED
            return False

        # 根据合同类型选择中标者
        if contract.contract_type == ContractType.TAX_FARMING:
            max_bid = max(contract._bids, key=lambda b: b["amount"])
            winner = max_bid
        else:  # PUBLIC_WORKS
            min_bid = min(contract._bids, key=lambda b: b["amount"])
            winner = min_bid

        contract.mark_winner(winner["bidder_id"], self.turn.turn_number, 0)

        if contract.contract_type == ContractType.TAX_FARMING:
            # 包税权处理（原有逻辑，略作简化，确保字段正确）
            contract._winning_bid = winner
            contract._tax_rate = winner["tax_rate"]
            province = self.get_province(contract.province_id)
            if province:
                land_price = self.get_economic_rule("land_price_per_unit", 10)
                private_income_rate = self.get_economic_rule("private_land_income_rate", 0.05)
                base_tax_rate = self.get_economic_rule("province_tax_rate", 0.1)
                land_value = province.land_public * land_price
                base_income = int(land_value * private_income_rate)
                actual_tax_rate = base_tax_rate * (1 + winner["tax_rate"])
                actual_tax = int(base_income * actual_tax_rate)
                annual_net = actual_tax - winner["amount"]
                contract._annual_profit = annual_net
                contract.expected_profit = annual_net * contract.duration_years
        else:
            # 公共工程处理
            contract._winning_bid = winner
            r = winner["r"]
            contract._original_budget = winner["original_budget"]
            contract._construction_years = winner["construction"]
            contract._warranty_years = winner["warranty"]
            contract._annual_income = winner["annual_income"]
            contract._annual_cost = winner["annual_cost"]
            contract.base_cost = winner["amount"]
            contract.remaining_years = winner["construction"]  # 施工剩余年限
            contract._warranty_remaining = winner["warranty"]

            province = self.get_province(contract.province_id)
            if province:
                land_price = self.get_economic_rule("land_price_per_unit", 10)
                infra_rate = self.get_economic_rule("infrastructure_cost_rate", 0.001)
                land_value = province.land_public * land_price
                infra_cost = int(land_value * infra_rate)
                actual_cost = int(infra_cost * (1 - r))
                contract.expected_profit = winner["amount"] - actual_cost  # 总收益

        # 绑定骑士和行省
        figure = self.get_member(winner["bidder_id"])
        if figure:
            figure.add_contract(contract_id)
            contract.awarded_faction = figure.faction_id

        province = self.get_province(contract.province_id)
        if province:
            if contract.contract_type == ContractType.TAX_FARMING:
                province.bind_tax_contract(contract_id)
            else:
                province.bind_project_contract(contract_id)

        return True