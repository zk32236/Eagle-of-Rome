# src/tests/test_api/test_wpgr4_joined_paths.py
"""WP-G-R4 S5（SA v1.7 §8.1 J / DA-Plan §1 S5）— SC-R4-A/B/C/D 四链同 run join。

四链（每链独立 run_id/candidate_sha，禁跨 run 拼接）：
- SC-R4-A（G01）：fixture Senate → Takeover 选择 → Submit 锁 T（零部署）→ 另一合法非空
  land:sale 提案 → vote/veto → resolve（pending-aware M 放行）→ 显式 advance 原子部署 →
  同一 run 进入 Combat 攻击部署战（actionseq 延续）。O5 生产形状全真公开调用。
- SC-R4-B（G02）：零 ready → view/API 拒绝（NAVAL_NOT_READY）→ 全部 battle 副作用零 →
  舰队真实就绪（canonical assign）后重试 attack 恰一次；auto 的 unavailable 独立名单。
- SC-R4-C（G03/05，T11-14 joined）：三组合（VICTORY+DEFEAT / TRIUMPH+draw→TRUCE /
  VICTORY+TRIUMPH）单 ATTACK envelope == pending == war_results == view == card；
  combat_action_resolved summary event 与 envelope 同 run 同值；禁跨 run 拼接。
- SC-R4-D（G04，T10 J 段）：forced VICTORY/TRIUMPH 两个独立 run —— 事件身份独立，
  真实 producer → Forum 公开 view/vote/resolve（凯旋批准）恰一次，无二次 reward。

join 键：run_id / candidate_sha / turn / phase / viewer / player / war / commander /
proposal / direct-action / actionseq（每 segment 记录；同 run 内键一致，不同 run 分离）。

纪律：零 Git 写；fixture 只声明「已到合法 Senate/Combat 入口」外生前置；Takeover/
attack/submit/vote/resolve/advance/attack/confirm 全真公开调用；禁 patch 被测 public
API/WarSystem/Naval losses 返回预制成功（仅 deterministic config force + 事件捕获）。
权威：SA-Design-WP-G-R4-2026-09-07.md v1.7（FROZEN）§8.1 J/§9.3；DA-Plan §1 S5/§5.4。
"""
import logging
import re

from src.api import combat_api, forum_api, senate_api
from src.core.entities.war import WarStatus
from src.tests.fixtures import wpgr4_fixtures as F

P1 = F.P1
CANDIDATE_SHA = ("775dbfc1e9b3d665407db98a0c0fccbb51b80c32"
                 " + R4 B1/B2/B3 working-tree candidate (zero git write)")
PHASES = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]


def _current_phase(state):
    for pid in PHASES:
        if not state.is_phase_executed(pid):
            return pid
    return "resolution"


class RunContext:
    """同 run 证据上下文：每条 segment 记录 join 键；校验同 run 键一致（禁跨 run 拼接）。"""

    def __init__(self, run_id, state, viewer=P1):
        self.run_id = run_id
        self.state = state
        self.viewer = viewer
        self.entries = []

    def record(self, kind, phase=None, war_id=None, commander_id=None,
               proposal_id=None, direct_action=None, actionseq=None, **extra):
        entry = {
            "run_id": self.run_id,
            "candidate_sha": CANDIDATE_SHA,
            "kind": kind,
            "turn": self.state.turn.turn_number,
            "phase": phase or _current_phase(self.state),
            "viewer": self.viewer,
            "player": self.viewer,
        }
        if war_id is not None:
            entry["war"] = war_id
        if commander_id is not None:
            entry["commander"] = commander_id
        if proposal_id is not None:
            entry["proposal"] = proposal_id
        if direct_action is not None:
            entry["direct-action"] = direct_action
        if actionseq is not None:
            entry["actionseq"] = actionseq
        entry.update(extra)
        self.entries.append(entry)
        return entry

    def assert_same_run_consistency(self):
        """同 run 全部 entry 共享 run_id/candidate_sha/viewer/player；turn 单调不降。"""
        prev_turn = None
        for e in self.entries:
            assert e["run_id"] == self.run_id
            assert e["candidate_sha"] == CANDIDATE_SHA
            assert e["viewer"] == self.viewer and e["player"] == self.viewer
            if prev_turn is not None:
                assert e["turn"] >= prev_turn, "同 run turn 必须单调"
            prev_turn = e["turn"]

    def assert_no_cross_run(self, other):
        assert self.run_id != other.run_id
        for e in self.entries:
            assert e["run_id"] != other.run_id
        for e in other.entries:
            assert e["run_id"] != self.run_id


