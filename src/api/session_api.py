"""
src/api/session_api.py
GUI 安全状态 API —— 按 viewer_player_id 过滤的只读 DTO 与阶段协调
"""
import logging
from typing import Any, Dict, List, Optional

from src.api import api_response
from src.api import population_api
from src.api import player_api
from src.api import faction_api
from src.api import figure_api
from src.core.game_state import GameState
from src.core.scenario_loader import ScenarioLoader


logger = logging.getLogger("EOR-GUI")


# ---------------------------------------------------------------------------
# 1. 会话创建
# ---------------------------------------------------------------------------

def create_gui_prototype_session(config_path: Optional[str] = None, start_phase: str = "mortality") -> dict:
    """
    创建 GUI 原型会话。
    使用 gui_prototype.json 场景。默认从真实天命阶段开始；测试可显式指定 start_phase。
    """
    try:
        state = GameState(config_path)
        ScenarioLoader.load_scenario(state, "gui_prototype.json")

        phase_order = _phase_order()
        if start_phase not in phase_order:
            start_phase = "mortality"
        for phase_id in phase_order:
            if phase_id == start_phase:
                break
            state.mark_phase_executed(phase_id)

        # 设置当前玩家为第一个 HUMAN 玩家
        human_players = [
            p.player_id for p in state.get_all_players()
            if p.player_type.value == "human"
        ]
        if human_players:
            state.set_current_player(human_players[0])
            state.set_turn_order(human_players)

        current_player = state.get_current_player()
        logger.info("GUI prototype session created", extra={
            "players": human_players,
            "current_player": current_player.player_id if current_player else None,
            "start_phase": start_phase,
        })
        return api_response(True, "GUI prototype session created", {
            "state": state,
            "human_players": human_players,
            "start_phase": start_phase,
        })
    except Exception as e:
        logger.exception("Session creation failed")
        return api_response(False, f"Session creation failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 2. 按 viewer 过滤的快照
# ---------------------------------------------------------------------------

def get_session_snapshot(state: GameState, viewer_player_id: str) -> dict:
    """
    返回 GUI 需要的安全快照。只包含 viewer_player_id 有权查看的信息。
    """
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        current_player = state.get_current_player()
        faction = state.get_faction(viewer.faction_id) if viewer.faction_id else None

        # 当前玩家可见的人物（仅本派系 + 公开信息）
        my_figures = []
        for fig in state.get_living_members():
            if fig.faction_id == viewer.faction_id:
                my_figures.append({
                    "id": fig.id,
                    "name": fig.get_formal_name(),
                    "faction_id": fig.faction_id,
                    "wealth": fig.wealth,
                    "popularity": fig.popularity,
                    "influence": fig.influence,
                    "office": fig.office,
                    "is_faction_leader": fig.is_faction_leader,
                    "is_absent": fig.is_absent,
                    "class_tier": fig.class_tier.value if hasattr(fig.class_tier, 'value') else str(fig.class_tier),
                    "age": fig.age,
                })

        # 国家资源（公开）
        public_resources = {
            "treasury": state.treasury,
            "turn_number": state.turn.turn_number if state.turn else 0,
            "year": state.turn.year if state.turn else 0,
            "year_display": _format_year(state.turn.year if state.turn else 0),
            "living_members": len(state.get_living_members()),
        }

        # 派系资源（仅本派系）
        faction_resources = None
        if faction:
            members = [m for m in state.get_living_members() if m.faction_id == faction.id]
            faction_resources = {
                "id": faction.id,
                "name": faction.name,
                "treasury": faction.treasury,
                "member_count": len(members),
                "total_influence": sum(m.influence for m in members),
            }

        current_phase_id = _infer_current_phase_id(state)
        phase_nav = _build_phase_navigation(state, current_phase_id, viewer_player_id)
        selected_phase_summary = _build_phase_summary(current_phase_id, state, viewer_player_id)
        global_warnings = _build_global_warnings(state, viewer_player_id)

        # 当前可执行动作
        actions = _build_available_actions(state, viewer_player_id)

        # 人口阶段进度
        population_progress = _build_population_progress(state, viewer_player_id)

        data = {
            "current_player_id": current_player.player_id if current_player else None,
            "viewer_player_id": viewer_player_id,
            "viewer_faction_id": viewer.faction_id,
            "is_current_player": state.is_current_player(viewer_player_id),
            "current_phase_id": current_phase_id,
            "selected_phase_id": current_phase_id,
            "public_resources": public_resources,
            "faction_resources": faction_resources,
            "my_figures": my_figures,
            "phase_navigation": phase_nav,
            "selected_phase_summary": selected_phase_summary,
            "global_warnings": global_warnings,
            "available_actions": actions,
            "population_progress": population_progress,
        }
        return api_response(True, "Snapshot refreshed", data)
    except Exception as e:
        logger.exception("Snapshot failed")
        return api_response(False, f"Snapshot failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 3. 人口阶段视图
# ---------------------------------------------------------------------------

def get_population_view(state: GameState, viewer_player_id: str) -> dict:
    """
    返回人口阶段的详细视图，包含候选人、已投票状态、可执行操作。
    """
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        # 本派系可操作人物
        my_figures = []
        for fig in state.get_living_members():
            if fig.faction_id == viewer.faction_id:
                my_figures.append({
                    "id": fig.id,
                    "name": fig.get_formal_name(),
                    "faction_id": fig.faction_id,
                    "wealth": fig.wealth,
                    "popularity": fig.popularity,
                    "influence": fig.influence,
                    "office": fig.office,
                    "is_faction_leader": fig.is_faction_leader,
                    "is_absent": fig.is_absent,
                    "class_tier": fig.class_tier.value if hasattr(fig.class_tier, 'value') else str(fig.class_tier),
                    "age": fig.age,
                })

        # 候选人（所有人可见，但只含公开信息）
        cand_result = population_api.get_candidates(state)
        candidates = cand_result.get("data", {}) if cand_result.get("success") else {}
        result = state.get_phase_result("population")
        result_data = result.get("data", {}) if isinstance(result, dict) else {}
        resolved = bool(result) or state.is_phase_executed("population")
        if resolved and isinstance(result_data, dict) and result_data.get("candidates"):
            candidates = result_data["candidates"]

        # 当前 viewer 已投票的官职
        my_votes = {}
        for vote in state.get_population_votes():
            if vote[0] == viewer_player_id:
                my_votes[vote[1]] = vote[2]

        # 当前 viewer 已完成的庆典
        my_campaigns = []
        for camp in state.get_population_campaigns():
            if camp[0] == viewer_player_id:
                my_campaigns.append({"figure_id": camp[1], "amount": camp[2]})

        # 是否允许操作
        is_current = state.is_current_player(viewer_player_id)
        current_phase_id = _infer_current_phase_id(state)
        is_population_phase = current_phase_id == "population"
        office_count = len([office for office, rows in candidates.items() if rows])
        campaign_done = bool(my_campaigns)
        vote_done = office_count > 0 and len(my_votes) >= office_count
        current_step = "results" if resolved else ("vote" if campaign_done else "campaign")
        can_campaign = is_current and is_population_phase and not resolved
        can_vote = is_current and is_population_phase and campaign_done and not resolved
        can_complete = is_current and is_population_phase and vote_done and not resolved
        # Standard 4-condition pattern matching Mortality/Revenue/Forum/Senate/Combat
        can_advance = (
            current_phase_id == "population"
            and state.is_current_player(viewer_player_id)
            and not state.is_phase_executed("population")
            and bool(state.get_phase_result("population"))
        )

        # 字段级错误/禁用原因
        field_errors = {}
        if not is_current:
            field_errors["global"] = "不是你的回合"

        data = {
            "my_figures": my_figures,
            "candidates": candidates,
            "my_votes": my_votes,
            "my_campaigns": my_campaigns,
            "current_step": current_step,
            "resolved": resolved,
            "office_count": office_count,
            "campaign_done": campaign_done,
            "vote_done": vote_done,
            "election_results": result_data.get("election_results", []) if isinstance(result_data, dict) else [],
            "faction_influence_before": (
                result_data.get("faction_influence_before", _faction_influence_rows(state))
                if isinstance(result_data, dict) else _faction_influence_rows(state)
            ),
            "faction_influence_after": (
                result_data.get("faction_influence_after", _faction_influence_rows(state))
                if isinstance(result_data, dict) else _faction_influence_rows(state)
            ),
            "is_current_player": is_current,
            "current_phase_id": current_phase_id,
            "can_campaign": can_campaign,
            "can_vote": can_vote,
            "can_complete": can_complete,
            "can_advance": can_advance,
            "field_errors": field_errors,
        }
        return api_response(True, "Population view", data)
    except Exception as e:
        logger.exception("Population view failed")
        return api_response(False, f"Population view failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 4. 完成当前玩家操作
# ---------------------------------------------------------------------------

def complete_population_player(state: GameState, player_id: str) -> dict:
    """
    标记当前玩家完成人口阶段操作，切换到下一个玩家。
    """
    try:
        result = player_api.next_player(state, player_id)
        return result
    except Exception as e:
        logger.exception("Player completion failed")
        return api_response(False, f"Player completion failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 5. 人口阶段结算（选举结果）
# ---------------------------------------------------------------------------

def resolve_population_slice(state: GameState) -> dict:
    """
    结算人口阶段选举。所有玩家完成后调用。
    返回结构化选举结果，供 GUI 消费。
    """
    try:
        influence_before = _faction_influence_rows(state)
        # 先让 AI 自动完成（如果还有未完成的玩家）
        from src.ui.processors.auto_player_processor import AutoPlayerProcessor
        from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
        from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
        from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
        from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider
        from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
        from src.core.deciders.impl.auto_vote_decider import AutoVoteDecider
        auto = AutoPlayerProcessor(
            state,
            retirement_decider=AutoRetirementDecider(state),
            recruitment_decider=AutoRecruitmentDecider(),
            bid_decider=AutoBidDecider(),
            triumph_decider=AutoTriumphDecider(),
            festival_decider=AutoFestivalDecider(),
            vote_decider=AutoVoteDecider(),
        )
        while True:
            current = state.get_current_player()
            if not current or current.player_type.value != "human":
                faction = state.get_faction(current.faction_id) if current and current.faction_id else None
                auto.process_festival(current.player_id if current else "", faction, bypass_permission=True)
                auto.process_vote(current.player_id if current else "", faction, bypass_permission=True)
                state.next_player()
            else:
                break

        cand_result = population_api.get_candidates(state)
        candidates_before_resolve = cand_result.get("data", {}) if cand_result.get("success") else {}
        # 结算选举
        resolve_result = population_api.resolve_election(state)
        if not resolve_result:
            return api_response(False, "Election resolve returned None")

        raw_result = resolve_result.get("data", {}) or {}
        structured = raw_result.get("election_results") or _population_election_results_from_state(state)
        influence_after = _faction_influence_rows(state)
        data = {
            "election_results": structured,
            "candidates": candidates_before_resolve,
            "faction_influence_before": influence_before,
            "faction_influence_after": influence_after,
            "raw_result": raw_result,
        }

        # Two-step pattern: resolve records result, does NOT mark phase executed
        state.record_phase_result("population", {
            "success": True,
            "message": "Election resolved",
            "data": data,
        })
        logger.info("Population phase resolved", extra={"results": structured})
        return api_response(True, "Election resolved", data)
    except Exception as e:
        logger.exception("Population resolution failed")
        return api_response(False, f"Population resolution failed: {e}", errors=[str(e)])


# ---------------------------------------------------------------------------
# 6. 人口阶段推进
# ---------------------------------------------------------------------------

def advance_population_phase(state: GameState, viewer_player_id: str) -> dict:
    """Confirm population result and advance to Senate phase.

    Failure semantics:
    - If phase not yet resolved (no result) -> return failure, no state change
    - If not current player -> return failure, no state change
    - If already executed -> return failure, no duplicate state change
    - If current phase is not population -> return failure
    """
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    # Guard: phase not yet executed (prevents double-advance)
    if state.is_phase_executed("population"):
        return api_response(False, "Population phase already executed")

    # Guard: correct current phase
    current_phase_id = _infer_current_phase_id(state)
    if current_phase_id != "population":
        return api_response(False, f"Current phase is {current_phase_id}, not population")

    # Guard: active player check
    if not state.is_current_player(viewer_player_id):
        return api_response(False, "Viewer is not the active player")

    # Guard: result must exist (cannot advance unresolved phase)
    result = state.get_phase_result("population")
    if not result:
        return api_response(False, "Population phase has not been resolved")

    # Perform the advance (single state mutation point)
    state.mark_phase_executed("population")
    return api_response(True, "Population phase advanced", {
        "phase_executed": True,
        "next_phase_id": "senate",
        "result": result,
    })


# ---------------------------------------------------------------------------
# 7. 决算阶段视图
# ---------------------------------------------------------------------------

def get_resolution_view(state: GameState, viewer_player_id: str) -> dict:
    """
    返回决算阶段的只读视图 DTO。

    仅包含业务事实，不包含 Store 私有状态。
    can_advance / is_advancing 由 Store 组合，API 不返回。

    五步进度采用二态模型（resolve 前全部 pending → resolve 后全部 completed）。
    """
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        resolved = state.is_phase_executed("resolution")
        status = "completed" if resolved else "pending"

        # 五步进度（二态模型）
        step_definitions = [
            {"step": 1, "name": "governor_return", "display": "总督返回"},
            {"step": 2, "name": "contract_expiry", "display": "合同到期"},
            {"step": 3, "name": "risk_check", "display": "风险检查"},
            {"step": 4, "name": "annual_decay", "display": "年度衰减"},
            {"step": 5, "name": "next_year", "display": "推进下一年度"},
        ]
        step_statuses = [{**sd, "status": status} for sd in step_definitions]

        # 结算结果
        if resolved:
            results = _build_resolution_results(state)
        else:
            results = _empty_resolution_results()

        # 风险警告
        warnings = _build_resolution_warnings(state) if resolved else []

        # 年度总结
        if resolved:
            summary = _build_resolution_summary(state)
        else:
            summary = _empty_resolution_summary()

        data = {
            "resolved": resolved,
            "step_statuses": step_statuses,
            "results": results,
            "warnings": warnings,
            "summary": summary,
            "is_current_player": state.is_current_player(viewer_player_id),
        }
        return api_response(True, "Resolution view", data)
    except Exception as e:
        logger.exception("Resolution view failed")
        return api_response(False, f"Resolution view failed: {e}", errors=[str(e)])


def _build_resolution_results(state: GameState) -> dict:
    """从游戏状态提取结算结果。"""
    # 总督轮换记录 - 检查有候任总督的行省
    governor_transitions = []
    for province in state.get_all_provinces():
        desig_id = province.governor_designate_id
        if desig_id is not None:
            designate = state.get_member(desig_id)
            if designate:
                governor = state.get_member(province.governor_id)
                governor_transitions.append({
                    "province": province.name,
                    "governor": designate.get_formal_name(),
                    "old_governor": governor.get_formal_name() if governor else None,
                })

    # 合同到期数量
    expired_count = 0
    for contract in state.contracts:
        c_status = getattr(contract, "status", None)
        if c_status is not None:
            status_name = getattr(c_status, "name", str(c_status))
            if status_name == "EXPIRED":
                expired_count += 1

    # 和约到期（转为威胁的战争）
    truce_expired = []
    war_system = state.get_war_system()
    if war_system:
        threat_wars = war_system.get_threat_wars()
        truce_expired = [w.name for w in threat_wars]

    # 元老院主导派系
    total_influence = 0
    faction_infos = []
    for faction in state.factions.values():
        inf = 0
        for mid in faction.member_ids:
            member = state.get_member(mid)
            if member:
                inf += getattr(member, "influence", 0)
        total_influence += inf
        faction_infos.append({"id": faction.id, "name": faction.name, "influence": inf})

    dominant_faction = None
    if total_influence > 0 and faction_infos:
        top = max(faction_infos, key=lambda x: x["influence"])
        dominant_faction = {
            "id": top["id"],
            "name": top["name"],
            "influence_share": round(top["influence"] / total_influence, 4),
        }

    # 军团状态
    legion_status = "active"
    ms = state.get_military_system()
    if ms:
        all_legions = ms.get_all_legions()
        if all_legions and all(
            getattr(l, "status", None) is not None
            and getattr(l.status, "name", str(l.status)) == "DESTROYED"
            for l in all_legions
        ):
            legion_status = "destroyed"

    return {
        "governor_transitions": governor_transitions,
        "contracts_expired": expired_count,
        "truce_expired": truce_expired,
        "dominant_faction": dominant_faction,
        "treasury": state.treasury,
        "legion_status": legion_status,
    }


def _empty_resolution_results() -> dict:
    return {
        "governor_transitions": [],
        "contracts_expired": 0,
        "truce_expired": [],
        "dominant_faction": None,
        "treasury": 0,
        "legion_status": "unknown",
    }


def _build_resolution_warnings(state: GameState) -> list:
    """从当前游戏状态提取风险警告。"""
    warnings = []

    # 国库赤字检查
    if state.treasury < 0:
        level = "critical" if state.treasury <= -50 else "warning"
        warnings.append({
            "level": level,
            "message": f"国库赤字：{state.treasury} 第纳尔",
        })

    # 派系独裁风险检查
    total_inf = 0
    faction_infos = []
    for faction in state.factions.values():
        inf = 0
        for mid in faction.member_ids:
            member = state.get_member(mid)
            if member:
                inf += getattr(member, "influence", 0)
        total_inf += inf
        faction_infos.append({"name": faction.name, "influence": inf})

    if total_inf > 0:
        for fi in faction_infos:
            share = fi["influence"] / total_inf
            if share >= 0.7:
                warnings.append({
                    "level": "critical",
                    "message": f"{fi['name']} 影响力 {share:.1%}，独裁风险！",
                })
            elif share >= 0.5:
                warnings.append({
                    "level": "warning",
                    "message": f"{fi['name']} 影响力 {share:.1%}，接近绝对多数",
                })

    return warnings


def _build_resolution_summary(state: GameState) -> dict:
    """从游戏状态提取年度总结。"""
    # 元老院主导派系
    total_influence = 0
    faction_infos = []
    for faction in state.factions.values():
        inf = 0
        for mid in faction.member_ids:
            member = state.get_member(mid)
            if member:
                inf += getattr(member, "influence", 0)
        total_influence += inf
        faction_infos.append({"id": faction.id, "name": faction.name, "influence": inf})

    dominant = None
    if total_influence > 0 and faction_infos:
        top = max(faction_infos, key=lambda x: x["influence"])
        dominant = {
            "id": top["id"],
            "name": top["name"],
            "influence_share": round(top["influence"] / total_influence, 4),
        }

    # 年份显示
    current_year = state.turn.year if state.turn else 0
    next_year = current_year + 1
    next_year_display = _format_year(next_year)

    # 衰减状态
    decay_applied = resolved = state.is_phase_executed("resolution")

    return {
        "dominant_faction": dominant,
        "treasury": state.treasury,
        "next_year": next_year_display,
        "decay_applied": decay_applied,
        "decay_details": "影响力年度衰减已应用" if decay_applied else "",
        "current_year": _format_year(current_year),
    }


def _empty_resolution_summary() -> dict:
    return {
        "dominant_faction": None,
        "treasury": 0,
        "next_year": "",
        "decay_applied": False,
        "decay_details": "",
        "current_year": "",
    }


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _format_year(year: int) -> str:
    if year < 0:
        return f"{abs(year)} BC"
    return f"{year} AD"


def _phase_name(phase_id: str) -> str:
    return _phase_definition_map().get(phase_id, {}).get("name", phase_id)


def _phase_order() -> List[str]:
    return ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]


def _implemented_phase_ids() -> set:
    return {"mortality", "revenue", "forum", "population", "senate", "combat", "resolution"}


def _phase_interaction_mode(phase_id: str) -> str:
    if phase_id in {"mortality", "revenue", "forum", "population", "senate", "combat", "resolution"}:
        return "interactive"
    return "placeholder"


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in _phase_order():
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


def _faction_influence_rows(state: GameState) -> List[Dict[str, Any]]:
    rows = []
    for faction in state.factions.values():
        members = [m for m in state.get_living_members() if m.faction_id == faction.id]
        rows.append({
            "id": faction.id,
            "name": faction.name,
            "short_name": _faction_short_name(faction.name),
            "total_influence": sum(m.influence for m in members),
        })
    return rows


def _faction_short_name(name: str) -> str:
    mapping = {
        "Optimates": "Opt",
        "Populares": "Pop",
        "Equites": "Equ",
    }
    return mapping.get(name, name[:3])


def _population_election_results_from_state(state: GameState) -> List[Dict[str, Any]]:
    office_order = ["consul", "censor", "praetor", "quaestor", "tribune"]
    results: List[Dict[str, Any]] = []
    for office in office_order:
        winners = [
            fig for fig in state.get_living_members()
            if getattr(fig, "office", "") == office
        ]
        for winner in winners:
            faction = state.get_faction(winner.faction_id) if winner.faction_id else None
            results.append({
                "office": office,
                "office_name": _office_name(office),
                "figure_id": winner.id,
                "figure_name": winner.get_formal_name(),
                "faction_id": winner.faction_id,
                "faction_name": faction.name if faction else "",
                "faction_short_name": _faction_short_name(faction.name) if faction else "",
            })
    return results


def _office_name(office: str) -> str:
    names = {
        "consul": "执政官",
        "censor": "监察官",
        "praetor": "大法官",
        "quaestor": "财务官",
        "tribune": "保民官",
    }
    return names.get(office, office)


def _phase_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "id": "mortality",
            "name_key": "phase.mortality.name",
            "subtitle_key": "phase.mortality.subtitle",
            "description_key": "phase.mortality.description",
            "name": "天命",
            "subtitle": "死亡、继承与年度开端",
            "description": "抽取天命事件并应用死亡、丰收、和平、猛男或灾害等年度影响。",
            "handoff_task": "GUI-P0-02B",
        },
        {
            "id": "revenue",
            "name_key": "phase.revenue.name",
            "subtitle_key": "phase.revenue.subtitle",
            "description_key": "phase.revenue.description",
            "name": "收入",
            "subtitle": "国家收入、维护费与派系分配",
            "description": "GUI-P0-03 已实现收入结算切片。结算国家收入与支出，整理派系财政，确认国库变动。",
            "handoff_task": "GUI-P0-03",
        },
        {
            "id": "forum",
            "name_key": "phase.forum.name",
            "subtitle_key": "phase.forum.subtitle",
            "description_key": "phase.forum.description",
            "name": "广场",
            "subtitle": "招募、裁员、土地与公共行动",
            "description": "广场阶段将在 GUI-P0-02D 承接。本轮不执行广场业务操作。",
            "handoff_task": "GUI-P0-03",
        },
        {
            "id": "population",
            "name_key": "phase.population.name",
            "subtitle_key": "phase.population.subtitle",
            "description_key": "phase.population.description",
            "name": "人口",
            "subtitle": "庆典、公职投票与选举",
            "description": "GUI-P0-01 已实现的人口阶段真实切片，可继续举办庆典、投票并完成玩家操作。",
            "handoff_task": "GUI-P0-02B",
        },
        {
            "id": "senate",
            "name_key": "phase.senate.name",
            "subtitle_key": "phase.senate.subtitle",
            "description_key": "phase.senate.description",
            "name": "元老院",
            "subtitle": "执政官提案 → 元老院表决 → 保民官否决",
            "description": "执政官提案 → 元老院表决 → 保民官否决 → 法案公示与政府运作。",
            "handoff_task": "GUI-P0-02C",
        },
        {
            "id": "combat",
            "name_key": "phase.combat.name",
            "subtitle_key": "phase.combat.subtitle",
            "description_key": "phase.combat.description",
            "name": "战争",
            "subtitle": "陆战、海战与战役结果",
            "description": "战争阶段将在 GUI-P0-02E 承接。海战信息将在该阶段后续切片中呈现，本轮不执行战争结算。",
            "handoff_task": "GUI-P0-02E",
        },
        {
            "id": "resolution",
            "name_key": "phase.resolution.name",
            "subtitle_key": "phase.resolution.subtitle",
            "description_key": "phase.resolution.description",
            "name": "决算",
            "subtitle": "革命检查、年度决算与回合推进",
            "description": "决算阶段将在 GUI-P0-02F 承接。革命检查保留为后续决算切片内容，本轮不推进回合。",
            "handoff_task": "GUI-P0-02F",
        },
    ]


def _phase_definition_map() -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in _phase_definitions()}


