# src/core/systems/military_system.py

from typing import List, Optional, Dict, Tuple, TYPE_CHECKING
from src.core.entities.legion import Legion, LegionStatus
from src.core.localization import TerminologyService

if TYPE_CHECKING:
    from src.core.game_state import GameState


class MilitarySystem:
    """
    军事管理系统

    职责：
    1. 管理10个军团池
    2. 征召/解散逻辑
    3. 维护费计算
    4. 军团指派到战争
    5. 新增：军团恢复机制
    """

    MAX_LEGIONS = 8

    def __init__(self, state: 'GameState'):
        self.state = state
        self._legions: List[Legion] = []
        self._initialize_legions()

    def _initialize_legions(self):
        """初始化10个军团"""
        for i in range(1, self.MAX_LEGIONS + 1):
            legion = Legion(number=i)
            self._legions.append(legion)
        # print(f"   ⚔️  Military system: {self.MAX_LEGIONS} legions ready")

    # ========== 查询方法 ==========

    def get_all_legions(self) -> List[Legion]:
        """获取所有军团"""
        return self._legions

    def get_available_legions(self) -> List[Legion]:
        """获取可征召的军团（包括未征召和已解散的）"""
        return [l for l in self._legions
                if l.status in (LegionStatus.UNRAISED, LegionStatus.DISBANDED)]

    def get_active_legions(self) -> List[Legion]:
        """获取已征召的活跃军团（ACTIVE 和 VETERAN）"""
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

    # ========== 新增：获取被摧毁的军团 ==========
    def get_destroyed_legions(self) -> List[Legion]:
        """获取所有被摧毁的军团，按摧毁回合升序排序（最老的在前面）"""
        destroyed = [l for l in self._legions if l.status == LegionStatus.DESTROYED]
        destroyed.sort(key=lambda l: l.destroyed_turn)
        return destroyed

    # ========== 新增：军团恢复逻辑 ==========
    def process_legion_recovery(self, current_turn: int) -> List[int]:
        """
        公共方法：处理军团恢复，返回本次恢复的军团编号列表。
        """
        return self._process_legion_recovery(current_turn)

    def _process_legion_recovery(self, current_turn: int) -> List[int]:
        """
        处理军团恢复：
        - 从配置读取恢复间隔 interval
        - 遍历所有被摧毁的军团，检查是否满足恢复条件（current_turn - destroyed_turn >= interval）
        - 每 interval 回合恢复一个最老的被摧毁军团（满足条件的第一个）
        - 恢复后的军团状态变为 DISBANDED
        返回本次恢复的军团编号列表（用于日志）
        """
        interval = self.state.config.get("combat_rules.legion_recovery_interval", 5)
        if interval <= 0:
            return []

        destroyed = self.get_destroyed_legions()
        if not destroyed:
            return []

        recovered = []
        # 从最老的开始检查，恢复第一个满足条件的
        for legion in destroyed:
            if current_turn - legion.destroyed_turn >= interval:
                if legion.recover():
                    recovered.append(legion.number)
                    # 注意：每次只恢复一个（最老且满足条件的）
                    break

        if recovered:
            terms = TerminologyService.get()
            print(f"      ♻️ 军团 {recovered[0]} 已恢复，可重新征召")

        return recovered

    # ========== 军团操作 ==========

    def recruit_legion(self, legion_number: int) -> Tuple[bool, str]:
        """征召指定军团（支持重新招募已解散的）"""
        terms = TerminologyService.get()
        legion = self.get_legion_by_number(legion_number)

        if not legion:
            return False, f"Invalid {terms.legion} number"

        # 检查是否可以征召（UNRAISED 或 DISBANDED）
        if legion.status not in (LegionStatus.UNRAISED, LegionStatus.DISBANDED):
            return False, f"{legion.name} already active"

        # 检查国库
        recruit_cost = self.state.get_economic_rule("legion_recruit_cost", 10)
        if self.state.treasury < recruit_cost:
            return False, f"Insufficient treasury ({recruit_cost} needed)"

        # 执行征召
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
        """指派多个军团到战争（同时记录军团编号到战争对象）"""
        terms = TerminologyService.get()
        assigned = 0
        errors = []

        # 获取战争对象（需要从战争系统获取）
        war_system = self.state.get_war_system()
        war = war_system.get_war_by_id(war_id) if war_system else None
        if not war:
            return 0, f"战争 {war_id} 不存在"

        for num in legion_numbers:
            legion = self.get_legion_by_number(num)
            if not legion:
                errors.append(f"Invalid {terms.legion} {num}")
                continue

            if legion.status not in (LegionStatus.ACTIVE, LegionStatus.VETERAN):
                errors.append(f"{legion.name} not active")
                continue

            if legion.war_id:
                errors.append(f"{legion.name} already assigned to war")
                continue

            if legion.assign_to_war(war_id, commander_id):
                assigned += 1
                # 记录军团编号到战争对象
                if hasattr(war, 'add_legion_number'):
                    war.add_legion_number(num)

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
                # 灾难：军团覆灭 -> 标记为 DESTROYED
                legion.mark_destroyed(self.state.turn.turn_number)
                print(f"      💀 {legion.name} destroyed in disaster!")
            elif victory:
                # 胜利：晋升为老兵
                legion.promote_to_veteran()
                legion.recall()
                print(f"      🏆 {legion.name} returns in triumph!")
            else:
                # 失败或僵持：保持现状
                print(f"      ⏳ {legion.name} remains in field")

    # ========== 显示 ==========

    def get_military_summary(self) -> str:
        """获取军事摘要（已包含 DESTROYED 统计）"""
        terms = TerminologyService.get()

        unraised = len([l for l in self._legions if l.status == LegionStatus.UNRAISED])
        active = len([l for l in self._legions if l.status in (LegionStatus.ACTIVE, LegionStatus.VETERAN)])
        disbanded = len([l for l in self._legions if l.status == LegionStatus.DISBANDED])
        destroyed = len([l for l in self._legions if l.status == LegionStatus.DESTROYED])
        assigned = len(self.get_assigned_legions())

        total_cost, _ = self.calculate_maintenance()

        lines = [
            f"\n   🛡️  {terms.legion} Status:",
            f"      Available: {unraised} | Active: {active} | Disbanded: {disbanded} | Destroyed: {destroyed}",
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
            destroyed_info = f" (摧毁于{legion.destroyed_turn})" if legion.status == LegionStatus.DESTROYED else ""
            print(f"      {status} {info['name']}{vet}[Cost:{cost}] {war}{destroyed_info}")

    # ========== 新增：解散军团（用于战争结束） ==========
    def disband_legions_for_war(self, legion_numbers: List[int]) -> Tuple[int, List[str]]:
        """
        解散指定编号列表的军团。
        返回 (成功解散数量, 错误信息列表)
        """
        terms = TerminologyService.get()
        disbanded = 0
        errors = []

        for num in legion_numbers:
            legion = self.get_legion_by_number(num)
            if not legion:
                errors.append(f"军团 {num} 不存在")
                continue

            # 检查是否已指派给战争
            if legion.war_id:
                errors.append(f"{legion.name} 仍指派给战争，无法解散")
                continue

            # 检查是否可以解散
            if not legion.can_be_disbanded(None):
                errors.append(f"{legion.name} 无法解散（可能已在解散状态或未征召）")
                continue

            if legion.disband():
                disbanded += 1
            else:
                errors.append(f"{legion.name} 解散失败")

        return disbanded, errors