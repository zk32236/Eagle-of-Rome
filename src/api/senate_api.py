# src/api/senate_api.py
"""
元老院阶段 API
提供统一的操作接口，供 CLI 和决策器调用。
"""

import copy
import logging
import random
import uuid
from typing import Any, Dict, List, Optional

from src.api import api_response
from src.core.deciders.impl.auto_budget_decider import AutoBudgetDecider
from src.core.deciders.impl.auto_land_proposal_decider import AutoLandProposalDecider
from src.core.deciders.land_proposal_decider import LandProposalDecider
from src.core.deciders.senate_vote_decider import SenateVoteDecider
from src.core.deciders.impl.auto_tribune_veto_decider import AutoTribuneVetoDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.figure import Figure
from src.core.entities.war import WarStatus
from src.core.game_state import GameState
from src.core.systems.political_system import PoliticalSystem, _tribune_absent_guard


def _political_system(state: GameState) -> PoliticalSystem:
    return PoliticalSystem(state)


def get_senate_initial_info(state: GameState) -> dict:
    """返回元老院阶段初始展示所需的所有信息。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    try:
        result = _political_system(state).build_initial_info()
        return api_response(
            success=result.get("success", False),
            message=result.get("message", ""),
            data=result.get("data", {}),
            errors=result.get("errors", []),
        )
    except Exception as exc:
        return api_response(False, f"获取信息失败: {exc}", errors=[str(exc)])



def _safe_name(item: Any, *attrs: str) -> str:
    for attr in attrs:
        value = getattr(item, attr, None)
        if value:
            return str(value)
    if isinstance(item, dict):
        for attr in attrs:
            value = item.get(attr)
            if value:
                return str(value)
    return ""


def _proposal_label(state: GameState, proposal: Dict[str, Any]) -> str:
    ptype = proposal.get("type", "")
    if ptype == "war":
        ws = state.get_war_system()
        war = ws.get_war_by_id(proposal.get("war_id")) if ws else None
        return f"宣战 — {_safe_name(war, 'name') or proposal.get('war_id')}（征召 {proposal.get('legions', 0)} 个军团）"
    if ptype == "peace":
        ws = state.get_war_system()
        war = ws.get_war_by_id(proposal.get("war_id")) if ws else None
        return f"停战 — {_safe_name(war, 'name') or proposal.get('war_id')}"
    if ptype == "governor":
        province = state.get_province(proposal.get("province_id"))
        candidate = state.get_member(proposal.get("candidate_id"))
        candidate_name = candidate.get_formal_name() if candidate else proposal.get("candidate_id")
        return f"总督任命 — {_safe_name(province, 'name') or proposal.get('province_id')}：{candidate_name}"
    if ptype == "budget":
        contract = state.get_contract(proposal.get("contract_id"))
        amount = proposal.get("modified_budget")
        return f"建造合同 — {_safe_name(contract, 'name') or proposal.get('contract_id')}（预算 {amount} T）"
    if ptype == "land":
        amount_C = proposal.get("amount_C")
        percent = proposal.get("percent") or 0.0
        if proposal.get("act_type") == "sale":
            return f"卖地法案 — 出售 {amount_C} C（约 {percent * 100:.0f}%）"
        return f"分地法案 — 分配 {amount_C} C 公地"
    return ptype


def _proposal_option(key: str, proposal_type: str, title: str, detail: str, params: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    option = {
        "key": key,
        "type": proposal_type,
        "title": title,
        "detail": detail,
        "params": params,
        "selected": False,
        "enabled": True,
    }
    option.update(extra)
    return option


def _announcement_key_params(proposal: Dict[str, Any]) -> Dict[str, Any]:
    """Public Announcement 关键参数映射（AU-6/S-10）。

    值全部来自 authoritative proposal dict（params 透传语义，D-08 §10.3），禁 QML 自行推导。
    per-type：land→{act_type,amount_C,percent}；war→{war_id,legions}；
    budget→{contract_id,modified_budget}；governor→{province_id,candidate_id}；peace→{war_id}。
    """
    ptype = proposal.get("type")
    if ptype == "land":
        return {
            "act_type": proposal.get("act_type"),
            "amount_C": proposal.get("amount_C"),
            "percent": proposal.get("percent"),
        }
    if ptype == "war":
        return {"war_id": proposal.get("war_id"), "legions": proposal.get("legions")}
    if ptype == "budget":
        return {"contract_id": proposal.get("contract_id"), "modified_budget": proposal.get("modified_budget")}
    if ptype == "governor":
        return {"province_id": proposal.get("province_id"), "candidate_id": proposal.get("candidate_id")}
    if ptype == "peace":
        return {"war_id": proposal.get("war_id")}
    return {}


def _budget_range_for_contract(state: GameState, contract) -> Optional[Dict[str, int]]:
    """authoritative budget range, anchored to contract.base_cost (ODR-ED-01).

    PUBLIC_WORKS: min = 1T (absolute), max = base_cost x 1.5
    TAX_FARMING:  min = base_cost x 0.75, max = base_cost x 2.0
    step = 1, default = base_cost (unchanged current default).

    Returns {"min", "max", "step", "default"}; None if config keys absent
    (defensive; ODR closed so config is present in production).
    """
    sb = state.config.get("economic_rules.senate_budget")
    if not sb:
        return None
    if isinstance(contract, dict):
        base = int(contract.get("base_cost", 0) or 0)
        ctype = contract.get("type")
        if isinstance(ctype, str):
            ctype = ContractType(ctype)
    else:
        base = int(getattr(contract, "base_cost", 0) or 0)
        ctype = getattr(contract, "contract_type", None)
    if ctype == ContractType.PUBLIC_WORKS:
        mn = max(1, int(sb.get("public_works_min", 1)))
        mx = int(base * float(sb.get("public_works_max_ratio", 1.5)))
    else:  # TAX_FARMING
        mn = int(base * float(sb.get("tax_farming_min_ratio", 0.75)))
        mx = int(base * float(sb.get("tax_farming_max_ratio", 2.0)))
    step = int(sb.get("step", 1))
    return {"min": mn, "max": mx, "step": step, "default": base}


def _legion_options_for_war(state: GameState, war) -> Optional[Dict[str, Any]]:
    """authoritative legion value range for a war proposal (ODR-ED-02).

    min = config min (1, cannot declare war with 0), default = config default (4),
    max = dynamic available legion pool (len(get_available_legions())),
    allowed = [min .. available_pool].

    Returns {"min", "max", "default", "allowed"}; None if config keys absent
    (defensive; ODR closed so config is present in production).
    """
    sw = state.config.get("economic_rules.senate_war_legions")
    if not sw:
        return None
    ms = state.get_military_system()
    pool = len(ms.get_available_legions()) if ms else 0
    # WP-G-R4 (§2.5)：reserved N（其他目标战）从本战可征召池扣除
    pool -= _takeover_reserved_offset(state, getattr(war, "id", None))
    pool = max(pool, 0)
    lo = int(sw.get("min", 1))
    default = int(sw.get("default", 4))
    allowed = list(range(lo, pool + 1))
    default = max(lo, min(default, pool))
    return {"min": lo, "max": pool, "default": default, "allowed": allowed}


def reinforcement_range(state: GameState, war) -> Optional[Dict[str, Any]]:
    """Reinforcement N 冻结值域（G 件 §4 / G1-23 / G1-24 / G1-17，A3）。

    正常：1 ≤ N ≤ count(UNRAISED+DISBANDED)；零池例外：pool==0 → N=0 允许；
    国库不参与上限。返回 {"min", "max", "default", "allowed", "zero_pool_exception"}；
    供 GUI DTO / API 重校验 / GB·GC·GD 下游消费（G 件 §5「GA 统一暴露」）。
    """
    ms = state.get_military_system()
    pool = len(ms.get_available_legions()) if ms else 0
    # WP-G-R4 (§2.5 生产者消费者守恒)：同一 session 内 V/T 持有的 N（其他目标战）从池中扣除
    pool -= _takeover_reserved_offset(state, getattr(war, "id", None))
    pool = max(pool, 0)
    if pool == 0:
        return {
            "min": 0, "max": 0, "default": 0,
            "allowed": [0], "zero_pool_exception": True,
        }
    return {
        "min": 1, "max": pool, "default": 1,
        "allowed": list(range(1, pool + 1)), "zero_pool_exception": False,
    }


def _takeover_reserved_offset(state: GameState, for_war_id: Optional[str]) -> int:
    """WP-G-R4 (§2.5)：跨消费者守恒——V（RESERVED）或 T（LOCKED）持有的增援 N
    在目标战之外的所有军团消费者（宣战/继续指挥/其他接管）可见池中扣除。"""
    pending = getattr(state, "_takeover_pending", None)
    if not pending or pending.get("status") not in ("RESERVED", "LOCKED"):
        return 0
    if pending.get("war_id") == for_war_id:
        return 0
    return int(pending.get("reinforcement_n", 0) or 0)


def _war_has_valid_commander(state: GameState, war) -> bool:
    """薄委托：单一权威判定（PoliticalSystem.is_war_commander_valid，H 件 §3）。"""
    return _political_system(state).is_war_commander_valid(war)


# R1-G-05（WP-G-R1 v1.6 §2.5.1，P2-01/G5）：takeover_required.rows[].reason 冻结
# machine-token 值域（commander_dead / commander_absent / commander_missing）。DTO/API
# 层透传 token；中文展示文案由展示层映射（_commander_unavailable_reason = legacy
# takeover_options UI 文本，Q 件 J，语义不变）。单一谓词（dead → absent → missing）为
# token 与展示文案两消费点同源权威。
_COMMANDER_UNAVAILABLE_DISPLAY = {
    "commander_dead": "指挥官已阵亡",
    "commander_absent": "指挥官离任",
    "commander_missing": "指挥官缺失",
}


def _commander_unavailable_token(state: GameState, war) -> str:
    """commanderless 原因 machine token（冻结值域：commander_dead/commander_absent/
    commander_missing；v1.6 §2.5.1）。P2 接管原因单一谓词权威（dead → absent →
    missing），`takeover_required.rows[].reason` 直接透传本 token。"""
    old_cmd = state.get_member(war.commander_id) if war.commander_id else None
    if old_cmd and old_cmd.is_dead:
        return "commander_dead"
    if old_cmd and old_cmd.is_absent:
        return "commander_absent"
    return "commander_missing"


def _commander_unavailable_reason(state: GameState, war) -> str:
    """legacy P2 接管 reason 展示文案（takeover_options UI，Q 件 J）——由 machine token
    映射（与 takeover_required.rows[].reason 同源单一谓词），不改既有展示契约。"""
    return _COMMANDER_UNAVAILABLE_DISPLAY[_commander_unavailable_token(state, war)]


def _resolve_takeover_required(state: GameState) -> Dict[str, Any]:
    """权威只读 takeover_required 态（R1-G-05，WP-G-R1 v1.6 §2.5，S4）。

    冻结为 per-war required rows（P2-03）：每场 commanderless ACTIVE 战争（ACTIVE +
    无有效指挥官 + 非起义）产出一行；required=True 仅当存在至少一行且当前行动玩家派系
    有 eligible consul（无 eligible consul 的行 eligible_consul=False，不引入无解软锁——
    "强制"语义针对有能力接管的当前派系执政官）。target 复用 `_is_eligible_consul`
    （PoliticalSystem，:906）唯一权威，与 takeover_war 选 consul_figure 同源，不另起
    资格逻辑（R1-04：仍唯一 mutation owner = execute_war_takeover_direct）。

    P1（TRUCE+pending 接管）不计入（可选替换指挥官，非强制）；ACTIVE+valid commander
    不产生 row（禁任意接管，F 件 §5.1）；起义战争排除（总督接管）。rows 按 war_id
    字典序确定性排序。只补 Core truth，不涉 Senate/Shell 强制导航 gating（R1-10）。
    """
    ws = state.get_war_system()
    player = state.get_current_player()
    faction = state.get_faction(player.faction_id) if player else None
    consul_figure = None
    if faction:
        politics = _political_system(state)
        for member in faction.get_members(state):
            if politics._is_eligible_consul(member):
                consul_figure = member
                break
    rows = []
    if ws:
        for war in ws.get_active_wars():
            if war.rebellion_province_id is not None:
                continue
            if _war_has_valid_commander(state, war):
                continue
            rows.append({
                "war_id": war.id,
                "war_name": war.name,
                "eligible_consul": consul_figure is not None,
                "target_commander_id": consul_figure.id if consul_figure else None,
                # P2-01（G5）：rows[].reason = 冻结 machine token（v1.6 §2.5.1 值域
                # commander_dead/commander_absent/commander_missing）；展示文案另层映射
                "reason": _commander_unavailable_token(state, war),
            })
    rows.sort(key=lambda row: row["war_id"])
    # WP-G-R4 (SA v1.7 §2.1/§2.3, P1-RF-01)：pending-aware M——会期级 commitment slot 语义，
    # 非 per-war。M_open（未作 mandatory 决策，仍阻塞）= C 非空 ∧ 无 LOCKED T 覆盖任何 C 战
    # ∧ 有 eligible Consul；M_deploy_ready（已 LOCKED 待部署，放行）= C 非空 ∧ ∃LOCKED T 覆盖
    # 某 C 战 ∧ 有 eligible Consul。两者全局互斥（单 commitment 至多锁 1 战）。
    # `required` 保持 R3 兼容语义 = M_open（无解软锁防护不变：无 eligible Consul → M 不适用）。
    pending = getattr(state, "_takeover_pending", None)
    locked_covers_c = bool(
        pending and pending.get("status") == "LOCKED"
        and any(row["war_id"] == pending.get("war_id") for row in rows)
    )
    m_open = bool(rows) and not locked_covers_c and consul_figure is not None
    m_deploy_ready = bool(rows) and locked_covers_c and consul_figure is not None
    return {
        "required": m_open,
        "m_open": m_open,
        "m_deploy_ready": m_deploy_ready,
        "rows": rows,
    }



def _build_proposal_options(state: GameState, info: Dict[str, Any]) -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = []
    for war in info.get("war_threats", []):
        recruit_cost = state.get_economic_rule("legion_recruit_cost", 4)
        maintenance_base = state.get_economic_rule("legion_maintenance_base", 8)
        veteran_bonus = state.get_economic_rule("veteran_maintenance_bonus", 1)
        veteran_maintenance = maintenance_base + veteran_bonus
        legion_options = _legion_options_for_war(state, war)
        if legion_options is None:
            default_legions = None
            legions_label = "征召数量待定（规则未配置）"
        else:
            default_legions = legion_options["default"]
            legions_label = f"征召 {default_legions} 个军团"
        war_detail = (
            f"{legions_label}；威胁 {war.get('threat_level', 0)}；"
            f"招募费（一次性）{recruit_cost} T/军团；维护费：新军团 {maintenance_base} T/月，老兵军团 {veteran_maintenance} T/月"
        )
        options.append(_proposal_option(
            f"war:{war.get('war_id')}", "war",
            f"宣战 — {war.get('name', war.get('war_id'))}",
            war_detail,
            {"war_id": war.get("war_id"), "legions": default_legions},
            legion_options=legion_options,
        ))
    for peace in info.get("pending_peace_treaties", []):
        options.append(_proposal_option(
            f"peace:{peace.get('war_id')}", "peace",
            f"停战 — {peace.get('name', peace.get('war_id'))}",
            f"赔款 {peace.get('indemnity', 0)} T；期限 {peace.get('duration', 0)} 年",
            {"war_id": peace.get("war_id")},
        ))
    politics = _political_system(state)
    vacancies = info.get("governor_vacancies", {}) or {}
    for governor_type, provinces in vacancies.items():
        candidates = politics.get_eligible_governor_candidates(governor_type)
        available = [candidate for candidate in candidates if not politics.is_governor_position_occupied(candidate.id)]
        candidate = available[0] if available else None
        for province in provinces:
            if not candidate:
                continue
            options.append(_proposal_option(
                f"governor:{province.get('province_id')}", "governor",
                f"总督任命 — {province.get('province_name', province.get('province_id'))}",
                f"候选人：{candidate.get_formal_name()}",
                {"province_id": province.get("province_id"), "candidate_id": candidate.id},
            ))
    for contract in info.get("pending_contracts", []):
        base_cost = contract.get("base_cost", 0)
        budget_range = _budget_range_for_contract(state, contract)
        default_budget = budget_range["default"] if budget_range else base_cost
        options.append(_proposal_option(
            f"budget:{contract.get('contract_id')}", "budget",
            f"建造合同 — {contract.get('name', contract.get('contract_id'))}",
            f"预算金额 {base_cost} T；预期收益 {contract.get('expected_profit', 0)} T",
            {"contract_id": contract.get("contract_id"), "modified_budget": default_budget},
            budget_range=budget_range,
            contract_type=contract.get("type", ""),
        ))
    public_land = state.get_national_public_land()
    if public_land > 0:
        # D-1 / AU-7：默认比例 = config economic_rules.senate_land.default_percent（缺失回退 0.10，保持现状行为）
        senate_land = state.config.get("economic_rules.senate_land") or {}
        default_percent = float(senate_land.get("default_percent", 0.10))
        default_amount_C = max(1, int(public_land * default_percent))
        derived_percent = default_amount_C / public_land
        options.append(_proposal_option(
            "land:sale", "land", "卖地法案 — 出售国家公地",
            f"出售 {default_amount_C} C（约 {derived_percent * 100:.0f}%）国家公地；当前公地 {public_land} C",
            {"act_type": "sale", "amount_C": default_amount_C, "percent": derived_percent},
            public_land=public_land,
        ))
        options.append(_proposal_option(
            "land:distribution", "land", "分地法案 — 分配公地给平民",
            f"分配 {default_amount_C} C 国家公地；当前公地 {public_land} C",
            {"act_type": "distribution", "amount_C": default_amount_C, "percent": derived_percent},
            public_land=public_land,
        ))
    return options


def _submitted_proposal_rows(state: GameState) -> List[Dict[str, Any]]:
    rows = []
    for proposal in state.get_senate_proposals():
        row = proposal.copy()
        row["label"] = _proposal_label(state, proposal)
        rows.append(row)
    return rows


def _seat_share_rows(state: GameState) -> List[Dict[str, Any]]:
    total = sum(faction.get_senate_influence(state) for faction in state.get_active_factions())
    rows = []
    for faction in state.get_active_factions():
        influence = faction.get_senate_influence(state)
        rows.append({
            "faction_id": faction.id,
            "faction_name": faction.name,
            "influence": influence,
            "percent": int(round(influence * 100 / total)) if total else 0,
        })
    return rows


def _current_tribune(state: GameState) -> Optional[Figure]:
    """全局首个 eligible Tribune（AI 语义；迭代范围 = 全局 living members）。

    AU-R2-3c（D-4）：薄委托 → PoliticalSystem._find_any_eligible_tribune（单一迭代范围 +
    单一谓词 _is_eligible_tribune，方案 B：在职+未死亡，is_absent 不参与判定——法律上
    保民官不存在缺席）。调用点稳定（apply_auto_tribune_vetoes / 测试）。
    """
    return _political_system(state)._find_any_eligible_tribune()


def _build_takeover_options(state: GameState) -> List[Dict[str, Any]]:
    """可接管战争列表（A4，Q 件 J）：P1（TRUCE+pending treaty）∪ P2（ACTIVE+no valid commander）。

    排除 ACTIVE+valid commander（禁任意接管，F 件 §5.1）；起义战争排除（总督接管）。
    每项附 reason + reinforcement_range（DTO 只透传权威值，禁 QML 推断 R-01）。
    """
    ws = state.get_war_system()
    if not ws:
        return []
    options = []
    seen = set()
    wars = list(ws.get_truce_wars_with_pending_treaty()) + list(ws.get_active_wars())
    for war in wars:
        if war.id in seen:
            continue
        seen.add(war.id)
        if war.rebellion_province_id is not None:
            continue
        if war.status == WarStatus.TRUCE:
            # P1：TRUCE + pending treaty（候选集已保证 pending）→ 可接管（替换现有指挥官）
            reason = "停战接管"
        else:
            # P2：ACTIVE —— 仅无有效指挥官时可接管
            if _war_has_valid_commander(state, war):
                continue
            reason = _commander_unavailable_reason(state, war)
        options.append({
            "war_id": war.id,
            "name": war.name,
            "reason": reason,
            "reinforcement_range": reinforcement_range(state, war),
        })
    return options


def _build_continue_options(state: GameState) -> List[Dict[str, Any]]:
    """Continue Existing Command 候选（A5，G1-21 / Q 件 J）：TRUCE + pending + 现有 commander 有效。"""
    ws = state.get_war_system()
    if not ws:
        return []
    options = []
    for war in ws.get_truce_wars_with_pending_treaty():
        if war.rebellion_province_id is not None:
            continue
        if not _war_has_valid_commander(state, war):
            continue
        options.append({
            "war_id": war.id,
            "name": war.name,
            "commander_id": war.commander_id,
            "reinforcement_range": reinforcement_range(state, war),
        })
    return options


def _build_governor_appointments(state: GameState) -> dict:
    """构建总督任命 DTO。

    S5: 遍历所有已征服行省，区分 pending（待分配）和 completed（已有候任总督）。
    - pending_provinces: 无 governor_designate_id 的行省，含合法候选人列表
    - completed_provinces: 已有 governor_designate_id 的行省
    """
    politics = _political_system(state)
    all_provinces = [p for p in state.get_all_provinces() if p.conquered and p.province_id != 0]

    pending_provinces = []
    completed_provinces = []
    type_names = {"proconsul": "代执政官行省", "propraetor": "代大法官行省"}

    for province in all_provinces:
        province_id = province.province_id
        governor_type = province.governor_type
        designate_id = province.governor_designate_id

        # 当前总督信息
        current_gov_id = province.governor_id
        current_gov = state.get_member(current_gov_id) if current_gov_id else None
        current_gov_info = {"id": current_gov_id, "name": current_gov.get_formal_name()} if current_gov else None

        governor_type_name = type_names.get(governor_type, governor_type)

        if designate_id:
            designated_gov = state.get_member(designate_id)
            designated_name = designated_gov.get_formal_name() if designated_gov else str(designate_id)
            completed_provinces.append({
                "province_id": province_id,
                "name": province.name,
                "governor_type": governor_type,
                "governor_type_name": governor_type_name,
                "designated_governor": designated_name,
                "designated_id": designate_id,
            })
        else:
            # 待分配行省 — 获取合法候选人
            candidates = []
            for fig in politics.get_eligible_governor_candidates(governor_type):
                if politics.is_governor_position_occupied(fig.id):
                    continue
                faction = state.get_faction(fig.faction_id)
                candidates.append({
                    "id": fig.id,
                    "name": fig.get_formal_name(),
                    "faction_id": fig.faction_id,
                    "faction_name": faction.name if faction else "",
                    "influence": fig.influence,
                    "class_tier": fig.class_tier.name if fig.class_tier else "",
                    "martial": fig.martial,
                    "intelligence": fig.intelligence,
                    "charisma": fig.charisma,
                })

            pending_provinces.append({
                "province_id": province_id,
                "name": province.name,
                "governor_type": governor_type,
                "governor_type_name": governor_type_name,
                "current_governor": current_gov_info,
                "candidates": candidates,
            })

    # 检查是否已提交（resolve_senate 已执行并产生 assign_governors 结果）
    senate_result = state.get_phase_result("senate")
    senate_data = senate_result.get("data", {}) if isinstance(senate_result, dict) else {}
    has_assignments = bool(senate_data.get("governor_assignments"))

    return {
        "pending_provinces": pending_provinces,
        "completed_provinces": completed_provinces,
        "can_submit": len(pending_provinces) > 0 and not has_assignments,
        "submitted": has_assignments,
    }


def _passed_proposals_for_veto(state: GameState) -> List[Dict[str, Any]]:
    """WP-F R2-01（单一 producer 收敛）：委托 _build_vote_results_and_candidates 的
    veto_candidate_ids（权威 passed-only 候选集），仅做 id → proposal 映射，零平行 passed 判定。
    """
    candidate_ids = set(_build_vote_results_and_candidates(state)["veto_candidate_ids"])
    return [p for p in state.get_senate_proposals() if p.get("id") in candidate_ids]


def _build_vote_results_and_candidates(state: GameState) -> Dict[str, Any]:
    """WP-F R2-01：单一权威中间投影 producer 的 API 层薄委托。

    权威实现 = PoliticalSystem.build_vote_results_and_candidates（唯一 passed-only 候选集
    生产点，复用 calculate_vote_result，零重算/零重掷）。AI veto / Human-direct record_veto /
    DTO / Store / QML 全消费者同源此 producer。
    """
    return _political_system(state).build_vote_results_and_candidates()


def apply_auto_tribune_vetoes(
    state: GameState,
    veto_decider: Optional[TribuneVetoDecider] = None,
    viewer_player_id: Optional[str] = None,
) -> dict:
    """Apply AI tribune veto decisions for GUI when current viewer does not own the tribune.

    AU-R2-3a（C2，R2-B-1）：新增 viewer_player_id 参数 + fail-closed guard——人类派系持有
    eligible Tribune → AutoTribuneVetoDecider 零构造零调用（guard 置于 decider 构造之前
    return），返回 api_response(False) + WARNING 日志（type="tribune_veto_human_guard"）。
    viewer_player_id 默认 None → CLI auto 模式（phase_senate._handle_step_4，无 viewer 概念）
    行为不变（FACT-8 向后兼容）。
    """
    if not state:
        return api_response(False, "Invalid game state")
    # ★ R2-B-1（C2 冻结原文）：viewer-owns-tribune fail-closed guard（API 兜底，权威 mutation 边界）
    if viewer_player_id:
        control = _political_system(state).resolve_veto_control(viewer_player_id)
        if control["mode"] == "HUMAN":
            state.log_event(
                "AI 保民官否决被拒：人类派系持有 eligible Tribune，AI 否决不可执行",
                level=logging.WARNING,
                extra={
                    "type": "tribune_veto_human_guard",
                    "viewer_player_id": viewer_player_id,
                    "tribune_id": control["actor"],
                },
            )
            return api_response(
                False,
                "人类保民官拥有否决权，AI 否决不可执行",
                data={"vetoed": [], "decisions": []},
            )
    tribune = _current_tribune(state)
    if not tribune:
        return api_response(True, "No tribune is available; veto step skipped", data={"vetoed": [], "decisions": []})
    decider = veto_decider or AutoTribuneVetoDecider()
    politics = _political_system(state)
    vetoed = []
    decisions = []
    for proposal in _passed_proposals_for_veto(state):
        issue = politics.build_issue_from_proposal(proposal)
        should_veto = decider.decide_veto(issue, tribune.id, state)
        if should_veto:
            state.record_senate_veto(proposal["id"])
            vetoed.append(proposal["id"])
        decisions.append({
            "proposal_id": proposal["id"],
            "proposal_type": proposal.get("type"),
            "vetoed": should_veto,
            "tribune_id": tribune.id,
            "tribune_faction_id": tribune.faction_id,
        })
    return api_response(
        True,
        f"AI tribune veto decisions completed; vetoed {len(vetoed)} proposal(s)",
        data={"vetoed": vetoed, "decisions": decisions},
    )

def get_senate_view(state: GameState, viewer_player_id: str) -> dict:
    """返回 GUI 元老院只读视图，不执行提案、投票或结算业务。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        politics = _political_system(state)
        result = politics.build_initial_info()
        if not result.get("success", False):
            return api_response(
                False,
                result.get("message", "获取元老院视图失败"),
                data={},
                errors=result.get("errors", []),
            )

        info = result.get("data", {}) or {}
        current_phase_id = _infer_current_phase_id(state)
        current_player = state.get_current_player()
        active_foreign_wars = info.get("active_foreign_wars", [])
        war_threats = info.get("war_threats", [])
        pending_peace_treaties = info.get("pending_peace_treaties", [])
        governor_vacancies = info.get("governor_vacancies", {})
        governor_appointments = _build_governor_appointments(state)
        pending_contracts = info.get("pending_contracts", [])

        senate_result = state.get_phase_result("senate")
        result_data = senate_result.get("data", {}) if isinstance(senate_result, dict) else {}
        proposals = _submitted_proposal_rows(state)
        proposal_options = _build_proposal_options(state, info)
        if not proposals and result_data:
            proposals = []
            for proposal in result_data.get("passed_proposals_snapshot", []) or []:
                row = proposal.copy()
                row["label"] = _proposal_label(state, proposal)
                row["result"] = "passed"
                proposals.append(row)
            # WP-F R3：vetoed / failed 分开打标签（缺陷 B 修复）；旧存档无新字段 → 退化 rejected 全部 "rejected"（容错）
            vetoed_snapshot = result_data.get("vetoed_proposals_snapshot")
            failed_snapshot = result_data.get("failed_proposals_snapshot")
            if vetoed_snapshot is not None or failed_snapshot is not None:
                for proposal in vetoed_snapshot or []:
                    row = proposal.copy()
                    row["label"] = _proposal_label(state, proposal)
                    row["result"] = "vetoed"
                    proposals.append(row)
                for proposal in failed_snapshot or []:
                    row = proposal.copy()
                    row["label"] = _proposal_label(state, proposal)
                    row["result"] = "rejected"
                    proposals.append(row)
            else:
                for proposal in result_data.get("rejected_proposals_snapshot", []) or []:
                    row = proposal.copy()
                    row["label"] = _proposal_label(state, proposal)
                    row["result"] = "rejected"
                    proposals.append(row)
        player_votes = state.get_senate_votes_copy().get(viewer_player_id, {})
        voted_all = bool(proposals) and all(proposal.get("id") in player_votes for proposal in proposals)
        decision_complete = state.senate_proposal_decision_complete
        # WP-F R2-01（D-1 derive(A) 主案）：voted_all 后执行中间投影——复用 calculate_vote_result
        # （幂等 AI 回填：未投票派系首次决策即持久化，此后纯读零重掷），产出中间 vote_results
        # （Stage 2 支持率载体）+ veto_candidate_ids（权威 passed-only 候选集）。
        if voted_all:
            projection = _build_vote_results_and_candidates(state)
            projected_vote_results = projection["vote_results"]
            veto_candidate_ids = projection["veto_candidate_ids"]
        else:
            projected_vote_results = []
            veto_candidate_ids = []
        if result_data:
            current_step = "results"
        elif not decision_complete:
            current_step = "proposal"
        elif not proposals:
            current_step = "results"  # Path A：0 提案 → 跳过 vote/veto，由提交处理函数直接 resolve（D-09）
        elif voted_all:
            # WP-F R2-01（D-2 对齐 CLI 先例 phase_senate.py:495-506）：zero-passed 收敛——
            # 无 passed 提案 → 直接 results（跳过「否决空集」）；有候选才进 tribune_veto。
            current_step = "tribune_veto" if len(veto_candidate_ids) > 0 else "results"
        else:
            current_step = "senate_vote"
        actionable = current_phase_id == "senate" and state.is_current_player(viewer_player_id)
        # AU-R2-2b（C4/C5）：能力位全由单一 authority resolver 产出（provenance 全收敛）——
        # _viewer_eligible_consul / _viewer_has_tribune 独立重算已退役（FACT-1）。
        proposal_control = politics.resolve_proposal_control(viewer_player_id)
        veto_control = politics.resolve_veto_control(viewer_player_id)
        viewer_has_consul = proposal_control["mode"] == "HUMAN"
        viewer_has_tribune = veto_control["mode"] == "HUMAN"
        can_create = actionable and current_step == "proposal" and viewer_has_consul
        # D-3 收严：can_trigger_ai 严格 mode=="AI"（NONE 不再暴露 AI 入口，fail-closed D-R2-05）
        can_trigger_ai = actionable and current_step == "proposal" and proposal_control["mode"] == "AI"
        takeover_options = _build_takeover_options(state)
        continue_options = _build_continue_options(state)
        can_takeover = actionable and bool(takeover_options) and viewer_has_consul
        can_continue = actionable and bool(continue_options) and viewer_has_consul
        # R3-G-01（设计 §1.5，FROZEN）：单一权威判定复用（DTO 并列态 takeover_required 同源），
        # can_advance 必须以真实 phase_result 为权威——禁拿 current_step=="results" 冒充阶段完成
        # （decision_complete+无提案可投影 results 而无真实 result，见 §1.1/§1.5）。
        takeover_required = _resolve_takeover_required(state)
        has_real_senate_result = bool(senate_result)
        senate_settlement_pending = (current_step == "results") and not has_real_senate_result
        # WP-G-R4 (SA v1.7 §2.3/§2.5)：T/V 读模型 + 显式空选择/部署 capability（O5）
        pending_takeover = _takeover_pending_dto(state)
        pending_takeover_locked = bool(pending_takeover and pending_takeover.get("status") == "LOCKED")
        can_finish_empty = (
            actionable and current_step == "proposal"
            and not takeover_required.get("m_open", False) and viewer_has_consul
        )
        can_deploy = (
            actionable and (current_step == "results") and has_real_senate_result
            and not takeover_required.get("m_open", False) and pending_takeover_locked
        )
        proposal_selection_disabled_reason = ""
        if current_step != "proposal":
            proposal_selection_disabled_reason = "当前不在提案选择环节"
        elif not viewer_has_consul:
            proposal_selection_disabled_reason = "您的派系没有在城执政官可提交（接管配置为边界空结束保留）"
        elif takeover_required.get("m_open", False):
            proposal_selection_disabled_reason = "存在未承诺的强制战争接管（先锁定 commanderless 接管目标）"

        data = {
            "phase_id": "senate",
            "viewer_player_id": viewer_player_id,
            "current_player_id": current_player.player_id if current_player else None,
            "is_current_phase": current_phase_id == "senate",
            "is_current_player": state.is_current_player(viewer_player_id),
            "current_phase_id": current_phase_id,
            "interaction_mode": "interactive" if current_phase_id == "senate" else "readonly",
            "current_step": current_step,
            "actionable": actionable,
            "can_create_proposal": can_create,
            # R2-A-2（C5）：can_select_proposal 补 actionable+step guard，对齐 can_create_proposal 三重 guard
            "can_select_proposal": actionable and current_step == "proposal" and viewer_has_consul,
            "can_propose": actionable and current_step == "proposal",
            "can_trigger_ai_proposer": can_trigger_ai,
            "viewer_has_consul": viewer_has_consul,
            "can_vote": actionable and current_step == "senate_vote" and len(proposals) > 0,
            # D-3 收严：can_veto/can_auto_veto 由 ±viewer_has_tribune 改为严格 mode（NONE → 双 False）
            "can_veto": actionable and current_step == "tribune_veto" and veto_control["mode"] == "HUMAN",
            "can_auto_veto": actionable and current_step == "tribune_veto" and veto_control["mode"] == "AI",
            "viewer_has_tribune": viewer_has_tribune,
            "can_resolve": actionable and current_step == "tribune_veto",
            # R3-G-01 §1.5 冻结公式：can_advance = (current_step=="results") and
            # has_real_senate_result and not takeover_required.required
            # R3-G-01 §1.5 冻结公式：can_advance = (current_step=="results") and
            # has_real_senate_result and not takeover_required.required（required==M_open）
            "can_advance": (current_step == "results") and has_real_senate_result
                           and not takeover_required.get("required", False),
            # WP-G-R4：pending Takeover / 显式空结束 / can_deploy 读模型（会期级 M）
            "pending_takeover": pending_takeover,
            "pending_takeover_locked": pending_takeover_locked,
            "can_deploy": can_deploy,
            "can_finish_proposal_selection": can_finish_empty,
            "can_finish_empty": can_finish_empty,
            "proposal_selection_disabled_reason": proposal_selection_disabled_reason,
            # R3-G-01 §1.5：settlement-pending 可见恢复态（DTO 字段 + 恢复动作位）
            "senate_settlement_pending": senate_settlement_pending,
            "can_resolve_settlement": senate_settlement_pending,
            # AU-R2-2b provenance（AC-R2-11 observability，D-2：authority_reason 为 JSON dict）
            "proposal_control_mode": proposal_control["mode"],
            "veto_control_mode": veto_control["mode"],
            "proposal_actor": proposal_control["actor"],
            "veto_actor": veto_control["actor"],
            "authority_reason": {
                "proposal": proposal_control["authority_reason"],
                "veto": veto_control["authority_reason"],
            },
            "summary": {
                "title": "元老院议事",
                "status": current_step,
                "message": "执政官提案 → 元老院表决 → 保民官否决 → 法案公示与政府运作",
                "faction_leader_count": len(info.get("faction_leaders", [])),
                "active_foreign_war_count": len(active_foreign_wars),
                "war_threat_count": len(war_threats),
                "pending_peace_treaty_count": len(pending_peace_treaties),
                "pending_contract_count": len(pending_contracts),
                "proposal_option_count": len(proposal_options),
                "submitted_proposal_count": len(proposals),
            },
            "faction_leaders": info.get("faction_leaders", []),
            "presiding_officer": info.get("presiding_officer"),
            "active_foreign_wars": active_foreign_wars,
            "takeover_wars": active_foreign_wars,
            "takeover_options": takeover_options,
            "can_takeover": can_takeover,
            # R1-G-05（WP-G-R1 v1.6 §2.5，S4）：并列权威态 takeover_required（per-war
            # required rows）——commanderless ACTIVE 强制接管 Core truth；can_takeover /
            # takeover_options 保持既有可选动作语义不变。R4 增 m_open/m_deploy_ready 会期级。
            "takeover_required": takeover_required,
            "continue_options": continue_options,
            "can_continue": can_continue,
            "war_threats": war_threats,
            "pending_peace_treaties": pending_peace_treaties,
            "governor_vacancies": governor_vacancies,
            "governor_appointments": governor_appointments,
            "pending_contracts": pending_contracts,
            "proposal_options": proposal_options,
            "submitted_proposals": proposals,
            "senate_result": senate_result or {},
            "direct_actions": state.get_senate_direct_actions(),
            "public_announcement": result_data.get("public_announcement", {}) if isinstance(result_data, dict) else {},
            # WP-F R1-F-03 / R2-01：透传每提案已算 vote result——优先中间投影（voted_all 后
            # Stage 2 即可读支持率）；非 voted_all / 结算后无 pending 提案时回退 phase_data
            # 落盘值（R1 既有 results 展示行为不变）。
            "vote_results": projected_vote_results if projected_vote_results else (result_data.get("vote_results", []) if isinstance(result_data, dict) else []),
            # WP-F R2-01：权威 passed-only 否决候选 id 集（单一 producer，AI/Human/DTO/Store/QML 全消费者同源）
            "veto_candidate_ids": veto_candidate_ids,
            "seat_shares": _seat_share_rows(state),
            "warnings": [{
                "type": "info",
                "key": "senate.phase5a",
                "message": "当前开放 Phase 5A 执政官提案；表决、否决与结算由后续子环节接入。",
            }],
            "disabled_reason": "" if actionable else "当前不是元老院阶段或当前行动玩家，暂不可操作。",
        }
        return api_response(True, "Senate phase view refreshed", data)
    except Exception as exc:
        return api_response(False, f"获取元老院视图失败: {exc}", errors=[str(exc)])


