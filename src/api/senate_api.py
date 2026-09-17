# src/api/senate_api.py
"""
元老院阶段 API
提供统一的操作接口，供 CLI 和决策器调用。
"""

import copy
import logging
import random
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
    if ptype == "war_proposal":
        # R5（SA §2.1/§5.3，DA-5）：War Proposal 标签——中性政治描述（不冒充物理执行结果）。
        payload = proposal.get("payload") or {}
        label = proposal.get("war_label") or proposal.get("war_id")
        if proposal.get("mode") == "peace":
            return f"停战决议 — {label}"
        cmd_label = payload.get("target_commander_label") or ""
        n = payload.get("reinforcement_n", 0)
        if cmd_label:
            return f"战争决议 — {label}（指挥官 {cmd_label}；征召 {n} 个军团）"
        return f"战争决议 — {label}（征召 {n} 个军团）"
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
    if ptype == "war_proposal":
        payload = proposal.get("payload") or {}
        if proposal.get("mode") == "peace":
            return {"war_id": proposal.get("war_id"), "war_label": proposal.get("war_label"),
                    "mode": "peace", "treaty_ref": payload.get("treaty_snapshot", {}).get("treaty_ref")}
        return {"war_id": proposal.get("war_id"), "war_label": proposal.get("war_label"),
                "mode": proposal.get("mode", "command"),
                "target_commander_id": payload.get("target_commander_id"),
                "target_commander_label": payload.get("target_commander_label"),
                "reinforcement_n": payload.get("reinforcement_n")}
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
    # R5（SA §5.2 C-M08，DA-4）：单 reservation 偏移（_takeover_reserved_offset）退役。
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
    # R5（SA §5.2 C-M08，DA-4）：单 reservation 扣池退役（N≥0 统一；无单槽配额）。
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


# R5（SA §5.2 C-M08/C-M09，DA-4）：legacy mandatory Takeover 门与 takeover_required 生产者
# （`_war_has_valid_commander` / `_commander_unavailable_*` / `_resolve_takeover_required` /
# `_takeover_reserved_offset`）整体退役——不再存在 commanderless 驱动的 Senate 门禁
# （SA §2.7 A-I14：commanderless/legionless 为合法军事状态，不阻止政治结算）。



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


# R5（SA §5.1/§5.2，DA-4）：旧 Takeover/Continue 选区 producer 退役——统一 War Card 只读
# 投影（`war_cards`）取代。


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
        # R5（SA §5.1，DA-4）：旧 Takeover/Continue 读模型与 mandatory 门整体退役；
        # can_advance 以真实 phase_result 为权威（禁拿 current_step=="results" 冒充阶段完成）。
        has_real_senate_result = bool(senate_result)
        senate_settlement_pending = (current_step == "results") and not has_real_senate_result
        # R5（SA §2.7 A-I14，DA-4）：显式空结束不再受 mandatory Takeover 门阻塞。
        can_finish_empty = (actionable and current_step == "proposal" and viewer_has_consul)
        proposal_selection_disabled_reason = ""
        if current_step != "proposal":
            proposal_selection_disabled_reason = "当前不在提案选择环节"
        elif not viewer_has_consul:
            proposal_selection_disabled_reason = "您的派系没有在城执政官可提交"

        # R5（SA §5.1，DA-1）：统一 War Card 只读投影（QML 零推导）
        war_cards = politics.build_war_card_views({
            "current_turn": state.turn.turn_number if state.turn else None,
        })

        # R5（SA §5.1/§5.3，DA-5）：WarExecutionReceipt 只读摘要（唯一边界事务产出；展示层不得
        # 据此重新执行）；同版附在 senate_result 下（SA §5.1 落点）。
        war_receipt = None
        _session_id = state.get_senate_session()
        if _session_id:
            war_receipt = state.get_war_execution_receipt_for_session(_session_id)
        war_execution = {
            "execution_id": war_receipt.get("execution_id"),
            "status": war_receipt.get("status"),
            "committed": war_receipt.get("status") == "COMMITTED",
            "pending_fallback_war_ids": list(war_receipt.get("pending_fallback_war_ids") or []),
        } if war_receipt else {}
        senate_result_view = dict(senate_result) if isinstance(senate_result, dict) else {}
        if war_execution:
            senate_result_view["war_execution"] = war_execution

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
            "can_advance": (current_step == "results") and has_real_senate_result,
            # R5（SA §5.1，DA-4）：旧 pending Takeover / can_deploy 读模型键退役
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
            # R5（SA §5.1，DA-4）：takeover_options/can_takeover/takeover_required/
            # continue_options/can_continue 键退役——统一 war_cards 投影取代。
            "war_threats": war_threats,
            "pending_peace_treaties": pending_peace_treaties,
            "governor_vacancies": governor_vacancies,
            "governor_appointments": governor_appointments,
            "pending_contracts": pending_contracts,
            "proposal_options": proposal_options,
            "submitted_proposals": proposals,
            "war_cards": war_cards,
            "senate_result": senate_result_view,
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


