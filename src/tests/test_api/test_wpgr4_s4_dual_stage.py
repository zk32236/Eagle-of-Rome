# src/tests/test_api/test_wpgr4_s4_dual_stage.py
"""WP-G-R4 S3（R4-G-03/G-05，SA v1.7 §8.1 D：T05/T06/T07 + T11/T12/T13/T14/T15）—
Dual-Stage Persistence：每次 ATTACK 单一 finalized v2 envelope（naval/land 并列 executed），
构建次序 §5.2 冻结，同一完整 envelope deepcopy 持久 pending_result + war_results[war_id]，
confirm/newStore/多 war 不丢不覆盖，TRUCE 卡附 result。

权威：SA-Design-WP-G-R4 v1.7 §5（§5.1 字段级 schema / §5.2 构建次序 / §5.3 关键例 /
§5.4 Persistence-Refresh Map）；§8.1/§8.2；§13 红线 R4-02/R4-05（无假 Land 零值——
omitted keys 非 null 非 0 占位）。

纪律：DATA test 禁 patch 被测 public API/WarSystem/Naval losses 返回预制成功。所有结果
经 fixture 真实舰队/军团 + 双独立 force 内存键（FIX03~07 builder）生产；损失 mutation
（mark_destroyed/remove_fleet/apply_land_casualties）全部真实执行；采样确定性仅控制
random.sample 源（§9.1）；wrap 计数只记录调用序不改返回值。
"""
import logging
import unittest.mock as mock

from src.api import combat_api
from src.core.entities.war import WarStatus
from src.tests.fixtures import wpgr4_fixtures as F

P1 = F.P1

# v2 envelope 顶层 alias 键集（land.executed=true 时旧顶层字段 = land.* 纯 alias；§5.1 兼容窗口）
_TOP_ALIAS_KEYS = [
    "dice", "total_attack", "enemy_defence", "total_score",
    "losses", "casualty_numbers", "triumph", "loot",
    "treasury_share", "faction_share", "commander_share", "soldier_share",
]


class _LogCapture:
    """capture GameState.log_event extra（type=...）——需先挂 logger（create_for_testing 默认无）。"""
    def __init__(self, state):
        self.records = []
        self.logger = logging.Logger(name=f"r4d-{id(self)}", level=logging.INFO)
        self.handler = _Handler(self.records)
        self.logger.addHandler(self.handler)
        self._prev = state._logger
        state._logger = self.logger

    def close(self, state):
        state._logger = self._prev
        self.logger.removeHandler(self.handler)
        self.handler.close()


class _Handler(logging.Handler):
    def __init__(self, records):
        super().__init__()
        self._records = records

    def emit(self, record):
        self._records.append(record.getMessage())


def _event_types(records):
    import re
    types = []
    for msg in records:
        m = re.search(r"type=(\w+)", msg)
        if m:
            types.append(m.group(1))
    return types


def _attack(state, war, land_force_override=None):
    if land_force_override is not None:
        state.config.testing.force_battle_result = land_force_override  # task-local 内存键
    return combat_api.do_combat_action(state, P1, war.id, "attack")


def _phase(state):
    return state.get_phase_result("combat") or {}


def _view(state):
    res = combat_api.get_combat_view(state, P1)
    assert res["success"], res.get("message")
    return res["data"]


def _envelope_land_keys(data):
    """land stage 数值键集（仅 executed 时存在；未执行对象禁写 result/dice/...——R4-05）。"""
    return {k for k in data.get("land", {}) if k not in ("executed", "status", "reason")}


def _ready_fleets(state, war):
    return state.naval_system.get_ready_fleets_for_war(war)


