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
        """
        根据需要海战的战争威胁生成舰队建造合同。
        返回生成的合同列表。
        """
        war_system = self.state.get_war_system()
        if not war_system:
            return []

        # 获取所有需要海战的威胁战争
        threatening_wars = [w for w in war_system._threats if w.naval_required]
        if not threatening_wars:
            return []

        contracts = []
        # 每个需要海战的威胁生成一个舰队建造合同（简单处理：每个战争一个合同，建造一支舰队）
        for war in threatening_wars:
            # 检查是否已有针对该战争的建造合同（未决或执行中）
            if self._has_active_contract_for_war(war.id):
                continue

            # 确定舰队类型（可配置，暂时用默认）
            fleet_type = self.state.config.get("economic_rules.default_fleet_type", "trireme")
            fleet_config = self.state.config.get("economic_rules.fleet_types", {}).get(fleet_type, {})
            build_cost = fleet_config.get("build_cost", 40)
            build_time = fleet_config.get("build_time", 1)

            # 创建合同（作为公共工程合同的一种，但标识为舰队建造）
            contract = self.state.create_contract(
                contract_type=ContractType.PUBLIC_WORKS,  # 复用公共工程合同类型
                province_id=0,  # 意大利本土
                base_cost=build_cost,
                current_turn=current_turn
            )
            # 标记为舰队建造合同，并存储战争ID和舰队类型
            contract._is_fleet_construction = True
            contract._target_war_id = war.id
            contract._fleet_type = fleet_type
            contract._build_time = build_time
            contract.name = f"舰队建造（{war.name}）"
            # 确保质保年限为0
            contract._warranty_remaining = 0
            contracts.append(contract)

            self.state.log_event(
                f"生成舰队建造合同：{contract.name}，预算 {build_cost}，工期 {build_time} 年",
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
        """
        当建造合同中标后调用，创建舰队并标记为建造中。
        """
        if not getattr(contract, "_is_fleet_construction", False):
            return

        fleet_type = getattr(contract, "_fleet_type", "trireme")
        build_time = getattr(contract, "_build_time", 1)
        target_war_id = getattr(contract, "_target_war_id", None)

        # 创建舰队
        fleet = Fleet(
            number=self._next_fleet_number,
            fleet_type=fleet_type,
            name=f"舰队 {self._next_fleet_number} ({fleet_type})"
        )
        fleet.set_strength_from_config(
            self.state.config.get("economic_rules.fleet_types", {}).get(fleet_type, {})
        )
        fleet._target_war_id = target_war_id  # 记录目标战争ID
        self._fleets[self._next_fleet_number] = fleet
        self._next_fleet_number += 1

        # 标记为建造中
        fleet.start_building(
            start_turn=self.state.turn.turn_number,
            contract_id=contract.id,
            build_time=build_time
        )

        # 设置合同剩余年限（用于显示），但质保年限保持0
        contract.remaining_years = build_time
        contract.duration_years = build_time
        contract._warranty_remaining = 0  # 确保为0

        # 记录合同与舰队的关联
        self._construction_contracts[contract.id] = fleet.number

        self.state.log_event(
            f"舰队建造合同 {contract.id} 中标，开始建造 {fleet.name}，预计 {fleet.build_end_turn} 回合完工",
            extra={"fleet_number": fleet.number, "contract_id": contract.id}
        )

    def process_fleet_construction(self, current_turn: int) -> List[int]:
        """
        每回合调用，检查建造中的舰队是否完成。
        返回本回合完成的舰队编号列表。
        """
        completed = []
        for fleet in self._fleets.values():
            if fleet.is_building and fleet.build_end_turn == current_turn:
                fleet.complete_building()
                # 自动指派到目标战争（如果存在且战争仍活跃）
                if fleet._target_war_id:
                    war_system = self.state.get_war_system()
                    if war_system:
                        war = war_system.get_war_by_id(fleet._target_war_id)
                        if war and war.status == WarStatus.ACTIVE and war.naval_required:
                            self.assign_fleet_to_war(
                                fleet.number,
                                fleet._target_war_id,
                                "naval",
                                commander_id=None  # 无指挥官，可后续指派
                            )
                completed.append(fleet.number)
                self.state.log_event(
                    f"舰队 {fleet.name} 建造完成，现已可用",
                    extra={"fleet_number": fleet.number}
                )
        return completed

    # ---------- 舰队指派 ----------
    def assign_fleet_to_war(self, fleet_id: int, war_id: str, mission_type: str,
                            commander_id: Optional[int] = None) -> bool:
        """指派舰队到战争（仅当舰队可用且战争需要海战）"""
        fleet = self.get_fleet(fleet_id)
        if not fleet or fleet.status != FleetStatus.AVAILABLE:
            return False

        war_system = self.state.get_war_system()
        war = war_system.get_war_by_id(war_id) if war_system else None
        if not war or not war.naval_required:
            return False

        if fleet.assign_to_war(war_id, mission_type, commander_id):
            war.assign_fleet(fleet_id)
            return True
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

    # ---------- 维护费 ----------
    def calculate_maintenance(self) -> int:
        """计算所有活跃舰队的维护费总和"""
        total = 0
        for fleet in self._fleets.values():
            if fleet.status not in (FleetStatus.DESTROYED, FleetStatus.BUILDING):
                total += fleet.get_maintenance_cost(self.state)
        return total

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