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
        can_campaign = is_current and is_population_phase and len(my_campaigns) < len(my_figures)
        can_vote = is_current and is_population_phase
        can_complete = is_current and is_population_phase

        # 字段级错误/禁用原因
        field_errors = {}
        if not is_current:
            field_errors["global"] = "不是你的回合"

        data = {
            "my_figures": my_figures,
            "candidates": candidates,
            "my_votes": my_votes,
            "my_campaigns": my_campaigns,
            "is_current_player": is_current,
            "current_phase_id": current_phase_id,
            "can_campaign": can_campaign,
            "can_vote": can_vote,
            "can_complete": can_complete,
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

        # 结算选举
        resolve_result = population_api.resolve_election(state)
        if not resolve_result:
            return api_response(False, "Election resolve returned None")

        # 将结果结构化
        structured = []
        if resolve_result.get("success") and resolve_result.get("data"):
            for item in resolve_result.get("data", []):
                if isinstance(item, dict):
                    structured.append({
                        "office": item.get("office", ""),
                        "figure_id": item.get("figure_id", 0),
                        "figure_name": item.get("figure_name", ""),
                        "faction_id": item.get("faction_id", ""),
                        "faction_name": item.get("faction_name", ""),
                    })

        state.mark_phase_executed("population")
        logger.info("Population phase resolved", extra={"results": structured})
        return api_response(True, "Election resolved", {"election_results": structured})
    except Exception as e:
        logger.exception("Population resolution failed")
        return api_response(False, f"Population resolution failed: {e}", errors=[str(e)])


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
    return {"mortality", "revenue", "forum", "population", "senate"}


def _phase_interaction_mode(phase_id: str) -> str:
    if phase_id == "senate":
        return "readonly"
    if phase_id in {"mortality", "revenue", "forum", "population"}:
        return "interactive"
    return "placeholder"


def _infer_current_phase_id(state: GameState) -> str:
    for phase_id in _phase_order():
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


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
            "subtitle": "提案、表决与国家决议",
            "description": "元老院阶段将在 GUI-P0-02C 承接。本轮不执行提案或表决业务。",
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
            disabled_reason = "元老院已接入只读；提案、投票与结算由 GUI-P0-02C 后续子任务承接"
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
        disabled_reason = "元老院已接入只读；提案、投票与结算由 GUI-P0-02C 后续子任务承接"
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
        "key": "warning.gui_p0_02c_1.readonly_senate",
        "message": "GUI-P0-02C-1 接入元老院只读状态；收入、广场、战争、决算仍为占位。",
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
