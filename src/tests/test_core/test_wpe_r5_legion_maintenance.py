# src/tests/test_core/test_wpe_r5_legion_maintenance.py
"""WP-E-R5 — 军团维护费短款修复（先裁军后透支，赤字兜底）10 用例。

覆盖 SA §C/G 矩阵：足额全扣 / 短款先裁后扣（真实 savings）/ 短款无候选扣负 /
国库 0 / 负值遗留 / 无军团早退 + ODR-1 重置 / 老兵不解散 / 战争军团不解散 /
破产联动 smoke / DTO 重建一致性。显式配置防生产 config 漂移（base=8）。
"""
from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.legion import LegionStatus
from src.core.systems.military_system import MilitarySystem
from src.core.systems.war_system import WarSystem
from src.core.service.economic_service import EconomicService

# 显式 economic rules（与生产 game_config 对齐：base=8 / vet+1 / recruit=4 / stipend=5 / 破产上限 3）
_R5_ECON_CONFIG = {"economic_rules": {
    "legion_maintenance_base": 8,
    "veteran_maintenance_bonus": 1,
    "legion_recruit_cost": 4,
    "faction_stipend": 5,
    "national_opex_deficit_limit": 3,
    "initial_national_public_land": 0,
}}


def _make_state():
    """create_for_testing 状态 + 显式挂载军事/战争系统（该工厂不创建系统实例）。"""
    s = GameState.create_for_testing(_R5_ECON_CONFIG)
    s.turn = GameTurn(turn_number=5, year=-260)
    s._military_system = MilitarySystem(s)
    s._war_system = WarSystem(s)
    return s


def _recruit(s, nums):
    """走权威链 recruit_legion（treasury 需 ≥ 4×N）。"""
    ms = s.get_military_system()
    for n in nums:
        ok, msg = ms.recruit_legion(n)
        assert ok, f"recruit legion {n}: {msg}"


def _assign_war(s, nums, war_id="w1"):
    """战争指派（简化路径，DA-Plan §C.1 授权）：legion.assign_to_war 直接设 war_id。"""
    ms = s.get_military_system()
    for n in nums:
        legion = ms.get_legion_by_number(n)
        assert legion.assign_to_war(war_id, commander_id=1), f"assign legion {n}"


def _settle(s):
    result = EconomicService(s).settle_revenue_phase()
    assert result["success"], f"Settlement failed: {result}"
    return result["data"]


def _log_msgs(s):
    return list(s._event_log)


def _maintenance_log(s):
    """返回最近一条军团维护费结算日志消息（含 extra 字段则拼接）。"""
    for msg in reversed(_log_msgs(s)):
        if "军团维护费" in msg:
            return msg
    return None


# ─── T-R5-01 足额全扣 ─────────────────────────────────────────────────────

def test_charged_full_when_sufficient():
    s = _make_state()
    s.treasury = 500  # 征召费 4×3
    _recruit(s, [1, 2, 3])  # 3 × base 8 = 24
    s.treasury = 500  # 场景国库（征召费已扣，随后显式设值）
    ms = s.get_military_system()

    ok, msg = ms.apply_maintenance(verbose=True)

    assert ok is True
    assert "Paid 24" in msg
    assert s.treasury == 476
    assert ms._last_maintenance_disbanded == 0
    # 同源断言：charged == before − after
    charged = 500 - s.treasury
    assert charged == 24
    log = _maintenance_log(s)
    assert log is not None
    assert "应扣 24 实扣 24 缺口 0 解散 0" in log
    assert any("legion_maintenance" in m for m in _log_msgs(s)) or "军团维护费" in log


# ─── T-R5-02 短款先裁后扣（真实 savings 回归防护）────────────────────────

def test_shortfall_disband_then_charge():
    """treasury=40, 10×未指派（total=80）→ 短款 40 → 解散 5（5×8=40 真实 savings）
    → total_after=40 → charged=40 → treasury=0 → shortfall=0。
    旧逻辑 savings+=2 需解散 20 个（候选仅 10）必失败——本用例即回归防护。"""
    s = _make_state()
    s.treasury = 500
    _recruit(s, list(range(1, 11)))  # 征召费 4×10=40
    s.treasury = 40  # 场景国库
    ms = s.get_military_system()

    ok, _msg = ms.apply_maintenance(verbose=False)

    assert ok is True
    assert ms._last_maintenance_disbanded == 5
    assert ms.calculate_maintenance()[0] == 40  # 5 个仍 ACTIVE
    assert s.treasury == 0
    assert "解散 5" in _maintenance_log(s)
    assert "实扣 40" in _maintenance_log(s)
    assert "缺口 0" in _maintenance_log(s)
    # 解散的 5 个军团状态 = DISBANDED
    disbanded = [l for l in ms.get_all_legions() if l.status == LegionStatus.DISBANDED]
    assert len(disbanded) == 5