# ════════════════════════════════════════════════════════════════════════
# T05 — naval STALEMATE 阻断 Land 无统计（真实 ready fleet + forced STALEMATE）
# ════════════════════════════════════════════════════════════════════════
def test_t05_naval_stalemate_blocks_land_without_stats():
    ctx = F.build_fix03(naval_force="STALEMATE", land_force="TRIUMPH")
    state, war = ctx["state"], ctx["war"]
    assert _ready_fleets(state, war), "前置：真实 ready fleet"
    cap = _LogCapture(state)
    try:
        result = _attack(state, war)
    finally:
        cap.close(state)
    assert result["success"], result.get("message")
    data = result["data"]

    # v2 envelope：naval executed=true（真实 STALEMATE），land false
    assert data["schema_version"] == 2
    assert data["action_status"] == "naval_blocked"
    assert data["result_stage"] == "naval"
    assert data["naval"]["executed"] is True
    assert data["naval"]["result"] == "STALEMATE"
    assert data["naval"]["roman_losses"] == 0
    assert data["naval"]["sea_control_acquired"] is False
    assert data["land"]["executed"] is False
    assert data["land"]["status"] == "NOT_EXECUTED"
    assert data["land"]["reason"] == "NAVAL_GATE_BLOCKED"
    # R4-05：land false → 所有 Land 数字 key absent（禁假 0/null 占位）
    assert _envelope_land_keys(data) == set()
    for key in _TOP_ALIAS_KEYS:
        assert key not in data, f"land=false 顶层 Land 统计必须 absent（R4-05）: {key}"
    # 顶层结果 = 显式 naval summary（禁把 Naval 损失放 losses）
    assert data["result"] == "naval_stalemate"
    assert data["land_battle"] == "blocked"

    # 真实副作用恰一次：duration+1；resolved_wars 一次；无 land/treaty resolver
    assert war.duration == 1
    assert war.status == WarStatus.ACTIVE
    phase = _phase(state)
    assert phase["resolved_wars"].count(war.id) == 1
    assert war.sea_control_acquired is False
    # Land 未消费：land_force 设为 TRIUMPH 也未触发（无 land resolver/事件/终结）
    types = _event_types(cap.records)
    assert "naval_battle_stalemate" in types
    assert "combat_triumph" not in types
    assert "combat_victory" not in types
    assert "combat_action_resolved" in types, "真实 ATTACK 完成（blocking）→ summary event"
    # 军团/Commander 不变（零 Land 副作用）
    ms = state.get_military_system()
    attached = ms.get_legions_for_battle(war.id)
    assert len(attached) == 2
    assert all(l.war_id == war.id for l in attached)
    assert war.commander_id is not None

    # confirm 后卡相同（view 附 war_results[id]，结果对象逐字段不变）
    assert combat_api.confirm_battle_result(state, P1)["success"]
    view = _view(state)
    assert view["battle_results"] == []
    active_cards = {c["war_id"]: c for c in view["active_wars"]}
    assert active_cards[war.id]["result"] == data
    assert active_cards[war.id]["presentation_state"] == "CURRENT_TURN_RESULT"