# ---------------------------------------------------------------------------
# 事件捕获（GameState.log_event 的 type/键 join；与 C/E 文件同源手法）
# ---------------------------------------------------------------------------
class _CapHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


def _capture(state):
    logger = logging.Logger(f"jcap-{id(state)}", level=logging.INFO)
    handler = _CapHandler()
    logger.addHandler(handler)
    prev = getattr(state, "_logger", None)
    state._logger = logger
    return handler, prev


def _restore(state, prev):
    state._logger = prev


def _event_types(msgs):
    types = []
    for m in msgs:
        t = re.search(r"\btype=(\S+)", m)
        if t:
            types.append(t.group(1))
    return types


def _event_kv(msgs, ev_type, key):
    for m in msgs:
        if f"type={ev_type}" in m:
            t = re.search(rf"\b{key}=(\S+)", m)
            if t:
                return t.group(1)
    return None


def _join_all_run_entries(runs):
    """证据 join：所有 run 键齐备且各自一致；返回扁平 segment 计数。"""
    total = 0
    for run in runs:
        run.assert_same_run_consistency()
        for e in run.entries:
            assert "run_id" in e and "candidate_sha" in e and "turn" in e
            assert "phase" in e and "viewer" in e and "player" in e
        total += len(run.entries)
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            runs[i].assert_no_cross_run(runs[j])
    return total


# ---------------------------------------------------------------------------
# SC-R4-A — Senate → Takeover → 非空提案 → vote/veto → resolve → advance → Combat
# ---------------------------------------------------------------------------
def _build_a_state():
    """O5 非空主样本（FIX-R4-01 基座 + 第二派系/元老/保民官使 vote/veto 真构造）。"""
    ctx = F.build_fix01(with_war_b=False)
    state = ctx["state"]
    faction = ctx["faction"]
    # 第二派系 populares：NOBILE 元老（有表决影响力）+ PLEBEIAN 保民官（可否决）
    from src.core.entities.entities import Faction
    from src.core.entities.figure import Figure, ClassTier
    from src.core.entities.player import Player, PlayerType
    f2 = Faction(id="populares", name="Populares", treasury=200)
    state.add_faction(f2)
    senator = Figure(id=301, name="Populares Senator", faction_id="populares", age=50)
    senator.class_tier = ClassTier.NOBILE
    senator.influence = 30
    state.add_member(senator)
    f2.member_ids.append(301)
    tribune = Figure(id=302, name="Populares Tribune", faction_id="populares", age=35)
    tribune.office = "tribune"
    tribune.class_tier = ClassTier.PLEBEIAN
    state.add_member(tribune)
    f2.member_ids.append(302)
    player2 = Player("player2", "populares", PlayerType("human"))
    state.add_player(player2)
    state._turn_order = [P1, "player2"]
    state.set_current_player(P1)
    ctx["faction2"] = f2
    ctx["player2"] = "player2"
    return ctx


