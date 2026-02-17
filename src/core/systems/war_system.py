# src/core/systems/war_system.py

import json
import random
from pathlib import Path
from typing import List, Dict, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.game_state import GameState

from core.entities.war import War, WarStatus, WarType
from core.localization import TerminologyService


class WarSystem:
    """
    战争管理系统

    职责：
    1. 战争牌堆管理（加载、洗牌、抽取）
    2. 战争激活与推进
    3. 战争结算（胜利/失败判定）
    4. 战争与将领/军团关联
    """

    def __init__(self, state: 'GameState'):  # 使用字符串注解
        self.state: 'GameState' = state
        self._war_deck: List[War] = []
        self._war_discard: List[War] = []
        self._active_wars: List[War] = []

    # ========== 数据加载 ==========

    def load_wars_from_json(self, filename: str = "wars.json") -> List[War]:
        """从JSON加载战争卡数据"""
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / filename

        wars = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for war_data in data.get('wars', []):
                war = self._parse_war_data(war_data)
                wars.append(war)

        except FileNotFoundError:
            print(f"   ⚠️  War data file not found: {file_path}")
            # 创建默认测试战争
            wars = self._create_default_wars()
        except json.JSONDecodeError as e:
            print(f"   ⚠️  JSON parse error: {e}")
            wars = self._create_default_wars()

        self._war_deck = wars
        print(f"   📚 Loaded {len(wars)} wars into deck")
        return wars

    def _parse_war_data(self, data: Dict[str, Any]) -> War:
        """解析战争JSON数据"""
        # 解析战争类型
        war_type_str = data.get('type', 'foreign').upper()
        try:
            war_type = WarType[war_type_str]
        except KeyError:
            war_type = WarType.FOREIGN

        # 创建战争实体
        war = War(
            id=data.get('id', f"war_{random.randint(1000, 9999)}"),
            name=data.get('name', 'Unknown War'),
            description=data.get('description', ''),
            war_type=war_type,
            strength=data.get('strength', 5),
            naval_support_required=data.get('naval_required', False),
            naval_strength=data.get('naval_strength', 0),
            land_battle=data.get('land_battle', True),
            disaster_numbers=data.get('disaster_numbers', [2, 3, 4]),
            standoff_numbers=data.get('standoff_numbers', [5, 6, 7, 8, 9]),
            rewards=data.get('rewards', {}),
            penalties=data.get('penalties', {}),
            is_imminent=data.get('imminent', False),
            matched_war_id=data.get('matched_war'),
        )

        return war

    def _create_default_wars(self) -> List[War]:
        """创建默认测试战争（当JSON加载失败时）"""
        terms = TerminologyService.get()

        return [
            War(
                id="test_war_1",
                name=f"Gallic Raiders",
                description="Barbarian incursion from the north",
                war_type=WarType.BARBARIAN,
                strength=4,
                naval_support_required=False,
                rewards={'treasury': 25, 'influence': 1},
                penalties={'unrest_per_turn': 1},
            ),
            War(
                id="test_war_2",
                name=f"Pirate Fleet",
                description="Mediterranean pirates threaten trade",
                war_type=WarType.FOREIGN,
                strength=6,
                naval_support_required=True,
                naval_strength=3,
                rewards={'treasury': 40, 'influence': 2},
                penalties={'treasury_cost': 5},
            ),
            War(
                id="test_war_3",
                name=f"Provincial Revolt",
                description="Unrest in the provinces",
                war_type=WarType.PROVINCIAL,
                strength=8,
                rewards={'treasury': 60, 'influence': 3, 'unrest_reduction': 3},
                penalties={'unrest_per_turn': 2},
            ),
        ]

    # ========== 牌堆管理 ==========

    def shuffle_deck(self):
        """洗牌"""
        random.shuffle(self._war_deck)
        print("   🔀 War deck shuffled")

    def draw_war(self) -> Optional[War]:
        """抽取战争卡"""
        if not self._war_deck:
            # 牌堆空时，弃牌堆重洗
            if self._war_discard:
                print("   ♻️  Reshuffling discard pile...")
                self._war_deck = self._war_discard
                self._war_discard = []
                self.shuffle_deck()
            else:
                return None

        war = self._war_deck.pop()
        return war

    def activate_war(self, war: War, turn: int) -> bool:
        """激活战争"""
        if war.status != WarStatus.INACTIVE:
            return False

        war.status = WarStatus.ACTIVE
        war.activation_turn = turn
        self._active_wars.append(war)

        terms = TerminologyService.get()
        print(f"   ⚔️  {terms.phase_combat} declared: {war.name}!")
        print(f"      Strength: {war.strength}", end="")
        if war.naval_support_required:
            print(f" | Naval: {war.naval_strength} ⚓", end="")
        print()

        return True

    def check_imminent_wars(self) -> List[War]:
        """检查即将爆发的战争（预警）"""
        return [w for w in self._war_deck if w.is_imminent]

    # ========== 战争查询 ==========

    def get_active_wars(self) -> List[War]:
        """获取所有活跃战争"""
        return [w for w in self._active_wars if w.status == WarStatus.ACTIVE]

    def get_war_by_id(self, war_id: str) -> Optional[War]:
        """通过ID查找战争"""
        all_wars = self._war_deck + self._war_discard + self._active_wars
        for war in all_wars:
            if war.id == war_id:
                return war
        return None

    def get_war_by_commander(self, commander_id: int) -> Optional[War]:
        """查找将领指派的战争"""
        for war in self._active_wars:
            if war.commander_id == commander_id:
                return war
        return None

    # ========== 战争操作 ==========

    def assign_commander(self, war_id: str, commander_id: int, legions: int = 0, fleets: int = 0) -> bool:
        """指派将领和军队到战争"""
        war = self.get_war_by_id(war_id)
        if not war or war.status != WarStatus.ACTIVE:
            return False

        # 检查是否已有将领（需要召回）
        if war.commander_id is not None:
            print(f"   ⚠️  Replacing commander on {war.name}")

        war.commander_id = commander_id
        war.legions_assigned = legions
        war.fleets_assigned = fleets

        terms = TerminologyService.get()
        print(f"   🎖️  {terms.commander} assigned to {war.name}")
        print(f"      Forces: {legions} {terms.legion}, {fleets} {terms.fleet}")

        return True

    def recall_commander(self, war_id: str) -> bool:
        """召回将领"""
        war = self.get_war_by_id(war_id)
        if not war:
            return False

        war.commander_id = None
        war.legions_assigned = 0
        war.fleets_assigned = 0
        return True

    def apply_turn_penalties(self) -> List[str]:
        """应用所有活跃战争的拖延惩罚"""
        events = []
        for war in self._active_wars:
            if war.status == WarStatus.ACTIVE:
                war_events = war.apply_penalties(self.state)
                events.extend(war_events)
                war.duration += 1

        return events

    # ========== 战争结算 ==========

    def resolve_war(self, war_id: str, victory: bool) -> Dict[str, Any]:
        """结算战争（胜利或失败）"""
        war = self.get_war_by_id(war_id)
        if not war:
            return {}

        terms = TerminologyService.get()

        # 获取军事系统并召回所有军团
        ms = self.state.get_military_system()
        if ms:
            # 强制召回所有军团（双重保险）
            ms.recall_from_war(war.id)

        # 清理战争数据
        war.commander_id = None
        war.legions_assigned = 0
        war.fleets_assigned = 0

        result = {
            'war_name': war.name,
            'victory': victory,
            'duration': war.duration,
            'rewards': {},
            'penalties_applied': [],
        }

        if victory:
            war.status = WarStatus.RESOLVED
            result['rewards'] = war.calculate_rewards()
            print(f"   ✅ {war.name} resolved! Victory!")
            print(f"   🎁 Rewards: {result['rewards']}")
        else:
            war.status = WarStatus.DEFEATED
            print(f"   ❌ {war.name} lost! Defeat!")

        # 从活跃列表移除，加入弃牌堆
        if war in self._active_wars:
            self._active_wars.remove(war)
        self._war_discard.append(war)

        # 清理将领状态
        if war.commander_id:
            commander = self.state.get_member(war.commander_id)
            if commander:
                # 凯旋或阵亡处理（第4阶段完善）
                pass

        return result

    def check_war_victory_condition(self, war: War) -> bool:
        """检查战争胜利条件（简化版）"""
        # MVP 0.3：通过战斗阶段CRT判定，这里仅做状态检查
        return war.status == WarStatus.RESOLVED

    # ========== 与GameState集成 ==========

    def sync_to_state(self):
        """同步战争状态到GameState（用于保存/加载）"""
        # 将战争数据存入state的临时存储（第5阶段完善持久化）
        self.state._war_system_data = {
            'deck': [w.id for w in self._war_deck],
            'discard': [w.id for w in self._war_discard],
            'active': [w.id for w in self._active_wars],
        }

    def load_from_state(self):
        """从GameState恢复战争状态"""
        # 第5阶段完善
        pass

    def get_active_wars(self) -> List[War]:
        """获取所有活跃战争（过滤掉已解决的）"""
        return [w for w in self._active_wars
                if w.status == WarStatus.ACTIVE]

    def get_wars_needing_reassignment(self) -> List[War]:
        """获取需要重新指派的战争（指挥官伤亡或0军团）"""
        ms = self.state.get_military_system()
        result = []

        for war in self.get_active_wars():
            # 检查指挥官状态
            if war.commander_status != "active":
                result.append(war)
                continue

            # 检查军团数量
            if ms:
                legions = ms.get_legions_for_battle(war.id)
                if not legions:
                    result.append(war)

        return result