# src/core/entities/war.py

from typing import List, Optional, Dict, Any,Tuple
from enum import Enum
import copy
import math


# EOR20261009-03（FC-16/§5.1；ATTEMPT-3 R01）：权威 commit receipt 的**单一**校验器。
# 同时被 `WarSystem.resolve_war`（生成时）与 `combat_api._reward_view`（DTO 读取时）调用，
# 保证"committed = 有效完整 receipt 且 committed==True"的唯一定义（FC-06/FC-16）。
# fail-closed：任一 schema/war_id/类型/组合/守恒不满足 → False（调用方不得以此 receipt 宣称 committed）。
_RECEIPT_TOP_KEYS = (
    "schema_version", "war_id", "result", "result_identity_source", "result_multiplier",
    "base_snapshot", "total_monetary", "treasury_part", "faction_part", "commander_part",
    "pool_part", "faction_target", "land", "family_prestige", "influence_granted",
    "committed", "identity_capture", "actual_recipients",
)
_RECEIPT_BASE_KEYS = ("treasury", "land", "family_prestige", "influence")
_RECEIPT_IDENTITY_KEYS = (
    "commander_id_at_commit", "office_at_commit", "faction_id_at_commit",
    "shares_effective", "config_version",
)
_RECEIPT_SHARE_KEYS = ("treasury", "faction", "commander", "soldier")
_RECEIPT_ACTUAL_KEYS = (
    "treasury_delta", "faction_delta", "commander_delta",
    "faction_id", "commander_id", "pool_held",
)
_RECEIPT_SHARE_SUM_TOLERANCE = 1e-9

# EOR20261009-03（ATTEMPT-4 R01/F01）：持久化（JSON）可承载的回执值形状。
# 一个「present」的 receipt 若属于这些形状却不是合法 dict receipt，必须在读模型
# fail-closed；opaque 的内存 sentinel（如测试 mock）不是持久值，保持「缺席」语义。
_PERSISTED_RECEIPT_TYPES = (dict, list, str, int, float, bool)


def is_persisted_receipt_shape(receipt: Any) -> bool:
    """True 当且仅当 receipt 是持久化层可承载的值（JSON scalar/container），
    即一个候选持久回执。内存 opaque 对象（mock 等）返回 False。"""
    return isinstance(receipt, _PERSISTED_RECEIPT_TYPES)


def receipt_present_and_invalid(receipt: Any, war_id: str) -> bool:
    """present-but-invalid 判定（读模型 fail-closed 前置）：
    存在（非 None）的持久形状 receipt 但未通过 `validate_reward_receipt` → True。
    None 或 opaque sentinel → False（视为缺席，保持 legacy 语义）。
    """
    if receipt is None or not is_persisted_receipt_shape(receipt):
        return False
    return not validate_reward_receipt(receipt, war_id)