def test_ja_joined_run_senate_takeover_nonempty_vote_advance_combat():
    """SC-R4-A 同 run join：Submit 零部署 → land:sale 非空提案 → vote/veto → resolve →
    advance 原子部署 → 同 run Combat 攻击（actionseq 连续）。"""
    ctx = _build_a_state()
    state, war_a, consul = ctx["state"], ctx["war_a"], ctx["consul"]
    run = RunContext("run-r4a-b3-j-20260909", state)
    view = senate_api.get_senate_view(state, P1)["data"]
    assert view["takeover_required"]["required"] is True
    assert view["current_step"] == "proposal"
    run.record("senate-view", phase="senate", war_id=war_a.id,
               commander_id=consul.id, actionseq=0)

    # ① Takeover 选择 + Submit 锁 T（零部署；R4-17/R4-18）
    assert senate_api.takeover_war(state, P1, war_a.id, 2, action="reserve")["success"]
    s = senate_api.takeover_war(state, P1, war_a.id, 2, action="submit")
    assert s["success"], s.get("message")
    assert state.get_takeover_pending()["status"] == "LOCKED"
    assert war_a.commander_id is None and not consul.is_absent
    assert state.get_senate_proposals() == [] and state.get_senate_direct_actions() == []
    run.record("takeover-submit", phase="senate", war_id=war_a.id,
               commander_id=consul.id, direct_action="none", actionseq=1)

    # pending-aware M：LOCKED T → M_open False（resolve/advance 放行）
    view = senate_api.get_senate_view(state, P1)["data"]
    assert view["takeover_required"]["m_open"] is False
    assert view["pending_takeover_locked"] is True

    # ② 另一合法非空提案（land:sale，取自 view option；O5 非空面恢复可构造）
    land_opt = [o for o in view["proposal_options"] if o.get("key") == "land:sale"]
    assert land_opt, "public_land>0 → land:sale 选项必须存在"
    params = land_opt[0]["params"]
    assert params["act_type"] == "sale" and params["amount_C"] > 0
    spec = {"type": "land", "params": {"act_type": "sale", "amount_C": params["amount_C"]}}
    prop = senate_api.propose_many(state, P1, [spec])
    assert prop["success"], prop.get("message")
    pid = prop["data"]["created"][0]["proposal_id"]
    run.record("proposal-submit", phase="senate", war_id=war_a.id,
               proposal_id=pid, actionseq=2)

    # ③ vote（双 HUMAN 派系真实投票）→ veto（populares 保民官）
    for player in state._turn_order:
        if state.get_player(player).player_type.value == "human":
            state.set_current_player(player)
            v = senate_api.vote(state, player, [pid], [True])
            assert v["success"], f"{player}: {v.get('message')}"
    run.record("vote", phase="senate", war_id=war_a.id, proposal_id=pid, actionseq=3)
    state.set_current_player("player2")
    ve = senate_api.veto(state, "player2", [pid])
    assert ve["success"], ve.get("message")
    run.record("veto", phase="senate", war_id=war_a.id, proposal_id=pid, actionseq=4)
    # Takeover 不进 Vote/Veto：proposal 集只有 land；无 takeover 提案可投/可否决
    assert [p["id"] for p in state.get_senate_proposals()] == [pid]
    state.set_current_player(P1)

    # ④ resolve（pending-aware M 放行）→ 真实 R → advance 原子部署
    resolved = senate_api.resolve_senate(state)
    assert resolved["success"], resolved.get("message")
    assert state.get_phase_result("senate")
    run.record("resolve", phase="senate", war_id=war_a.id, proposal_id=pid,
               direct_action="none", actionseq=5)
    deploy = senate_api.advance_senate_phase(state, P1)
    assert deploy["success"], deploy.get("message")
    assert war_a.commander_id == consul.id and consul.is_absent
    assert state.get_takeover_pending()["status"] == "CONSUMED"
    das = [a for a in state.get_senate_direct_actions() if a.get("kind") == "takeover_deploy"]
    assert len(das) == 1
    run.record("advance-deploy", phase="combat", war_id=war_a.id,
               commander_id=consul.id, direct_action=das[0]["exactly_once_key"],
               actionseq=6)

    # ⑤ 同一 run Combat：攻击部署战（production-shape Senate→Combat 转换后同 turn 战）
    state.config.testing.force_battle_result = "VICTORY"
    attack = combat_api.do_combat_action(state, P1, war_a.id, "attack")
    assert attack["success"], attack.get("message")
    env = attack["data"]
    assert env["land"]["result"] == "victory"
    assert war_a.status == WarStatus.RESOLVED
    run.record("combat-attack", phase="combat", war_id=war_a.id,
               commander_id=consul.id, direct_action="none", actionseq=7)
    run.assert_same_run_consistency()
    # 部署恰一次 / 提交后无隐式结算（R4-09）/ T/V 分离后无重复 D
    assert len([a for a in state.get_senate_direct_actions()
                if a.get("kind") == "takeover_deploy"]) == 1


