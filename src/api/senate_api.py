# src/api/senate_api.py
"""
元老院阶段 API
提供统一的操作接口，供 CLI 和决策器调用。
"""

import copy
import hashlib
import json
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
from src.core.deciders.impl.auto_war_takeover_decider import AutoWarTakeoverDecider
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.figure import Figure
from src.core.entities.war import WarStatus
from src.core.game_state import GameState, SenateFinalizationTransaction
from src.core.systems.political_system import (
    AUTHORITY_CONSUL_DIRECT,
    AUTHORITY_SENATE_VOTE,
    PoliticalSystem,
    _tribune_absent_guard,
    classify_war_authority,
)


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


# R6（SA §D.4，DA-4 B3）：Results / PA 三身份文案锚点（QML 只渲染，禁自行推断）。
# 真 Senate 获批行 =「元老院批准 · 待边界执行」；Consul 冻结 direct 行 =
# 「执政官决定 · 待推进到战斗阶段执行」；COMMITTED 后由边界 receipt 证明实际已执行。
SENATE_ENACTED_ROW_LABEL = "元老院批准 · 待边界执行"
CONSUL_DIRECT_ROW_LABEL = "执政官决定 · 待推进到战斗阶段执行"
CONSUL_DIRECT_EXECUTED_LABEL = "执政官决定 · 已执行（边界 receipt）"