def takeover_war(
    state: GameState,
    player_id: str,
    war_id: str,
    reinforcement_n: Optional[int] = None,
    *,
    action: str = "reserve",
    bypass_turn_check: bool = False,
) -> dict:
    """WP-G-R4 (SA v1.7 §2.2/§2.5, O5/OD-R4-06)：Takeover 决策/承诺与物理部署分离。

    action 语义（V=reservation，T=pending commitment，同一持久对象两个状态）：
      reserve（默认）——勾选+选 War+设 N → 创建/更新单 reservation（RESERVED）；
        edit N 释放旧 N 占用新 N；换 war 重建；reservation 保持至 Submit。
      cancel —— RESERVED → 释放（None）；不触碰已锁定配置。
      submit —— whole-package 校验 → RESERVED→LOCKED（T 写入）；**零部署副作用**：
        不清 treaty / 不 TRUCE→ACTIVE / 不改 Commander / 不 rebind / 不征召 /
        不置 absent / 不结束 Senate / 不写 D_Takeover（R4-17/R4-18/R4-10）。

    C 优先单 commitment：C（commanderless ACTIVE）非空时 lock 目标必须为 C 战；
    P（TRUCE+pending）战仅 C 为空时可锁。同战 Peace 双向互斥（Core 强制，R4-20）。
    校验失败留在 RESERVED、零写入、可编辑重试（whole-package 原子，P1-RF-02）。

    部署唯一 owner = advance_senate_phase（§2.4b 迁移表 #1~#14）。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    # 1. 权限校验（bypass_turn_check 仅供 AI canonical 路径内部使用，语义与 propose 同源）
    if not bypass_turn_check and not state.is_current_player(player_id):
        state.log_event(
            "战争接管: 权限失败（非当前玩家）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reason": "not_current_player"},
        )
        return api_response(False, "当前不是您的回合")

    player = state.get_player(player_id)
    if not player:
        state.log_event(
            "战争接管: 权限失败（玩家不存在）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reason": "player_not_found"},
        )
        return api_response(False, "玩家不存在")

    faction = state.get_faction(player.faction_id)
    if not faction:
        state.log_event(
            "战争接管: 权限失败（派系不存在）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reason": "faction_not_found"},
        )
        return api_response(False, "派系不存在")

    politics = _political_system(state)
    consul_figure = None
    for member in faction.get_members(state):
        # AU-R2-2c（C5）：内联四条件退役 → 委托单一谓词（行为等价 FACT-5；war 生命周期仍 WP-G）
        if politics._is_eligible_consul(member):
            consul_figure = member
            break
    if not consul_figure:
        state.log_event(
            "战争接管: 权限失败（无存活且在罗马的执政官）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reason": "no_eligible_consul"},
        )
        return api_response(False, "您的派系没有存活且在罗马的执政官，无法接管战争")

    # 2. 可执行校验
    if not war_id:
        state.log_event(
            "战争接管: 拒绝（war_id 缺失）",
            level=logging.DEBUG,
            extra={"player_id": player_id, "reason": "missing_war_id"},
        )
        return api_response(False, "缺少 war_id")

    ws = state.get_war_system()
    if not ws:
        return api_response(False, "战争系统不可用")

    war = ws.get_war_by_id(war_id)
    if not war:
        state.log_event(
            "战争接管: 拒绝（战争不存在）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reason": "war_not_found"},
        )
        return api_response(False, "战争不存在")

    # A1（F 件 §2.1）：双前置 P1/P2 + 异常态 fail closed
    treaty = war.peace_treaty
    treaty_pending = bool(treaty and treaty.get("status") == "pending")
    if war.status == WarStatus.TRUCE:
        if not treaty_pending:
            state.log_event(
                "战争接管: 拒绝（TRUCE 但无待决草案）",
                level=logging.DEBUG,
                extra={"war_id": war_id, "player_id": player_id, "reason": "truce_without_pending"},
            )
            return api_response(False, "该停战战争无待决和约草案，无法接管")
        # P1 合法入口（TRUCE + pending；可替换现有指挥官）
    elif war.status == WarStatus.ACTIVE:
        if treaty_pending:
            state.log_event(
                "战争接管: 拒绝（ACTIVE+pending 异常态）",
                level=logging.DEBUG,
                extra={"war_id": war_id, "player_id": player_id, "reason": "active_with_pending"},
            )
            return api_response(False, "异常状态：活跃战争存在待决草案，无法接管")
        # 3. 幂等/重入拒绝：已有有效指挥官（禁任意接管，F 件 §5.1）
        if _war_has_valid_commander(state, war):
            state.log_event(
                "战争接管: 幂等拒绝（已有有效指挥官）",
                level=logging.DEBUG,
                extra={"war_id": war_id, "player_id": player_id, "commander_id": war.commander_id, "reason": "already_taken_over"},
            )
            return api_response(False, "该战争已有有效指挥官，无法接管")
        # P2 合法入口（commanderless ACTIVE）
    else:
        state.log_event(
            "战争接管: 拒绝（状态不可接管）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reason": "war_not_takeoverable"},
        )
        return api_response(False, "该战争不处于可接管状态")

    if war.rebellion_province_id is not None:
        state.log_event(
            "战争接管: 拒绝（起义战争）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reason": "rebellion_war"},
        )
        return api_response(False, "起义战争由总督接管，无法由执政官接管")

    # 4. Reinforcement N 校验（G 件 §4，fail-closed）
    rng = reinforcement_range(state, war)
    if rng is None:
        return api_response(False, "增援值域不可用")
    if reinforcement_n is None:
        reinforcement_n = rng["default"]
    if not isinstance(reinforcement_n, int) or isinstance(reinforcement_n, bool):
        return api_response(False, "增援数量必须为整数")
    if reinforcement_n not in rng["allowed"]:
        state.log_event(
            "战争接管: 拒绝（Reinforcement N 超出值域）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "player_id": player_id, "reinforcement_n": reinforcement_n,
                   "range": rng, "reason": "reinforcement_out_of_range"},
        )
        return api_response(False, f"增援数量超出允许范围（{rng['min']}~{rng['max']}）")

    # ===== WP-G-R4 (O5 / SA v1.7 §2.2/§2.5)：T/V 生命周期（Submit 零部署，R4-17/R4-18）=====
    if action not in ("reserve", "submit", "cancel"):
        return api_response(False, "未知的接管动作（reserve/submit/cancel）")

    # 目标战合法性（P1/P2 双前置 + 起义排除）——reserve/submit 共用同一可接管面：
    # P1 = TRUCE + pending treaty；P2 = commanderless ACTIVE（无 pending treaty）。
    treaty = war.peace_treaty
    treaty_pending = bool(treaty and treaty.get("status") == "pending")
    takeoverable = (
        (war.status == WarStatus.TRUCE and treaty_pending)
        or (war.status == WarStatus.ACTIVE and not treaty_pending
            and not _war_has_valid_commander(state, war))
    ) and war.rebellion_province_id is None
    if not takeoverable:
        state.log_event(
            "战争接管: 拒绝（目标不可接管）",
            level=logging.DEBUG,
            extra={"war_id": war_id, "reason": "war_not_takeoverable"},
        )
        return api_response(False, "该战争当前不可作为接管目标（需 TRUCE+待决草案 或 commanderless ACTIVE 非起义战）")

    pending = state._takeover_pending
    if action == "cancel":
        if not pending or pending.get("status") != "RESERVED":
            return api_response(False, "当前没有可取消的接管配置")
        if pending.get("actor", {}).get("player_id") != player_id:
            return api_response(False, "接管配置不属于当前玩家")
        state.log_event(
            "接管配置: 已取消（reservation 释放）",
            level=logging.DEBUG,
            extra={"war_id": pending.get("war_id"), "reason": "user_cancel"},
        )
        state.set_takeover_pending(None)
        return api_response(True, "已取消接管配置（reservation 释放）", data={"pending_takeover": None, "locked": False})

    # 同战 Peace 双向互斥（Core 强制，R4-20）：目标战已有 peace 提案 → 拒绝新接管配置
    for prop in state.get_senate_proposals():
        if prop.get("type") == "peace" and prop.get("war_id") == war_id:
            return api_response(False, "该战争已有停战提案——接管与停战互斥（需先经表决/否决处置停战提案）")

    # C 集合（mandatory commanderless ACTIVE）；P 战仅 C 为空时可作 commitment 目标
    m_state = _resolve_takeover_required(state)
    c_rows = m_state.get("rows", []) or []
    target_in_c = any(row["war_id"] == war_id for row in c_rows)

    if action == "submit":
        # whole-package 校验（零写入；失败留 RESERVED 可编辑重试）
        if not pending or pending.get("status") != "RESERVED":
            return api_response(False, "没有待锁定的接管配置（请先勾选接管并设置增援数）")
        if pending.get("actor", {}).get("player_id") != player_id:
            return api_response(False, "接管配置不属于当前玩家")
        if pending.get("war_id") != war_id:
            return api_response(False, "接管配置目标与提交目标不一致")
        if c_rows and not target_in_c:
            return api_response(
                False,
                "存在未承诺的强制接管战争——接管目标须为 commanderless ACTIVE 战（P 战仅 C 为空时可锁）",
                data={"pending_takeover": _takeover_pending_dto(state), "whole_package_failed": True},
            )
        ms_now = state.get_military_system()
        pool_now = len(ms_now.get_available_legions()) if ms_now else 0
        n_lock = pending.get("reinforcement_n", 0)
        if pool_now < n_lock:
            return api_response(
                False,
                "增援数量超出当前可用军团池（reservation 保持，可编辑重试）",
                data={"pending_takeover": _takeover_pending_dto(state), "whole_package_failed": True},
            )
        previous_status = war.status.value if hasattr(war.status, "value") else str(war.status)
        pending["status"] = "LOCKED"
        pending["target_commander_id"] = consul_figure.id
        pending["locked_at"] = _turn_label(state)
        pending["provenance"] = "AI" if bypass_turn_check else "HUMAN"
        state.set_takeover_pending(pending)
        state.log_event(
            "战争接管: Submit 锁定（零部署；Senate→Combat 显式推进时原子部署）",
            level=logging.INFO,
            extra={
                "war_id": war_id, "player_id": player_id, "commander_id": consul_figure.id,
                "reinforcement_n": n_lock, "previous_status": previous_status,
                "reason": "takeover_submit_locked", "method": "takeover_war",
            },
        )
        return api_response(
            True,
            "接管配置已锁定（Submit 零部署；显式 Senate→Combat 推进时部署）",
            data={
                "war_id": war_id,
                "commander_id": consul_figure.id,
                "reinforcement_n": n_lock,
                "locked": True,
                "pending_takeover": _takeover_pending_dto(state),
            },
        )

    # reserve（create / edit）：单 reservation（R4-21，无 Soft/Hard 拆分）
    if pending and pending.get("status") == "LOCKED":
        return api_response(False, "接管配置已锁定（Submit 后不可编辑；如无需部署请完成本会期推进）")
    n = reinforcement_n if reinforcement_n is not None else rng.get("default", 1)
    if pending and pending.get("actor", {}).get("player_id") == player_id and pending.get("war_id") == war_id:
        # edit N：旧 N 释放回池、新 N 占用（守恒）；reservation_id 不变
        pending["reinforcement_n"] = n
        state.set_takeover_pending(pending)
        state.log_event(
            "接管配置: reservation 更新 N",
            level=logging.DEBUG,
            extra={"war_id": war_id, "reinforcement_n": n, "reason": "reservation_edit"},
        )
    else:
        # create（或换 war 重建；单 reservation 覆盖释放旧占用）
        new_pending = {
            "reservation_id": uuid.uuid4().hex[:12],
            "session_id": _turn_label(state),
            "actor": {"player_id": player_id, "faction_id": faction.id},
            "war_id": war_id,
            "reinforcement_n": n,
            "status": "RESERVED",
            "provenance": "HUMAN",
            "created_at": _turn_label(state),
            "locked_at": None,
            "consumed_at": None,
        }
        state.set_takeover_pending(new_pending)
        state.log_event(
            "接管配置: reservation 暂存",
            level=logging.DEBUG,
            extra={"war_id": war_id, "reinforcement_n": n, "reason": "reservation_created"},
        )
    return api_response(
        True,
        "接管配置已暂存（reservation；Submit 锁定后零部署，显式推进时部署）",
        data={"war_id": war_id, "reinforcement_n": n, "locked": False,
              "pending_takeover": _takeover_pending_dto(state)},
    )


def _turn_label(state: GameState) -> str:
    """session/turn 审计标签（WP-G-R4 §2.5 schema created_at/locked_at/consumed_at）。"""
    if state.turn is None:
        return "turn0"
    return f"t{state.turn.turn_number}y{abs(state.turn.year)}"


def _takeover_pending_dto(state: GameState) -> Optional[Dict[str, Any]]:
    """get_senate_view T/V 读模型（V/T 共享持有者 GameState._takeover_pending）。"""
    pending = state.get_takeover_pending()
    if not pending:
        return None
    war_name = None
    ws = state.get_war_system()
    if ws:
        war = ws.get_war_by_id(pending.get("war_id"))
        war_name = war.name if war else None
    return {
        "reservation_id": pending.get("reservation_id"),
        "session_id": pending.get("session_id"),
        "war_id": pending.get("war_id"),
        "war_name": war_name,
        "reinforcement_n": pending.get("reinforcement_n"),
        "status": pending.get("status"),
        "provenance": pending.get("provenance"),
        "target_commander_id": pending.get("target_commander_id"),
        "created_at": pending.get("created_at"),
        "locked_at": pending.get("locked_at"),
        "consumed_at": pending.get("consumed_at"),
    }


def _takeover_pool_available(state: GameState, pending: Dict[str, Any]) -> bool:
    """whole-package 校验：reserved N 仍 ≤ 当前可用军团池（跨消费者守恒 §2.5）。"""
    ms = state.get_military_system()
    pool = len(ms.get_available_legions()) if ms else 0
    return pool >= int(pending.get("reinforcement_n", 0) or 0)


def _snapshot_takeover_deploy(state: GameState, war, consul, ms, ns):
    """PRE-COMMIT 受控快照（§2.4b 语义 1 rollback domain 列全）。"""
    ws = state.get_war_system()
    surviving_legions = ms.get_legions_for_battle(war.id) if ms else []
    surviving_fleets = ns.get_fleets_by_war(war.id) if ns else []
    old_cmd = state.get_member(war.commander_id) if war.commander_id else None
    pool_before = {}
    if ms:
        for legion in ms.get_available_legions():
            pool_before[legion.number] = legion.status
    return {
        "war": war,
        "status": war.status,
        "treaty": copy.deepcopy(war.peace_treaty),
        "commander_id": war.commander_id,
        "legion_numbers": list(getattr(war, "legion_numbers", []) or []),
        "in_truce": bool(ws and war in ws._truce_wars),
        "in_active": bool(ws and war in ws._active_wars),
        "legion_cmd": {legion.number: legion.commander_id for legion in surviving_legions},
        "fleet_cmd": {fleet.number: fleet.commander_id for fleet in surviving_fleets},
        "old_cmd": {
            "id": old_cmd.id,
            "is_absent": old_cmd.is_absent,
            "office": old_cmd.office,
            "influence": old_cmd.influence,
        } if old_cmd and old_cmd.id != consul.id and not old_cmd.is_dead else None,
        "consul": consul,
        "consul_absent": consul.is_absent,
        "treasury": state.treasury,
        "pool_before": pool_before,
    }


def _rollback_takeover_deploy(state: GameState, snap: Dict[str, Any]) -> None:
    """完整回滚（§2.4b 语义 1/2：operational mutations + T/V + executed 全回滚域）。"""
    war = snap["war"]
    ws = state.get_war_system()
    ms = state.get_military_system()
    ns = state.naval_system
    # 容器成员 + status/treaty/commander（迁移表 #1/#2/#3 回滚）
    if snap["in_truce"]:
        if war in ws._active_wars:
            ws._active_wars.remove(war)
        if war not in ws._truce_wars:
            ws._truce_wars.append(war)
    else:
        if war in ws._truce_wars:
            ws._truce_wars.remove(war)
        if not snap["in_active"] and war in ws._active_wars:
            ws._active_wars.remove(war)
        if snap["in_active"] and war not in ws._active_wars:
            ws._active_wars.append(war)
    war.status = snap["status"]
    if snap["treaty"] is None:
        war.clear_peace_treaty()
    else:
        war.set_peace_treaty(copy.deepcopy(snap["treaty"]))
    war.commander_id = snap["commander_id"]
    war._legion_numbers = list(snap["legion_numbers"])
    # 幸存 Legion/Fleet rebind 回滚（#7）
    for num, cid in snap["legion_cmd"].items():
        legion = ms.get_legion_by_number(num) if ms else None
        if legion:
            legion.commander_id = cid
    for num, cid in snap["fleet_cmd"].items():
        fleet = ns.get_fleet(num) if ns else None
        if fleet:
            fleet.commander_id = cid
    # 新征召/部分征召军团回滚（#8）：凡来自部署前可用池而现在不再可用的实体 → 释放回池
    # （覆盖「已征召未指派 war_id=None」的 partial recruit 注入与「已指派」两条路径）
    if ms:
        current_available = {legion.number for legion in ms.get_available_legions()}
        for number, pre_status in snap["pool_before"].items():
            legion = ms.get_legion_by_number(number)
            if legion and legion.number not in current_available:
                legion.status = pre_status
                legion.war_id = None
                legion.commander_id = None
    # 旧 Commander 清理回滚（#4/#5/#6）
    old = snap.get("old_cmd")
    if old:
        fig = state.get_member(old["id"])
        if fig:
            fig.is_absent = old["is_absent"]
            fig.office = old["office"]
            fig.influence = old["influence"]
    # Consul absent 回滚（#9）
    if snap["consul"]:
        snap["consul"].is_absent = snap["consul_absent"]
    # treasury 回滚（#10）
    state.treasury = snap["treasury"]


def _deploy_pending_takeover(state: GameState, pending: Dict[str, Any]) -> dict:
    """Senate→Combat 部署单元（SA v1.7 §2.4b）：唯一部署 owner（R4-10），
    由 advance_senate_phase 调用。PRE-COMMIT TRANSACTION → COMMIT FINALIZATION
    （顺序 A 冻结：先 T/V→CONSUMED 后 mark_phase_executed）→ POST-COMMIT AUDIT。
    """
    politics = _political_system(state)
    ws = state.get_war_system()
    ms = state.get_military_system()
    ns = state.naval_system
    war = ws.get_war_by_id(pending.get("war_id")) if ws else None
    if war is None:
        return {"success": False, "message": "接管目标战争不存在（fail-closed）", "reason": "war_not_found"}
    consul = state.get_member(pending.get("target_commander_id") or -1)
    if consul is None or consul.is_dead or consul.is_absent or consul.office != "consul":
        return {"success": False, "message": "锁定执政官不再 eligible（fail-closed）", "reason": "consul_not_eligible"}
    n = int(pending.get("reinforcement_n", 0) or 0)
    previous_status = war.status.value if hasattr(war.status, "value") else str(war.status)

    # ---- A. PRE-COMMIT TRANSACTION ----
    snap = _snapshot_takeover_deploy(state, war, consul, ms, ns)
    try:
        deployed = politics.execute_war_takeover_deploy(war, consul, reinforcement_n=n)
        if not deployed:
            raise RuntimeError("deployment_step_failed")
    except Exception as exc:  # F1/F2/F3 注入 + 真实失败 → 全回滚
        _rollback_takeover_deploy(state, snap)
        state.set_takeover_pending(pending)
        state.log_event(
            "接管部署失败: 完整回滚（T 回 LOCKED，no D，no executed）",
            level=logging.WARNING,
            extra={"war_id": war.id, "reason": "precommit_failed", "error": str(exc)},
        )
        return {"success": False, "message": f"接管部署失败（已回滚，可重试）: {exc}",
                "reason": "precommit_failed", "rolled_back": True}

    # ---- B. COMMIT FINALIZATION（顺序 A 冻结：先 T/V→CONSUMED 后 mark_phase_executed）----
    try:
        pending["status"] = "CONSUMED"
        pending["consumed_at"] = _turn_label(state)
        state.set_takeover_pending(pending)
        state.mark_phase_executed("senate")
    except Exception as exc:  # F3b：commit-finalization 内失败 → 全回滚 + T 回 LOCKED
        _rollback_takeover_deploy(state, snap)
        pending["status"] = "LOCKED"
        pending["consumed_at"] = None
        state.set_takeover_pending(pending)
        state.log_event(
            "接管部署 commit-finalization 失败: 完整回滚（T 回 LOCKED，retry-safe）",
            level=logging.WARNING,
            extra={"war_id": war.id, "reason": "commit_finalization_failed", "error": str(exc)},
        )
        return {"success": False, "message": f"接管部署提交失败（已回滚，可重试）: {exc}",
                "reason": "commit_finalization_failed", "rolled_back": True}

    resulting_status = war.status.value if hasattr(war.status, "value") else str(war.status)
    trigger = "ai_auto" if pending.get("provenance") == "AI" else "human_explicit"

    # ---- C. POST-COMMIT AUDIT（不回滚业务；失败独立上报不重跑，§2.4b 语义 8）----
    try:
        state.record_senate_direct_action({
            "action_type": "takeover_deploy",
            "action": "takeover",
            "kind": "takeover_deploy",
            "exactly_once_key": (
                f"takeover_deploy:{war.id}:{pending.get('session_id')}:{pending.get('reservation_id')}"
            ),
            "war_id": war.id,
            "war_name": war.name,
            "commander_id": consul.id,
            "commander_name": consul.get_formal_name(),
            "legions": list(getattr(war, "legion_numbers", []) or []),
            "reinforcement_n": n,
            "trigger_source": trigger,
            "previous_status": previous_status,
            "resulting_status": resulting_status,
        })
        state.log_event(
            "战争接管: Senate→Combat 原子部署完成",
            level=logging.INFO,
            extra={
                "type": "senate_takeover_deployed",
                "war_id": war.id,
                "new_commander": consul.id,
                "reinforcement_n": n,
                "exactly_once_key": f"takeover_deploy:{war.id}:{pending.get('session_id')}:{pending.get('reservation_id')}",
                "trigger_source": trigger,
            },
        )
    except Exception as exc:
        state.log_event(
            "接管部署 audit 上报失败（业务已 committed；独立记录，不重跑军事部署）",
            level=logging.WARNING,
            extra={"war_id": war.id, "reason": "audit_failed", "error": str(exc)},
        )
    return {"success": True, "war_id": war.id, "commander_id": consul.id, "reinforcement_n": n,
            "reason": "deployed", "previous_status": previous_status,
            "resulting_status": resulting_status}


def continue_war(state: GameState, player_id: str, war_id: str, reinforcement_n: Optional[int] = None) -> dict:
    """Continue Existing Command（A2，G1-21 / F 件 §2.2）：执政官继续现有指挥，不接管、不提交和约。

    前置：TRUCE + pending treaty + 现有 commander 有效；N 经 reinforcement_range 重校验。
    语义：清条约 → TRUCE→ACTIVE → 保留 commander → 保留幸存 → 征召 N → bind 现有 commander。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    # 1. 权限校验
    if not state.is_current_player(player_id):
        return api_response(False, "当前不是您的回合")
    player = state.get_player(player_id)
    if not player:
        return api_response(False, "玩家不存在")
    faction = state.get_faction(player.faction_id)
    if not faction:
        return api_response(False, "派系不存在")
    politics = _political_system(state)
    consul_figure = None
    for member in faction.get_members(state):
        if politics._is_eligible_consul(member):
            consul_figure = member
            break
    if not consul_figure:
        return api_response(False, "您的派系没有存活且在罗马的执政官，无法继续指挥")

    # 2. 可执行校验
    if not war_id:
        return api_response(False, "缺少 war_id")
    ws = state.get_war_system()
    if not ws:
        return api_response(False, "战争系统不可用")
    war = ws.get_war_by_id(war_id)
    if not war:
        return api_response(False, "战争不存在")
    treaty = war.peace_treaty
    treaty_pending = bool(treaty and treaty.get("status") == "pending")
    if war.status != WarStatus.TRUCE or not treaty_pending:
        return api_response(False, "该战争不处于可继续指挥状态（需停战且有待决和约）")
    if not _war_has_valid_commander(state, war):
        return api_response(False, "现有指挥官无效，无法继续指挥（可考虑接管）")
    if war.rebellion_province_id is not None:
        return api_response(False, "起义战争由总督接管，无法继续指挥")

    # 3. Reinforcement N 校验（G 件 §4，fail-closed）
    rng = reinforcement_range(state, war)
    if rng is None:
        return api_response(False, "增援值域不可用")
    if reinforcement_n is None:
        reinforcement_n = rng["default"]
    if not isinstance(reinforcement_n, int) or isinstance(reinforcement_n, bool):
        return api_response(False, "增援数量必须为整数")
    if reinforcement_n not in rng["allowed"]:
        return api_response(False, f"增援数量超出允许范围（{rng['min']}~{rng['max']}）")

    # 4. 执行（Continue 唯一 mutation）
    previous_status = war.status.value if hasattr(war.status, "value") else str(war.status)
    if not politics.execute_war_continue_direct(war, consul_figure, reinforcement_n=reinforcement_n):
        return api_response(False, "继续指挥失败")
    resulting_status = war.status.value if hasattr(war.status, "value") else str(war.status)
    state.record_senate_direct_action({
        "action_type": "continue",
        "action": "continue",
        "war_id": war_id,
        "war_name": war.name,
        "commander_id": war.commander_id,
        "legions": list(getattr(war, "legion_numbers", []) or []),
        "reinforcement_n": reinforcement_n,
        "trigger_source": "human_explicit",
        "previous_status": previous_status,
        "resulting_status": resulting_status,
    })
    return api_response(
        True,
        "继续现有指挥成功",
        data={
            "war_id": war_id,
            "commander_id": war.commander_id,
            "legions": list(getattr(war, "legion_numbers", []) or []),
            "reinforcement_n": reinforcement_n,
        },
    )


