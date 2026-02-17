# src/core/game_state.py

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

from core.entities import Figure, Faction, GameTurn, Curia, Contract
from core.localization import TerminologyService, GamePhase
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.systems.war_system import WarSystem

class GameState:
    """游戏状态单例容器"""

    _instance = None
    MAX_MEMBER_ID = 300

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reset()
        return cls._instance

    def reset(self):
        self.members: Dict[int, Figure] = {}  # 原senators
        self.factions: Dict[str, Faction] = {}
        self.treasury: int = 0  # 原state_treasury
        self.turn: GameTurn = GameTurn()
        self.event_log: List[str] = []

        self._used_ids: Set[int] = set()
        self._initialize_mortality_pool()  # 原death_bag

        # MVP 0.3: 战争系统（第2阶段）
        self.war_system: Optional['WarSystem'] = None
        # MVP 0.3: 军事系统（第3阶段新增）
        self.military_system: Optional['MilitarySystem'] = None

        # MVP 0.4: 广场等待区
        self.curia: Curia = Curia()

        # MVP 0.4: 合同系统
        self.contracts: List[Contract] = []


        self.config: Dict[str, Any] = self._load_config()
        self.executed_phases: Set[str] = set()

        self._military_prepared = False  # 军事准备标记



    def _initialize_mortality_pool(self):
        """初始化天命池（原死亡袋）"""
        self.mortality_pool: List[int] = list(range(1, self.MAX_MEMBER_ID + 1))
        random.shuffle(self.mortality_pool)

    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        default = {
            "political_rules": {
                "leader_cooldown_years": 10,
                "leaders_per_election": 2,
            },
            "mortality_rules": {
                "base_draw_count": 1,
                "draw_per_members": 5,
                "max_draws": 3
            }
        }

        try:
            base_path = Path(__file__).parent.parent.parent
            config_path = base_path / "data" / "config" / "game_config.json"

            if not config_path.exists():
                return default

            with open(config_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            # 加载术语预设
            term_preset = loaded.get("terminology_preset", "original")
            TerminologyService.set_preset(term_preset)

            merged = default.copy()
            for key, value in loaded.items():
                if isinstance(value, dict) and key in merged:
                    merged[key].update(value)
                else:
                    merged[key] = value

            return merged

        except Exception as e:
            print(f"   ⚠️  Config error: {e}")
            return default

    # ========== 配置获取 ==========

    def get_cooldown_years(self) -> int:
        return self.config.get("political_rules", {}).get("leader_cooldown_years", 10)

    def get_leaders_per_election(self) -> int:
        return self.config.get("political_rules", {}).get("leaders_per_election", 2)

    # ========== ID 管理 ==========

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

    # ========== 实体管理 ==========

    def add_member(self, member: Figure):
        self._used_ids.add(member.id)
        self.members[member.id] = member

    def get_member(self, member_id: int) -> Optional[Figure]:
        return self.members.get(member_id)

    def get_living_member(self, member_id: int) -> Optional[Figure]:
        member = self.members.get(member_id)
        return member if (member and not member.is_dead) else None

    def get_living_members(self) -> List[Figure]:
        return [m for m in self.members.values() if not m.is_dead]

    def add_faction(self, faction: Faction):
        self.factions[faction.id] = faction

    def get_faction(self, faction_id: str) -> Optional[Faction]:
        return self.factions.get(faction_id)

    # ========== 查询方法 ==========

    def get_presiding_officer(self) -> Optional[Figure]:
        """获取主持人（原HRAO）"""
        candidates = [
            m for m in self.members.values()
            if not m.is_dead and m.is_present
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.power)

    def get_living_members(self) -> List[Figure]:
        return [m for m in self.members.values() if not m.is_dead]

    def get_active_factions(self) -> List[Faction]:
        active = []
        for faction in self.factions.values():
            living = [m for m in faction.get_members(self) if not m.is_dead]
            if living:
                active.append(faction)
        return active

    # ========== 天命机制 ==========

    def draw_mortality_number(self) -> int:
        """抽取天命号码"""
        if not self.mortality_pool:
            self._initialize_mortality_pool()
            dead_ids = [mid for mid, m in self.members.items() if m.is_dead]
            self.mortality_pool = [x for x in self.mortality_pool if x not in dead_ids]

        return self.mortality_pool.pop()

    # ========== 回合管理 ==========

    def advance_year(self):
        """推进到下一年"""
        self.turn.turn_number += 1
        self.turn.year += 1

        cleared = len(self.executed_phases)
        self.executed_phases.clear()

        print(f"\n📅 Year {abs(self.turn.year)} BC (Turn {self.turn.turn_number})")
        if cleared > 0:
            print(f"   [Cleared {cleared} phase locks]")

        # 修复：使用 years_since_last_consulship 替代 years_since_last_leadership
        cooldown = self.get_cooldown_years()
        ineligible = [
            m for m in self.get_living_members()
            if not m.can_be_candidate(self.turn.turn_number, cooldown)
        ]
        if ineligible:
            names = ", ".join([
                f"{m.name}({m.years_since_last_consulship(self.turn.turn_number) or 'new'})"
                for m in ineligible
            ])
            print(f"   ⛔ Ineligible ({cooldown}y rule): {names}")

    # ========== 阶段执行跟踪 ==========

    def is_phase_executed(self, phase_name: str) -> bool:
        return phase_name in self.executed_phases

    def mark_phase_executed(self, phase_name: str):
        self.executed_phases.add(phase_name)

    # ========== 辅助方法 ==========

    def log_event(self, message: str):
        entry = f"Turn {self.turn.turn_number}: {message}"
        self.event_log.append(entry)
        print(message)

    def get_status_summary(self) -> str:
        """生成状态摘要"""
        terms = TerminologyService.get()

        lines = [
            "=" * 50,
            f"Year: {abs(self.turn.year)} BC (Turn {self.turn.turn_number})",
            f"Phase: {self.turn.current_phase}",
            f"Treasury: {self.treasury} {terms.currency}",
            "-" * 50,
            "FACTIONS & MEMBERS:"
        ]

        for faction in self.factions.values():
            living = [m for m in faction.get_members(self) if not m.is_dead]

            lines.append(f"\n{faction.name} ({faction.id}) - {terms.treasury}: {faction.treasury}{terms.currency}")
            if faction.is_player:
                lines.append("  [PLAYER CONTROLLED]")

            for member in living:
                # 修复：is_leader -> is_faction_leader
                # 同时检查是否担任执政官（consul）
                is_consul = member.office == "consul"
                leader_mark = f" {terms.leader_title[0]}" if is_consul else ""
                # 或者如果想显示派系领袖标记：
                # leader_mark = f" 👑" if member.is_faction_leader else ""
                lines.append(f"  {member}{leader_mark}")

        lines.append("=" * 50)
        return "\n".join(lines)

    # ========== 战争系统访问 ==========

    def get_war_system(self) -> Optional['WarSystem']:
        """获取战争系统（延迟初始化，确保只加载一次）"""
        if self.war_system is None:
            try:
                from core.systems.war_system import WarSystem
                self.war_system = WarSystem(self)
                self.war_system.load_wars_from_json()
                # 标记已初始化，避免重复加载
                self._war_system_initialized = True
            except Exception as e:
                print(f"   ⚠️  War system init error: {e}")
                import traceback
                traceback.print_exc()
                return None
        return self.war_system

    def get_active_wars(self) -> List[Any]:
        """获取活跃战争列表"""
        ws = self.get_war_system()
        if ws:
            return ws.get_active_wars()
        # 回退到临时存储
        return getattr(self, '_temp_wars', [])

    def get_military_system(self) -> Optional['MilitarySystem']:
        """获取军事系统（延迟初始化）"""
        if self.military_system is None:
            try:
                from core.systems.military_system import MilitarySystem
                self.military_system = MilitarySystem(self)
            except Exception as e:
                print(f"   ⚠️  Military system init error: {e}")
                return None
        return self.military_system

    def is_military_prepared(self) -> bool:
        """检查是否已完成军事准备（所有战争都有指挥官和军团）"""
        ws = self.get_war_system()
        if not ws:
            return True

        active = ws.get_active_wars()
        if not active:
            return True  # 无战争不需要准备

        ms = self.get_military_system()

        for war in active:
            # 检查指挥官
            if war.commander_id is None:
                return False

            # 检查军团
            if ms:
                legions = ms.get_legions_for_battle(war.id)
                if not legions:
                    return False

        return True

    def get_military_preparation_status(self) -> tuple:
        """获取军事准备详细状态"""
        ws = self.get_war_system()
        ms = self.get_military_system()

        if not ws:
            return True, [], []

        active = ws.get_active_wars()
        if not active:
            return True, [], []

        unassigned = [w for w in active if w.commander_id is None]
        no_legions = []

        for war in active:
            if war.commander_id and ms:
                if not ms.get_legions_for_battle(war.id):
                    no_legions.append(war)

        is_ready = not unassigned and not no_legions
        return is_ready, unassigned, no_legions

    # MVP 0.4.5 新增加：

    def get_office_cooldown(self, office_type: str) -> int:
        """获取指定公职的冷却期"""
        return self.config.get("political_rules", {}).get("office_cooldowns", {}).get(office_type, 2)

    def get_offices_per_election(self, office_type: str) -> int:
        """获取每次选举该公职的名额"""
        return self.config.get("political_rules", {}).get("offices_per_election", {}).get(office_type, 1)

    # 兼容旧代码（逐步废弃）
    def get_cooldown_years(self) -> int:
        """⚠️ 废弃：使用get_office_cooldown('consul')"""
        return self.get_office_cooldown("consul")

    def get_leaders_per_election(self) -> int:
        """获取执政官选举人数"""
        return self.config.get("political_rules", {}).get("offices_per_election", {}).get("consul", 2)