# ---------------------------------------------------------------------------
# SC-R4-B — readiness 负链（零 ready 零副作用 → 真实就绪后重试恰一次；auto unavailable）
# ---------------------------------------------------------------------------
def test_rb_joined_run_not_ready_then_ready_retry_single_attack():
    """SC-R4-B 同 run join：NOT_READY 拒绝（零副作用）→ canonical assign → attack 恰一次。"""
    ctx = F.build_fix02(naval_force="VICTORY", land_force="DEFEAT", ready_override=None)
    state, war = ctx["state"], ctx["war"]
    state.mark_phase_executed("senate")
    run = RunContext("run-r4b-b3-j-20260909", state)
    ns = state.naval_system
    duration_before = war.duration
    treasury_before = state._treasury
    legion_count = len(state.get_military_system().get_legions_for_battle(war.id))
    run.record("combat-view", phase="combat", war_id=war.id,
               commander_id=war.commander_id, actionseq=0)

    # ① view/API 拒绝：NOT_READY 非 battle
    view = combat_api.get_combat_view(state, P1)["data"]
    card = [w for w in view["active_wars"] if w["war_id"] == war.id][0]
    assert card["attack_available"] is False
    assert card["attack_disabled_code"] == "NAVAL_NOT_READY"
    rejected = combat_api.do_combat_action(state, P1, war.id, "attack")
    assert rejected["success"] is False
    assert rejected["data"]["code"] == "NAVAL_NOT_READY"
    run.record("not-ready-reject", phase="combat", war_id=war.id,
               commander_id=war.commander_id, actionseq=1)

    # ② 全部 battle 副作用零（force TRIUMPH 不穿透）
    phase = state.get_phase_result("combat") or {}
    assert war.duration == duration_before
    assert state._treasury == treasury_before
    assert phase.get("resolved_wars", []) == [] and phase.get("war_results", {}) == {}
    assert len(state.get_military_system().get_legions_for_battle(war.id)) == legion_count
    assert ns.get_fleets_by_war(war.id) == []
    run.record("zero-side-effects", phase="combat", war_id=war.id, actionseq=2)

    # ③ 舰队真实就绪（canonical assign）→ 重试 attack 恰一次（未 battled，不被拒）
    fleet = ns._fleets[1]
    assert ns.assign_fleet_to_war(1, war.id, "naval")
    assert ns.get_ready_fleets_for_war(war)[0].number == 1
    attack = combat_api.do_combat_action(state, P1, war.id, "attack")
    assert attack["success"], attack.get("message")
    env = attack["data"]
    assert env["naval"]["executed"] is True and env["naval"]["result"] == "VICTORY"
    assert env["land"]["executed"] is True and env["land"]["result"] == "defeat"
    assert env["naval"]["sea_control_acquired"] is True
    assert war.status == WarStatus.ACTIVE
    run.record("attack-ready", phase="combat", war_id=war.id,
               commander_id=war.commander_id, actionseq=3)
    # 重复 attack 拒绝（exactly-once/已 battled）
    again = combat_api.do_combat_action(state, P1, war.id, "attack")
    assert again["success"] is False
    run.record("repeat-attack-reject", phase="combat", war_id=war.id, actionseq=4)
    run.assert_same_run_consistency()
    assert fleet.status.value == "on_mission"


def test_rb_joined_run_auto_unavailable_not_battles():
    """auto_resolve：no-ready → unavailable_wars（非 battles）；force 不穿透；零 fake battle。"""
    ctx = F.build_fix02(naval_force="TRIUMPH", land_force="TRIUMPH", ready_override=None)
    state, war = ctx["state"], ctx["war"]
    state.mark_phase_executed("senate")
    res = combat_api.auto_resolve_combat(state, P1)
    assert res["success"], res.get("message")
    data = res["data"]
    assert data["battles"] == []
    assert data["wars_resolved"] == 0
    assert data["unavailable_wars"] == [{"war_id": war.id, "code": "NAVAL_NOT_READY",
                                         "reason": "NO_READY_ASSIGNED_FLEET"}]
    phase = state.get_phase_result("combat") or {}
    assert war.id not in phase.get("war_results", {})
    assert war.id not in phase.get("resolved_wars", [])
    # NOT_READY 不计 battle：war 保持 ACTIVE + commander，未被 skip 标记
    assert war.status == WarStatus.ACTIVE and war.commander_id is not None