# ─── T-R5-03 短款无候选扣负（T6 对齐）────────────────────────────────────

def test_shortfall_no_candidate_overdraft():
    """treasury=131, 20×全战争指派（total=160）→ 候选空 → disbanded=0 → charged=160
    → treasury=-29 → shortfall=29。"""
    s = _make_state()
    s.treasury = 500
    _recruit(s, list(range(1, 21)))
    _assign_war(s, list(range(1, 21)))
    s.treasury = 131
    ms = s.get_military_system()

    ok, msg = ms.apply_maintenance(verbose=True)

    assert ok is True
    assert ms._last_maintenance_disbanded == 0
    assert s.treasury == -29
    assert "缺口 29" in msg
    log = _maintenance_log(s)
    assert "应扣 160 实扣 160 缺口 29 解散 0" in log
    assert "treasury_after=-29" in log or "军团维护费" in log
    # 战争军团不解散：20 个仍 ACTIVE 且 war_id 保留（三重保护）
    active = [l for l in ms.get_all_legions() if l.status == LegionStatus.ACTIVE]
    assert len(active) == 20
    assert all(l.war_id == "w1" for l in active)


# ─── T-R5-04 国库 0 ──────────────────────────────────────────────────────

def test_treasury_zero():
    """treasury=0, 3×未指派（total=24）→ 裁军补额（3×8=24 ≥ 24）→ total_after=0
    → charged=0 → treasury=0。不变式：charged == total_after 且 treasury ≤ 0。"""
    s = _make_state()
    s.treasury = 500
    _recruit(s, [1, 2, 3])  # 征召费 4×3=12
    s.treasury = 0  # 场景国库
    ms = s.get_military_system()

    ok, _msg = ms.apply_maintenance(verbose=False)

    assert ok is True
    assert ms._last_maintenance_disbanded == 3
    total_after = ms.calculate_maintenance()[0]
    charged = 0 - s.treasury
    assert charged == total_after == 0
    assert s.treasury <= 0
    assert "解散 3" in _maintenance_log(s)


# ─── T-R5-05 负值遗留续扣 ────────────────────────────────────────────────

def test_negative_carried_over():
    """treasury=-10（上年度遗留），无候选（全战争指派，total=24）→ 短款分支
    → charged=24 → treasury=-34 → shortfall=34（= charged − before）。"""
    s = _make_state()
    s.treasury = 500
    _recruit(s, [1, 2, 3])
    _assign_war(s, [1, 2, 3])
    s.treasury = -10
    ms = s.get_military_system()

    ok, _msg = ms.apply_maintenance(verbose=False)

    assert ok is True
    before = -10
    assert ms._last_maintenance_disbanded == 0
    assert s.treasury == before - 24
    assert s.treasury == -34
    assert 24 - before == 34
    assert "缺口 34" in _maintenance_log(s)


# ─── T-R5-06 无军团早退 + ODR-1 入口重置 ─────────────────────────────────

def test_no_legions_zero_total():
    """total=0 早退：charged=0、treasury 不变、日志含应扣 0、恒 return True。
    ODR-R5-G3-1：入口清零——先设陈旧 _last_maintenance_disbanded=5 → 早退后读 0。"""
    s = _make_state()
    s.treasury = 100
    ms = s.get_military_system()
    ms._last_maintenance_disbanded = 5  # 模拟上回合解散 5 的陈旧计数

    ok, msg = ms.apply_maintenance(verbose=False)

    assert ok is True
    assert msg == ""
    assert ms._last_maintenance_disbanded == 0  # ODR-1：入口清零
    assert s.treasury == 100
    log = _maintenance_log(s)
    assert log is not None and "应扣 0" in log
    # economic_service 经 getattr(..., 0) 读 0 非陈旧 5
    assert getattr(ms, "_last_maintenance_disbanded", 0) == 0


# ─── T-R5-07 老兵不解散 ──────────────────────────────────────────────────

def test_veteran_not_disband_candidate():
    """treasury=20；1×老兵未指派（9）+ 2×非老兵未指派（16）→ total=25 短款 5
    → 候选仅 2 非老兵 → disbanded=1（8 ≥ 5）→ total_after=17 → charged=17
    → treasury=3。老兵非候选（status 仍 ACTIVE），维护费含 vet+1（计费规则零改动）。"""
    s = _make_state()
    s.treasury = 500
    _recruit(s, [1, 2, 3])  # 征召费 4×3=12
    s.treasury = 20  # 场景国库
    s.get_military_system().get_legion_by_number(1).promote_to_veteran()
    ms = s.get_military_system()

    assert ms.calculate_maintenance()[0] == 9 + 8 + 8  # vet+1 计费含入
    ok, _msg = ms.apply_maintenance(verbose=False)

    assert ok is True
    assert ms._last_maintenance_disbanded == 1
    veteran = ms.get_legion_by_number(1)
    assert veteran.status == LegionStatus.ACTIVE  # 老兵非解散候选
    assert ms.get_legion_by_number(2).status == LegionStatus.DISBANDED
    assert ms.get_legion_by_number(3).status == LegionStatus.ACTIVE
    assert ms.calculate_maintenance()[0] == 17
    assert s.treasury == 3
    assert "实扣 17" in _maintenance_log(s)
    assert "缺口 0" in _maintenance_log(s)


