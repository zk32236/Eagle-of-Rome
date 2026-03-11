# src/core/systems/naval_system.py
import random
import logging
from typing import Dict, List, Optional, Tuple
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import WarStatus



class NavalSystem:
    """海军系统：管理舰队、建造合同、海战"""

    def __init__(self, state):
        self.state = state
        self._fleets: Dict[int, Fleet] = {}          # 所有舰队，键为编号
        self._next_fleet_number: int = 1
        self._construction_contracts: Dict[int, int] = {}  # 合同ID -> 舰队编号（建造中）

    # ---------- 舰队管理 ----------
    def _can_build_fleet(self) -> bool:
        """检查是否允许建造舰队（皮洛士战争胜利后方可）"""
        return getattr(self.state, "pyrrhic_war_won", False)

    def get_fleet(self, number: int) -> Optional[Fleet]:
        return self._fleets.get(number)

    def get_all_fleets(self) -> List[Fleet]:
        return list(self._fleets.values())

    def get_available_fleets(self) -> List[Fleet]:
        """获取可用舰队（非建造中、非摧毁）"""
        return [f for f in self._fleets.values() if f.status == FleetStatus.AVAILABLE]

    def get_fleets_by_war(self, war_id: str) -> List[Fleet]:
        """获取指派给某战争的所有舰队"""
        return [f for f in self._fleets.values() if f.assigned_war_id == war_id]

    # ---------- 建造合同生成 ----------
    def generate_construction_contracts(self, current_turn: int) -> List[Contract]:
        if not self._can_build_fleet():
            self.state.log_event(
                "[DEBUG] 舰队建造合同生成跳过：皮洛士战争未胜利（技术未解锁）",
                level=logging.DEBUG,
                extra={"function": "generate_construction_contracts", "reason": "tech_locked"}
            )
            return []   # 未解锁，不生成合同
        war_system = self.state.get_war_system()
        if not war_system:
            return []

        threatening_wars = [w for w in war_system._threats if w.naval_required]
        if not threatening_wars:
            return []

        contracts = []
        for war in threatening_wars:
            if self._has_active_contract_for_war(war.id):
                continue

            # 获取敌方海军强度
            enemy_strength = war.enemy_naval_current
            if enemy_strength <= 0:
                continue

            # 从配置获取默认舰队类型和战力
            default_type = self.state.config.get("economic_rules.default_fleet_type", "trireme")
            fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
            if default_type not in fleet_configs:
                continue
            base_strength = fleet_configs[default_type].get("strength_base", 3)
            build_cost_per_ship = fleet_configs[default_type].get("build_cost", 20)

            # 计算所需舰队数量（向上取整）
            needed_ships = (enemy_strength + base_strength - 1) // base_strength  # 简单按单舰战力匹配
            if needed_ships < 1:
                needed_ships = 1

            # 总预算
            total_budget = needed_ships * build_cost_per_ship
            composition = [{"type": default_type, "count": needed_ships}]

            # 创建合同
            contract = self.state.create_contract(
                contract_type=ContractType.PUBLIC_WORKS,
                province_id=0,
                base_cost=total_budget,  # 注意这里 base_cost 设为总预算
                current_turn=current_turn
            )
            contract._is_fleet_construction = True
            contract._target_war_id = war.id
            contract._fleet_type = default_type  # 保留原有字段，但可忽略
            contract._build_time = fleet_configs[default_type].get("build_time", 1)
            contract.name = f"舰队建造（{war.name}）"
            contract._warranty_remaining = 0

            # 存储舰队组成建议
            contract.set_fleet_composition(composition, enemy_strength, total_budget)

            contracts.append(contract)

            self.state.log_event(
                f"生成舰队建造合同：{contract.name}，预算 {total_budget}，需建造 {needed_ships} 艘 {default_type}，工期 {contract._build_time} 年",
                extra={"contract_id": contract.id, "war_id": war.id}
            )

        return contracts

    def _has_active_contract_for_war(self, war_id: str) -> bool:
        """检查是否已有针对该战争的活动合同（PENDING 或 ACTIVE）"""
        for contract in self.state.get_all_contracts():
            if getattr(contract, "_target_war_id", None) == war_id:
                if contract.status in (ContractStatus.PENDING, ContractStatus.BUDGETED, ContractStatus.ACTIVE):
                    return True
        return False

    # ---------- 建造过程管理 ----------
    def on_contract_awarded(self, contract: Contract, winner_id: int):
        if not contract._is_fleet_construction:
            return

        # 获取舰队组成建议
        composition = contract.recommended_fleet_composition
        if not composition:
            # 兼容旧数据：按原逻辑建一艘
            fleet_type = getattr(contract, "_fleet_type", "trireme")
            build_time = getattr(contract, "_build_time", 1)
            target_war_id = getattr(contract, "_target_war_id", None)

            fleet = Fleet(
                number=self._next_fleet_number,
                fleet_type=fleet_type,
                name=f"舰队 {self._next_fleet_number} ({fleet_type})"
            )
            fleet.set_strength_from_config(
                self.state.config.get("economic_rules.fleet_types", {}).get(fleet_type, {})
            )
            fleet._target_war_id = target_war_id
            self._fleets[self._next_fleet_number] = fleet
            self._next_fleet_number += 1

            fleet.start_building(
                start_turn=self.state.turn.turn_number,
                contract_id=contract.id,
                build_time=build_time
            )

            contract.remaining_years = build_time
            contract.duration_years = build_time
            self._construction_contracts[contract.id] = fleet.number

            self.state.log_event(
                f"舰队建造合同 {contract.id} 中标，开始建造 {fleet.name}，预计 {fleet.build_end_turn} 回合完工",
                extra={"fleet_number": fleet.number, "contract_id": contract.id}
            )
        else:
            # 按建议组成建造多艘舰队
            target_war_id = getattr(contract, "_target_war_id", None)
            build_time = getattr(contract, "_build_time", 1)  # 所有舰艇建造时间相同
            fleet_configs = self.state.config.get("economic_rules.fleet_types", {})

            built_fleets = []
            for item in composition:
                fleet_type = item["type"]
                count = item["count"]
                config = fleet_configs.get(fleet_type, {})
                for i in range(count):
                    fleet = Fleet(
                        number=self._next_fleet_number,
                        fleet_type=fleet_type,
                        name=f"舰队 {self._next_fleet_number} ({fleet_type})"
                    )
                    fleet.set_strength_from_config(config)
                    fleet._target_war_id = target_war_id
                    self._fleets[self._next_fleet_number] = fleet
                    self._next_fleet_number += 1

                    fleet.start_building(
                        start_turn=self.state.turn.turn_number,
                        contract_id=contract.id,
                        build_time=build_time
                    )
                    built_fleets.append(fleet.number)

            # 记录合同与舰队的关联（可存储所有舰队编号，这里简化）
            self._construction_contracts[contract.id] = built_fleets[0]  # 只存第一个，但实际需要存储列表

            contract.remaining_years = build_time
            contract.duration_years = build_time

            self.state.log_event(
                f"舰队建造合同 {contract.id} 中标，开始建造 {len(built_fleets)} 艘舰队，预计 {build_time} 回合完工",
                extra={"contract_id": contract.id, "fleet_count": len(built_fleets)}
            )

    def process_fleet_construction(self, current_turn: int) -> List[int]:
        completed = []
        for fleet in self._fleets.values():
            if fleet.is_building and fleet.build_end_turn == current_turn:
                fleet.complete_building()
                # 基础完成日志
                self.state.log_event(
                    f"[DEBUG] 舰队 {fleet.number} 建造完成",
                    level=logging.DEBUG,
                    extra={"fleet": fleet.number, "event": "construction_complete"}
                )
                if fleet._target_war_id:
                    war_system = self.state.get_war_system()
                    if war_system:
                        war = war_system.get_war_by_id(fleet._target_war_id)
                        # 记录目标战争信息
                        self.state.log_event(
                            f"[DEBUG] 舰队 {fleet.number} 目标战争: {fleet._target_war_id}, 战争存在={war is not None}",
                            level=logging.DEBUG,
                            extra={
                                "fleet": fleet.number,
                                "target_war_id": fleet._target_war_id,
                                "war_exists": war is not None
                            }
                        )
                        if war:
                            # 记录战争状态和 naval_required
                            self.state.log_event(
                                f"[DEBUG] 舰队 {fleet.number} 目标战争 {war.id} 状态={war.status.value}, naval_required={war.naval_required}",
                                level=logging.DEBUG,
                                extra={
                                    "fleet": fleet.number,
                                    "war_id": war.id,
                                    "war_status": war.status.value,
                                    "naval_required": war.naval_required
                                }
                            )
                            if war.status.value == "active" and war.naval_required:
                                success = self.assign_fleet_to_war(
                                    fleet.number,
                                    fleet._target_war_id,
                                    "naval",
                                    commander_id=None
                                )
                                self.state.log_event(
                                    f"[DEBUG] 舰队 {fleet.number} 自动指派结果: {success}",
                                    level=logging.DEBUG,
                                    extra={
                                        "fleet": fleet.number,
                                        "war_id": war.id,
                                        "assign_success": success
                                    }
                                )
                            else:
                                # 记录不指派的原因
                                reason = []
                                if war.status.value != "active":
                                    reason.append("war_not_active")
                                if not war.naval_required:
                                    reason.append("naval_not_required")
                                self.state.log_event(
                                    f"[DEBUG] 舰队 {fleet.number} 未指派: 原因 {reason}",
                                    level=logging.DEBUG,
                                    extra={
                                        "fleet": fleet.number,
                                        "war_id": war.id,
                                        "assign_skipped_reason": reason
                                    }
                                )
                        else:
                            self.state.log_event(
                                f"[DEBUG] 舰队 {fleet.number} 目标战争 {fleet._target_war_id} 不存在，未指派",
                                level=logging.DEBUG,
                                extra={
                                    "fleet": fleet.number,
                                    "target_war_id": fleet._target_war_id,
                                    "reason": "war_not_found"
                                }
                            )
                completed.append(fleet.number)
        return completed

    # ---------- 舰队指派 ----------
    def assign_fleet_to_war(self, fleet_id: int, war_id: str, mission_type: str,
                            commander_id: Optional[int] = None) -> bool:
        # 入口日志
        self.state.log_event(
            f"[DEBUG] assign_fleet_to_war 开始: fleet_id={fleet_id}, war_id={war_id}, mission_type={mission_type}, commander_id={commander_id}",
            level=logging.DEBUG,
            extra={
                "function": "assign_fleet_to_war",
                "fleet_id": fleet_id,
                "war_id": war_id,
                "mission_type": mission_type,
                "commander_id": commander_id,
                "phase": "enter"
            }
        )
        fleet = self.get_fleet(fleet_id)
        if not fleet or fleet.status != FleetStatus.AVAILABLE:
            self.state.log_event(
                f"[DEBUG] assign_fleet_to_war 失败: 舰队不可用",
                level=logging.DEBUG,
                extra={
                    "function": "assign_fleet_to_war",
                    "fleet_id": fleet_id,
                    "phase": "exit",
                    "success": False,
                    "reason": "fleet_unavailable"
                }
            )
            return False

        war_system = self.state.get_war_system()
        war = war_system.get_war_by_id(war_id) if war_system else None
        if not war or not war.naval_required:
            self.state.log_event(
                f"[DEBUG] assign_fleet_to_war 失败: 战争不存在或不需要海战",
                level=logging.DEBUG,
                extra={
                    "function": "assign_fleet_to_war",
                    "fleet_id": fleet_id,
                    "war_id": war_id,
                    "phase": "exit",
                    "success": False,
                    "reason": "war_invalid_or_no_naval"
                }
            )
            return False

        if fleet.assign_to_war(war_id, mission_type, commander_id):
            war.assign_fleet(fleet_id)
            self.state.log_event(
                f"[DEBUG] assign_fleet_to_war 成功",
                level=logging.DEBUG,
                extra={
                    "function": "assign_fleet_to_war",
                    "fleet_id": fleet_id,
                    "war_id": war_id,
                    "phase": "exit",
                    "success": True
                }
            )
            return True
        else:
            self.state.log_event(
                f"[DEBUG] assign_fleet_to_war 失败: fleet.assign_to_war 返回 False",
                level=logging.DEBUG,
                extra={
                    "function": "assign_fleet_to_war",
                    "fleet_id": fleet_id,
                    "war_id": war_id,
                    "phase": "exit",
                    "success": False,
                    "reason": "assign_method_failed"
                }
            )
            return False

    def recall_fleet_from_war(self, fleet_id: int) -> bool:
        """从战争召回舰队"""
        fleet = self.get_fleet(fleet_id)
        if not fleet or fleet.assigned_war_id is None:
            return False
        war_id = fleet.assigned_war_id
        fleet.recall()
        war_system = self.state.get_war_system()
        if war_system:
            war = war_system.get_war_by_id(war_id)
            if war:
                war.remove_fleet(fleet_id)
        return True

    def recall_fleets_from_war(self, war_id: str) -> None:
        """
        召回指定战争的所有指派舰队。
        遍历所有舰队，将 assigned_war_id 匹配且状态为 ON_MISSION 的舰队召回。
        """
        for fleet in list(self._fleets.values()):
            if fleet.assigned_war_id == war_id and fleet.status == FleetStatus.ON_MISSION:
                self.recall_fleet_from_war(fleet.number)

    # ---------- 海战判定 ----------
    def resolve_naval_battle(self, war) -> Tuple[str, Dict]:
        """
        执行海战，返回 (结果字符串, 损失详情)
        结果: "TRIUMPH", "VICTORY", "STALEMATE", "DEFEAT", "DISASTER"
        """
        # 获取我方舰队（排除建造中的）
        roman_fleets = [self.get_fleet(fid) for fid in war.assigned_fleet_ids
                        if self.get_fleet(fid) and not self.get_fleet(fid).is_building]
        if not roman_fleets:
            # 没有可用舰队，海战自动失败
            return "DEFEAT", {"roman_losses": 0, "enemy_loss": 0}

        roman_strength = sum(f.get_combat_strength(self.state) for f in roman_fleets)
        enemy_strength = war.enemy_naval_current
        dice = random.randint(2, 12)
        total = dice + roman_strength - enemy_strength
        result = self._simplified_crt(dice, total, war)
        losses = self._apply_naval_losses(war, result, roman_fleets)
        return result, {"roman_losses": losses, "enemy_loss": 0}

    def _simplified_crt(self, dice: int, total: int, war) -> str:
        """简化版CRT判定，与 combat 阶段一致"""
        if war.is_disaster_roll(dice):
            return "DISASTER"
        elif total >= 12:
            return "TRIUMPH"
        elif total >= 6:
            return "VICTORY"
        elif war.is_standoff_roll(dice) or -3 <= total < 6:
            return "STALEMATE"
        elif total < -3:
            return "DEFEAT"
        else:
            return "STALEMATE"

    def _apply_naval_losses(self, war, result: str, roman_fleets: List[Fleet]) -> int:
        """
        应用海战损失，返回罗马损失舰队数。
        简化处理：灾难时全部摧毁，大胜时无损，其他情况按比例。
        """
        losses = 0
        if result == "DISASTER":
            for fleet in roman_fleets:
                fleet.mark_destroyed(self.state.turn.turn_number)
                war.remove_fleet(fleet.number)
            losses = len(roman_fleets)
        elif result == "DEFEAT":
            # 损失一半
            half = len(roman_fleets) // 2
            for i, fleet in enumerate(roman_fleets):
                if i < half:
                    fleet.mark_destroyed(self.state.turn.turn_number)
                    war.remove_fleet(fleet.number)
                    losses += 1
        elif result == "STALEMATE":
            # 损失少量（如1艘）
            if roman_fleets:
                fleet = roman_fleets[0]
                fleet.mark_destroyed(self.state.turn.turn_number)
                war.remove_fleet(fleet.number)
                losses = 1
        # VICTORY 和 TRIUMPH 无损
        return losses

    # ---------- 维护与解散 ----------
    def calculate_maintenance(self) -> int:
        """计算所有活跃舰队的维护费总和"""
        total = 0
        for fleet in self._fleets.values():
            if fleet.status not in (FleetStatus.DESTROYED, FleetStatus.BUILDING):
                total += fleet.get_maintenance_cost(self.state)
        return total

    def disband_unused_fleets(self, current_turn: int, decider: 'FleetDisbandDecider') -> List[int]:
        """
        根据决策器解散舰队。
        返回被解散的舰队编号列表。
        """
        disbanded = []
        for fleet in list(self._fleets.values()):
            if decider.should_disband_fleet(fleet, self.state):
                fleet.mark_destroyed(current_turn)
                disbanded.append(fleet.number)
                self.state.log_event(
                    f"[DEBUG] 舰队 {fleet.number} 已解散（根据决策器）",
                    level=logging.DEBUG,
                    extra={"fleet": fleet.number, "reason": "decider"}
                )
        return disbanded

    # ---------- 舰队恢复 ----------

    def generate_replacement_contracts(self, current_turn: int) -> List[Contract]:
        if not self._can_build_fleet():
            return []
        """为活跃的需要海战且罗马无可用舰队的战争生成补充舰队建造合同"""
        war_system = self.state.get_war_system()
        if not war_system:
            return []
        active_wars = war_system.get_active_wars()
        if not active_wars:
            return []
        # 如果有任何可用舰队，则无需补充
        if self.get_available_fleets():
            return []

        contracts = []
        for war in active_wars:
            if not war.naval_required:
                continue
            # 检查是否有针对该战争的活跃合同（PENDING/BUDGETED/ACTIVE）
            if self._has_active_contract_for_war(war.id):
                continue
            # 检查是否有针对该战争的舰队正在建造
            building_fleets = [f for f in self._fleets.values()
                               if f.is_building and f._target_war_id == war.id]
            if building_fleets:
                continue

            # 获取敌方海军强度
            enemy_strength = war.enemy_naval_current
            if enemy_strength <= 0:
                continue

            # 从配置获取默认舰队类型和战力
            default_type = self.state.config.get("economic_rules.default_fleet_type", "trireme")
            fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
            if default_type not in fleet_configs:
                continue
            base_strength = fleet_configs[default_type].get("strength_base", 3)
            build_cost_per_ship = fleet_configs[default_type].get("build_cost", 20)

            # 计算所需舰队数量（向上取整）
            needed_ships = (enemy_strength + base_strength - 1) // base_strength
            if needed_ships < 1:
                needed_ships = 1

            total_budget = needed_ships * build_cost_per_ship
            composition = [{"type": default_type, "count": needed_ships}]

            # 创建合同
            contract = self.state.create_contract(
                contract_type=ContractType.PUBLIC_WORKS,
                province_id=0,
                base_cost=total_budget,
                current_turn=current_turn
            )
            contract._is_fleet_construction = True
            contract._target_war_id = war.id
            contract._fleet_type = default_type
            contract._build_time = fleet_configs[default_type].get("build_time", 1)
            contract.name = f"舰队建造（{war.name}）"
            contract._warranty_remaining = 0
            contract.set_fleet_composition(composition, enemy_strength, total_budget)
            contracts.append(contract)

            self.state.log_event(
                f"为激活战争生成补充舰队建造合同：{contract.name}，预算 {total_budget}，需建造 {needed_ships} 艘 {default_type}，工期 {contract._build_time} 年",
                extra={"contract_id": contract.id, "war_id": war.id}
            )
        return contracts


    def apply_maintenance(self) -> Tuple[bool, str]:
        """扣除维护费，国库不足时尝试解散"""
        total = self.calculate_maintenance()
        if total == 0:
            return True, "无需支付舰队维护费"

        if self.state.treasury < total:
            # 国库不足，解散部分可用舰队
            available = self.get_available_fleets()
            to_disband = []
            for fleet in available:
                if self.state.treasury + fleet.get_maintenance_cost(self.state) >= total:
                    break
                to_disband.append(fleet)
            for fleet in to_disband:
                fleet.mark_destroyed(self.state.turn.turn_number)
                self.state.log_event(f"因国库不足，舰队 {fleet.name} 解散")
            # 重新计算维护费
            total = self.calculate_maintenance()
            if self.state.treasury < total:
                return False, f"国库仍不足以支付舰队维护费，需要 {total}"

        self.state.treasury -= total
        return True, f"支付舰队维护费 {total}"

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "_fleets": {num: fleet.to_dict() for num, fleet in self._fleets.items()},
            "_next_fleet_number": self._next_fleet_number,
            "_construction_contracts": self._construction_contracts.copy(),
        }

    def load_from_dict(self, data: dict):
        self._fleets = {}
        for num, fleet_data in data.get("_fleets", {}).items():
            self._fleets[int(num)] = Fleet.from_dict(fleet_data)
        self._next_fleet_number = data.get("_next_fleet_number", 1)
        self._construction_contracts = data.get("_construction_contracts", {}).copy()