def propose(state: GameState, player_id: str, proposal_type: str, bypass_turn_check: bool = False, **kwargs) -> dict:
    """记录元老院提案。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    result = _political_system(state).create_proposal(
        player_id,
        proposal_type,
        bypass_turn_check=bypass_turn_check,
        **kwargs,
    )
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )



def propose_many(state: GameState, player_id: str, proposals: List[Dict[str, Any]]) -> dict:
    """Record a batch of GUI-selected senate proposals (0…N; empty batch is a legal decision)."""
    if not state:
        return api_response(False, "无效的游戏状态")
    if not proposals:
        # D-09 / SA §3.1（AU-3）：空批 = 合法政治决策「本会期不提交法案」，标记决策完成
        state.senate_proposal_decision_complete = True
        return api_response(True, "本会期未提交法案", data={"created": []})
    created = []
    errors = []
    for spec in proposals:
        proposal_type = spec.get("type")
        params = spec.get("params", {}) or {}
        result = propose(state, player_id, proposal_type, **params)
        if result.get("success"):
            created.append({
                "proposal_id": result.get("data", {}).get("proposal_id"),
                "type": proposal_type,
            })
        else:
            errors.append(result.get("message", "提案失败"))
    if errors and not created:
        return api_response(False, "提交法案失败", data={"created": created}, errors=errors)
    # 非空批成功路径同样标记决策完成（供 get_senate_view 区分「未决策」vs「已决策」）
    state.senate_proposal_decision_complete = True
    return api_response(
        True,
        f"已提交 {len(created)} 项法案",
        data={"created": created, "errors": errors},
        errors=errors,
    )


def auto_submit_proposals(
    state: GameState,
    budget_decider: Optional[AutoBudgetDecider] = None,
    land_proposal_deciders: Optional[List[LandProposalDecider]] = None,
) -> dict:
    """为 AI 执政官自动生成所有提案（无控制台输出）。

    Args:
        state: 游戏状态
        budget_decider: 预算决策器（默认 AutoBudgetDecider）
        land_proposal_deciders: 土地法案决策器列表
            （默认 [AutoLandProposalDecider("populares","distribution"),
                   AutoLandProposalDecider("optimates","sale")]）

    Returns:
        api_response dict:
            success: bool
            message: str
            data: {"proposals": [{"type": ..., "description": ..., ...}]}
            errors: []
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    # 1. 查找执政官人物（AU-R2-2c，C3 收敛）：全局 eligible Consul 唯一查找路径 =
    #    PoliticalSystem._find_any_eligible_consul（FACT-3：原 leader fallback 带完整资格校验，
    #    在 get_living_members 全量迭代下不可达成功 → 等效死代码，收敛移除；行为等价 D-7）。
    consul_figure = _political_system(state)._find_any_eligible_consul()
    if not consul_figure:
        return api_response(False, "没有执政官，无法自动提交提案")

    # 2. 查找执政官对应玩家
    consul_player = state.get_player_by_faction(consul_figure.faction_id)
    if not consul_player:
        return api_response(False, "执政官无对应玩家")
    consul_player_id = consul_player.player_id

    # 3. 默认决策器
    if budget_decider is None:
        budget_decider = AutoBudgetDecider()
    if land_proposal_deciders is None:
        land_proposal_deciders = [
            AutoLandProposalDecider("populares", "distribution"),
            AutoLandProposalDecider("optimates", "sale"),
        ]

    created_proposals = []
    errors = []

    # ========== 4a. 宣战提案（战争威胁） ==========
    ws = state.get_war_system()
    if ws:
        threats = ws.get_threat_wars()
        if threats:
            propose_chance = state.config.get("testing.propose_war_chance", 0.7)
            always_declare = state.config.get("testing.always_declare", False)
            # P1-a: value range 改由 _legion_options_for_war（config 派生）提供，多战争总和守恒
            ms = state.get_military_system()
            remaining = len(ms.get_available_legions()) if ms else 0

            for war in threats:
                if war.peace_treaty and war.peace_treaty.get('status') == 'pending':
                    continue
                if war.naval_required:
                    naval_system = state.naval_system
                    if not naval_system or not naval_system.get_available_fleets():
                        continue

                if always_declare or random.random() < propose_chance:
                    legion_options = _legion_options_for_war(state, war)
                    if legion_options is None or remaining < 1:
                        continue  # 无权威值域 / 可用军团不足 → 跳过宣战（防御）
                    lo = legion_options["min"]
                    hi = min(remaining, legion_options["max"])
                    if hi < lo:
                        continue
                    legions = random.randint(lo, hi)
                    result = propose(
                        state, consul_player_id, "war",
                        bypass_turn_check=True,
                        war_id=war.id,
                        legions=legions,
                    )
                    if result["success"]:
                        remaining -= legions  # 总和守恒：已提交宣战占用的军团从池中扣除
                        created_proposals.append({
                            "type": "war",
                            "war_id": war.id,
                            "legions": legions,
                            "description": f"对 {war.name} 宣战，申请征召 {legions} 个军团",
                        })
                    else:
                        errors.append(f"宣战失败({war.id}): {result['message']}")

    # ========== 4b. 停战草案（待决停战） ==========
    # A7（F 件 §2.3 / R-16 互斥）：同轮不双路径——先做 AI 接管只读预决策（单次 decider
    # 决策，零 mutation），AI 将接管的 TRUCE 战争跳过 peace 提案；尾部执行复用同一决策
    # （防 decider 二次 random 漂移）。AI Continue 不在 GA 新增（4b peace + takeover
    # 二选一，AI 策略由 decider 驱动，不发明新策略）。
    politics = _political_system(state)
    ai_takeover_plan = politics.plan_ai_takeovers()
    ai_takeover_war_ids = {r["war_id"] for r in ai_takeover_plan}
    if ws:
        pending_peace = ws.get_truce_wars_with_pending_treaty()
        for war in pending_peace:
            if war.id in ai_takeover_war_ids:
                state.log_event(
                    f"AI 停战提案跳过（同轮接管互斥）: war={war.id}",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "reason": "ai_takeover_mutual_exclusion"},
                )
                continue
            result = propose(
                state, consul_player_id, "peace",
                bypass_turn_check=True,
                war_id=war.id,
            )
            if result["success"]:
                created_proposals.append({
                    "type": "peace",
                    "war_id": war.id,
                    "description": f"对 {war.name} 的停战协议进行表决",
                })
            else:
                errors.append(f"停战提案失败({war.id}): {result['message']}")

    # ========== 4c. 总督任命（行省空缺） ==========
    all_provinces = [p for p in state.get_all_provinces() if p.conquered and p.province_id != 0]
    proconsul_provinces = [p for p in all_provinces if p.governor_type == "proconsul"]
    propraetor_provinces = [p for p in all_provinces if p.governor_type == "propraetor"]

    def _get_candidates(office_type: str):
        cand_list = []
        for fig in state.get_living_members():
            if fig.is_absent:
                continue
            if fig.office is not None and not fig.office.startswith("ex-"):
                continue
            last_end = None
            for term in fig.office_history:
                if term.office_type == office_type and term.end_turn is not None:
                    if last_end is None or term.end_turn > last_end:
                        last_end = term.end_turn
            if last_end is not None:
                cand_list.append((fig, last_end))
        cand_list.sort(key=lambda x: -x[1])
        return [c[0] for c in cand_list]

    consuls = _get_candidates('consul')
    praetors = _get_candidates('praetor')
    used = set()

    def _assign(provinces, candidates, used_set):
        remaining = list(provinces)
        random.shuffle(remaining)
        assignments = []
        for cand in candidates:
            if cand.id in used_set:
                continue
            if not remaining:
                break
            chosen = random.choice(remaining)
            remaining.remove(chosen)
            assignments.append((chosen, cand))
            used_set.add(cand.id)
        return assignments

    proconsul_assignments = _assign(proconsul_provinces, consuls, used)
    propraetor_assignments = _assign(propraetor_provinces, praetors, used)

    for province, candidate in proconsul_assignments + propraetor_assignments:
        result = propose(
            state, consul_player_id, "governor",
            bypass_turn_check=True,
            province_id=province.province_id,
            candidate_id=candidate.id,
        )
        if result["success"]:
            created_proposals.append({
                "type": "governor",
                "province_id": province.province_id,
                "candidate_id": candidate.id,
                "description": f"任命 {candidate.get_formal_name()} 为 {province.name} 行省总督",
            })
        else:
            errors.append(f"总督任命失败({province.province_id}): {result['message']}")

    # ========== 4d. 预算合同 ==========
    pending_contracts = [c for c in state.contracts if c.status == ContractStatus.PENDING]
    if pending_contracts:
        budget_proposals = budget_decider.decide_proposals(pending_contracts, state)
        for contract in budget_proposals:
            kwargs = {"contract_id": contract.id}
            if contract.contract_type == ContractType.PUBLIC_WORKS:
                # P1-a: 值域改由 _budget_range_for_contract（config 派生）提供，不再读 code-default margin
                budget_range = _budget_range_for_contract(state, contract)
                if budget_range is None:
                    modified_budget = contract.base_cost
                else:
                    modified_budget = random.randint(budget_range["min"], budget_range["max"])
                kwargs["modified_budget"] = modified_budget
                state.log_event(
                    f"自动预算提案: 合同 {contract.name} 值域 [{budget_range['min'] if budget_range else contract.base_cost},{budget_range['max'] if budget_range else contract.base_cost}] → {modified_budget}",
                    level=logging.DEBUG,
                )
            result = propose(state, consul_player_id, "budget", bypass_turn_check=True, **kwargs)
            if result["success"]:
                budget_display = kwargs.get("modified_budget", contract.base_cost)
                created_proposals.append({
                    "type": "budget",
                    "contract_id": contract.id,
                    "modified_budget": budget_display,
                    "description": f"{contract.name} 预算 {budget_display} 塔兰特",
                })
            else:
                errors.append(f"预算提案失败({contract.id}): {result['message']}")

    # ========== 4e. 土地法案 ==========
    for faction in state.factions.values():
        for decider in land_proposal_deciders:
            decider_result = decider.decide_proposal(faction.id, state)
            if decider_result:
                act_type, percent = decider_result
                # AU-7（P2-04 clamp）：percent → amount_C 权威换算，小公地量下防 0（≥1）
                amount_C = max(1, int(state.get_national_public_land() * percent))
                proposal_id_ref = None
                result = propose(
                    state, consul_player_id, "land",
                    bypass_turn_check=True,
                    act_type=act_type,
                    amount_C=amount_C,
                )
                if result["success"]:
                    act_name = "公地出售法案" if act_type == "sale" else "公地分配法案"
                    proposal_id_ref = result.get("data", {}).get("proposal_id")
                    state.log_event(
                        f"Land proposal {proposal_id_ref}: submitted to senate for vote",
                        level=logging.DEBUG,
                        extra={
                            "proposal_id": proposal_id_ref,
                            "act_type": act_type,
                            "amount_C": amount_C,
                            "faction_id": faction.id,
                        },
                    )
                    created_proposals.append({
                        "type": "land",
                        "act_type": act_type,
                        "amount_C": amount_C,
                        "percent": amount_C / state.get_national_public_land() if state.get_national_public_land() else 0.0,
                        "description": f"{act_name} {amount_C} C 国家公地",
                    })
                else:
                    errors.append(f"土地法案失败({act_type}): {result['message']}")

    # ========== 4f. AI 自动接管（C1 触发点，G3/D-1 采纳） ==========
    # AU-R1-05b：AI 接管走 Direct Action 语义（execute_ai_takeover_direct_action，与 human
    # takeover_war 同 mutation 路径 + provenance trigger_source="ai_auto"）。唯一 AI 接管调用点
    # ——不得放回 resolve_senate（resolve 零 takeover）；GUI（session_store）与 CLI
    # （phase_senate）双入口共享本函数，AI 接管经同入口继承（D-4，CLI 语义不回归）。
    # A7：复用 4b 前 plan_ai_takeovers 的单次决策（同轮互斥，防二次 random 漂移）。
    ai_takeovers = politics.execute_ai_takeover_direct_action(predecided=ai_takeover_plan)
    if ai_takeovers:
        state.log_event(
            f"AI 自动接管 {len(ai_takeovers)} 个战争（Direct Action 语义）",
            level=logging.INFO,
            extra={
                "type": "senate_ai_takeover_batch",
                "count": len(ai_takeovers),
                "war_ids": [r["war_id"] for r in ai_takeovers],
                "trigger_source": "ai_auto",
            },
        )

    # ========== 返回结果 ==========
    message = f"已自动提交 {len(created_proposals)} 项提案"
    success = bool(created_proposals) or not errors
    if success:
        # D-09 / SA §3.1（AU-3）：AI 空批同样合法，标记提案决策完成（0 提案也推进阶段）
        state.senate_proposal_decision_complete = True
    return api_response(
        success=success,
        message=message,
        data={"proposals": created_proposals},
        errors=errors,
    )