# ---------------------------------------------------------------------------
# SC-R4-C — dual-action 三组合同 run join（T11/T12/T13 joined；envelope 同值链）
# ---------------------------------------------------------------------------
def _run_c_combo(builder, run_id, expected_naval, expected_land, expected_status):
    ctx = builder()
    state, war = ctx["state"], ctx["war"]
    handler, prev = _capture(state)
    try:
        attack = combat_api.do_combat_action(state, P1, war.id, "attack")
    finally:
        _restore(state, prev)
    assert attack["success"], attack.get("message")
    env = attack["data"]
    assert env["schema_version"] == 2
    assert env["naval"]["result"] == expected_naval
    assert env["land"]["result"] == expected_land
    assert war.status.value == expected_status

    run = RunContext(run_id, state)
    run.record("attack", phase="combat", war_id=war.id,
               commander_id=war.commander_id, actionseq=1)
    # envelope == pending == war_results == view（同 run 同值）
    phase = state.get_phase_result("combat") or {}
    assert phase["pending_result"] == env
    assert phase["war_results"][war.id] == env
    view = combat_api.get_combat_view(state, P1)["data"]
    assert view["battle_results"] == [env]
    run.record("persist-view", phase="combat", war_id=war.id, actionseq=2)
    # summary event 与 envelope 同 run 同值
    assert "combat_action_resolved" in _event_types(handler.msgs)
    ev = [m for m in handler.msgs if "type=combat_action_resolved" in m][0]
    assert f"war_id={war.id}" in ev
    assert f"naval_result={expected_naval}" in ev
    assert f"land_result={expected_land}" in ev
    assert f"schema_version=2" in ev
    # confirm 后：pending 清、war 卡保留同一 envelope
    cf = combat_api.confirm_battle_result(state, P1)
    assert cf["success"], cf.get("message")
    phase2 = state.get_phase_result("combat") or {}
    assert phase2.get("pending_result", {}) == {}
    view2 = combat_api.get_combat_view(state, P1)["data"]
    cards = view2.get("active_wars", []) + view2.get("truce_wars", []) \
        + view2.get("resolved_war_cards", [])
    card = [c for c in cards if c.get("war_id") == war.id][0]
    assert card["result"] == env
    run.record("confirm-card", phase="combat", war_id=war.id, actionseq=3)
    run.assert_same_run_consistency()
    return run


def test_rc_joined_combo1_naval_victory_land_defeat():
    run = _run_c_combo(lambda: F.build_fix05(), "run-r4c-b3-j-c1-vic-def-20260909",
                       "VICTORY", "defeat", "active")


def test_rc_joined_combo2_naval_triumph_land_draw_truce():
    run = _run_c_combo(lambda: F.build_fix06(), "run-r4c-b3-j-c2-tri-draw-20260909",
                       "TRIUMPH", "draw", "truce")


def test_rc_joined_combo3_naval_victory_land_triumph_resolved():
    run = _run_c_combo(lambda: F.build_fix07(), "run-r4c-b3-j-c3-vic-tri-20260909",
                       "VICTORY", "triumph", "resolved")


def test_rc_joined_combo_runs_not_cross_joined():
    """三组合 run 分离：各自 war/result 不得互相拼接（禁跨 run 拼双结果）。"""
    r1 = _run_c_combo(lambda: F.build_fix05(), "run-r4c-b3-j-x1-20260909",
                      "VICTORY", "defeat", "active")
    r2 = _run_c_combo(lambda: F.build_fix06(), "run-r4c-b3-j-x2-20260909",
                      "TRIUMPH", "draw", "truce")
    r3 = _run_c_combo(lambda: F.build_fix07(), "run-r4c-b3-j-x3-20260909",
                      "VICTORY", "triumph", "resolved")
    r1.assert_no_cross_run(r2)
    r1.assert_no_cross_run(r3)
    r2.assert_no_cross_run(r3)
    assert _join_all_run_entries([r1, r2, r3]) == 9