# ════════════════════════════════════════════════════════════════════════
# T06 — naval DEFEAT 保真实损失（5 ready fleets → 真实 _apply_naval_losses 损 3）
# ════════════════════════════════════════════════════════════════════════
def test_t06_naval_defeat_preserves_actual_losses():
    ctx = F.build_fix04(n_fleets=5, naval_force="DEFEAT", land_force="TRIUMPH")
    state, war = ctx["state"], ctx["war"]
    fleets_before = {f.number for f in _ready_fleets(state, war)}
    assert fleets_before == {1, 2, 3, 4, 5}

    # 确定性采样：random.sample 取参战集前 ceil(N/2)=3（只控制采样源，_apply_naval_losses 真实执行）
    ns = state.naval_system
    with mock.patch("src.core.systems.naval_system.random.sample",
                    side_effect=lambda population, k: population[:k]):
        cap = _LogCapture(state)
        try:
            result = _attack(state, war)
        finally:
            cap.close(state)
    assert result["success"], result.get("message")
    data = result["data"]

    # v2：naval executed + 真实损失；land false 无 Land 数字
    assert data["naval"]["executed"] is True
    assert data["naval"]["result"] == "DEFEAT"
    assert data["naval"]["roman_losses"] == 3
    assert data["naval"]["enemy_losses"] == 0
    assert sorted(data["naval"]["participating_fleet_ids"]) == [1, 2, 3, 4, 5]
    assert sorted(data["naval"]["casualty_fleet_ids"]) == [1, 2, 3], "实际损失差集（去重）"
    assert data["land"]["executed"] is False
    assert data["land"]["reason"] == "NAVAL_GATE_BLOCKED"
    assert _envelope_land_keys(data) == set()
    assert "losses" not in data and "casualty_numbers" not in data
    assert data["result"] == "naval_defeat"

    # 实体真实损失：3 艘 DESTROYED + war 侧 remove；2 幸存 ON_MISSION
    destroyed = [f for f in ns.get_all_fleets() if f.status.value == "destroyed"]
    assert sorted(f.number for f in destroyed) == [1, 2, 3]
    survivors = [f for f in ns.get_all_fleets() if f.status.value == "on_mission"]
    assert sorted(f.number for f in survivors) == [4, 5]
    assert sorted(war.assigned_fleet_ids) == [4, 5]
    assert war.duration == 1

    # Land 军团/Commander 不变（零 Land 伤亡/后果）
    ms = state.get_military_system()
    attached = ms.get_legions_for_battle(war.id)
    assert len(attached) == 2
    assert all(l.status.value == "active" for l in attached)
    assert war.commander_id is not None

    # 事件：真实 naval_battle_defeat；无 Land 终结事件
    types = _event_types(cap.records)
    assert "naval_battle_defeat" in types
    assert "combat_triumph" not in types
    # 事件/DTO 损失逐舰一致
    card_result = None
    view = _view(state)
    for c in view["active_wars"]:
        if c["war_id"] == war.id:
            card_result = c["result"]
    assert card_result is not None
    assert sorted(card_result["naval"]["casualty_fleet_ids"]) == [1, 2, 3]
    assert card_result["naval"]["roman_losses"] == 3


# ════════════════════════════════════════════════════════════════════════
# T07 — naval DISASTER 全灭（N fleets 全真实 DESTROYED；Land 未执行；repeat 零增损）
# ════════════════════════════════════════════════════════════════════════
def test_t07_naval_disaster_preserves_actual_losses():
    ctx = F.build_fix04(n_fleets=5, naval_force="DISASTER", land_force="TRIUMPH")
    state, war = ctx["state"], ctx["war"]
    ns = state.naval_system
    cap = _LogCapture(state)
    try:
        result = _attack(state, war)
    finally:
        cap.close(state)
    assert result["success"], result.get("message")
    data = result["data"]

    assert data["naval"]["executed"] is True
    assert data["naval"]["result"] == "DISASTER"
    assert data["naval"]["roman_losses"] == 5
    assert sorted(data["naval"]["participating_fleet_ids"]) == [1, 2, 3, 4, 5]
    assert sorted(data["naval"]["casualty_fleet_ids"]) == [1, 2, 3, 4, 5]
    assert data["land"]["executed"] is False
    assert data["land"]["reason"] == "NAVAL_GATE_BLOCKED"
    assert _envelope_land_keys(data) == set()

    # 全真实 DESTROYED；war 侧清空
    assert all(f.status.value == "destroyed" for f in ns.get_all_fleets())
    assert war.assigned_fleet_ids == []
    assert war.duration == 1
    # Land 未执行：军团零损、Commander 不按 Land disaster 死亡
    ms = state.get_military_system()
    attached = ms.get_legions_for_battle(war.id)
    assert len(attached) == 2
    assert all(l.status.value == "active" for l in attached)
    commander = state.get_member(war.commander_id)
    assert commander is not None and commander.is_dead is False
    # 事件
    types = _event_types(cap.records)
    assert "naval_battle_disaster" in types
    assert "combat_disaster" not in types, "Land disaster 未执行——禁伪 Land 事件"

    # repeat（同回合再次 attack）不再损失/不再 duration（exactly-once guard）
    before_destroyed = len([f for f in ns.get_all_fleets() if f.status.value == "destroyed"])
    repeat = _attack(state, war)
    assert repeat["success"] is False
    assert war.duration == 1
    assert len([f for f in ns.get_all_fleets() if f.status.value == "destroyed"]) == before_destroyed
    assert war.commander_id is not None, "repeat 无 Land 后果"


