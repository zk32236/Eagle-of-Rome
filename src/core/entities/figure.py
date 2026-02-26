# src/core/entities/figure.py

from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
import random

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ClassTier(Enum):
    """社会阶层"""
    NOBILE = "nobile"
    EQUES = "eques"
    PLEBEIAN = "plebeian"


# 罗马历史名字库
ROMAN_NAMES = {
    "praenomina": [
        "Gaius", "Marcus", "Lucius", "Publius", "Quintus",
        "Titus", "Gnaeus", "Sextus", "Aulus", "Decimus",
        "Spurius", "Manius", "Servius", "Appius", "Numerius"
    ],
    "nomina": [
        "Julius", "Claudius", "Cornelius", "Aemilius", "Fabius",
        "Valerius", "Sempronius", "Tullius", "Calpurnius", "Domitius",
        "Antonius", "Licinius", "Junius", "Papirius", "Sulpicius",
        "Plautius", "Atilius", "Furius", "Manlius", "Veturius"
    ],
    "cognomina": [
        "Caesar", "Cicero", "Cato", "Brutus", "Pompeius",
        "Crassus", "Marius", "Sulla", "Gracchus", "Scipio",
        "Africanus", "Hispanus", "Macedonicus", "Asiaticus", "Naso",
        "Bibulus", "Buteo", "Rufus", "Longus", "Maximus"
    ],
    "plebeian_names": [
        "Quartus", "Sextilis", "Octavius", "Nonius", "Decius",
        "Vibius", "Statius", "Salvius", "Caius", "Tertius"
    ]
}


class RomanNameGenerator:
    """罗马名字生成器"""

    @staticmethod
    def generate_nobile_name() -> tuple:
        praenomen = random.choice(ROMAN_NAMES["praenomina"])
        nomen = random.choice(ROMAN_NAMES["nomina"])
        cognomen = random.choice(ROMAN_NAMES["cognomina"])
        full_name = f"{praenomen} · {nomen} · {cognomen}"
        return praenomen, nomen, cognomen, full_name

    @staticmethod
    def generate_eques_name() -> tuple:
        praenomen = random.choice(ROMAN_NAMES["praenomina"])
        nomen = random.choice(ROMAN_NAMES["nomina"])
        if random.random() > 0.5:
            cognomen = random.choice(ROMAN_NAMES["cognomina"])
            full_name = f"{praenomen} · {nomen} · {cognomen}"
        else:
            cognomen = None
            full_name = f"{praenomen} · {nomen}"
        return praenomen, nomen, cognomen, full_name

    @staticmethod
    def generate_plebeian_name() -> tuple:
        if random.random() > 0.3:
            name = random.choice(ROMAN_NAMES["plebeian_names"])
            return None, None, None, name
        else:
            praenomen = random.choice(ROMAN_NAMES["praenomina"])
            simple_nomen = random.choice([
                "Carpenter", "Smith", "Miller", "Fisher", "Hill",
                "Rivers", "Fields", "Stone", "Young", "Strong"
            ])
            return praenomen, simple_nomen, None, f"{praenomen} · {simple_nomen}"


@dataclass
class OfficeTerm:
    """公职任期记录"""
    office_type: str
    start_turn: int
    end_turn: Optional[int] = None
    is_active: bool = True