def advance_senate_phase(state: GameState, player_id: str) -> dict:
    """Mark senate complete and advance the GUI shell to combat.

    WP-G-R4 (SA v1.7 §2.4b, O5)：本函数 = Senate→Combat **唯一部署 owner**。当存在
    LOCKED pending Takeover 时，在真实 Senate result 之后执行原子部署单元（迁移表
    #1→#14，PRE-COMMIT/COMMIT FINALIZATION 顺序 A/POST-COMMIT AUDIT）；无 pending 时
    保持原 mark-executed 语义。开 Combat GUI/打开 Combat 阶段不是部署触发（R4-23）。
    """
    if not state:
        return api_response(False, "Invalid game state")
    if not state.is_current_player(player_id):
        return api_response(False, "Current player mismatch")
    # Guard: prevents double-advance if phase already marked executed
    if state.is_phase_executed("senate"):
        return api_response(False, "Senate phase already executed")
    # pending-aware M 门（SA v1.7 §2.3）：not M_open 才放行（LOCKED T 覆盖 C 战 → 放行）
    takeover_state = _resolve_takeover_required(state)
    if takeover_state.get("m_open"):
        return api_response(
            False,
            "存在未完成的强制战争接管（执政官须先锁定接管目标），暂不能推进阶段",
            data={"takeover_required": takeover_state, "advance_guard": "takeover_required"},
        )
    if not state.get_phase_result("senate"):
        return api_response(False, "Senate result is not ready")
    pending = state._takeover_pending
    if pending and pending.get("status") == "LOCKED":
        # 唯一部署边界：原子/exactly-once 部署（失败 fail-closed，T 回 LOCKED 可重试）
        deploy = _deploy_pending_takeover(state, pending)
        if not deploy.get("success"):
            return api_response(
                False,
                deploy.get("message", "接管部署失败（已回滚，不进入 Combat）"),
                data={
                    "takeover_required": takeover_state,
                    "pending_takeover": _takeover_pending_dto(state),
                    "deploy": deploy,
                    "advance_guard": "deployment_failed",
                },
            )
        return api_response(
            True,
            "Advanced to combat phase（Senate→Combat 原子部署完成）",
            data={"next_phase_id": "combat", "deploy": deploy,
                  "pending_takeover": _takeover_pending_dto(state)},
        )
    state.mark_phase_executed("senate")
    return api_response(True, "Advanced to combat phase", data={"next_phase_id": "combat"})

