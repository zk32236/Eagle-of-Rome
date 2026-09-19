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

    LEGACY_ERROR_CODE = "LEGACY_ERROR"
    UNKNOWN_ERROR_CODE = "UNKNOWN_ERROR"

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
        refresh_error: str = ""
        error_items: List[Dict[str, Any]] = []
        errors_by_scope: Dict[str, List[Dict[str, Any]]] = {}
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
                # R6（SA §B.5，DA-2 B5）：**唯一** structured error formatter。
                # 替换 baseline `'; '.join(errors)`（= N3 崩溃点：errors 为 list[dict]
                # 时 join 抛 TypeError）。dict / legacy str / 未知类型三态一律安全。
                normalized = self.normalize_error_feedback(errors, message or "操作失败")
                feedback_message = normalized["feedback_message"]
                error_items = normalized["error_items"]
                errors_by_scope = normalized["errors_by_scope"]

            feedback = self._build_feedback(
                success, message, errors, feedback_type, feedback_message, data,
                error_items=error_items, errors_by_scope=errors_by_scope,
            )

        except Exception as e:
            logger.exception(f"API call exception: {api_func.__name__}")
            traceback_str = traceback.format_exc()
            return self._build_feedback(
                False, f"API exception: {e}", [traceback_str], "error"
            )

        # R6（SA §B.3，DA-2 B5）：**Adapter API 调用异常与 refresh 异常分离捕获**。
        # baseline 把 refresh 放在同一 try 内 → refresh 异常被伪报为「API 失败」。
        # 提交后 refresh / PA 格式化失败**不反转**已成功的 API 结果，只降级 warning。
        if success and self._refresh_callback:
            try:
                self._refresh_callback()
            except Exception as e:  # pragma: no cover - defensive
                logger.exception("API refresh callback exception")
                refresh_error = str(e)
                feedback["refresh_error"] = refresh_error
                feedback["feedback_type"] = "warning"
                feedback["feedback_message"] = (
                    (feedback.get("feedback_message") or "") + f"（刷新失败：{e}）"
                )

        return feedback

    # -----------------------------------------------------------------------
    # R6（SA §B.5，DA-2 B5）：**唯一** structured error formatter
    # -----------------------------------------------------------------------
    @classmethod
    def normalize_error_feedback(cls, errors, base_message: str = "") -> Dict[str, Any]:
        """将 Core `_error` 结构化错误（或 legacy 字符串）归一为 GUI 可消费反馈。

        权威 machine schema = Core `{code, scope, field, details, message}`
        （`political_system._error`）。本方法为 GUI 侧**唯一**显示路径（QML 不再各写
        dict formatter）。

        - **dict**：保留五字段与 `details` 原值；`message` 缺失 → `code` + 安全 fallback；
          **绝不** stringify dict 代替可用反馈。
        - **legacy str**：安全包装为 `{code: LEGACY_ERROR, scope: "package", field: None,
          details: {raw: text}, message: text}`；raw 原文保留用于兼容。
        - **未知类型**：受限 fallback（`UNKNOWN_ERROR`），**不抛 TypeError**。

        输出：`error_items`（规范排序 `(code, str(scope), str(field))` 的 dict 列表）/\
`feedback_message`（可读摘要）/ `errors_by_scope`（`scope → items`；`scope=package`
        的 item 若 `details.claims` / `details.requests` 含 `war_id` → 另建 `war:<id>`
        桶 = 相关卡关联；`scope=war_id` 直接定位该卡）。`package` 桶始终存在。
        """
        if isinstance(errors, (list, tuple)):
            raw_items = list(errors)
        elif errors:
            raw_items = [errors]
        else:
            raw_items = []

        items: List[Dict[str, Any]] = [cls._normalize_one_error(raw) for raw in raw_items]
        items.sort(key=lambda e: (str(e.get("code", "")), str(e.get("scope", "")),
                                  str(e.get("field", ""))))

        by_scope: Dict[str, List[Dict[str, Any]]] = {"package": []}
        for item in items:
            scope_key = str(item.get("scope") or "package")
            by_scope.setdefault(scope_key, []).append(item)
            if scope_key == "package":
                for war_id in cls._related_war_ids(item):
                    bucket = by_scope.setdefault(f"war:{war_id}", [])
                    if item not in bucket:
                        bucket.append(item)

        summary_parts: List[str] = []
        for item in items:
            prefix = str(item.get("code") or cls.UNKNOWN_ERROR_CODE)
            field = item.get("field")
            if field:
                prefix += f"·{field}"
            message = item.get("message") or ""
            summary_parts.append(f"{prefix}: {message}" if message else prefix)
        summary = "; ".join(summary_parts)

        if base_message:
            feedback_message = f"{base_message} [{summary}]" if summary else base_message
        else:
            feedback_message = summary or "操作失败"

        return {"error_items": items, "feedback_message": feedback_message,
                "errors_by_scope": by_scope}

    @classmethod
    def _normalize_one_error(cls, raw) -> Dict[str, Any]:
        """单条错误归一（dict / str / 未知类型三态；永不抛 TypeError）。"""
        if isinstance(raw, dict):
            code = raw.get("code") or cls.UNKNOWN_ERROR_CODE
            scope = raw.get("scope") or "package"
            field = raw.get("field")
            details = raw.get("details")
            if not isinstance(details, dict):
                details = {} if details is None else {"value": details}
            message = raw.get("message") or ""
            if not message:
                message = str(code) + (f"（{field}）" if field else "")
            return {"code": str(code), "scope": str(scope), "field": field,
                    "details": details, "message": str(message)}
        if isinstance(raw, str):
            return {"code": cls.LEGACY_ERROR_CODE, "scope": "package", "field": None,
                    "details": {"raw": raw}, "message": raw}
        text = "" if raw is None else str(raw)
        return {"code": cls.UNKNOWN_ERROR_CODE, "scope": "package", "field": None,
                "details": {"raw": text}, "message": text or cls.UNKNOWN_ERROR_CODE}

    @staticmethod
    def _related_war_ids(item: Dict[str, Any]) -> List[str]:
        """从 package scope item 的 `details.claims` / `details.requests` 抽取 war_id。"""
        out: List[str] = []
        details = item.get("details") or {}
        for key in ("claims", "requests"):
            rows = details.get(key)
            if not isinstance(rows, (list, tuple)):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                war_id = row.get("war_id")
                if war_id is None:
                    continue
                text = str(war_id)
                if text not in out:
                    out.append(text)
        return out

    # -----------------------------------------------------------------------
    # 人口阶段专用 API
    # -----------------------------------------------------------------------
    def campaign(self, player_id: str, figure_id: int, amount: int) -> Dict[str, Any]:
        from src.api import population_api
        return self.call(
            population_api.campaign,
            self._state, player_id, figure_id, amount
        )

    def batch_campaign(self, player_id: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        from src.api import population_api
        return self.call(
            population_api.batch_campaign,
            self._state, player_id, entries
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

    def all_human_population_votes_complete(self) -> bool:
        """Delegate to session_api._all_human_population_votes_complete."""
        from src.api import session_api
        return session_api._all_human_population_votes_complete(self._state)

    def advance_population(self, player_id: str) -> Dict[str, Any]:
        from src.api import session_api
        return self.call(session_api.advance_population_phase, self._state, player_id)

    def submit_population_votes(self, player_id: str, selections: Dict[str, int]) -> Dict[str, Any]:
        """Delegate the WP-02b fixed-five vote submission use case."""
        from src.api import session_api
        return self.call(session_api.submit_population_votes, self._state, player_id, selections)

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
        construction_cost: Optional[int] = None,
    ) -> Dict[str, Any]:
        from src.api import forum_api
        # R3-G-03（§3.5）：可选 construction_cost keyword 原样透传（Fleet C+D 双输入）
        return self.call(
            forum_api.place_bid,
            self._state,
            player_id,
            figure_id,
            contract_id,
            amount,
            profit_rate,
            construction_cost=construction_cost,
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

    def execute_forum(self, player_id: str) -> Dict[str, Any]:
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

    # R5（SA §5.2 C-M08，DA-4）：takeover_war / continue_war 绑定已退役——Human/AI/CLI
    # 统一经 submit_senate_proposals（propose_many）；无旁路直接部署入口。

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

    # -----------------------------------------------------------------------
    # Resolution stage API
    # -----------------------------------------------------------------------
    def get_resolution_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import session_api
        result = session_api.get_resolution_view(self._state, viewer_id)
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Resolution view failed: {result.get('message')}")
        return {}

    def execute_phase(self, phase_id: str, player_id: str) -> Dict[str, Any]:
        from src.api.game_api import execute_phase as _exec_phase
        return self.call(_exec_phase, self._state, phase_id, player_id)

    def advance_year(self, player_id: str) -> Dict[str, Any]:
        from src.api import game_api
        return self.call(game_api.advance_year, self._state, player_id)

    def auto_resolve_combat(self, player_id: str) -> dict:
        """
        S1 共享用例：自动结算所有活跃战争。
        委托给 combat_api.auto_resolve_combat()，Adapter 不再保留 for-loop。
        """
        from src.api import combat_api
        return self.call(combat_api.auto_resolve_combat, self._state, player_id)

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
        error_items: Optional[List[Dict[str, Any]]] = None,
        errors_by_scope: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "message": message,
            "data": data,
            "errors": errors,
            "feedback_type": feedback_type,
            "feedback_message": feedback_message or message,
            # R6（SA §B.5，DA-2 B5）：structured error 唯一显示路径（QML 零 formatter）。
            "error_items": error_items or [],
            "errors_by_scope": errors_by_scope or {},
        }
