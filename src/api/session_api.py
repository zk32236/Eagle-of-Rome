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

def create_gui_prototype_session(config_path: Optional[str] = None) -> dict:
    """
    创建 GUI 原型会话。
    使用 gui_prototype.json 场景，并标记 forum 为已完成，直接进入人口阶段。
    """
    try:
        state = GameState(config_path)
        ScenarioLoader.load_scenario(state, "gui_prototype.json")

        # 标记前置阶段已完成，直接进入人口阶段
        state.mark_phase_executed("mortality")
        state.mark_phase_executed("revenue")
        state.mark_phase_executed("forum")

        # 设置当前玩家为第一个 HUMAN 玩家
        human_players = [
            p.player_id for p in state.get_all_players()
            if p.player_type.value == "human"
        ]
        if human_players:
            state.set_current_player(human_players[0])
            state.set_turn_order(human_players)

        logger.info("GUI prototype session created", extra={
            "players": human_players,
            "current_player": state._current_player_id
        })
        return api_response(True, "GUI prototype session created", {
            "state": state,
            "human_players": human_players,
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

        # 七阶段导航状态
        phase_order = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]
        phase_nav = []
        for i, ph in enumerate(phase_order):
            phase_nav.append({
                "id": ph,
                "index": i + 1,
                "name": _phase_name(ph),
                "executed": state.is_phase_executed(ph),
                "current": (ph == "population"),  # 本轮固定为人口阶段
                "locked": False if ph == "population" else not state.is_phase_executed(ph) and ph != "population",
            })

        # 当前可执行动作
        actions = _build_available_actions(state, viewer_player_id)

        # 人口阶段进度
        population_progress = _build_population_progress(state, viewer_player_id)

        data = {
            "current_player_id": current_player.player_id if current_player else None,
            "viewer_player_id": viewer_player_id,
            "viewer_faction_id": viewer.faction_id,
            "is_current_player": state.is_current_player(viewer_player_id),
            "public_resources": public_resources,
            "faction_resources": faction_resources,
            "my_figures": my_figures,
            "phase_navigation": phase_nav,
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
        can_campaign = is_current and len(my_campaigns) < len(my_figures)
        can_vote = is_current
        can_complete = is_current

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
    names = {
        "mortality": "天命",
        "revenue": "收入",
        "forum": "广场",
        "population": "人口",
        "senate": "元老院",
        "combat": "战斗",
        "resolution": "决算",
    }
    return names.get(phase_id, phase_id)


def _build_available_actions(state: GameState, viewer_player_id: str) -> List[str]:
    """当前玩家可执行的动作列表"""
    if not state.is_current_player(viewer_player_id):
        return []
    actions = []
    if not state.is_phase_executed("population"):
        actions.append("campaign")
        actions.append("vote")
        actions.append("complete_player")
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