# ════════════════════════════════════════════════════════════════════════
# T11 — Naval VICTORY + Land DEFEAT（两独立 override；公开 ATTACK 恰一次；War ACTIVE）
# ════════════════════════════════════════════════════════════════════════
def test_t11_one_attack_naval_victory_land_defeat():
    ctx = F.build_fix05(naval_force="VICTORY", land_force="DEFEAT")
    state, war = ctx["state"], ctx["war"]
    ns = state.naval_system
    order = []
    orig_naval = ns.resolve_naval_battle
    orig_land = combat_api._compute_combat_result

    def naval_spy(war_obj):
        order.append("naval")
        return orig_naval(war_obj)

    def land_spy(*args, **kwargs):
        order.append("land")
        return orig_land(*args, **kwargs)

    cap = _LogCapture(state)
    try:
        with mock.patch.object(ns, "resolve_naval_battle", side_effect=naval_spy), \
             mock.patch.object(combat_api, "_compute_combat_result", side_effect=land_spy):
            result = combat_api.do_combat_action(state, P1, war.id, "attack")
    finally:
        cap.close(state)
    assert result["success"], result.get("message")
    data = result["data"]

    # 一次 ATTACK → Naval→Land 顺序各 1（两阶段独立、无二次确认——R4-02）
    assert order == ["naval", "land"]
    assert data["schema_version"] == 2
    assert data["action_status"] == "land_resolved"
    assert data["result_stage"] == "land"
    assert data["naval"]["executed"] is True
    assert data["naval"]["result"] == "VICTORY"
    assert data["naval"]["sea_control_acquired"] is True
    assert data["naval"]["sea_control_before"] is False
    assert data["land"]["executed"] is True
    assert data["land"]["status"] == "RESOLVED"
    assert data["land"]["result"] == "defeat"
    assert data["result"] == "defeat"
    assert data["land_battle"] == "allowed"
    # 顶层 alias == land.*（兼容窗口值逐项相同）
    for key in _TOP_ALIAS_KEYS:
        assert data[key] == data["land"][key], f"顶层 alias {key} != land.{key}"

    # War ACTIVE 非 RESOLVED；sea 保持 true（land DEFEAT 不清制海权）
    assert war.status == WarStatus.ACTIVE
    assert war.sea_control_acquired is True
    assert data["war_outcome"]["status_after"] == "active"
    assert data["war_outcome"]["terminal_success"] is False
    assert data["war_outcome"]["sea_control_after"] is True
    assert data["war_outcome"]["combat_duration_delta"] == 1  # land 损失后果 +1（§5.3 例 1）

    # 真实 Land 损失（defeat：ceil(2/2)=1 destroyed）+ Commander 后果（离场）
    ms = state.get_military_system()
    destroyed = [l for l in ms.get_all_legions() if l.status.value == "destroyed"]
    assert len(destroyed) == 1
    assert len(data["land"]["casualty_numbers"]) == 1
    assert war.commander_id is None, "land defeat → commander consequence"

    # 事件：无 resolve_war(True)（无 combat_victory/triumph）；有 summary event
    types = _event_types(cap.records)
    assert "combat_victory" not in types
    assert "combat_triumph" not in types
    assert "combat_action_resolved" in types
    # 持久：同一完整 envelope 进 pending_result + war_results[id]
    phase = _phase(state)
    assert phase["pending_result"] == data
    assert phase["war_results"][war.id] == data
    assert phase["resolved_wars"].count(war.id) == 1


