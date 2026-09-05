# src/core/systems/naval_system.py
import random
import logging
from typing import Any, Dict, List, Optional, Tuple
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import WarStatus


# R1-G-01（WP-G-R1 v1.6 §2.1.6，S1）：naval-only forced-result 词表归一（fail-closed）。
# `testing.force_naval_result` 与 land `testing.force_battle_result` 分离——单一 override
# 无法确定性表达「naval DEFEAT 阻断陆战」与「naval VICTORY → 继续陆战」两条正交路径。
# 未命中/非法/空/缺省 → None → 正常 random.randint + _simplified_crt。
_FORCED_NAVAL_RESULT_MAP = {
    "stalemate": "STALEMATE",
    "draw": "STALEMATE",
    "victory": "VICTORY",
    "triumph": "TRIUMPH",
    "defeat": "DEFEAT",
    "disaster": "DISASTER",
}


def _normalize_forced_naval_result(value: Any) -> Optional[str]:
    """R1-G-01：naval forced-result 归一化（大小写/空格容忍；非 str / 非法值 → None）。"""
    if not isinstance(value, str):
        return None
    return _FORCED_NAVAL_RESULT_MAP.get(value.strip().lower())


def _fleet_contract_nominal_strength(contract: Contract, fleet_configs: dict) -> int:
    """R1-G-04（WP-G-R1 v1.6 §2.4）：PENDING/BUDGETED 舰队建造合同的未物化约定容量。

    按合同组成（recommended_fleet_composition：needed_ships × base_strength）推导——
    尚无 Fleet 实体前其容量以合同组成计 committed_pending；无组成 → 0（无计划容量）。
    """
    total = 0
    for item in contract.recommended_fleet_composition or []:
        ftype = item.get("type", "")
        count = int(item.get("count", 0) or 0)
        if count <= 0:
            continue
        cfg = fleet_configs.get(ftype, {})
        total += count * int(cfg.get("strength_base", 3))
    return total