def _consul_direct_decision_rows(state: GameState,
                                 senate_session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """D.4：会期 FROZEN `ConsulWarDecision` 只读投影（**整个会期可读**）。

    - 身份 = `item_ref`（冻结 `snapshot_ref`）：刷新 / 离开重入 / SaveLoad 后按同一
      `item_ref` 重取同一冻结内容。**行内不出现 `proposal_id` 键**（不混用 display row
      ID 与 proposal_id；direct ID 为带类型前缀 opaque string）。
    - `execution` 只有边界 receipt（`WarExecutionReceipt.status == COMMITTED`）能翻成
      `executed`；边界前恒 `awaiting_boundary`（不宣称早部署）。
    - 排序稳定（`war_id`, `direct_decision_id`）——与账本迭代/存档外形无关。
    """
    session_id = senate_session_id or state.get_senate_session()
    if not session_id:
        return []
    receipt = state.get_war_execution_receipt_for_session(session_id) or {}
    executed = receipt.get("status") == "COMMITTED"
    rows: List[Dict[str, Any]] = []
    for direct_id, record in (state.get_consul_war_decisions(session_id) or {}).items():
        payload = record.get("payload") or {}
        item_ref = record.get("snapshot_ref") or {
            "kind": "consul_direct",
            "senate_session_id": record.get("senate_session_id"),
            "package_id": record.get("package_id"),
            "direct_decision_id": direct_id,
            "schema_version": record.get("schema_version", 1),
        }
        rows.append({
            "identity": "consul_direct_decision",
            "item_ref": copy.deepcopy(item_ref),
            "direct_decision_id": direct_id,
            "type": record.get("type", "consul_war_decision"),
            "authority": record.get("authority", "consul_direct"),
            "authority_label": "执政官决定",
            "decision_state": record.get("decision_state", "FROZEN"),
            "mode": record.get("mode", "command"),
            "source": record.get("source"),
            "war_id": record.get("war_id"),
            "war_label": record.get("war_label"),
            "senate_session_id": record.get("senate_session_id"),
            "package_id": record.get("package_id"),
            "submission_context_id": record.get("submission_context_id"),
            "target_commander_id": payload.get("target_commander_id"),
            "target_commander_label": payload.get("target_commander_label"),
            "reinforcement_n": payload.get("reinforcement_n", 0),
            "execution": "executed" if executed else "awaiting_boundary",
            "execution_label": ("已执行（边界 receipt）" if executed
                                else "待推进到战斗阶段执行"),
            "display_label": (CONSUL_DIRECT_EXECUTED_LABEL if executed
                              else CONSUL_DIRECT_ROW_LABEL),
        })
    rows.sort(key=lambda row: (str(row.get("war_id")), str(row.get("direct_decision_id"))))
    return rows


def _current_canonical_direct_scope(state: GameState) -> Optional[str]:
    """R9（FC-R9-02/03）：当前顶层 direct 投影的 **canonical 会期**（由有效 PackageRecord 证明）。

    仅当下列 AND 全满足时返回该会期 id，否则返回 None（顶层投影据此返回 []）：
      ① 存在当前会期指针 `state.get_senate_session()`（缺 s → 排除）；
      ② `state.turn` 存在且 `turn_number` 为整数（缺 / 非整数 → 排除）；
      ③ 该会期存在身份匹配的有效 PackageRecord：`get_senate_package_id_for_session(s)`
         → `get_senate_package_record(package_id)`，且 `record.senate_session_id == s`
         （**无 PackageRecord 一律排除**，含 direct 自身带有效 turn / s 恰为 `turn-{current}`）；
      ④ 该 PackageRecord 的 `submitted_at.turn` 完整、类型为整数（bool 非法）、
         且 `== state.turn.turn_number`（缺失/非法/不匹配 → 排除，**不 fallback 到无包规则**）。

    判定只用 opaque 会期 id 与 package 元数据，**不解析 session ID 文本**。
    """
    session_id = state.get_senate_session()
    if not session_id:
        return None
    turn = state.turn.turn_number if state.turn else None
    if not isinstance(turn, int) or isinstance(turn, bool):
        return None
    package_id = state.get_senate_package_id_for_session(session_id)
    if not package_id:
        return None
    record = state.get_senate_package_record(package_id)
    if not isinstance(record, dict):
        return None
    if record.get("senate_session_id") != session_id:
        return None
    submitted_at = record.get("submitted_at")
    if not isinstance(submitted_at, dict):
        return None
    package_turn = submitted_at.get("turn")
    if not isinstance(package_turn, int) or isinstance(package_turn, bool):
        return None
    if package_turn != turn:
        return None
    return session_id


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
        # WP-J J-AC-10 / FC-01..FC-06: authoritative intra-phase step read model.
        # Senate has exactly three sub-steps [proposal, senate_vote, tribune_veto]; 「公示」
        # is NOT a sub-step (FC-06). tribune_veto is `not_applicable` only when the
        # authoritative flow skipped the veto (zero passed candidates → direct `results`).
        _senate_veto_reached = (
            bool(veto_candidate_ids)
            or bool(result_data.get("passed_proposals_snapshot"))
            or bool(result_data.get("vetoed_proposals_snapshot"))
        )
        if current_step == "tribune_veto":
            _tribune_veto_state = "current"
        elif current_step == "results":
            _tribune_veto_state = "complete" if _senate_veto_reached else "not_applicable"
        else:
            _tribune_veto_state = "todo"
        steps = [
            {
                "key": "proposal",
                "label": "执政官提案",
                "state": "current" if current_step == "proposal"
                else ("complete" if current_step in {"senate_vote", "tribune_veto", "results"} else "todo"),
            },
            {
                "key": "senate_vote",
                "label": "元老表决",
                "state": "current" if current_step == "senate_vote"
                else ("complete" if current_step in {"tribune_veto", "results"} else "todo"),
            },
            {
                "key": "tribune_veto",
                "label": "保民官否决",
                "state": _tribune_veto_state,
            },
        ]
        actionable = current_phase_id == "senate" and state.is_current_player(viewer_player_id)
        # AU-R2-2b（C4/C5）：能力位全由单一 authority resolver 产出（provenance 全收敛）——
        # _viewer_eligible_consul / _viewer_has_tribune 独立重算已退役（FACT-1）。
        proposal_control = politics.resolve_proposal_control(viewer_player_id)
        veto_control = politics.resolve_veto_control(viewer_player_id)
        # WP-M D5.2：无主持人（FC-01=0）标志（单一权威 host）
        senate_no_host = state.get_presiding_officer() is None
        viewer_has_consul = proposal_control["mode"] == "HUMAN"
        viewer_has_tribune = veto_control["mode"] == "HUMAN"
        can_create = actionable and current_step == "proposal" and viewer_has_consul
        # D-3 收严：can_trigger_ai 严格 mode=="AI"（NONE 不再暴露 AI 入口，fail-closed D-R2-05）
        can_trigger_ai = actionable and current_step == "proposal" and proposal_control["mode"] == "AI"
        # R5（SA §5.1，DA-4）：旧 Takeover/Continue 读模型与 mandatory 门整体退役；
        # can_advance 以真实 phase_result 为权威（禁拿 current_step=="results" 冒充阶段完成）。
        has_real_senate_result = bool(senate_result)
        # R6（SA §D.1.1/D.1，DA-4 B1）：settlement 字段**正常态退役**——auto-finalization 已由
        # 服务端命令流程（`finalize_senate_if_ready`）完成，正常态不再产出「待结算」恢复动作位。
        # legacy 键保留（兼容读取器）但**恒 False 且不得驱动正常 UI**；真实异常恢复走
        # `finalization_error` 内部能力位（非正常态「完成结算」按钮）。
        senate_settlement_pending = False
        # 异常恢复能力位：只有真实 finalization 失败（无成功 phase_result + 错误标记）才为 True
        _existing_senate_result = state.get_phase_result("senate")
        senate_finalization_error = bool(
            current_phase_id == "senate"
            and not (isinstance(_existing_senate_result, dict)
                     and _existing_senate_result.get("success"))
            and bool(getattr(state, "_last_senate_finalization_error", None)))
        # R5（SA §2.7 A-I14，DA-4）：显式空结束不再受 mandatory Takeover 门阻塞。
        can_finish_empty = (actionable and current_step == "proposal" and viewer_has_consul)
        proposal_selection_disabled_reason = ""
        if senate_no_host:
            # WP-M D5.2：无主持人 → 结构性跳过；零提案结算
            proposal_selection_disabled_reason = "元老院无在职主持官员"
        elif current_step != "proposal":
            proposal_selection_disabled_reason = "当前不在提案选择环节"
        elif not viewer_has_consul:
            proposal_selection_disabled_reason = "您的派系没有在城执政官可提交"

        # R5（SA §5.1，DA-1）：统一 War Card 只读投影（QML 零推导）；R6（SA §A.2）：
        # 投影只读透传 Core 的 schema_version/authority_by_mode，senate_api 不新写 route。
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
        # R6（SA §D.4，DA-4 B3）：Consul 冻结 direct 决策只读投影（**整个会期可读**，不依赖
        # `_senate_pending` 是否已清）；direct-only 结果页据此非空（**不得因无 passed_proposals 清空**）。
        # R9（FC-R9-02/03/04）：顶层作用域收敛——仅 **canonical 当前会期**（由有效 current-turn
        # PackageRecord 证明）的 direct 决策进入玩家当前行动面；无包 / 坏包（turn 缺失/非法/
        # 不匹配）**一律排除、不 fallback**。scope guard 仅在本顶层调用处：原 helper 与
        # `_build_public_announcement` 语义不变（历史 PA 不清）。
        _direct_scope_session = _current_canonical_direct_scope(state)
        consul_direct_decisions = (
            _consul_direct_decision_rows(state, _direct_scope_session)
            if _direct_scope_session else []
        )

        data = {
            "phase_id": "senate",
            "viewer_player_id": viewer_player_id,
            "current_player_id": current_player.player_id if current_player else None,
            "is_current_phase": current_phase_id == "senate",
            "is_current_player": state.is_current_player(viewer_player_id),
            "current_phase_id": current_phase_id,
            "interaction_mode": "interactive" if current_phase_id == "senate" else "readonly",
            "current_step": current_step,
            "steps": steps,
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
            "can_advance": ((current_step == "results") and has_real_senate_result)
            or (senate_no_host and actionable),
            # R5（SA §5.1，DA-4）：旧 pending Takeover / can_deploy 读模型键退役
            "can_finish_proposal_selection": can_finish_empty,
            "can_finish_empty": can_finish_empty,
            "senate_no_host": senate_no_host,
            "proposal_selection_disabled_reason": proposal_selection_disabled_reason,
            # R3-G-01 §1.5：settlement-pending 可见恢复态（DTO 字段 + 恢复动作位）
            # R6（SA §D.1.1，DA-4 B1）：legacy 键保留但正常态恒 False（不得驱动 UI）
            "senate_settlement_pending": senate_settlement_pending,
            "can_resolve_settlement": senate_settlement_pending,
            # R6（DA-4 B1）：异常恢复能力位（内部；非正常态动作位）
            "senate_finalization_error": senate_finalization_error,
            "can_retry_finalization": senate_finalization_error,
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
            # R6（SA §D.4，DA-4 B3）：直选身份面（按 `item_ref` 可重取；行内无 `proposal_id`）
            "consul_direct_decisions": consul_direct_decisions,
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
    """R6（SA §A.4）：legacy 单提案入口退役——单项规范化为完整 package 后委托 propose_many。

    兼容签名保留（生产 CLI 不再使用该便捷入口）。``bypass_turn_check`` 仅保留参数位，
    **不得**跳过 route/claims/事务/授权——统一由 propose_many → submit_proposal_package 校验。
    一次成功即关闭本会期选择（禁止循环追加）。
    """
    if not state:
        return api_response(False, "无效的游戏状态")
    request = _single_proposal_request(state, player_id, proposal_type, kwargs)
    if request is None:
        return api_response(False, f"未知的提案类型: {proposal_type}",
                            errors=[f"unknown proposal type: {proposal_type}"])
    result = propose_many(state, player_id, request)
    # 兼容桥（legacy 单项调用方读 ``data.proposal_id``）：submit 的 ``created`` 已含真 id；
    # 仅补一个顶层便捷字段，不改任何 route/claims/事务语义（War 身份/字段仍按 R6 快照）。
    if result.get("success") and isinstance(result.get("data"), dict):
        data = result["data"]
        created = data.get("created") or []
        if "proposal_id" not in data and len(created) == 1:
            data["proposal_id"] = created[0].get("proposal_id")
    return result


def _consul_for_actor(state: GameState, player_id: str):
    """actor 所属派系的 eligible Consul（供 legacy war 的显式 target 默认）。"""
    player = state.get_player(player_id) if player_id else None
    if not player:
        return None
    faction = state.get_faction(player.faction_id)
    if not faction:
        return None
    return _political_system(state)._find_consul_for_faction(faction)


def _single_proposal_request(state: GameState, player_id: str, proposal_type: str,
                             kwargs: dict) -> Optional[Dict[str, Any]]:
    """R6（SA §A.4）：legacy 单项 → 完整 package envelope（canonical）。

    - ``war``：``legions`` → ``reinforcement_n``；缺 target → Consul 显式 default
      （不再依赖隐式 Consul 语义）。
    - ``peace``：丢弃 Commander/N 缓存（仅 mode=peace）。
    - 其余（budget/land/governor/...）：作为普通 non-War 提案进入同一 package。
    未知类型 → None（调用方 fail-closed）。
    """
    params = dict(kwargs)
    if proposal_type == "war":
        target = params.get("target_commander_id")
        if target is None:
            consul = _consul_for_actor(state, player_id)
            target = consul.id if consul is not None else None
        return {"war_drafts": [{
            "war_id": params.get("war_id"),
            "checked": True,
            "mode": "command",
            "target_commander_id": target,
            "reinforcement_n": params.get("reinforcement_n", params.get("legions")),
        }], "proposals": []}
    if proposal_type == "peace":
        return {"war_drafts": [{
            "war_id": params.get("war_id"),
            "checked": True,
            "mode": "peace",
            "target_commander_id": None,
            "reinforcement_n": None,
        }], "proposals": []}
    if proposal_type in ("war_proposal",):
        return None
    return {"war_drafts": [], "proposals": [{"type": proposal_type, "params": params}]}



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
        request = _package_request_from_specs(proposals or [], state, player_id)

    # R5（SA §4.8/§5.4，DA-5）：冻结会期身份（execution_id 依赖会期唯一性；存档需持久化）
    turn = state.turn.turn_number if state.turn else 0
    if not request.get("senate_session_id"):
        request["senate_session_id"] = f"turn-{turn}"

    # R6（SA §B.2 V4，DA-2 B2；收口 DA-2 B1 D-1）：空包**完全走 V0–V4**，不再在 API 侧
    # 凭空置完成标记——由 Core `submit_proposal_package` 统一鉴权/校验/事务/授权，
    # 真注册 SubmissionContext/PackageRecord（零 proposed/direct items）。

    result = _political_system(state).submit_proposal_package(
        player_id, request, _build_submit_context(state))
    return api_response(
        success=result.get("success", False),
        message=result.get("message", ""),
        data=result.get("data", {}),
        errors=result.get("errors", []),
    )


def _package_request_from_specs(specs: List[Dict[str, Any]], state: Optional[GameState] = None,
                                player_id: Optional[str] = None) -> Dict[str, Any]:
    """把 API 层 specs 归一为 R6 整包 envelope（canonical war_drafts + 非 War proposals）。

    R6（SA §A.4）：旧 ``war`` / ``peace`` specs 在 API 边界统一翻成 canonical war_drafts
    （``war`` 的 ``legions`` → ``reinforcement_n``；``peace`` 丢弃 Commander/N 缓存）；
    未提供 target 的 ``war`` 保留 None（由 Submit fail-closed 报 COMMANDER_REQUIRED，不静默换将）。
    """
    war_drafts = []
    non_war = []
    for spec in specs or []:
        if not isinstance(spec, dict):
            non_war.append(spec)
            continue
        stype = spec.get("type")
        src = spec.get("params") if isinstance(spec.get("params"), dict) else spec
        merged = dict(src)
        for k, v in spec.items():
            merged.setdefault(k, v)
        if stype in ("war", "peace"):
            if stype == "peace":
                war_drafts.append({
                    "war_id": merged.get("war_id"), "checked": True, "mode": "peace",
                    "target_commander_id": None, "reinforcement_n": None,
                })
            else:
                target = merged.get("target_commander_id")
                if target is None and state is not None:
                    consul = _consul_for_actor(state, player_id)
                    target = consul.id if consul is not None else None
                war_drafts.append({
                    "war_id": merged.get("war_id"), "checked": True, "mode": "command",
                    "target_commander_id": target,
                    "reinforcement_n": merged.get("reinforcement_n", merged.get("legions")),
                })
            continue
        if stype == "war_proposal" or "checked" in spec:
            war_drafts.append({
                "war_id": merged.get("war_id"),
                "checked": bool(merged.get("checked", False)),
                "mode": merged.get("mode", "command"),
                "target_commander_id": merged.get("target_commander_id"),
                "reinforcement_n": merged.get("reinforcement_n"),
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

    # 1. 查找主持人（WP-M D4.5：由 _find_any_eligible_consul 改为单一权威 GameState.get_presiding_officer）。
    host_figure = state.get_presiding_officer()
    if not host_figure:
        return api_response(False, "没有可主持的官员，无法自动提交提案")

    # 2. 查找主持人对应玩家
    consul_player = state.get_player_by_faction(host_figure.faction_id)
    if not consul_player:
        return api_response(False, "主持人无对应玩家")
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
        _live_cmd = (state.get_living_member(_war.commander_id)
                     if _war.commander_id is not None else None)
        if _live_cmd is not None:
            used_commanders.add(_live_cmd.id)
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
        # R11-S1（共享剩余池）：4a 与 4b′ 共享同一可用军团池——此处一次读取
        # （语义等价：有 threats 时值不变；无 threats 时 remaining=满池，供 4b′ 消费）。
        ms = state.get_military_system()
        remaining = len(ms.get_available_legions()) if ms else 0
        threats = ws.get_threat_wars()
        if threats:
            propose_chance = state.config.get("testing.propose_war_chance", 0.7)
            always_declare = state.config.get("testing.always_declare", False)

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

    # ========== 4b′. 现有/进行中真实战 → consul_direct command（WP-G-R11 补族） ==========
    # 经共享权威路由（build_war_card_views 透传的 authority_by_mode = classify_war_authority
    # 产物）枚举真实进行中/被动战争（禁私有 switch）；询问保留策略
    # AutoWarTakeoverDecider.decide_takeover（TAKE ACTION / NO ACTION）；行动时用共享候选
    # producer 选 target（有效现任 = Continue 保留；无有效现任 = Takeover 新选），用权威
    # reinforcement_range 值域内 random.randint 取援军 N（镜像 4a 宣战随机口径、共享剩余池
    # 守恒）；仅 append checked command draft，随既有 propose_many 整包提交（零构造期
    # mutation / 零绕过整包 / 对 consul_direct 不走 Vote-Veto）。
    if ws:
        pending_peace_ids = {w.id for w in ws.get_truce_wars_with_pending_treaty()}
        # Addendum A1 §4.1：复用既有共享候选 producer（commander_candidates closure，≈L1104；
        # 零新候选逻辑/零第二 producer）。producer 忽略 ctx（仅读 state），故其候选集与
        # submit 期 `submit_proposal_package` 校验的 candidate_ids 同集合。
        _candidate_ids = {row["figure_id"] for row in commander_candidates}
        takeover_decider = AutoWarTakeoverDecider()
        for card in politics.build_war_card_views({
                "current_turn": (state.turn.turn_number if state.turn else None),
                "consul_id": host_figure.id}):
            wid = card.get("war_id")
            if (card.get("authority_by_mode") or {}).get("command") != AUTHORITY_CONSUL_DIRECT:
                continue  # 非 consul_direct command（active_declaration=senate_vote 归 4a）→ 跳过
            if wid in pending_peace_ids:
                continue  # 已由 4b 产出 peace intent → 同一 War 禁双 intent（cross_route_conflict）
            war = ws.get_war_by_id(wid)
            if war is None:
                continue
            old_commander = (state.get_living_member(card.get("current_commander_id"))
                             if card.get("current_commander_id") is not None else None)
            if not takeover_decider.decide_takeover(war, host_figure, old_commander, state):
                continue  # NO ACTION（含起义/同人守卫）→ omit（= unchecked / 保留 claim）
            if card.get("current_commander_id") is not None:
                target = card["current_commander_id"]  # Continue：保留现任（无强制替换）
                if target not in _candidate_ids:
                    # ★ Addendum A1 对称守卫：现任 ∉ 共享候选集 → Core 必拒
                    # （COMMANDER_INELIGIBLE 整包 fail-closed）→ omit 本战，与 Takeover
                    # 分支 `if target is None: continue` 对称；其余战争/提案照常发布。
                    continue
            else:
                target = _pick_ai_commander()  # Takeover：共享候选 producer + claim 唯一性
                if target is None:
                    continue  # 无合法 Commander → 无法组合法草案 → omit
            rng = reinforcement_range(state, war)
            if rng is None:
                continue  # 值域不可得（防御；生产 config 存在）
            lo = rng["min"]
            hi = min(remaining, rng["max"])  # 与 4a 共享剩余池（ΣN ≤ 实际池守恒）
            if hi < lo:
                n = 0  # 残余池不足 → N=0（仍绑定 Commander；REINFORCEMENT N≥0 合法）
            else:
                n = random.randint(lo, hi)  # 镜像 4a 宣战随机口径（同一 randint 机制）
            remaining -= n
            war_drafts.append({
                "war_id": wid, "checked": True, "mode": "command",
                "target_commander_id": target, "reinforcement_n": n,
            })
            created_proposals.append({
                "type": "war",
                "war_id": wid,
                "legions": n,
                "description": f"对 {war.name} 下达执政官直行动命令，增援 {n} 个军团",
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
    # WP-M D4.5：当主持人 office != consul 时，构造阶段跳过会路由到 AUTHORITY_CONSUL_DIRECT
    # 的草案（与 D4.4 单一权威一致；复用唯一 route producer classify_war_authority）。
    if host_figure.office != "consul" and war_drafts:
        ws_route = state.get_war_system()
        filtered_drafts: List[Dict[str, Any]] = []
        for draft in war_drafts:
            mode = draft.get("mode")
            if draft.get("checked") and mode in ("command", "peace") and ws_route is not None:
                facts = ws_route.describe_senate_war(draft["war_id"], {}) or {}
                if classify_war_authority(facts).get(mode) == AUTHORITY_CONSUL_DIRECT:
                    continue  # 回退主持人不得经 AI 路径提交 direct 草案
            filtered_drafts.append(draft)
        war_drafts = filtered_drafts
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


def _war_direct_decision_refs(consul_decisions: List[dict]) -> List[dict]:
    """R6（SA §C.4，DA-3 B1）：receipt 的 `direct_decision_refs`（无 proposal_id）。"""
    refs = []
    for d in consul_decisions:
        refs.append({"direct_decision_id": d.get("direct_decision_id"),
                     "war_id": d.get("war_id"),
                     "authority": d.get("authority"),
                     "decision_state": d.get("decision_state"),
                     "snapshot_ref": copy.deepcopy(d.get("snapshot_ref") or {})})
    return sorted(refs, key=lambda r: str(r["direct_decision_id"]))


def _frozen_pending_peace_ids(submission_context) -> Optional[List[str]]:
    """R6（SA §C.1，DA-3 B2）：`PT` = **frozen Context 的真实 pending-peace War**。

    只从冻结 `SubmissionContext` 的 War 深值（`status`/`peace_treaty.status`）派生，
    **不**读边界当次 live `get_truce_wars_with_pending_treaty()`（消 TOCTOU；Submit 后漂移的
    新 pending universe 不属于本包冻结面）。

    返回 ``None`` = 不存在冻结上下文（无包/legacy 路径），调用方回退 live。
    """
    if not isinstance(submission_context, dict):
        return None
    wars = submission_context.get("wars")
    if not isinstance(wars, dict):
        return None
    out: List[str] = []
    for war_id, row in wars.items():
        if not isinstance(row, dict):
            continue
        if str(row.get("status")) != "truce":
            continue
        treaty = row.get("peace_treaty") or {}
        if isinstance(treaty, dict) and treaty.get("status") == "pending":
            out.append(str(war_id))
    return sorted(out)


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
    # R6（SA §C.1，DA-3 B1）：显式双输入——FROZEN ConsulWarDecision 独立账本（无 proposal_id）。
    consul_decisions = [copy.deepcopy(d) for _did, d in
                        state.get_consul_war_decisions(session_id).items()]
    consul_decisions.sort(key=lambda d: str(d.get("direct_decision_id")))
    # package 身份从 PackageRecord 读（不得只从第一条 Senate decision 找；direct-only/空包会丢）
    package_id = state.get_senate_package_id_for_session(session_id)
    package_record = state.get_senate_package_record(package_id) if package_id else None
    submission_context = None
    if isinstance(package_record, dict) and package_record.get("submission_context_id"):
        submission_context = state.get_submission_context(package_record["submission_context_id"])
    real_wars = politics._real_wars()
    # R6（SA §C.1，DA-3 B2）：`PT` = frozen Context 的真实 pending-peace War（非边界当次 live）。
    frozen_pending_ids = _frozen_pending_peace_ids(submission_context)
    if frozen_pending_ids is not None:
        pending_ids = frozen_pending_ids
        pending_source = "frozen_context"
    else:
        pending_ids = [w.id for w in ws.get_truce_wars_with_pending_treaty()] if ws else []
        pending_source = "live_fallback_no_context"
    u0 = sorted(legion.number for legion in ms.get_available_legions()) if ms else []
    plan = politics.build_war_resolution_plan(
        decisions, consul_decisions, current_turn=turn, session_id=session_id,
        real_wars=real_wars, available_legion_ids=u0, pending_war_ids=pending_ids,
        package_id=package_id, submission_context=submission_context)
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

    # R6（SA §C.1）：集合合法性 assert（D 仅真实 War command / V command 只能 active / V peace
    # 只能 pending / 同 War 跨 route 与重复 intent）→ fail-closed 拒绝，不 last-write-wins。
    if plan.get("input_conflicts"):
        return {"success": False, "message": "输入完整性失败：执行集合身份冲突",
                "data": {"code": "WAR_EXECUTION_INPUT_INVALID", "execution_id": execution_id,
                         "committed": False, "next_phase_id": None, "retryable": False,
                         "failed_stage": "plan", "offending_refs": plan["input_conflicts"]}}
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
                "package_id": package_id or next((
                    d.get("snapshot_ref", {}).get("package_id") for d in decisions
                    if d.get("snapshot_ref", {}).get("package_id")), None),
                "execution_id": execution_id,
                "protocol_version": plan.get("protocol_version"),
                "status": "COMMITTED",
                "proposal_refs": _war_proposal_refs(decisions),
                "direct_decision_refs": _war_direct_decision_refs(consul_decisions),
                "input_fingerprint": fingerprint,
                "pending_fallback_war_ids": list(plan["pending_fallback_set"]),
                "pt_source": pending_source,
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
    # WP-M D5.4：无主持人（FC-01=0）→ 先触发 finalize 豁免（零提案结算）再执行边界；
    # 有主持人且无 phase_result → 仍按既有「未就绪」拒绝（禁隐式结算）。
    if not state.get_phase_result("senate") and state.get_presiding_officer() is None:
        finalize_result = finalize_senate_if_ready(state)
        if not finalize_result.get("success"):
            return api_response(False, finalize_result.get("message", ""))
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


# ==================== R6（SA §D.1.1，DA-4 B1）：政治 finalization 完成协议 ====================

#: 完成协议版本（幂等键第三元；协议语义变更必须递增）。
SENATE_FINALIZATION_PROTOCOL_VERSION = 2


class _FinalizationStageError(RuntimeError):
    """finalization 中段失败（`stage` = 故障点；`retryable` 供调用方语义判定）。"""

    def __init__(self, stage: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.stage = stage
        self.retryable = retryable


def senate_finalization_id(state: GameState) -> tuple:
    """幂等键：`(session_id, senate_session_id, protocol_version=2)`（SA §D.1.1）。"""
    senate_session_id = state.get_senate_session()
    if not senate_session_id:
        turn = state.turn.turn_number if state.turn else 0
        senate_session_id = f"turn-{turn}"
    session_id = getattr(state, "session_id", None) or senate_session_id
    return (session_id, senate_session_id, SENATE_FINALIZATION_PROTOCOL_VERSION)


def _finalization_fingerprint(source: dict) -> str:
    """内容指纹：确定性序列化（sort_keys）+ SHA256——**不重读当前部署态重算**。"""
    payload = json.dumps(source, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pending_cleared(state: GameState) -> bool:
    """完成事实③：`_senate_pending` 临时集清理标记（提案/决策完成标记/直接动作全清）。"""
    return (len(state.get_senate_proposals()) == 0
            and not state.senate_proposal_decision_complete
            and len(state.get_senate_direct_actions()) == 0)


def completion_facts(state: GameState, senate_session_id: str) -> Dict[str, Any]:
    """读四完成事实（缺一即未完成；**顶层 `result.success` 不足以关闭窗口**）。"""
    phase_result = state.get_phase_result("senate")
    data = phase_result.get("data", {}) if isinstance(phase_result, dict) else {}
    # ②「final outcome 已冻结」= 冻结步骤已同版落存（含合法 0 条：零 War 提案会期）。
    # 不以 decisions 账本非空为判据（零提案/direct-only 合法路径无 War 决策）。
    frozen = isinstance(data, dict) and "frozen_war_decisions" in data
    return {
        "phase_result": bool(isinstance(phase_result, dict) and phase_result.get("success")),
        "final_outcome_frozen": bool(frozen),
        "pending_cleared": _pending_cleared(state),
        "receipt": state.has_senate_finalization_receipt(senate_session_id),
    }


def _build_finalization_receipt(state: GameState, finalization_id: tuple,
                               phase_result: dict) -> dict:
    """组装 finalization receipt（幂等键 + 内容指纹）——全 JSON 安全标量（B6 tuple 教训）。"""
    data = dict(phase_result.get("data", {}) or {})
    return {
        "finalization_id": tuple(finalization_id),
        "finalization_id_list": [str(part) for part in finalization_id],
        "session_id": str(finalization_id[0]),
        "senate_session_id": str(finalization_id[1]),
        "protocol_version": int(finalization_id[2]),
        "phase_id": "senate",
        "phase_result_success": bool(phase_result.get("success")),
        "content_fingerprint": _finalization_fingerprint(data),
        "governor_assignment_count": len(data.get("governor_assignments") or []),
        "retained_effect_intent_count": len(data.get("retained_effect_intents") or []),
    }


def _build_public_announcement(state: GameState, passed_snapshot: List[dict],
                               direct_actions: List[dict]) -> dict:
    """PA（public_announcement）组装 —— 纯读纯函数（幂等；供 PA 故障点注入测试）。

    D.4：`enacted_proposals` 仅 final enacted 真 Senate items（D-06：rejected/vetoed 不进公示）；
    每行带三身份字段（`identity` / `authority` / `authority_label` / `execution` / `display_label`）——
    真 Senate 获批行 =「元老院批准 · 待边界执行」；`consul_direct_decisions` = 冻结执政官战争决定
    （`execution=awaiting_boundary`，不宣称已执行）；Peace 行仅登记 `pending_boundary_effects`
    （含 `peace_recall`）——**未执行不得写「已召回」**；legacy `direct_actions` = 已执行审计。
    """
    enacted = []
    for p in (passed_snapshot or []):
        mode = p.get("mode")
        row = {
            "identity": "senate_proposal",
            "proposal_id": p.get("id"),
            "type": p.get("type"),
            "authority": p.get("authority") or AUTHORITY_SENATE_VOTE,
            "authority_label": "元老院批准",
            "execution": "awaiting_boundary",
            "execution_label": "待边界执行",
            "display_label": SENATE_ENACTED_ROW_LABEL,
            "pending_boundary_effects": ["peace_recall"] if mode == "peace" else [],
            "title": _proposal_label(state, p) + (
                "（获批 · 待边界执行）" if p.get("type") == "war_proposal" else ""),
            "key_parameters": _announcement_key_params(p),
        }
        enacted.append(row)
    return {
        "enacted_proposals": enacted,
        # R6（SA §D.4，DA-4 B3）：冻结 Consul direct 行（整个会期可读；与 legacy 审计表分身份）
        "consul_direct_decisions": _consul_direct_decision_rows(state),
        "direct_actions": direct_actions,
    }


def finalize_senate_if_ready(state: GameState,
                             vote_decider: Optional[SenateVoteDecider] = None) -> dict:
    """服务端命令流程调用的**唯一**政治 finalization 入口（API / CLI / GUI 三入口共用）。

    **不在 GET DTO 路径隐式写**：仅由 Submit 成功后的命令流程（零 Senate / vote 完成且零
    veto 候选 / veto 完成三入口）与 `resolve_senate` 兼容别名调用。

    完成四事实必须**同版一致**（缺一即未完成）：
    ① 真实 `phase_result(senate){success:true}`；② final outcome 冻结；
    ③ `_senate_pending` 清理标记；④ receipt（`finalization_id` + 内容指纹）。

    **clear 位置硬约束**：`clear_senate_pending` 位于「非 War 效果已执行 + final outcome
    已冻结 + 结果已暂存」**之后**、receipt 写齐**之前**，且同一事务 commit 内；
    禁「先 clear 再补写」/「从已清空临时集重建结果」。
    """
    if not state:
        return api_response(False, "无效的游戏状态")
    finalization_id = senate_finalization_id(state)
    senate_session_id = finalization_id[1]
    existing_result = state.get_phase_result("senate")
    existing_receipt = state.get_senate_finalization_receipt(senate_session_id)

    # —— 幂等重放：四事实已同版 → 按 finalization_id 返回**原** phase_result/PA/direct 摘要，
    # 零再次执行非 War 效果、零重复 Governor、零重复征召。
    if existing_result and existing_receipt:
        data = dict(existing_result.get("data", {}) or {})
        data["finalization_id"] = [str(part) for part in finalization_id]
        data["finalization_receipt"] = existing_receipt
        data["replayed"] = True
        return api_response(True, "元老院 finalization 已完成（幂等重放）", data=data)

    # 显式空选择守卫（仅对**首次** finalization 生效）——逐字保留 R4-09：零提案且未显式提交
    # 空批 → 拒绝，禁隐式 resolve。部分完成态（①已在、④缺）不适用本守卫（pending 已清）。
    # WP-M D5.3 / FC-09：空选择守卫的**唯一豁免** = 无主持人（get_presiding_officer() is None）——
    # 此时允许零提案结算（结构性跳过）。
    if (not existing_result
            and not state.get_senate_proposals()
            and not state.senate_proposal_decision_complete
            and state.get_presiding_officer() is not None):
        return api_response(
            False,
            "提案选择未完成：请先显式提交空批或完成提案后再结算",
            data={"proposal_selection_not_complete": True,
                  "settlement_guard": "proposal_selection_not_complete"},
        )

    # WP-M D8：无主持人结构性跳过（零提案结算前登记 DEBUG provenance）
    if (not existing_result
            and not state.get_senate_proposals()
            and not state.senate_proposal_decision_complete
            and state.get_presiding_officer() is None):
        state.log_event(
            "元老院无主持官员，按无法案提交结构性跳过",
            level=logging.DEBUG,
            extra={"type": "senate_no_host_skip", "senate_session_id": senate_session_id},
        )

    stage = "political_resolve"
    try:
        with SenateFinalizationTransaction(state) as txn:
            # —— 部分事实（①已写、④未齐；如 record_phase_result 后响应丢失）→ **补齐**而非重跑：
            # ① ② 已在（非 War 效果 + final outcome 冻结先于落存），只需补 ③ ④。
            if existing_result and not existing_receipt:
                stage = "clear_pending"
                if not _pending_cleared(state):
                    state.clear_senate_pending()
                stage = "receipt"
                receipt = _build_finalization_receipt(state, finalization_id, existing_result)
                state.record_senate_finalization_receipt(receipt)
                facts = completion_facts(state, senate_session_id)
                if not all(facts.values()):
                    raise _FinalizationStageError("receipt", f"四完成事实未同版: {facts}")
                txn.commit()
                data = dict(existing_result.get("data", {}) or {})
                data["finalization_id"] = [str(part) for part in finalization_id]
                data["finalization_receipt"] = receipt
                data["recovered"] = True
                data["completion_facts"] = facts
                state._last_senate_finalization_error = None
                return api_response(True, "元老院 finalization 已补齐（幂等恢复）", data=data)

            # —— 完整重跑（S0 起，单一受锁临界区；任何中段失败 → 精确回滚 S0）——
            stage = "political_resolve"
            result = _political_system(state).resolve_senate(vote_decider)
            if not result.get("success"):
                raise _FinalizationStageError(
                    "political_resolve", str(result.get("message")), retryable=False)
            phase_data = dict(result.get("data", {}) or {})
            # 军事 hook（Fleet / 起义）只登记 intent（C.5.1：零军事写，应用在边界事务）
            phase_data["retained_effect_intents"] = \
                _political_system(state)._retained_effect_intents()
            phase_data["fleet_assignments"] = []
            phase_data["rebellion_commander_assignments"] = []
            # Governor（政治步骤，C.5.3 claim-aware；仍在 finalization 内）
            # ②final outcome 冻结（含合法 0 条）与军事 intent 登记（C.5.1：零军事写）
            frozen_decisions = [
                d for (sess, _pid), d in state.get_war_decisions().items()
                if str(sess) == str(senate_session_id)
            ]
            phase_data["frozen_war_decisions"] = frozen_decisions
            stage = "governor"
            phase_data["governor_assignments"] = assign_governors(state)
            # PA / direct 摘要组装（纯读，幂等）
            stage = "public_announcement"
            phase_data["direct_actions"] = result.get("data", {}).get("direct_actions", [])
            phase_data["public_announcement"] = _build_public_announcement(
                state,
                result.get("data", {}).get("passed_proposals_snapshot", []) or [],
                phase_data["direct_actions"],
            )
            # ①结果已暂存（真实 success:true 才落存；失败路径从不持久化 phase_result 冒充成功）
            stage = "record_phase_result"
            stored = {"success": True, "message": result.get("message", ""), "data": phase_data}
            state.record_phase_result("senate", stored)
            if not completion_facts(state, senate_session_id)["final_outcome_frozen"]:
                raise _FinalizationStageError(
                    "record_phase_result", "完成事实②（final outcome 冻结）未落地")
            # ③ pending 清理标记（非 War 效果 + 冻结 + 暂存**之后**、receipt **之前**）
            stage = "clear_pending"
            state.clear_senate_pending()
            if not _pending_cleared(state):
                raise _FinalizationStageError("clear_pending", "完成事实③（pending 清理标记）未落地")
            # ④ receipt 写齐（commit 前最后一步）
            stage = "receipt"
            receipt = _build_finalization_receipt(state, finalization_id, stored)
            state.record_senate_finalization_receipt(receipt)
            facts = completion_facts(state, senate_session_id)
            if not all(facts.values()):
                raise _FinalizationStageError("receipt", f"四完成事实未同版: {facts}")
            txn.commit()
            data = dict(phase_data)
            data["finalization_id"] = [str(part) for part in finalization_id]
            data["finalization_receipt"] = receipt
            data["completion_facts"] = facts
            state._last_senate_finalization_error = None
            return api_response(True, result.get("message", ""), data=data,
                                errors=result.get("errors", []))
    except Exception as exc:  # noqa: BLE001 —— 失败必须结构化登记 + S0 回滚（禁谎报成功）
        stage = getattr(exc, "stage", stage)
        retryable = getattr(exc, "retryable", True)
        diagnostic_id = uuid.uuid4().hex[:12]
        state.log_event(
            f"元老院 finalization 失败[{stage}]: {exc}",
            level=logging.ERROR,
            extra={"type": "senate_finalization_error", "stage": stage,
                   "diagnostic_id": diagnostic_id, "retryable": retryable},
        )
        # 异常恢复能力位（内部）：仅真实失败时置位；成功路径复位为 None
        state._last_senate_finalization_error = {
            "stage": stage, "retryable": retryable, "diagnostic_id": diagnostic_id}
        return api_response(
            False,
            f"元老院 finalization 失败（stage={stage}，可重试={retryable}）",
            data={
                "finalization_error": {
                    "stage": stage,
                    "retryable": retryable,
                    "diagnostic_id": diagnostic_id,
                    "finalization_id": [str(part) for part in finalization_id],
                },
                "finalization_id": [str(part) for part in finalization_id],
                "completion_facts": completion_facts(state, senate_session_id),
                "can_advance": False,
            },
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
    # R6（SA §D.1.1，DA-4 B1）：本函数退役为 `finalize_senate_if_ready` 的兼容别名——三入口
    # （API / CLI / GUI）共用同一服务端完成协议（空选择守卫 / 幂等重放 / 受锁事务 /
    # 四完成事实同版）。旧前置幂等 no-op 与守卫整体迁入后者，此处零重复判定。
    return finalize_senate_if_ready(state, vote_decider)


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

    R6（SA §C.5.1/C.5.2，DA-3 B3）：本函数的**自动层调用点已收口**到
    `PoliticalSystem.commit_war_resolution` 的 retained automatic effects 层（边界事务内）；
    本函数保留为既有业务规则载体（Fleet 挑配 / 动力需求 / 可用舰队语义逐字不变），
    `phase_senate.py` CLI 第二调用退役属 DA-3 B4（C.5.2）。
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


def _frozen_commander_claim_ids(state: GameState) -> set:
    """R6（SA §C.5.3 / §D.1.2，DA-3 B5）：本包**冻结 claims 的 Commander 身份集**。

    读取当前会期的 `PackageRecord` → `SubmissionContext.claims`（与 Submit 校验 V3 同一冻结
    快照），作为最终结算内自动 `assign_governors` 的**硬排除输入** —— 排除「本包将被冻结
    direct/Peace 任命为 Commander」的人物，防止自动任命制造同一 figure 的
    Governor×Commander 双角色（及其自身制造的永久 CONTEXT_CHANGED / 重试环）。

    - 无包 / 无 context（legacy 直调）→ **空集**（不静默改变既有语义）；
    - 只作**排除**，不新增候选、不改 Governor/Commander 业务规则（C.5.3 禁项）。
    """
    if not state:
        return set()
    session_id = state.get_senate_session()
    if not session_id:
        return set()
    package_id = state.get_senate_package_id_for_session(session_id)
    if not package_id:
        return set()
    record = state.get_senate_package_record(package_id) or {}
    context_id = record.get("submission_context_id")
    if not context_id:
        return set()
    context = state.get_submission_context(context_id) or {}
    excluded: set = set()
    for claim in (context.get("claims") or []):
        if isinstance(claim, dict) and claim.get("commander_id") is not None:
            excluded.add(claim["commander_id"])
    return excluded


def assign_governors(state: GameState, excluded_commander_ids=None) -> list[dict]:
    """总督候选人筛选与分配。

    分析所有行省 → 筛选候选人 → 分配总督职位。
    返回分配结果列表：[{province_id, governor_id, name, assigned_at}, ...]

    业务逻辑继承自 phase_senate.py CLI _process_governor_appointments + _execute_governor_appointments:
    - 遍历无总督行省
    - 按候选人资格/忠诚度条件筛选
    - 分配最佳候选人
    - 更新 Province 实体 governor_designate_id 字段

    R6（SA §C.5.3 / §D.1.2，DA-3 B5 — **claim-aware**）：`excluded_commander_ids` = 本包冻结
    claims 的 Commander 身份集；命中的候选人从候选池**硬排除**（正常 business 语义不动：无候选
    即不分配、空位合法）。**禁**提前置军事 absent / 跳过 Governor 步骤 / 撤回已发布 direct /
    忽略 cross-role / 强制重提 —— 本函数的解法仅「候选排除 + 空位合法」。
    **缺省 `None`** = 自动取本包冻结 claims（`_frozen_commander_claim_ids`；无包/legacy → 空集，
    行为与 baseline 逐字一致）；显式传入（含空集）→ 以传入值为准。
    """
    if not state:
        return []

    import datetime

    if excluded_commander_ids is None:
        excluded = _frozen_commander_claim_ids(state)
    else:
        excluded = set(excluded_commander_ids)

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
            if fig.id in excluded:
                # R6（SA §C.5.3）：冻结 claims 的 Commander 硬排除（防 Governor×Commander 双角色）
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