# ════════════════════════════════════════════════════════════════════════
# T12 — Naval TRIUMPH + Land draw → 合法 treaty decider → TRUCE pending（TRUCE 卡两结果）
# ════════════════════════════════════════════════════════════════════════
def test_t12_one_attack_naval_triumph_land_stalemate():
    ctx = F.build_fix06(naval_force="TRIUMPH", land_force="STALEMATE")
    state, war = ctx["state"], ctx["war"]
    cap = _LogCapture(state)
    try:
        result = _attack(state, war)
    finally:
        cap.close(state)
    assert result["success"], result.get("message")
    data = result["data"]

    # 两独立结果：naval TRIUMPH 不变成 Land 大胜（§5.3 例 2）
    assert data["naval"]["executed"] is True
    assert data["naval"]["result"] == "TRIUMPH"
    assert data["naval"]["sea_control_acquired"] is True
    assert data["land"]["executed"] is True
    assert data["land"]["result"] == "draw"
    assert data["land"]["triumph"] is False
    assert data["result"] == "draw"
    # War → TRUCE + pending treaty（合法 decider，无伪 terminal）
    assert war.status == WarStatus.TRUCE
    assert war.peace_treaty is not None
    assert war.peace_treaty.get("status") == "pending"
    assert data["war_outcome"]["status_after"] == "truce"
    assert data["war_outcome"]["terminal_success"] is False
    assert data["war_outcome"]["sea_control_after"] is True  # sea 保持
    assert data["war_outcome"]["combat_duration_delta"] == 0

    types = _event_types(cap.records)
    assert "naval_battle_triumph" in types
    assert "combat_triumph" not in types
    assert "peace_treaty_generated" in types
    assert "combat_action_resolved" in types

    # confirm/newStore 后 TRUCE 锁定卡也有两个结果（view + Store 同值）
    assert combat_api.confirm_battle_result(state, P1)["success"]
    view = _view(state)
    truce_cards = {c["war_id"]: c for c in view["truce_wars"]}
    assert war.id in truce_cards
    assert truce_cards[war.id]["presentation_state"] == "TRUCE_LOCKED"
    assert truce_cards[war.id]["result"] == data, "TRUCE 卡附完整两阶段 result（§5.3 例 2/§5.4）"
    assert view["battle_results"] == []
    # 卡 result = 完整两阶段 envelope（naval 与 land 独立字段并列）
    card_res = truce_cards[war.id]["result"]
    assert card_res["naval"]["result"] == "TRIUMPH"
    assert card_res["land"]["result"] == "draw"


# ════════════════════════════════════════════════════════════════════════
# T13 — Naval VICTORY + Land TRIUMPH（War RESOLVED；naval sea 快照 true vs final false）
# ════════════════════════════════════════════════════════════════════════
def test_t13_one_attack_naval_victory_land_triumph():
    ctx = F.build_fix07(naval_force="VICTORY", land_force="TRIUMPH")
    state, war = ctx["state"], ctx["war"]
    cap = _LogCapture(state)
    try:
        result = _attack(state, war)
    finally:
        cap.close(state)
    assert result["success"], result.get("message")
    data = result["data"]

    # 两阶段各 1：naval VICTORY 获控；land TRIUMPH 终结
    assert data["naval"]["executed"] is True
    assert data["naval"]["result"] == "VICTORY"
    assert data["naval"]["sea_control_acquired"] is True      # naval 阶段快照（未清前）
    assert data["naval"]["participating_fleet_ids"] == [1]    # recall 后 naval 参与 IDs 保留
    assert data["land"]["executed"] is True
    assert data["land"]["result"] == "triumph"
    assert data["result"] == "triumph"
    assert data["result_stage"] == "land"

    # War RESOLVED；final sea false（resolve_war 清理）——两字段不矛盾（§5.3 例 3）
    assert war.status == WarStatus.RESOLVED
    assert war.sea_control_acquired is False
    assert data["war_outcome"]["status_after"] == "resolved"
    assert data["war_outcome"]["terminal_success"] is True
    assert data["war_outcome"]["sea_control_after"] is False
    assert data["war_outcome"]["combat_duration_delta"] == 0

    # 事件 carrier：combat_triumph（显式词）+ summary
    types = _event_types(cap.records)
    assert "combat_triumph" in types
    assert "combat_victory" not in types
    assert "combat_action_resolved" in types

    # RESOLVED 卡附同一 envelope（view resolved_war_cards）
    view = _view(state)
    resolved_cards = {c["war_id"]: c for c in view["resolved_war_cards"]}
    assert war.id in resolved_cards
    assert resolved_cards[war.id]["result"] == data


