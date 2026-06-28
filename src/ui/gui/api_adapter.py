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
        from src.api import population_api
        return self.call(population_api.resolve_election, self._state)

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
