# src/tests/fixtures/wpgr6_fixtures.py
"""WP-G-R6 DA-2 B6（SA-Design v1.1 §B.6）— F6 合法双 War fixture 族 + 双层取件 helper。

本模块是 **DA-2 计划产物**（DA-3 / DA-4 / DA-6 复用）：只构造真实实体与提交意图，
**不代跑业务**、不改写任何 R5 fixture（`wpgr5_fixtures.py` 名称/语义逐字保留）。

基面（SA v1.1 §B.6 逐条）：
- `wpgr5_fixtures.build_r5_base(turn_number, with_governor=False, with_passive=False)`：
  Consul `C1=1` 在城；`cmd_a=2`（ex-consul）、`cmd_b=3`（ex-praetor）；
  ongoing `pyrrhic_war`→2；pending-peace `first_punic_war`→3；
  `passive=null`；`threat_war` 未勾选（active declaration candidate）；
  Province 无 Governor/designate（无角色冲突）；权威池 = UNRAISED∪DISBANDED（默认 25）。

正例语义（§B.6 表）：
- **F6-DD**：pyrrhic command→2,N=1；first_punic command→3,N=2
  ⇒ `created=[]`、2 direct refs、claims={2,3}、pending treaty 未清。
- **F6-MIX**：pyrrhic command→2,N=1；threat command→1,N=2；first_punic unchecked→3
  ⇒ 1 direct + 1 Senate proposal、claims={2,1,3}、无提前宣战。
- **F6-VV**：threat command→1,N=1；first_punic Peace；pyrrhic unchecked→2
  ⇒ 2 Senate proposals、Peace 保留 claim 3、不依赖未来召回。
- **F6-ZERO-SWAP**：两真实 War 同将各 N=0（zero）；A→3 / B→2 各 N=0（swap）
  ⇒ 两组均成功；submit 阶段无换绑，swap 只边界生效。

纪律：真实 `GameState`/`War`/`Figure` 实体；force 键保持 committed 默认；
本模块零私有字段写入（除 `build_r5_base` 既有构造面）。
"""

from typing import Any, Dict, List, Optional

from src.tests.fixtures.wpgr5_fixtures import (  # noqa: F401  (re-export 供测试复用)
    build_r5_base,
    FIXED,
    command_draft,
    peace_draft,
    submit_request,
    error_codes,
    card_by_war,
)

#: 本批（DA-2 B6）登记的四条 F6 fixture 名称（DA-3/4/6 复用，不得改名）。
F6_NAMES = ("F6-DD", "F6-MIX", "F6-VV", "F6-ZERO-SWAP")


# ---------------------------------------------------------------------------
# 基面与只读观测
# ---------------------------------------------------------------------------
def pool_legion_ids(state) -> List[int]:
    """权威可征召池（UNRAISED ∪ DISBANDED）军团编号 —— 供 pool 证据逐 ID 复算。"""
    ms = state.get_military_system()
    return sorted(legion.number for legion in ms.get_available_legions())


def build_f6_base(turn_number: int = 1) -> Dict[str, Any]:
    """F6 基面（SA v1.1 §B.6：passive=null、Province 无 Governor、threat 未勾选）。"""
    ctx = build_r5_base(turn_number=turn_number, with_governor=False, with_passive=False)
    ctx["manifest"] = {
        "fixture": "F6-BASE",
        "fixed_ids": dict(FIXED),
        "turn": turn_number,
        "note": "真实 War command → consul_direct；THREAT active-declaration → senate_vote",
    }
    ctx["pool_ids"] = pool_legion_ids(ctx["state"])
    return ctx


def _command(ctx: Dict[str, Any], war_id: str, target_id: Optional[int], n: int,
             checked: bool = True) -> Dict[str, Any]:
    return command_draft(war_id, target_id, reinforcement_n=n, checked=checked)


