"""
战斗阶段 API
提供战斗阶段的只读视图、战斗操作和推进接口。
"""

import random
import logging
from typing import Any, Dict, List, Optional

from src.api import api_response
from src.core.game_state import GameState
from src.core.entities.war import War, WarStatus
from src.core.entities.fleet import FleetStatus


logger = logging.getLogger("EOR-CombatAPI")

# GUI/API 战斗结果词 → decider canonical 词（对齐 CLI STALEMATE，落地 L151 注释契约）
# 复用既有 decider 白名单语义，不新增第四套结果模型。
_COMBAT_RESULT_CANONICAL = {
    "triumph": "TRIUMPH",
    "victory": "VICTORY",
    "draw": "STALEMATE",
    "defeat": "DEFEAT",
    "disaster": "DISASTER",
}

# R1-G-01（WP-G-R1 v1.6 §2.1，S1）：land forced-result 词表归一（fail-closed）。
# `testing.force_battle_result` 是既有调试配置，本次由 `_compute_combat_result`（canonical
# 唯一结果选择点）消费；"stalemate" 与 GUI "draw" 同义（对齐 CLI STALEMATE）。
# 未命中/非法/空/缺省 → None → 正常 2d6 CRT 分类（红线 R1-09：无生产默认 STALEMATE）。
_FORCED_RESULT_MAP = {
    "stalemate": "draw",
    "draw": "draw",
    "triumph": "triumph",
    "victory": "victory",
    "defeat": "defeat",
    "disaster": "disaster",
}


def _normalize_forced_result(value: Any) -> Optional[str]:
    """R1-G-01：land forced-result 归一化（大小写/空格容忍；非 str / 非法值 → None）。"""
    if not isinstance(value, str):
        return None
    return _FORCED_RESULT_MAP.get(value.strip().lower())



# ════════════════════════════════════════════════════════════════════════
# 内部辅助
# ════════════════════════════════════════════════════════════════════════

def _war_system(state: GameState):
    return state.get_war_system()


def _military_system(state: GameState):
    return state.get_military_system()


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


# WP-G-R4 (SA v1.7 §3.1/§3.3)：Naval readiness gate helper（单一事实源 =
# NavalSystem.get_ready_fleets_for_war）。返回 (code, reason)——code None = gate 不要求或已就绪。
def _naval_attack_readiness(state: GameState, war: War):
    if not (war.naval_required and not war.sea_control_acquired):
        return None, None
    ns = getattr(state, "naval_system", None)
    if ns is None:
        return "NAVAL_SYSTEM_UNAVAILABLE", "NavalSystem unavailable (fail-closed)"
    ready = ns.get_ready_fleets_for_war(war)
    if not ready:
        return "NAVAL_NOT_READY", "NO_READY_ASSIGNED_FLEET"
    return None, None


def _naval_not_ready_dto(war: War, reason: str) -> Dict[str, Any]:
    """NOT_READY 非战 envelope（SA v1.7 §5.1 未执行语义：不写 battle 数值/损失）。"""
    return {
        "schema_version": 2,
        "war_id": war.id,
        "war_name": war.name,
        "action": "attack",
        "action_status": "readiness_rejected",
        "result_stage": "readiness",
        "result": "NAVAL_NOT_READY",
        "result_label": "海军未就绪",
        "naval": {
            "required": True,
            "gate_required": True,
            "executed": False,
            "status": "NOT_READY",
            "reason": reason or "NO_READY_ASSIGNED_FLEET",
            "sea_control_acquired": False,
        },
        "land": {
            "executed": False,
            "status": "NOT_EXECUTED",
            "reason": "NAVAL_NOT_READY",
        },
        "war_outcome": {
            "status_after": war.status.value if hasattr(war.status, "value") else str(war.status),
            "terminal_success": False,
            "sea_control_after": bool(war.sea_control_acquired),
            "combat_duration_delta": 0,
        },
    }


_ATTACK_DISABLED_TEXT = {
    "NAVAL_NOT_READY": "未就绪：本战无已指派可用舰队",
    "NAVAL_SYSTEM_UNAVAILABLE": "海军系统不可用（技术失败，阻断攻击）",
}


def _attack_capability_fields(war: War, state: GameState) -> Dict[str, Any]:
    code, reason = _naval_attack_readiness(state, war)
    available = code is None
    return {
        "attack_available": available,
        "attack_disabled_code": code,
        "attack_disabled_reason": "" if available else (_ATTACK_DISABLED_TEXT.get(code, reason or code)),
    }


def _war_card(war: War, state: GameState) -> Dict[str, Any]:
    """Build a single war_card dict for the CombatView DTO."""
    commander_name = ""
    commander_martial = 0
    commander_id = -1
    commander = None
    if war.commander_id is not None:
        commander = state.get_member(war.commander_id)
        if commander:
            commander_name = commander.get_formal_name() if hasattr(commander, 'get_formal_name') else commander.name or ""
            commander_martial = getattr(commander, 'martial', 0) or 0
            commander_id = war.commander_id

    # POST-07P（ODR-A/B）：计数/番号源 = 实时军团实体附着（legion.war_id == war.id）。
    # 镜像字段（legions_assigned / legion_numbers）仅兼容 debug：GUI 生产路径恒 0/
    # 召回后残留旧号，禁以其判定存在性或作战斗权威（R-17 / N 件）。
    ms = _military_system(state)
    attached = ms.get_legions_for_battle(war.id) if ms else []
    legion_count = len(attached)
    # R-17（G2-C §2，WP-G GB）：战力 = live 实体 Σ get_combat_strength()
    # （含 veteran +1，MVP0.3-03 §3.4 既有规则；GUI canonical 路径此前漏应用 = 收敛，非新规则）
    legion_power = sum(l.get_combat_strength() for l in attached)
    total_power = commander_martial + legion_power
    enemy_power = war.get_total_strength()

    # R1-G-08（WP-G-R1 v1.6 §2.8，P2-02/G5）：per-war `assigned_fleet_count`/`naval_ready`
    # （read-model 唯一 schema）。归属作用域 = war._assigned_fleet_ids（指派本战的编号）；
    # 计入状态集 = **显式 status == ON_MISSION**（live Fleet 实体为准）——不再用「排除
    # BUILDING/DESTROYED/DISBANDED」补集谓词（旧式补集理论上允许残留 AVAILABLE/
    # IN_COMBAT 误计）。镜像字段 war.fleets_assigned 恒 0/不可靠，禁生产权威（POST-07P
    # 同款 live-实体原则）。R3-G-04（§4.5）：strength 分层读模型同源（单一实现
    # NavalSystem.get_war_fleet_strength_read_model）。
    assigned_fleet_count = 0
    fleet_read_model: Dict[str, Any] = {
        "assigned_fleet_ids": [],
        "fleet_nominal_strength": 0,
        "fleet_quality_adjusted_base": 0,
        "fleet_experience_bonus": 0,
        "fleet_commander_bonus": 0,
        "fleet_effective_combat_strength": 0,
        "fleet_strength_packages": [],
    }
    ns = getattr(state, "naval_system", None)
    if ns is not None:
        fleet_read_model = ns.get_war_fleet_strength_read_model(war)
    assigned_fleet_count = len(fleet_read_model["assigned_fleet_ids"])
    naval_ready = assigned_fleet_count >= 1

    return {
        "war_id": war.id,
        "name": war.name,
        "enemy_name": war.name,  # FC-3: DTO 别名（复用 War.name，非新实体字段）
        "war_type": war.war_type.value,
        "commander_name": commander_name,
        "commander_martial": commander_martial,
        "commander_id": commander_id,
        "commander_faction_id": commander.faction_id if commander else None,
        "legion_count": legion_count,
        "legion_numbers": [legion.number for legion in attached],
        "total_power": total_power,
        "enemy_power": enemy_power,
        "threat_level": war.threat_level,
        "status": war.status.value if hasattr(war.status, 'value') else str(war.status),
        "has_commander": commander_id >= 0,
        # R1-G-08（WP-G-R1 v1.6 §2.8）：per-war 舰队就绪权威字段（war card / combat view
        # war 条目同源透传；GUI 改读本字段，不再读 stale 镜像）
        "assigned_fleet_count": assigned_fleet_count,
        "naval_ready": naval_ready,
        # R3-G-04（§4.5）：strength 分层读模型字段（有效强度只对该战已完成已指派舰队聚合）
        "assigned_fleet_ids": fleet_read_model["assigned_fleet_ids"],
        "fleet_nominal_strength": fleet_read_model["fleet_nominal_strength"],
        "fleet_quality_adjusted_base": fleet_read_model["fleet_quality_adjusted_base"],
        "fleet_experience_bonus": fleet_read_model["fleet_experience_bonus"],
        "fleet_commander_bonus": fleet_read_model["fleet_commander_bonus"],
        "fleet_effective_combat_strength": fleet_read_model["fleet_effective_combat_strength"],
        "fleet_strength_packages": fleet_read_model["fleet_strength_packages"],
        # WP-E F7（E-G7-11）：TRUCE 剩余回合权威计算（禁 QML 猜测 R-05）
        "truce_end_turn": war.truce_end_turn,
        "truce_remaining_turns": (
            max(0, war.truce_end_turn - state.turn.turn_number)
            if war.truce_end_turn
            else None
        ),
        # K 件 §5（WP-G GC）：海军门状态 DTO 透出（禁 QML 推断 R-01；CombatStage 展示 = WP-F）
        "naval_required": war.naval_required,
        "sea_control_acquired": war.sea_control_acquired,
        # WP-G-R4 (SA v1.7 §3.3)：attack capability（同一 gate helper；NOT_READY = 可显式 advance）
        **_attack_capability_fields(war, state),
    }


