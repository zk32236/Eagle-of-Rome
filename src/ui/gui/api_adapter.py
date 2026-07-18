"""
src/ui/gui/api_adapter.py
GuiApiAdapter — 统一负责 API 调用、响应验证、错误映射和状态刷新。
"""
import logging
import traceback
from typing import Any, Callable, Dict, List, Optional

from src.core.game_state import GameState

logger = logging.getLogger("EOR-GUI")


class GuiApiAdapter:
    """
    GUI API 适配器。
    - 调用 API 函数
    - 验证 {success, message, data, errors}
    - 将成功/失败/异常映射为结构化反馈
    - 成功操作后重新请求权威快照
    - 失败后不污染 Core 状态
    """

    def __init__(self, state: GameState, refresh_callback: Optional[Callable] = None):
        self._state = state
        self._refresh_callback = refresh_callback

    # -----------------------------------------------------------------------
    # 通用调用包装
    # -----------------------------------------------------------------------
    def call(self, api_func, *args, **kwargs) -> Dict[str, Any]:
        """
        调用 API 函数，统一处理返回格式和异常。
        返回结构化反馈字典:
        {
            "success": bool,
            "message": str,
            "data": Any,
            "errors": List[str],
            "feedback_type": str,  # "success" | "error" | "warning" | "info"
            "feedback_message": str,
        }
        """
        try:
            result = api_func(*args, **kwargs)
            if not isinstance(result, dict):
                return self._build_feedback(
                    False, f"API returned non-dict: {type(result)}", [], "error"
                )

            success = result.get("success", False)
            message = result.get("message", "")
            data = result.get("data")
            errors = result.get("errors", []) or []

            if success:
                feedback_type = "success"
                feedback_message = message or "操作成功"
            else:
                feedback_type = "error"
                feedback_message = message or "操作失败"
                if errors:
                    feedback_message += f" [{'; '.join(errors)}]"

            feedback = self._build_feedback(
                success, message, errors, feedback_type, feedback_message, data
            )

            # 成功后触发快照刷新
            if success and self._refresh_callback:
                self._refresh_callback()

            return feedback

        except Exception as e:
            logger.exception(f"API call exception: {api_func.__name__}")
            traceback_str = traceback.format_exc()
            return self._build_feedback(
                False, f"API exception: {e}", [traceback_str], "error"
            )

    # -----------------------------------------------------------------------
    # 人口阶段专用 API
    # -----------------------------------------------------------------------
    def campaign(self, player_id: str, figure_id: int, amount: int) -> Dict[str, Any]:
        from src.api import population_api
        return self.call(
            population_api.campaign,
            self._state, player_id, figure_id, amount
        )

    def vote(self, player_id: str, office: str, figure_id: int) -> Dict[str, Any]:
        from src.api import population_api
        return self.call(
            population_api.vote,
            self._state, player_id, office, figure_id
        )

    def next_player(self, player_id: str) -> Dict[str, Any]:
        from src.api import player_api
        return self.call(player_api.next_player, self._state, player_id)

    def resolve_election(self) -> Dict[str, Any]:
        from src.api import session_api
        return self.call(session_api.resolve_population_slice, self._state)

    def advance_population(self, player_id: str) -> Dict[str, Any]:
        from src.api import session_api
        return self.call(session_api.advance_population_phase, self._state, player_id)

    # -----------------------------------------------------------------------
    # 天命阶段专用 API
    # -----------------------------------------------------------------------
    def execute_mortality(self, player_id: str) -> Dict[str, Any]:
        from src.api import mortality_api
        return self.call(mortality_api.execute_mortality_phase, self._state, player_id)

    def advance_mortality(self, player_id: str) -> Dict[str, Any]:
        from src.api import mortality_api
        return self.call(mortality_api.advance_mortality_phase, self._state, player_id)

    # -----------------------------------------------------------------------
    # 收入阶段专用 API
    # -----------------------------------------------------------------------
    def get_revenue_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import revenue_api
        result = revenue_api.get_revenue_view(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Revenue view failed: {result.get('message')}")
        return {}

    def settle_revenue(self, player_id: str) -> Dict[str, Any]:
        from src.api import revenue_api
        return self.call(revenue_api.execute_revenue_phase, self._state, player_id)

    def advance_revenue(self, player_id: str) -> Dict[str, Any]:
        from src.api import revenue_api
        return self.call(revenue_api.advance_revenue_phase, self._state, player_id)

    def get_forum_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import forum_api
        result = forum_api.get_forum_view(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Forum view failed: {result.get('message')}")
        return {}

    def retire_figure(self, player_id: str, figure_id: int) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(forum_api.retire_figure, self._state, player_id, figure_id)

    def open_forum_market(self, player_id: str) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(forum_api.open_market, self._state, player_id)

    def recruit_figure(self, player_id: str, figure_id: int, amount: int) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(forum_api.recruit_figure, self._state, player_id, figure_id, amount)

    def place_bid(
        self,
        player_id: str,
        figure_id: int,
        contract_id: int,
        amount: int,
        profit_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(
            forum_api.place_bid,
            self._state,
            player_id,
            figure_id,
            contract_id,
            amount,
            profit_rate,
        )

    def buy_land(self, player_id: str, figure_id: int, amount: int) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(forum_api.buy_land, self._state, player_id, figure_id, amount)

    def vote_triumph(self, player_id: str, war_id: str, vote: bool) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(forum_api.vote_triumph, self._state, player_id, war_id, vote)

    def resolve_forum(self) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(forum_api.resolve_forum, self._state)

    def advance_forum(self, player_id: str) -> Dict[str, Any]:
        from src.api import forum_api
        return self.call(forum_api.advance_forum_phase, self._state, player_id)

    # -----------------------------------------------------------------------
    # Session API 包装
    # -----------------------------------------------------------------------
    def get_snapshot(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import session_api
        result = session_api.get_session_snapshot(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Snapshot failed: {result.get('message')}")
        return {}

    def get_population_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import session_api
        result = session_api.get_population_view(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Population view failed: {result.get('message')}")
        return {}

    def get_mortality_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import mortality_api
        result = mortality_api.get_mortality_view(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Mortality view failed: {result.get('message')}")
        return {}

    def get_senate_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import senate_api
        result = senate_api.get_senate_view(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Senate view failed: {result.get('message')}")
        return {}

    def submit_senate_proposals(self, player_id: str, proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
        from src.api import senate_api
        return self.call(senate_api.propose_many, self._state, player_id, proposals)

    def submit_senate_votes(self, player_id: str, proposal_ids: List[int], votes: List[bool]) -> Dict[str, Any]:
        from src.api import senate_api
        return self.call(senate_api.vote, self._state, player_id, proposal_ids, votes)

    def submit_senate_vetoes(self, player_id: str, proposal_ids: List[int]) -> Dict[str, Any]:
        from src.api import senate_api
        return self.call(senate_api.veto, self._state, player_id, proposal_ids)

    def apply_auto_senate_vetoes(self) -> Dict[str, Any]:
        from src.api import senate_api
        return self.call(senate_api.apply_auto_tribune_vetoes, self._state)

    def resolve_senate(self) -> Dict[str, Any]:
        from src.api import senate_api
        feedback = self.call(senate_api.resolve_senate, self._state)
        # Phase result is now recorded inside senate_api.resolve_senate()
        return feedback

    def advance_senate(self, player_id: str) -> Dict[str, Any]:
        from src.api import senate_api
        return self.call(senate_api.advance_senate_phase, self._state, player_id)

    # -----------------------------------------------------------------------
    # Combat stage API
    # -----------------------------------------------------------------------
    def get_combat_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import combat_api
        result = combat_api.get_combat_view(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Combat view failed: {result.get('message')}")
        return {}

    def do_combat_action(self, player_id: str, war_id: str, action: str) -> Dict[str, Any]:
        from src.api import combat_api
        return self.call(combat_api.do_combat_action, self._state, player_id, war_id, action)

    def confirm_battle_result(self, player_id: str) -> Dict[str, Any]:
        from src.api import combat_api
        return self.call(combat_api.confirm_battle_result, self._state, player_id)

    def advance_combat(self, player_id: str) -> Dict[str, Any]:
        from src.api import combat_api
        return self.call(combat_api.advance_combat, self._state, player_id)

    def get_global_query_result(self, viewer_id: str, query_id: str) -> Dict[str, Any]:
        from src.api import gui_query_api
        result = gui_query_api.get_global_query_result(self._state, viewer_id, query_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Global query failed: {result.get('message')}")
        return {
            "id": query_id,
            "title": query_id,
            "title_key": query_id,
            "status": "placeholder",
            "message": result.get("message", ""),
            "message_key": "query.error",
            "message_params": {},
            "items": [],
            "summary": {},
            "errors": result.get("errors", []),
        }

    def auto_resolve_combat(self, player_id: str) -> dict:
        """Auto-resolve all active wars for AI players."""
        from src.api import combat_api
        try:
            combat_view = self.get_combat_view(player_id)
            active_wars = combat_view.get("active_wars", []) if isinstance(combat_view, dict) else []

            if not active_wars:
                return {
                    "success": True,
                    "message": "No active wars to resolve",
                    "feedback_type": "info",
                    "feedback_message": "没有活跃的战争",
                }

            for war_card in active_wars:
                war_id = war_card["war_id"]
                select_result = combat_api.select_war(self._state, player_id, war_id)
                if not select_result.get("success"):
                    continue
                action_result = combat_api.do_combat_action(
                    self._state, player_id, war_id, "attack", auto=True
                )
                if not action_result.get("success"):
                    continue
                combat_api.confirm_battle_result(self._state, player_id)

            advance_result = combat_api.advance_combat(self._state, player_id)

            if advance_result.get("success") and self._refresh_callback:
                self._refresh_callback()

            return advance_result
        except Exception as exc:
            logger.exception("auto_resolve_combat failed")
            return {
                "success": False,
                "message": f"Auto-resolve combat failed: {exc}",
                "errors": [str(exc)],
                "feedback_type": "error",
                "feedback_message": f"自动战斗失败: {exc}",
            }

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------
    def _build_feedback(
        self,
        success: bool,
        message: str,
        errors: List[str],
        feedback_type: str,
        feedback_message: str = "",
        data: Any = None,
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "message": message,
            "data": data,
            "errors": errors,
            "feedback_type": feedback_type,
            "feedback_message": feedback_message or message,
        }
