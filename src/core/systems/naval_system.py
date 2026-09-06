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
    """R1-G-04 + R3-G-04（§4.3）：PENDING/BUDGETED 舰队建造合同的未物化约定容量（nominal）。

    按合同组成（recommended_fleet_composition：needed_ships × nominal）推导——尚无 Fleet
    实体前其容量以合同组成计 committed_pending；无组成 → 0（无计划容量）。
    R3（P2-G3R3-02）：优先用 generation 时点 `_fleet_nominal_snapshot`（配置当前值与历史已
    确定 hull nominal 不能混用）；快照缺 type 时回退现场 fleet type config。
    """
    total = 0
    snapshot = getattr(contract, "_fleet_nominal_snapshot", None) or {}
    for item in contract.recommended_fleet_composition or []:
        ftype = item.get("type", "")
        count = int(item.get("count", 0) or 0)
        if count <= 0:
            continue
        if ftype in snapshot:
            total += count * int(snapshot[ftype])
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
        # R3-G-02（设计 §2.1/§2.3，FROZEN）：运行期维护结算证据（不持久）——逐次调用清零，
        # 不复用上次计数；_last_naval_maintenance 为本次 naval_maintenance 结构化 summary。
        self._last_maintenance_disbanded: int = 0
        self._last_naval_maintenance: Dict[str, Any] = {}

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
            # P2-G3R3-02：PENDING composition nominal 快照（generation 时点；见 §4.3）
            contract._fleet_nominal_snapshot = {default_type: base_strength}

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
        # R3-G-03（§3.3）：D 已由 place_bid 入队持久并经 resolve_forum 固化到
        # contract._actual_cost（正式字段化 Optional[int]；award 不重算）。legacy 缺键 → None
        # （旧路径兼容 fallback：不写 exact quality——舰队保持默认 q=1 语义，禁伪造历史）。
        # A = _original_budget 恒为 generator 冻结基线（Senate 不得改写；D/A quality 分母，§4.2）。
        actual_cost = contract._actual_cost
        original_budget = getattr(contract, '_original_budget', 0)
        quality_known = actual_cost is not None and original_budget > 0
        if not quality_known:
            # 兼容旧数据或手动出价未设置：不写 exact quality（默认 q=1；不伪造）
            self.state.log_event(
                f"舰队合同 {contract.id} 缺少实际成本或原始预算，跳过 quality 标注",
                level=logging.WARNING
            )

        # 获取舰队配置
        fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
        default_type = getattr(contract, "_fleet_type", "trireme")

        # R3-G-03（§3.6，FROZEN）：Fleet 在 award 以最终 build_time 为唯一 N 同步
        # _construction_years/duration/remaining_years 与 annual C//N、D//N（EconomicService
        # 按此年付 + 末期尾差 D-(N-1)*annual_cost 归并——总付款 C、总成本 D 守恒）。
        # Fleet 无质保契约（warranty_remaining=0 保持，不把公共工程质保重算值泄入）。
        build_time = getattr(contract, "_build_time", None) or 1
        contract._construction_years = build_time
        contract.duration_years = build_time
        contract.remaining_years = build_time
        if contract.contract_price and contract.contract_price > 0:
            contract._annual_income = contract.contract_price // build_time
        if contract._actual_cost is not None:
            contract._annual_cost = contract._actual_cost // build_time
        contract._warranty_years = 0
        contract._warranty_remaining = 0

        # 获取舰队组成建议
        composition = contract.recommended_fleet_composition
        if not composition:
            # 单舰队
            fleet_type = default_type
            config = fleet_configs.get(fleet_type, {})
            base_strength = config.get("strength_base", 3)

            fleet = Fleet(
                number=self._next_fleet_number,
                fleet_type=fleet_type,
                name=f"舰队 {self._next_fleet_number} ({fleet_type})"
            )
            # R3-G-04（§4.1/§4.2）：nominal 快照（当次 type config）+ exact q=D/A + package_id；
            # _strength_base = nominal 兼容镜像（禁 per-fleet round/clamp——Owner 选项 B）
            if quality_known:
                fleet.set_construction_quality(contract.id, actual_cost, original_budget, base_strength)
            else:
                fleet._strength_base = base_strength
            fleet._target_war_id = getattr(contract, "_target_war_id", None)
            self._fleets[self._next_fleet_number] = fleet
            self._next_fleet_number += 1

            fleet.start_building(
                start_turn=self.state.turn.turn_number,
                contract_id=contract.id,
                build_time=build_time
            )
            self._construction_contracts[contract.id] = fleet.number

            self.state.log_event(
                f"舰队建造合同 {contract.id} 中标，开始建造 {fleet.name}，nominal {base_strength}，"
                f"quality {actual_cost}/{original_budget}，预计 {build_time} 回合完工",
                extra={"fleet_number": fleet.number, "contract_id": contract.id}
            )
        else:
            # 多舰队：按组成建造多艘（同 package 共享同一 q=D/A——§4.2 数学前提）
            built_fleets = []
            for item in composition:
                fleet_type = item["type"]
                count = item["count"]
                config = fleet_configs.get(fleet_type, {})
                base_strength = config.get("strength_base", 3)

                for _i in range(count):
                    fleet = Fleet(
                        number=self._next_fleet_number,
                        fleet_type=fleet_type,
                        name=f"舰队 {self._next_fleet_number} ({fleet_type})"
                    )
                    if quality_known:
                        fleet.set_construction_quality(
                            contract.id, actual_cost, original_budget, base_strength)
                    else:
                        fleet._strength_base = base_strength
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

            self.state.log_event(
                f"舰队建造合同 {contract.id} 中标，开始建造 {len(built_fleets)} 艘舰队，"
                f"quality {actual_cost}/{original_budget}（nominal 快照逐舰），预计 {build_time} 回合完工",
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
                        # R3-G-04（§4.1/V04）：completion join 日志补原 contract/package_id
                        "contract_id": contract_id,
                        "construction_package_id": getattr(fleet, "_construction_package_id", None),
                        "final_status": fleet.status.value,
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

    # ---------- R3-G-04 strength aggregator（设计 §4.2 冻结主线） ----------
    def fleet_nominal(self, fleet: Fleet) -> Optional[int]:
        """Fleet nominal n（replacement/聚合消费）：R3 award 快照 `_nominal_strength_base`；
        legacy（缺快照、quality_source=legacy_baked）由同版 type config 派生；未知舰型 → None
        （不猜跨战归属，报告兼容限制）。配置当前值与历史已确定 hull nominal 不能混用
        （P2-G3R3-02）——快照存在时优先快照。"""
        if fleet._nominal_strength_base is not None:
            return fleet._nominal_strength_base
        fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
        if fleet._fleet_type in fleet_configs:
            return int(fleet_configs[fleet._fleet_type].get("strength_base", 3))
        return None

    def get_fleet_strength_breakdown(self, fleets: List[Fleet]) -> Dict[str, Any]:
        """只读聚合 helper（设计 §4.2 冻结主线，FROZEN）：对本次参与/存活集合按
        `_construction_package_id` 分组——逐 package raw（精确有理数 Fraction）→ upper-cap
        min(raw, 2×nominal_package) → round 一次（ties-to-even）→ 跨 package 求和。

        lower floor=1 已由 Owner 裁决（2026-09-05 19:41 选项 B）取消（无 per-fleet
        floor/clamp）；upper cap 保留并落 package 级（§4.2 已证明与逐舰 upper cap 等价）。
        D=0 → q=0 不 fallback。无 package 的 legacy entity 独立 group，保留其已烘焙 snapshot
        （旧 _strength_base），跨 package 绝不合并 raw/cap。

        modifiers：experience_bonus = Σ fleet.experience；commander_bonus = Σ 每 Fleet 一次
        martial（war commander 权威，原 source/加法次数保留——G1-20）。

        返回 {"nominal_total", "quality_adjusted_base", "experience_bonus",
        "commander_bonus", "effective_combat_strength", "fleet_strength_packages"}。
        本 helper 是 naval combat / DTO 读模型唯一 effective 权威（§4.2：禁 Σ
        per-fleet get_combat_strength 冒充）；replacement 消费 nominal（不消费本 helper）。
        """
        from fractions import Fraction
        packages: Dict[Any, Dict[str, Any]] = {}
        quality_adjusted_base = 0
        nominal_total = 0
        experience_bonus = 0
        commander_bonus = 0
        ws = self.state.get_war_system()

        for fleet in fleets:
            experience_bonus += fleet.experience
            # 每 Fleet 一次 martial（G1-20：war commander 权威；无指派/空 commander 回退私有绑定）
            commander_id = fleet._commander_id
            if ws and fleet.assigned_war_id:
                war = ws.get_war_by_id(fleet.assigned_war_id)
                if war is not None and war.commander_id is not None:
                    commander_id = war.commander_id
            if commander_id:
                commander = self.state.get_member(commander_id)
                if commander:
                    commander_bonus += commander.martial

            if fleet.has_exact_quality():
                nominal = fleet._nominal_strength_base if fleet._nominal_strength_base is not None \
                    else fleet._strength_base
                pkg = packages.get(fleet._construction_package_id)
                if pkg is None:
                    pkg = {
                        "package_id": fleet._construction_package_id,
                        "fleet_ids": [],
                        "nominal": 0,
                        # 同 package 共享同一 q=D/A（§4.2 数学前提：uniform q per contract）
                        "q": Fraction(fleet._construction_quality_numerator,
                                      fleet._construction_quality_denominator),
                    }
                    packages[fleet._construction_package_id] = pkg
                pkg["nominal"] += nominal
                pkg["fleet_ids"].append(fleet.number)
            else:
                # legacy/manual：独立 group，保留已烘焙 snapshot（= 其 effective base 贡献）
                quality_adjusted_base += fleet._strength_base
                nominal = self.fleet_nominal(fleet)
                if nominal is not None:
                    nominal_total += nominal

        fleet_strength_packages = []
        for pkg in packages.values():
            raw = Fraction(pkg["nominal"]) * pkg["q"]
            capped = min(raw, Fraction(2) * pkg["nominal"])   # upper cap（package 级保留）
            rounded = round(capped)                            # 唯一一次舍入
            quality_adjusted_base += rounded
            nominal_total += pkg["nominal"]
            fleet_strength_packages.append({
                "package_id": pkg["package_id"],
                "fleet_ids": sorted(pkg["fleet_ids"]),
                "nominal": pkg["nominal"],
                "q_numerator": pkg["q"].numerator,
                "q_denominator": pkg["q"].denominator,
                "raw": str(raw),
                "capped": str(capped),
                "rounded": rounded,
            })
        return {
            "nominal_total": nominal_total,
            "quality_adjusted_base": quality_adjusted_base,
            "experience_bonus": experience_bonus,
            "commander_bonus": commander_bonus,
            "effective_combat_strength": quality_adjusted_base + experience_bonus + commander_bonus,
            "fleet_strength_packages": fleet_strength_packages,
        }

    # ---------- 舰队指派 ----------
    def get_war_fleet_strength_read_model(self, war) -> Dict[str, Any]:
        """R3-G-04（§4.5，FROZEN）：per-war 舰队 strength 分层读模型——单一实现，供
        combat_api._war_card / gui_query_api._war_summary 同源消费（不重复实现/不漂移）。

        归属作用域 = war._assigned_fleet_ids（指派本战的编号）；计入状态集 = 显式
        status == ON_MISSION（live 实体；沿用 R1-G-08 显式集语义）。有效强度只对该战已完成
        已指派舰队聚合（NavalSystem.get_fleet_strength_breakdown）。count/readiness 语义
        不变（naval_ready = count>=1，**不可**改成 effective>=enemy 的 readiness 新规则）。
        聚合 evidence 带 fleet_strength_packages（package_id/q/ids/nominal/raw/capped/
        rounded）；不泄漏其他派系未公布的 bid。
        """
        assigned_ids = []
        for fid in (getattr(war, "_assigned_fleet_ids", None) or []):
            fleet = self.get_fleet(fid)
            if fleet is not None and fleet.status == FleetStatus.ON_MISSION:
                assigned_ids.append(fid)
        assigned_ids = sorted(assigned_ids)
        zero = {
            "assigned_fleet_ids": [],
            "fleet_nominal_strength": 0,
            "fleet_quality_adjusted_base": 0,
            "fleet_experience_bonus": 0,
            "fleet_commander_bonus": 0,
            "fleet_effective_combat_strength": 0,
            "fleet_strength_packages": [],
        }
        if not assigned_ids:
            return zero
        live = [self.get_fleet(fid) for fid in assigned_ids]
        bd = self.get_fleet_strength_breakdown(live)
        return {
            "assigned_fleet_ids": assigned_ids,
            "fleet_nominal_strength": bd["nominal_total"],
            "fleet_quality_adjusted_base": bd["quality_adjusted_base"],
            "fleet_experience_bonus": bd["experience_bonus"],
            "fleet_commander_bonus": bd["commander_bonus"],
            "fleet_effective_combat_strength": bd["effective_combat_strength"],
            "fleet_strength_packages": bd["fleet_strength_packages"],
        }

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

        roman_strength = self.get_fleet_strength_breakdown(roman_fleets)["effective_combat_strength"]
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
        """为活跃海战战争按同战 nominal 权威 deficit 生成补充舰队建造合同（R3-G-04 §4.3，FROZEN）。

        Required = war.enemy_naval_current；Usable = Σ 同战完成 live Fleets nominal
        （_target_war_id == war.id 且非 DESTROYED/BUILDING/DISBANDED，含 AVAILABLE/ON_MISSION/
        既有 IN_COMBAT——不以是否有 Commander 决定 hull 存不存在）；Committed_building = Σ 同战
        BUILDING live fleets nominal（ACTIVE 合同容量只经物化 BUILDING 表示，绝不再叠加合同
        composition）；Committed_pending = Σ 同战 PENDING/BUDGETED 合同 composition nominal
        快照（未物化，禁 get_combat_strength/martial/experience/quality——quality 降不授权补
        hull，R3-06）；Deficit = Required - Usable - Building - Pending；> 0 →
        needed = ceil(Deficit / default_type nominal)；否则无补充。每舰 ID/合同 ID 去重；
        target_war 必须匹配；None 不计新战争。
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

            default_type = self.state.config.get("economic_rules.default_fleet_type", "trireme")
            fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
            if default_type not in fleet_configs:
                continue
            base_strength = fleet_configs[default_type].get("strength_base", 3)
            build_cost_per_ship = fleet_configs[default_type].get("build_cost", 20)

            usable = 0
            usable_ids = set()
            for f in self._fleets.values():
                if f._target_war_id != war.id:
                    continue
                if f.status in (FleetStatus.DESTROYED, FleetStatus.BUILDING, FleetStatus.DISBANDED):
                    continue
                n = self.fleet_nominal(f)
                if n is None:
                    continue
                usable += n
                usable_ids.add(f.number)
            committed_building = 0
            building_ids = set()
            for f in self._fleets.values():
                if f._target_war_id == war.id and f.is_building:
                    n = self.fleet_nominal(f)
                    if n is None:
                        continue
                    committed_building += n
                    building_ids.add(f.number)
            committed_pending = 0
            for c in self.state.get_all_contracts():
                if getattr(c, "_target_war_id", None) != war.id:
                    continue
                if not getattr(c, "_is_fleet_construction", False):
                    continue
                if c.status not in (ContractStatus.PENDING, ContractStatus.BUDGETED):
                    continue
                committed_pending += _fleet_contract_nominal_strength(c, fleet_configs)
            deficit = enemy_strength - usable - committed_building - committed_pending
            if deficit <= 0:
                continue

            # 计算所需补充舰队数量（向上取整 ceil(deficit/nominal)，G1-11）
            needed_ships = max(1, (deficit + base_strength - 1) // base_strength)

            total_budget = needed_ships * build_cost_per_ship
            composition = [{"type": default_type, "count": needed_ships}]

            # 创建合同（PENDING；A/B 未批准态/target/composition/nominal 快照一次写入——
            # 再生成调用应看到 PENDING commitment 而返回 0，§4.3）
            contract = self.state.create_contract(
                contract_type=ContractType.PUBLIC_WORKS,
                province_id=0,
                base_cost=total_budget,
                current_turn=current_turn
            )
            contract._original_budget = total_budget
            contract._is_fleet_construction = True
            contract._target_war_id = war.id
            contract._fleet_type = default_type
            contract._build_time = fleet_configs[default_type].get("build_time", 1)
            contract.name = f"舰队建造（{war.name}）"
            contract._warranty_remaining = 0
            # P2-G3R3-02：PENDING composition nominal 快照（配置当前值与历史已确定 hull nominal
            # 不能混用——未物化容量用 generation 时点的快照）
            contract._fleet_nominal_snapshot = {default_type: base_strength}
            contract.set_fleet_composition(composition, enemy_strength, total_budget)
            contracts.append(contract)

            self.state.log_event(
                f"为激活战争生成补充舰队建造合同：{contract.name}，预算 {total_budget}，"
                f"需建造 {needed_ships} 艘 {default_type}（nominal deficit {deficit} = target "
                f"{enemy_strength} - usable {usable}{sorted(usable_ids)} - building "
                f"{committed_building}{sorted(building_ids)} - pending {committed_pending}），"
                f"工期 {contract._build_time} 年",
                extra={"contract_id": contract.id, "war_id": war.id, "deficit": deficit,
                       "target": enemy_strength, "existing": usable, "building": committed_building,
                       "pending": committed_pending, "needed_ships": needed_ships}
            )
        return contracts


    def apply_maintenance(self) -> Tuple[bool, str]:
        """扣除舰队维护费（R3-G-02 设计 §2.1/§2.2，FROZEN）。

        正常 / 零维护 / 短款解散后支付 / 失败四出口均产生同一 `naval_maintenance` 结构化
        summary（self._last_naval_maintenance + log_event type=naval_maintenance，字段见
        §2.3）；逐次调用入口清零 `_last_maintenance_disbanded` 与 summary，不复用上次计数。

        短款算法（§2.2 冻结）：initial_due = Σ eligible 费用（Fleet.status ∉
        {BUILDING, DESTROYED, DISBANDED}——含 AVAILABLE/ON_MISSION/既有 IN_COMBAT）；
        candidates = 既有 AVAILABLE 序 + 其余 maintenance-bearing 既有序（稳定遍历，不随机、
        不按战力重排、不引入 AI 策略）；for fleet in candidates: if treasury >=
        remaining_due: break（先查后拆，break-before-add 修正）→ 记 assigned war + target
        war + status + unit cost → 若 assigned war 存在先清该 war assignment index →
        fleet.disband()（非 mark_destroyed，R-11）→ remaining_due -= unit_cost（含“恰好
        足够”的最后一艘）→ recompute_due = calculate_maintenance() 对账；不足 → 既有失败
        策略（MVP0.5-04 §5.6，不移植 military 可负国库强扣）：charge 0 + 失败证据；
        否则 treasury -= recompute_due。每艘成功短款退役恰一条 naval_fleet_disbanded 事件
        （fleet_number/war_id/target_war_id/reason=treasury_shortfall/current_turn/
        fleet_status=disbanded）。
        """
        # R3-G-02（§2.1）：入口清零，防 total==0 早退/上次计数复用
        self._last_maintenance_disbanded = 0
        summary: Dict[str, Any] = {
            "available": True,
            "total": 0,
            "charged": 0,
            "shortfall": 0,
            "initial_shortfall": 0,
            "unpaid": 0,
            "disbanded": 0,
            "disbanded_fleet_ids": [],
            "fleet_costs": [],
            "eligible_fleet_ids": [],
            "required_after_disband": 0,
            "treasury_before": self.state.treasury,
            "treasury_after": self.state.treasury,
            "success": True,
            "message": "",
        }
        self._last_naval_maintenance = summary
        try:
            # maintenance-bearing 全状态集（§2.1：不缩成 AVAILABLE）
            eligible = [
                f for f in self._fleets.values()
                if f.status not in (FleetStatus.DESTROYED, FleetStatus.BUILDING, FleetStatus.DISBANDED)
            ]
            summary["eligible_fleet_ids"] = sorted(f.number for f in eligible)
            initial_due = sum(f.get_maintenance_cost(self.state) for f in eligible)
            summary["total"] = initial_due
            treasury_before = self.state.treasury
            summary["treasury_before"] = treasury_before
            summary["initial_shortfall"] = max(0, initial_due - max(treasury_before, 0))

            if initial_due == 0:
                # 零维护出口：不扣款，结构化 summary + 事件（不静默）
                summary["treasury_after"] = treasury_before
                summary["message"] = "无需支付舰队维护费"
                self._last_naval_maintenance = summary
                self._log_naval_maintenance(summary)
                return True, summary["message"]

            if treasury_before >= initial_due:
                # 足额正常出口：全扣（charged = initial_due）
                self.state.treasury -= initial_due
                summary["charged"] = initial_due
                summary["required_after_disband"] = initial_due
                summary["treasury_after"] = self.state.treasury
                summary["message"] = f"支付舰队维护费 {initial_due}"
                self._last_naval_maintenance = summary
                self._log_naval_maintenance(summary)
                return True, summary["message"]

            # 短款出口（§2.2 冻结算法）：候选 = AVAILABLE 序 + 其余 maintenance-bearing 序
            remaining_due = initial_due
            available = [f for f in self._fleets.values() if f.status == FleetStatus.AVAILABLE]
            other_bearing = [
                f for f in self._fleets.values()
                if f.status != FleetStatus.AVAILABLE
                and f.status not in (FleetStatus.DESTROYED, FleetStatus.BUILDING, FleetStatus.DISBANDED)
            ]
            candidates = available + other_bearing
            disbanded_ids: List[int] = []
            fleet_costs: List[Dict[str, Any]] = []
            for fleet in candidates:
                if treasury_before >= remaining_due:
                    break
                unit_cost = fleet.get_maintenance_cost(self.state)
                war_id = fleet.assigned_war_id
                target_war_id = fleet._target_war_id
                status_before = fleet.status.value if hasattr(fleet.status, "value") else str(fleet.status)
                # 对 ON_MISSION 行政解散：先清 War assignment index（entity binding 由 disband 清，
                # 保留 _target_war_id provenance；后续真 hull loss 致 nominal deficit 是合法补充）
                if war_id:
                    ws = self.state.get_war_system()
                    if ws:
                        war = ws.get_war_by_id(war_id)
                        if war is not None:
                            war.remove_fleet(fleet.number)
                fleet.disband()                  # 非 mark_destroyed（R-11 / G1-13）
                remaining_due -= unit_cost       # 含“恰好足够”的最后一艘
                disbanded_ids.append(fleet.number)
                self._last_maintenance_disbanded += 1
                fleet_costs.append({
                    "fleet_number": fleet.number,
                    "fleet_type": fleet.fleet_type,
                    "target_war": target_war_id,
                    "war_id": war_id,
                    "status_before": status_before,
                    "unit_cost": unit_cost,
                })
                current_turn = self.state.turn.turn_number if self.state.turn else 0
                self.state.log_event(
                    f"因国库不足，舰队 {fleet.name} 解散",
                    extra={
                        "type": "naval_fleet_disbanded",
                        "fleet_number": fleet.number,
                        "war_id": war_id,
                        "target_war_id": target_war_id,
                        "reason": "treasury_shortfall",
                        "current_turn": current_turn,
                        "fleet_status": "disbanded",
                    },
                )
            summary["disbanded"] = self._last_maintenance_disbanded
            summary["disbanded_fleet_ids"] = disbanded_ids
            summary["fleet_costs"] = fleet_costs
            # 重算对账（冻结不变量：recompute_due == remaining_due）
            recompute_due = self.calculate_maintenance()
            summary["required_after_disband"] = recompute_due
            if recompute_due != remaining_due:
                self.state.log_event(
                    f"舰队维护费对账不一致: recompute={recompute_due} remaining={remaining_due}",
                    level=logging.WARNING,
                    extra={"type": "naval_maintenance_reconcile_mismatch",
                           "recompute": recompute_due, "remaining": remaining_due},
                )
            if treasury_before < recompute_due:
                # 失败出口（MVP0.5-04 §5.6：解散后仍不足 → 失败保留；不移植负国库强扣）
                summary["unpaid"] = recompute_due - 0
                summary["success"] = False
                summary["message"] = f"国库仍不足以支付舰队维护费，需要 {recompute_due}"
                summary["treasury_after"] = treasury_before
                self._last_naval_maintenance = summary
                self._log_naval_maintenance(summary)
                return False, summary["message"]
            # 短款解散后支付出口
            self.state.treasury -= recompute_due
            summary["charged"] = recompute_due
            summary["treasury_after"] = self.state.treasury
            summary["message"] = f"支付舰队维护费 {recompute_due}"
            if summary["disbanded"]:
                summary["message"] += f"（解散 {summary['disbanded']} 艘）"
            self._last_naval_maintenance = summary
            self._log_naval_maintenance(summary)
            return True, summary["message"]
        except Exception as e:
            print(f"      ⚓ 舰队维护费计算异常: {e}")
            summary["success"] = False
            summary["message"] = "维护费计算失败"
            self._last_naval_maintenance = summary
            return False, "维护费计算失败"

    def _log_naval_maintenance(self, summary: Dict[str, Any]) -> None:
        """R3-G-02（§2.3）：naval_maintenance 结构化事件（turn/phase=revenue/全字段）。"""
        current_turn = self.state.turn.turn_number if self.state.turn else 0
        self.state.log_event(
            f"舰队维护费结算: 应扣 {summary['total']} 实扣 {summary['charged']} "
            f"缺口 {summary['shortfall']} 退役 {summary['disbanded']}",
            extra={
                "type": "naval_maintenance",
                "turn": current_turn,
                "phase": "revenue",
                "eligible_fleet_ids": summary.get("eligible_fleet_ids", []),
                "fleet_costs": summary.get("fleet_costs", []),
                "total": summary.get("total", 0),
                "required_after_disband": summary.get("required_after_disband", 0),
                "charged": summary.get("charged", 0),
                "shortfall": summary.get("shortfall", 0),
                "initial_shortfall": summary.get("initial_shortfall", 0),
                "unpaid": summary.get("unpaid", 0),
                "disbanded_fleet_ids": summary.get("disbanded_fleet_ids", []),
                "treasury_before": summary.get("treasury_before", 0),
                "treasury_after": summary.get("treasury_after", 0),
                "success": summary.get("success", False),
            },
        )

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "_fleets": {num: fleet.to_dict() for num, fleet in self._fleets.items()},
            "_next_fleet_number": self._next_fleet_number,
            "_construction_contracts": self._construction_contracts.copy(),
        }

    def load_from_dict(self, data: dict):
        self._fleets = {}
        # R3-G-04（§4.1）：Fleet.from_dict 提供配置上下文（legacy nominal 派生）
        fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
        for num, fleet_data in data.get("_fleets", {}).items():
            self._fleets[int(num)] = Fleet.from_dict(fleet_data, fleet_configs=fleet_configs)
        self._next_fleet_number = data.get("_next_fleet_number", 1)
        self._construction_contracts = data.get("_construction_contracts", {}).copy()