# ---------------------------------------------------------------------------
# F6 正例 spec（可被判据逐条比较）
# ---------------------------------------------------------------------------
def f6_dd_spec(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """F6-DD：两真实 War 全 direct（无 Senate 提案）。"""
    return {
        "fixture": "F6-DD",
        "drafts": [
            _command(ctx, FIXED["war_ongoing"], ctx["cmd_a"].id, 1),
            _command(ctx, FIXED["war_peace"], ctx["cmd_b"].id, 2),
        ],
        "expect": {
            "created_count": 0,
            "direct_count": 2,
            "direct_war_ids": sorted([FIXED["war_ongoing"], FIXED["war_peace"]]),
            "claims": {FIXED["war_ongoing"]: ctx["cmd_a"].id,
                       FIXED["war_peace"]: ctx["cmd_b"].id},
            "sum_n": 3,
            "peace_treaty_status": "pending",
            "threat_status": "threat",
        },
    }


def f6_mix_spec(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """F6-MIX：1 direct（ongoing）+ 1 Senate proposal（threat 主动宣战）+ unchecked pending。"""
    return {
        "fixture": "F6-MIX",
        "drafts": [
            _command(ctx, FIXED["war_ongoing"], ctx["cmd_a"].id, 1),
            _command(ctx, FIXED["war_threat"], ctx["consul_id"], 2),
            _command(ctx, FIXED["war_peace"], ctx["cmd_b"].id, 0, checked=False),
        ],
        "expect": {
            "created_count": 1,
            "created_war_ids": [FIXED["war_threat"]],
            "direct_count": 1,
            "direct_war_ids": [FIXED["war_ongoing"]],
            "claims": {FIXED["war_ongoing"]: ctx["cmd_a"].id,
                       FIXED["war_threat"]: ctx["consul_id"],
                       FIXED["war_peace"]: ctx["cmd_b"].id},
            "sum_n": 3,
            "threat_status": "threat",  # 无提前宣战（Submit 不改军事/状态）
        },
    }


def f6_vv_spec(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """F6-VV：两 Senate 提案（主动宣战 + Peace），ongoing unchecked 保留 claim。"""
    return {
        "fixture": "F6-VV",
        "drafts": [
            _command(ctx, FIXED["war_threat"], ctx["consul_id"], 1),
            peace_draft(FIXED["war_peace"]),
            _command(ctx, FIXED["war_ongoing"], ctx["cmd_a"].id, 0, checked=False),
        ],
        "expect": {
            "created_count": 2,
            "created_war_ids": sorted([FIXED["war_threat"], FIXED["war_peace"]]),
            "direct_count": 0,
            "claims": {FIXED["war_threat"]: ctx["consul_id"],
                       FIXED["war_peace"]: ctx["cmd_b"].id,
                       FIXED["war_ongoing"]: ctx["cmd_a"].id},
            "sum_n": 1,
            "peace_treaty_status": "pending",
        },
    }


_F6_SPEC_BUILDERS = {"F6-DD": f6_dd_spec, "F6-MIX": f6_mix_spec, "F6-VV": f6_vv_spec}


def build_f6(name: str, turn_number: int = 1) -> Dict[str, Any]:
    """按名称构造 F6 正例（返回 ctx + drafts + expect + manifest）。"""
    if name == "F6-ZERO-SWAP":
        return build_f6_zero_swap(turn_number=turn_number)
    if name not in _F6_SPEC_BUILDERS:
        raise ValueError(f"unknown F6 fixture: {name!r} (known: {F6_NAMES})")
    ctx = build_f6_base(turn_number=turn_number)
    ctx.update(_F6_SPEC_BUILDERS[name](ctx))
    ctx["manifest"]["fixture"] = name
    return ctx


def build_f6_zero_swap(turn_number: int = 1) -> Dict[str, Any]:
    """F6-ZERO-SWAP：两组独立基面（zero = 各保留原将 N=0；swap = 交换将 N=0）。

    两组各自 fresh state（submit 会期唯一性 = `by_session`，「one package per session」），
    故不可在同一 state 上连跑。
    """
    zero = build_f6_base(turn_number)
    zero.update({
        "variant": "zero",
        "drafts": [
            _command(zero, FIXED["war_ongoing"], zero["cmd_a"].id, 0),
            _command(zero, FIXED["war_peace"], zero["cmd_b"].id, 0),
        ],
        "expect": {
            "created_count": 0, "direct_count": 2, "sum_n": 0,
            "claims": {FIXED["war_ongoing"]: zero["cmd_a"].id,
                       FIXED["war_peace"]: zero["cmd_b"].id},
        },
    })
    zero["manifest"]["fixture"] = "F6-ZERO-SWAP/zero"

    swap = build_f6_base(turn_number)
    swap.update({
        "variant": "swap",
        "drafts": [
            _command(swap, FIXED["war_ongoing"], swap["cmd_b"].id, 0),
            _command(swap, FIXED["war_peace"], swap["cmd_a"].id, 0),
        ],
        "expect": {
            "created_count": 0, "direct_count": 2, "sum_n": 0,
            "claims": {FIXED["war_ongoing"]: swap["cmd_b"].id,
                       FIXED["war_peace"]: swap["cmd_a"].id},
        },
    })
    swap["manifest"]["fixture"] = "F6-ZERO-SWAP/swap"

    return {"fixture": "F6-ZERO-SWAP", "manifest": {"fixture": "F6-ZERO-SWAP"},
            "variants": {"zero": zero, "swap": swap}}


# ---------------------------------------------------------------------------
# 双层提交 helper（API 层 / GUI 层）—— DA-2 B6 的「至少两层」取件面
# ---------------------------------------------------------------------------
def submit_api(state, drafts: List[Dict[str, Any]], session_id: str = "S1",
               request_id: str = "req-1", player_id: str = FIXED["player"]) -> Dict[str, Any]:
    """API 层：`senate_api.propose_many`（唯一整包提交门面）。"""
    from src.api import senate_api
    request = submit_request(war_drafts=list(drafts), session=session_id, request_id=request_id)
    return senate_api.propose_many(state, player_id, request)


def submit_gui(state, drafts: List[Dict[str, Any]], player_id: str = FIXED["player"]):
    """GUI 层：`GuiSessionStore.initialize` → `doSubmitSenateProposals`（Store→Adapter→API）。

    返回 `(store, feedback)`；store 已刷新 `senate_view`（成功路径）。
    """
    from src.ui.gui.session_store import GuiSessionStore
    store = GuiSessionStore(state)
    store.initialize(player_id)
    feedback = store.doSubmitSenateProposals(list(drafts))
    return store, feedback


def frozen_record(state, result: Dict[str, Any], session_id: Optional[str] = None,
                  pool_before: Optional[List[int]] = None) -> Dict[str, Any]:
    """把一次 Submit 回包 → 可复算证据记录（created / direct refs / claims / pool / errors / refs）。"""
    data = result.get("data") or {}
    created = data.get("created") or []
    direct = data.get("direct_decisions") or []
    package_id = data.get("package_id")
    context_id = data.get("submission_context_id")
    session_id = session_id or state.get_senate_session()
    record = state.get_senate_package_record(package_id) if package_id else None
    context = state.get_submission_context(context_id) if context_id else None
    # 权威账本（route/authority 的唯一来源：Senate 提案集 + consul_war_decisions）
    proposal_ledger = {p.get("id"): p for p in state.get_senate_proposals()}
    direct_ledger = state.get_consul_war_decisions(session_id) or {}
    claims = {}
    drafts = []
    if context:
        claims = {c["war_id"]: {"commander_id": c["commander_id"], "basis": c["basis"]}
                  for c in context.get("claims", [])}
        drafts = context.get("submitted_drafts", []) or []
    checked_command_n = sum(int(d.get("reinforcement_n") or 0) for d in drafts
                            if d.get("checked") and d.get("mode") == "command")

    def _direct_row(d):
        rec = direct_ledger.get(d.get("direct_decision_id"), {}) or {}
        payload = rec.get("payload") or d.get("payload") or {}
        return {"war_id": rec.get("war_id") or d.get("war_id"),
                "direct_decision_id": d.get("direct_decision_id"),
                "authority": rec.get("authority"),
                "decision_state": rec.get("decision_state"),
                "has_proposal_id": "proposal_id" in rec,
                "target_commander_id": payload.get("target_commander_id"),
                "reinforcement_n": payload.get("reinforcement_n")}

    def _created_row(c):
        rec = proposal_ledger.get(c.get("proposal_id"), {}) or {}
        return {"war_id": c.get("war_id"), "proposal_id": c.get("proposal_id"),
                "authority": rec.get("authority"), "mode": rec.get("mode"),
                "type": rec.get("type")}

    return {
        "success": bool(result.get("success")),
        "message": result.get("message"),
        "errors": error_codes(result),
        "session_id": session_id,
        "package_id": package_id,
        "submission_context_id": context_id,
        "created": [_created_row(c) for c in created],
        "direct_decisions": [_direct_row(d) for d in direct],
        "proposal_refs": (record or {}).get("proposal_refs"),
        "direct_decision_refs": (record or {}).get("direct_decision_refs"),
        "package_record_state": (record or {}).get("publication_state"),
        "claims": claims,
        "proposal_ledger": [_created_row(c) for c in
                            ({"war_id": p.get("war_id"), "proposal_id": p.get("id")}
                             for p in state.get_senate_proposals())],
        "submitted_drafts": [{"war_id": d.get("war_id"), "checked": d.get("checked"),
                              "mode": d.get("mode"),
                              "target_commander_id": d.get("target_commander_id"),
                              "reinforcement_n": d.get("reinforcement_n")} for d in drafts],
        "checked_command_n": checked_command_n,
        "war_items": sorted(str(k) for k in (state.get_senate_war_items(session_id) or {})),
        "pool_ids": pool_before if pool_before is not None else pool_legion_ids(state),
        "pool_after": pool_legion_ids(state),
    }


#: 判据断言 helper（DA-3/4/6 复用）：把 record 与 expect 逐条比对。
def check_expect(record: Dict[str, Any], expect: Dict[str, Any]) -> List[str]:
    """返回不满足项清单（空 = 全部通过）。不抛异常，供证据报告逐条登记。"""
    problems: List[str] = []
    if not record.get("success"):
        problems.append(f"submit failed: {record.get('errors')}")
        return problems
    if "created_count" in expect and len(record["created"]) != expect["created_count"]:
        problems.append(f"created_count {len(record['created'])} != {expect['created_count']}")
    if "direct_count" in expect and len(record["direct_decisions"]) != expect["direct_count"]:
        problems.append(f"direct_count {len(record['direct_decisions'])} != {expect['direct_count']}")
    if "created_war_ids" in expect:
        got = sorted(c["war_id"] for c in record["created"])
        if got != sorted(expect["created_war_ids"]):
            problems.append(f"created_war_ids {got} != {sorted(expect['created_war_ids'])}")
    if "direct_war_ids" in expect:
        got = sorted(d["war_id"] for d in record["direct_decisions"])
        if got != sorted(expect["direct_war_ids"]):
            problems.append(f"direct_war_ids {got} != {sorted(expect['direct_war_ids'])}")
    if "claims" in expect:
        want = {k: v for k, v in expect["claims"].items()}
        for war_id, commander_id in want.items():
            got = record["claims"].get(war_id)
            if not got or got["commander_id"] != commander_id:
                problems.append(f"claim[{war_id}] {got} != commander {commander_id}")
    if "sum_n" in expect:
        total = record.get("checked_command_n")
        if total != expect["sum_n"]:
            problems.append(f"sum_n {total} != {expect['sum_n']}")
    return problems