# R5（SA §5.2 C-M07/C-M08，DA-4）：旧 Takeover 入口（`takeover_war` reserve/submit/cancel、
# 单 reservation/lock 协议）整体退役——Human/AI/CLI 意图统一经 `propose_many` →
# `submit_proposal_package`（Package Submit），执行统一 `advance_senate_phase`（唯一 owner）。
# 旧协议退役 = 显式不支持，不得保留旁路直接部署。



# R5（SA §5.2 C-M07/C-M08，DA-4）：单 Takeover 部署域（`_turn_label` / `_takeover_pending_dto` /
# `_takeover_pool_available` / `_snapshot_takeover_deploy` / `_rollback_takeover_deploy` /
# `_deploy_pending_takeover`）整体退役——整包 shadow/receipt 事务（B2 `advance_senate_phase`）取代；
# 单 Consul / 单 War rollback / reservation exactly-once 不再存在于 R5 入口面。



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
    """R5（SA §3.1/§3.7，DA-2）：唯一整包提交门面（validate → stage → 原子发布）。

    输入兼容两种形态：
      - 列表 specs：R5 War Card 行（含 `checked` 键或 `type=="war_proposal"`）→ war_drafts；
        其余 `{"type": ..., "params": {...}}` → 普通/legacy 提案。空列表 = 合法政治决策。
      - dict envelope：直接透传 {senate_session_id, submit_request_id, war_drafts, proposals}。
    all-or-nothing：任一校验失败整包零发布、保留 draft；不得部分成功。
    """
    if not state:
        return api_response(False, "无效的游戏状态")

    if isinstance(proposals, dict):
        request = dict(proposals)
    else:
        request = _package_request_from_specs(proposals or [])

    # R5（SA §4.8/§5.4，DA-5）：冻结会期身份（execution_id 依赖会期唯一性；存档需持久化）
    turn = state.turn.turn_number if state.turn else 0
    if not request.get("senate_session_id"):
        request["senate_session_id"] = f"turn-{turn}"

    if not request.get("war_drafts") and not request.get("proposals"):
        # D-09 / SA §3.1：空批 = 合法政治决策「本会期不提交法案」（边界仍处理 pending fallback）
        state.set_senate_session(request["senate_session_id"])
        state.senate_proposal_decision_complete = True
        return api_response(True, "本会期未提交法案", data={"created": []})

    result = _political_system(state).submit_proposal_package(
        player_id, request, _build_submit_context(state))
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