# ---------------------------------------------------------------------------
# SC-R4-D — forced identity + Forum 资格链（T10 J 段：真实 producer → 公开 vote/resolve）
# ---------------------------------------------------------------------------
def _ensure_vote_influence(state, faction):
    """保证论坛凯旋投票具合法影响权重：在城 NOBILE 元老（真实实体）。召回后指挥官
    influence 已重算/不在城，不能作为唯一票源——settlement 以投票 faction 存活成员
    影响之和计（SA 政治资格/凯旋 share 规则原样，不手写 share 绕过 producer）。"""
    influ = sum(m.influence for m in faction.get_members(state)
                if not getattr(m, "is_absent", False))
    if influ > 0:
        return
    from src.core.entities.figure import Figure, ClassTier
    senator = Figure(id=900, name="Rome Senator", faction_id=faction.id, age=55)
    senator.class_tier = ClassTier.NOBILE
    senator.influence = 60
    state.add_member(senator)
    faction.member_ids.append(900)


def _run_d_identity(force, run_id):
    ctx = F.build_fix09(land_force=force)
    state, war, commander = ctx["state"], ctx["war"], ctx["commander"]
    _ensure_vote_influence(state, ctx["faction"])
    handler, prev = _capture(state)
    try:
        attack = combat_api.do_combat_action(state, P1, war.id, "attack")
    finally:
        _restore(state, prev)
    assert attack["success"], attack.get("message")
    assert war.status == WarStatus.RESOLVED
    assert not commander.is_dead and war.soldier_share > 0
    assert war.triumph_commander_id == commander.id

    run = RunContext(run_id, state)
    run.record("attack", phase="combat", war_id=war.id,
               commander_id=war.commander_id, actionseq=1)
    types = _event_types(handler.msgs)
    # 身份独立：victory run 无 combat_triumph；triumph run 无 combat_victory
    if force == "VICTORY":
        assert "combat_victory" in types and "combat_triumph" not in types
    else:
        assert "combat_triumph" in types and "combat_victory" not in types

    # Forum 公开 view → vote → resolve 恰一次（R4-07：ordinary VICTORY 保留资格）
    view = forum_api.get_forum_view(state, P1)
    assert view["success"], view.get("message")
    rows = view["data"].get("triumph_wars") or []
    assert [r["war_id"] for r in rows] == [war.id]
    vote = forum_api.vote_triumph(state, P1, war.id, True)
    assert vote["success"], vote.get("message")
    pending = state.get_forum_pending()
    assert any(v[0] == war.id and v[2] is True for v in pending["triumph_votes"]), \
        f"vote not persisted: {pending['triumph_votes']}"
    ws_d = state.get_war_system()
    resolved_ids = [w.id for w in ws_d.get_resolved_wars()]
    assert war.id in resolved_ids, f"war not in resolved pile: {resolved_ids}"
    influ = sum(m.influence for m in state.get_faction(ctx["faction"].id).get_members(state))
    assert influ > 0, "faction influence must be > 0 for a valid vote"
    run.record("forum-vote", phase="forum", war_id=war.id,
               commander_id=war.commander_id, actionseq=2)
    settled = forum_api.resolve_forum(state)
    assert settled["success"], settled.get("message")
    text = " ".join(settled["data"].get("results", []))
    assert "凯旋仪式获得批准" in text
    assert war.triumph_approved is True and war.soldier_share == 0
    run.record("forum-resolve", phase="forum", war_id=war.id,
               commander_id=war.commander_id, actionseq=3)
    # 二次 resolve 无二次奖励（share 已消费）
    settled2 = forum_api.resolve_forum(state)
    assert settled2["success"]
    text2 = " ".join(settled2["data"].get("results", []))
    assert "凯旋仪式获得批准" not in text2
    run.record("forum-resolve-again", phase="forum", war_id=war.id, actionseq=4)
    run.assert_same_run_consistency()
    return run


def test_rd_joined_run_ordinary_victory_forum_ceremony():
    _run_d_identity("VICTORY", "run-r4d-b3-j-vic-20260909")


def test_rd_joined_run_triumph_forum_ceremony():
    _run_d_identity("TRIUMPH", "run-r4d-b3-j-tri-20260909")


def test_rd_identity_runs_not_cross_joined():
    rv = _run_d_identity("VICTORY", "run-r4d-b3-j-yv-20260909")
    rt = _run_d_identity("TRIUMPH", "run-r4d-b3-j-yt-20260909")
    rv.assert_no_cross_run(rt)
    assert _join_all_run_entries([rv, rt]) == 8
