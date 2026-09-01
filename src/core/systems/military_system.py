# src/core/systems/military_system.py

import random
from typing import List, Optional, Dict, Tuple, Any, TYPE_CHECKING
from src.core.entities.legion import Legion, LegionStatus
from src.core.localization import TerminologyService

if TYPE_CHECKING:
    from src.core.game_state import GameState


class MilitarySystem:
    """
    军事管理系统

    职责：
    1. 管理25个军团池
    2. 征召/解散逻辑
    3. 维护费计算
    4. 军团指派到战争
    5. 新增：军团恢复机制
    """

    MAX_LEGIONS = 25

    def __init__(self, state: 'GameState'):
        self.state = state
        self._legions: List[Legion] = []
        # DA-3（WP-E-R5）：属性兜底——economic_service 经 getattr 读取；
        # 运行期每回合由 apply_maintenance 入口清零（ODR-R5-G3-1）
        self._last_maintenance_disbanded = 0
        self._initialize_legions()

    def _initialize_legions(self):
        """初始化25个军团"""
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
        """获取已征召的活跃军团（ACTIVE 状态）"""
        return [l for l in self._legions if l.status == LegionStatus.ACTIVE]

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
            legion = self.get_legion_by_number(recovered[0])
            self.state.log_event(
                f"军团恢复: #{recovered[0]}",
                extra={
                    "type": "legion_recovered",
                    "legion_number": recovered[0],
                    "legion_name": legion.name if legion else f"Legion {recovered[0]}",
                    "destroyed_turn": legion.destroyed_turn if legion else None,
                    "current_turn": current_turn,
                    "recovery_interval": interval,
                }
            )

        return recovered

    # ========== 军团操作 ==========

    def recruit_legion(self, legion_number: int) -> Tuple[bool, str]:
        terms = TerminologyService.get()
        legion = self.get_legion_by_number(legion_number)

        if not legion:
            return False, f"❌ 无效军团编号"

        if legion.status not in (LegionStatus.UNRAISED, LegionStatus.DISBANDED):
            return False, f"⚠️ {legion.name} 当前状态无法征召"

        recruit_cost = self.state.get_economic_rule("legion_recruit_cost", 10)

        # 执行征召（G1-17/R-10：国库不设军事承诺上限——移除国库拒绝；扣款照扣，国库可负，
        # 赤字由 Resolution/game-over 兑底）
        legion.status = LegionStatus.ACTIVE
        # G1-19（WP-G GB）：正常重募保留 is_veteran——Veteran 唯一清除点 = mark_destroyed（R-13）
        self.state.treasury -= recruit_cost

        success_msg = f"✅ 征召 {legion.name}，花费 {recruit_cost} {terms.currency}，国库剩余 {self.state.treasury} {terms.currency}"
        return True, success_msg

    def recruit_multiple(self, count: int) -> List[Tuple[int, bool, str]]:
        """
        征召多个军团，返回每个征召尝试的结果，但控制台输出为汇总信息。
        """
        terms = TerminologyService.get()
        available = self.get_available_legions()
        recruit_cost = self.state.get_economic_rule("legion_recruit_cost", 10)
        total_cost = 0
        recruited_count = 0
        results = []

        for legion in available[:count]:
            # 执行征召（recruit_legion 会扣款并修改状态；G1-17：国库无逐军团门槛，禁 affordability 上限）
            success, msg = self.recruit_legion(legion.number)
            results.append((legion.number, success, msg))
            if success:
                recruited_count += 1
                total_cost += recruit_cost

        # 打印汇总信息
        if recruited_count > 0:
            print(
                f"      ✅ 征召 {recruited_count} 个军团，总花费 {total_cost} {terms.currency}，国库剩余 {self.state.treasury} {terms.currency}")
        if len(results) > recruited_count:
            failed_count = len(results) - recruited_count
            print(f"      ⚠️ 有 {failed_count} 个军团征召失败（状态不可用或其他原因）")

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

            if legion.status != LegionStatus.ACTIVE:  # 修改：只有 ACTIVE 才能指派
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
            cost = legion.get_maintenance_cost(self.state)
            total += cost
            breakdown[legion.name] = cost

        return total, breakdown

    def apply_maintenance(self, verbose: bool = True) -> Tuple[bool, str]:
        """扣除维护费，verbose 控制是否打印详细消息"""
        terms = TerminologyService.get()
        # DA-1（WP-E-R5）：入口清零，防 total==0 早退读陈旧 disbanded 计数（ODR-R5-G3-1）
        self._last_maintenance_disbanded = 0
        total_before, _ = self.calculate_maintenance()

        if total_before == 0:
            # 无现役军团：不扣款，但强制日志（FC-R5-C：不静默）
            self.state.log_event(
                "军团维护费: 无现役军团（应扣 0）",
                extra={"type": "legion_maintenance", "total": 0, "charged": 0,
                       "shortfall": 0, "disbanded": 0, "treasury_after": self.state.treasury})
            return True, (f"No {terms.legion} maintenance needed" if verbose else "")

        treasury_before = self.state.treasury
        disbanded = 0
        if treasury_before < total_before:
            # 短款（FC-R5-A）：① 先裁军（非老兵+未指派，真实 savings）→ ② 重算应扣 → ③ 剩余差额照扣（国库可负）
            disbanded = self._auto_disband_for_funds(total_before - treasury_before)
            total_after, _ = self.calculate_maintenance()
        else:
            # 足额：全扣（现状不变）
            total_after = total_before

        charged = total_after
        self.state.treasury -= charged
        shortfall = max(0, charged - treasury_before)
        self._last_maintenance_disbanded = disbanded

        # FC-R5-C：无条件强制日志（verbose=False 亦不静默；修复 G1 Q3 无 maintenance 事件）
        self.state.log_event(
            f"军团维护费结算: 应扣 {total_before} 实扣 {charged} 缺口 {shortfall} 解散 {disbanded}",
            extra={"type": "legion_maintenance",
                   "total": total_before, "charged": charged,
                   "shortfall": shortfall, "disbanded": disbanded,
                   "treasury_after": self.state.treasury})

        if verbose:
            msg = f"Paid {charged} {terms.currency} for {terms.legion} maintenance"
            if shortfall > 0:
                msg += f"（缺口 {shortfall}）"
            if disbanded > 0:
                msg += f"（解散 {disbanded} 军团）"
        else:
            msg = ""
        return True, msg

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
            # DA-2（WP-E-R5 / FC-R5-E）：savings 用真实维护费（非硬编码 2），disband 成功才累计
            cost = legion.get_maintenance_cost(self.state)
            if legion.disband():
                savings += cost
                disbanded += 1

        return disbanded

    # ========== 战斗相关 ==========

    def get_legions_for_battle(self, war_id: str) -> List[Legion]:
        """获取指派到某战争的所有军团（live 实体附着 = 战斗参与者唯一权威，R-17）"""
        return [l for l in self._legions if l.war_id == war_id]

    def apply_land_casualties(self, war_id: str, result: str) -> List[int]:
        """陆战伤亡唯一 mutation owner（G1-05/06/07 / G2-C §4，WP-G GB）。

        - DEFEAT:   从 live 参战集 random.sample 无放回 ceil(N/2) → mark_destroyed(turn)
        - DISASTER: 全部 live 参战 → mark_destroyed(turn)
        幸存者零 mutation（保持 ACTIVE + war_id + commander_id）。
        返回被摧毁军团编号列表。
        """
        participants = self.get_legions_for_battle(war_id)
        N = len(participants)
        result_upper = (result or "").upper()
        if result_upper == "DISASTER":
            loss_count = N
        elif result_upper == "DEFEAT":
            loss_count = N - N // 2  # = ceil(N/2)（G1-06）
        else:
            loss_count = 0
        if loss_count <= 0 or N == 0:
            return []
        # G1-05：随机无放回（禁 participants[:losses] 前缀序/列表序）
        casualties = random.sample(participants, loss_count)
        current_turn = self.state.turn.turn_number if self.state.turn else 0
        numbers = []
        for legion in casualties:
            legion.mark_destroyed(current_turn)  # DESTROYED + 清 war_id/commander_id/is_veteran（G1-07）
            numbers.append(legion.number)
        return numbers

    def apply_battle_results(self, war_id: str, victory: bool, disaster: bool = False) -> List[int]:
        """应用战斗结果到军团（legacy/测试面；生产 canonical 入口 = combat_api.auto_resolve_combat）。

        D-2（WP-G GB）：DEFEAT/DISASTER 委托 apply_land_casualties（S2 唯一伤亡 mutation
        owner——随机 ceil(N/2) DESTROYED / 全灭，G1-05/06/07）；VICTORY/TRIUMPH 保留
        既有 legacy 晋升+召回语义（canonical 晋升统一在 war_system.resolve_war victory 分支）。
        """
        legions = self.get_legions_for_battle(war_id)
        for legion in legions:
            legion.battles_fought += 1

        if disaster:
            return self.apply_land_casualties(war_id, "DISASTER")
        if not victory:
            return self.apply_land_casualties(war_id, "DEFEAT")

        for legion in legions:
            # 胜利：晋升为老兵
            legion.promote_to_veteran()
            legion.recall()
            print(f"      🏆 {legion.name} returns in triumph!")
        return []

    # ========== 显示 ==========

    def get_military_summary(self) -> str:
        """获取军事摘要（已包含 DESTROYED 统计）"""
        terms = TerminologyService.get()

        available = len([l for l in self._legions if l.status in (LegionStatus.UNRAISED, LegionStatus.DISBANDED)])
        active = len([l for l in self._legions if l.status == LegionStatus.ACTIVE])  # 修改：只统计 ACTIVE
        destroyed = len([l for l in self._legions if l.status == LegionStatus.DESTROYED])
        assigned = len(self.get_assigned_legions())

        total_cost, _ = self.calculate_maintenance()

        lines = [
            f"\n   🛡️  {terms.legion} Status:",
            f"      Available: {available} | Active: {active} | Destroyed: {destroyed}",
            f"      Assigned to wars: {assigned}",
            f"      Maintenance: {total_cost} {terms.currency}/turn",
        ]

        return "\n".join(lines)

    def display_legion_status(self):
        """显示详细军团状态"""
        terms = TerminologyService.get()
        print(f"\n   🛡️  {terms.legion} Status (10 total):")

        for legion in self._legions:
            info = legion.to_display_dict(self.state)
            status_emoji = info['status_emoji']  # 修改：从 status_emoji 获取
            vet = "⭐" if info['is_veteran'] else " "  # 修改：使用 is_veteran
            cost = info['cost']
            war = f"→War" if info['assigned'] else ""
            destroyed_info = f" (摧毁于{legion.destroyed_turn})" if legion.status == LegionStatus.DESTROYED else ""
            print(f"      {status_emoji} {info['name']}{vet}[Cost:{cost}] {war}{destroyed_info}")

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

    # ========== 序列化原语（O 件 §1/§2，WP-G G4-GD）==========
    # GameState.to_dict/load_from_dict 存档接线消费；Legion.to_dict/from_dict = GB S6
    # （is_veteran/war_id/commander_id/_destroyed_turn/_legion_type 全字段 + 退化路径）。

    def to_dict(self) -> Dict[str, Any]:
        """军事系统全量持久（25 军团全状态，O 件 §2）。"""
        return {
            "_legions": [l.to_dict() for l in self._legions],
        }

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """恢复军事系统（缺键 → 重建 25 UNRAISED 军团，旧存档退化不崩，O 件 §3）。

        `_last_maintenance_disbanded` 为运行期计数（apply_maintenance 入口清零），不持久。
        """
        raw = data.get("_legions")
        if not raw:
            self._legions = [Legion(number=i) for i in range(1, self.MAX_LEGIONS + 1)]
        else:
            self._legions = [Legion.from_dict(d) for d in raw]
        self._last_maintenance_disbanded = 0