def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


def vote(state: GameState, player_id: str, proposal_ids: List[int], votes: List[bool]) -> dict:
    """记录玩家对多个提案的投票。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    result = _political_system(state).record_vote(player_id, proposal_ids, votes)
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


def veto(state: GameState, player_id: str, proposal_ids: List[int]) -> dict:
    """记录保民官对已通过提案的否决。"""
    if not state:
        return api_response(False, "无效的游戏状态")
    result = _political_system(state).record_veto(player_id, proposal_ids)
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


def resolve_senate(
    state: GameState,
    vote_decider: Optional[SenateVoteDecider] = None,
) -> dict:
    """执行元老院阶段最终结算。

    AU-R1-05a（C1，D-1 采纳）：takeover_decider 参数已移除——resolve_senate 零 takeover
    mutation（不再隐藏 process_war_takeover）；AI 自动接管唯一触发点 = auto_submit_proposals
    尾部（execute_ai_takeover_direct_action，Direct Action 语义）。

    R3-G-01（设计 §1.2 #5 / §1.5，FROZEN）：WP-G mandatory Takeover 专用门——任何结算
    mutation 前复检 live takeover_required；required=True → 结构化 takeover_required 拒绝
    （不结算、不写 phase_result、不安排总督/舰队副作用）。已存在成功 phase_result → 幂等
    no-op success（不重复结算/不二次安排副作用）。失败路径从不持久化 phase_result 冒充成功。
    """
    if not state:
        return api_response(False, "无效的游戏状态")
    takeover_required = _resolve_takeover_required(state)
    if takeover_required.get("required"):
        state.log_event(
            "元老院结算拒绝: 存在未完成的强制战争接管（不结算不写 phase_result）",
            level=logging.WARNING,
            extra={"reason": "takeover_required", "rows": takeover_required.get("rows", [])},
        )
        return api_response(
            False,
            "存在未完成的强制战争接管（执政官须先完成接管），暂不能结算元老院",
            data={"takeover_required": takeover_required, "settlement_guard": "takeover_required"},
        )
    existing_result = state.get_phase_result("senate")
    if existing_result:
        # §1.5 幂等 no-op：已存在成功 phase_result → 不重复结算、不二次安排副作用
        return api_response(
            True,
            "元老院结果已记录（幂等 no-op）",
            data=existing_result.get("data", {}) if isinstance(existing_result, dict) else {},
        )
    # WP-G-R4 (SA v1.7 §2.3/§2.3b)：显式空选择守卫——零 proposals、P=false、R 不存在时
    # 必须先显式提交空批（propose_many([]) → P=true）关闭选择，禁隐式 resolve（R4-09：
    # Takeover-only Submit 不触发隐式 resolve_senate(0)；空批合法决策 = 显式 finish）。
    if not state.get_senate_proposals() and not state.senate_proposal_decision_complete:
        return api_response(
            False,
            "提案选择未完成：请先显式提交空批或完成提案后再结算",
            data={
                "proposal_selection_not_complete": True,
                "takeover_required": takeover_required,
                "settlement_guard": "proposal_selection_not_complete",
            },
        )
    result = _political_system(state).resolve_senate(vote_decider)

    # Add DBUG logging for land proposal resolution results
    passed_snapshot = result.get("data", {}).get("passed_proposals_snapshot", [])
    for prop in passed_snapshot:
        if prop.get("type") == "land":
            prop_id = prop.get("id")
            act_type = prop.get("act_type")
            state.log_event(
                f"Land proposal {prop_id}: resolution=passed",
                level=logging.DEBUG,
                extra={
                    "proposal_id": prop_id,
                    "act_type": act_type,
                    "resolution": "passed",
                },
            )
    rejected_snapshot = result.get("data", {}).get("rejected_proposals_snapshot", [])
    for prop in rejected_snapshot:
        if prop.get("type") == "land":
            prop_id = prop.get("id")
            act_type = prop.get("act_type")
            state.log_event(
                f"Land proposal {prop_id}: resolution=rejected",
                level=logging.DEBUG,
                extra={
                    "proposal_id": prop_id,
                    "act_type": act_type,
                    "resolution": "rejected",
                },
            )

    # Phase result data — start with core resolve result, then extend with
    # post-settlement operations so both CLI and GUI paths execute them.
    phase_data = result.get("data", {}) or {}

    # S4: Fleet assignment — assign available fleets to active naval wars
    fleet_result = assign_fleets_to_active_wars(state)
    fleet_data = fleet_result.get("data") or {}
    if fleet_result.get("success"):
        assigned_fleets = fleet_data.get("assigned", [])
        if assigned_fleets:
            state.log_event(
                f"resolve_senate: assigned fleets to {len(assigned_fleets)} wars",
                level=logging.INFO,
                extra={"assigned_fleets": assigned_fleets},
            )
    phase_data["fleet_assignments"] = fleet_data.get("assigned", [])

    # S4: Governor assignment — appoint governors to vacant provinces
    governor_results = assign_governors(state)
    phase_data["governor_assignments"] = governor_results

    # S4: Rebellion commander assignment — appoint commanders to active rebellions
    ws = state.get_war_system()
    if ws:
        commander_results = ws.assign_rebellion_commanders()
        phase_data["rebellion_commander_assignments"] = commander_results

    # WP-D AU-5/AU-6: direct_actions + public_announcement 组装（公示随 phase_result 持久化，
    # get_senate_view 经 result_data 回读）。enacted_proposals 仅 final enacted（D-06：rejected/vetoed 不进公示）。
    phase_data["direct_actions"] = result.get("data", {}).get("direct_actions", [])
    phase_data["public_announcement"] = {
        "enacted_proposals": [
            {
                "proposal_id": p.get("id"),
                "type": p.get("type"),
                "title": _proposal_label(state, p),
                "key_parameters": _announcement_key_params(p),
            }
            for p in (result.get("data", {}).get("passed_proposals_snapshot", []) or [])
        ],
        "direct_actions": phase_data["direct_actions"],
    }

    # Record phase result immediately — before any callback (e.g. _on_refresh)
    # can read it. This eliminates the stale-state window where QML binding
    # sees no senate result during adapter.resolve_senate().
    state.record_phase_result("senate", {
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "data": phase_data,
    })
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=phase_data,
        errors=result.get("errors", []),
    )


# ==================== 兼容辅助函数 ====================

def execute_war_declaration(state: GameState, war, consul_id: int, legions: int):
    """执行宣战。保留旧公共函数名，内部委托 PoliticalSystem。"""
    return _political_system(state).execute_war_declaration(war, consul_id, legions)


def execute_passed_peace_treaty(state: GameState, war):
    """执行通过的停战草案。保留旧公共函数名，内部委托 PoliticalSystem。"""
    return _political_system(state).execute_passed_peace_treaty(war)


def process_war_takeover(state: GameState) -> dict:
    """处理战争接管逻辑（自动执行）。

    分析当前战争状态 → 判断接管条件 → 执行接管 → 更新实体。
    返回接管结果字典。

    业务逻辑继承自 phase_senate.py CLI _execute_war_takeover_manual:
    - 检查接管条件（军事优势/政治支持等）
    - 执行接管操作
    - 更新相关实体状态（Province, Faction, War 等）
    - 处理接管后连锁反应

    Returns:
        dict: {
            "takeover_executed": bool,
            "war_id": str | None,
            "affected_provinces": list[str],
            "result_details": str,
            "timestamp": int
        }
    """
    if not state:
        return {"takeover_executed": False, "war_id": None, "affected_provinces": [], "result_details": "Invalid state", "timestamp": 0}

    ws = state.get_war_system()
    if not ws:
        return {"takeover_executed": False, "war_id": None, "affected_provinces": [], "result_details": "War system unavailable", "timestamp": 0}

    ms = state.get_military_system()
    if not ms:
        return {"takeover_executed": False, "war_id": None, "affected_provinces": [], "result_details": "Military system unavailable", "timestamp": 0}

    import datetime
    timestamp = state.turn.turn_number if hasattr(state, 'turn') and state.turn else 0
    executed = False
    affected_provinces = []
    war_id = None
    details = []

    # 遍历活跃战争，检查接管条件
    for war in ws.get_active_wars():
        if war.rebellion_province_id is not None:
            # 起义战争由总督自动接管，跳过
            state.log_event(
                f"process_war_takeover: checking war {war.id}, takeover_eligible=False (rebellion)",
                level=logging.DEBUG,
                extra={"war_id": war.id, "eligible": False, "reason": "rebellion_war", "method": "process_war_takeover"},
            )
            continue

        # 检查是否需要接管（无指挥官或指挥官已阵亡/缺失）
        needs_takeover = war.commander_id is None or not state.get_member(war.commander_id)
        if not needs_takeover:
            commander = state.get_member(war.commander_id)
            if commander and commander.is_dead:
                needs_takeover = True

        if not needs_takeover:
            state.log_event(
                f"process_war_takeover: checking war {war.id}, takeover_eligible=False (already assigned)",
                level=logging.DEBUG,
                extra={"war_id": war.id, "eligible": False, "reason": "commander_assigned", "method": "process_war_takeover"},
            )
            continue

        state.log_event(
            f"process_war_takeover: checking war {war.id}, takeover_eligible=True",
            level=logging.DEBUG,
            extra={"war_id": war.id, "eligible": True, "method": "process_war_takeover"},
        )

        # 获取可用军团
        available = ms.get_available_legions()
        if not available:
            details.append(f"War {war.name}: no available legions")
            continue

        # 计算所需军团数（D-2/P1-a：值域改由 config 派生 senate_war_legions.min..可用池，不再读 testing.min/max_legions）
        sw = state.config.get("economic_rules.senate_war_legions")
        min_leg = int(sw.get("min", 1)) if sw else 1
        recruit_count = min(random.randint(min_leg, len(available)), len(available))

        # 征召军团
        results = ms.recruit_multiple(recruit_count)
        recruited_numbers = [r[0] for r in results if r[1]]
        if not recruited_numbers:
            details.append(f"War {war.name}: recruitment failed")
            continue

        # 指派军团至战争
        assigned, msg = ms.assign_to_war(recruited_numbers, war.id, war.commander_id or 0)
        if assigned > 0:
            for num in recruited_numbers:
                war.add_legion_number(num)

            state.log_event(
                f"process_war_takeover: province {getattr(war, 'rebellion_province_id', None)}: takeover_action=assign_legions",
                level=logging.DEBUG,
                extra={"war_id": war.id, "legions": len(recruited_numbers), "method": "process_war_takeover"},
            )
            affected_provinces.append(war.name)
            war_id = war.id
            executed = True
            details.append(f"War {war.name}: assigned {len(recruited_numbers)} legions ({msg})")

            state.log_event(
                f"War takeover executed: war={war.id}, result={msg}",
                level=logging.INFO,
                extra={"war_id": war.id, "result": msg, "method": "process_war_takeover"},
            )
        else:
            details.append(f"War {war.name}: assignment failed - {msg}")

    result_summary = "; ".join(details) if details else "No takeover needed"

    return {
        "takeover_executed": executed,
        "war_id": war_id,
        "affected_provinces": affected_provinces,
        "result_details": result_summary,
        "timestamp": timestamp,
    }


def get_eligible_governor_candidates(state: GameState, governor_type: str) -> List[Figure]:
    """获取符合行省总督资格的人物列表（按卸任时间倒序排序）。"""
    return _political_system(state).get_eligible_governor_candidates(governor_type)


def is_governor_position_occupied(state: GameState, figure_id: int) -> bool:
    """检查人物是否已被任命为其他行省的总督（候任或现任）。"""
    return _political_system(state).is_governor_position_occupied(figure_id)


def assign_fleets_to_active_wars(state: GameState) -> dict:
    """
    为需要海战且尚无舰队的活跃战争指派可用舰队（补漏函数）。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    ws = state.get_war_system()
    if not ws:
        return api_response(False, "战争系统不可用")

    naval = state.naval_system
    if not naval:
        return api_response(False, "海军系统不可用")

    target_wars = [
        war for war in ws.get_active_wars()
        if war.naval_required and not war.assigned_fleet_ids
        # WP-G-R4 (SA v1.7 §2.3, P1-01/Oracle-A)：LOCKED pending Takeover 目标战免自动配舰
        # ——幸存 force rebind/指派仅属于 advance 部署单元（迁移表 #7/#8），resolve 不提前绑舰
        and not (state._takeover_pending is not None
                 and state._takeover_pending.get("status") == "LOCKED"
                 and state._takeover_pending.get("war_id") == war.id)
    ]
    if not target_wars:
        return api_response(True, "无需指派舰队")

    target_wars.sort(key=lambda war: getattr(war, "enemy_naval_current", 0), reverse=True)

    available_fleets = naval.get_available_fleets()
    if not available_fleets:
        return api_response(True, "无可指派舰队")

    available_fleets.sort(key=lambda fleet: getattr(fleet, "power", 0), reverse=True)

    assigned_details = []
    assigned_any = False

    for war in target_wars:
        if war.assigned_fleet_ids:
            continue

        needed_power = getattr(war, "enemy_naval_current", 0)
        if needed_power <= 0:
            needed_power = 1

        assigned_fleets = []
        total_power = 0
        fleets_to_remove = []

        for fleet in available_fleets:
            if total_power >= needed_power:
                break
            assigned_fleets.append(fleet.number)
            total_power += getattr(fleet, "power", 0)
            fleets_to_remove.append(fleet)

        if not assigned_fleets:
            continue

        for fleet_num in assigned_fleets:
            if naval.assign_fleet_to_war(fleet_num, war.id, "naval"):
                war.assign_fleet(fleet_num)

        for fleet in fleets_to_remove:
            available_fleets.remove(fleet)

        assigned_details.append({
            "war_id": war.id,
            "war_name": war.name,
            "fleets": assigned_fleets,
            "total_power": total_power,
            "needed_power": needed_power,
        })
        assigned_any = True

        if not available_fleets:
            break

    if not assigned_any:
        return api_response(True, "无符合条件的战争需要舰队，或可用舰队不足")

    message = "\n".join(
        f"⚓ 自动指派 {len(detail['fleets'])} 支舰队至 {detail['war_name']} "
        f"（当前海军战力 {detail['total_power']}，需 {detail['needed_power']}）"
        for detail in assigned_details
    )

    state.log_event(
        f"舰队指派补漏：{len(assigned_details)} 个战争获得舰队",
        level=logging.INFO,
        extra={"assigned_wars": [detail["war_id"] for detail in assigned_details]},
    )

    return api_response(True, message, data={"assigned": assigned_details})