def _is_nonneg_int(v: Any) -> bool:
    """整数、非 bool、非负（Python 中 bool 是 int 子类，必须显式排除）。"""
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _is_finite_share(v: Any) -> bool:
    """有限数值、非 bool、∈ [0,1]（NaN/Inf/bool/字符串一律 False）。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    fv = float(v)
    return math.isfinite(fv) and 0.0 <= fv <= 1.0


def validate_reward_receipt(receipt: Any, war_id: str) -> bool:
    """校验权威 commit receipt（FC-16/§5.1）。返回 True 当且仅当 receipt 完整有效。

    覆盖：顶层键集合 / schema_version==1 / war_id 相符 / committed is True /
    result↔(source,multiplier) 组合 / base_snapshot 四键非负 int /
    整数 parts 非 bool 非负且 sum(parts)==total_monetary / identity_capture 五键类型 /
    shares_effective 四键 finite 非 bool ∈[0,1] 且 sum≈1.0 / actual_recipients 六键
    且 delta 非负 int 且 sum==total_monetary / faction_target 枚举。
    """
    try:
        if not isinstance(receipt, dict):
            return False
        if set(receipt.keys()) != set(_RECEIPT_TOP_KEYS):
            return False
        # EOR20261009-03（ATTEMPT-4 R01/F01.3）：schema_version 必须是非 bool 整数且 ==1
        # （Python 中 `True == 1`，旧的 `!= 1` 比较会错误接受 bool）。
        if not _is_nonneg_int(receipt.get("schema_version")) \
                or receipt.get("schema_version") != 1:
            return False
        if receipt.get("war_id") != war_id:
            return False
        if receipt.get("committed") is not True:
            return False

        # result ↔ (identity_source, multiplier) 组合（非独立成员检查）
        result = receipt.get("result")
        source = receipt.get("result_identity_source")
        multiplier = receipt.get("result_multiplier")
        # EOR20261009-03（ATTEMPT-4 R01/F01.3）：乘子必须是非 bool 数值（`True == 1.0` 会
        # 错误通过 victory 乘子检查）。
        if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
            return False
        if result == "triumph":
            if multiplier != 1.5 or source != "explicit_crt":
                return False
        elif result == "victory":
            if multiplier != 1.0 or source not in ("explicit_crt", "legacy_unspecified"):
                return False
        else:
            return False

        if receipt.get("faction_target") not in ("faction", "treasury"):
            return False

        # 金额整数（非 bool 非负）
        for key in ("total_monetary", "treasury_part", "faction_part", "commander_part",
                    "pool_part", "land", "family_prestige", "influence_granted"):
            if not _is_nonneg_int(receipt.get(key)):
                return False
        if (receipt["treasury_part"] + receipt["faction_part"]
                + receipt["commander_part"] + receipt["pool_part"]) != receipt["total_monetary"]:
            return False

        # base_snapshot：完整四键 + 非负 int
        base = receipt.get("base_snapshot")
        if not isinstance(base, dict) or set(base.keys()) != set(_RECEIPT_BASE_KEYS):
            return False
        for key in _RECEIPT_BASE_KEYS:
            if not _is_nonneg_int(base[key]):
                return False

        # identity_capture：五键 + 类型
        ic = receipt.get("identity_capture")
        if not isinstance(ic, dict) or set(ic.keys()) != set(_RECEIPT_IDENTITY_KEYS):
            return False
        cid = ic.get("commander_id_at_commit")
        if cid is not None and not _is_nonneg_int(cid):
            return False
        office = ic.get("office_at_commit")
        if office is not None and not isinstance(office, str):
            return False
        fid = ic.get("faction_id_at_commit")
        if fid is not None and not isinstance(fid, str):
            return False
        if not isinstance(ic.get("config_version"), str):
            return False
        shares_eff = ic.get("shares_effective")
        if not isinstance(shares_eff, dict) or set(shares_eff.keys()) != set(_RECEIPT_SHARE_KEYS):
            return False
        for key in _RECEIPT_SHARE_KEYS:
            if not _is_finite_share(shares_eff[key]):
                return False
        if abs(sum(float(shares_eff[k]) for k in _RECEIPT_SHARE_KEYS) - 1.0) > _RECEIPT_SHARE_SUM_TOLERANCE:
            return False

        # actual_recipients：六键 + delta 非负 int + 守恒
        ar = receipt.get("actual_recipients")
        if not isinstance(ar, dict) or set(ar.keys()) != set(_RECEIPT_ACTUAL_KEYS):
            return False
        for key in ("treasury_delta", "faction_delta", "commander_delta", "pool_held"):
            if not _is_nonneg_int(ar[key]):
                return False
        if (ar["treasury_delta"] + ar["faction_delta"] + ar["commander_delta"]
                + ar["pool_held"]) != receipt["total_monetary"]:
            return False
        ar_cid = ar.get("commander_id")
        if ar_cid is not None and not _is_nonneg_int(ar_cid):
            return False
        ar_fid = ar.get("faction_id")
        if ar_fid is not None and not isinstance(ar_fid, str):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


class WarStatus(Enum):
    INACTIVE = "inactive"
    THREAT = "threat"
    ACTIVE = "active"
    TRUCE = "truce"
    RESOLVED = "resolved"
    DEFEATED = "defeated"

class WarType(Enum):
    BARBARIAN = "barbarian"
    FOREIGN = "foreign"
    PROVINCIAL = "provincial"
    CIVIL = "civil"

class War:
    """战争实体"""

    def __init__(
            self,
            id: str,
            name: str,
            description: str = "",
            war_type: WarType = WarType.FOREIGN,
            start_year: int = 0,
            threat_level: int = 0,
            auto_escalate: bool = True,
            escalate_rate: int = 1,
            strength: int = 5,
            naval_support_required: bool = False,
            naval_strength: int = 0,
            land_battle: bool = True,
            disaster_numbers: List[int] = None,
            standoff_numbers: List[int] = None,
            rewards: Dict[str, int] = None,
            penalties: Dict[str, int] = None,
            is_imminent: bool = False,
            matched_war_id: Optional[str] = None,
            # ---------- MVP 0.7-2 新增 ----------
            unlocked_provinces: List[int] = None,
            # ---------- MVP 0.7-4 新增 ----------
            naval_required: bool = False,
            enemy_naval_current: int = 0,
            enemy_naval_max: int = 0,
            enemy_land_current: int = 0,
            enemy_land_max: int = 0,
            enemy_budget_initial: int = 0,
            enemy_recovery_per_turn: int = 0,
            enemy_maintenance_cost_per_unit: int = 0,
            sea_zone_id: Optional[int] = None,
            mission_type: str = "JOINT_INVASION",
            rebellion_province_id: Optional[int] = None,
            # ---------- MVP 0.7 战斗统计预留 ----------
            battles_fought: int = 0,
            battles_won: int = 0,
    ):
        self._id = id
        self._name = name
        self._description = description
        self._war_type = war_type
        self._start_year = start_year
        self._threat_level = threat_level
        self._auto_escalate = auto_escalate
        self._escalate_rate = escalate_rate
        self._strength = strength
        self._naval_support_required = naval_support_required
        self._naval_strength = naval_strength
        self._land_battle = land_battle
        self._disaster_numbers = disaster_numbers or [2, 3, 4]
        self._standoff_numbers = standoff_numbers or [5, 6, 7, 8, 9]
        self._rewards = rewards or {}
        self._penalties = penalties or {}
        self._is_imminent = is_imminent
        self._matched_war_id = matched_war_id

        # 运行时字段
        self._status = WarStatus.INACTIVE
        self._commander_id: Optional[int] = None
        self._legions_assigned: int = 0
        self._fleets_assigned: int = 0
        self._activation_turn: Optional[int] = None
        self._duration: int = 0
        self._commander_status: str = "active"
        self._soldier_share: int = 0
        self._triumph_commander_id: Optional[int] = None
        self._triumph_approved: bool = False
        # EOR20261009-03（FC-16）：权威 commit receipt（唯一 committed 权威）。
        # None = 未结算；dict = 有效完整 receipt（含 committed=True）。持久键 = reward_receipt。
        self._reward_receipt: Optional[Dict[str, Any]] = None
        self._original_commander_id: Optional[int] = None
        self._commander_assigned_turn: Optional[int] = None
        self._peace_treaty: Optional[Dict] = None
        self._indemnity_due: int = 0
        self._truce_end_turn: Optional[int] = None
        self._legion_numbers: List[int] = []
        self._combat_slot_index: int = -1  # 战斗槽位身份（-1 = 未分配）
        # R5（SA §2.1/§2.2，DA-1）：War lifecycle activation-origin 事实。
        # None = 尚未成为真实战争；真实战缺记载来源由 describe_senate_war 判为 legacy_unknown。
        # 与当会期 classification 分离；取值 active_declaration/passive_declaration/
        # other_existing/legacy_unknown。唯一写入者 = WarSystem 激活/威胁升级 owner。
        self._activation_origin: Optional[str] = None
        self._activation_episode: int = 0
        self._declared_by: Optional[int] = None

        # ---------- MVP 0.7-2 新增 ----------
        self._unlocked_provinces = unlocked_provinces or []

        # ---------- MVP 0.7-4 新增字段 ----------
        self._naval_required = naval_required
        self._enemy_naval_current = enemy_naval_current
        self._enemy_naval_max = enemy_naval_max
        self._enemy_land_current = enemy_land_current
        self._enemy_land_max = enemy_land_max
        self._enemy_budget_initial = enemy_budget_initial
        self._enemy_budget_remaining = enemy_budget_initial  # 初始值与预算相同
        self._enemy_recovery_per_turn = enemy_recovery_per_turn
        self._enemy_maintenance_cost_per_unit = enemy_maintenance_cost_per_unit
        self._sea_zone_id = sea_zone_id
        self._mission_type = mission_type
        self._rebellion_province_id = rebellion_province_id

        # 以下字段没有参数传入，直接初始化为默认值
        self._assigned_fleet_ids: List[int] = []  # 我方指派舰队编号
        self._unanswered_turns: int = 0  # 连续未应战回合数
        self._indemnity_schedule: List[Tuple[int, int]] = []  # 战争赔款分期
        # 历史残留字段（N 件 §2）：默认 1.0 会造成「未获控却看似获控」误读——
        # 禁以 _sea_control_ratio 判定获控状态（K 件 §1）；权威字段 = _sea_control_acquired。
        self._sea_control_ratio: float = 1.0  # 当前制海权比例（dormant，仅存档兼容）
        # 权威制海权（G1-16 / K 件）：唯一获控判定源，唯一 mutation owner = GC
        # （resolve_naval_battle TRIUMPH/VICTORY 写 True；clear_sea_control 随战争正式结束写 False，接线 = GD）
        self._sea_control_acquired: bool = False
        self._battles_fought = battles_fought
        self._battles_won = battles_won
        self._triggered_this_turn = False  # 标记本回合是否刚被激活为威胁



    # ---------- 属性访问器 ----------

    @property
    def battles_fought(self) -> int:
        return self._battles_fought

    @property
    def battles_won(self) -> int:
        return self._battles_won

    # ---------- MVP 0.7-4 新增字段开始----------
    @property
    def naval_required(self) -> bool: return self._naval_required
    @property
    def enemy_naval_current(self) -> int: return self._enemy_naval_current
    @property
    def assigned_fleet_ids(self) -> List[int]: return self._assigned_fleet_ids.copy()
    @property
    def sea_zone_id(self) -> Optional[int]: return self._sea_zone_id
    @property
    def unanswered_turns(self) -> int: return self._unanswered_turns
    @property
    def indemnity_schedule(self) -> List[Tuple[int, int]]: return self._indemnity_schedule.copy()
    @property
    def sea_control_ratio(self) -> float: return self._sea_control_ratio
    @property
    def sea_control_acquired(self) -> bool:
        """权威制海权状态（G1-16 / K 件）——唯一判定源，替代 _sea_control_ratio。"""
        return self._sea_control_acquired
    @property
    def rebellion_province_id(self) -> Optional[int]: return self._rebellion_province_id

    # ---------- MVP 0.7-4 新增字段结束 ----------

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def war_type(self) -> WarType:
        return self._war_type

    @property
    def start_year(self) -> int:
        return self._start_year

    @property
    def threat_level(self) -> int:
        return self._threat_level

    @threat_level.setter
    def threat_level(self, value: int):
        self._threat_level = value

    @property
    def auto_escalate(self) -> bool:
        return self._auto_escalate

    @property
    def escalate_rate(self) -> int:
        return self._escalate_rate

    @property
    def strength(self) -> int:
        return self._strength

    @property
    def naval_support_required(self) -> bool:
        return self._naval_support_required

    @property
    def naval_strength(self) -> int:
        return self._naval_strength

    @property
    def land_battle(self) -> bool:
        return self._land_battle

    @property
    def disaster_numbers(self) -> List[int]:
        return self._disaster_numbers

    @property
    def standoff_numbers(self) -> List[int]:
        return self._standoff_numbers

    @property
    def rewards(self) -> Dict[str, int]:
        return self._rewards.copy()

    @property
    def penalties(self) -> Dict[str, int]:
        return self._penalties.copy()

    @property
    def is_imminent(self) -> bool:
        return self._is_imminent

    @property
    def matched_war_id(self) -> Optional[str]:
        return self._matched_war_id

    @property
    def status(self) -> WarStatus:
        return self._status

    @status.setter
    def status(self, value: WarStatus):
        self._status = value

    @property
    def commander_id(self) -> Optional[int]:
        return self._commander_id

    @commander_id.setter
    def commander_id(self, value: Optional[int]):
        self._commander_id = value

    @property
    def legions_assigned(self) -> int:
        return self._legions_assigned

    @legions_assigned.setter
    def legions_assigned(self, value: int):
        self._legions_assigned = value

    @property
    def fleets_assigned(self) -> int:
        return self._fleets_assigned

    @fleets_assigned.setter
    def fleets_assigned(self, value: int):
        self._fleets_assigned = value

    @property
    def activation_turn(self) -> Optional[int]:
        return self._activation_turn

    @activation_turn.setter
    def activation_turn(self, value: Optional[int]):
        self._activation_turn = value

    @property
    def duration(self) -> int:
        return self._duration

    @duration.setter
    def duration(self, value: int):
        self._duration = value

    @property
    def commander_status(self) -> str:
        return self._commander_status

    @property
    def soldier_share(self) -> int:
        return self._soldier_share

    @property
    def veteran_support_pool(self) -> int:
        """EOR20261009-03（FC-15/OD-04）：veteran support pool 域概念名——
        与兼容别名 soldier_share 同底层存储（不另存第二个金额键）。"""
        return self._soldier_share

    @property
    def reward_receipt(self) -> Optional[Dict[str, Any]]:
        """EOR20261009-03（FC-16）：权威 commit receipt（只读，含 present-but-malformed）。"""
        return self._reward_receipt

    def set_reward_receipt(self, receipt: Optional[Dict[str, Any]]) -> None:
        """设置权威 commit receipt（唯一写入者 = WarSystem.resolve_war）。"""
        self._reward_receipt = receipt

    def has_valid_receipt(self) -> bool:
        """FC-16/§5.1：receipt present 且通过完整校验（fail-closed）。

        `committed` 唯一权威 = 该值（**不得**仅凭 result 资格置 True）；present-but-invalid
        receipt 返回 False → DTO/守卫按 history_unrecorded 处理，不崩溃、不补发。
        """
        return validate_reward_receipt(self._reward_receipt, self._id)

    @property
    def triumph_commander_id(self) -> Optional[int]:
        return self._triumph_commander_id

    @property
    def triumph_approved(self) -> bool:
        return self._triumph_approved

    @property
    def original_commander_id(self) -> Optional[int]:
        return self._original_commander_id

    @property
    def commander_assigned_turn(self) -> Optional[int]:
        return self._commander_assigned_turn

    @property
    def peace_treaty(self) -> Optional[Dict]:
        return self._peace_treaty

    @property
    def indemnity_due(self) -> int:
        return self._indemnity_due

    @property
    def truce_end_turn(self) -> Optional[int]:
        return self._truce_end_turn

    @property
    def legion_numbers(self) -> List[int]:
        return self._legion_numbers.copy()

    @property
    def combat_slot_index(self) -> int:
        return self._combat_slot_index

    # ---------- R5 activation-origin 事实（DA-1）----------
    @property
    def activation_origin(self) -> Optional[str]:
        return self._activation_origin

    @property
    def activation_episode(self) -> int:
        return self._activation_episode

    @property
    def declared_by(self) -> Optional[int]:
        return self._declared_by

    @declared_by.setter
    def declared_by(self, value: Optional[int]):
        self._declared_by = value

    def set_activation_origin(self, origin: str, episode: Optional[int] = None) -> None:
        """记载当前战争激活 episode 的来源事实（仅 WarSystem 调用）。"""
        self._activation_origin = origin
        if episode is not None:
            self._activation_episode = episode
        else:
            self._activation_episode = self._activation_episode + 1

    @combat_slot_index.setter
    def combat_slot_index(self, value: int):
        self._combat_slot_index = value


    # ---------- MVP 0.7-2 新增属性 ----------
    @property
    def unlocked_provinces(self) -> List[int]:
        """返回战争胜利后解锁的行省ID列表（只读副本）。"""
        return self._unlocked_provinces.copy()

    # ---------- 公共方法 ----------
    def get_total_strength(self) -> int:
        """获取敌国总战力（含海军）。"""
        total = self._strength
        if self._naval_support_required:
            total += self._naval_strength
        return total

    def is_disaster_roll(self, dice: int) -> bool:
        return dice in self._disaster_numbers

    def is_standoff_roll(self, dice: int) -> bool:
        return dice in self._standoff_numbers

    def calculate_rewards(self) -> Dict[str, int]:
        return self._rewards.copy()

    def apply_penalties(self, state) -> List[str]:
        # 简化实现，实际应引用 GameState
        return []

    def set_soldier_share(self, amount: int):
        self._soldier_share = amount

    def set_triumph_commander(self, commander_id: int):
        self._triumph_commander_id = commander_id

    def set_triumph_approved(self, approved: bool):
        self._triumph_approved = approved

    def set_original_commander(self, commander_id: int, assigned_turn: int):
        self._original_commander_id = commander_id
        self._commander_assigned_turn = assigned_turn

    def clear_original_commander(self) -> None:
        """清除返回指针 original_commander_id（FC-03；仅匹配死者时由 WarSystem 调用）。

        窄方法：只清返回指针，**不重置** commander_assigned_turn（存活替补的指派回合
        保留）。不触碰 current/legion/fleet 或其他历史身份。
        """
        self._original_commander_id = None

    def reset_commander_status_to_active(self) -> None:
        """显式成功指派存活指挥官后恢复既有值 active（FC-03/B4）。

        `killed` = 该次阵亡指挥的 command 终止标记，**非** War 永久属性；重入本身不清，
        仅显式成功 command 绑定（存活 Figure）时复位。
        """
        self._commander_status = "active"

    def set_peace_treaty(self, treaty: Dict):
        """设置和约，若未指定 status 则默认为 'pending'"""
        if 'status' not in treaty:
            treaty['status'] = 'pending'
        self._peace_treaty = treaty

    def set_peace_treaty_status(self, status: str):
        if self._peace_treaty:
            self._peace_treaty["status"] = status

    def set_indemnity_due(self, amount: int):
        self._indemnity_due = amount

    def set_truce_end_turn(self, turn: int):
        self._truce_end_turn = turn

    def clear_peace_treaty(self):
        self._peace_treaty = None

    def add_legion_number(self, legion_num: int):
        if legion_num not in self._legion_numbers:
            self._legion_numbers.append(legion_num)

    def clear_legion_numbers(self):
        self._legion_numbers.clear()

    def report_commander_casualty(self, status: str, turn: int):
        self._commander_status = status
        # 记录阵亡回合等（可扩展）

    def set_commander_assigned_turn(self, turn: int):
        """设置指挥官指派回合（用于人口阶段官职转换）"""
        self._commander_assigned_turn = turn

    def assign_commander(self, commander_id: int, legions: int = 0):
        """指派指挥官（供测试使用，实际指派通过 WarSystem）"""
        self._commander_id = commander_id
        self._legions_assigned = legions
        # 可选：记录指派回合
        # self._commander_assigned_turn = current_turn

    def is_truce_expired(self, current_turn: int) -> bool:
        """判断停战是否到期（G3C 恢复：当前回合 >= truce_end_turn 即到期）。"""
        return self._truce_end_turn is not None and current_turn >= self._truce_end_turn

    # ---------- MVP 0.7-4 新增方法开始----------

    def assign_fleet(self, fleet_id: int) -> None:
        if fleet_id not in self._assigned_fleet_ids:
            self._assigned_fleet_ids.append(fleet_id)

    def remove_fleet(self, fleet_id: int) -> None:
        if fleet_id in self._assigned_fleet_ids:
            self._assigned_fleet_ids.remove(fleet_id)

    def clear_sea_control(self) -> None:
        """清理制海权（K 件 §3 / D-1）：战争正式结束时由 GD 接线调用，置回未获控。

        唯一写 False 的原语（True 唯一写入点 = GC resolve_naval_battle TRIUMPH/VICTORY 分支）。
        战争 RESOLVED 后 flag 天然 inert；GD 集成前无人调用。
        """
        self._sea_control_acquired = False

    def apply_naval_losses(self, result: str, fleet_ids: List[int], enemy_naval_loss: int) -> None:
        """应用海战损失（当前版本占位）"""
        # 具体实现留空，仅保留接口
        pass

    def apply_land_losses(self, result: str, legion_numbers: List[int], enemy_land_loss: int) -> None:
        """应用陆战损失（当前版本占位）"""
        pass

    def increment_unanswered_turns(self) -> None:
        self._unanswered_turns += 1

    def reset_unanswered_turns(self) -> None:
        self._unanswered_turns = 0

    def process_enemy_reinforcements(self, state) -> None:
        """处理敌军增援（预留，当前版本留空）"""
        pass

    def set_indemnity_schedule(self, schedule: List[Tuple[int, int]]) -> None:
        self._indemnity_schedule = schedule

    # ---------- MVP 0.7-4 新增方法结束----------


    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        """将战争对象转换为字典，用于存档。"""
        data = {
            "id": self._id,
            "name": self._name,
            "description": self._description,
            "war_type": self._war_type.value,
            "start_year": self._start_year,
            "threat_level": self._threat_level,
            "auto_escalate": self._auto_escalate,
            "escalate_rate": self._escalate_rate,
            "strength": self._strength,
            "naval_support_required": self._naval_support_required,
            "naval_strength": self._naval_strength,
            "land_battle": self._land_battle,
            "disaster_numbers": self._disaster_numbers.copy(),
            "standoff_numbers": self._standoff_numbers.copy(),
            "rewards": self._rewards.copy(),
            "penalties": self._penalties.copy(),
            "is_imminent": self._is_imminent,
            "matched_war_id": self._matched_war_id,
            "status": self._status.value,
            "commander_id": self._commander_id,
            "legions_assigned": self._legions_assigned,
            "fleets_assigned": self._fleets_assigned,
            "activation_turn": self._activation_turn,
            "duration": self._duration,
            "commander_status": self._commander_status,
            "soldier_share": self._soldier_share,
            "triumph_commander_id": self._triumph_commander_id,
            "triumph_approved": self._triumph_approved,
            # EOR20261009-03（ATTEMPT-3 R01）：present-but-malformed / 空 dict 也原键保留
            # （`is not None`；不再把 falsy {} 塌缩为 None），保留 raw-present 诊断区分。
            "reward_receipt": copy.deepcopy(self._reward_receipt) if self._reward_receipt is not None else None,
            "original_commander_id": self._original_commander_id,
            "commander_assigned_turn": self._commander_assigned_turn,
            "peace_treaty": self._peace_treaty.copy() if self._peace_treaty else None,
            "indemnity_due": self._indemnity_due,
            "truce_end_turn": self._truce_end_turn,
            "legion_numbers": self._legion_numbers.copy(),
            "combat_slot_index": self._combat_slot_index,
            "activation_origin": self._activation_origin,
            "activation_episode": self._activation_episode,
            "declared_by": self._declared_by,
            # MVP 0.7-2 新增
            "unlocked_provinces": self._unlocked_provinces.copy(),

            # MVP 0.7-4 战争系统新增
            "_naval_required": self._naval_required,
            "_enemy_naval_current": self._enemy_naval_current,
            "_assigned_fleet_ids": self._assigned_fleet_ids.copy(),
            "_sea_zone_id": self._sea_zone_id,
            "_enemy_naval_max": self._enemy_naval_max,
            "_enemy_land_current": self._enemy_land_current,
            "_enemy_land_max": self._enemy_land_max,
            "_enemy_budget_initial": self._enemy_budget_initial,
            "_enemy_budget_remaining": self._enemy_budget_remaining,
            "_enemy_recovery_per_turn": self._enemy_recovery_per_turn,
            "_enemy_maintenance_cost_per_unit": self._enemy_maintenance_cost_per_unit,
            "_mission_type": self._mission_type,
            "_unanswered_turns": self._unanswered_turns,
            "_indemnity_schedule": self._indemnity_schedule.copy(),
            "_sea_control_ratio": self._sea_control_ratio,
            "_sea_control_acquired": self._sea_control_acquired,
            "_rebellion_province_id": self._rebellion_province_id,
            "_battles_fought": self._battles_fought,
            "_battles_won": self._battles_won,
            "_triggered_this_turn":self._triggered_this_turn,
        }
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "War":
        """从字典重建战争对象。"""
        # 处理枚举
        war_type = WarType(data.get("war_type", "foreign"))
        status = WarStatus(data.get("status", "inactive"))

        war = War(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            war_type=war_type,
            start_year=data.get("start_year", 0),
            threat_level=data.get("threat_level", 0),
            auto_escalate=data.get("auto_escalate", True),
            escalate_rate=data.get("escalate_rate", 1),
            strength=data.get("strength", 5),
            naval_support_required=data.get("naval_support_required", False),
            naval_strength=data.get("naval_strength", 0),
            land_battle=data.get("land_battle", True),
            disaster_numbers=data.get("disaster_numbers"),
            standoff_numbers=data.get("standoff_numbers"),
            rewards=data.get("rewards"),
            penalties=data.get("penalties"),
            is_imminent=data.get("is_imminent", False),
            matched_war_id=data.get("matched_war_id"),
            unlocked_provinces=data.get("unlocked_provinces", []),
        )

        # 设置运行时字段
        war._status = status
        war._commander_id = data.get("commander_id")
        war._legions_assigned = data.get("legions_assigned", 0)
        war._fleets_assigned = data.get("fleets_assigned", 0)
        war._activation_turn = data.get("activation_turn")
        war._duration = data.get("duration", 0)
        war._commander_status = data.get("commander_status", "active")
        war._soldier_share = data.get("soldier_share", 0)
        war._triumph_commander_id = data.get("triumph_commander_id")
        war._triumph_approved = data.get("triumph_approved", False)
        # EOR20261009-03（FC-10/FC-16；ATTEMPT-3 R01）：receipt 原键逐字恢复（旧档缺键 → None）。
        # present-but-malformed / 空 dict {} 亦保留（`is not None`）——committed 有效性由
        # `validate_reward_receipt` 判定（DTO/守卫 fail-closed），不在 load 期静默补默认。
        receipt = data.get("reward_receipt")
        war._reward_receipt = copy.deepcopy(receipt) if receipt is not None else None
        war._original_commander_id = data.get("original_commander_id")
        war._commander_assigned_turn = data.get("commander_assigned_turn")
        war._peace_treaty = data.get("peace_treaty")
        war._indemnity_due = data.get("indemnity_due", 0)
        war._truce_end_turn = data.get("truce_end_turn")
        war._legion_numbers = data.get("legion_numbers", [])
        war._combat_slot_index = data.get("combat_slot_index", -1)
        # R5：旧存档缺键 → None（真实战由 describe_senate_war 判 legacy_unknown；不虚构历史起源）
        war._activation_origin = data.get("activation_origin")
        war._activation_episode = data.get("activation_episode", 0)
        war._declared_by = data.get("declared_by")

        # MVP 0.7-4 设置新增字段
        war._naval_required = data.get("_naval_required", False)
        war._enemy_naval_current = data.get("_enemy_naval_current", 0)
        war._assigned_fleet_ids = data.get("_assigned_fleet_ids", []).copy()
        war._sea_zone_id = data.get("_sea_zone_id")
        war._enemy_naval_max = data.get("_enemy_naval_max", 0)
        war._enemy_land_current = data.get("_enemy_land_current", 0)
        war._enemy_land_max = data.get("_enemy_land_max", 0)
        war._enemy_budget_initial = data.get("_enemy_budget_initial", 0)
        war._enemy_budget_remaining = data.get("_enemy_budget_remaining", 0)
        war._enemy_recovery_per_turn = data.get("_enemy_recovery_per_turn", 0)
        war._enemy_maintenance_cost_per_unit = data.get("_enemy_maintenance_cost_per_unit", 0)
        war._mission_type = data.get("_mission_type", "JOINT_INVASION")
        war._unanswered_turns = data.get("_unanswered_turns", 0)
        war._indemnity_schedule = data.get("_indemnity_schedule", [])
        war._sea_control_ratio = data.get("_sea_control_ratio", 1.0)
        # O 件 §3 退化路径：旧存档缺键 / None → False（is not None 容错；禁以 _sea_control_ratio 映射）
        acquired = data.get("_sea_control_acquired")
        war._sea_control_acquired = acquired is True
        war._rebellion_province_id = data.get("_rebellion_province_id")

        war._battles_fought = data.get("_battles_fought", 0)
        war._battles_won = data.get("_battles_won", 0)
        war._triggered_this_turn = data.get("_triggered_this_turn", False)

        return war