def _build_battle_result(
    war: War,
    state: GameState,
    dice: int,
    total_attack: int,
    enemy_defence: int,
    result: str,
    loot: int,
    losses: int,
    triumph: bool,
    casualty_numbers: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Build a battle_result DTO."""
    label_map = {
        "triumph": "🏆 大胜！",
        "victory": "⚔️ 胜利",
        "draw": "🤝 僵持",
        "defeat": "😞 战败",
        "disaster": "💀 灾难",
    }
    result_label = label_map.get(result, result)

    # Compute loot shares using standard formula
    treasury_share = int(loot * 0.50)
    faction_share = int(loot * 0.25)
    commander_share_value = int(loot * 0.15)
    soldier_share = loot - treasury_share - faction_share - commander_share_value

    return {
        "war_id": war.id,
        "war_name": war.name,
        "result": result,
        "result_label": result_label,
        "dice": dice,
        "total_attack": total_attack,
        "enemy_defence": enemy_defence,
        "total_score": total_attack - enemy_defence,
        "losses": losses,
        # WP-G GB（S2，G1-05/06/07）：伤亡编号列表（向后兼容增量；GUI 现有
        # `losses` 字段语义不变 = 伤亡数，CombatStage.qml 零改）
        "casualty_numbers": list(casualty_numbers) if casualty_numbers else [],
        "triumph": triumph,
        "loot": loot,
        "treasury_share": treasury_share,
        "commander_share": commander_share_value,
        "faction_share": faction_share,
        "soldier_share": soldier_share,
    }


def _build_naval_block_result(
    war: War,
    state: GameState,
    naval_result: str,
    details: Dict[str, Any],
    participating: Optional[List[int]] = None,
    casualty_ids: Optional[List[int]] = None,
    sea_before: bool = False,
    duration_delta: int = 1,
) -> Dict[str, Any]:
    """海战阻断 v2 envelope（WP-G-R4 S3，SA v1.7 §5.1/§5.3 例 4：真实 Naval block 仅
    Naval 结果，Land 明确未执行，无假 0-vs-0——R4-05 omitted keys 非 null 非 0）。

    supersede WP-G GC `_build_naval_block_result`（顶层 land 零值面：dice:0/total_attack:0/
    losses:roman 等）——SA v1.7 §1 G03/§5.1 兼容窗口：land=false 删除全部顶层 Land 统计；
    顶层 result 只能显式 naval summary（naval_stalemate/naval_defeat/naval_disaster），
    禁把 Naval 损失放顶层 losses。land_battle 仅保留 deprecated presentation alias。
    """
    result_map = {
        "TRIUMPH": ("naval_triumph", "🏆 海战大胜"),
        "VICTORY": ("naval_victory", "⚔️ 海战胜利"),
        "STALEMATE": ("naval_stalemate", "⚓ 海战僵持（无法登陆）"),
        "DEFEAT": ("naval_defeat", "⚓ 海战战败（无法登陆）"),
        "DISASTER": ("naval_disaster", "⚓ 海战灾难（无法登陆）"),
    }
    summary, label = result_map.get(naval_result, (f"naval_{naval_result.lower()}", naval_result))
    naval_label_map = {
        "TRIUMPH": "海战大胜", "VICTORY": "海战胜利", "STALEMATE": "海战僵持",
        "DEFEAT": "海战战败", "DISASTER": "海战灾难",
    }
    if not isinstance(details, dict):
        details = {}
    roman_losses = details.get("roman_losses", 0) or 0
    part = list(participating) if participating else list(
        details.get("participating_fleet_ids", []) or [])
    if not part:
        part = list(getattr(war, "_assigned_fleet_ids", None) or [])
    cas = list(casualty_ids) if casualty_ids else list(
        details.get("casualty_fleet_ids", []) or [])
    if not cas and naval_result in ("DEFEAT", "DISASTER"):
        # 真实损失差集回退：未提供时按参战集 − 当前仍指派集（阻断路径无 recall，差集即阵亡）
        remaining = set(getattr(war, "_assigned_fleet_ids", None) or [])
        cas = [fid for fid in part if fid not in remaining]
    cas = sorted(set(cas))
    return {
        "schema_version": 2,
        "war_id": war.id,
        "war_name": war.name,
        "action": "attack",
        "turn": state.turn.turn_number if state.turn else 0,
        "phase": "combat",
        "action_status": "naval_blocked",
        "result_stage": "naval",
        "result": summary,
        "result_label": label,
        "naval": {
            "required": bool(war.naval_required),
            "gate_required": True,
            "executed": True,
            "status": "RESOLVED",
            "result": naval_result,
            "result_label": naval_label_map.get(naval_result, naval_result),
            "roman_losses": roman_losses,
            "enemy_losses": details.get("enemy_loss", 0) or 0,
            "participating_fleet_ids": sorted(part),
            "casualty_fleet_ids": cas,
            "sea_control_before": bool(sea_before),
            "sea_control_acquired": bool(details.get("sea_control_acquired", False)),
        },
        "land": {
            "executed": False,
            "status": "NOT_EXECUTED",
            "reason": "NAVAL_GATE_BLOCKED",
        },
        "war_outcome": {
            "status_after": war.status.value if hasattr(war.status, "value") else str(war.status),
            "terminal_success": False,
            "sea_control_after": bool(war.sea_control_acquired),
            "combat_duration_delta": int(duration_delta),
        },
        "land_battle": "blocked",
    }


def _v2_naval_not_executed_stage(war: War, reason: str) -> Dict[str, Any]:
    """Naval 未执行 stage（§5.1：不写 battle 结果/损失——omitted keys，非 null 非 0 占位）。
    reason ∈ NOT_REQUIRED / SEA_CONTROL_ALREADY_ACQUIRED。"""
    return {
        "required": bool(war.naval_required),
        "gate_required": False,
        "executed": False,
        "status": "NOT_EXECUTED",
        "reason": reason,
        "sea_control_before": bool(war.sea_control_acquired),
        "sea_control_acquired": bool(war.sea_control_acquired),
    }


def _v2_land_executed_stage(flat: Dict[str, Any]) -> Dict[str, Any]:
    """Land 已执行 stage（从旧顶层 flat DTO 派生——值逐项相同，兼容窗口 §5.1）。"""
    stage = {
        "executed": True,
        "status": "RESOLVED",
    }
    for key in ("result", "result_label", "dice", "total_attack", "enemy_defence",
                "total_score", "losses", "casualty_numbers", "triumph", "loot",
                "treasury_share", "faction_share", "commander_share", "soldier_share"):
        if key in flat:
            stage[key] = flat[key]
    return stage


def _v2_finalize_land_envelope(
    war: War,
    state: GameState,
    flat: Dict[str, Any],
    naval_stage: Dict[str, Any],
    duration_delta: int,
    land_battle_alias: str,
) -> Dict[str, Any]:
    """land.executed=true 单一 finalized envelope（§5.1/§5.2）：naval/land 并列 + 旧顶层
    land 纯 alias（值逐项相同）+ 顶层 summary + war_outcome。"""
    land_stage = _v2_land_executed_stage(flat)
    terminal_success = land_stage.get("result") in ("victory", "triumph")
    envelope = {
        "schema_version": 2,
        "war_id": war.id,
        "war_name": war.name,
        "action": "attack",
        "turn": state.turn.turn_number if state.turn else 0,
        "phase": "combat",
        "action_status": "land_resolved",
        "result_stage": "land",
        "result": land_stage.get("result"),
        "result_label": land_stage.get("result_label"),
        "naval": naval_stage,
        "land": land_stage,
        "war_outcome": {
            "status_after": war.status.value if hasattr(war.status, "value") else str(war.status),
            "terminal_success": terminal_success,
            "sea_control_after": bool(war.sea_control_acquired),
            "combat_duration_delta": int(duration_delta),
        },
        "land_battle": land_battle_alias,
    }
    # 兼容窗口：顶层旧 land 字段纯 alias（值逐项相同）——供旧测试/消费者
    for key in ("dice", "total_attack", "enemy_defence", "total_score", "losses",
                "casualty_numbers", "triumph", "loot", "treasury_share", "faction_share",
                "commander_share", "soldier_share"):
        if key in flat:
            envelope[key] = flat[key]
    return envelope


def _emit_combat_action_resolved(state: GameState, war: War, envelope: Dict[str, Any]) -> None:
    """纯观察 summary event（§5.4：动作总结，非第三场 battle；不额外奖励/计数；NOT_READY 不发）。"""
    naval = envelope.get("naval", {}) or {}
    land = envelope.get("land", {}) or {}
    outcome = envelope.get("war_outcome", {}) or {}
    state.log_event(
        f"战斗结算: {war.name}",
        level=logging.INFO,
        extra={
            "type": "combat_action_resolved",
            "turn": envelope.get("turn", 0),
            "phase": envelope.get("phase", "combat"),
            "war_id": war.id,
            "action_status": envelope.get("action_status"),
            "naval_executed": naval.get("executed"),
            "naval_result": naval.get("result") or naval.get("status"),
            "land_executed": land.get("executed"),
            "land_result": land.get("result") or land.get("reason"),
            "terminal_success": outcome.get("terminal_success"),
            "schema_version": envelope.get("schema_version"),
        },
    )


def _persist_combat_envelope(state: GameState, war: War, envelope: Dict[str, Any]) -> None:
    """§5.4：同一完整 envelope 持久进 pending_result + war_results[war_id]；battled id 恰一次。"""
    phase_data = state.get_phase_result("combat") or {}
    if not isinstance(phase_data, dict):
        phase_data = {}
    phase_data["pending_result"] = envelope
    resolved = list(phase_data.get("resolved_wars", []))
    if war.id not in resolved:
        resolved.append(war.id)
    phase_data["resolved_wars"] = resolved
    phase_data["selected_war_id"] = war.id
    war_results = phase_data.get("war_results", {})
    if not isinstance(war_results, dict):
        war_results = {}
    war_results[war.id] = envelope
    phase_data["war_results"] = war_results
    state.record_phase_result("combat", phase_data)


def _compute_combat_result(
    war: War,
    state: GameState,
    dice: int,
    action: str,
) -> Dict[str, Any]:
    """
    Core combat formula.
    Returns a dict with result, total_attack, enemy_defence, loot, losses, triumph.
    """
    # Commander bonus
    commander_martial = 0
    if war.commander_id is not None:
        commander = state.get_member(war.commander_id)
        if commander:
            commander_martial = getattr(commander, 'martial', 0) or 0

    # Legion power — R-17（G2-C §2，WP-G GB）：live Legion 实体附着为唯一参与者/战力源；
    # 镜像字段（legions_assigned / legion_numbers）仅兼容 debug，禁战斗权威（N 件）
    ms = _military_system(state)
    attached = ms.get_legions_for_battle(war.id) if ms else []
    legion_power = sum(l.get_combat_strength() for l in attached)

    # Apply action modifiers
    action_bias = 0
    if action == "defence":
        action_bias = 2  # Defensive stance gives +2
    elif action == "scout":
        action_bias = -1  # Scout is preview-only, slight penalty

    total_attack = dice + commander_martial + legion_power + action_bias
    enemy_defence = war.get_total_strength()
    score = total_attack - enemy_defence

    # Result classification — thresholds read from Config combat_rules (FC-2 / DEV-04).
    # Aligned with CLI phase_combat._simplified_crt: TRIUMPH(>=12) / VICTORY(>=6) /
    # STALEMATE(standoff_roll or -3<=score<6) / DEFEAT(<-3). GUI "draw" == CLI "STALEMATE".
    triumph_threshold = state.config.get("combat_rules.triumph_threshold", 12)
    victory_threshold = state.config.get("combat_rules.victory_threshold", 6)
    defeat_threshold = state.config.get("combat_rules.defeat_threshold", -3)

    # R1-G-01（WP-G-R1 v1.6 §2.1，S1）：单一 canonical override 消费点——强制结果在 CRT
    # 分类之前短路（stalemate/draw/triumph/victory/defeat/disaster 五词）；空/缺省/非法 →
    # None → 正常 2d6 CRT 分类。losses / loot / triumph 计算与 post-result mutation
    # （do_combat_action 四分支）原样复用，forced 结果走同一条 canonical 生命周期。
    forced = _normalize_forced_result(
        state.config.get("testing.force_battle_result", "")
    )
    if forced is not None:
        result = forced
    elif war.is_disaster_roll(dice):
        result = "disaster"
    elif score >= triumph_threshold:
        result = "triumph"
    elif score >= victory_threshold:
        result = "victory"
    elif war.is_standoff_roll(dice) or defeat_threshold <= score < victory_threshold:
        result = "draw"
    elif score < defeat_threshold:
        result = "defeat"
    else:
        result = "draw"

    # Losses — G1-05/06/07（G2-C §4 冻结数学）：伤亡源 = live 参战集；
    # DEFEAT: ceil(N/2) 随机无放回；DISASTER: 全灭；其余 0
    N = len(attached)
    losses = 0
    if result == "disaster":
        losses = N
    elif result == "defeat":
        losses = N - N // 2  # = ceil(N/2)（G1-06：1→1, 2→1, 3→2, 4→2, 5→3, 6→3）

    # Loot (only for non-disaster)
    loot = 0
    triumph = False
    if result != "disaster" and result != "defeat":
        rewards = war.calculate_rewards()
        loot = rewards.get("treasury", 0)
        if result == "triumph":
            triumph = True
            # Triumph gives bonus loot
            loot = int(loot * 1.5)

    return {
        "result": result,
        "total_attack": total_attack,
        "enemy_defence": enemy_defence,
        "loot": loot,
        "losses": losses,
        "triumph": triumph,
        "dice": dice,
        "commander_martial": commander_martial,
        "legion_power": legion_power,
    }


def _apply_loss_consequence(war: War, result: str, state: GameState) -> None:
    """应用战败/灾难后果（INV-C3：LOSS 后 war 保持 ACTIVE，不 resolve、不 discard）。

    语义对齐 CLI legacy `phase_combat._apply_battle_result`（DEFEAT/DISASTER 分支）：
    - defeat：指挥官伤损（fled/captured/wounded 概率）+ 离开战场（commander_id=None）
    - disaster：指挥官阵亡（mark_member_dead + report_commander_casualty("killed")）
    - war.duration += 1（战争拖延惩罚）
    - 不调用 resolve_war、不入 _war_discard、status 保持 ACTIVE → 下回合（新 Combat
      阶段）仍可战（INV-C3）；commander 离开是「后果」而非无差别清空战争。
    """
    current_turn = state.turn.turn_number if state.turn else 0
    commander = state.get_member(war.commander_id) if war.commander_id is not None else None

    if result == "disaster":
        if commander and not commander.is_dead:
            state.mark_member_dead(commander.id, transfer_land=True, transfer_wealth=True)
        war.report_commander_casualty("killed", current_turn)
        war.commander_id = None
        war.legions_assigned = 0
        war.fleets_assigned = 0
        state.log_event(
            f"💀 战斗灾难: {war.name}",
            extra={
                "type": "combat_disaster",
                "war_id": war.id,
                "war_name": war.name,
                "result": result,
            },
        )
    else:  # defeat
        roll = random.random()
        if roll < 0.3:
            war.report_commander_casualty("fled", current_turn)
        elif roll < 0.5:
            war.report_commander_casualty("captured", current_turn)
        else:
            war.report_commander_casualty("wounded", current_turn)
        war.commander_id = None
        state.log_event(
            f"战斗战败: {war.name}",
            extra={
                "type": "combat_defeat",
                "war_id": war.id,
                "war_name": war.name,
                "result": result,
            },
        )
    war.duration += 1


def _actionable_wars(ws, phase_data, state=None) -> List[War]:
    """本回合仍可战斗的 ACTIVE 战争：有指挥官且未在本回合战斗（resolved_wars）。

    INV-C3/Δ6 单点真值（U2/U6 共用）：LOSS 后 war 仍 ACTIVE，但 commander 已
    离场/阵亡 → 视同无需再战（与 `_skip_all_unassigned` 语义一致）；TRUCE war
    不在 get_active_wars()，天然不计入。
    WP-G-R4 (SA v1.7 §3.4)：海军门正常 NOT_READY（或技术 UNAVAILABLE）战争不计入
    「可执行战斗」——同 gate helper，不新增跳过布尔 ledger；显式 advance 不受阻。
    """
    if not ws:
        return []
    battled_ids = (
        set(phase_data.get("resolved_wars", []))
        if isinstance(phase_data, dict)
        else set()
    )
    result = []
    for w in ws.get_active_wars():
        if w.commander_id is None or w.id in battled_ids:
            continue
        if state is not None:
            code, _reason = _naval_attack_readiness(state, w)
            if code is not None:
                continue  # NOT_READY / UNAVAILABLE：不阻塞 advance，但也非可执行战斗
        result.append(w)
    return result


def _all_battled(ws, phase_data, state=None) -> bool:
    """advance 谓词：全部可战斗战争（有指挥官且未战且 readiness 通过）已结算。"""
    return len(_actionable_wars(ws, phase_data, state=state)) == 0


def _build_war_slots(
    war_cards: List[Dict[str, Any]],
    truce_cards: List[Dict[str, Any]],
    resolved_war_cards: List[Dict[str, Any]],
    ws,
) -> List[Optional[Dict[str, Any]]]:
    """构建 war_slots 有序 DTO（P1-01 槽位身份 + 有序输出）。

    - represented：全部非空卡，按 active → truce → resolved 插入序；
    - 惰性分配：combat_slot_index < 0 的 war 按插入序取最低空槽
      （基础 {0,1,2} 优先，满 3 后追加 max_slot+1 = overflow），并写回 war 实体
      持久化（槽位身份跨回合/存档保留）；
    - 输出 war_slots：长度 max(3, max_slot+1)，空槽填 None 占位，按 slot 排序。
    """
    represented = list(war_cards) + list(truce_cards) + list(resolved_war_cards)

    used_slots = set()
    for card in represented:
        slot = card.get("slot_index", -1)
        if slot is not None and slot >= 0:
            used_slots.add(slot)

    max_slot = max(used_slots) if used_slots else -1
    for card in represented:
        slot = card.get("slot_index", -1)
        if slot is None or slot < 0:
            slot = 0
            while slot in used_slots:
                slot += 1
            used_slots.add(slot)
            max_slot = max(max_slot, slot)
            card["slot_index"] = slot
            # 槽位身份写回 war 实体（持久化）
            war = ws.get_war_by_id(card.get("war_id")) if ws else None
            if war is not None:
                war.combat_slot_index = slot

    length = max(3, max_slot + 1)
    war_slots: List[Optional[Dict[str, Any]]] = [None] * length
    for card in represented:
        war_slots[card["slot_index"]] = card
    return war_slots


# ════════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════════

def get_combat_view(state: GameState, viewer_player_id: str) -> dict:
    """Return read-only combat stage DTO."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        ws = _war_system(state)
        ms = _military_system(state)
        ns = state.naval_system

        active_wars = ws.get_active_wars() if ws else []
        # R1-G-08（WP-G-R1 v1.6 §2.8）：全局 `built_fleet_count` = 完成舰队（AVAILABLE +
        # ON_MISSION，明确排除 BUILDING/DESTROYED/DISBANDED）——替代旧
        # `fleet_count = len(get_available_fleets())`（完工→指派 ON_MISSION 后旧值归零，
        # 造成「舰队从未完工」误读）；`fleet_count` 保留为兼容 alias（本 R1，P2-N01）。
        if ns:
            built_fleet_count = len([
                f for f in ns.get_all_fleets()
                if f.status in (FleetStatus.AVAILABLE, FleetStatus.ON_MISSION)
            ])
        else:
            built_fleet_count = 0
        available_legion_count = len(ms.get_available_legions()) if ms else 0
        # WP-F R2-02（F-02B）：权威已动员军团数 = len(get_active_legions())（ACTIVE 全集，
        # 含 TRUCE 附着 ACTIVE 与未指派 ACTIVE；语义区别于 available_legion_count 可征召池）
        mobilized_legion_count = len(ms.get_active_legions()) if ms else 0
        treasury = getattr(state, '_treasury', 0)

        current_phase_id = _infer_current_phase_id(state)
        current_player = state.get_current_player()

        # Determine current step and phase data
        phase_data = state.get_phase_result("combat") or {}
        if isinstance(phase_data, dict):
            selected_war_id = phase_data.get("selected_war_id", "")
            resolved_wars = phase_data.get("resolved_wars", [])
            pending_result = phase_data.get("pending_result", {})
            war_results = phase_data.get("war_results", {})
        else:
            selected_war_id = ""
            resolved_wars = []
            pending_result = {}
            war_results = {}

        # INV-C3/Δ6（GUI 软锁防线）：advance 判定由「可战斗战争已全结算」驱动
        # （有指挥官且未战），替代 len(active_wars)==0 —— LOSS 后 war 仍 ACTIVE 不阻塞。
        # pending_result 优先：先展示结果视图再转 advance。
        if pending_result:
            current_step = "result"
        elif _all_battled(ws, phase_data, state=state):
            current_step = "advance"
        elif selected_war_id:
            current_step = "action"
        else:
            current_step = "select"
        all_resolved = _all_battled(ws, phase_data, state=state)

        actionable = (
            current_phase_id == "combat"
            and state.is_current_player(viewer_player_id)
        )
        interaction_mode = "interactive" if current_phase_id == "combat" else "readonly"

        # Build war cards for active wars（INV-C3：LOSS 后 war 仍 ACTIVE → 卡仍在 active_wars）
        # presentation_state（L2 卡构建层唯一落点，D2 §1）：由 war.status + 本回合已战
        # （war_id ∈ resolved_wars）合成；不删 status 字段（API 兼容）
        war_cards = []
        for w in active_wars:
            card = _war_card(w, state)
            card["slot_index"] = w.combat_slot_index
            if w.id in resolved_wars:
                card["presentation_state"] = "CURRENT_TURN_RESULT"
                # P2-d：本回合已战斗的 ACTIVE 卡（defeat/disaster）附 result 摘要
                if isinstance(war_results, dict) and w.id in war_results:
                    card["result"] = war_results[w.id]
            else:
                card["presentation_state"] = "ACTIVE_ACTIONABLE"
            war_cards.append(card)

        # INV-C6：TRUCE war 卡面可见（TRUCE_LOCKED，计入容量、不可战斗）
        # WP-G-R4 (SA v1.7 §5.3 例 2/§5.4)：TRUCE 分支同回合附 war_results[id] result——
        # Naval TRIUMPH + Land draw 确认后仍保留双结果卡（TRUCE_LOCKED 不阻止看历史）
        truce_cards = []
        for w in (ws.get_truce_wars() if ws else []):
            card = _war_card(w, state)
            card["slot_index"] = w.combat_slot_index
            card["presentation_state"] = "TRUCE_LOCKED"
            if isinstance(war_results, dict) and w.id in war_results:
                card["result"] = war_results[w.id]
            truce_cards.append(card)

        # Build resolved war cards from war_system discard pile, filtered by phase_data
        resolved_war_ids = resolved_wars  # list of war_ids from phase_data
        resolved_wars_full = ws.get_resolved_wars() if ws else []
        relevant_resolved = [w for w in resolved_wars_full if w.id in resolved_war_ids]
        resolved_war_cards = []
        for w in relevant_resolved:
            card = _war_card(w, state)
            card["slot_index"] = w.combat_slot_index
            # AC-4.3: 逐场结果留卡片内 — 每张结算卡附本场 result 对象
            if isinstance(war_results, dict) and w.id in war_results:
                card["result"] = war_results[w.id]
            card["presentation_state"] = "CURRENT_TURN_RESULT"
            resolved_war_cards.append(card)

        # P1-01：war_slots 有序 DTO（槽位身份 + None 占位）
        war_slots = _build_war_slots(war_cards, truce_cards, resolved_war_cards, ws)

        # Battle results
        battle_results = []
        if pending_result:
            battle_results = [pending_result]

        # Summary
        active_war_count = len(active_wars)
        resolved_war_count = len(resolved_wars)

        data = {
            "phase_id": "combat",
            "viewer_player_id": viewer_player_id,
            "current_player_id": current_player.player_id if current_player else None,
            "is_current_phase": current_phase_id == "combat",
            "is_current_player": state.is_current_player(viewer_player_id),
            "current_phase_id": current_phase_id,
            "interaction_mode": interaction_mode,
            "current_step": current_step,
            "actionable": actionable,
            "selected_war_id": selected_war_id,
            "can_advance": all_resolved,
            "all_resolved": all_resolved,
            # R1-G-08（WP-G-R1 v1.6 §2.8）：权威全局 key `built_fleet_count`；`fleet_count`
            # 保留为兼容 alias（GUI 已改读新字段）
            "built_fleet_count": built_fleet_count,
            "fleet_count": built_fleet_count,
            "available_legion_count": available_legion_count,
            "mobilized_legion_count": mobilized_legion_count,
            "treasury": treasury,
            "active_wars": war_cards,
            "truce_wars": truce_cards,
            "resolved_war_cards": resolved_war_cards,
            "war_slots": war_slots,
            "resolved_war_ids": resolved_war_ids,
            "battle_results": battle_results,
            "summary": {
                "title": "战斗阶段",
                "status": current_step,
                "message": "选择战争 → 进攻/防御/侦查 → 查看战果 → 推进决算",
                "active_war_count": active_war_count,
                "resolved_war_count": resolved_war_count,
            },
        }
        return api_response(True, "Combat phase view refreshed", data)
    except Exception as exc:
        logger.exception("get_combat_view failed")
        return api_response(False, f"获取战斗视图失败: {exc}", errors=[str(exc)])


def select_war(state: GameState, viewer_player_id: str, war_id: str) -> dict:
    """Mark a war as selected for combat action."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        ws = _war_system(state)
        war = ws.get_war_by_id(war_id) if ws else None
        if not war:
            return api_response(False, f"War not found: {war_id}")

        # Store selected war in phase data
        phase_data = state.get_phase_result("combat") or {}
        if isinstance(phase_data, dict):
            phase_data["selected_war_id"] = war_id
        else:
            phase_data = {"selected_war_id": war_id}
        state.record_phase_result("combat", phase_data)

        return api_response(
            True,
            f"Selected war: {war.name}",
            data={"selected_war_id": war_id, "war_name": war.name},
        )
    except Exception as exc:
        logger.exception("select_war failed")
        return api_response(False, f"选择战争失败: {exc}", errors=[str(exc)])


def do_combat_action(
    state: GameState,
    viewer_player_id: str,
    war_id: str,
    action: str,  # "scout", "defence", "attack"
    auto: bool = False,
) -> dict:
    """Execute a combat action on a war."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not auto and not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        ws = _war_system(state)
        war = ws.get_war_by_id(war_id) if ws else None
        if not war:
            return api_response(False, f"War not found: {war_id}")

        if action not in ("scout", "defence", "attack"):
            return api_response(False, f"Unknown action: {action}")

        # Idempotency guard (FC-1 AC-1.3): a war already resolved must not be
        # re-resolved on double-click / repeated attack signals.
        if action == "attack":
            phase_data = state.get_phase_result("combat") or {}
            resolved = phase_data.get("resolved_wars", []) if isinstance(phase_data, dict) else []
            if war_id in resolved:
                return api_response(False, f"该战争已结算: {war_id}")

        # Scout is preview-only (DEPRECATED — FUNC-03 attack-only). Retained for
        # API compatibility (B-19); the GUI no longer exposes this action.
        if action == "scout":
            preview_dice = 7  # Average dice for preview
            preview_result = _compute_combat_result(war, state, preview_dice, "scout")
            data = _build_battle_result(
                war, state,
                dice=preview_result["dice"],
                total_attack=preview_result["total_attack"],
                enemy_defence=preview_result["enemy_defence"],
                result=preview_result["result"],
                loot=preview_result["loot"],
                losses=preview_result["losses"],
                triumph=preview_result["triumph"],
            )
            data["deprecated"] = True
            return api_response(
                True,
                f"侦查预览（已弃用）— {war.name}",
                data=data,
            )

        # ── Naval gate（G1-09 / R-04 / R-05 / R-06，WP-G GC；WP-G-R4 G02 前置）──
        # WP-G-R4 (SA v1.7 §3.3)：readiness 前置在任何结果副作用之前——NOT_READY →
        # api False + code（零 CRT/零损失/零 event/零 duration/零 battled/pending/war_results，
        # 不 roll Land 骰）；NavalSystem 缺失 = 技术 fail-closed（不落入正常 skip）。
        readiness_code, readiness_reason = _naval_attack_readiness(state, war)
        if readiness_code:
            state.log_event(
                f"do_combat_action: war={war.id} readiness 拒绝（{readiness_code}）",
                level=logging.DEBUG,
                extra={"war_id": war.id, "code": readiness_code, "reason": readiness_reason},
            )
            return api_response(
                False,
                "海军未就绪：本战无已指派可用舰队（readiness，非战败）"
                if readiness_code == "NAVAL_NOT_READY" else "海军系统不可用（技术失败）",
                data={
                    "code": readiness_code,
                    "reason": readiness_reason,
                    "attack_result": _naval_not_ready_dto(war, readiness_reason),
                },
            )

        ns = getattr(state, "naval_system", None)
        duration_before = int(getattr(war, "duration", 0) or 0)
        sea_before = bool(war.sea_control_acquired)

        # ── Naval gate（SA v1.7 §5.2 构建次序：gate_required → resolve_naval_battle →
        #     naval 真实结果快照（实际 losses + acquired）→ blocking 则 Land NOT_EXECUTED）──
        naval_gate_triggered = False
        naval_stage = None
        if war.naval_required and not war.sea_control_acquired:
            naval_gate_triggered = True
            naval_result, naval_details = ns.resolve_naval_battle(war)
            if naval_result == "NAVAL_NOT_READY":
                # 防御性（view/action 间舰队毁伤竞态）：共享 Core 前置不得造 battle result
                return api_response(
                    False,
                    "海军未就绪：本战无已指派可用舰队（readiness，非战败）",
                    data={"code": "NAVAL_NOT_READY",
                          "reason": "NO_READY_ASSIGNED_FLEET",
                          "attack_result": _naval_not_ready_dto(war, "NO_READY_ASSIGNED_FLEET")},
                )
            if not isinstance(naval_details, dict):
                naval_details = {}
            # naval 阶段快照（Land mutation 前捕获——获控可能被 Land terminal 清理，§0.2-5/§5.2）
            participating = list(naval_details.get("participating_fleet_ids", []) or [])
            if not participating:
                participating = list(getattr(war, "_assigned_fleet_ids", None) or [])
            remaining = set(getattr(war, "_assigned_fleet_ids", None) or [])
            casualty_ids = sorted(fid for fid in participating if fid not in remaining)
            naval_label_map = {
                "TRIUMPH": "海战大胜", "VICTORY": "海战胜利", "STALEMATE": "海战僵持",
                "DEFEAT": "海战战败", "DISASTER": "海战灾难",
            }
            naval_stage = {
                "required": True,
                "gate_required": True,
                "executed": True,
                "status": "RESOLVED",
                "result": naval_result,
                "result_label": naval_label_map.get(naval_result, naval_result),
                "roman_losses": naval_details.get("roman_losses", 0) or 0,
                "enemy_losses": naval_details.get("enemy_loss", 0) or 0,
                "participating_fleet_ids": sorted(set(participating)),
                "casualty_fleet_ids": casualty_ids,
                "sea_control_before": sea_before,
                "sea_control_acquired": bool(
                    war.sea_control_acquired or naval_details.get("sea_control_acquired")
                ),
            }
            if naval_result in ("STALEMATE", "DEFEAT", "DISASTER"):
                # blocking：duration+1 一次；land=NOT_EXECUTED(NAVAL_GATE_BLOCKED)；envelope
                # finalize + persist + return naval_blocked（R4-05：无假 Land 统计）
                war.duration += 1
                envelope = _build_naval_block_result(
                    war, state, naval_result, naval_details,
                    participating=participating, casualty_ids=casualty_ids,
                    sea_before=sea_before,
                    duration_delta=war.duration - duration_before,
                )
                _persist_combat_envelope(state, war, envelope)
                _emit_combat_action_resolved(state, war, envelope)
                return api_response(True, f"海战{naval_result}，无法登陆，战争持续", data=envelope)
            # 非 blocking：须真实 sea_control acquired（内部矛盾 fail-closed，不默认继续 Land，§5.2）
            if not (war.sea_control_acquired
                    or naval_details.get("sea_control_acquired")):
                logger.error(
                    "do_combat_action internal contradiction: naval success without "
                    "sea_control acquired (war=%s result=%s)", war.id, naval_result
                )
                return api_response(
                    False,
                    "海战成功但未获制海权（内部矛盾，fail-closed；真实异常半完成 mutation 需单列缺陷/STOP）",
                )
        else:
            # 无海军门 → naval NOT_EXECUTED（NOT_REQUIRED / SEA_CONTROL_ALREADY_ACQUIRED；§3.2 BYPASSED）
            reason = "NOT_REQUIRED" if not war.naval_required else "SEA_CONTROL_ALREADY_ACQUIRED"
            naval_stage = _v2_naval_not_executed_stage(war, reason)

        # ── Land：同一 ATTACK 条件执行（_compute_combat_result 保留原 Land 词）──
        dice = random.randint(2, 12)
        result_data = _compute_combat_result(war, state, dice, action)
        result = result_data["result"]

        # 决定性结果四分支（INV-C1/C3，替代 5898ef1 两分）：
        # - triumph/victory → resolve_war(True, combat_result)：war 结束 RESOLVED + discard（不变）
        # - draw → _generate_peace_treaty：→ TRUCE（不变）
        # - defeat/disaster → _apply_loss_consequence：war 保持 ACTIVE（不 resolve、
        #   不 discard、commander consequence + duration+1；INV-C3）
        if ws:
            if result in ("triumph", "victory"):
                # WP-G-R4 (§4.2)：现代成功入口必传显式 CRT 身份（禁 bool-only 塌缩）
                ws.resolve_war(war_id, True, combat_result=result)
            elif result == "draw":
                _generate_peace_treaty(war, result, state)
            elif result in ("defeat", "disaster"):
                _apply_loss_consequence(war, result, state)

        # Apply land casualties（G1-05/06/07 / G2-C §4，WP-G GB）——唯一伤亡 mutation
        # owner = MilitarySystem.apply_land_casualties（random.sample 无放回 ceil(N/2) →
        # DESTROYED / DISASTER 全灭）；删除 add_legions_to_disband 前缀镜像路径
        # （§11.2 根因：该路径使伤亡滞留 ACTIVE+assigned 且解散失败重排队）。
        ms = _military_system(state)
        casualty_numbers = []
        if ms and result in ("defeat", "disaster"):
            raw = ms.apply_land_casualties(war.id, result)
            if isinstance(raw, (list, tuple)):
                casualty_numbers = list(raw)

        # Build land flat DTO（旧顶层兼容 alias 源——land.executed=true 时顶层字段纯 alias）
        battle_result = _build_battle_result(
            war, state,
            dice=result_data["dice"],
            total_attack=result_data["total_attack"],
            enemy_defence=result_data["enemy_defence"],
            result=result,
            loot=result_data["loot"],
            losses=result_data["losses"],
            triumph=result_data["triumph"],
            casualty_numbers=casualty_numbers,
        )

        # WP-G GC（S7）：本场曾触发海军门且获控（TRIUMPH/VICTORY）→ 陆战继续路径标注
        # （land_battle deprecated presentation alias：allowed/bypassed）
        land_battle_alias = "allowed" if naval_gate_triggered else "bypassed"

        # 单一 finalized envelope（schema_version=2；naval/land 并列 executed）→ 持久 + summary
        envelope = _v2_finalize_land_envelope(
            war, state, battle_result, naval_stage,
            duration_delta=war.duration - duration_before,
            land_battle_alias=land_battle_alias,
        )
        # Defence is DEPRECATED (FUNC-03 attack-only). Retained for API compatibility (B-19);
        # the GUI no longer exposes this action. Marker 保留（非新双阶段产品入口宣传，§8.1 T15）。
        if action == "defence":
            envelope["deprecated"] = True
            battle_result["deprecated"] = True

        _persist_combat_envelope(state, war, envelope)
        _emit_combat_action_resolved(state, war, envelope)

        return api_response(
            True,
            f"战斗结算完成: {result}",
            data=envelope,
        )
    except Exception as exc:
        logger.exception("do_combat_action failed")
        return api_response(False, f"执行战斗操作失败: {exc}", errors=[str(exc)])


def confirm_battle_result(state: GameState, viewer_player_id: str) -> dict:
    """Acknowledge the battle result and return to SELECT or ADVANCE."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        phase_data = state.get_phase_result("combat") or {}
        if not isinstance(phase_data, dict):
            phase_data = {}

        # Clear pending result
        phase_data["pending_result"] = {}
        phase_data["selected_war_id"] = ""

        # Advance 谓词（INV-C3/Δ6）：所有「可战斗」战争（有指挥官且未战）已结算 → advance。
        # 替代 len(active_wars)==0：LOSS 后 war 仍 ACTIVE，但 commander 已离场/阵亡
        # （consequence）→ 视同无需再战；TRUCE war 天然不计入。
        ws = _war_system(state)
        all_battled = _all_battled(ws, phase_data, state=state)
        if all_battled:
            next_step = "advance"
        else:
            next_step = "select"
        all_resolved = all_battled

        state.record_phase_result("combat", phase_data)

        return api_response(
            True,
            "战果已确认",
            data={"next_step": next_step, "all_resolved": all_resolved},
        )
    except Exception as exc:
        logger.exception("confirm_battle_result failed")
        return api_response(False, f"确认战果失败: {exc}", errors=[str(exc)])


def advance_combat(state: GameState, viewer_player_id: str) -> dict:
    """Confirm all combat is done, advance to Phase 7 (Resolution)."""
    if not state:
        return api_response(False, "Invalid game state")
    try:
        if not state.is_current_player(viewer_player_id):
            return api_response(False, "Current player mismatch")

        # Check that all wars are resolved
        phase_data = state.get_phase_result("combat") or {}
        if not isinstance(phase_data, dict):
            phase_data = {}
        ws = _war_system(state)

        # INV-C3/Δ6：剩余计数 = 可战斗战争（有指挥官且未战）
        # 无指挥官 war（含 LOSS 后 commander 离场）不阻塞；TRUCE war 不计入
        actionable = _actionable_wars(ws, phase_data, state=state)
        if actionable:
            remaining = len(actionable)
            return api_response(False, f"尚有 {remaining} 场战争未结算")

        # Record combat result and mark phase executed
        state.record_phase_result("combat", phase_data)
        state.mark_phase_executed("combat")

        return api_response(
            True,
            "战斗阶段完成，推进到决算阶段",
            data={"next_phase_id": "resolution"},
        )
    except Exception as exc:
        logger.exception("advance_combat failed")
        return api_response(False, f"推进战斗阶段失败: {exc}", errors=[str(exc)])


# ════════════════════════════════════════════════════════════════════════
# S1 Combat 共享用例：auto_resolve_combat
# ════════════════════════════════════════════════════════════════════════
# 整合 CLI CombatCommand 与 GUI auto_resolve 的公共战斗结算逻辑
# CLI + GUI 均委托给此唯一实现
# ════════════════════════════════════════════════════════════════════════

def _generate_peace_treaty(
    war: War,
    battle_result: str,
    state: GameState,
) -> Optional[Dict]:
    """
    根据战斗结果尝试生成停战条约（G1，G1-08：仅 STALEMATE（draw）生成 pending treaty）。
    适配自 CLI _maybe_generate_treaty 逻辑。
    非 STALEMATE 结果 fail-closed 不生成（VICTORY/DEFEAT/DISASTER 无条约）。
    """
    # G1-08（R-07）：仅 STALEMATE（GUI 路径结果为 "draw"）生成条约
    if battle_result != "draw":
        return None

    from src.core.deciders.impl.auto_peace_treaty_decider import (
        AutoPeaceTreatyDecider
    )
    decider = AutoPeaceTreatyDecider()
    treaty = decider.decide_treaty(
        war,
        _COMBAT_RESULT_CANONICAL.get(battle_result, battle_result.upper()),
        state,
    )
    if treaty is None:
        return None

    required = {"indemnity", "duration", "generated_turn"}
    if required - treaty.keys():
        logger.warning(
            f"Peace treaty missing required keys for war {war.id}: "
            f"{required - treaty.keys()}"
        )
        return None

    war_system = _war_system(state)
    if war_system and war_system.enter_truce(war, treaty):
        state.log_event(
            f"战争 {war.name} 达成停战草案，赔款 {treaty['indemnity']}，"
            f"有效期 {treaty['duration']} 回合",
            extra={
                "type": "peace_treaty_generated",
                "war_id": war.id,
                "result": battle_result,
                "indemnity": treaty["indemnity"],
                "duration": treaty["duration"],
                "generated_turn": treaty["generated_turn"],
            },
        )
        return treaty
    return None


def _process_commanders_returning(state: GameState) -> List[Dict]:
    """
    处理已批准停战的指挥官返回罗马。
    适配自 CLI _process_commanders_returning 逻辑。
    """
    ws = _war_system(state)
    if not ws:
        return []
    returned = []
    current_turn = state.turn.turn_number if state.turn else 0
    for war in ws.get_truce_wars_with_approved_treaty():
        commander_id = getattr(war, "original_commander_id", None) or war.commander_id
        if not commander_id:
            continue
        commander = state.get_member(commander_id)
        if not commander or commander.is_dead:
            continue

        old_office = getattr(commander, "office", None)
        if old_office in ("proconsul", "propraetor"):
            assigned_turn = getattr(war, "commander_assigned_turn", None) or (
                current_turn - 1
            )
            commander.add_office_history(old_office, assigned_turn, current_turn - 1)
            commander.office = None
            commander.is_absent = False
            commander.update_influence()
            state.log_event(
                f"指挥官 {commander.name} 返回罗马",
                extra={
                    "type": "commander_return",
                    "figure_id": commander.id,
                    "war_id": war.id,
                },
            )
            returned.append({
                "commander_id": commander.id,
                "commander_name": commander.name,
                "war_id": war.id,
                "war_name": war.name,
                "former_office": old_office,
            })
    return returned


def _skip_all_unassigned(state: GameState, wars: List) -> None:
    """
    将无指挥官战争记录到 phase_data resolved_wars，使其不阻塞 advance。
    """
    phase_data = state.get_phase_result("combat") or {}
    if not isinstance(phase_data, dict):
        phase_data = {}
    resolved = list(phase_data.get("resolved_wars", []))
    for war in wars:
        if war.id not in resolved:
            resolved.append(war.id)
    phase_data["resolved_wars"] = resolved
    state.record_phase_result("combat", phase_data)


def auto_resolve_combat(state: GameState, player_id: str) -> dict:
    """
    阶段级公共用例：自动结算所有活跃战争。
    
    CLI CombatCommand 与 GUI adapter.auto_resolve_combat 均委托给此函数。
    Adapter 不再保留 for-loop / 子步骤编排。
    
    返回含以下结构的 dict:
    {
        "success": bool,
        "message": str,
        "data": {
            "wars_resolved": int,        # 已结算战争数
            "active_war_count": int,      # 总活跃战争数
            "skipped_no_commander": int,  # 无指挥官跳过数
            "battles": [                  # 每场战斗结算详情
                {
                    "war_id": str,
                    "war_name": str,
                    "result": str,        # GUI 命名 (triumph/victory/...)
                    "dice": int,
                    "total_attack": int,
                    "enemy_defence": int,
                    "total_score": int,
                    "losses": int,
                    "triumph": bool,
                    "loot": int,
                    ...
                }
            ],
            "treaties": [Dict],          # 生成的停战条约
            "commanders_returned": [Dict], # 返回罗马的指挥官
            "completed": bool,            # combat 阶段是否已完成
            "next_phase": str,            # 下一阶段 ID
        }
    }
    """
    try:
        ws = _war_system(state)
        if not ws:
            return api_response(False, "War system not available")

        active_wars = ws.get_active_wars()
        total_active = len(active_wars)

        if total_active == 0:
            # 无活跃战争也推进阶段（与 CLI 原始行为一致）
            adv_result = advance_combat(state, player_id)
            completed = adv_result.get("success", False)
            adv_data = adv_result.get("data") or {}
            next_phase = adv_data.get("next_phase_id", "resolution")
            return api_response(True, "没有活跃的战争", data={
                "wars_resolved": 0,
                "active_war_count": 0,
                "skipped_no_commander": 0,
                "battles": [],
                "treaties": [],
                "commanders_returned": [],
                "completed": completed,
                "next_phase": next_phase,
            })

        # 分类：有指挥官 vs 无指挥官
        assigned_wars = [w for w in active_wars if w.commander_id is not None]
        skipped = total_active - len(assigned_wars)

        # WP-G-R4 (SA v1.7 §3.4)：no-ready 战争输出独立 unavailable_wars（非 battles），
        # 继续其他 ready war；不 _skip_all_unassigned、不标 battled、不进 wars_resolved。
        unavailable_wars = []
        battle_candidates = []
        for w in assigned_wars:
            code, reason = _naval_attack_readiness(state, w)
            if code is not None:
                unavailable_wars.append({"war_id": w.id, "code": code, "reason": reason})
            else:
                battle_candidates.append(w)

        if not assigned_wars:
            # 无指挥官战争：全部标记为已处理，然后推进（与 CLI 一致）
            _skip_all_unassigned(state, active_wars)
            adv_result = advance_combat(state, player_id)
            completed = adv_result.get("success", False)
            adv_data = adv_result.get("data") or {}
            next_phase = adv_data.get("next_phase_id", "resolution")
            return api_response(True, "所有战争均无指挥官，跳过战斗结算", data={
                "wars_resolved": 0,
                "active_war_count": total_active,
                "skipped_no_commander": skipped,
                "battles": [],
                "treaties": [],
                "commanders_returned": [],
                "completed": completed,
                "next_phase": next_phase,
            })

        # 先处理无指挥官战争：标记为已跳过
        _skip_all_unassigned(state, [w for w in active_wars if w.commander_id is None])

        # 逐场结算（仅 ready wars；NOT_READY 已在 unavailable_wars）
        battles = []
        treaties = []
        for war in battle_candidates:
            # Select war
            select_war(state, player_id, war.id)

            # Execute battle (auto 模式跳过玩家校验)
            action_result = do_combat_action(
                state, player_id, war.id, "attack", auto=True
            )
            if not action_result.get("success"):
                continue

            battle_data = action_result.get("data", {})
            battles.append(battle_data)

            # Confirm result
            confirm_battle_result(state, player_id)

        # 处理指挥官返回
        commanders_returned = _process_commanders_returning(state)

        # 推进战斗阶段
        advance_result = advance_combat(state, player_id)
        completed = advance_result.get("success", False)
        adv_data = advance_result.get("data") or {}
        next_phase = adv_data.get("next_phase_id", "resolution")

        return api_response(True, f"战斗结算完成，共 {len(battles)} 场战斗", data={
            "wars_resolved": len(battles),
            "active_war_count": total_active,
            "skipped_no_commander": skipped,
            "unavailable_wars": unavailable_wars,
            "battles": battles,
            "treaties": treaties,
            "commanders_returned": commanders_returned,
            "completed": completed,
            "next_phase": next_phase,
        })

    except Exception as exc:
        logger.exception("auto_resolve_combat failed")
        return api_response(
            False, f"自动战斗结算失败: {exc}", errors=[str(exc)]
        )