def _build_phase_navigation(state: GameState, current_phase_id: str, viewer_player_id: str) -> List[Dict[str, Any]]:
    phase_nav = []
    for index, definition in enumerate(_phase_definitions(), start=1):
        phase_id = definition["id"]
        implemented = phase_id in _implemented_phase_ids()
        interaction_mode = _phase_interaction_mode(phase_id)
        current = phase_id == current_phase_id
        actionable = interaction_mode == "interactive" and current and state.is_current_player(viewer_player_id)
        disabled_reason = ""
        disabled_reason_key = ""
        if not implemented:
            disabled_reason_key = "phase.disabled.placeholder"
            disabled_reason = f"{definition['handoff_task']} 后续任务承接，当前暂不可操作"
        elif interaction_mode == "readonly":
            disabled_reason_key = "phase.disabled.readonly"
            disabled_reason = "当前不是元老院阶段或当前行动玩家，暂不可操作"
        elif not current:
            disabled_reason_key = "phase.disabled.not_current"
            disabled_reason = "该阶段不是当前阶段，暂不可操作"
        elif not state.is_current_player(viewer_player_id):
            disabled_reason_key = "phase.disabled.not_player"
            disabled_reason = "当前 viewer 不是行动玩家，暂不可操作"
        phase_nav.append({
            "id": phase_id,
            "index": index,
            "name_key": definition["name_key"],
            "subtitle_key": definition["subtitle_key"],
            "description_key": definition["description_key"],
            "status_key": "phase.status.current" if current else ("phase.status.completed" if state.is_phase_executed(phase_id) else "phase.status.placeholder"),
            "name": definition["name"],
            "subtitle": definition["subtitle"],
            "description": definition["description"],
            "status": "current" if current else ("completed" if state.is_phase_executed(phase_id) else "placeholder"),
            "implemented": implemented,
            "interaction_mode": interaction_mode,
            "enabled": True,
            "actionable": actionable,
            "handoff_task": definition["handoff_task"],
            "disabled_reason_key": disabled_reason_key,
            "disabled_reason": disabled_reason,
            "locked_reason": "" if implemented else f"{definition['name']}阶段尚未迁移到 GUI",
            "executed": state.is_phase_executed(phase_id),
            "current": current,
            "locked": False,
        })
    return phase_nav