# ─── T-R5-08 战争军团不解散 ──────────────────────────────────────────────

def test_war_assigned_not_disbanded():
    """treasury=10；1×战争指派（非老兵）+ 1×未指派（非老兵）→ total=16 短款 6
    → 候选仅未指派 1 个 → disbanded=1 → total_after=8 → charged=8 → treasury=2。
    战争指派军团 status 仍 ACTIVE、war_id 保留（三重保护）。"""
    s = _make_state()
    s.treasury = 500
    _recruit(s, [1, 2])  # 征召费 4×2=8
    s.treasury = 10  # 场景国库
    _assign_war(s, [1])
    ms = s.get_military_system()

    ok, _msg = ms.apply_maintenance(verbose=False)

    assert ok is True
    assert ms._last_maintenance_disbanded == 1
    war_legion = ms.get_legion_by_number(1)
    assert war_legion.status == LegionStatus.ACTIVE
    assert war_legion.war_id == "w1"
    assert ms.get_legion_by_number(2).status == LegionStatus.DISBANDED
    assert ms.calculate_maintenance()[0] == 8
    assert s.treasury == 2
    assert "实扣 8" in _maintenance_log(s)


# ─── T-R5-09 破产联动 smoke（仅验证，不改机制）───────────────────────────

def test_bankruptcy_linkage_smoke():
    """T6 国库负场景（131 无候选 → −29）→ check_victory_conditions 赤字计数递增；
    连续 3 回合负 → bankruptcy（critical=True game_over=True）。机制零改动。"""
    s = _make_state()
    s.treasury = 500
    _recruit(s, list(range(1, 21)))
    _assign_war(s, list(range(1, 21)))
    s.treasury = 131
    ms = s.get_military_system()
    ok, _msg = ms.apply_maintenance(verbose=False)
    assert ok is True
    assert s.treasury == -29

    outcome1 = s.check_victory_conditions()
    assert s.treasury_deficit_turns == 1
    assert outcome1["summary"]["deficit_turns"] == 1
    assert outcome1["summary"]["deficit_limit"] == 3

    s.check_victory_conditions()
    assert s.treasury_deficit_turns == 2

    outcome3 = s.check_victory_conditions()
    assert s.treasury_deficit_turns == 3
    bankruptcy = [c for c in outcome3["conditions"] if c["type"] == "bankruptcy"]
    assert bankruptcy and bankruptcy[0]["triggered"] is True
    assert bankruptcy[0]["critical"] is True
    assert outcome3["game_over"] is True


# ─── T-R5-10 DTO 重建一致性（刷新重入）───────────────────────────────────

def test_dto_rebuild_consistency():
    """同一构造的独立 state 连续 settle：charged/shortfall/disbanded 一致；
    charged == before − after 恒成立；四键向后兼容 + 三新键在位。"""
    def _build_and_settle():
        s = _make_state()
        s.treasury = 500
        _recruit(s, list(range(1, 21)))
        _assign_war(s, list(range(1, 21)))
        s.treasury = 131
        return _settle(s)

    data1 = _build_and_settle()
    data2 = _build_and_settle()

    for data in (data1, data2):
        military = data["maintenance"]["military"]
        # 向后兼容四键
        assert set(("available", "total", "success", "message")).issubset(military.keys())
        # 新增三键
        assert set(("charged", "shortfall", "disbanded")).issubset(military.keys())
        assert military["total"] == 160
        assert military["charged"] == 160
        assert military["shortfall"] == 29
        assert military["disbanded"] == 0
        assert military["success"] is True
        # 同源断言：charged == before − after
        assert military["charged"] == data["starting_treasury"] - data["ending_treasury"]
        assert data["ending_treasury"] == -29

    # 刷新重入：两次独立结算 DTO 完全一致
    assert data1["maintenance"]["military"]["charged"] == data2["maintenance"]["military"]["charged"]
    assert data1["maintenance"]["military"]["shortfall"] == data2["maintenance"]["military"]["shortfall"]
    assert data1["maintenance"]["military"]["disbanded"] == data2["maintenance"]["military"]["disbanded"]
    assert data1["treasury_delta"] == data2["treasury_delta"] == -160