# ════════════════════════════════════════════════════════════════════════
# T14 — dual-stage 快照 survive confirm/refresh/re-entry（chain equality + 不覆盖）
# ════════════════════════════════════════════════════════════════════════
def _land_stage_keys():
    return {"result", "result_label", "dice", "total_attack", "enemy_defence",
            "total_score", "losses", "casualty_numbers", "triumph", "loot",
            "treasury_share", "faction_share", "commander_share", "soldier_share"}


def test_t14a_envelope_chain_survives_confirm_refresh_newstore():
    """action DTO == pending == war_results == view == Store；confirm 后仅 pending 清；
    newStore 重建同值；mutate 返回 DTO 不污染 GameState（deepcopy）。"""
    from src.ui.gui.session_store import GuiSessionStore
    ctx = F.build_fix05(naval_force="VICTORY", land_force="DEFEAT")
    state, war = ctx["state"], ctx["war"]

    store = GuiSessionStore(state)
    store.initialize(P1)
    sel = store.doSelectWar(war.id)
    assert sel["success"], sel.get("message")
    fb = store.doCombatAction(war.id, "attack")
    assert fb["success"], fb.get("message")
    data = fb["data"]

    # 五层同值（§5.4）：action DTO == pending == war_results == view == Store
    phase = _phase(state)
    assert phase["pending_result"] == data
    assert phase["war_results"][war.id] == data
    view = _view(state)
    assert view["battle_results"] == [data]
    assert store.combatBattleResultDetail == data

    # mutate 返回 DTO 不污染 GameState 持久（deepcopy）
    data["land"]["result"] = "MUTATED"
    data["war_outcome"]["status_after"] = "MUTATED"
    phase2 = _phase(state)
    assert phase2["pending_result"]["land"]["result"] == "defeat"
    assert phase2["war_results"][war.id]["war_outcome"]["status_after"] == "active"

    # confirm → 仅 pending 清（war_results/resolved_wars 保留）
    cf = store.doConfirmBattleResult()
    assert cf["success"], cf.get("message")
    phase3 = _phase(state)
    assert phase3["pending_result"] == {}
    assert war.id in phase3["resolved_wars"]
    assert phase3["war_results"][war.id]["land"]["result"] == "defeat"
    assert store.combatBattleResultDetail == {}

    # view/Store 卡仍带完整 envelope
    view2 = _view(state)
    active_cards = {c["war_id"]: c for c in view2["active_wars"]}
    assert active_cards[war.id]["result"]["land"]["result"] == "defeat"
    assert active_cards[war.id]["result"]["naval"]["result"] == "VICTORY"
    assert store.combatView.get("active_wars") and any(
        c.get("war_id") == war.id and c.get("result", {}).get("naval", {}).get("result") == "VICTORY"
        for c in store.combatView.get("active_wars", []))

    # 重入（同回合再次 attack）不再 roll/resolve（exactly-once guard）
    re = combat_api.do_combat_action(state, P1, war.id, "attack")
    assert re["success"] is False
    phase4 = _phase(state)
    assert phase4["war_results"][war.id]["land"]["result"] == "defeat"

    # newStore 重建同态（不覆盖、不重复结算）
    store2 = GuiSessionStore(state)
    store2.initialize(P1)
    detail2 = store2.combatBattleResultDetail
    assert detail2 == {}
    assert any(c.get("war_id") == war.id and c.get("result", {}).get("land", {}).get("result") == "defeat"
               for c in store2.combatView.get("active_wars", []))