def _build_phase_summary(phase_id: str, state: Optional[GameState] = None, viewer_player_id: str = "") -> Dict[str, Any]:
    definition = _phase_definition_map().get(phase_id, {})
    implemented = phase_id in _implemented_phase_ids()
    interaction_mode = _phase_interaction_mode(phase_id)
    current = state is not None and phase_id == _infer_current_phase_id(state)
    actionable = bool(
        interaction_mode == "interactive"
        and current
        and viewer_player_id
        and state
        and state.is_current_player(viewer_player_id)
    )
    disabled_reason = ""
    disabled_reason_key = ""
    if not implemented:
        disabled_reason_key = "phase.disabled.placeholder"
        disabled_reason = f"{definition.get('handoff_task', '后续任务')} 承接，本轮不会改变游戏状态"
    elif interaction_mode == "readonly":
        disabled_reason_key = "phase.disabled.readonly"
        disabled_reason = "当前不是元老院阶段或当前行动玩家，暂不可操作"
    elif not current:
        disabled_reason_key = "phase.disabled.not_current"
        disabled_reason = "该阶段不是当前阶段，暂不可操作"
    elif state and viewer_player_id and not state.is_current_player(viewer_player_id):
        disabled_reason_key = "phase.disabled.not_player"
        disabled_reason = "当前 viewer 不是行动玩家，暂不可操作"
    return {
            "id": phase_id,
            "name_key": definition.get("name_key", ""),
            "subtitle_key": definition.get("subtitle_key", ""),
            "description_key": definition.get("description_key", ""),
            "status_key": "phase.status.actionable" if actionable else (
                "phase.status.readonly" if interaction_mode == "readonly" else (
                    "phase.status.ready" if implemented else "phase.status.placeholder"
                )
            ),
            "disabled_reason_key": disabled_reason_key,
            "name": definition.get("name", phase_id),
            "subtitle": definition.get("subtitle", ""),
            "description": definition.get("description", ""),
        "implemented": implemented,
        "interaction_mode": interaction_mode,
        "actionable": actionable,
        "handoff_task": definition.get("handoff_task", ""),
        "status_text": "可操作真实切片" if actionable else (
            "已接入只读 / 后续子任务接入操作" if interaction_mode == "readonly" else (
                "已接入 / 等待正确阶段或玩家" if implemented else "后续任务承接 / 暂不可操作"
            )
        ),
        "disabled_reason": disabled_reason,
    }