def _package_request_from_specs(specs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把 API 层 specs 归一为 R5 整包 envelope（war_drafts + 非 War proposals）。"""
    war_drafts = []
    non_war = []
    for spec in specs or []:
        if not isinstance(spec, dict):
            non_war.append(spec)
            continue
        stype = spec.get("type")
        if stype == "war_proposal" or "checked" in spec:
            src = spec.get("params") if isinstance(spec.get("params"), dict) else spec
            war_drafts.append({
                "war_id": src.get("war_id", spec.get("war_id")),
                "checked": bool(src.get("checked", spec.get("checked", False))),
                "mode": src.get("mode", spec.get("mode", "command")),
                "target_commander_id": src.get("target_commander_id", spec.get("target_commander_id")),
                "reinforcement_n": src.get("reinforcement_n", spec.get("reinforcement_n")),
            })
        else:
            non_war.append(spec)
    return {"war_drafts": war_drafts, "proposals": non_war}


def _build_submit_context(state: GameState) -> Dict[str, Any]:
    """构建 Submit 共享上下文（同次权威读取的最小身份）。"""
    ctx: Dict[str, Any] = {}
    if state.turn:
        ctx["current_turn"] = state.turn.turn_number
    return ctx


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

    # R5（SA §5.2，DA-4）：AI 入口重构为「构造一次整包 request → propose_many」——不再循环
    # `propose` 逐条落库（D-SC03），不得经旧 Takeover 协议旁路直接部署（C-M08）。
    politics = _political_system(state)
    war_drafts: List[Dict[str, Any]] = []
    non_war_proposals: List[Dict[str, Any]] = []
    used_commanders = set()
    # 已真实战的现任指挥官保留 claim（unchecked/Peace 保留）→ 本包不得重复指派（A-I04 唯一性）
    for _war in politics._real_wars():
        if _war.commander_id is not None:
            used_commanders.add(_war.commander_id)
    commander_candidates = politics.build_war_commander_candidates({})

    def _pick_ai_commander():
        for row in commander_candidates:
            if row["figure_id"] in used_commanders:
                continue
            if row.get("current_command_war_ids"):
                continue
            used_commanders.add(row["figure_id"])
            return row["figure_id"]
        return None

    # ========== 4a. 宣战提案（战争威胁 → checked command draft） ==========
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
                    target = _pick_ai_commander()
                    if target is None:
                        continue  # 无合法 Commander（唯一性）→ 跳过，避免整包 Claim 冲突
                    lo = legion_options["min"]
                    hi = min(remaining, legion_options["max"])
                    if hi < lo:
                        continue
                    legions = random.randint(lo, hi)
                    war_drafts.append({
                        "war_id": war.id, "checked": True, "mode": "command",
                        "target_commander_id": target, "reinforcement_n": legions,
                    })
                    remaining -= legions  # 总和守恒：已提交宣战占用的军团从池中扣除
                    created_proposals.append({
                        "type": "war",
                        "war_id": war.id,
                        "legions": legions,
                        "description": f"对 {war.name} 宣战，申请征召 {legions} 个军团",
                    })

    # ========== 4b. 停战草案（待决停战 → checked peace draft） ==========
    # R5（SA §2.1/§5.1，DA-4）：Peace 意图经同一 War Card tagged union（mode=peace）提交，
    # 不再走 legacy `type="peace"` 单项入口；AI 不得预借/预释放 Commander（A-I04）。
    if ws:
        pending_peace = ws.get_truce_wars_with_pending_treaty()
        for war in pending_peace:
            war_drafts.append({
                "war_id": war.id, "checked": True, "mode": "peace",
                "target_commander_id": None, "reinforcement_n": None,
            })
            created_proposals.append({
                "type": "peace",
                "war_id": war.id,
                "description": f"对 {war.name} 的停战协议进行表决",
            })

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
        if candidate.id in used_commanders:
            continue  # G_package × Commander claim 冲突防御（A-I05）
        non_war_proposals.append({
            "type": "governor",
            "params": {"province_id": province.province_id, "candidate_id": candidate.id},
        })
        created_proposals.append({
            "type": "governor",
            "province_id": province.province_id,
            "candidate_id": candidate.id,
            "description": f"任命 {candidate.get_formal_name()} 为 {province.name} 行省总督",
        })

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
            non_war_proposals.append({"type": "budget", "params": dict(kwargs)})
            budget_display = kwargs.get("modified_budget", contract.base_cost)
            created_proposals.append({
                "type": "budget",
                "contract_id": contract.id,
                "modified_budget": budget_display,
                "description": f"{contract.name} 预算 {budget_display} 塔兰特",
            })

    # ========== 4e. 土地法案 ==========
    for faction in state.factions.values():
        for decider in land_proposal_deciders:
            decider_result = decider.decide_proposal(faction.id, state)
            if decider_result:
                act_type, percent = decider_result
                # AU-7（P2-04 clamp）：percent → amount_C 权威换算，小公地量下防 0（≥1）
                amount_C = max(1, int(state.get_national_public_land() * percent))
                proposal_id_ref = None
                act_name = "公地出售法案" if act_type == "sale" else "公地分配法案"
                non_war_proposals.append({
                    "type": "land",
                    "params": {"act_type": act_type, "amount_C": amount_C},
                })
                created_proposals.append({
                    "type": "land",
                    "act_type": act_type,
                    "amount_C": amount_C,
                    "percent": amount_C / state.get_national_public_land() if state.get_national_public_land() else 0.0,
                    "description": f"{act_name} {amount_C} C 国家公地",
                })

    # ========== 4f. 单一整包提交（R5 SA §3.1/§3.7/§5.2：AI 与 Human 同源） ==========
    # R5（SA §5.2 C-M08，DA-4）：旧 AI 自动接管（execute_ai_takeover_direct_action Direct
    # Action / 4f 块）已退役——AI 意图统一经 propose_many → submit_proposal_package，
    # 执行统一 advance_senate_phase（不得经旧协议旁路直接部署）。
    submit = propose_many(state, consul_player_id, {
        "war_drafts": war_drafts, "proposals": non_war_proposals})
    if not submit.get("success"):
        errors.extend([e.get("message", "") for e in (submit.get("errors") or [])])
    created = (submit.get("data") or {}).get("created", [])

    # ========== 返回结果 ==========
    message = f"已自动提交 {len(created)} 项提案"
    return api_response(
        success=submit.get("success", False),
        message=message,
        data={"proposals": created_proposals, "created": created},
        errors=errors,
    )


def _war_proposal_refs(decisions: List[dict]) -> List[dict]:
    refs = []
    for d in decisions:
        refs.append({"proposal_id": d.get("proposal_id"), "war_id": d.get("war_id"),
                     "outcome": d.get("outcome"), "snapshot_ref": copy.deepcopy(d.get("snapshot_ref") or {})})
    return sorted(refs, key=lambda r: (r["proposal_id"] is None, r["proposal_id"]))


def _execute_war_resolution_boundary(state: GameState, player_id: str) -> dict:
    """SA §4.1/§4.6/§4.8：Senate→Combat 唯一整包边界事务（receipt exactly-once 优先）。

    读 immutable final decisions + SubmissionContext + live PT；构建规范 Plan；在单一受锁
    shadow 事务内 commit；同版写入 COMMITTED receipt + phase 标记（公共线性化点）。任一失败
    → 回滚 S0（零部分变更），不进入 Combat。
    """
    from src.core.game_state import WarResolutionTransaction
    politics = _political_system(state)
    ws = state.get_war_system()
    ms = state.get_military_system()
    turn = state.turn.turn_number if state.turn else 0
    session_id = state.get_senate_session() or f"turn-{turn}"

    decisions = [copy.deepcopy(d) for (s, _pid), d in state.get_war_decisions().items()
                 if s == session_id]
    real_wars = politics._real_wars()
    pending_ids = [w.id for w in ws.get_truce_wars_with_pending_treaty()] if ws else []
    u0 = sorted(legion.number for legion in ms.get_available_legions()) if ms else []
    plan = politics.build_war_resolution_plan({
        "current_turn": turn, "session_id": session_id, "decisions": decisions,
        "real_wars": real_wars, "available_legion_ids": u0, "pending_war_ids": pending_ids,
    })
    execution_id = plan["execution_id"]
    fingerprint = plan["input_fingerprint"]

    # C-T01：执行身份 receipt 重放优先（不读当前 War 重验/不重跑部署）
    existing = state.get_war_execution_receipt(execution_id)
    if existing and existing.get("status") == "COMMITTED":
        if existing.get("input_fingerprint") == fingerprint:
            return {"success": True, "message": "Senate→Combat 已执行（receipt 重放）",
                    "data": {"execution_id": execution_id, "committed": True, "replayed": True,
                             "receipt": existing, "next_phase_id": "combat"}}
        return {"success": False, "message": "执行身份冲突（同键不同输入）",
                "data": {"code": "WAR_EXECUTION_IDENTITY_CONFLICT", "execution_id": execution_id,
                         "committed": False, "next_phase_id": None, "retryable": False,
                         "failed_stage": "identity", "receipt_status": existing.get("status")}}

    if plan.get("duplicate_targets"):
        return {"success": False, "message": "输入完整性失败：Commander target 重复",
                "data": {"code": "WAR_EXECUTION_INPUT_INVALID", "execution_id": execution_id,
                         "committed": False, "next_phase_id": None, "retryable": False,
                         "failed_stage": "plan", "offending_refs": plan["duplicate_targets"]}}
    if plan.get("legion_shortfall", 0) > 0:
        return {"success": False, "message": "输入完整性失败：征召池不足",
                "data": {"code": "WAR_EXECUTION_CONTEXT_CHANGED", "execution_id": execution_id,
                         "committed": False, "next_phase_id": None, "retryable": False,
                         "failed_stage": "plan", "changed_domains": ["legion_pool"]}}

    try:
        with WarResolutionTransaction(state) as txn:
            effects = politics.commit_war_resolution(plan, txn)
            receipt = {
                "senate_session_id": session_id,
                "package_id": next((d.get("snapshot_ref", {}).get("package_id") for d in decisions
                                    if d.get("snapshot_ref", {}).get("package_id")), None),
                "execution_id": execution_id,
                "status": "COMMITTED",
                "proposal_refs": _war_proposal_refs(decisions),
                "input_fingerprint": fingerprint,
                "pending_fallback_war_ids": list(plan["pending_fallback_set"]),
                "effect_summary": {k: (list(v) if isinstance(v, list) else v) for k, v in effects.items()},
                "commit_revision": (turn, session_id),
            }
            state.record_war_execution_receipt(receipt)
            state.mark_phase_executed("senate")
            txn.commit()
    except Exception as exc:
        state.log_event("Senate→Combat 边界事务失败: 完整回滚（零部分变更）", level=logging.WARNING,
                        extra={"execution_id": execution_id, "error": str(exc)})
        return {"success": False, "message": f"Senate→Combat 执行失败（已回滚，可重试）: {exc}",
                "data": {"code": "WAR_EXECUTION_APPLY_FAILED", "execution_id": execution_id,
                         "committed": False, "next_phase_id": None, "retryable": True,
                         "failed_stage": "apply", "receipt_status": None}}

    # POST-COMMIT AUDIT（不回滚业务；失败独立上报不重跑）
    try:
        state.record_senate_direct_action({
            "action_type": "war_resolution_commit",
            "kind": "war_resolution",
            "exactly_once_key": execution_id,
            "executed_units": list(effects.get("peace", [])) + list(effects.get("activated", []))
            + list(effects.get("fallback", [])) + list(effects.get("bound", [])),
            "pending_fallback_war_ids": list(plan["pending_fallback_set"]),
            "trigger_source": "human_explicit",
        })
        state.log_event("Senate→Combat 整包原子执行完成", level=logging.INFO,
                        extra={"type": "senate_war_resolution_committed", "execution_id": execution_id})
    except Exception as exc:
        state.log_event("War resolution audit 上报失败（业务已 committed；不重跑）", level=logging.WARNING,
                        extra={"execution_id": execution_id, "reason": "audit_failed", "error": str(exc)})

    return {"success": True, "message": "Advanced to combat phase（Senate→Combat 整包原子执行完成）",
            "data": {"execution_id": execution_id, "committed": True, "replayed": False,
                     "receipt": state.get_war_execution_receipt(execution_id),
                     "next_phase_id": "combat", "effects": effects}}


def advance_senate_phase(state: GameState, player_id: str) -> dict:
    """Mark senate complete and advance the GUI shell to combat.

    R5（SA §2.6/§4.6）：本函数 = Senate→Combat 唯一外部 mutation 入口。读取冻结政治结果，
    构建一个整包 War resolution 事务（含全部 ENACTED War Proposals + 全部 pending-peace
    fallback），原子执行并同版写 receipt/phase；任一失败零部分变更、不进入 Combat。

    R4 legacy pending-Takeover 部署单元已退役（R5 SA §5.2 C-M09，DA-4）——本函数不再有
    第二执行分支（唯一整包事务）。
    """
    if not state:
        return api_response(False, "Invalid game state")
    if not state.is_current_player(player_id):
        return api_response(False, "Current player mismatch")
    # C-T01（SA §4.8）：同执行身份 receipt 重放优先于「Senate already executed」首次执行门。
    turn = state.turn.turn_number if state.turn else 0
    session_id = state.get_senate_session() or f"turn-{turn}"
    prior = state.get_war_execution_receipt_for_session(session_id)
    if prior and prior.get("status") == "COMMITTED":
        return api_response(True, "Senate→Combat 已执行（receipt 重放）",
                            data={"execution_id": prior.get("execution_id"), "committed": True,
                                  "replayed": True, "receipt": prior, "next_phase_id": "combat"})
    if state.is_phase_executed("senate"):
        return api_response(False, "Senate phase already executed")
    if not state.get_phase_result("senate"):
        return api_response(False, "Senate result is not ready")
    result = _execute_war_resolution_boundary(state, player_id)
    if not result.get("success"):
        return api_response(False, result.get("message", ""), data=result.get("data", {}))
    return api_response(True, result.get("message", ""), data=result.get("data", {}))

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
    # R5（SA §2.7 A-I14 / §4.10 C-M09）：mandatory Takeover 门已拆除——commanderless/
    # legionless 真实 War 是合法状态，不得阻止 Senate settle/advance（军事后果由边界事务承担）；
    # takeover_required 只读态与 _resolve_takeover_required 生产者已在 DA-4 退役。
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
                "title": _proposal_label(state, p) + ("（获批 · 待边界执行）" if p.get("type") == "war_proposal" else ""),
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


# R5（SA §5.2 C-M07/C-M08，DA-4）：`process_war_takeover`（旧自动接管逻辑，直接
# 征召/指派 Legion）退役——R5 无自动接管 mutation 入口；AI 意图经 Package Submit，
# 执行经唯一 advance_senate_phase 事务。

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