def assign_governors(state: GameState) -> list[dict]:
    """总督候选人筛选与分配。

    分析所有行省 → 筛选候选人 → 分配总督职位。
    返回分配结果列表：[{province_id, governor_id, name, assigned_at}, ...]

    业务逻辑继承自 phase_senate.py CLI _process_governor_appointments + _execute_governor_appointments:
    - 遍历无总督行省
    - 按候选人资格/忠诚度条件筛选
    - 分配最佳候选人
    - 更新 Province 实体 governor_designate_id 字段
    """
    if not state:
        return []

    import datetime

    # 获取所有已征服的行省（排除意大利行省 ID 0）
    all_provinces = [p for p in state.get_all_provinces() if p.conquered and p.province_id != 0]

    # 行省分类
    proconsul_provinces = [p for p in all_provinces if p.governor_type == "proconsul"]
    propraetor_provinces = [p for p in all_provinces if p.governor_type == "propraetor"]

    # 候选人获取函数
    def _get_candidates(office_type: str):
        cand_list = []
        for fig in state.get_living_members():
            if fig.is_absent:
                continue
            if fig.office is not None and not fig.office.startswith("ex-"):
                continue
            last_end = None
            for term in fig.office_history:
                if term.office_type == office_type and term.end_turn is not None:
                    if last_end is None or term.end_turn > last_end:
                        last_end = term.end_turn
            if last_end is not None:
                cand_list.append((fig, last_end))
        cand_list.sort(key=lambda x: -x[1])
        return [c[0] for c in cand_list]

    # 分配逻辑
    def _assign(provinces, candidates, used_set):
        remaining = list(provinces)
        random.shuffle(remaining)
        assignments = []
        for cand in candidates:
            if cand.id in used_set:
                continue
            if not remaining:
                break
            chosen = random.choice(remaining)
            remaining.remove(chosen)
            assignments.append((chosen, cand))
            used_set.add(cand.id)
        return assignments

    used = set()
    consuls = _get_candidates('consul')
    praetors = _get_candidates('praetor')
    proconsul_assignments = _assign(proconsul_provinces, consuls, used)
    propraetor_assignments = _assign(propraetor_provinces, praetors, used)

    assigned_at = state.turn.turn_number if hasattr(state, 'turn') and state.turn else 0
    results = []

    for province, candidate in proconsul_assignments + propraetor_assignments:
        province_id = province.province_id
        candidate_id = candidate.id
        name = candidate.get_formal_name() if hasattr(candidate, 'get_formal_name') else str(candidate.name)
        current = getattr(province, 'governor_id', None)

        state.log_event(
            f"assign_governors: checking province {province_id}, current_governor={current}",
            level=logging.DEBUG,
            extra={"province_id": province_id, "current_governor": current, "method": "assign_governors"},
        )
        state.log_event(
            f"assign_governors: selected candidate {candidate_id} for province {province_id}",
            level=logging.DEBUG,
            extra={"province_id": province_id, "candidate_id": candidate_id, "method": "assign_governors"},
        )

        old_gov_id = getattr(province, 'governor_id', None)
        province.set_governor_designate(candidate_id, old_gov_id)
        # ODR-WP-D-01 防线 2：在职保民官不得置位 absent（fail-closed；候选 office=None/ex-* 天然排除，纯防御）
        if _tribune_absent_guard(candidate):
            candidate.is_absent = True

        state.log_event(
            f"Governor assigned: province={province_id}, governor={candidate_id}, name={name}",
            level=logging.INFO,
            extra={"province_id": province_id, "governor_id": candidate_id, "name": name, "method": "assign_governors"},
        )

        results.append({
            "province_id": province_id,
            "governor_id": candidate_id,
            "name": name,
            "assigned_at": assigned_at,
        })

    return results