def _build_global_warnings(state: GameState, viewer_player_id: str) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = [{
        "type": "info",
        "key": "warning.gui_p0_05.senate_phase5a",
        "message": "GUI-P0-05 已开放元老院 Phase 5A 执政官提案；表决、否决与结算按子环节逐步验收。",
    }]
    if not state.is_current_player(viewer_player_id):
        warnings.append({
            "type": "warning",
            "key": "warning.viewer.not_current_player",
            "message": "当前 viewer 不是行动玩家，操作入口将保持受限。",
        })
    return warnings


def _build_available_actions(state: GameState, viewer_player_id: str) -> List[str]:
    """当前玩家可执行的动作列表"""
    if not state.is_current_player(viewer_player_id):
        return []
    actions = []
    current_phase_id = _infer_current_phase_id(state)
    if current_phase_id == "mortality" and not state.is_phase_executed("mortality"):
        actions.append("execute_mortality")
    if current_phase_id == "population" and not state.is_phase_executed("population"):
        actions.append("campaign")
        actions.append("vote")
        actions.append("complete_player")
    if current_phase_id == "forum" and not state.is_phase_executed("forum"):
        actions.append("retire_figure")
        actions.append("recruit_figure")
        actions.append("place_bid")
        actions.append("buy_land")
        actions.append("vote_triumph")
        actions.append("resolve_forum")
    return actions


def _build_population_progress(state: GameState, viewer_player_id: str) -> dict:
    """人口阶段进度"""
    votes = state.get_population_votes()
    my_votes = [v for v in votes if v[0] == viewer_player_id]
    campaigns = state.get_population_campaigns()
    my_campaigns = [c for c in campaigns if c[0] == viewer_player_id]
    return {
        "campaigns_done": len(my_campaigns),
        "votes_done": len(my_votes),
        "total_offices": 5,
    }
