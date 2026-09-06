# src/core/entities/fleet.py
from enum import Enum
from typing import Optional, Dict, Any, List


class FleetStatus(Enum):
    BUILDING = "building"       # 建造中（合同已签，未完工）
    AVAILABLE = "available"      # 可用
    ON_MISSION = "on_mission"    # 执行任务中
    IN_COMBAT = "in_combat"      # 战斗中
    DESTROYED = "destroyed"      # 被摧毁（仅战斗伤亡，G1-13）
    DISBANDED = "disbanded"      # 行政退役（正常退役/国库解散，G1-13 / J 件 §1）


class Fleet:
    """舰队实体"""

    def __init__(
        self,
        number: int,
        name: str = "",
        fleet_type: str = "trireme",   # 舰队类型，如 trireme, quinquereme
    ):
        self._number = number
        self._name = name or f"Fleet {number}"
        self._fleet_type = fleet_type
        self._status = FleetStatus.BUILDING  # 默认为建造中
        self._commander_id: Optional[int] = None
        self._experience: int = 0
        self._strength_base: int = 3          # 从配置读取，初始化后根据类型设置
        self._is_veteran: bool = False
        self._assigned_war_id: Optional[str] = None
        self._assigned_mission_type: Optional[str] = None
        self._location_zone_id: Optional[int] = None
        self._destroyed_turn: int = 0
        # 建造相关
        self._build_start_turn: Optional[int] = None
        self._build_end_turn: Optional[int] = None
        self._contract_id: Optional[int] = None   # 关联的建造合同ID（complete_building 清空）
        self._target_war_id: Optional[str] = None  # 关联的战争ID（用于建造后自动指派）
        # R3-G-04（设计 §4.1，FROZEN）：nominal/quality/package 持久字段
        #   nominal base：award 当次 type config 快照（不受 quality/experience/martial 影响）
        self._nominal_strength_base: Optional[int] = None
        #   quality q = D/A 精确整数比（numerator=D / denominator=A；None = 未经合同调整/legacy）
        self._construction_quality_numerator: Optional[int] = None
        self._construction_quality_denominator: Optional[int] = None
        #   package 身份 = 建造合同 id（完工后保留——与 complete_building 清 _contract_id 不同）
        self._construction_package_id: Optional[int] = None
        #   quality 来源诚实标注：None（exact 或默认 q=1） / "legacy_baked"（旧存档已烘焙 effective，
        #   不声称能还原原始 240/280，§4.1/§3.2）
        self._quality_source: Optional[str] = None

    @property
    def target_war_id(self) -> Optional[str]:
        return self._target_war_id

    # === R3-G-04（§4.1）nominal/quality/package 访问器 ===
    @property
    def nominal_strength_base(self) -> Optional[int]:
        """Nominal type base n（award 当次 type config 快照；None = legacy 未知舰型/未归属）。"""
        return self._nominal_strength_base

    @property
    def construction_quality_numerator(self) -> Optional[int]:
        return self._construction_quality_numerator

    @property
    def construction_quality_denominator(self) -> Optional[int]:
        return self._construction_quality_denominator

    @property
    def construction_package_id(self) -> Optional[int]:
        return self._construction_package_id

    @property
    def quality_source(self) -> Optional[str]:
        return self._quality_source

    def has_exact_quality(self) -> bool:
        """exact quality：package 身份 + D/A 均持久（R3 award 物化产物）。"""
        return (
            self._construction_package_id is not None
            and self._construction_quality_numerator is not None
            and self._construction_quality_denominator is not None
            and (self._construction_quality_denominator or 0) > 0
        )

    def set_construction_quality(self, package_id: int, numerator: int, denominator: int,
                                 nominal_base: int):
        """R3-G-04（§4.1）：award 物化时写入 exact quality（D/A）+ nominal 快照 + package_id。

        _strength_base 同步为 nominal 兼容镜像（n）——不可供 replacement/GUI 假称 effective
        （§4.2：唯一 effective 权威 = NavalSystem.get_fleet_strength_breakdown）。
        """
        self._construction_package_id = package_id
        self._construction_quality_numerator = numerator
        self._construction_quality_denominator = denominator
        self._nominal_strength_base = nominal_base
        self._strength_base = nominal_base  # nominal 兼容镜像
        self._quality_source = None

    @property
    def quality_adjusted_base(self) -> int:
        """纯派生（不另存可独立写的 effective ledger；§4.1）。

        exact-package fleet：其 package 的有效贡献只能经 NavalSystem aggregator 计算（raw→
        cap→round 为 package 级一次）；单舰查询无权威值 → 返回本舰 raw share 的 rounded 值作
        兼容展示（不供战斗/补船消费）。legacy/manual fleet：已烘焙 _strength_base snapshot。
        """
        if self.has_exact_quality():
            from fractions import Fraction
            n = self._nominal_strength_base or self._strength_base
            q = Fraction(self._construction_quality_numerator, self._construction_quality_denominator)
            return round(min(Fraction(n) * q, Fraction(2) * n))
        return self._strength_base

    # 属性访问器
    @property
    def number(self) -> int:
        return self._number

    @property
    def name(self) -> str:
        return self._name

    @property
    def fleet_type(self) -> str:
        return self._fleet_type

    @property
    def status(self) -> FleetStatus:
        return self._status

    @property
    def commander_id(self) -> Optional[int]:
        return self._commander_id

    @commander_id.setter
    def commander_id(self, value: Optional[int]):
        """Fleet 指挥官绑定 setter（G2-WP-G-H §5 / Q 件 E：GA rebind 原语消费；GC 派生 martial）。

        仅维护 _commander_id 收敛 War Commander（G1-20/R-14）；不触碰 _assigned_war_id
        （单战归属持久归 GC）。
        """
        self._commander_id = value

    @property
    def experience(self) -> int:
        return self._experience

    @property
    def is_veteran(self) -> bool:
        return self._is_veteran

    @property
    def assigned_war_id(self) -> Optional[str]:
        return self._assigned_war_id

    @property
    def destroyed_turn(self) -> int:
        return self._destroyed_turn

    @property
    def build_start_turn(self) -> Optional[int]:
        return self._build_start_turn

    @property
    def build_end_turn(self) -> Optional[int]:
        return self._build_end_turn

    @property
    def contract_id(self) -> Optional[int]:
        return self._contract_id

    @property
    def is_building(self) -> bool:
        return self._status == FleetStatus.BUILDING

    # 从配置加载基础战力
    def set_strength_from_config(self, config: dict):
        self._strength_base = config.get("strength_base", 3)

    def get_combat_strength(self, state) -> int:
        """计算舰队战力（基础 + 经验 + 指挥官 martial）。

        G1-20（H 件 §4）：martial 权威 = War Commander（war.commander_id）——
        Fleet._commander_id 为绑定镜像/兼容；无指派（AVAILABLE staging）或
        war.commander_id 为空时回退舰队私有绑定。

        R3-G-04（§4.2，FROZEN）supersession：本方法 = **兼容单舰查询**——exact-package 舰队的
        权威 effective 只能经 `NavalSystem.get_fleet_strength_breakdown` 的 package 级 raw→cap→
        round 计算（无 per-fleet round/clamp）；单舰返回未聚合 raw share 的 rounded 值 + 原
        modifiers，**任何生产消费（resolve_naval_battle / generate_replacement_contracts /
        DTO）不得 Σ 本方法冒充 effective**（该三处已定向改用 aggregator/nominal）。
        """
        strength = self.quality_adjusted_base + self._experience
        commander_id = self._commander_id
        ws = getattr(state, "get_war_system", lambda: None)()
        if ws and self._assigned_war_id:
            war = ws.get_war_by_id(self._assigned_war_id)
            if war is not None and war.commander_id is not None:
                commander_id = war.commander_id  # 权威 = War Commander（G1-20）
        if commander_id:
            commander = state.get_member(commander_id)
            if commander:
                strength += commander.martial  # 使用 martial 作为海战加成
        return strength

    def get_maintenance_cost(self, state) -> int:
        """获取维护费（从配置读取）"""
        fleet_config = state.config.get("economic_rules.fleet_types", {}).get(self._fleet_type, {})
        return fleet_config.get("maintenance_cost", 5)

    def assign_to_war(self, war_id: str, mission_type: str, commander_id: Optional[int] = None):
        if self._status != FleetStatus.AVAILABLE:
            return False
        self._assigned_war_id = war_id
        self._assigned_mission_type = mission_type
        self._commander_id = commander_id
        self._status = FleetStatus.ON_MISSION
        return True

    def recall(self):
        self._assigned_war_id = None
        self._assigned_mission_type = None
        self._commander_id = None
        self._status = FleetStatus.AVAILABLE

    def start_building(self, start_turn: int, contract_id: int, build_time: int):
        """开始建造"""
        self._status = FleetStatus.BUILDING
        self._build_start_turn = start_turn
        self._build_end_turn = start_turn + build_time
        self._contract_id = contract_id

    def complete_building(self):
        """建造完成"""
        self._status = FleetStatus.AVAILABLE
        self._build_start_turn = None
        self._build_end_turn = None
        self._contract_id = None

    def mark_destroyed(self, current_turn: int):
        self._status = FleetStatus.DESTROYED
        self._destroyed_turn = current_turn
        self._is_veteran = False
        self._experience = 0
        self._commander_id = None
        self._assigned_war_id = None

    def disband(self):
        """行政退役（G1-13）：正常退役专用，非战斗伤亡（R-11）。

        与 legion.disband 语义对齐：不清 is_veteran/experience（行政退役非伤亡）；
        保留 _target_war_id（单战归属 provenance 持久，G1-12）；DISBANDED 为终端态不可复用。
        """
        self._status = FleetStatus.DISBANDED
        self._commander_id = None
        self._assigned_war_id = None
        self._assigned_mission_type = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "_number": self._number,
            "_name": self._name,
            "_fleet_type": self._fleet_type,
            "_status": self._status.value,
            "_commander_id": self._commander_id,
            "_experience": self._experience,
            "_strength_base": self._strength_base,
            "_is_veteran": self._is_veteran,
            "_assigned_war_id": self._assigned_war_id,
            "_assigned_mission_type": self._assigned_mission_type,
            "_location_zone_id": self._location_zone_id,
            "_destroyed_turn": self._destroyed_turn,
            "_build_start_turn": self._build_start_turn,
            "_build_end_turn": self._build_end_turn,
            "_contract_id": self._contract_id,
            "_target_war_id": self._target_war_id,
            # R3-G-04（§4.1/§4.2）：nominal/q/package 持久（round-trip 无损）
            "_nominal_strength_base": self._nominal_strength_base,
            "_construction_quality_numerator": self._construction_quality_numerator,
            "_construction_quality_denominator": self._construction_quality_denominator,
            "_construction_package_id": self._construction_package_id,
            "_quality_source": self._quality_source,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any], fleet_configs: Optional[Dict[str, Any]] = None) -> "Fleet":
        """R3-G-04（§4.1，FROZEN）：Fleet deserializer（fleet_configs 可选——legacy 缺新字段时
        由所绑定版本 fleet type config 建 nominal；NavalSystem.load_from_dict 提供配置上下文）。

        旧 Fleet：缺新字段时旧 `_strength_base` 是已经舍入的 effective，不可直接称 nominal——
        已保存 target/type 明确时由同版 type config 建 nominal（快照），保留旧 effective 值作
        legacy effective snapshot；quality 不可证明 → `_quality_source=legacy_baked`（不声称能
        还原原始 240/280）。未知舰型 → nominal=None（不猜，报告兼容限制）。缺省不创造 target
        （禁 load 后变跨战无主容量）。新数据必须无损。
        """
        fleet = Fleet(data["_number"], data.get("_name", ""), data.get("_fleet_type", "trireme"))
        fleet._status = FleetStatus(data["_status"])
        fleet._commander_id = data.get("_commander_id")
        fleet._experience = data.get("_experience", 0)
        fleet._strength_base = data.get("_strength_base", 3)
        fleet._is_veteran = data.get("_is_veteran", False)
        fleet._assigned_war_id = data.get("_assigned_war_id")
        fleet._assigned_mission_type = data.get("_assigned_mission_type")
        fleet._location_zone_id = data.get("_location_zone_id")
        fleet._destroyed_turn = data.get("_destroyed_turn", 0)
        fleet._build_start_turn = data.get("_build_start_turn")
        fleet._build_end_turn = data.get("_build_end_turn")
        fleet._contract_id = data.get("_contract_id")
        # O 件 §3：单战归属 provenance 持久（G1-12）；旧存档缺键 → None
        fleet._target_war_id = data.get("_target_war_id")
        if "_nominal_strength_base" in data:
            # 新格式：直读无损
            fleet._nominal_strength_base = data.get("_nominal_strength_base")
            fleet._construction_quality_numerator = data.get("_construction_quality_numerator")
            fleet._construction_quality_denominator = data.get("_construction_quality_denominator")
            fleet._construction_package_id = data.get("_construction_package_id")
            fleet._quality_source = data.get("_quality_source")
        else:
            # legacy 格式：旧 _strength_base = 已舍入 effective（保留为 snapshot）
            fleet._quality_source = "legacy_baked"
            if fleet_configs and fleet._fleet_type in fleet_configs:
                fleet._nominal_strength_base = int(
                    fleet_configs[fleet._fleet_type].get("strength_base", 3))
            # 未知舰型 → nominal=None（兼容限制报告，不猜跨战归属）
        return fleet