@dataclass
class Figure:
    """
    人物实体 - MVP 0.4.5 术语澄清版
    """

    # 类属性（配置项，可通过 load_config 覆盖）
    OFFICE_RANK = {
        "dictator": 6,
        "censor": 5,
        "consul": 4,
        "praetor": 3,
        "tribune": 2,
        "quaestor": 1,
    }

    OFFICE_INFLUENCE_BONUS = {
        "dictator": 60,
        "censor": 50,
        "consul": 40,
        "praetor": 30,
        "tribune": 20,
        "quaestor": 10,
        "proconsul": 0,
        "propraetor": 0,
    }

    EX_OFFICE_INFLUENCE_BONUS = {
        "ex-dictator": 30,
        "ex-censor": 25,
        "ex-consul": 20,
        "ex-praetor": 15,
        "ex-tribune": 10,
        "ex-quaestor": 5,
        "ex-proconsul": 20,
        "ex-propraetor": 15,
    }

    FAMILY_PRESTIGE = {
        "Julius": 3,
        "Cornelius": 3,
        "Claudius": 2,
        "Fabius": 2,
        "Aemilius": 1,
        "Servilius": 1,
        "Valerius": 1,
    }

    # 基础信息
    id: int
    name: str
    faction_id: Optional[str] = None
    praenomen: Optional[str] = None
    nomen: Optional[str] = None
    cognomen: Optional[str] = None

    # MVP核心属性
    wealth: int = 0
    popularity: int = 0
    land: int = 0          # 保留，但不再使用
    veterans: int = 0
    office: Optional[str] = None
    class_tier: ClassTier = ClassTier.PLEBEIAN
    age: int = 30

    # 资格属性
    zeal: int = 0
    charisma: int = 0
    martial: int = 0
    intelligence: int = 0

    # 机制属性
    family: Optional[str] = None
    family_prestige: int = 0
    experience: int = 0
    military_exp: int = 0
    economic_exp: int = 0
    political_exp: int = 0
    loyalty: int = 5
    loyalty_history: List[Dict] = field(default_factory=list)
    corruption: int = 0
    bribe_income: int = 0

    # 状态标记
    is_faction_leader: bool = False
    is_dead: bool = False
    is_present: bool = True
    is_available: bool = True
    abandoned_by: Optional[str] = None  # 记录抛弃该人物的派系ID

    # 历史记录
    office_history: List[OfficeTerm] = field(default_factory=list)
    festival_history: List[Dict] = field(default_factory=list)
    contract_history: List[Dict] = field(default_factory=list)
    land_trade_history: List[Dict] = field(default_factory=list)

    # ==================== MVP 0.5 新增字段 ====================
    _land_private: int = 0
    _contract_ids: List[int] = field(default_factory=list)
    _has_active_contract: bool = False
    _tribute_profit: int = 0
    _project_profit: int = 0
    _influence: int = field(default=0, init=False)

    # ==================== 核心方法 ====================

    def __post_init__(self):
        self.update_influence()

    def get_seat_share(self) -> int:
        return self._land_private + self.veterans

    def get_voting_power(self) -> int:
        return self.influence

    def update_influence(self) -> int:
        base = self._land_private * 10 + self.veterans * 10 + self.popularity
        family_bonus = self.family_prestige * 10
        office_bonus = self.get_office_influence_bonus()
        self._influence = base + family_bonus + office_bonus
        return self._influence

    @property
    def influence(self) -> int:
        return self._influence

    @influence.setter
    def influence(self, value: int):
        self._influence = value

    @property
    def rank(self) -> int:
        if not self.office:
            return 0
        return self.__class__.OFFICE_RANK.get(self.office, 0)

    def has_military_command(self) -> bool:
        return self.office in ("consul", "dictator", "propraetor")

    def has_veto_power(self) -> bool:
        return self.office == "tribune"

    def has_prosecution_power(self) -> bool:
        return self.office == "censor"

    def get_qualification_attribute(self, office_type: str) -> int:
        mapping = {
            "consul": self.charisma,
            "praetor": self.intelligence,
            "quaestor": self.martial,
            "censor": self.zeal,
            "aedile": self.intelligence,
            "dictator": self.martial,
        }
        return mapping.get(office_type, 0)

    def get_office_cooldown_years(self, office_type: str, config: Dict) -> int:
        cooldowns = config.get("political_rules", {}).get("office_cooldowns", {})
        return cooldowns.get(office_type, 2)

    # 在 can_hold_office 方法中，增加监察官的特殊条件
    def can_hold_office(self, office_type: str, current_turn: int, config: Dict) -> Tuple[bool, str]:
        # 获取目标官职等级
        target_rank = self.__class__.OFFICE_RANK.get(office_type, 0)
        if target_rank == 0:
            return False, f"Unknown office type: {office_type}"

        # 辅助函数：获取任何官职（含ex-）的等级
        def get_rank(off: Optional[str]) -> int:
            if not off:
                return 0
            if off.startswith("ex-"):
                base = off[3:]
            else:
                base = off
            return self.__class__.OFFICE_RANK.get(base, 0)

        # 检查当前官职：如果当前官职是现任官职（非ex-）且等级高于目标，则不能竞选
        if self.office and not self.office.startswith("ex-") and get_rank(self.office) > target_rank:
            return False, f"Cannot run for lower office while holding higher office: {self.office}"

        # 检查历史官职：如果曾担任过高阶官职，则不能竞选低阶（监察官除外）
        if office_type != "censor":
            for term in self.office_history:
                if get_rank(term.office_type) > target_rank:
                    return False, f"Has held higher office: {term.office_type}"

        # 年龄检查
        min_ages = config.get("political_rules", {}).get("min_ages", {})
        if self.age < min_ages.get(office_type, 30):
            return False, f"Age {self.age} < {min_ages.get(office_type, 30)}"

        # 现任相同官职检查
        if self.office == office_type:
            return False, "Already holding this office"

        # 冷却期检查
        cooldowns = config.get("political_rules", {}).get("office_cooldowns", {})
        cooldown = cooldowns.get(office_type, 2)
        for term in self.office_history:
            if term.office_type == office_type:
                years_ago = current_turn - term.start_turn
                if years_ago < cooldown:
                    return False, f"Cooldown: {years_ago}/{cooldown} years"

        # 前置职务检查
        if office_type == "consul":
            has_praetor = any(h.office_type == "praetor" for h in self.office_history)
            if not has_praetor:
                return False, "Requires prior Praetor service"
        elif office_type == "praetor":
            has_quaestor = any(h.office_type == "quaestor" for h in self.office_history)
            if not has_quaestor:
                return False, "Requires prior Quaestor service"
        elif office_type == "censor":
            has_consul = any(h.office_type == "consul" for h in self.office_history)
            if not has_consul:
                return False, "Requires prior Consul service"
        elif office_type == "tribune":
            # 保民官仅限骑士和平民
            if self.class_tier not in (ClassTier.EQUES, ClassTier.PLEBEIAN):
                return False, "Only equites and plebeians can be tribune"

        return True, "Eligible"

    def get_formal_name(self) -> str:
        parts = []
        if self.praenomen:
            parts.append(self.praenomen)
        if self.nomen:
            parts.append(self.nomen)
        if self.cognomen:
            parts.append(self.cognomen)
        if parts:
            return " · ".join(parts)
        return self.name

    def add_wealth(self, amount: int):
        self.wealth += amount

    def add_popularity(self, amount: int):
        self.popularity = max(0, self.popularity + amount)

    def apply_annual_decay(self, decay_rates: Dict[str, float]):
        if "veterans" in decay_rates and self.veterans > 0:
            self.veterans = int(self.veterans * (1 - decay_rates["veterans"]))
        if "popularity" in decay_rates and self.popularity > 0:
            self.popularity = int(self.popularity * (1 - decay_rates["popularity"]))

    def can_be_candidate(self, current_turn: int, cooldown: int = 10) -> bool:
        if self.is_faction_leader:
            return False
        if self.age < 20:
            return False
        for term in self.office_history:
            if term.office_type == "consul":
                years_ago = current_turn - term.start_turn
                if 0 < years_ago < cooldown:
                    return False
        return True

    def years_since_last_consulship(self, current_turn: int) -> Optional[int]:
        consul_terms = [h for h in self.office_history if h.office_type == "consul"]
        if not consul_terms:
            return None
        return current_turn - max(t.start_turn for t in consul_terms)

    def can_sell_land(self, amount: int) -> bool:
        return self._land_private >= amount

    def can_buy_land(self, amount: int, price_per_unit: int) -> bool:
        total_cost = amount * price_per_unit
        return self.wealth >= total_cost

    def sell_land(self, amount: int, price_per_unit: int) -> int:
        if not self.can_sell_land(amount):
            return 0
        self._land_private -= amount
        earnings = amount * price_per_unit
        self.wealth += earnings
        return earnings

    def buy_land(self, amount: int, price_per_unit: int) -> bool:
        if not self.can_buy_land(amount, price_per_unit):
            return False
        total_cost = amount * price_per_unit
        self.wealth -= total_cost
        self._land_private += amount
        return True

    # ==================== 工厂方法 ====================
    @classmethod
    def create_nobile(cls, id: int, faction_id: str, age: int = 35) -> "Figure":
        praenomen, nomen, cognomen, full_name = RomanNameGenerator.generate_nobile_name()
        initial_prestige = cls.FAMILY_PRESTIGE.get(nomen, 1)
        figure = cls(
            id=id,
            name=full_name,
            faction_id=faction_id,
            praenomen=praenomen,
            nomen=nomen,
            cognomen=cognomen,
            class_tier=ClassTier.NOBILE,
            age=age,
            wealth=random.randint(10, 20),
            popularity=random.randint(2, 5),
            veterans=0,
            family=nomen,
            family_prestige=initial_prestige,
            loyalty=7,
            charisma=random.randint(5, 9),
            intelligence=random.randint(3, 7),
            martial=random.randint(3, 7),
            zeal=random.randint(2, 6),
        )
        return figure

    @classmethod
    def create_eques(cls, id: int, faction_id: str, age: int = 30) -> "Figure":
        praenomen, nomen, cognomen, full_name = RomanNameGenerator.generate_eques_name()
        figure = cls(
            id=id,
            name=full_name,
            faction_id=faction_id,
            praenomen=praenomen,
            nomen=nomen,
            cognomen=cognomen,
            class_tier=ClassTier.EQUES,
            age=age,
            wealth=random.randint(15, 30),
            popularity=random.randint(1, 3),
            veterans=0,
            family=None,
            family_prestige=0,
            loyalty=5,
            economic_exp=random.randint(1, 5),
            intelligence=random.randint(5, 9),
            charisma=random.randint(3, 6),
            martial=random.randint(2, 5),
            zeal=random.randint(1, 4),
        )
        return figure

    @classmethod
    def create_plebeian(cls, id: int, faction_id: str, age: int = 25) -> "Figure":
        praenomen, nomen, cognomen, full_name = RomanNameGenerator.generate_plebeian_name()
        figure = cls(
            id=id,
            name=full_name,
            faction_id=faction_id,
            praenomen=praenomen,
            nomen=nomen,
            cognomen=cognomen,
            class_tier=ClassTier.PLEBEIAN,
            age=age,
            wealth=random.randint(3, 8),
            popularity=random.randint(0, 2),
            veterans=0,
            family=None,
            family_prestige=0,
            loyalty=3,
            zeal=random.randint(5, 9),
            charisma=random.randint(2, 6),
            intelligence=random.randint(1, 4),
            martial=random.randint(1, 4),
        )
        return figure

    # ==================== 其他方法 ====================

    def __repr__(self) -> str:
        if self.is_dead:
            status = "☠️"
        elif self.is_faction_leader:
            status = "👑"
        else:
            status = "🟢"

        tier_emoji = {
            ClassTier.NOBILE: "🏛️",
            ClassTier.EQUES: "💰",
            ClassTier.PLEBEIAN: "👤"
        }.get(self.class_tier, "❓")

        office_emoji = ""
        if self.office:
            office_emoji = {
                "consul": "🏛️",
                "praetor": "⚖️",
                "quaestor": "💰",
                "censor": "📜",
                "aedile": "🏗️"
            }.get(self.office, "📋")
            office_emoji = f"[{office_emoji}{self.office[:3]}]"

        display_name = self.get_formal_name()
        seat_share = self.get_seat_share()

        return (f"{status}{tier_emoji} ID:{self.id} {display_name}{office_emoji} "
                f"影响力{self.influence} 财富{self.wealth} 人气{self.popularity} 地产{self._land_private} 老兵{self.veterans} 席位{seat_share}")

    def add_office_history(self, office_type: str, start_turn: int, end_turn: Optional[int] = None):
        term = OfficeTerm(
            office_type=office_type,
            start_turn=start_turn,
            end_turn=end_turn or start_turn + 1,
            is_active=False
        )
        self.office_history.append(term)
        self.office = None
        if office_type == "consul":
            self.age = max(self.age, 42)
        elif office_type == "praetor":
            self.age = max(self.age, 37)
        elif office_type == "quaestor":
            self.age = max(self.age, 32)

    @classmethod
    def create_nobile_with_history(cls, id: int, faction_id: str,
                                   previous_office: Optional[str] = None,
                                   age: int = 40) -> "Figure":
        figure = cls.create_nobile(id, faction_id, age)
        if previous_office:
            start_turn = random.randint(-10, -3)
            figure.add_office_history(previous_office, start_turn)
            if previous_office == "consul":
                figure.charisma = max(figure.charisma, 7)
            elif previous_office == "praetor":
                figure.intelligence = max(figure.intelligence, 7)
        return figure

    @classmethod
    def create_eques_with_history(cls, id: int, faction_id: str,
                                  previous_office: Optional[str] = None,
                                  age: int = 35) -> "Figure":
        figure = cls.create_eques(id, faction_id, age)
        if previous_office:
            start_turn = random.randint(-10, -3)
            figure.add_office_history(previous_office, start_turn)
            if previous_office == "praetor":
                figure.intelligence = max(figure.intelligence, 8)
            elif previous_office == "quaestor":
                figure.martial = max(figure.martial, 7)
        return figure

    @classmethod
    def create_plebeian_with_history(cls, id: int, faction_id: str,
                                     previous_office: Optional[str] = None,
                                     age: int = 30) -> "Figure":
        figure = cls.create_plebeian(id, faction_id, age)
        if previous_office:
            start_turn = random.randint(-10, -3)
            figure.add_office_history(previous_office, start_turn)
            if previous_office == "quaestor":
                figure.martial = max(figure.martial, 6)
        return figure

    # ==================== MVP 0.5 新增方法 ====================
    def add_contract(self, contract_id: int) -> None:
        if contract_id in self._contract_ids:
            raise ValueError(f"Contract ID {contract_id} already exists")
        self._contract_ids.append(contract_id)
        self._has_active_contract = True

    def remove_contract(self, contract_id: int) -> None:
        if contract_id in self._contract_ids:
            self._contract_ids.remove(contract_id)
        self._has_active_contract = bool(self._contract_ids)

    def settle_contract_profit(self, profit: int) -> None:
        self.wealth += profit

    def get_office_influence_bonus(self) -> int:
        if not self.office:
            return 0
        if self.office.startswith("ex-"):
            return self.__class__.EX_OFFICE_INFLUENCE_BONUS.get(self.office, 0)
        else:
            return self.__class__.OFFICE_INFLUENCE_BONUS.get(self.office, 0)

    @classmethod
    def load_config(cls, config):
        """从配置加载静态数据（覆盖默认值）"""
        if config:
            political_rules = config.get("political_rules", {})
            # 使用 get 并传入当前值作为默认，避免覆盖时丢失原值
            cls.OFFICE_RANK = political_rules.get("office_rank", cls.OFFICE_RANK)
            cls.OFFICE_INFLUENCE_BONUS = political_rules.get("office_influence_bonus", cls.OFFICE_INFLUENCE_BONUS)
            cls.EX_OFFICE_INFLUENCE_BONUS = political_rules.get("ex_office_influence_bonus", cls.EX_OFFICE_INFLUENCE_BONUS)
            cls.FAMILY_PRESTIGE = political_rules.get("family_prestige", cls.FAMILY_PRESTIGE)

    # ==================== MVP 0.5 新增属性访问器 ====================
    @property
    def land_private(self) -> int:
        return self._land_private

    @property
    def contract_ids(self) -> List[int]:
        return self._contract_ids.copy()

    @property
    def has_active_contract(self) -> bool:
        return self._has_active_contract

    @property
    def tribute_profit(self) -> int:
        return self._tribute_profit

    @property
    def project_profit(self) -> int:
        return self._project_profit