def test_t14b_naval_block_envelope_chain_and_reentry():
    """naval block（STALEMATE）同样：五层同值 + confirm 后卡相同 + 重入零增损。"""
    ctx = F.build_fix03(naval_force="STALEMATE", land_force="TRIUMPH")
    state, war = ctx["state"], ctx["war"]
    result = _attack(state, war)
    assert result["success"], result.get("message")
    data = result["data"]

    phase = _phase(state)
    assert phase["pending_result"] == data
    assert phase["war_results"][war.id] == data
    view = _view(state)
    assert view["battle_results"] == [data]

    assert combat_api.confirm_battle_result(state, P1)["success"]
    view2 = _view(state)
    active_cards = {c["war_id"]: c for c in view2["active_wars"]}
    assert active_cards[war.id]["result"] == data

    # 重入：guard 拒绝（battled 恰一次）——不重复 duration/损失
    re = _attack(state, war)
    assert re["success"] is False
    assert war.duration == 1
    assert all(f.status.value == "on_mission" for f in state.naval_system.get_all_fleets())


def test_t14c_second_war_does_not_overwrite_first():
    """第二场 war 结算不覆盖 A：war_results[A] 逐字段不变、pending=B（§5.4）。"""
    ctx = F.build_fix05(naval_force="VICTORY", land_force="DEFEAT")
    state, war_a = ctx["state"], ctx["war"]

    # 追加第二场非海军战（独立 commander + legions；真实公开 producer 链）
    from src.core.entities.war import War, WarType
    from src.core.entities.figure import Figure, ClassTier
    war_b = War(id="land_war_b", name="Land War B", war_type=WarType.FOREIGN,
                strength=4, threat_level=3, rewards={"treasury": 80},
                naval_required=False, enemy_land_current=2,
                disaster_numbers=[99], standoff_numbers=[99])
    war_b.status = WarStatus.ACTIVE
    commander_b = Figure(id=202, name="Commander B", faction_id="optimates", age=38)
    commander_b.martial = 3
    commander_b.office = "proconsul"
    commander_b.is_absent = True
    state.add_member(commander_b)
    ctx["faction"].member_ids.append(202)
    war_b.commander_id = 202
    state.get_war_system()._active_wars.append(war_b)
    F.recruit_legions_for_war(state, war_b, 202, count=2)

    # A 战先结算（naval VICTORY + land DEFEAT）
    r1 = _attack(state, war_a)
    assert r1["success"], r1.get("message")
    envelope_a = _phase(state)["war_results"][war_a.id]

    # B 战 attack（非海军，独立 override VICTORY）——force_battle_result 为 task-local 内存键，
    # B 结算前显式改值（A 已结算且缓存 envelope 不变，不受影响）
    state.config.testing.force_battle_result = "VICTORY"
    r2 = combat_api.do_combat_action(state, P1, war_b.id, "attack")
    assert r2["success"], r2.get("message")
    envelope_b = r2["data"]

    phase = _phase(state)
    assert phase["war_results"][war_a.id] == envelope_a, "A 逐字段不变（不覆盖）"
    assert phase["war_results"][war_b.id] == envelope_b
    assert phase["pending_result"] == envelope_b
    assert phase["resolved_wars"].count(war_a.id) == 1
    assert phase["resolved_wars"].count(war_b.id) == 1
    assert war_b.status == WarStatus.RESOLVED