def auto_vote(
    state: GameState,
    player_id: str,
    proposals: list,
    vote_decider: Optional[SenateVoteDecider] = None,
) -> dict:
    """
    Auto-vote for a specific player on pending proposals.

    Args:
        state: GameState
        player_id: Target player
        proposals: List of proposal dicts to vote on
        vote_decider: Optional decider; defaults to AutoSenateVoteDecider

    Returns:
        dict: {
            "voted": int,           # proposals voted on
            "skipped": int,         # proposals already voted
            "errors": list[str],
        }
    """
    if vote_decider is None:
        from src.core.deciders.impl.auto_senate_vote_decider import AutoSenateVoteDecider
        vote_decider = AutoSenateVoteDecider()

    player = state.get_player(player_id)
    if not player:
        return {"voted": 0, "skipped": 0, "errors": ["player not found"]}

    faction = state.get_faction(player.faction_id)
    if not faction:
        return {"voted": 0, "skipped": 0, "errors": ["faction not found"]}

    voted_count = 0
    skipped_count = 0
    errors = []

    for proposal in proposals:
        pid = proposal["id"]
        # Check if already voted
        if state.has_senate_vote(player_id, pid):
            skipped_count += 1
            continue

        # Build issue and decide vote
        try:
            from src.core.systems.political_system import PoliticalSystem
            politics = PoliticalSystem(state)
            issue = politics.build_issue_from_proposal(proposal)
            support = vote_decider.decide_vote(issue, faction, state)
            state.record_senate_vote(player_id, pid, support)
            voted_count += 1
        except Exception as exc:
            errors.append(f"proposal {pid}: {exc}")

    return {
        "voted": voted_count,
        "skipped": skipped_count,
        "errors": errors,
    }

