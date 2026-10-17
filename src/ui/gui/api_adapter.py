"""
src/ui/gui/api_adapter.py
GuiApiAdapter — 统一负责 API 调用、响应验证、错误映射和状态刷新。
"""
import logging
import traceback
from typing import Any, Callable, Dict, List, Optional

from src.core.game_state import GameState
from src.api import session_access

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

    # Fixed safe failure enum (A3/F6). A malformed/legacy failure envelope may
    # only be forwarded after its first error code is validated against this set;
    # otherwise it is rebuilt as the fixed safe ``query_failed`` shell.
    _SAFE_FAILURE_CODES = frozenset({
        "state_unavailable",
        "viewer_unavailable",
        "unknown_query",
        "invalid_request",
        "system_unavailable",
        "record_unavailable",
        "query_failed",
        "query_unavailable",
        "not_implemented",
    })

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

        # S-B-R3a (DG-01): the Adapter is the TRUSTED routing layer. It obtains the
        # current service-issued handle from the session service and PRESENTS it
        # explicitly to the boundary; the boundary never fetches it off ``state``.
        caller_context = session_access.current_caller_context(self._state)

        # S-B Group 1: state-mutating API boundary guard. Every mutating GUI call
        # is routed through here; reads use the get_* methods directly. A
        # registered Hot-seat session denies a mutation unless the authoritative
        # current actor is the HUMAN principal (ACTIVE lifecycle), so a
        # non-current/unauthorized command never reaches the API and the source
        # state is NOT mutated. The structured refusal envelope is preserved (the
        # caller keeps a typed failure rather than a successful empty result);
        # un-registered CLI/historical states keep the historical behaviour.
        denied = session_access.denied_or_none(
            self._state, session_access.OP_MUTATE,
            command=getattr(api_func, "__name__", None),
            caller_context=caller_context)
        if denied is not None:
            normalized = self.normalize_error_feedback(
                denied.get("errors", []), denied.get("message", ""))
            return self._build_feedback(
                False, denied.get("message", ""), denied.get("errors", []),
                "error", feedback_message=normalized["feedback_message"],
                error_items=normalized["error_items"],
                errors_by_scope=normalized["errors_by_scope"])

        try:
            # Present the handle to the boundary (only if it accepts one).
            if caller_context is not None:
                kwargs.setdefault("caller_context", caller_context)
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
            # S1/FC-712-01: the typed delivery envelope is preserved verbatim (no
            # flattening / no guessed receiver). Consumers validate it against the
            # REAL coordinator/Core facts; the Adapter adds no authority.
            if success and isinstance(data, dict) \
                    and isinstance(data.get("delivery"), dict):
                feedback["delivery"] = data["delivery"]

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
    # S-C grContinuationRecover — bounded continuation recovery (AI-drain only)
    # -----------------------------------------------------------------------
    def recover_continuation(self, viewer_id: str) -> Dict[str, Any]:
        """Route ``grContinuationRecover`` → owner-layer recovery entry (R-02).

        The route goes through ``self.call(...)`` so the Adapter's S-B guard /
        authority path is preserved. The owner entry
        (``session_api.recover_continuation``) supplies the phase-specific AI
        executor, so the recovery ACTUALLY resumes only the outstanding
        scheduled-AI work (mirroring the forward ``submit_population_votes``
        wiring) instead of returning a dict that stays ``MASKED_FAILURE`` via
        ``NO_EXECUTOR``. It never resubmits the committed HUMAN command
        (same-revision ``DK`` replay denied). Distinct from activation retry
        (S-B) and resolution-entry settlement retry (R4)."""
        from src.api import session_api
        return self.call(session_api.recover_continuation, self._state)

    # -----------------------------------------------------------------------
    # D4/D6 item3 §5.2 (Errata E5) — read-only owner-checkpoint resume-kind
    # adapter. Added under the PM write-face Amendment (api_adapter.py narrow
    # extension): a NEW read-only method only. It changes NO existing adapter
    # method / route / semantics.
    # -----------------------------------------------------------------------
    def recovery_resume_kind(self) -> Optional[str]:
        """Return the coordinator-owned owner-checkpoint resume-kind (or None).

        The Store's no-argument recovery intent must NOT pick a resume-kind
        itself and must NOT use the I1 cardinality proxy
        (``determinate_recovery_resume_kind`` returns a value only for a
        singleton permitted set — every admission row is multi-kind). This
        trusted routing-layer adapter routes the intent to the coordinator's
        ``session_turn_service.resolve_recovery_resume_kind`` against the
        CURRENT sealed mandate; the resolver chooses the SINGLE kind from the
        REAL checkpoint facts and membership-validates it against the mandate's
        permitted closed set.

        Strictly READ-ONLY: it never mints/comsumes a capability, never opens a
        scope, never writes the ledger/cursor, and takes NO caller-supplied kind.
        """
        from src.api import session_access, session_turn_service
        mandate = session_access.recovery_mandate(self._state)
        if mandate is None:
            return None
        return session_turn_service.resolve_recovery_resume_kind(
            self._state, mandate)

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
    # S-B Group 1/4 (SB-V07): envelope-preserving internal read path.
    # The ordinary GUI getters above map a failure to a safe empty model for QML
    # (safe empty/unavailable). The Store's authority-bearing activation path
    # must instead observe the REAL envelope so a denied/empty read is never
    # mistaken for a successful projection.
    # -----------------------------------------------------------------------
    def read_envelope(self, api_func, *args, **kwargs) -> Dict[str, Any]:
        """Call a read API and return its RAW envelope (never collapsed to ``{}``).

        Returns ``{success, message, data, errors}``; an exception is converted to
        a typed failure envelope so the caller can fail closed. The trusted routing
        layer presents the current service handle (DG-01); during masked staging the
        internal neutral activation reservation authorizes the read for its reserved
        target regardless of the presented (revoked) handle.
        """
        try:
            caller_context = session_access.current_caller_context(self._state)
            if caller_context is not None:
                kwargs.setdefault("caller_context", caller_context)
            result = api_func(*args, **kwargs)
        except Exception as e:  # pragma: no cover - defensive
            logger.exception(f"API read exception: {getattr(api_func, '__name__', api_func)}")
            return {"success": False, "message": f"API exception: {e}",
                    "data": None, "errors": [str(e)]}
        if not isinstance(result, dict):
            return {"success": False, "message": f"API returned non-dict: {type(result)}",
                    "data": None, "errors": []}
        return result

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
        result = revenue_api.get_revenue_view(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
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
        result = forum_api.get_forum_view(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
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
        result = session_api.get_session_snapshot(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Snapshot failed: {result.get('message')}")
        return {}

    def get_population_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import session_api
        result = session_api.get_population_view(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Population view failed: {result.get('message')}")
        return {}

    def get_mortality_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import mortality_api
        result = mortality_api.get_mortality_view(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
        if result.get("success"):
            return result.get("data", {})
        logger.error(f"Mortality view failed: {result.get('message')}")
        return {}

    def get_senate_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import senate_api
        result = senate_api.get_senate_view(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
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
        result = combat_api.get_combat_view(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
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

    def get_global_query_result(
        self, viewer_id: str, query_id: str, filter_text: str = "", record_id: str = ""
    ) -> Dict[str, Any]:
        """Mirror the read seam ``gui_query_api.get_global_query_result`` (A05-01).

        Returns the typed safe QueryDTO. The Adapter retains the API truth and
        **always** sanitizes: a false envelope or malformed/unvalidated payload is
        mapped to a fixed safe failure shell with a whitelisted enum code and
        redacted copy. Raw backend text (``message`` / error strings / unknown
        codes / unsafe params) is **never** forwarded into the DTO (A05-02, F6).
        """
        from src.api import gui_query_api
        caller_context = session_access.current_caller_context(self._state)
        try:
            result = gui_query_api.get_global_query_result(
                self._state, viewer_id, query_id, filter_text, record_id,
                caller_context=caller_context,
            )
        except Exception:  # pragma: no cover - defensive fail-closed
            logger.exception("Global query exception: %s", query_id)
            return gui_query_api.build_failure_dto(
                query_id, "ERROR", gui_query_api.ERR_QUERY_FAILED
            )
        if not isinstance(result, dict):
            return gui_query_api.build_failure_dto(
                query_id, "ERROR", gui_query_api.ERR_QUERY_FAILED
            )
        data = result.get("data")
        success = bool(result.get("success", False))
        if not isinstance(data, dict):
            # Legacy/malformed failure with data=None -> fixed safe shell only;
            # NEVER forward a raw backend message through the DTO (F6).
            return gui_query_api.build_failure_dto(
                query_id, "ERROR", gui_query_api.ERR_QUERY_FAILED,
            )
        if success:
            if data.get("result_state") in ("OK", "EMPTY") \
                    and self._valid_success_dto(data, query_id):
                return data
            logger.error("Global query malformed success envelope for query: %s", query_id)
            return gui_query_api.build_failure_dto(
                query_id, "ERROR", gui_query_api.ERR_QUERY_FAILED
            )
        # -- failure envelope: validated safe enum + redacted copy (F6) --------
        code = self._safe_failure_code(data)
        if code is None:
            logger.error("Global query malformed failure envelope for query: %s", query_id)
            return gui_query_api.build_failure_dto(
                query_id, "ERROR", gui_query_api.ERR_QUERY_FAILED
            )
        safe_state = "DENIED" if data.get("result_state") == "DENIED" else "ERROR"
        return gui_query_api.build_failure_dto(query_id, safe_state, code)

    @staticmethod
    def _valid_success_dto(data: Dict[str, Any], query_id: str) -> bool:
        """Schema check for a claimed success DTO (id / state / items / summary /
        capabilities must be present and well-typed)."""
        if data.get("id") not in ("", query_id):
            return False
        if data.get("result_state") not in ("OK", "EMPTY"):
            return False
        if not isinstance(data.get("items"), list):
            return False
        if not isinstance(data.get("summary"), dict):
            return False
        if not isinstance(data.get("capabilities"), dict):
            return False
        return True

    @classmethod
    def _safe_failure_code(cls, data: Dict[str, Any]):
        """Validate a failure envelope's enum + error schema. Returns the fixed
        safe code, or ``None`` when the payload is malformed/unsafe (→ the caller
        rebuilds ``query_failed``); raw ``message`` text is never read here.

        A4/F6: the code is **type-validated before** the frozenset membership test.
        A non-``str`` code (list/dict/int/None) can never be hashable-safe against
        the enum, so it is rejected here (returns ``None``) rather than raising
        ``TypeError`` outside the caller's protective try. Malformed sanitisation
        is therefore TOTAL and never raises.
        """
        if data.get("result_state") not in ("DENIED", "ERROR"):
            return None
        errors = data.get("errors")
        if not isinstance(errors, (list, tuple)) or not errors:
            return None
        first = errors[0]
        if not isinstance(first, dict):
            return None
        code = first.get("code")
        if not isinstance(code, str):
            return None
        if code in cls._SAFE_FAILURE_CODES:
            return code
        return None

    # -----------------------------------------------------------------------
    # Resolution stage API
    # -----------------------------------------------------------------------
    def get_resolution_view(self, viewer_id: str) -> Dict[str, Any]:
        from src.api import session_api
        result = session_api.get_resolution_view(
            self._state, viewer_id,
            caller_context=session_access.current_caller_context(self._state))
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