# ════════════════════════════════════════════════════════════════════════
# T15 — 非海军五结果 + 已获控零舰队 bypass（DTO/persistence 面）
# ════════════════════════════════════════════════════════════════════════
_LAND_WORD_CASES = [
    ("VICTORY", "victory", "resolved"),
    ("TRIUMPH", "triumph", "resolved"),
    ("STALEMATE", "draw", "truce"),
    ("DEFEAT", "defeat", "active"),
    ("DISASTER", "disaster", "active"),
]


def test_t15_non_naval_five_results_envelope():
    """非海军五结果：naval NOT_EXECUTED(NOT_REQUIRED)；land executed；alias 与旧值相同；
    empty/absent force 原 CRT 不受影响（本批不重开 dice 语义）。"""
    for land_force, word, status_after in _LAND_WORD_CASES:
        ctx = F.build_fix08(land_force=land_force)
        state, war = ctx["state"], ctx["war"]
        result = _attack(state, war)
        assert result["success"], f"{land_force}: {result.get('message')}"
        data = result["data"]
        assert data["schema_version"] == 2
        assert data["naval"]["required"] is False
        assert data["naval"]["gate_required"] is False
        assert data["naval"]["executed"] is False
        assert data["naval"]["status"] == "NOT_EXECUTED"
        assert data["naval"]["reason"] == "NOT_REQUIRED"
        assert "result" not in data["naval"] and "roman_losses" not in data["naval"], \
            "naval 未执行不写 battle 数值（§5.1）"
        assert data["land"]["executed"] is True
        assert data["land"]["result"] == word
        assert data["result"] == word
        assert data["result_stage"] == "land"
        # 顶层 alias == land.*（旧消费者可读；值逐项相同——兼容窗口）
        for key in _TOP_ALIAS_KEYS:
            assert data[key] == data["land"][key], f"{land_force}: alias {key} 不一致"
        assert data["war_outcome"]["status_after"] == status_after
        assert data["land_battle"] == "bypassed"
        # 持久
        phase = _phase(state)
        assert phase["war_results"][war.id] == data


def test_t15_sea_control_already_acquired_zero_fleet_bypass():
    """已获控零舰队（naval_required + sea_control_acquired + 零 ready）→ bypass：
    naval NOT_EXECUTED(SEA_CONTROL_ALREADY_ACQUIRED)，Land 正常执行。"""
    ctx = F.build_fix05(naval_force="VICTORY", land_force="VICTORY")
    state, war = ctx["state"], ctx["war"]
    # 已获控 + 舰队离场（recall → AVAILABLE；war 侧清空）
    war._sea_control_acquired = True
    ns = state.naval_system
    for fleet in list(ns._fleets.values()):
        ns.recall_fleet_from_war(fleet.number)
    assert war.assigned_fleet_ids == []
    assert not ns.get_ready_fleets_for_war(war)

    ns2 = state.naval_system
    with mock.patch.object(ns2, "resolve_naval_battle",
                           side_effect=AssertionError("已获控不得再触发海战")):
        result = _attack(state, war)
    assert result["success"], result.get("message")
    data = result["data"]
    assert data["naval"]["required"] is True
    assert data["naval"]["gate_required"] is False
    assert data["naval"]["executed"] is False
    assert data["naval"]["status"] == "NOT_EXECUTED"
    assert data["naval"]["reason"] == "SEA_CONTROL_ALREADY_ACQUIRED"
    assert data["naval"]["sea_control_acquired"] is True
    assert data["land"]["executed"] is True
    assert data["land"]["result"] == "victory"
    assert data["war_outcome"]["status_after"] == "resolved"
    assert data["war_outcome"]["sea_control_after"] is False  # land terminal 清理（K 件 §3）
    assert data["land_battle"] == "bypassed"
    # 禁伪造 Naval VICTORY 表示 bypass（§3.2）
    assert data["result"] == "victory" and data["result_stage"] == "land"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