class NavalSystem:
    """海军系统：管理舰队、建造合同、海战"""

    def __init__(self, state):
        self.state = state
        self._fleets: Dict[int, Fleet] = {}          # 所有舰队，键为编号
        self._next_fleet_number: int = 1
        self._construction_contracts: Dict[int, int] = {}  # 合同ID -> 舰队编号（建造中）

    # ---------- 舰队管理 ----------
    def assign_available_fleets_to_war(self, war_id: str) -> int:
        """
        将所有 available 状态且目标战争为 war_id 的舰队指派给该战争。
        返回成功指派的舰队数量。
        """
        assigned = 0
        for fleet in self.get_all_fleets():
            if fleet.status == FleetStatus.AVAILABLE and fleet._target_war_id == war_id:
                if self.assign_fleet_to_war(fleet.number, war_id, mission_type="naval"):
                    assigned += 1
        if assigned:
            self.state.log_event(
                f"[DEBUG] 战争 {war_id} 重新激活，自动指派 {assigned} 艘舰队",
                level=logging.DEBUG,
                extra={"war_id": war_id, "assigned_count": assigned}
            )
        return assigned

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
    def _has_existing_fleet_or_contract_for_war(self, war_id: str) -> bool:
        """检查是否已有针对该战争的活动合同或存在非摧毁状态的舰队"""
        # 检查合同
        for contract in self.state.get_all_contracts():
            if getattr(contract, "_target_war_id", None) == war_id:
                if contract.status in (ContractStatus.PENDING, ContractStatus.BUDGETED, ContractStatus.ACTIVE):
                    return True
        # 检查舰队
        for fleet in self._fleets.values():
            if fleet._target_war_id == war_id and fleet.status != FleetStatus.DESTROYED:
                return True
        return False

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

        threatening_wars = war_system.get_naval_threat_wars()
        if not threatening_wars:
            return []

        contracts = []
        for war in threatening_wars:
            if self._has_existing_fleet_or_contract_for_war(war.id):
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
            # R1-G-04（WP-G-R1 v1.6 §7.12.2）：冻结原始预算不变量——离开 generator 时
            # _original_budget == base_cost == total_budget == total_budget > 0
            # （MVP0.5-04 §2.5/§3.5 cost_ratio = actual_cost/original_budget 的分母；
            # 修复前漏设 → 0 → ratio=1.0 fallback，折价 bid 无法调低舰队实际强度）
            contract._original_budget = total_budget
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
                extra={
                    "type": "naval_construction_generated",
                    "contract_id": contract.id,
                    "war_id": war.id,
                    "total_budget": total_budget,
                    "needed_ships": needed_ships,
                    "fleet_type": default_type,
                }
            )

        return contracts

    # ---------- 建造过程管理 ----------
    def on_contract_awarded(self, contract: Contract, winner_id: int):
        if not contract._is_fleet_construction:
            return

        # 获取实际成本和原始预算
        actual_cost = getattr(contract, '_actual_cost', 0)
        original_budget = getattr(contract, '_original_budget', 0)
        if actual_cost <= 0 or original_budget <= 0:
            # 兼容旧数据或手动出价未设置，使用原逻辑不调整
            self.state.log_event(
                f"舰队合同 {contract.id} 缺少实际成本或原始预算，跳过战斗力调整",
                level=logging.WARNING
            )
            cost_ratio = 1.0
        else:
            cost_ratio = actual_cost / original_budget

        # 获取舰队配置
        fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
        default_type = getattr(contract, "_fleet_type", "trireme")

        # 获取舰队组成建议
        composition = contract.recommended_fleet_composition
        if not composition:
            # 单舰队
            fleet_type = default_type
            config = fleet_configs.get(fleet_type, {})
            base_strength = config.get("strength_base", 3)
            actual_strength = base_strength * cost_ratio
            actual_strength = max(1, min(actual_strength, base_strength * 2))
            actual_strength = int(round(actual_strength))

            fleet = Fleet(
                number=self._next_fleet_number,
                fleet_type=fleet_type,
                name=f"舰队 {self._next_fleet_number} ({fleet_type})"
            )
            fleet._strength_base = actual_strength
            fleet._target_war_id = getattr(contract, "_target_war_id", None)
            self._fleets[self._next_fleet_number] = fleet
            self._next_fleet_number += 1

            build_time = getattr(contract, "_build_time", 1)
            fleet.start_building(
                start_turn=self.state.turn.turn_number,
                contract_id=contract.id,
                build_time=build_time
            )
            contract.remaining_years = build_time
            contract.duration_years = build_time
            self._construction_contracts[contract.id] = fleet.number

            self.state.log_event(
                f"舰队建造合同 {contract.id} 中标，开始建造 {fleet.name}，实际强度 {actual_strength}，预计 {build_time} 回合完工",
                extra={"fleet_number": fleet.number, "contract_id": contract.id}
            )
        else:
            # 多舰队：按组成建造多艘，每艘根据类型单独计算强度
            build_time = getattr(contract, "_build_time", 1)
            built_fleets = []
            for item in composition:
                fleet_type = item["type"]
                count = item["count"]
                config = fleet_configs.get(fleet_type, {})
                base_strength = config.get("strength_base", 3)
                actual_strength = base_strength * cost_ratio
                actual_strength = max(1, min(actual_strength, base_strength * 2))
                actual_strength = int(round(actual_strength))

                for i in range(count):
                    fleet = Fleet(
                        number=self._next_fleet_number,
                        fleet_type=fleet_type,
                        name=f"舰队 {self._next_fleet_number} ({fleet_type})"
                    )
                    fleet._strength_base = actual_strength
                    fleet._target_war_id = getattr(contract, "_target_war_id", None)
                    self._fleets[self._next_fleet_number] = fleet
                    self._next_fleet_number += 1

                    fleet.start_building(
                        start_turn=self.state.turn.turn_number,
                        contract_id=contract.id,
                        build_time=build_time
                    )
                    built_fleets.append(fleet.number)

            self._construction_contracts[contract.id] = built_fleets[0] if built_fleets else None
            contract.remaining_years = build_time
            contract.duration_years = build_time

            self.state.log_event(
                f"舰队建造合同 {contract.id} 中标，开始建造 {len(built_fleets)} 艘舰队，实际强度比例 {cost_ratio:.2f}，预计 {build_time} 回合完工",
                extra={"contract_id": contract.id, "fleet_count": len(built_fleets)}
            )

    def process_fleet_construction(self, current_turn: int) -> List[int]:
        """
        检查所有建造中的舰队，完成已到期的舰队，并关联舰队合同标记为完成。
        返回已完成的舰队编号列表。
        """
        completed = []
        for fleet in list(self._fleets.values()):  # 使用 list 避免遍历时修改字典
            if fleet.is_building and fleet.build_end_turn == current_turn:
                # 先保存合同 ID，因为 complete_building 会将其清空
                contract_id = getattr(fleet, '_contract_id', None)

                # 记录建造完成前的状态
                self.state.log_event(
                    f"[DEBUG] 舰队 {fleet.number} 建造完成前: 状态={fleet.status.value}, 战力={fleet._strength_base}, 目标战争={fleet._target_war_id}",
                    level=logging.DEBUG,
                    extra={"fleet": fleet.number, "pre_status": fleet.status.value, "strength": fleet._strength_base}
                )

                # 完成建造（会清除 _contract_id）
                fleet.complete_building()

                self.state.log_event(
                    f"舰队 {fleet.number} 建造完成，实际战力 {fleet._strength_base}",
                    level=logging.INFO,
                    extra={
                        "type": "naval_construction_complete",
                        "fleet_number": fleet.number,
                        "strength": fleet._strength_base,
                        "target_war_id": fleet._target_war_id,
                    }
                )

                # 防御性检查：确保舰队在 _fleets 中
                if fleet.number not in self._fleets:
                    self.state.log_event(
                        f"警告: 舰队 {fleet.number} 不在 _fleets 中，重新添加",
                        level=logging.WARNING,
                        extra={"fleet": fleet.number}
                    )
                    self._fleets[fleet.number] = fleet

                # 查找关联的舰队合同，并标记完成（必须在 complete_building 之后，但使用之前保存的 contract_id）
                if contract_id:
                    contract = self.state.get_contract(contract_id)
                    if contract and getattr(contract, '_is_fleet_construction', False):
                        if contract.status != ContractStatus.COMPLETED:
                            contract.mark_complete(self.state.turn.turn_number)
                            self.state.log_event(
                                f"舰队合同竣工: {contract.name}",
                                level=logging.INFO,
                                extra={"contract_id": contract.id}
                            )
                        else:
                            self.state.log_event(
                                f"舰队合同 {contract_id} 已标记为完成，跳过",
                                level=logging.DEBUG
                            )
                    else:
                        self.state.log_event(
                            f"未找到关联的舰队合同: contract_id={contract_id}",
                            level=logging.WARNING
                        )

                # 处理战争指派（仅当舰队有目标战争时）
                if fleet._target_war_id:
                    war_system = self.state.get_war_system()
                    if war_system:
                        war = war_system.get_war_by_id(fleet._target_war_id)
                        if war and war.status.value == "active" and war.naval_required:
                            # 尝试指派，但不影响舰队可用性
                            success = self.assign_fleet_to_war(
                                fleet.number,
                                fleet._target_war_id,
                                "naval",
                                commander_id=None
                            )
                            if success:
                                self.state.log_event(
                                    f"舰队 {fleet.number} 已自动指派给战争 {war.name}",
                                    level=logging.INFO
                                )
                            else:
                                # 指派失败，舰队仍保持可用状态
                                self.state.log_event(
                                    f"舰队 {fleet.number} 自动指派失败，舰队保持可用状态",
                                    level=logging.WARNING,
                                    extra={"fleet": fleet.number, "war_id": war.id, "reason": "assign_failed"}
                                )
                        else:
                            # 战争不存在或不需要海战，舰队保持可用状态
                            self.state.log_event(
                                f"舰队 {fleet.number} 目标战争 {fleet._target_war_id} 未激活或无海战需求，舰队保持可用状态",
                                level=logging.INFO,
                                extra={"fleet": fleet.number, "target_war_id": fleet._target_war_id}
                            )
                    else:
                        self.state.log_event(
                            f"战争系统不可用，舰队 {fleet.number} 保持可用状态",
                            level=logging.WARNING
                        )
                else:
                    self.state.log_event(
                        f"舰队 {fleet.number} 没有目标战争，保持可用状态",
                        level=logging.DEBUG
                    )

                # 最终确认舰队状态
                self.state.log_event(
                    f"[DEBUG] 舰队 {fleet.number} 完成处理后: 状态={fleet.status.value}",
                    level=logging.DEBUG,
                    extra={"fleet": fleet.number, "final_status": fleet.status.value}
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

        # R-12（G1-12）：单战专属资产——已归属其他战争（_target_war_id != war_id）禁跨战复用
        # （_target_war_id is None = legacy/未归属 → 放行，防旧存档/测试舰队不可指派，D-3）
        if fleet._target_war_id not in (None, war_id):
            self.state.log_event(
                f"[DEBUG] assign_fleet_to_war 拒绝: 舰队 {fleet_id} 专属战争 {fleet._target_war_id}，禁跨战复用（R-12）",
                level=logging.DEBUG,
                extra={
                    "function": "assign_fleet_to_war",
                    "fleet_id": fleet_id,
                    "war_id": war_id,
                    "target_war_id": fleet._target_war_id,
                    "phase": "exit",
                    "success": False,
                    "reason": "cross_war_reuse_forbidden"
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

        # G1-20（H 件 §4）：Fleet 绑定 = War Commander（无独立海军指挥官）；
        # commander_id 缺省解析为 war.commander_id（None 时保持 None）
        if commander_id is None and war.commander_id is not None:
            commander_id = war.commander_id

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
            result = "DEFEAT"
            self.state.log_event(
                f"海战自动战败（无可用舰队）: {war.name}",
                extra={
                    "type": "naval_battle_defeat",
                    "war_id": war.id,
                    "result": result,
                    "roman_losses": 0,
                    "enemy_loss": 0,
                }
            )
            return result, {"roman_losses": 0, "enemy_loss": 0}

        roman_strength = sum(f.get_combat_strength(self.state) for f in roman_fleets)
        enemy_strength = war.enemy_naval_current
        # R1-G-01（WP-G-R1 v1.6 §2.1.6，S1）：naval-only override 消费点——强制结果跳过
        # random.randint + _simplified_crt；空/非法/缺省 → 正常随机。损耗 mutation
        # （_apply_naval_losses）与「无可用舰队自动 DEFEAT」分支原样保留（override 仅在
        # roman_fleets 非空且骰子路径处生效——「无舰队必败」既有规则不被覆盖，R-04 无第二 resolver）。
        override_raw = self.state.config.get("testing.force_naval_result", "")
        forced = _normalize_forced_naval_result(override_raw)
        if forced is not None:
            result = forced
        else:
            dice = random.randint(2, 12)
            total = dice + roman_strength - enemy_strength
            result = self._simplified_crt(dice, total, war)
        losses = self._apply_naval_losses(war, result, roman_fleets)

        # G1-16 / K 件 §7：制海权唯一 True 写入点（GC）——TRIUMPH/VICTORY 获控
        # （获控后同战未来战斗跳过海战，R-06）；False 清理 = clear_sea_control（GD 接线）
        if result in ("TRIUMPH", "VICTORY") and not war.sea_control_acquired:
            war._sea_control_acquired = True
            self.state.log_event(
                f"制海权获取: {war.name}（{result}）",
                extra={
                    "type": "sea_control_acquired",
                    "war_id": war.id,
                    "result": result,
                },
            )

        # 海战结果变体日志
        variant_map = {
            "TRIUMPH": "naval_battle_triumph",
            "VICTORY": "naval_battle_victory",
            "STALEMATE": "naval_battle_stalemate",
            "DEFEAT": "naval_battle_defeat",
            "DISASTER": "naval_battle_disaster",
        }
        variant_type = variant_map.get(result, "naval_battle_stalemate")
        self.state.log_event(
            f"海战结果: {war.name} -> {result}",
            extra={
                "type": variant_type,
                "war_id": war.id,
                "result": result,
                "roman_losses": losses,
                "enemy_loss": 0,
            }
        )

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
        应用海战损失，返回罗马损失舰队数（G1-10 冻结数学，D 件 §3）。

        TRIUMPH / VICTORY / STALEMATE → 0 损失
        DEFEAT    → random.sample(参战舰队, ceil(N/2)) 无放回 → DESTROYED（war.remove_fleet 同步）
        DISASTER  → 全部参战舰队 DESTROYED
        """
        losses = 0
        current_turn = self.state.turn.turn_number
        if result == "DISASTER":
            for fleet in roman_fleets:
                fleet.mark_destroyed(current_turn)
                war.remove_fleet(fleet.number)
            losses = len(roman_fleets)
        elif result == "DEFEAT":
            # G1-10：losses = ceil(N/2)（= N - N//2，G1-06 对齐）随机无放回（G1-05 精神）
            loss_count = len(roman_fleets) - len(roman_fleets) // 2
            casualties = random.sample(roman_fleets, loss_count)
            for fleet in casualties:
                fleet.mark_destroyed(current_turn)
                war.remove_fleet(fleet.number)
            losses = loss_count
        # STALEMATE / VICTORY / TRIUMPH → 0 损失（删除「STALEMATE 损 1」旧分支，§11.10）
        return losses

    # ---------- 维护与解散 ----------
    def calculate_maintenance(self) -> int:
        """计算所有活跃舰队的维护费总和（J 件 §5：排除 DISBANDED/BUILDING/DESTROYED）。

        G1-14：战争结束召回后 AVAILABLE 幸存者仍计维护（下个 Revenue 最后一次）；
        仅 DISBANDED 后不再产生维护。
        """
        total = 0
        for fleet in self._fleets.values():
            if fleet.status not in (FleetStatus.DESTROYED, FleetStatus.BUILDING, FleetStatus.DISBANDED):
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
                # R-11（G1-13）：正常行政退役走 disband() → DISBANDED，禁 mark_destroyed
                fleet.disband()
                disbanded.append(fleet.number)
                self.state.log_event(
                    f"舰队 {fleet.number} 已解散（根据决策器）",
                    level=logging.INFO,
                    extra={
                        "type": "naval_fleet_disbanded",
                        "fleet_number": fleet.number,
                        "reason": "decider",
                        "current_turn": current_turn,
                        "fleet_status": "disbanded",
                    }
                )
        return disbanded

    # ---------- 舰队恢复 ----------

    def generate_replacement_contracts(self, current_turn: int) -> List[Contract]:
        """为活跃海战战争按同战权威 deficit 生成补充舰队建造合同（G1-11 + R1-G-04 / D 件 §6，R-12）。

        Required = war.enemy_naval_current；Usable = Σ 同战完成舰队实际战力（_target_war_id ==
        war.id 且非 DESTROYED/BUILDING/DISBANDED）；Committed = committed_building（同战 BUILDING
        live fleets，ACTIVE 合同已物化容量权威）+ committed_pending（同战 PENDING/BUDGETED 合同
        按组成计未物化容量）；Deficit = Required - Usable - Committed；> 0 → 补 ceil(Deficit /
        base_strength)；否则无补充。禁跨战舰队满足 deficit（R-12）；禁 blanket skip（P1-02：
        旧二值守卫删除——ACTIVE 合同容量归 BUILDING 侧只计一次，折价 true deficit 可达）。
        """
        if not self._can_build_fleet():
            return []
        war_system = self.state.get_war_system()
        if not war_system:
            return []
        active_wars = war_system.get_active_wars()
        if not active_wars:
            return []

        contracts = []
        for war in active_wars:
            if not war.naval_required:
                continue

            # 获取敌方海军强度
            enemy_strength = war.enemy_naval_current
            if enemy_strength <= 0:
                continue

            # R1-G-04（WP-G-R1 v1.6 §2.4，P1-02 冻结 committed 去重模型）：防重复不再用
            # 二值守卫 blanket skip（旧 `_has_active_fleet_contract_for_war` skip 与
            # 「building_fleets → continue」均删除）——按权威 deficit 四要素精确计算：
            #   usable             = Σ 同战完成舰队（非 DESTROYED/BUILDING/DISBANDED）实际战力
            #   committed_building = Σ 同战 BUILDING live fleets 实际战力（ACTIVE 合同已物化
            #                        容量权威——含竞标折价后的真实强度；ACTIVE 不再按合同另计）
            #   committed_pending  = Σ 同战 PENDING/BUDGETED 舰队建造合同约定容量（未物化，
            #                        按合同组成 needed_ships × base_strength 计）
            #   deficit            = required - usable - committed_building - committed_pending
            # 同一容量只计一次（ACTIVE 合同容量归 BUILDING 侧，不叠加）；deficit <= 0 → 无新合同。
            default_type = self.state.config.get("economic_rules.default_fleet_type", "trireme")
            fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
            if default_type not in fleet_configs:
                continue
            base_strength = fleet_configs[default_type].get("strength_base", 3)
            build_cost_per_ship = fleet_configs[default_type].get("build_cost", 20)

            usable = sum(
                f.get_combat_strength(self.state)
                for f in self._fleets.values()
                if f._target_war_id == war.id
                and f.status not in (FleetStatus.DESTROYED, FleetStatus.BUILDING, FleetStatus.DISBANDED)
            )
            committed_building = sum(
                f.get_combat_strength(self.state)
                for f in self._fleets.values()
                if f._target_war_id == war.id and f.is_building
            )
            committed_pending = sum(
                _fleet_contract_nominal_strength(c, fleet_configs)
                for c in self.state.get_all_contracts()
                if getattr(c, "_target_war_id", None) == war.id
                and getattr(c, "_is_fleet_construction", False)
                and c.status in (ContractStatus.PENDING, ContractStatus.BUDGETED)
            )
            deficit = enemy_strength - usable - committed_building - committed_pending
            if deficit <= 0:
                continue

            # 计算所需补充舰队数量（向上取整 ceil(deficit/base)，G1-11）
            needed_ships = max(1, (deficit + base_strength - 1) // base_strength)

            total_budget = needed_ships * build_cost_per_ship
            composition = [{"type": default_type, "count": needed_ships}]

            # 创建合同
            contract = self.state.create_contract(
                contract_type=ContractType.PUBLIC_WORKS,
                province_id=0,
                base_cost=total_budget,
                current_turn=current_turn
            )
            # R1-G-04（WP-G-R1 v1.6 §7.12.2）：冻结原始预算不变量（同 generate_construction_contracts）
            contract._original_budget = total_budget
            contract._is_fleet_construction = True
            contract._target_war_id = war.id
            contract._fleet_type = default_type
            contract._build_time = fleet_configs[default_type].get("build_time", 1)
            contract.name = f"舰队建造（{war.name}）"
            contract._warranty_remaining = 0
            contract.set_fleet_composition(composition, enemy_strength, total_budget)
            contracts.append(contract)

            self.state.log_event(
                f"为激活战争生成补充舰队建造合同：{contract.name}，预算 {total_budget}，"
                f"需建造 {needed_ships} 艘 {default_type}（deficit {deficit} = target {enemy_strength} "
                f"- usable {usable} - building {committed_building} - pending {committed_pending}），工期 {contract._build_time} 年",
                extra={"contract_id": contract.id, "war_id": war.id, "deficit": deficit,
                       "target": enemy_strength, "existing": usable, "building": committed_building,
                       "pending": committed_pending, "needed_ships": needed_ships}
            )
        return contracts


    def apply_maintenance(self) -> Tuple[bool, str]:
        """扣除维护费，国库不足时尝试解散"""
        try:
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
                    # R-11（G1-13）：国库不足行政解散走 disband() → DISBANDED，禁 mark_destroyed
                    fleet.disband()
                    self.state.log_event(f"因国库不足，舰队 {fleet.name} 解散")
                # 重新计算维护费
                total = self.calculate_maintenance()
                if self.state.treasury < total:
                    return False, f"国库仍不足以支付舰队维护费，需要 {total}"

            self.state.treasury -= total
            return True, f"支付舰队维护费 {total}"
        except Exception as e:
            print(f"      ⚓ 舰队维护费计算异常: {e}")
            return False, "维护费计算失败"

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
