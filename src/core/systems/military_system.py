# src/core/systems/military_system.py

from typing import List, Optional, Dict, Tuple
from src.core.entities.legion import Legion, LegionStatus
from src.core.game_state import GameState
from src.core.localization import TerminologyService


class MilitarySystem:
    """
    军事管理系统

    职责：
    1. 管理10个军团池
    2. 征召/解散逻辑
    3. 维护费计算
    4. 军团指派到战争
    """

    MAX_LEGIONS = 10

    def __init__(self, state: GameState):
        self.state = state
        self._legions: List[Legion] = []
        self._initialize_legions()

    def _initialize_legions(self):
        """初始化10个军团"""
        for i in range(1, self.MAX_LEGIONS + 1):
            legion = Legion(number=i)
            self._legions.append(legion)
        print(f"   ⚔️  Military system: {self.MAX_LEGIONS} legions ready")

    # ========== 查询方法 ==========

    def get_all_legions(self) -> List[Legion]:
        """获取所有军团"""
        return self._legions

    def get_available_legions(self) -> List[Legion]:
        """获取可征召的军团（包括已解散的）"""
        return [l for l in self._legions
                if l.status in (LegionStatus.UNRAISED, LegionStatus.DISBANDED)]

    def get_active_legions(self) -> List[Legion]:
        """获取已征召的活跃军团"""
        return [l for l in self._legions
                if l.status in (LegionStatus.ACTIVE, LegionStatus.VETERAN)]

    def get_assigned_legions(self) -> List[Legion]:
        """获取已指派到战争的军团"""
        return [l for l in self._legions if l.war_id is not None]

    def get_unassigned_legions(self) -> List[Legion]:
        """获取未指派的活跃军团"""
        return [l for l in self.get_active_legions() if l.war_id is None]

    def get_legion_by_number(self, number: int) -> Optional[Legion]:
        """通过编号获取军团"""
        for legion in self._legions:
            if legion.number == number:
                return legion
        return None

    # ========== 军团操作 ==========

    def recruit_legion(self, legion_number: int) -> Tuple[bool, str]:
        """征召指定军团（支持重新招募已解散的）"""
        terms = TerminologyService.get()
        legion = self.get_legion_by_number(legion_number)

        if not legion:
            return False, f"Invalid {terms.legion} number"

        # 检查是否可以征召（未征召或已解散）
        if legion.status not in (LegionStatus.UNRAISED, LegionStatus.DISBANDED):
            return False, f"{legion.name} already active"

        # 检查国库
        recruit_cost = 10
        if self.state.treasury < recruit_cost:
            return False, f"Insufficient treasury ({recruit_cost} needed)"

        # 执行征召（重置状态）
        legion.status = LegionStatus.ACTIVE
        legion.is_veteran = False  # 重新招募不是老兵
        self.state.treasury -= recruit_cost

        return True, f"{legion.name} recruited for {recruit_cost} {terms.currency}"

    def recruit_multiple(self, count: int) -> List[Tuple[int, bool, str]]:
        """征召多个军团"""
        results = []
        available = self.get_available_legions()

        for i, legion in enumerate(available[:count], 1):
            success, msg = self.recruit_legion(legion.number)
            results.append((legion.number, success, msg))

        return results

    def disband_legion(self, legion_number: int) -> Tuple[bool, str]:
        """解散军团"""
        terms = TerminologyService.get()
        legion = self.get_legion_by_number(legion_number)

        if not legion:
            return False, f"Invalid {terms.legion} number"

        if legion.war_id:
            return False, f"{legion.name} is assigned to war"

        if legion.disband():
            return True, f"{legion.name} disbanded"

        return False, "Cannot disband this legion"

    def assign_to_war(self, legion_numbers: List[int], war_id: str, commander_id: int) -> Tuple[int, str]:
        """指派多个军团到战争（修复：严格检查征召状态）"""
        terms = TerminologyService.get()
        assigned = 0
        errors = []

        for num in legion_numbers:
            legion = self.get_legion_by_number(num)
            if not legion:
                errors.append(f"Invalid {terms.legion} {num}")
                continue

            # 严格检查：必须已征召且活跃
            if legion.status == LegionStatus.UNRAISED:
                errors.append(f"{legion.name} not recruited (unraised)")
                continue

            if legion.status == LegionStatus.DISBANDED:
                errors.append(f"{legion.name} disbanded")
                continue

            if legion.war_id:
                errors.append(f"{legion.name} already assigned to war")
                continue

            if legion.assign_to_war(war_id, commander_id):
                assigned += 1

        msg = f"Assigned {assigned} {terms.legion}(s)"
        if errors:
            msg += f" | Errors: {', '.join(errors[:3])}"
            if len(errors) > 3:
                msg += f" (+{len(errors) - 3} more)"

        return assigned, msg

    def recall_from_war(self, war_id: str) -> int:
        """从战争召回所有军团"""
        recalled = 0
        for legion in self._legions:
            if legion.war_id == war_id:
                legion.recall()
                recalled += 1
        return recalled

    # ========== 维护费 ==========

    def calculate_maintenance(self) -> Tuple[int, Dict[str, int]]:
        """计算总维护费"""
        terms = TerminologyService.get()
        total = 0
        breakdown = {}

        for legion in self.get_active_legions():
            cost = legion.get_maintenance_cost()
            total += cost
            breakdown[legion.name] = cost

        return total, breakdown

    def apply_maintenance(self) -> Tuple[bool, str]:
        """扣除维护费"""
        terms = TerminologyService.get()
        total, breakdown = self.calculate_maintenance()

        if total == 0:
            return True, f"No {terms.legion} maintenance needed"

        if self.state.treasury < total:
            # 国库不足，强制解散部分军团
            shortfall = total - self.state.treasury
            disbanded = self._auto_disband_for_funds(shortfall)
            return False, f"Treasury shortfall! {disbanded} {terms.legion}(s) disbanded"

        self.state.treasury -= total
        return True, f"Paid {total} {terms.currency} for {terms.legion} maintenance"

    def _auto_disband_for_funds(self, shortfall: int) -> int:
        """自动解散军团以节省开支"""
        terms = TerminologyService.get()
        disbanded = 0
        savings = 0

        # 优先解散非老兵的未指派军团
        candidates = [l for l in self.get_active_legions()
                      if not l.is_veteran and l.war_id is None]

        for legion in candidates:
            if savings >= shortfall:
                break
            legion.disband()
            savings += 2  # 节省的维护费
            disbanded += 1

        return disbanded

    # ========== 战斗相关 ==========

    def get_legions_for_battle(self, war_id: str) -> List[Legion]:
        """获取指派到某战争的所有军团"""
        return [l for l in self._legions if l.war_id == war_id]

    def apply_battle_results(self, war_id: str, victory: bool, disaster: bool = False):
        """应用战斗结果到军团"""
        legions = self.get_legions_for_battle(war_id)

        for legion in legions:
            legion.battles_fought += 1

            if disaster:
                # 灾难：军团覆灭
                legion.status = LegionStatus.DISBANDED
                legion.recall()
                print(f"      💀 {legion.name} destroyed in disaster!")
            elif victory:
                # 胜利：晋升为老兵
                legion.promote_to_veteran()
                legion.recall()  # 凯旋召回
                print(f"      🏆 {legion.name} returns in triumph!")
            else:
                # 失败或僵持：保持现状
                print(f"      ⏳ {legion.name} remains in field")
                pass

    # ========== 显示 ==========

    def get_military_summary(self) -> str:
        """获取军事摘要"""
        terms = TerminologyService.get()

        unraised = len(self.get_available_legions())
        active = len([l for l in self.get_active_legions() if not l.is_veteran])
        veteran = len([l for l in self.get_active_legions() if l.is_veteran])
        assigned = len(self.get_assigned_legions())

        total_cost, _ = self.calculate_maintenance()

        lines = [
            f"\n   🛡️  {terms.legion} Status:",
            f"      Available: {unraised} | Active: {active} | Veteran: {veteran}",
            f"      Assigned to wars: {assigned}",
            f"      Maintenance: {total_cost} {terms.currency}/turn",
        ]

        return "\n".join(lines)

    def display_legion_status(self):
        """显示详细军团状态"""
        terms = TerminologyService.get()
        print(f"\n   🛡️  {terms.legion} Status (10 total):")

        for legion in self._legions:
            info = legion.to_display_dict()
            status = info['emoji']
            vet = "⭐" if info['veteran'] else " "
            cost = info['cost']
            war = f"→War" if info['assigned'] else ""
            print(f"      {status} {info['name']}{vet} [Cost:{cost}] {war}")