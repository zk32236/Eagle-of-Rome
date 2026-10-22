"""
src/ui/gui/session_store.py
GuiSessionStore — 唯一 GUI 会话存储。
QML 只能访问只读属性、列表模型和 Slot。
每次 API 操作后从 session_api 重新刷新。
"""
import importlib
import logging
import uuid
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Property, Slot, QAbstractListModel, Qt, QModelIndex

from src.core.game_state import GameState
from src.core.entities.player import PlayerType
from src.api import session_access
from src.ui.gui.api_adapter import GuiApiAdapter
from src.ui.gui.localization import gui_localization, gui_text
from src.ui.processors.auto_player_processor import AutoPlayerProcessor
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
from src.core.deciders.impl.auto_bid_decider import AutoBidDecider
from src.core.deciders.impl.auto_triumph_decider import AutoTriumphDecider

logger = logging.getLogger("EOR-GUI")

# ---------------------------------------------------------------------------
# S-B Group 2 — handoff authority lifecycle labels (frozen design G2/R2).
# The Store is the *publication* owner; Core owns the current actor/phase; the
# session access service owns the authority epoch. Names follow the frozen
# ACTIVE -> MASKED_PENDING_HANDOFF -> ACTIVATE -> MASKED_FAILURE machine, plus a
# transient internal BUSY phase (SUSPENDING/EXECUTING_MASKED) that is never a
# player-facing copy.
# ---------------------------------------------------------------------------
SEAT_ACTIVE = "ACTIVE"
SEAT_BUSY = "SUSPENDING"
SEAT_MASKED_PENDING = "MASKED_PENDING_HANDOFF"
SEAT_ACTIVATE = "ACTIVATE"
SEAT_MASKED_FAILURE = "MASKED_FAILURE"

#: Failure classification used only inside the Store (never player copy).
FAIL_BEFORE_COMMIT = "before_commit"
FAIL_AFTER_COMMIT = "after_commit"

#: SD-R02 (§1.1.R) safe, EXCLUSIVE failure-origin routing token. A status enum
#: only — never player id / faction-beyond-safe-name / token / epoch, never
#: player copy. Exactly ONE origin value is active per MASKED_FAILURE, so the
#: overlay can offer exactly one bounded failure action:
#:   * ``RECOVER_ROUTE_ACTIVATION``   -> grHandoffRetry (activation re-arm)
#:   * ``RECOVER_ROUTE_CONTINUATION`` -> grContinuationRecover (AI-drain resume)
#: Every EXISTING ``_fail_masked`` call site defaults to ``activation``; the
#: AI-drain continuation masked-failure site passes ``continuation``.
RECOVER_ROUTE_ACTIVATION = "activation"
RECOVER_ROUTE_CONTINUATION = "continuation"

#: SD1-V01 — the REAL post-commit AI-drain continuation failure producer
#: contract. ``session_api.submit_population_votes`` (N7-R) and the senate AI
#: vote drain (N10-R) return, on a failed continuation, a structured failure whose
#: ``data.status`` is ``"masked_failure"`` and whose typed error carries
#: ``AI_DRAIN_MASKED_FAILURE``. The recognizer binds to THIS envelope (never a
#: boolean-only ``masked_failure`` key) while preserving the post-commit meaning.
MASKED_CONTINUATION_STATUS = "masked_failure"
MASKED_CONTINUATION_ERROR_CODE = "AI_DRAIN_MASKED_FAILURE"


# ---------------------------------------------------------------------------
# W2b (FC-712-17..20) — declarative private staged inventory.
#
# The activation bundle is a DECLARED inventory (one entry per resource), not an
# ad-hoc tuple. Each entry carries the frozen fields:
#
#   resource_id / scope / source / required / neutral_value / validator /
#   notify / tags
#
# ``scope`` is the publication scope of the resource:
#   * SCOPE_SEAT            — seat-facing DTO of the target seat;
#   * SCOPE_SESSION_DISPLAY — session display data (faction style) that is
#                             REQUIRED but is NOT a public/global surface;
#   * SCOPE_TRANSIENT       — reserved for transient derivations (none yet).
#
# ``tags`` names the bundle tags every resource is bound to; they are recorded
# on the bundle and re-validated at publish time so an old/foreign bundle can
# never publish into a newer epoch.
# ---------------------------------------------------------------------------
SCOPE_SEAT = "SEAT"
SCOPE_SESSION_DISPLAY = "SESSION_DISPLAY"
SCOPE_TRANSIENT = "TRANSIENT"

#: The tag names every staged resource is bound to (FC-712-17).
STAGED_TAG_NAMES = (
    "session",
    "scope",
    "target",
    "seat_epoch",
    "core_revision",
    "publication_revision",
)


def _is_mapping(value: Any) -> bool:
    """Base DTO validator: every staged DTO is a mapping."""
    return isinstance(value, dict)


def _is_style_map_dto(value: Any) -> bool:
    """FC-712-20 schema check for ``factionStyleMap``.

    A style map that is not the declared shape (``map`` mapping + ``fallback``
    mapping + ``default_unknown_color`` string) is malformed, never an empty
    legal value.
    """
    if not isinstance(value, dict):
        return False
    if not isinstance(value.get("map"), dict):
        return False
    if not isinstance(value.get("fallback"), dict):
        return False
    if not isinstance(value.get("default_unknown_color"), str):
        return False
    return True


class GuiSessionStore(QObject):
    """
    GUI 会话存储。
    内部持有 GameState 引用，对 QML 暴露只读属性和信号。
    """

    #: FC-712-17 — the DECLARATIVE activation inventory. The order is the
    #: staging read order; publication order is fixed by ``_apply_staged``.
    #: Every entry is REQUIRED today (the eight DTOs already failed closed as a
    #: package; ``factionStyleMap`` joins them as the ninth REQUIRED resource).
    #: R03 (FC-712-17): each entry ALSO declares where the value is published
    #: (``attr`` = the private backing attribute), the ORDER the public
    #: notification runs in (``publish_order``), and the value that
    #: ``_neutralize_public_projection`` restores (``neutral_value``). Apply /
    #: notify / neutralize are ALL derived from this single declaration, so a new
    #: resource can never be staged and then silently dropped on publication.
    _ACTIVATION_INVENTORY = (
        {
            "resource_id": "snapshot", "scope": SCOPE_SEAT,
            "source": "session_api.get_session_snapshot", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "snapshotChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_snapshot", "publish_order": 1,
        },
        {
            "resource_id": "population", "scope": SCOPE_SEAT,
            "source": "session_api.get_population_view", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "populationViewChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_population_view", "publish_order": 2,
        },
        {
            "resource_id": "resolution", "scope": SCOPE_SEAT,
            "source": "session_api.get_resolution_view", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "resolutionViewChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_resolution_view", "publish_order": 8,
        },
        {
            "resource_id": "mortality", "scope": SCOPE_SEAT,
            "source": "mortality_api.get_mortality_view", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "mortalityViewChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_mortality_view", "publish_order": 3,
        },
        {
            "resource_id": "senate", "scope": SCOPE_SEAT,
            "source": "senate_api.get_senate_view", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "senateViewChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_senate_view", "publish_order": 4,
        },
        {
            "resource_id": "revenue", "scope": SCOPE_SEAT,
            "source": "revenue_api.get_revenue_view", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "revenueViewChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_revenue_view", "publish_order": 5,
        },
        {
            "resource_id": "forum", "scope": SCOPE_SEAT,
            "source": "forum_api.get_forum_view", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "forumViewChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_forum_view", "publish_order": 6,
        },
        {
            "resource_id": "combat", "scope": SCOPE_SEAT,
            "source": "combat_api.get_combat_view", "required": True,
            "neutral_value": {}, "validator": _is_mapping,
            "notify": "combatViewChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_combat_view", "publish_order": 7,
        },
        {
            # FC-712-17/20: the colour/name card is a SESSION DISPLAY resource,
            # never "public because it looks static". It is REQUIRED in every
            # activation bundle and read target-aware.
            "resource_id": "factionStyleMap", "scope": SCOPE_SESSION_DISPLAY,
            "source": "faction_api.get_faction_style_map", "required": True,
            "neutral_value": {}, "validator": _is_style_map_dto,
            "notify": "snapshotChanged", "tags": STAGED_TAG_NAMES,
            "attr": "_faction_style_map", "publish_order": 0,
        },
    )

    @classmethod
    def activation_inventory(cls) -> tuple:
        """The declared activation inventory (read-only copy per call)."""
        return tuple(dict(entry) for entry in cls._ACTIVATION_INVENTORY)

    @classmethod
    def _required_resource_ids(cls) -> tuple:
        """R05: the resources whose freshness a WRITE depends on.

        Derived from the SAME declaration as staging (``required=True``), never
        from a hand-maintained list, so adding a REQUIRED resource automatically
        adds its freshness dependency to ``freshnessWritesBlocked``.
        """
        return tuple(entry["resource_id"] for entry in cls._ACTIVATION_INVENTORY
                     if entry.get("required"))

    # 信号
    snapshotChanged = Signal()
    populationViewChanged = Signal()
    mortalityViewChanged = Signal()
    senateViewChanged = Signal()
    revenueViewChanged = Signal()
    forumViewChanged = Signal()
    combatViewChanged = Signal()
    resolutionViewChanged = Signal()
    resolutionAdvancingChanged = Signal()
    queryResultChanged = Signal()
    # EOR20261011-01 S1：viewer/handoff/reset invalidation barrier（v1.2 §2.1）。
    # 单一 boolean 载荷 = 安全 shell 策略（keep_open），无 viewer/record/private payload。
    queryInvalidated = Signal(bool)  # keep_open
    queryGuardChanged = Signal()
    currentPlayerChanged = Signal()
    phaseChanged = Signal()
    phaseStepsChanged = Signal()  # WP-J J-AC-10：选中相位的权威步骤读模型 notify
    feedbackRaised = Signal(str, str)  # type, message
    handoffRequired = Signal(str)  # next_player_id (LEGACY informational handoff)
    # W2a: startup-page value/mode notification. Emitted when the neutral
    # startup state is established and when the GUI locale changes (the
    # year/territory display strings are locale-dependent).
    startupChanged = Signal()
    # S-B Group 2/3: masked handoff authority machine signals.
    # ``handoffMaskPending`` carries ONLY the safe faction display name; the raw
    # next player id / token / epoch stay private routing metadata (never copy).
    seatLifecycleChanged = Signal()
    handoffMaskChanged = Signal()
    handoffMaskPending = Signal(str)  # safe faction name ONLY
    handoffFinished = Signal(str, bool)  # txn_id, success (R2 completion)
    handoffPendingFactionChanged = Signal()
    handoffExitRequested = Signal()
    populationVoteSubmittingChanged = Signal()
    senateSubmitErrorsChanged = Signal()  # R6 DA-2 B5：Submit 结构化错误 + 草稿保留面
    senateFinalizationWarningChanged = Signal()  # R6 DA-4 B2：自动 finalization 失败 warning

    # R8（SA §5.3，FC-UI-04，D-R8-04）：Senate 诊断**人话展示副本**映射（code 为内部查表键）。
    # 仅用于 Store 侧旁路反馈（shell toast/status）的玩家可读摘要——不改原 feedback 返回 /
    # 错误对象 / 日志（原始结构化诊断仍留 Store 数据面 / 运行日志）。
    _SENATE_FRIENDLY_MESSAGES = {
        "REINFORCEMENT_INVALID": "增援军团数量不符合要求，请修改数量",
        "LEGION_POOL_EXCEEDED": "增援请求超过可用军团，请减少增援军团数量",
        "COMMANDER_CLAIM_DUPLICATE": "同一指挥官不能同时指挥这些战争，请为涉事战争选择不同指挥官",
        "COMMANDER_TARGET_INVALID": "所选指挥官不可用，请重新选择指挥官",
        "COMMANDER_INELIGIBLE": "所选人物不符合指挥官资格，请另行选择",
        "PACKAGE_ALREADY_SUBMITTED": "本会期已提交，请查看已提交内容",
    }

    def __init__(self, state: GameState, parent=None, *, neutral_startup: bool = False):
        super().__init__(parent)
        self._state = state
        self._neutral_startup = bool(neutral_startup)
        self._adapter = GuiApiAdapter(state, refresh_callback=self._on_refresh)

        # 缓存的快照数据（只含 DTO）
        self._snapshot: Dict[str, Any] = {}
        self._population_view: Dict[str, Any] = {}
        self._population_vote_submitting: bool = False
        self._mortality_view: Dict[str, Any] = {}
        self._senate_view: Dict[str, Any] = {}
        self._revenue_view: Dict[str, Any] = {}
        self._forum_view: Dict[str, Any] = {}
        self._forum_result: Dict[str, Any] = {}
        self._forum_step_override: str = ""
        self._combat_view: Dict[str, Any] = {}
        self._combat_result: Dict[str, Any] = {}
        self._resolution_view: Dict[str, Any] = {}
        self._resolution_resolving: bool = False
        self._resolution_advancing: bool = False
        self._revenue_result: Dict[str, Any] = {}
        self._mortality_result: Dict[str, Any] = {}
        self._current_player_id: str = ""
        self._viewer_id: str = ""
        self._selected_phase_id: str = ""
        self._selected_phase_summary: Dict[str, Any] = {}
        self._global_query_result: Dict[str, Any] = {}
        # EOR20261011-01 S1 query shell protocol state（只读查询壳）
        self._query_guard: bool = False
        self._query_guard_depth: int = 0
        self._query_epoch: int = 0
        self._query_open: bool = False
        self._query_active_id: str = ""
        self._pending_auto_refresh: Optional[str] = None
        self._viewer_txn: Optional[Dict[str, Any]] = None
        self._feedback_queue: List[Dict[str, str]] = []
        self._forum_ai_processed = False
        self._last_reset_turn: int = 0
        self._faction_style_map: Dict[str, Any] = {}
        # W2b (FC-712-18): PRIVATE last-good projection cache + freshness state.
        # ``_last_good_views[resource_id] = {"viewer": <player_id>, "data": {...}}``
        # — a cached value is only ever reused for the SAME viewer, so a stale A
        # value can never be rendered for B.
        self._last_good_views: Dict[str, Dict[str, Any]] = {}
        self._stale_resources: Dict[str, bool] = {}
        # FC-712-20: a public refresh requested while the seat is masked is
        # deferred (never applied) and satisfied by the complete private
        # activation bundle.
        self._deferred_public_refresh: bool = False
        # R6（SA §B.5，DA-2 B5）：Submit 结构化错误 + 草稿保留
        # - _senate_submit_errors：规范排序的 error_items（Adapter formatter 输出）
        # - _senate_submit_errors_by_war：war_id → items（卡级 cardErrors 定位）
        # - _senate_submit_errors_by_scope：scope key（package / war:<id>）→ items
        # - _senate_drafts：**(session + war_id)** → draft 深值（checked/mode/target/N
        #   + 另一模式缓存）；失败/refresh **不**重建、不取消 checkbox、不 clamp、不换将
        self._senate_submit_errors: List[Dict[str, Any]] = []
        self._senate_submit_errors_by_war: Dict[str, List[Dict[str, Any]]] = {}
        self._senate_submit_errors_by_scope: Dict[str, List[Dict[str, Any]]] = {}
        self._senate_drafts: Dict[str, Dict[str, Any]] = {}
        self._senate_draft_session_id: str = ""
        # R6（SA §D.1，DA-4 B2）：自动 finalization 失败 warning 文本（Submit 回包携带）
        self._senate_finalization_warning: str = ""
        # D13（Option 4）：AI 执政官提案发布失败的 UI-local 阻止态。仅 typed seat
        # `DENIED` 建立；reason 由同席恢复后的既有反馈通道实际消费（不是闲置
        # QML 属性）；key = 调用前捕获的 (session, step, viewer)，不含 epoch。
        self._senate_ai_proposer_blocked: bool = False
        self._senate_ai_proposer_blocked_reason: str = ""
        self._senate_ai_proposer_block_key: Optional[Any] = None

        # EOR20261011-01 S1（v1.2 §2.1 step 3，A3/F2）：**真实** receiver 完成见证。
        # 真实 QML receiver（Overlay.resetForInvalidation）在**完成本地/绑定模型清空
        # 之后**同步回写 ack（= 当时的 epoch）到 `ackQueryInvalidation`。Store 在
        # `_set_viewer` 发布新 viewer 前读取/校验该校验；未收到匹配 ack → fail
        # closed，不发布新 viewer、不写新 viewer。自证「Store dict 已空」**不**通过。
        # `had_content == False`（无可泄漏旧内容）时无清空义务，视为已投递。
        self._query_invalidation_ack: int = -1
        self._query_receiver_verified: bool = True
        # A4（F2 残留收口）：**持久**的接收清除义务。任一未被真实 receiver ack
        # 解除的清除（Close / 失败切换 / 失败关闭）都会置位；在义务未解除前，后续
        # 切人**不得**以「Store 空态 + CLOSED」冒充接收完成见证（须真实 ack 解除）。
        self._receiver_clear_outstanding: bool = False

        # ---- S-B Group 2/4: handoff authority state machine (Store side) ----
        # Core owns the current actor/phase; this Store owns only the projected
        # DTO / render transaction. ``_seat_epoch`` is the monotonic *seat*
        # lifecycle epoch (distinct from Query ``_query_epoch``).
        self._seat_lifecycle: str = SEAT_ACTIVE
        self._seat_epoch: int = 0
        self._seat_txn: Optional[Dict[str, Any]] = None
        self._barrier_provider: Optional[Any] = None
        self._pending_player_id: str = ""        # private routing metadata
        self._pending_faction_name: str = ""     # the ONLY pre-activation identity
        self._pending_token: str = ""            # opaque single-use token
        self._handoff_failure_kind: str = ""
        self._handoff_failure_route: str = RECOVER_ROUTE_ACTIVATION
        self._committed_receipt: Optional[Dict[str, Any]] = None
        #: W3 / A-W3-03: the EXACT envelope this transaction settled from. A
        #: failure retry re-validates THIS record only; the Core cursor is never a
        #: target source (D-W3-D08). Cleared by a successful activation.
        self._last_delivery: Optional[Dict[str, Any]] = None
        #: W3 / W-04: the in-scope owning command whose settlement REQUIRES a
        #: recorded delivery envelope. Set by the masked senate owning flow; empty
        #: for startup / population / forum legacy transactions (whose retry keeps
        #: its recorded transaction target, never the Core cursor).
        self._delivery_required_command: str = ""
        self._staged_viewer_id: str = ""
        self._reveal_pending: bool = False
        self._handoff_busy: bool = False
        self._handoff_feedback: Dict[str, Any] = {}
        # W2a: neutral startup presentation mode ("single_human"/"multi_human").
        # Empty until a neutral startup actually begins.
        self._startup_mode: str = ""
        # F4 (R2 §1/§4): the resumable frame-gate continuation. When the bound
        # provider exposes the real-frame async gate methods, the masked handoff
        # transaction SUSPENDS on a gate (arm / publication-under-mask / final
        # reveal) and resumes from the real frame receipt — ``confirmHandoff`` may
        # therefore return ``pending`` and complete later via ``handoffFinished``.
        self._async_gate: Optional[Dict[str, Any]] = None
        self._activation_result: Optional[Dict[str, Any]] = None
        # W3-C1 (F01) / AC-W3-19 §9.1 / G43 W13: the PRIVATE carrier of the
        # recovery diagnostic produced when a same-seat recovery of a legitimate
        # (non-mutating) business refusal fails. It is written ONLY from the
        # authorized recovery callback and is NEVER copied into the rejected
        # command's public ``success/message/data/errors`` envelope.
        self._w3_recovery_diagnostic: Optional[Dict[str, Any]] = None
        gui_localization.localeChanged.connect(self._on_gui_locale_changed)

    # -----------------------------------------------------------------------
    # 初始化
    # -----------------------------------------------------------------------
    def initialize(self, viewer_id: str):
        """初始化，设置 viewer 并加载第一帧快照

        E — neutral startup (R2 §3 / SB-V04 startup): when ``neutral_startup`` is
        enabled the Store does NOT publish the factory-chosen actor; it enters a
        neutral MASKED_PENDING and exposes ONLY the validated safe faction name +
        neutral reserved slot until an explicit first-HUMAN 「接管」
        (``requestTakeover``) completes. The default (legacy) behaviour is
        unchanged for the existing CLI/historical suite.
        """
        if self._neutral_startup and session_access.is_hotseat_registered(self._state):
            self._begin_neutral_startup(viewer_id)
            return
        self._begin_viewer_transaction()
        try:
            self._set_viewer(viewer_id)
            self._refresh_snapshot()
            self._refresh_faction_style_map()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
            self._refresh_revenue_view()
            self._refresh_forum_view()
            self._refresh_combat_view()
            self._refresh_resolution_view()
        finally:
            self._end_viewer_transaction()

    # -----------------------------------------------------------------------
    # QML 可访问属性
    # -----------------------------------------------------------------------
    @Property(str, notify=snapshotChanged)
    def currentPlayerId(self) -> str:
        return self._snapshot.get("current_player_id", "")

    @Property(str, notify=snapshotChanged)
    def viewerPlayerId(self) -> str:
        return self._snapshot.get("viewer_player_id", "")

    @Property(str, notify=snapshotChanged)
    def viewerFactionId(self) -> str:
        return self._snapshot.get("viewer_faction_id", "")

    @Property(bool, notify=snapshotChanged)
    def isCurrentPlayer(self) -> bool:
        return self._snapshot.get("is_current_player", False)

    @Property(str, notify=snapshotChanged)
    def yearDisplay(self) -> str:
        pr = self._snapshot.get("public_resources", {})
        return pr.get("year_display", "")

    @Property(int, notify=snapshotChanged)
    def turnNumber(self) -> int:
        pr = self._snapshot.get("public_resources", {})
        return pr.get("turn_number", 0)

    @Property(int, notify=snapshotChanged)
    def treasury(self) -> int:
        pr = self._snapshot.get("public_resources", {})
        return pr.get("treasury", 0)

    @Property(int, notify=snapshotChanged)
    def factionTreasury(self) -> int:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("treasury", 0) if fr else 0

    @Property(int, notify=snapshotChanged)
    def factionInfluence(self) -> int:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("total_influence", 0) if fr else 0

    @Property(int, notify=snapshotChanged)
    def factionMemberCount(self) -> int:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("member_count", 0) if fr else 0

    @Property(list, notify=snapshotChanged)
    def phaseNavigation(self) -> List[Dict[str, Any]]:
        return self._snapshot.get("phase_navigation", [])

    @Property(str, notify=phaseChanged)
    def selectedPhaseId(self) -> str:
        return self._selected_phase_id

    @Property(str, notify=phaseChanged)
    def selectedPhaseName(self) -> str:
        return self._selected_phase_summary.get("name", "")

    @Property(dict, notify=phaseChanged)
    def selectedPhaseSummary(self) -> Dict[str, Any]:
        return self._selected_phase_summary

    @Property(list, notify=phaseStepsChanged)
    def phaseSteps(self) -> List[Dict[str, Any]]:
        """WP-J J-AC-10 / FC-01/FC-08：选中相位的权威子环节步骤读模型。

        只读透传：各阶段 `get_*_view().steps` 为唯一 owner；Store 不重算、不造步骤
        （zero QML/Store business rebuild）。未实现相位 / 无步骤 → 空列表。
        """
        views = {
            "mortality": self._mortality_view,
            "revenue": self._revenue_view,
            "forum": self._forum_view,
            "population": self._population_view,
            "senate": self._senate_view,
            "combat": self._combat_view,
        }
        return views.get(self._selected_phase_id, {}).get("steps", []) or []

    @Property(str, notify=snapshotChanged)
    def currentPhaseId(self) -> str:
        return self._snapshot.get("current_phase_id", "mortality")

    @Property(str, notify=snapshotChanged)
    def currentPhaseName(self) -> str:
        for phase in self.phaseNavigation:
            if phase.get("id") == self.currentPhaseId:
                return phase.get("name", "")
        return "天命"

    @Property(int, notify=snapshotChanged)
    def currentPhaseIndex(self) -> int:
        nav = self.phaseNavigation
        for i, phase in enumerate(nav):
            if phase.get("id") == self.currentPhaseId:
                return i
        return 0

    @Property(str, notify=snapshotChanged)
    def viewerFactionName(self) -> str:
        fr = self._snapshot.get("faction_resources", {})
        return fr.get("name", "") if fr else self.viewerFactionId

    @Property(list, notify=snapshotChanged)
    def globalWarnings(self) -> List[Dict[str, str]]:
        return self._snapshot.get("global_warnings", [])

    @Property(list, notify=snapshotChanged)
    def myFigures(self) -> List[Dict[str, Any]]:
        return self._snapshot.get("my_figures", [])

    @Property(list, notify=populationViewChanged)
    def populationCandidates(self) -> List[Dict[str, Any]]:
        """返回按官职分组的候选人，转为扁平列表供 QML 消费"""
        candidates = self._population_view.get("candidates", {})
        flat = []
        office_names = {
            "consul": "执政官", "censor": "监察官", "praetor": "大法官",
            "quaestor": "财务官", "tribune": "保民官"
        }
        for office, cands in candidates.items():
            for c in cands:
                c_copy = dict(c)
                c_copy["office"] = office
                c_copy["office_name"] = office_names.get(office, office)
                flat.append(c_copy)
        return flat

    @Property(dict, notify=populationViewChanged)
    def populationFeaturedCandidateIds(self) -> Dict[str, Any]:
        """WP-J Group C-1（FC-C01）：每 office 的权威 featured figure_id（只读透传，零本地业务）。"""
        return self._population_view.get("featured_candidate_ids", {})

    @Property(dict, notify=populationViewChanged)
    def populationView(self) -> Dict[str, Any]:
        return self._population_view

    @Property(dict, notify=populationViewChanged)
    def populationOutcome(self) -> Dict[str, Any]:
        """WP-J Group D-Aftermath（FC-D01/FC-D02）：战后反馈只读透传（零本地缓存）。"""
        return self._population_view.get("population_outcome", {})

    @Property(list, notify=populationViewChanged)
    def populationCampaigns(self) -> List[Dict[str, Any]]:
        return self._population_view.get("my_campaigns", [])

    @Property(str, notify=populationViewChanged)
    def populationCurrentStep(self) -> str:
        return self._population_view.get("current_step", "campaign")

    @Property(bool, notify=populationViewChanged)
    def populationResolved(self) -> bool:
        return self._population_view.get("resolved", False)

    @Property(list, notify=populationViewChanged)
    def populationElectionResults(self) -> List[Dict[str, Any]]:
        return self._population_view.get("election_results", [])

    @Property(list, notify=populationViewChanged)
    def populationInfluenceBefore(self) -> List[Dict[str, Any]]:
        return self._population_view.get("faction_influence_before", [])

    @Property(list, notify=populationViewChanged)
    def populationInfluenceAfter(self) -> List[Dict[str, Any]]:
        return self._population_view.get("faction_influence_after", [])

    @Property(bool, notify=populationVoteSubmittingChanged)
    def populationVoteSubmitting(self) -> bool:
        return self._population_vote_submitting

    @Property(dict, notify=populationViewChanged)
    def myVotes(self) -> Dict[str, int]:
        return self._population_view.get("my_votes", {})

    @Property(bool, notify=populationViewChanged)
    def canCampaign(self) -> bool:
        return self._population_view.get("can_campaign", False)

    @Property(bool, notify=populationViewChanged)
    def canVote(self) -> bool:
        return self._population_view.get("can_vote", False)

    @Property(bool, notify=populationViewChanged)
    def canComplete(self) -> bool:
        return self._population_view.get("can_complete", False)

    @Property(bool, notify=populationViewChanged)
    def canAdvancePopulation(self) -> bool:
        return self._population_view.get("can_advance", False)

    @Property(dict, notify=populationViewChanged)
    def populationConversionResult(self) -> Dict[str, Any]:
        """
        返回战场指挥官转换结果 DTO（consul→proconsul, praetor→propraetor）。
        数据来自 state._phase_results，仅展示，不触发转换。
        """
        return self._population_view.get("battlefield_commander_conversion", {"converted": [], "total": 0})

    @Property(dict, notify=mortalityViewChanged)
    def mortalityResult(self) -> Dict[str, Any]:
        return self._mortality_result

    @Property(list, notify=mortalityViewChanged)
    def mortalityEvents(self) -> List[Dict[str, Any]]:
        return self._mortality_result.get("events", []) or self._mortality_view.get("events", [])

    @Property(bool, notify=mortalityViewChanged)
    def canExecuteMortality(self) -> bool:
        return self._mortality_view.get("can_execute", False)

    @Property(bool, notify=mortalityViewChanged)
    def canAdvanceMortality(self) -> bool:
        return self._mortality_view.get("can_advance", False)

    @Property(dict, notify=senateViewChanged)
    def senateView(self) -> Dict[str, Any]:
        return self._senate_view

    @Property(list, notify=senateViewChanged)
    def senateFactionLeaders(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("faction_leaders", [])

    @Property(dict, notify=senateViewChanged)
    def senatePresidingOfficer(self) -> Dict[str, Any]:
        return self._senate_view.get("presiding_officer") or {}

    @Property(int, notify=senateViewChanged)
    def warCount(self) -> int:
        return len(self._senate_view.get("active_foreign_wars", []))

    @Property(list, notify=senateViewChanged)
    def senateActiveForeignWars(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("active_foreign_wars", [])

    @Property(list, notify=senateViewChanged)
    def senateWarThreats(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("war_threats", [])

    @Property(list, notify=senateViewChanged)
    def senatePendingPeaceTreaties(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("pending_peace_treaties", [])

    @Property(list, notify=senateViewChanged)
    def senateGovernorVacancies(self) -> List[Dict[str, Any]]:
        vacancies = self._senate_view.get("governor_vacancies", {}) or {}
        flat = []
        type_names = {"proconsul": "行省总督", "propraetor": "副总督"}
        for governor_type, provinces in vacancies.items():
            for province in provinces:
                item = dict(province)
                item["governor_type"] = governor_type
                item["governor_type_name"] = type_names.get(governor_type, governor_type)
                flat.append(item)
        return flat

    @Property(list, notify=senateViewChanged)
    def senatePendingContracts(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("pending_contracts", [])

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self) -> str:
        return self._senate_view.get("current_step", "proposal")

    @Property(list, notify=senateViewChanged)
    def senateProposalOptions(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("proposal_options", [])

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("submitted_proposals", [])

    @Property(dict, notify=senateViewChanged)
    def governorAppointments(self) -> Dict[str, Any]:
        return self._senate_view.get("governor_appointments", {})

    @Property(list, notify=senateViewChanged)
    def senateSeatShares(self) -> List[Dict[str, Any]]:
        return self._senate_view.get("seat_shares", [])

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self) -> bool:
        return self._senate_view.get("can_create_proposal", False)

    @Property(bool, notify=senateViewChanged)
    def canSelectSenateProposal(self) -> bool:
        """WP-D AU-2：viewer 手选提案权（= viewer 派系拥有 eligible 执政官）。"""
        return self._senate_view.get("can_select_proposal", False)

    @Property(bool, notify=senateViewChanged)
    def canTriggerAIProposer(self) -> bool:
        """WP-D AU-2：非执政官派系 → AI 自动提案入口。"""
        return self._senate_view.get("can_trigger_ai_proposer", False)

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVote(self) -> bool:
        return self._senate_view.get("can_vote", False)

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVeto(self) -> bool:
        return self._senate_view.get("can_veto", False) or self._senate_view.get("can_auto_veto", False)

    @Property(bool, notify=senateViewChanged)
    def canManuallySelectSenateVeto(self) -> bool:
        return self._senate_view.get("can_veto", False)

    @Property(str, notify=senateViewChanged)
    def senateVetoControlMode(self) -> str:
        """WP-J Group B ④ (J-AC-02 / FC-B09): 保民官否决权威 actor/source 只读透传。

        ← ``_senate_view["veto_control_mode"]``（单一 owner = politics.resolve_veto_control
        → senate_api.get_senate_view）；值域 HUMAN/AI/NONE；缺省 NONE（不伪造 actor，FC-B12）。
        零本地业务缓存；随 view 刷新重算（FC-B07 同原则）。**不改**既有 veto 键。
        """
        mode = self._senate_view.get("veto_control_mode")
        return mode if mode in ("HUMAN", "AI", "NONE") else "NONE"

    @Property(bool, notify=senateViewChanged)
    def canAdvanceSenate(self) -> bool:
        return self._senate_view.get("can_advance", False)

    @Property(bool, notify=senateViewChanged)
    def senateSettlementPending(self) -> bool:
        """R6（SA §D.1，DA-4 B2）：settlement-pending 可见恢复态**正常态退役**。

        finalization 已由服务端命令流程（Submit 零 Senate / vote 完成零 veto 候选 / veto
        完成）自动完成；DTO legacy 键正常态恒 False。本属性**恒 False**，不再驱动正常 UI。
        """
        return False

    @Property(bool, notify=senateViewChanged)
    def canResolveSenateSettlement(self) -> bool:
        """R6（SA §D.1，DA-4 B2）：正常态「完成结算」动作位**退役**（恒 False）。

        唯一正常推进 = `doAdvanceSenate`；内部异常恢复走 `canRetrySenateFinalization`
        能力位（非玩家正常动作位）。
        """
        return False

    @Property(bool, notify=senateViewChanged)
    def senateCanFinishEmpty(self) -> bool:
        """R5/R6：显式空结束能力（零提案关闭选择需先提交 []）。"""
        return self._senate_view.get("can_finish_proposal_selection", False)

    @Property(bool, notify=senateViewChanged)
    def senateAiProposerBlocked(self) -> bool:
        """D13（Option 4）：AI 执政官提案因授权失败被本地阻止（按钮 disabled）。

        唯一的公开面就是这个 bool；reason/key 均为私有，reason 只经既有反馈
        通道消费（不新增 DTO 字段 / 不新增 QML 属性）。"""
        return self._senate_ai_proposer_blocked

    @Property(bool, notify=senateViewChanged)
    def senateFinalizationError(self) -> bool:
        """R6（SA §D.1，DA-4 B2）：内部 finalization 异常恢复能力位（非正常态动作位）。"""
        return self._senate_view.get("senate_finalization_error", False)

    @Property(bool, notify=senateViewChanged)
    def canRetrySenateFinalization(self) -> bool:
        """R6（SA §D.1，DA-4 B2）：仅**真实** finalization 失败时 True（内部恢复通道）。"""
        return self._senate_view.get("can_retry_finalization", False)

    @Property(str, notify=senateFinalizationWarningChanged)
    def senateFinalizationWarning(self) -> str:
        """R6（SA §D.1，DA-4 B2）：Submit 后自动 finalization 失败的可见 warning（空 = 无）。"""
        return self._senate_finalization_warning

    @Property(list, notify=senateViewChanged)
    def senateWarCards(self) -> List[Dict[str, Any]]:
        """R5（SA §5.1/§5.3）：统一 War Card 只读投影（WarCardView）——QML 零推导。"""
        return self._senate_view.get("war_cards", [])

    @Property(dict, notify=senateViewChanged)
    def senateWarExecution(self) -> Dict[str, Any]:
        """R5（SA §5.1/§5.3）：WarExecutionReceipt 只读摘要（不得据 receipt 重新执行）。"""
        return self._senate_view.get("senate_result", {}).get("war_execution", {})

    @Property(list, notify=senateViewChanged)
    def senateConsulDirectDecisions(self) -> List[Dict[str, Any]]:
        """R7（SA §A.4，DA-R7 B1）：Consul 冻结 direct 决策只读投影（整个会期可读）。
        顶层 DTO 透传（senate_api.get_senate_view → data.consul_direct_decisions）。
        只读；零生命周期推导；行内无 proposal_id（不进 Vote/Veto）。"""
        return self._senate_view.get("consul_direct_decisions", [])

    # -----------------------------------------------------------------------
    # R6（SA §B.5，DA-2 B5）：Submit 结构化错误 + 草稿保留（GUI session 面）
    # -----------------------------------------------------------------------
    @Property(list, notify=senateSubmitErrorsChanged)
    def senateSubmitErrors(self) -> List[Dict[str, Any]]:
        """最后一次失败 Submit 的规范排序 error_items（成功 / 未提交 = []）。"""
        return self._senate_submit_errors

    @Property(dict, notify=senateSubmitErrorsChanged)
    def senateSubmitErrorsByWar(self) -> Dict[str, List[Dict[str, Any]]]:
        """war_id → error_items：卡级 `cardErrors`（按 field 显示）。"""
        return self._senate_submit_errors_by_war

    @Property(dict, notify=senateSubmitErrorsChanged)
    def senateSubmitErrorsByScope(self) -> Dict[str, List[Dict[str, Any]]]:
        """scope key（`package` / `war:<id>`）→ error_items（包级横幅 + 相关卡关联）。"""
        return self._senate_submit_errors_by_scope

    @Property(bool, notify=senateSubmitErrorsChanged)
    def hasSenateSubmitErrors(self) -> bool:
        return bool(self._senate_submit_errors)

    @Property(str, notify=senateSubmitErrorsChanged)
    def senateSubmitErrorBanner(self) -> str:
        """包级全局失败横幅文本（含 code + 可操作 message）。"""
        if not self._senate_submit_errors:
            return ""
        parts = []
        for item in self._senate_submit_errors:
            code = str(item.get("code") or "")
            msg = str(item.get("message") or "")
            parts.append(f"{code}: {msg}" if msg else code)
        return "提交失败 —— " + "；".join(parts)

    def senate_draft_key(self, war_id) -> str:
        """draft 保留键 = **(session + war_id)**（GUI session 隔离，满足 §B.5）。"""
        session = self._senate_draft_session_id or self._viewer_id or ""
        return f"{session}\x1f{war_id}"

    @Slot(str, "QVariant", result=dict)
    def doUpdateSenateDraft(self, war_id, draft) -> dict:
        """记录某 War 的本地草稿（QML 编辑事件）。失败路径不得调用本槽重置草稿。"""
        wid = str(war_id or "")
        if not wid:
            return {"ok": False}
        payload = self._variant_to_python(draft)
        if not isinstance(payload, dict):
            return {"ok": False}
        self._senate_drafts[self.senate_draft_key(wid)] = dict(payload)
        return {"ok": True, "war_id": wid}

    @Slot(str, result=dict)
    def senateDraftFor(self, war_id) -> dict:
        """取回该 War 已保留的草稿（无 = {}）——QML 重入 / 刷新后仍可恢复 dirty draft。"""
        return dict(self._senate_drafts.get(self.senate_draft_key(war_id), {}))

    @Slot(result=dict)
    def senateDrafts(self) -> dict:
        """当前 session 下全部保留草稿（键含 session+war_id）——普通 dict 快照。"""
        return {k: dict(v) for k, v in self._senate_drafts.items()}


    @Property(dict, notify=senateViewChanged)
    def senateResult(self) -> Dict[str, Any]:
        """
        Senate settlement result data, including post-settlement operations:
        - governor_assignments: list of {province_id, governor_id, name, assigned_at}
        - rebellion_commander_assignments: list of {rebellion_id, commander_id, name, assigned_at}
        - fleet_assignments: list of {war_id, war_name, fleets, total_power, needed_power}
        - public_announcement: {enacted_proposals, direct_actions} (WP-D AU-6)
        """
        return self._senate_view.get("senate_result", {}).get("data", {})

    @Property(dict, notify=senateViewChanged)
    def senatePublicAnnouncement(self) -> Dict[str, Any]:
        """WP-D AU-6：本轮最终生效事项公示（enacted_proposals + direct_actions）。"""
        return self._senate_view.get("senate_result", {}).get("data", {}).get("public_announcement", {})

    @Property(list, notify=senateViewChanged)
    def senateVoteResults(self) -> List[Dict[str, Any]]:
        """WP-F R1-F-03：本轮每提案已算 vote result（support/oppose/total/passed/vetoed），只读透传。"""
        return self._senate_view.get("vote_results", [])

    @Property(list, notify=senateViewChanged)
    def senateVetoCandidateIds(self) -> List[int]:
        """WP-F R2-01：权威 passed-only 否决候选 id 集，只读透传 DTO（空集 = 无否决候选）。"""
        return self._senate_view.get("veto_candidate_ids", [])

    # -----------------------------------------------------------------------
    # 收入阶段属性
    # -----------------------------------------------------------------------
    @Property(dict, notify=revenueViewChanged)
    def revenueResult(self) -> Dict[str, Any]:
        return self._revenue_result

    @Property(dict, notify=revenueViewChanged)
    def revenueView(self) -> Dict[str, Any]:
        return self._revenue_view

    @Property(dict, notify=revenueViewChanged)
    def revenueSettledData(self) -> Dict[str, Any]:
        settled = self._revenue_view.get("settled_data")
        if settled:
            return settled
        return self._revenue_result or {}

    @Property(bool, notify=revenueViewChanged)
    def canExecuteRevenue(self) -> bool:
        return self._revenue_view.get("can_execute", False)

    @Property(bool, notify=revenueViewChanged)
    def canAdvanceRevenue(self) -> bool:
        return self._revenue_view.get("can_advance", False)

    @Property(int, notify=revenueViewChanged)
    def treasuryDelta(self) -> int:
        result = self._revenue_result
        data = result.get("data", {}) if isinstance(result, dict) else {}
        if not data:
            data = self._revenue_view.get("settled_data", {}) or {}
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
        return data.get("treasury_delta", 0) if isinstance(data, dict) else 0

    @Property(int, notify=revenueViewChanged)
    def endingTreasury(self) -> int:
        result = self._revenue_result
        data = result.get("data", {}) if isinstance(result, dict) else {}
        if not data:
            data = self._revenue_view.get("settled_data", {}) or {}
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
        return data.get("ending_treasury", self.treasury) if isinstance(data, dict) else self.treasury

    @Property(dict, notify=forumViewChanged)
    def forumView(self) -> Dict[str, Any]:
        return self._forum_view

    @Property(dict, notify=forumViewChanged)
    def forumResult(self) -> Dict[str, Any]:
        return self._forum_result or self._forum_view.get("result", {})

    @Property(str, notify=forumViewChanged)
    def forumCurrentStep(self) -> str:
        if self._forum_step_override:
            return self._forum_step_override
        return self._forum_view.get("current_step", "retirement")

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("my_figures", [])

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("available_figures", [])

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("pending_contracts", [])

    @Property(int, notify=forumViewChanged)
    def forumLandQuota(self) -> int:
        return self._forum_view.get("land_sale_quota", 0)

    # WP-E F5（E-11 无 QML 本地状态）：四载体只读属性均读 _forum_view
    @Property(int, notify=forumViewChanged)
    def forumLandSaleTotal(self) -> int:
        return self._forum_view.get("land_sale_total", 0)

    @Property(int, notify=forumViewChanged)
    def forumLandPricePerUnit(self) -> int:
        return self._forum_view.get("land_price_per_unit", 0)

    @Property(list, notify=forumViewChanged)
    def forumViewerLandRequests(self) -> list:
        return self._forum_view.get("viewer_land_requests", [])

    # WP-E F6（D-07）：viewer 作用域 contract-bid 只读透传（零本地业务缓存）
    @Property(list, notify=forumViewChanged)
    def forumViewerContractBids(self) -> list:
        return self._forum_view.get("viewer_contract_bids", [])

    @Property(list, notify=forumViewChanged)
    def forumLandAllocation(self) -> list:
        return self._forum_view.get("land_allocation", [])

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("triumph_wars", [])

    @Property(list, notify=forumViewChanged)
    def forumWarThreats(self) -> List[Dict[str, Any]]:
        return self._forum_view.get("war_threats", [])

    # WP-E F7：war_events 保留载体 + has_active_war（06P/14P）
    @Property(list, notify=forumViewChanged)
    def forumWarEvents(self) -> list:
        return self._forum_view.get("war_events", [])

    # WP-J Group D-Rebellion（FC-D09/FC-D10）：起义警示只读透传（零本地缓存）
    @Property(list, notify=forumViewChanged)
    def forumRebellionEvents(self) -> list:
        return self._forum_view.get("rebellion_events", [])

    @Property(bool, notify=forumViewChanged)
    def forumHasActiveWar(self) -> bool:
        return self._forum_view.get("has_active_war", False)

    @Property(bool, notify=forumViewChanged)
    def canExecuteForum(self) -> bool:
        return self._forum_view.get("can_execute", False)

    @Property(bool, notify=forumViewChanged)
    def canAdvanceForum(self) -> bool:
        return self._forum_view.get("can_advance", False)

    @Property(bool, notify=forumViewChanged)
    def forumResolved(self) -> bool:
        return self._forum_view.get("resolved", False) or bool(self._forum_result)

    # -----------------------------------------------------------------------
    # WP-I §3.G（DESIGN FROZEN 2026-09-26）：viewer 作用域权威招募容量只读透传。
    # 全部只读 `_forum_view`（单一 resolver 派生的 DTO），notify=forumViewChanged，
    # 零本地业务缓存；QML 只消费权威值、不自算容量（R-I06 / I-06）。
    # -----------------------------------------------------------------------
    @Property(dict, notify=forumViewChanged)
    def forumRecruitment(self) -> Dict[str, Any]:
        return self._forum_view.get("viewer_recruitment", {})

    @Property(int, notify=forumViewChanged)
    def forumRecruitmentCapacity(self) -> int:
        return self.forumRecruitment.get("capacity", 0)

    @Property(int, notify=forumViewChanged)
    def forumRecruitmentCurrentMemberCount(self) -> int:
        return self.forumRecruitment.get("current_member_count", 0)

    @Property(int, notify=forumViewChanged)
    def forumRecruitmentPhysicalVacancies(self) -> int:
        return self.forumRecruitment.get("physical_vacancies", 0)

    @Property(int, notify=forumViewChanged)
    def forumRecruitmentPendingTargetCount(self) -> int:
        return self.forumRecruitment.get("pending_recruitment_target_count", 0)

    @Property(int, notify=forumViewChanged)
    def forumRecruitmentRemainingSlots(self) -> int:
        return self.forumRecruitment.get("remaining_recruitment_slots", 0)

    @Property(bool, notify=forumViewChanged)
    def forumRecruitmentCanSubmit(self) -> bool:
        return bool(self.forumRecruitment.get("can_submit_recruitment_bid", False))

    @Property(list, notify=forumViewChanged)
    def forumViewerPendingRecruitmentTargetIds(self) -> list:
        return self._forum_view.get("viewer_pending_recruitment_target_ids", [])

    # -----------------------------------------------------------------------
    # Combat stage properties
    # -----------------------------------------------------------------------
    @Property(dict, notify=combatViewChanged)
    def combatView(self) -> Dict[str, Any]:
        return self._combat_view

    @Property(list, notify=combatViewChanged)
    def combatActiveWars(self) -> List[Dict[str, Any]]:
        return self._combat_view.get("active_wars", [])

    @Property(list, notify=combatViewChanged)
    def combatBattleResults(self) -> List[Dict[str, Any]]:
        return self._combat_view.get("battle_results", [])

    @Property(str, notify=combatViewChanged)
    def combatCurrentStep(self) -> str:
        return self._combat_view.get("current_step", "select")

    @Property(bool, notify=combatViewChanged)
    def canAdvanceCombat(self) -> bool:
        return self._combat_view.get("can_advance", False)

    @Property(bool, notify=combatViewChanged)
    def allCombatResolved(self) -> bool:
        return self._combat_view.get("all_resolved", False)

    @Property(str, notify=combatViewChanged)
    def combatSelectedWarId(self) -> str:
        return self._combat_view.get("selected_war_id", "")

    @Property(bool, notify=combatViewChanged)
    def hasActiveWars(self) -> bool:
        wars = self._combat_view.get("active_wars", [])
        return len(wars) > 0

    @Property(list, notify=combatViewChanged)
    def combatResolvedWarCards(self) -> List[Dict[str, Any]]:
        return self._combat_view.get("resolved_war_cards", [])

    @Property(list, notify=combatViewChanged)
    def combatResolvedWarIds(self) -> List[str]:
        return self._combat_view.get("resolved_war_ids", [])

    @Property(list, notify=combatViewChanged)
    def combatAllWarCards(self) -> List[Dict[str, Any]]:
        """war_slots 有序列表（含 None 占位）用于 QML Repeater。

        P1-01：优先读 get_combat_view 的 war_slots（槽位身份 + 有序 DTO，含 None 占位）；
        字段缺失时退回旧 active + truce + resolved（防旧存档/旧证据回放崩溃）。
        presentation_state 由 L2 卡构建层（get_combat_view）产出，随卡 dict 原样透传。
        """
        war_slots = self._combat_view.get("war_slots")
        if war_slots is not None:
            return war_slots
        active = self._combat_view.get("active_wars", [])
        truce = self._combat_view.get("truce_wars", [])
        resolved = self._combat_view.get("resolved_war_cards", [])
        return active + truce + resolved

    @Property(dict, notify=combatViewChanged)
    def combatResult(self) -> Dict[str, Any]:
        return self._combat_result

    @Property(dict, notify=combatViewChanged)
    def combatBattleResultDetail(self) -> Dict[str, Any]:
        results = self._combat_view.get("battle_results", [])
        return results[0] if results else {}

    @Property(int, notify=combatViewChanged)
    def combatFleetCount(self) -> int:
        # R1-G-08（WP-G-R1 v1.6 §2.8）：重绑定为权威全局 `built_fleet_count`（AVAILABLE +
        # ON_MISSION，排除 BUILDING）；旧 `fleet_count` key 仅作回退（旧存档/旧证据回放）
        return self._combat_view.get(
            "built_fleet_count", self._combat_view.get("fleet_count", 0)
        )

    @Property(int, notify=combatViewChanged)
    def combatAvailableLegions(self) -> int:
        return self._combat_view.get("available_legion_count", 0)

    @Property(int, notify=combatViewChanged)
    def combatMobilizedLegions(self) -> int:
        """WP-F R2-02：权威已动员军团数（MilitarySystem.get_active_legions()，含 TRUCE 附着
        ACTIVE 与未指派 ACTIVE；语义区别于 combatAvailableLegions 可征召池），只读透传 int。"""
        return self._combat_view.get("mobilized_legion_count", 0)

    @Property(dict, notify=queryResultChanged)
    def globalQueryResult(self) -> Dict[str, Any]:
        return self._global_query_result

    @Property(bool, notify=queryGuardChanged)
    def queryGuarded(self) -> bool:
        """viewer/handoff/reset invalidation barrier 是否持有（数据操作禁用）。"""
        return self._query_guard

    @Property(int, notify=queryGuardChanged)
    def queryInvalidationEpoch(self) -> int:
        """当前 invalidation epoch。真实 receiver 完成 reset 后须回写该值作为 ack
        （v1.2 §2.1 step 3，A3/F2）。"""
        return self._query_epoch

    @Slot(int)
    def ackQueryInvalidation(self, epoch: int) -> None:
        """Receiver-completion ack（真实 QML Overlay.resetForInvalidation 完成后调用）。

        仅当回写 epoch == 当前 epoch 时记为有效；stale / queued / 无 receiver 的
        ack 一律忽略（_query_invalidation_ack 保持 -1）→ Store 侧 fail closed。
        """
        try:
            epoch = int(epoch)
        except (TypeError, ValueError):
            return
        if epoch == self._query_epoch:
            self._query_invalidation_ack = epoch

    # -----------------------------------------------------------------------
    # Resolution stage properties
    # -----------------------------------------------------------------------
    @Property(dict, notify=resolutionViewChanged)
    def resolutionView(self) -> Dict[str, Any]:
        return self._resolution_view

    @Property(dict, notify=resolutionViewChanged)
    def resolutionResults(self) -> dict:
        return self._resolution_view.get("results", {})

    @Property(list, notify=resolutionViewChanged)
    def resolutionWarnings(self) -> list:
        return self._resolution_view.get("warnings", [])

    @Property(dict, notify=resolutionViewChanged)
    def resolutionSummary(self) -> dict:
        return self._resolution_view.get("summary", {})

    @Property(bool, notify=resolutionViewChanged)
    def resolutionResolved(self) -> bool:
        return self._resolution_view.get("resolved", False)

    @Property(bool, notify=resolutionViewChanged)
    def isResolutionResolving(self) -> bool:
        return self._resolution_resolving

    @Property(bool, notify=resolutionViewChanged)
    def canAdvanceResolution(self) -> bool:
        """是否可以推进下一年度（结算完成 + 当前玩家 + 非推进中 + 非分派中）"""
        if not self._resolution_view:
            return False
        resolved = self._resolution_view.get("resolved", False)
        is_current = self._resolution_view.get("is_current_player", False)
        return resolved and is_current and not self._resolution_resolving and not self._resolution_advancing

    @Property(dict, notify=snapshotChanged)
    def factionStyleMap(self) -> Dict[str, Any]:
        """FC-712-17/20 — SESSION_DISPLAY faction style map for the CURRENT seat.

        The public value is always the projection of the CURRENT viewer: it is
        emptied on neutralize (masked/pending/failure) and replaced by the
        target's own staged bundle on activation.
        """
        return self._faction_style_map

    @Property(bool, notify=snapshotChanged)
    def factionStyleMapStale(self) -> bool:
        """True when the style map is the private last_good, not fresh data."""
        return bool(self._stale_resources.get("factionStyleMap"))

    @Property(bool, notify=snapshotChanged)
    def projectionStale(self) -> bool:
        """True when ANY projected resource is served from last_good."""
        return any(bool(flag) for flag in self._stale_resources.values())

    @Property(list, notify=snapshotChanged)
    def staleResourceIds(self) -> List[str]:
        """Resource ids currently served from the private last_good cache."""
        return sorted(rid for rid, flag in self._stale_resources.items() if flag)

    def _stale_write_dependencies(self) -> List[str]:
        """R05 — the REQUIRED resources that are currently served from last_good.

        Dependency-driven: ONLY resources declared ``required`` in the activation
        inventory can gate a write (a purely transient/optional projection never
        does), and EVERY such resource can — not just the style map.
        """
        return sorted(rid for rid in self._required_resource_ids()
                      if self._stale_resources.get(rid))

    @Property(bool, notify=snapshotChanged)
    def freshnessWritesBlocked(self) -> bool:
        """FC-712-18 / R05 — freshness-dependent writes are disabled while stale.

        The predicate is DEPENDENCY-RELATED (per REQUIRED resource), not a style
        proxy: an ACTIVE seat served from ANY stale REQUIRED projection (style,
        population, senate, ...) may not start a NEW command. The gate is applied
        BEFORE any side effect (``_begin_masked_seat_transition``), so a refused
        write never reaches Core (no lease, no receipt, no RNG draw); the only
        bounded action left is a fresh refresh / activation.
        """
        return bool(self._stale_write_dependencies())

    @staticmethod
    def _read_outcome(envelope: Any) -> tuple:
        """FC-712-19 — classify one raw read envelope.

        Returns ``(ok, data)``. ``ok`` is True ONLY for a real success whose
        payload is a mapping. A DENIED (``success`` False), a malformed envelope
        (non-dict / non-boolean success), and ``data is None`` / non-mapping are
        all failures; ``success is True`` with ``data == {}`` is a LEGAL EMPTY.
        """
        if not isinstance(envelope, dict):
            return False, {}
        if envelope.get("success") is not True:
            return False, {}
        data = envelope.get("data")
        if not isinstance(data, dict):
            return False, {}
        return True, data

    def _publish_private_read(self, resource_id: str, envelope: Any) -> Dict[str, Any]:
        """Consume one envelope for the CURRENT viewer.

        On success the fresh value is published and remembered as last_good.
        On failure the private last_good is retained (same viewer only) and the
        resource is marked stale; a foreign/no cache yields a neutral value.
        """
        ok, data = self._read_outcome(envelope)
        if ok:
            self._last_good_views[resource_id] = {"viewer": self._viewer_id,
                                                  "data": data}
            self._stale_resources.pop(resource_id, None)
            return data
        cached = self._last_good_views.get(resource_id) or {}
        self._stale_resources[resource_id] = True
        if cached.get("viewer") == self._viewer_id \
                and isinstance(cached.get("data"), dict):
            return cached["data"]
        return {}

    def _refresh_faction_style_map(self, viewer_id: Optional[str] = None):
        """FC-712-20 — target-aware guarded style read with private last_good."""
        vid = self._viewer_id if viewer_id is None else viewer_id
        envelope = self._adapter.get_faction_style_map_envelope(vid)
        ok, data = self._read_outcome(envelope)
        if ok and not _is_style_map_dto(data):
            ok = False
        if ok:
            self._faction_style_map = data
            self._last_good_views["factionStyleMap"] = {"viewer": vid,
                                                       "data": data}
            self._stale_resources.pop("factionStyleMap", None)
            return
        cached = self._last_good_views.get("factionStyleMap") or {}
        if cached.get("viewer") == vid and _is_style_map_dto(cached.get("data")):
            self._faction_style_map = cached["data"]
        else:
            self._faction_style_map = {}
        self._stale_resources["factionStyleMap"] = True

    @Property(bool, notify=resolutionAdvancingChanged)
    def isResolutionAdvancing(self) -> bool:
        """是否正在执行 advance_year（loading 状态）"""
        return self._resolution_advancing

    # -----------------------------------------------------------------------
    # 阶段推进统一分派
    # -----------------------------------------------------------------------
    _PHASE_ADVANCE_DISPATCH = {
        "mortality": {
            "can_attr": "canAdvanceMortality",
            "slot": "doAdvanceMortality",
            "label": "\u23ed\ufe0f 推进到收入阶段",
        },
        "revenue": {
            "can_attr": "canAdvanceRevenue",
            "slot": "doAdvanceRevenue",
            "label": "\u23ed\ufe0f 推进到广场",
        },
        "forum": {
            "can_attr": "canAdvanceForum",
            "slot": "doAdvanceForum",
            "label": "\u23ed\ufe0f 推进到人口阶段",
        },
        "population": {
            "can_attr": "canAdvancePopulation",
            "slot": "doAdvancePopulation",
            "label": "\u23ed\ufe0f 进入元老院阶段",
        },
        "senate": {
            "can_attr": "canAdvanceSenate",
            "slot": "doAdvanceSenate",
            "label": "\u23ed\ufe0f 推进到战斗阶段",
        },
        "combat": {
            "can_attr": "canAdvanceCombat",
            "slot": "doAdvanceCombat",
            "label": "\u23ed\ufe0f 推进到决断阶段",
        },
        "resolution": {
            "can_attr": "canAdvanceResolution",
            "slot": "doAdvanceResolution",
            "label": "\u23ed\ufe0f 进入下一年度",
        },
    }

    @Property(bool, notify=phaseChanged)
    def canAdvanceCurrentPhase(self) -> bool:
        dispatch = self._PHASE_ADVANCE_DISPATCH.get(self.selectedPhaseId)
        if not dispatch:
            return False
        return getattr(self, dispatch["can_attr"], False)

    @Property(str, notify=[phaseChanged, resolutionViewChanged])
    def advanceCurrentPhaseText(self) -> str:
        dispatch = self._PHASE_ADVANCE_DISPATCH.get(self.selectedPhaseId)
        if not dispatch:
            return "\u23ed\ufe0f 推进到下一阶段"
        # WP-E-G7R：resolution 按钮标签唯一化（E-05 单命令，无两段标签）——统一走 dispatch label
        return dispatch["label"]

    # -----------------------------------------------------------------------
    # QML Slot — 操作入口
    # -----------------------------------------------------------------------
    @Slot(int, int, result=dict)
    def doCampaign(self, figure_id: int, amount: int) -> dict:
        """举办庆典（单条目，DEPRECATED — 新代码请使用 doBatchCampaign）"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.campaign(self._viewer_id, figure_id, amount)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_population_view()
        return feedback

    @Slot(list, result=dict)
    def doBatchCampaign(self, entries: list) -> dict:
        """批量庆典赞助——原子提交。entries = [{"figure_id": int, "amount": int}, ...]"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.batch_campaign(self._viewer_id, entries)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_population_view()
        return feedback

    @Slot(str, int, result=dict)
    def doVote(self, office: str, figure_id: int) -> dict:
        """投票"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.vote(self._viewer_id, office, figure_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_population_view()
        return feedback

    @Slot(dict, result=dict)
    def submitPopulationVotes(self, selections: dict) -> dict:
        """WP-02b formal QML entry for fixed-five population voting."""
        # S-B: masked handoff authority path when a barrier provider is bound.
        if self._barrier_provider is not None:
            return self._masked_submit_population_votes(selections)
        if not self._viewer_id:
            return self._feedback(False, "Not initialized", "error")
        if self._population_vote_submitting:
            return self._feedback(False, "投票正在提交，请稍候", "warning")
        self._population_vote_submitting = True
        self.populationVoteSubmittingChanged.emit()
        self._begin_viewer_transaction()
        txn_ok = False
        try:
            feedback = self._adapter.submit_population_votes(self._viewer_id, dict(selections))
            self._raise_feedback(feedback)
            if feedback.get("success"):
                data = feedback.get("data", {}) or {}
                awaiting = data.get("awaiting_player_id")
                if awaiting:
                    self._set_viewer(awaiting)
                    self.handoffRequired.emit(awaiting)
                self._refresh_snapshot()
                self._refresh_population_view()
                self.phaseChanged.emit()
                txn_ok = True
            else:
                self._refresh_population_view()
            return feedback
        finally:
            self._end_viewer_transaction(txn_ok)
            self._population_vote_submitting = False
            self.populationVoteSubmittingChanged.emit()

    @Slot(result=dict)
    def doCompletePlayer(self) -> dict:
        """完成当前玩家的人口阶段操作。
        全部 HUMAN 完成 → resolve election；否则仅 HUMAN handoff。"""
        # S-B: masked handoff authority path when a barrier provider is bound.
        if self._barrier_provider is not None:
            return self._masked_do_complete_player()
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}

        self._begin_viewer_transaction()
        txn_ok = False
        try:
            all_humans_complete = self._adapter.all_human_population_votes_complete()

            if all_humans_complete:
                # 最后一个 HUMAN 完成后，进入唯一 resolution 入口。
                feedback = self._adapter.resolve_election()
                self._raise_feedback(feedback)
                self._refresh_snapshot()
                self._refresh_population_view()
                self._refresh_senate_view()
                txn_ok = bool(feedback.get("success"))
                return feedback

            # 仍有 HUMAN 未完成：只在人类之间 handoff。
            feedback = self._adapter.next_player(self._viewer_id)
            self._raise_feedback(feedback)
            if feedback.get("success"):
                new_id = feedback.get("data", {}).get("new_player_id")
                if new_id:
                    self._set_viewer(new_id)
                    self.handoffRequired.emit(new_id)
                self._refresh_snapshot()
                self._refresh_population_view()
                txn_ok = True
            return feedback
        finally:
            self._end_viewer_transaction(txn_ok)

    @Slot(result=dict)
    def doResolveElection(self) -> dict:
        """结算选举"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.resolve_election()
        self._raise_feedback(feedback)
        self._refresh_snapshot()
        if feedback.get("success"):
            self._selected_phase_id = "population"
            self._selected_phase_summary = self._summary_from_phase(
                self._phase_by_id("population")
            )
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self.phaseChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvancePopulation(self) -> dict:
        """确认人口阶段结果并切换到元老院阶段视图。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        # item3 §2a S1: when a barrier provider is bound (production async host)
        # the population->senate advance runs through the SAME masked owning-flow
        # machine the senate commands use, so the owning dispatch (and thus the
        # senate terminal gate) is available to the continuation. Legacy unchanged.
        if self._barrier_provider is not None:
            return self._masked_senate_owning_flow(
                "advancePopulation", "advance_population_phase",
                lambda: self._adapter.advance_population(self._viewer_id))
        if not self.canAdvancePopulation:
            feedback = self._feedback(False, "人口阶段尚未完成，无法推进", "error")
            self._raise_feedback(feedback)
            return feedback

        # Call adapter -> session_api.advance_population_phase()
        feedback = self._adapter.advance_population(self._viewer_id)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._selected_phase_id = "senate"
            self._selected_phase_summary = self._summary_from_phase(self._phase_by_id("senate"))
            self._refresh_senate_view()
            self.phaseChanged.emit()
        self._raise_feedback(feedback)
        return feedback

    @Slot(result=dict)
    def doExecuteMortality(self) -> dict:
        """执行天命阶段。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.execute_mortality(self._viewer_id)
        if feedback.get("success"):
            self._mortality_result = feedback.get("data", {}) or {}
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
        self._raise_feedback(feedback)
        self.mortalityViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceMortality(self) -> dict:
        """确认天命结果并进入收入阶段。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.advance_mortality(self._viewer_id)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
        self._raise_feedback(feedback)
        self.mortalityViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doExecuteRevenue(self) -> dict:
        """执行收入结算。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.settle_revenue(self._viewer_id)
        if feedback.get("success"):
            self._revenue_result = feedback.get("data", {}) or {}
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
            self._refresh_revenue_view()
            self._refresh_forum_view()
        self._raise_feedback(feedback)
        self.revenueViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceRevenue(self) -> dict:
        """确认收入结算并推进到广场阶段。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.advance_revenue(self._viewer_id)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
            self._refresh_revenue_view()
            self._refresh_forum_view()
        self._raise_feedback(feedback)
        self.revenueViewChanged.emit()
        return feedback

    @Slot(int, result=dict)
    def doRetireFigure(self, figure_id: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.retire_figure(self._viewer_id, figure_id)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(int, int, result=dict)
    def doRecruitFigure(self, figure_id: int, amount: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.recruit_figure(self._viewer_id, figure_id, amount)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(int, int, int, result=dict)
    def doPlaceBid(self, figure_id: int, contract_id: int, amount: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.place_bid(self._viewer_id, figure_id, contract_id, amount)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(int, int, int, int, result=dict)
    def doPlaceFleetBid(self, figure_id: int, contract_id: int, amount: int,
                        construction_cost: int) -> dict:
        """R3-G-03（§3.5，FROZEN）：Fleet 竞标四整数 Slot——bid amount（C）与 intended
        construction cost（D）双独立输入原样透传 adapter（保留 doPlaceBid 3 整数 Slot 供
        tax/普通工程，避免 QML overload 歧义）。提交成功 refresh 后 pending 回显 API 的
        D/profit（非本地假计算）。"""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.place_bid(
            self._viewer_id, figure_id, contract_id, amount,
            construction_cost=construction_cost,
        )
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(int, int, result=dict)
    def doBuyLand(self, figure_id: int, amount: int) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.buy_land(self._viewer_id, figure_id, amount)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(str, bool, result=dict)
    def doVoteTriumph(self, war_id: str, vote: bool) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.vote_triumph(self._viewer_id, war_id, vote)
        self._raise_feedback(feedback)
        self._refresh_forum_view()
        return feedback

    @Slot(result=dict)
    def doCompleteForumStep(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        # D2 (FC-D2-03/04/05): under the bound production barrier provider the
        # retirement substep finish runs through the SAME masked seat-handoff
        # machine as the population path, so a cursor move to the next HUMAN is
        # paired with the seat-authority handoff IN ONE TRANSACTION (no bare
        # cursor move, no stale-viewer read). The legacy synchronous path (no
        # provider) is byte-for-byte unchanged below.
        if self._barrier_provider is not None and self.forumCurrentStep == "retirement":
            return self._masked_forum_finish("doCompleteForumStep", "retirement")
        # R11-F03: the public finish must pass the ONE controlled seat authority
        # BEFORE any ledger/receipt mutation (an old/masked/non-current invocation
        # can no longer mutate completion truth first).
        denied = self._authorize_public_finish("doCompleteForumStep")
        if denied is not None:
            self._raise_feedback(
                self._feedback(False, denied.get("message", ""), "error"))
            return denied
        if self.forumCurrentStep == "retirement":
            # S-C F4: record the CURRENT actor's LAWFUL retirement finish into the ONE
            # session ledger (owner completion via the coordinator), then let every
            # scheduled-AI controller finish its retirement (COMMON schedule, skip
            # satisfied before effects), so the forum owner's retirement barrier is
            # satisfied before the market is opened once. If another HUMAN's
            # retirement is still outstanding, hand off to that HUMAN (never a false
            # completion). The market OPEN itself remains the forum owner's operation.
            _rec = self._record_forum_ledger_finish(
                self._viewer_id, "retirement", "doCompleteForumStep:retirement")
            if not _rec.get("success"):
                # §4.3: an unsuccessful completion is a continuation failure — do
                # NOT run AI work / hand off / open the market on a failed record.
                feedback = self._feedback(
                    False, "退休完成未记录（请重试）", "warning")
                self._raise_feedback(feedback)
                return feedback
            self._process_ai_factions_forum("retirement")
            _next = self._advance_forum_to_next_human("retirement")
            if _next.get("status") == "BLOCKED":
                # D16 (FC-D16-03/05/09): a failed selection NEVER opens the market
                # and never invents a completion. The lawful own-seat finish above is
                # kept; the other seats stay outstanding for the next legal retry.
                feedback = self._feedback(
                    False, "退休完成交接失败，请重试", "warning")
                feedback["errors"] = [_next.get("error")]
                self._refresh_forum_view()
                self._raise_feedback(feedback)
                return feedback
            if _next.get("status") == "NEXT_HUMAN":
                self._refresh_forum_view()
                feedback = self._feedback(
                    False, "尚有其他玩家的退休操作未完成", "warning")
                self._raise_feedback(feedback)
                return feedback
            feedback = self._adapter.open_forum_market(self._viewer_id)
            if feedback.get("success"):
                self._forum_step_override = "market"
            self._refresh_forum_view()
            self._raise_feedback(feedback)
            return feedback
        return self.doResolveForum()

    def _authorize_public_finish(self, command: str) -> Optional[dict]:
        """R11-F03: route a public forum FINISH through the ONE controlled seat
        authority BEFORE any ledger/receipt mutation.

        This invokes the SHARED session-access predicate (the trusted routing layer
        explicitly PRESENTS the service handle via
        :func:`session_access.current_caller_context`); it does NOT re-implement
        seat/lifecycle logic inside the Store (no competing authority) and does NOT
        relax the S-B guards. Returns the ordinary DENIED envelope when refused,
        else ``None``. A never-registered CLI/legacy state keeps the historical
        CLI exemption (the predicate allows it).
        """
        ctx = session_access.current_caller_context(self._state)
        decision = session_access.authorize_public(
            self._state, session_access.OP_MUTATE, command=command,
            target_player_id=self._viewer_id, caller_context=ctx)
        if decision.allowed:
            return None
        return decision.denial()

    def _advance_forum_to_next_human(self, substep: str):
        """S-C F4 / D2 / D16: resolve ONE forum substep's next step as a TYPED
        three-value result (FC-D16-03) — never a bare actor / ``None``:

          * ``NEXT_HUMAN``      — another HUMAN is the canonical head; the caller
            pairs the cursor move with the seat handoff (sole writer: select_actor);
          * ``SUBSTEP_COMPLETE`` — every controller of THIS substep has no
            outstanding obligation and the schedule reported no error;
          * ``BLOCKED``         — snapshot error / unknown status / malformed
            selection / AI obligation still pending. A BLOCKED result forbids the
            same-seat follow-up (no open_market / resolve_forum / population).

        ``select_actor`` remains the ONLY cursor writer; no Core-cursor guessing and
        no political faction rotation.
        """
        from src.api import session_turn_service as _turn
        scope = _turn.mint_scope(self._state, "forum")
        sid = scope.scope_id

        def _blocked(reason):
            return {"status": "BLOCKED", "actor": None, "scope_id": sid,
                    "error": {"code": "FORUM_NEXT_ACTOR_FAILED",
                              "stage": "forum_select", "reason": reason}}

        try:
            snapshot = _turn.obligations(self._state, "forum")
        except Exception as exc:
            return _blocked(f"SNAPSHOT_ERROR:{type(exc).__name__}")
        if snapshot.errors:
            return _blocked(str(snapshot.errors[0]))
        outstanding = [o for o in snapshot.outstanding() if o.substep == substep]
        if not outstanding:
            return {"status": "SUBSTEP_COMPLETE", "actor": None,
                    "scope_id": sid, "error": None}
        target = outstanding[0]
        if target.controller == _turn.CONTROLLER_AI:
            return _blocked("AI_OBLIGATION_PENDING")
        if target.controller != _turn.CONTROLLER_HUMAN:
            return _blocked("NOT_EXECUTABLE")
        try:
            sel = _turn.select_actor(
                self._state, sid,
                expected_revision=_turn.current_revision(self._state))
        except Exception as exc:
            return _blocked(f"SELECT_EXCEPTION:{type(exc).__name__}")
        if not isinstance(sel, dict) or not sel.get("success"):
            reason = sel.get("reason") if isinstance(sel, dict) else "MALFORMED_SELECT"
            return _blocked(reason or "SELECT_FAILED")
        actor = sel.get("actor")
        if not actor:
            return _blocked("SELECT_EMPTY_ACTOR")
        if _turn.controller_of(self._state, actor) != _turn.CONTROLLER_HUMAN:
            return _blocked("SELECT_NOT_HUMAN")
        if actor != target.actor_player_id:
            return _blocked("SELECT_NOT_CANONICAL_HEAD")
        return {"status": "NEXT_HUMAN", "actor": actor, "scope_id": sid,
                "error": None}

    def _record_forum_ledger_finish(self, player_id: str, substep: str,
                                    command: str) -> dict:
        """S-C F4: record ONE lawful forum substep finish into the ONE session
        ledger via the coordinator's completion service (owner-recorded explicit
        finish) — never a cached Store boolean.

        §4.3: the finish is AUTHENTICATED by a real engine-issued owner receipt
        (the owner-declared no-action primitive is never called unauthenticated);
        the returned result is CHECKED by every caller.
        """
        from src.api import session_turn_service as _turn
        scope = _turn.mint_scope(self._state, "forum")
        oid = _turn._book(self._state).oid("forum", substep, ("player", player_id),
                                           scope.scope_id)
        # R10-2: the owner no-action finish carries an engine-issued owner-origin
        # credential (kind EXPLICIT_FINISH) — never an unauthenticated primitive call.
        receipt = _turn.issue_owner_receipt(
            self._state, command, actor_player_id=player_id,
            fact_ref=f"owner:{command}", scope_id=scope.scope_id,
            obligation_id=oid, kind=_turn.KIND_EXPLICIT_FINISH)
        return _turn.complete_actor(
            self._state, None, scope.scope_id, command,
            actor_player_id=player_id, phase="forum", substep=substep,
            satisfied_kind=_turn.KIND_EXPLICIT_FINISH, owner_receipt=receipt)

    def _record_forum_ai_completion(self, player_id: str, substep: str,
                                    outcome) -> dict:
        """S-C F4 / V11-F02: record ONE scheduled-AI forum substep completion into
        the ONE session ledger with the CORRECT satisfaction kind derived from the
        CHECKED owner outcome (no relabel at issuance, Errata §3.1.E conservation).

        * an ACCEPTED committed command outcome -> a receipt-bound ACTION carrying
          the immutable, exactly-bound real owner fact/receipt (the real command
          happened);
        * an owner-validated structural empty -> an owner-declared STRUCTURAL_NONE;
        * a genuine no-choice finish -> an owner-declared no-action
          (EXPLICIT_FINISH; no command happened).

        Never a cached Store boolean; every caller CHECKS the returned result.
        """
        from src.api import session_turn_service as _turn
        scope = _turn.mint_scope(self._state, "forum")
        oid = _turn._book(self._state).oid(
            "forum", substep, ("player", player_id), scope.scope_id)
        kind = getattr(outcome, "kind", "")
        command_id = getattr(outcome, "command_id", "") or f"ai-forum:{substep}"
        if kind == _turn.OUTCOME_ACCEPTED:
            receipt = _turn.issue_owner_receipt(
                self._state, command_id, actor_player_id=player_id,
                fact_ref=f"ai-receipt:{command_id}", scope_id=scope.scope_id,
                obligation_id=oid, kind=_turn.KIND_ACTION)
            return _turn.complete_actor(
                self._state, None, scope.scope_id, command_id,
                obligation_id=oid, actor_player_id=player_id, phase="forum",
                substep=substep, satisfied_kind=_turn.KIND_ACTION,
                authoritative_fact_ref=f"ai-receipt:{command_id}",
                owner_receipt=receipt)
        if kind == _turn.OUTCOME_STRUCTURAL_EMPTY:
            return _turn.complete_actor(
                self._state, None, scope.scope_id, command_id,
                obligation_id=oid, actor_player_id=player_id, phase="forum",
                substep=substep, satisfied_kind=_turn.KIND_STRUCTURAL_NONE,
                owner_declared=True)
        receipt = _turn.issue_owner_receipt(
            self._state, command_id, actor_player_id=player_id,
            fact_ref=f"owner:{command_id}", scope_id=scope.scope_id,
            obligation_id=oid, kind=_turn.KIND_EXPLICIT_FINISH)
        return _turn.complete_actor(
            self._state, None, scope.scope_id, command_id,
            obligation_id=oid, actor_player_id=player_id, phase="forum",
            substep=substep, satisfied_kind=_turn.KIND_EXPLICIT_FINISH,
            owner_receipt=receipt)

    @Slot(result=dict)
    def doResolveForum(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        # D2 (FC-D2-03/04/05): the market substep finish runs through the SAME
        # masked seat-handoff machine (the market settlement remains the recovered
        # same seat's follow-up when there is no next HUMAN).
        if self._barrier_provider is not None:
            return self._masked_forum_finish("doResolveForum", "market")
        # R11-F03: the public finish must pass the ONE controlled seat authority
        # BEFORE any ledger/receipt mutation (an old/masked/non-current invocation
        # can no longer mutate completion truth first).
        denied = self._authorize_public_finish("doResolveForum")
        if denied is not None:
            self._raise_feedback(
                self._feedback(False, denied.get("message", ""), "error"))
            return denied

        # S-C F4: record the CURRENT actor's lawful MARKET finish, then every
        # scheduled-AI market finish (COMMON schedule, skip satisfied before
        # effects), so the forum owner's market barrier holds before the market is
        # settled. If another HUMAN's market obligation is outstanding, hand off to
        # that HUMAN (never a false completion). Replaces the old cache-flag net.
        _rec = self._record_forum_ledger_finish(
            self._viewer_id, "market", "doResolveForum:market")
        if not _rec.get("success"):
            # §4.3: the market settlement must not proceed when the owner market
            # finish was not recorded.
            feedback = self._feedback(False, "市场完成未记录（请重试）", "warning")
            self._raise_feedback(feedback)
            return feedback
        self._process_ai_factions_forum("market")
        _next = self._advance_forum_to_next_human("market")
        if _next.get("status") == "BLOCKED":
            # D16 (FC-D16-03/05/09): zero resolve_forum / zero population advance.
            feedback = self._feedback(
                False, "市场完成交接失败，请重试", "warning")
            feedback["errors"] = [_next.get("error")]
            self._refresh_forum_view()
            self._raise_feedback(feedback)
            return feedback
        if _next.get("status") == "NEXT_HUMAN":
            self._refresh_forum_view()
            feedback = self._feedback(
                False, "尚有其他玩家的市场操作未完成", "warning")
            self._raise_feedback(feedback)
            return feedback

        feedback = self._adapter.resolve_forum()
        if feedback.get("success"):
            self._forum_result = feedback
            self._forum_step_override = "resolution"
        self._raise_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_forum_view()
        return feedback

    # -----------------------------------------------------------------------
    # AI Forum Processing
    # -----------------------------------------------------------------------
    def _process_ai_factions_forum(self, substep: str = "market") -> None:
        """S-C F4: drive the COMMON schedule's scheduled-AI forum controllers through
        their phase-owner operations and record each one's LAWFUL finish (explicit
        legal finish) into the ONE session ledger via the completion service.

        ``substep`` is ``"retirement"`` or ``"market"``. The obligations are read
        from the single derived schedule (``session_turn_service.obligations``): only
        the OUTSTANDING actual-AI obligations for this substep are driven, a
        satisfied ``OID`` is skipped BEFORE any effect (no retry replay), and other
        HUMAN seats are NEVER processed as AI. The structured processor outcome is
        CHECKED: a failure / ``None`` / exception is NOT recorded as satisfied (the
        obligation stays outstanding for recovery) — there is NO cache flag and NO
        flag-based success after a failure.
        """
        from src.api import session_turn_service as _turn
        scope = _turn.mint_scope(self._state, "forum")
        snapshot = _turn.obligations(self._state, "forum")
        # §4.3: honour the SINGLE common schedule's canonical next-obligation stop.
        # Within this substep, once a pending HUMAN obligation is reached in
        # canonical order, STOP — do NOT run AI work that comes after it (the
        # caller hands off to that HUMAN; never "every AI first, then a HUMAN").
        targets = []
        for o in snapshot.outstanding():
            if o.substep != substep:
                continue
            if o.controller == _turn.CONTROLLER_HUMAN:
                break
            if o.controller == _turn.CONTROLLER_AI:
                targets.append(o)
        if not targets:
            # passive legacy mirror only (never an authority/gate)
            self._forum_ai_processed = True
            return

        processor = AutoPlayerProcessor(
            self._state,
            retirement_decider=AutoRetirementDecider(self._state),
            recruitment_decider=AutoRecruitmentDecider(),
            bid_decider=AutoBidDecider(),
            triumph_decider=AutoTriumphDecider(),
        )

        failed = False
        for ob in targets:
            ai_player = self._state.get_player(ob.actor_player_id)
            if ai_player is None:
                failed = True
                continue
            ai_faction = self._state.get_faction(ai_player.faction_id)
            if not ai_faction:
                logger.warning(
                    "AI player has no faction, skipping forum processing",
                    extra={"player_id": ai_player.player_id},
                )
                failed = True
                continue
            # skip a satisfied OID BEFORE effects (defensive; the snapshot already
            # excluded it) — a completed seat's business work is never replayed.
            if _turn._book(self._state).satisfied(
                    ob.obligation_id, scope.scope_id,
                    _turn.current_revision(self._state)):
                continue
            logger.info(
                "Processing AI forum actions",
                extra={"player_id": ai_player.player_id,
                       "faction_id": ai_faction.id, "substep": substep},
            )
            try:
                if substep == "retirement":
                    outcome = _turn.run_scheduled_actor(
                        self._state, "forum", ai_player.player_id,
                        processor.process_retirement, ai_player.player_id, ai_faction,
                        scope_id=scope.scope_id)
                else:
                    outcome = _turn.run_scheduled_actor(
                        self._state, "forum", ai_player.player_id,
                        processor.process_market, ai_player.player_id, ai_faction,
                        scope_id=scope.scope_id)
            except Exception as e:
                # An exception is NOT completion: the obligation stays outstanding.
                logger.exception(
                    f"AI forum {substep} processing failed for {ai_faction.name}: {e}"
                )
                failed = True
                continue
            if outcome is None or getattr(outcome, "is_failure", False):
                # Structured failure is NOT completion (no flag-based success).
                logger.warning(
                    f"AI forum {substep} step did not succeed for {ai_faction.name}"
                )
                failed = True
                continue
            # V11-F02: DISTINGUISH an ACCEPTED committed command outcome (-> an
            # immutable, exactly-bound ACTION fact/receipt) from a genuine no-choice
            # / owner-validated structural empty (-> a lawful owner no-action
            # declaration). No relabel at issuance.
            _air = self._record_forum_ai_completion(
                ai_player.player_id, substep, outcome)
            if not _air.get("success"):
                # §4.3: a completion that was NOT recorded is a failure — the seat
                # stays outstanding for recovery (never a false satisfied).
                failed = True
        # Passive legacy mirror only — NEVER an authority/gate, and NEVER set after a
        # failure (F4: no flag-based success).
        self._forum_ai_processed = not failed

    # -----------------------------------------------------------------------
    # Cache Reset Helper
    # -----------------------------------------------------------------------
    def _reset_phase_caches(self) -> None:
        """清除所有阶段缓存字段。幂等——适用于年度推进、观众切换和初始化。

        EOR20261011-01 S1：barrier 为第一动作（v1.2 §2.1）；嵌套在 viewer 事务内时
        继承其 keep_open 意图，不丢失待处理 query ID/open 意图。
        """
        self._guard_enter()
        try:
            self._invalidate_global_query("reset", keep_open=False)
        finally:
            self._guard_exit()
        self._forum_result = {}
        self._forum_step_override = ""
        self._forum_ai_processed = False
        self._mortality_result = {}
        self._revenue_result = {}
        self._combat_result = {}
        self._last_reset_turn = self.turnNumber
        self._refresh_forum_view()

    # -----------------------------------------------------------------------
    # Forum stage Slot — Advance
    # -----------------------------------------------------------------------
    @Slot(result=dict)
    def doExecuteForum(self) -> dict:
        """Execute the forum settlement without advancing the phase."""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.execute_forum(self._viewer_id)
        if feedback.get("success"):
            self._forum_result = feedback.get("data", {}) or {}
            self._refresh_snapshot()
            self._refresh_forum_view()
        self._raise_feedback(feedback)
        self.forumViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceForum(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.advance_forum(self._viewer_id)
        if feedback.get("success"):
            self._forum_step_override = ""
            self._refresh_snapshot()
            self._refresh_forum_view()
            self._refresh_population_view()
        self._raise_feedback(feedback)
        self.forumViewChanged.emit()
        return feedback

    # -----------------------------------------------------------------------
    # Combat stage Slot
    # -----------------------------------------------------------------------
    @Slot(str, result=dict)
    def doSelectWar(self, war_id: str) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        from src.api import combat_api
        feedback = self._adapter.call(combat_api.select_war, self._state, self._viewer_id, war_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_combat_view()
        self.combatViewChanged.emit()
        return feedback

    @Slot(str, str, result=dict)
    def doCombatAction(self, war_id: str, action: str) -> dict:
        """Execute a combat action. Only 'attack' is supported (FUNC-03 attack-only).

        scout/defence are DEPRECATED: the GUI no longer exposes them, and this
        Slot hard-rejects any non-attack action as a frontend-side fail-safe.
        """
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if action != "attack":
            feedback = self._feedback(False, "仅支持进攻操作（attack）", "error")
            self._raise_feedback(feedback)
            self.combatViewChanged.emit()
            return feedback
        feedback = self._adapter.do_combat_action(self._viewer_id, war_id, action)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._combat_result = feedback.get("data", {}) or {}
            self._refresh_snapshot()
            self._refresh_combat_view()
        else:
            # WP-G-R4（SA v1.7 §3.3）：readiness 拒绝 → 只读刷新 + 结构化 feedback 原因；
            # 不把失败 data 写进 _combat_result 当 battle victory/defeat（R4-04）
            data = feedback.get("data") or {}
            if data.get("code") in ("NAVAL_NOT_READY", "NAVAL_SYSTEM_UNAVAILABLE"):
                self._combat_result = {}
                self._refresh_combat_view()
        self.combatViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doConfirmBattleResult(self) -> dict:
        """Acknowledge battle result, return to SELECT or go to ADVANCE."""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        feedback = self._adapter.confirm_battle_result(self._viewer_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_combat_view()
        self.combatViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceCombat(self) -> dict:
        """Advance to Resolution phase."""
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if not self.canAdvanceCombat:
            feedback = self._feedback(False, "尚有未结算的战争", "error")
            self._raise_feedback(feedback)
            return feedback
        feedback = self._adapter.advance_combat(self._viewer_id)
        self._raise_feedback(feedback)
        if feedback.get("success"):
            self._selected_phase_id = "resolution"
            self._selected_phase_summary = self._summary_from_phase(
                self._phase_by_id("resolution")
            )
            self.phaseChanged.emit()
        self.combatViewChanged.emit()
        return feedback

    # -----------------------------------------------------------------------
    # Resolution stage Slot
    # -----------------------------------------------------------------------
    @Slot(result=dict)
    def doAdvanceResolution(self) -> dict:
        """单命令年度推进（E-05 / D2 §2.1）：一键 → advance_year 恰好一次 → 直连 Mortality。

        成功分支直接导航 mortality（删除原第二段导航分支）；失败分支停留 resolution +
        刷新 view（advancing 复位 → 可重试，EC-09）；finally 补发 phaseChanged（P0 修复：
        闭合 QML 按钮绑定 notify 缺口，对照 _executeResolution finally 既有模式）。
        """
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if self._resolution_advancing:                      # 重入 guard（双击/重复分派，EC-08）
            feedback = self._feedback(False, "正在推进中，请稍候", "warning")
            self._raise_feedback(feedback)
            return feedback

        if not self.canAdvanceResolution:                    # 结算未完成前置
            feedback = self._feedback(False, "决算尚未完成，无法推进", "error")
            self._raise_feedback(feedback)
            return feedback

        self._resolution_advancing = True
        self.resolutionAdvancingChanged.emit()
        self.resolutionViewChanged.emit()

        try:
            # 权威推进唯一入口（恰好一次；game_api.advance_year 内部重入 guard + 原子性保留）
            feedback = self._adapter.advance_year(self._viewer_id)
            if feedback.get("success"):
                # ── 单命令：直接导航 Mortality（原第二段导航分支已删除）──
                self._reset_phase_caches()
                self._refresh_snapshot()   # executed_phases 已清 → snapshot 重同步 current_phase_id=mortality
                self._selected_phase_id = "mortality"
                self._selected_phase_summary = self._summary_from_phase(
                    self._phase_by_id("mortality")
                )
                self.phaseChanged.emit()                    # 通知按钮绑定 + 阶段导航
                self._raise_feedback(
                    self._feedback(True, "已进入下一年度（天命阶段）", "success")
                )
            else:
                # 失败：停留 resolution，刷新 view，advancing 复位 → 可重试（EC-09）
                logger.warning(f"Year advance failed: {feedback.get('message')}")
                self._refresh_resolution_view()
                self._raise_feedback(feedback)
            return feedback
        finally:
            self._resolution_advancing = False
            self.resolutionAdvancingChanged.emit()
            self.resolutionViewChanged.emit()
            self.phaseChanged.emit()                        # ← P0 修复：finally 补发，闭合 notify 缺口

    @Slot(result=dict)
    def doAdvanceCurrentPhase(self) -> dict:
        """Unified dispatch: advance button based on selectedPhaseId（WP-E-G7R：
        resolution 分派到单命令 doAdvanceResolution——一键直达 Mortality）。"""
        phase_id = self.selectedPhaseId
        if phase_id == "mortality":
            return self.doAdvanceMortality()
        elif phase_id == "revenue":
            return self.doAdvanceRevenue()
        elif phase_id == "forum":
            return self.doAdvanceForum()
        elif phase_id == "population":
            return self.doAdvancePopulation()
        elif phase_id == "senate":
            return self.doAdvanceSenate()
        elif phase_id == "combat":
            return self.doAdvanceCombat()
        elif phase_id == "resolution":
            return self.doAdvanceResolution()
        else:
            return {"success": False, "message": f"\u672a\u77e5\u9636\u6bb5: {phase_id}", "errors": [f"unknown phase: {phase_id}"]}

    def _variant_to_python(self, value):
        if hasattr(value, "toVariant"):
            return value.toVariant()
        if hasattr(value, "toPython"):
            return value.toPython()
        return value

    def _auto_finalize_after_submit(self, feedback: dict) -> None:
        """R6（SA §D.1，DA-4 B2）：Submit 零 Senate（空包 / direct-only）→ 委托服务端唯一
        finalization 完成协议自动结算。

        成功：正常态直接进入 RESULTS_READY（`can_advance`=True，唯一推进 = doAdvanceSenate）。
        失败（FINALIZATION_ERROR）：已发布包**不撤销**（`submitted/success` 保持 True），
        附 `finalization_error` + warning，UI 不允许重发包；仅内部恢复通道重试。
        """
        finalization = self._adapter.resolve_senate()
        data = feedback.get("data")
        if not isinstance(data, dict):
            data = {}
        feedback["data"] = data
        data["submitted"] = True
        finalization_data = finalization.get("data") or {}
        if finalization.get("success"):
            data["finalization"] = {
                "finalized": True,
                "finalization_id": finalization_data.get("finalization_id"),
                "completion_facts": finalization_data.get("completion_facts"),
                "replayed": bool(finalization_data.get("replayed")),
                "current_step": "results",
            }
            self._senate_finalization_warning = ""
        else:
            data["finalization"] = {
                "finalized": False,
                "finalization_id": finalization_data.get("finalization_id"),
                "current_step": "finalization_error",
            }
            error = finalization_data.get("finalization_error") or {}
            data["finalization_error"] = error
            data["warnings"] = list(data.get("warnings") or []) + [{
                "code": "FINALIZATION_ERROR",
                "message": finalization.get("message", ""),
            }]
            self._senate_finalization_warning = (
                "元老院 finalization 未完成（stage={stage}）：提案包已发布，"
                "请勿重复提交，稍后自动重试。").format(stage=error.get("stage", "?"))
        self._refresh_snapshot()
        self._refresh_senate_view()
        self.senateFinalizationWarningChanged.emit()

    def _apply_senate_submit_feedback(self, feedback: dict) -> None:
        """R6（SA §B.5，DA-2 B5）：把 Submit 反馈映射到 Store 结构化错误面。

        - 失败：`error_items` / `errors_by_scope` 来自 Adapter formatter（若无则就地
          归一）；由 `scope=war_id` 与 package 的 `details.claims/requests` 建
          `senateSubmitErrorsByWar` 相关卡关联。**不清除草稿**。
        - 成功：清空错误面；草稿在确认 package refs 后才切冻结只读（QML 侧）。
        """
        if feedback.get("success"):
            self._senate_submit_errors = []
            self._senate_submit_errors_by_war = {}
            self._senate_submit_errors_by_scope = {}
            self.senateSubmitErrorsChanged.emit()
            return
        error_items = feedback.get("error_items") or []
        errors_by_scope = feedback.get("errors_by_scope") or {}
        if not error_items:
            normalized = GuiApiAdapter.normalize_error_feedback(
                feedback.get("errors") or [], feedback.get("message") or "提交失败")
            error_items = normalized["error_items"]
            errors_by_scope = normalized["errors_by_scope"]
        self._senate_submit_errors = list(error_items)
        self._senate_submit_errors_by_scope = {k: list(v) for k, v in errors_by_scope.items()}
        by_war: Dict[str, List[Dict[str, Any]]] = {}
        for item in error_items:
            scope = str(item.get("scope") or "")
            if scope and scope != "package":
                by_war.setdefault(scope, []).append(item)
        for key, items in errors_by_scope.items():
            if key.startswith("war:"):
                by_war.setdefault(key[len("war:"):], []).extend(items)
        self._senate_submit_errors_by_war = by_war
        self.senateSubmitErrorsChanged.emit()

    # ------------------------------------------------------------------
    # D13（Option 4）— AI proposer UI-local guard
    # ------------------------------------------------------------------
    #: 元老院已知合法 step（身份同步只接受这些值；未知/空字段不构成「离开 proposal」）。
    _SENATE_STEPS = ("proposal", "senate_vote", "tribune_veto", "results",
                     "settlement_pending")
    #: AI 提案授权失败的可读说明（由既有反馈通道消费，不是 QML 属性）。
    AI_PROPOSER_BLOCK_REASON = "AI 执政官提案未能发布（授权失败），请报告缺陷。"

    def _senate_ai_proposer_origin(self) -> Optional[Any]:
        """调用前捕获的 origin 三元 `(session, step, viewer)`。

        只在 ACTIVE、proposal step、session/viewer 非空时返回；否则 None（不得
        制造空 key 锁）。不可在 cont / 拒绝处理重新读取 `_senate_view`——begin /
        dispatch 都会 neutralize。
        """
        if self._seat_lifecycle != SEAT_ACTIVE:
            return None
        viewer = self._viewer_id
        view = self._senate_view
        if (not viewer or not self._is_valid_senate_projection(view, viewer)
                or view.get("current_step") != "proposal"):
            return None
        session = self._senate_session_identity()
        if session is None:
            return None
        return (session, "proposal", viewer)

    def _senate_session_identity(self) -> Optional[str]:
        """Core-owned identity, exactly as propose_many names the GUI session.

        The read DTO deliberately has no session id. Never substitute a viewer,
        draft, previous package, or guard key for an unavailable Core turn.
        """
        turn = getattr(self._state, "turn", None)
        number = getattr(turn, "turn_number", None)
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            return None
        return f"turn-{number}"

    def _is_valid_senate_projection(self, view: Any, viewer: str) -> bool:
        """Only a successful, viewer-bound Senate projection can release a lock."""
        if not isinstance(view, dict) or not view or not viewer:
            return False
        if view.get("success") is False:
            return False
        if view.get("denied") or view.get("masked") or view.get("placeholder"):
            return False
        if view.get("status") in ("denied", "masked", "masked_failure"):
            return False
        return (view.get("phase_id") == "senate"
                and view.get("viewer_player_id") == viewer
                and view.get("current_step") in self._SENATE_STEPS)

    def _clear_ai_proposer_guard(self, *, notify: bool = True) -> None:
        """唯一重置入口：同时归零 bool/reason/key，变更完成后才 emit（幂等）。"""
        changed = (self._senate_ai_proposer_blocked
                   or bool(self._senate_ai_proposer_blocked_reason)
                   or self._senate_ai_proposer_block_key is not None)
        self._senate_ai_proposer_blocked = False
        self._senate_ai_proposer_blocked_reason = ""
        self._senate_ai_proposer_block_key = None
        if changed and notify:
            self.senateViewChanged.emit()

    def _sync_ai_proposer_guard(self, view: Any, *,
                                target_id: Optional[str] = None) -> None:
        """用**有效发布/有效 ACTIVE 投影**同步锁：只在真实身份变化时统一清除。

        1. 真换 viewer：只有成功的显式 target 才是可信事实（staged final reveal）。
        2. 同 viewer：必须是有效 senate DTO（含已知合法 step）；真实会期改变或真正
           离开 proposal 才清除。
        空 / denied / masked / 未知字段一律保锁（不推断换会期/离开 proposal）。
        """
        if not self._senate_ai_proposer_blocked:
            return
        key = self._senate_ai_proposer_block_key
        if key is None:
            self._clear_ai_proposer_guard(notify=False)
            return
        if target_id and target_id != key[2]:
            self._clear_ai_proposer_guard(notify=False)
            return
        session = self._senate_session_identity()
        if session is None or not self._is_valid_senate_projection(view, key[2]):
            return
        if session != key[0] or view.get("current_step") != key[1]:
            self._clear_ai_proposer_guard(notify=False)

    @staticmethod
    def _is_ai_proposer_seat_denied(feedback: Any) -> bool:
        """仅真实 typed seat `DENIED`（success 显式 False）→ 可选 Option 4 锁。

        不匹配 message；普通校验 / PACKAGE_ALREADY_SUBMITTED / continuation 均 False。
        """
        if not isinstance(feedback, dict) or feedback.get("success") is not False:
            return False
        errors = feedback.get("errors")
        if not isinstance(errors, (list, tuple)):
            return False
        return any(isinstance(err, dict) and err.get("code") == "DENIED"
                   for err in errors)

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals) -> dict:
        """WP-D AU-1/AU-3：提案提交路由（执政官 → propose_many 0…N；非执政官 → AI proposer 0…N）。

        Path A（0 提案）：提交空批后 submitted_proposals 为空 → 直接 resolve_senate 空结算
        （record_phase_result → advance_senate_phase 可过，P2-01 resolve hook）。
        """
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        self._senate_finalization_warning = ""
        # W-09 / U5 (PL-02): a REGISTERED Hot-seat HUMAN submit is released ONLY
        # by the trusted viewer-bound DTO capability (``can_create_proposal``) on a
        # valid projection. A false/MISSING capability is refused (B1 / AC-W3-18);
        # it is NEVER re-derived locally from the obligation schedule (A-W3-04).
        # The never-registered CLI/legacy route below is byte-for-byte unchanged.
        from src.api import session_access as _sa_capability
        registered_capability = bool(_sa_capability.is_hotseat_registered(self._state))
        payload = self._variant_to_python(proposals)
        selected = []
        for item in payload or []:
            item = self._variant_to_python(item)
            if isinstance(item, dict):
                selected.append(item)
        # G7-W3 restore (C4): a REGISTERED submit is routed ONLY by the two
        # mutually exclusive viewer-bound DTO capabilities. Local obligations /
        # controller / ``viewer_has_consul`` never re-authorise the command; a
        # contradictory (both true) or absent authorisation fails closed.
        valid_projection = False
        ai_presenter_route = False
        if registered_capability:
            valid_projection = self._is_valid_senate_projection(
                self._senate_view, self._viewer_id)
            can_create_dto = bool(valid_projection and self.canCreateSenateProposal)
            can_trigger_ai_dto = bool(valid_projection
                                     and self.canTriggerAIProposer)
            if can_create_dto == can_trigger_ai_dto:
                feedback = self._feedback(
                    False, "当前提案权不属于本玩家，不能代替其他玩家/无主持人提案", "warning")
                self._raise_senate_feedback(feedback)
                self.senateViewChanged.emit()
                return feedback
            # R1 (C4): the STEP itself is a precondition of dispatch, not only the
            # capability bit. A registered projection that has left the proposal
            # step (results / completed / ballot / veto / settlement_pending) is
            # refused HERE, BEFORE any dispatch: no AI producer, no HUMAN submit,
            # no masked owning flow. A stale/affirmative capability bit can never
            # turn a non-proposal step into a trigger surface.
            if self._senate_view.get("current_step") != "proposal":
                feedback = self._feedback(
                    False, "当前会期已离开提案阶段，不能提交提案", "warning")
                _typed_errors = feedback.get("errors")
                if not isinstance(_typed_errors, list):
                    _typed_errors = []
                    feedback["errors"] = _typed_errors
                _typed_errors.append({
                    "code": "STEP_NOT_PROPOSAL",
                    "message": "当前会期已离开提案阶段，不能提交提案",
                })
                self._raise_senate_feedback(feedback)
                self.senateViewChanged.emit()
                return feedback
            ai_presenter_route = can_trigger_ai_dto
        if registered_capability and ai_presenter_route:
            # The real AI decision owner stays the AI: the presenter only confirms
            # the presentation. A D13-locked proposer refuses with ZERO dispatch
            # (retry after a typed DENIED never unlocks or resubmits, C6).
            if self.senateAiProposerBlocked:
                feedback = self._feedback(
                    False, self.AI_PROPOSER_BLOCK_REASON, "error")
                self._raise_senate_feedback(feedback)
                self.senateViewChanged.emit()
                return feedback
            from src.api import senate_api
            if self._barrier_provider is not None:
                # D13（Option 1）：AI proposer 也必须走同一 masked owning flow
                # ——否则 AI-child `propose_many`（viewer = AI consul）在注册
                # 热座下无 owning possession → DENIED（发布死锁）。origin 必须
                # 在 begin/neutralize **之前**捕获（cont 不再回读公共投影）。
                _ai_origin = self._senate_ai_proposer_origin()

                def _dispatch_ai_proposals():
                    submitted = self._adapter.call(
                        senate_api.auto_submit_proposals, self._state)
                    try:
                        self._apply_senate_submit_feedback(submitted)
                        if submitted.get("success"):
                            self._senate_drafts = {}
                    except Exception:  # pragma: no cover - defensive
                        logger.exception(
                            "masked AI senate submit bookkeeping failed")
                    return submitted
                return self._masked_senate_owning_flow(
                    "doSubmitSenateProposals", "propose_many",
                    _dispatch_ai_proposals,
                    ai_proposer_origin=_ai_origin)
            feedback = self._adapter.call(senate_api.auto_submit_proposals,
                                          self._state)
        elif registered_capability or self._senate_view.get(
                "viewer_has_consul", False):
            if registered_capability and not (
                    valid_projection and self.canCreateSenateProposal):
                feedback = self._feedback(
                    False, "当前提案权不属于本玩家，不能代替其他玩家/无主持人提案", "warning")
                self._raise_senate_feedback(feedback)
                self.senateViewChanged.emit()
                return feedback
            if self._barrier_provider is not None:
                # item3 §2a S2: the consul's proposal submission runs through the
                # masked owning-flow machine, so the owning dispatch enables the
                # senate terminal gate for the command's built-in continuation.
                # G5 I2-R3 R1 (O-2): the legacy submit-time BOOKKEEPING (structured
                # error surface + draft-cache reset on success) is re-applied inside
                # the owning dispatch. It touches ONLY Store-local UI state (no
                # guarded read), so it is scope-safe; the snapshot/view refresh is
                # provided by the masked activation's staged re-read.
                def _dispatch_proposals():
                    submitted = self._adapter.submit_senate_proposals(
                        self._viewer_id, selected)
                    try:
                        self._apply_senate_submit_feedback(submitted)
                        if submitted.get("success"):
                            self._senate_drafts = {}
                    except Exception:  # pragma: no cover - defensive
                        logger.exception("masked senate submit bookkeeping failed")
                    return submitted
                return self._masked_senate_owning_flow(
                    "doSubmitSenateProposals", "propose_many", _dispatch_proposals)
            feedback = self._adapter.submit_senate_proposals(self._viewer_id, selected)
        else:
            # S-C F1/A3-02 (delta §3.3#3): the Store must NOT route EVERY non-consul
            # viewer to the AI proposer. The COMMON schedule selects the actual office
            # owner first; the AI auto-proposer capability requires an ACTUAL AI
            # controller (the same rule applies to the veto path). A viewer who is the
            # actual HUMAN owner submits for themselves; otherwise the command is
            # refused (no submitting on another HUMAN's behalf).
            from src.api import session_turn_service as _turn
            from src.api import session_access as _sa
            snap = _turn.obligations(self._state, "senate")
            # §4.2: a schedule DERIVATION error must FAIL CLOSED (never NONE ->
            # auto-submit); an UNRESOLVED controller (NONE) must NOT be auto-played
            # on a REGISTERED Hot-seat session (NONE is not affirmative AI
            # authority). Only a never-registered (CLI/legacy) state keeps the
            # historical non-consul route.
            prop = next((o for o in snap.obligations if o.substep == "proposal"), None)
            prop_ctrl = prop.controller if prop is not None else _turn.CONTROLLER_NONE
            prop_actor = prop.actor_player_id if prop is not None else None
            if snap.errors:
                feedback = self._feedback(
                    False, "提案调度暂不可用，请稍后重试", "warning")
                self._raise_senate_feedback(feedback)
                self.senateViewChanged.emit()
                return feedback
            viewer_is_owner = (prop_ctrl == _turn.CONTROLLER_HUMAN
                               and prop_actor == self._viewer_id)
            if viewer_is_owner:
                feedback = self._adapter.submit_senate_proposals(self._viewer_id, selected)
            elif prop_ctrl == _turn.CONTROLLER_AI:
                # actual AI controller -> AI proposer is the decision maker
                from src.api import senate_api
                if self._barrier_provider is not None:
                    # D13（Option 1）：AI proposer 也必须走同一 masked owning flow
                    # ——否则 AI-child `propose_many`（viewer = AI consul）在注册
                    # 热座下无 owning possession → DENIED（发布死锁）。origin 必须
                    # 在 begin/neutralize **之前**捕获（cont 不再回读公共投影）。
                    _ai_origin = self._senate_ai_proposer_origin()

                    def _dispatch_ai_proposals():
                        submitted = self._adapter.call(
                            senate_api.auto_submit_proposals, self._state)
                        try:
                            self._apply_senate_submit_feedback(submitted)
                            if submitted.get("success"):
                                self._senate_drafts = {}
                        except Exception:  # pragma: no cover - defensive
                            logger.exception(
                                "masked AI senate submit bookkeeping failed")
                        return submitted
                    return self._masked_senate_owning_flow(
                        "doSubmitSenateProposals", "propose_many",
                        _dispatch_ai_proposals,
                        ai_proposer_origin=_ai_origin)
                # 无 provider：保留原语句与公共尾部（legacy CLI/历史路径不变）。
                feedback = self._adapter.call(senate_api.auto_submit_proposals, self._state)
            elif prop_ctrl == _turn.CONTROLLER_NONE and not _sa.is_hotseat_registered(self._state):
                # NEVER-REGISTERED compatibility path ONLY (legacy / non-PlayerType
                # fixture): preserve the historical non-consul route. A registered
                # Hot-seat with an unresolved live controller is refused below.
                from src.api import senate_api
                feedback = self._adapter.call(senate_api.auto_submit_proposals, self._state)
            else:
                feedback = self._feedback(
                    False, "当前提案权不属于本玩家，不能代替其他玩家/无主持人提案", "warning")
                self._raise_senate_feedback(feedback)
                self.senateViewChanged.emit()
                return feedback

        # SD1-V01 (N10-R): a post-commit AI-drain continuation MASKED_FAILURE
        # surfaced by ``submit_senate_proposals`` (→ ``propose_many`` →
        # ``continue_after_command`` → senate AI vote decider) must enter the
        # bounded CONTINUATION recovery route — never an ordinary non-mutating
        # business refusal (which re-stages the same seat at a new epoch) nor an
        # activation retry. The REAL producer envelope is recognised by
        # ``_is_masked_continuation_failure`` (``data.status == "masked_failure"``
        # / ``AI_DRAIN_MASKED_FAILURE``), so this binds the actual N10-R seam at
        # the post-commit failure boundary; the exact service authorization and
        # the post-commit meaning are preserved (the committed package is NOT
        # resubmitted; recovery resumes only outstanding AI work).
        if not feedback.get("success") and self._is_masked_continuation_failure(feedback):
            self._fail_masked(FAIL_AFTER_COMMIT, route=RECOVER_ROUTE_CONTINUATION)
            self._raise_senate_feedback(feedback)
            self.senateViewChanged.emit()
            return feedback

        # R6（SA §B.5，DA-2 B5）：**结构化错误单一显示路径 + draft 保留**。
        # 失败路径：不重建 defaults、不取消 checkbox、不 clamp、不换将（不调 _refresh_*
        # 重建视图）；下面先缓存本次逐 War 草稿（键 = session+war_id）。
        self._senate_draft_session_id = (self._senate_view.get("senate_session_id")
                                         or self._senate_draft_session_id or self._viewer_id)
        for _row in selected:
            if _row.get("war_id") is not None:
                self._senate_drafts[self.senate_draft_key(_row["war_id"])] = dict(_row)
        self._apply_senate_submit_feedback(feedback)
        self._raise_senate_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_senate_view()
            # 成功且确认 package refs（`_refresh_senate_view` 后 DTO 已含 submitted）
            # 才切冻结只读：清空 dirty draft 缓存与错误面。
            self._senate_drafts = {}
            # G7R（FC-R11-G7R-01/02）：单一 canonical「真实元老院提案存在」谓词——仅取发布闭包
            # 产出的 canonical refs `data["created"]`（== PackageRecord.proposal_refs）。
            # **禁**用 `data["proposals"]`（AI 展示/动作摘要，mixed-purpose）作存在性谓词；
            # **禁**任何 `created or proposals` 式兜底 / 第二存在性来源。
            canonical_real_senate_proposal_refs = (feedback.get("data") or {}).get("created") or []
            # R6（SA §D.1，DA-4 B2，supersede R4-09）：Submit 发布成功且 **Senate count == 0**
            # （显式空包 / direct-only）→ 委托服务端唯一完成协议 `finalize_senate_if_ready`
            # **自动执行一次内部政治 finalization**（真实非空成功 phase_result / PA / direct
            # 摘要；无 Vote/Veto、无「完成结算」按钮）。GUI 不再自持第二结算判断；
            # 唯一正常推进 = `doAdvanceSenate`。
            # 失败**不撤销已发布包**：仍 `submitted:true` + `success:true` + `finalization_error`
            # warning（状态落 FINALIZATION_ERROR、`can_advance=false`），UI 不允许重发包
            # （再提交由服务端 `PACKAGE_ALREADY_SUBMITTED` 拦截），仅可内部恢复重试。
            if not canonical_real_senate_proposal_refs:
                self._auto_finalize_after_submit(feedback)
        self.senateViewChanged.emit()
        return feedback

    @Slot("QVariant", result=dict)
    def doSubmitSenateVotes(self, agree_ids=None) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        proposals = self._senate_view.get("submitted_proposals", []) or []
        proposal_ids = [int(item.get("id")) for item in proposals if item.get("id") is not None]
        if not proposal_ids:
            feedback = self._feedback(False, "没有可表决的法案", "error")
            self._raise_senate_feedback(feedback)
            return feedback
        # WP-J Group C G7 Test R7 Delta（delta v2.3 / FC-C42）：**删除**硬编码全赞成 `[True ...]`；
        # `votes` 由玩家 ② 选择派生（`agree_ids` = ② 勾选集：勾选 = 同意 / 未勾选 = 否决）。
        # **向后兼容签名** `agree_ids=None`：None（无参调用）**不静默全赞成** ⇒ 所有提案按
        # **反对**处理（`False`），不再虚构赞成票（原则「不无参静默全赞成」）。
        # `proposal_ids` 仍取 `submitted_proposals`（不变）；长度天然一致（逐 pid 映射）。
        selectable = set()
        for item in (self._variant_to_python(agree_ids) or []):
            try:
                selectable.add(int(item))
            except (TypeError, ValueError):
                continue
        votes = [pid in selectable for pid in proposal_ids]
        if self._barrier_provider is not None:
            # item3 §2a S3: the vote submission runs through the masked owning-flow
            # machine (the owning dispatch enables the senate terminal gate).
            # G5 I2-R3 REWORK (S3): the legacy settlement convergence (zero-passed /
            # NONE-veto ``resolve_senate``) runs INSIDE the same owning transaction —
            # the masked return must never skip it (production binds a provider).
            return self._masked_senate_owning_flow(
                "doSubmitSenateVotes", "vote",
                lambda: self._adapter.submit_senate_votes(
                    self._viewer_id, proposal_ids, votes),
                converge=self._converge_senate_settlement)
        feedback = self._adapter.submit_senate_votes(self._viewer_id, proposal_ids, votes)
        self._raise_senate_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_senate_view()
            # WP-F R2-01（D-2）：zero-passed 收敛结算——全部提案未通过 → current_step="results"
            # 且 senate_result 未落盘（未 resolve）→ 自动结算（对齐 CLI 先例：否决环节零提案
            # 直接跳过进结算 + 本文件 doSubmitSenateVetoes 否决后无条件 resolve 先例）；resolve_senate
            # 幂等（落盘后 result_data 非空 → 条件不满足），passed>0 路径 step=tribune_veto 不触发。
            if (
                self._senate_view.get("current_step") in ("results", "settlement_pending")
                and not self._senate_view.get("senate_result")
            ):
                resolve_feedback = self._adapter.resolve_senate()
                self._raise_senate_feedback(resolve_feedback)
                self._refresh_snapshot()
                self._refresh_senate_view()
            # WP-M-R1 R1-S1（FC-R1-04/06/07）：NONE veto 终条件自动收敛——投票完成且 DTO
            # 显示 current_step=="tribune_veto" 且 veto_control_mode=="NONE"（无 eligible
            # Tribune，resolver-backed 终条件）→ 复用 canonical finalization
            # （resolve_senate → senate_api.resolve_senate → finalize_senate_if_ready）自动
            # 结算 skip 否决权威步，使 results / canAdvanceSenate 恢复、Senate→Combat 可推进。
            # 门禁**唯一** = resolver-backed veto_control_mode=="NONE"（**非** can_resolve，
            # **非**能力位缺失推断）；HUMAN/AI 路径逐字不变（mode 门禁天然排除，不抢权）。
            elif (
                self._senate_view.get("current_step") == "tribune_veto"
                and self._senate_view.get("veto_control_mode") == "NONE"
            ):
                resolve_feedback = self._adapter.resolve_senate()
                self._raise_senate_feedback(resolve_feedback)
                self._refresh_snapshot()
                self._refresh_senate_view()
        self.senateViewChanged.emit()
        return feedback

    @Slot("QVariant", result=dict)
    def doSubmitSenateVetoes(self, proposal_ids) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        payload = self._variant_to_python(proposal_ids)
        # Rework-D3D6 D3/D5 R1 (R01 · FC-RW-03): an EXPLICIT ``[]`` is a lawful
        # no-veto decision; a MISSING / MALFORMED payload (None / bad shape /
        # non-int rows) must NOT be silently filtered into a lawful ``[]``.
        # ``veto_ids is None`` => malformed (never a lawful empty decision).
        veto_ids = None
        if isinstance(payload, (list, tuple)):
            veto_ids = []
            for item in payload:
                item = self._variant_to_python(item)
                try:
                    veto_ids.append(int(item))
                except (TypeError, ValueError):
                    veto_ids = None
                    break
        # AU-R2-3b（R2-B-2，C3）：路由改读 resolver-backed veto_control_mode——不再信任
        # cached can_auto_veto（stale 场景：cached True 但 mode=HUMAN → human 分支 + API
        # guard 双层兜底）。HUMAN→submit_senate_vetoes / AI→apply_auto（直传 viewer_id，
        # R2-B-1 guard 兜底；adapter 零改动，D-8 先例）/ NONE→resolve 直接结算。
        veto_mode = self._senate_view.get("veto_control_mode")
        if veto_mode is None:
            # 旧缓存兼容（R2 前 DTO 无 veto_control_mode）：退化回 can_veto/can_auto_veto 派生
            if self._senate_view.get("can_auto_veto", False):
                veto_mode = "AI"
            elif self._senate_view.get("can_veto", False):
                veto_mode = "HUMAN"
        if veto_mode == "AI":
            from src.api import senate_api
            auto_feedback = self._adapter.call(
                senate_api.apply_auto_tribune_vetoes, self._state, None, self._viewer_id
            )
            self._raise_senate_feedback(auto_feedback)
            if not auto_feedback.get("success"):
                self._refresh_senate_view()
                self.senateViewChanged.emit()
                return auto_feedback
        elif veto_mode == "HUMAN":
            # Rework-D3D6 D3 (FC-RW-05): the HUMAN veto owner's decision — an
            # EXPLICIT EMPTY set included — is routed through the owner API (the
            # sole completion writer); the Store never fabricates completion and
            # never infers the decision from the resolve outcome.
            # Rework-D3D6 D3/D5 R1 (R01): a missing/malformed payload is a REAL
            # failure — never silently degraded into a lawful no-veto decision.
            if veto_ids is None:
                rejected = self._feedback(False, "无效或缺失的否决决定", "error")
                self._raise_senate_feedback(rejected)
                self.senateViewChanged.emit()
                return rejected
            if self._barrier_provider is not None:
                # item3 §2a S4: the HUMAN veto owner's decision runs through the
                # masked owning-flow machine (the owning dispatch enables the
                # senate terminal gate for the command's built-in continuation).
                # G5 I2-R3 REWORK (S4): the legacy UNCONDITIONAL settlement
                # convergence after a HUMAN veto runs INSIDE the same owning
                # transaction — the masked return must never skip it.
                return self._masked_senate_owning_flow(
                    "doSubmitSenateVetoes", "veto",
                    lambda: self._adapter.submit_senate_vetoes(
                        self._viewer_id, veto_ids),
                    converge=self._converge_senate_settlement)
            veto_feedback = self._adapter.submit_senate_vetoes(self._viewer_id, veto_ids)
            self._raise_senate_feedback(veto_feedback)
            if not veto_feedback.get("success"):
                self._refresh_senate_view()
                self.senateViewChanged.emit()
                return veto_feedback

        feedback = self._adapter.resolve_senate()
        self._raise_senate_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_senate_view()
        self.senateViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doAdvanceSenate(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if not self.canAdvanceSenate:
            feedback = self._feedback(False, "Senate result is not ready", "error")
            self._raise_feedback(feedback)
            return feedback
        feedback = self._adapter.advance_senate(self._viewer_id)
        self._raise_senate_feedback(feedback)
        if feedback.get("success"):
            self._refresh_snapshot()
            self._refresh_senate_view()
            self._selected_phase_id = "combat"
            self._selected_phase_summary = self._summary_from_phase(self._phase_by_id("combat"))
            self.phaseChanged.emit()

            # Auto-resolve combat for AI players
            if self.currentPlayerId != self._viewer_id:
                self._adapter.auto_resolve_combat(self._viewer_id)
            # Refresh combat view for all players entering combat phase
            self._refresh_combat_view()
        self.senateViewChanged.emit()
        return feedback

    @Slot(result=dict)
    def doResolveSenateSettlement(self) -> dict:
        """R6（SA §D.1，DA-4 B2）：正常态「完成结算」动作**退役**——仅内部异常恢复通道。

        正常态 finalization 由服务端命令流程（Submit 零 Senate / vote 完成且零 veto 候选 /
        veto 完成）自动完成；**正常推进唯一入口 = `doAdvanceSenate`**，正常 UI 无「完成结算」
        动作位（`canResolveSenateSettlement` 恒 False）。

        本 Slot 仅在**真实 finalization 失败**（DTO `can_retry_finalization == True`，状态落
        FINALIZATION_ERROR、`can_advance == False`）时作为内部重试通道：adapter.resolve_senate
        → 服务端唯一 finalization 完成协议（四完成事实同版；已发布包不撤销、不重放非 War 效果）。
        其余调用一律结构化拒绝，零 business mutation。
        """
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if not self._senate_view.get("can_retry_finalization", False):
            feedback = self._feedback(
                False,
                "正常态无「完成结算」动作：finalization 已由服务端自动完成，请使用推进按钮",
                "error",
                data={
                    "can_resolve_settlement": False,
                    "can_retry_finalization": False,
                },
            )
            self._raise_senate_feedback(feedback)
            self.senateViewChanged.emit()
            return feedback
        feedback = self._adapter.resolve_senate()
        self._raise_senate_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_senate_view()
        self.senateViewChanged.emit()
        return feedback

    @Slot(str, result=dict)
    def selectPhase(self, phase_id: str) -> dict:
        """Select a shell phase without executing phase business."""
        phase = self._phase_by_id(phase_id)
        if not phase:
            feedback = self._feedback(False, gui_text("feedback.phase.unknown", phase_id=phase_id), "error")
            self._raise_feedback(feedback)
            return feedback

        self._selected_phase_id = phase_id
        self._selected_phase_summary = self._summary_from_phase(phase)
        self.phaseChanged.emit()
        self.phaseStepsChanged.emit()
        logger.info(
            "GUI phase selected",
            extra={
                "phase_id": phase_id,
                "viewer_player_id": self._viewer_id,
                "current_player_id": self.currentPlayerId,
                "implemented": phase.get("implemented", False),
            },
        )

        if not phase.get("implemented", False):
            feedback = self._feedback(
                True,
                gui_text(
                    "feedback.phase.placeholder",
                    name=phase.get("name", phase_id),
                    handoff_task=phase.get("handoff_task", "后续任务"),
                ),
                "warning",
                data={"phase_id": phase_id},
            )
            self._raise_feedback(feedback)
            return feedback

        feedback = self._feedback(
            True,
            gui_text("feedback.phase.selected", name=phase.get("name", phase_id)),
            "info",
            data={"phase_id": phase_id},
        )
        self._raise_feedback(feedback)
        if phase_id == "population":
            self._refresh_population_view()
        elif phase_id == "mortality":
            self._refresh_mortality_view()
        elif phase_id == "revenue":
            self._refresh_revenue_view()
        elif phase_id == "senate":
            self._refresh_senate_view()
        elif phase_id == "combat":
            self._refresh_combat_view()
        elif phase_id == "resolution":
            self._refresh_resolution_view()
            # 自动结算触发：首次进入且尚未结算
            if not self._resolution_view.get("resolved", False) and not self._resolution_resolving:
                self._executeResolution()
        return feedback

    # -----------------------------------------------------------------------
    # EOR20261011-01 S1 — shared read-only query shell
    # -----------------------------------------------------------------------
    @Slot(str, result=dict)
    @Slot(str, str, str, result=dict)
    def doGlobalQuery(self, query_id: str, filter_text: str = "", record_id: str = "") -> dict:
        """Run a safe read-only global query for the OPC bottom bar.

        Qt overloads: 1-string (legacy) and 3-string (id, filter, record).
        Every request clears the old DTO + notifies before the synchronous read
        (v1.1 §5.1 / v1.2 ④.1) and returns feedback.success == API truth.
        """
        if not self._viewer_id:
            feedback = self._feedback(False, gui_text("feedback.query.not_initialized"), "error")
            self._raise_feedback(feedback)
            return feedback
        if self._query_guard:
            # Read during an invalidation barrier fails closed (no stale rows).
            from src.api import gui_query_api
            dto = gui_query_api.build_failure_dto(
                query_id, "ERROR", gui_query_api.ERR_QUERY_UNAVAILABLE
            )
            feedback = self._feedback(False, dto["message"], "error", data=dto)
            self._raise_feedback(feedback)
            return feedback

        result = self._run_global_query(query_id, filter_text, record_id, keep_open=False)
        success = result.get("result_state") in ("OK", "EMPTY")
        if success:
            feedback = self._feedback(
                True,
                gui_text("feedback.query.selected", title=result.get("title", query_id)),
                "success",
                data=result,
            )
        else:
            feedback = self._feedback(
                False,
                str(result.get("message") or gui_text("feedback.query.failed")),
                "error",
                data=result,
            )
        self._raise_feedback(feedback)
        return feedback

    @Slot(result=dict)
    def clearGlobalQuery(self) -> dict:
        """Public close: clear/notify then local reset/close. No Core write."""
        self._guard_enter()
        try:
            self._invalidate_global_query("close", keep_open=False)
            self._query_open = False
            self._query_active_id = ""
            self._pending_auto_refresh = None
        finally:
            self._guard_exit()
        feedback = self._feedback(True, gui_text("feedback.query.closed"), "info")
        self._raise_feedback(feedback)
        return feedback

    def _capture_query_context(self) -> Dict[str, Any]:
        """Capture ONLY {was_open, query_id}; never filter/record/title/rows."""
        if self._query_open and self._query_active_id:
            return {"was_open": True, "query_id": self._query_active_id}
        return {"was_open": False, "query_id": ""}

    def _guard_enter(self) -> None:
        self._query_guard_depth += 1
        if not self._query_guard:
            self._query_guard = True
            self.queryGuardChanged.emit()

    def _guard_exit(self) -> None:
        self._query_guard_depth = max(0, self._query_guard_depth - 1)
        if self._query_guard_depth == 0 and self._query_guard:
            self._query_guard = False
            self.queryGuardChanged.emit()

    def _receiver_ack_verified(self, had_content: bool) -> bool:
        """**真实** receiver 完成见证（v1.2 §2.1 step 3，A4/F2 残留收口）。

        仅当同步同线程 receiver **已完成**本次/未决 invalidations 的本地清空（并通过
        ``ackQueryInvalidation`` 回写了与当前 epoch 匹配的 ack）时返回 True。
        receiver 缺失 / 未响应 / queued（Qt.QueuedConnection，emit 同步返回时尚未
        执行 receiver）→ ack 不等于当前 epoch → False → fail closed。
        **自证「Store dict 已空」不当作完成。**

        A4（F2 残留）：一次**未被确认**的清除（Close / 失败切换 / 失败关闭）会留下
        **持久接收清除义务** ``_receiver_clear_outstanding``。该义务**仅能由真实
        receiver ack（当前 epoch）解除**；义务未解除前，Store 空态 + CLOSED **不再**
        充当见证 —— “关闭/失败后再切人”“失败切换后重试”“僵尸/queued 持续不响应”一律
        fail-closed，不会以空态冒充接收完成。

        例外：真正 pristine 的预绑定 CLOSED 初始化（清空前 Store 无内容且**无**未决
        义务）无清空义务，缺失 receiver 安全（保证 CLOSED→viewer 初始化路径不被误阻）。
        """
        if self._query_invalidation_ack == self._query_epoch:
            # A REAL receiver ack discharges ANY outstanding obligation.
            self._receiver_clear_outstanding = False
            self._query_receiver_verified = True
            return True
        if had_content or self._receiver_clear_outstanding:
            # Unacknowledged clear (content present, or an obligation already
            # outstanding) -> PRESERVE the obligation; empty Store is NOT proof.
            self._receiver_clear_outstanding = True
            self._query_receiver_verified = False
            return False
        # Pristine pre-binding CLOSED state: no content, no prior obligation.
        self._query_receiver_verified = True
        return True

    def _invalidate_global_query(self, reason: str, keep_open: bool = False) -> None:
        """Ordered synchronous clear-before-publish barrier (v1.1 §7 / v1.2 §2.1).

        Sets non-reentrant guard, advances the epoch, empties the Store DTO, then
        emits queryResultChanged followed by the boolean queryInvalidated. The
        same-thread GameShell receiver resets all local models synchronously.

        An explicit ``close`` reason cancels any retained OPEN/refresh intent of
        the active viewer transaction and never auto-reopens (F3). Nested reset /
        viewer-change inside a transaction inherits the outer OPEN intent.

        Returns the REAL receiver-completion witness (v1.2 §2.1 step 3，A4/F2):
        ``True`` iff the synchronous same-thread receiver acknowledged this epoch
        after clearing, or there was genuinely no content **and** no persistent
        outstanding receiver-clear obligation. Only ``_set_viewer`` uses it to
        authorise publishing a new viewer.
        """
        txn = self._viewer_txn
        if txn is not None:
            if reason == "close":
                # Explicit Close cancels pending OPEN/refresh intent (F3).
                txn["cancelled"] = True
                txn["was_open"] = False
                txn["query_id"] = ""
                self._pending_auto_refresh = None
                keep_open = False
            else:
                keep_open = bool(txn.get("was_open"))
                txn["invalidated"] = True
                if keep_open and txn.get("query_id"):
                    self._query_active_id = txn["query_id"]
        had_content = bool(self._global_query_result) or self._query_open
        self._query_epoch += 1
        # Invalidate any prior ack; the receiver must re-ack this exact epoch
        # AFTER it completes the local reset (emit below runs it synchronously).
        self._query_invalidation_ack = -1
        self._global_query_result = {}
        self._query_open = bool(keep_open)
        if not keep_open:
            self._query_active_id = ""
        self.queryResultChanged.emit()
        # Same-thread receiver (Overlay.resetForInvalidation) clears every
        # local/bound model then acks this exact epoch synchronously.
        self.queryInvalidated.emit(bool(keep_open))
        return self._receiver_ack_verified(had_content)

    def _begin_viewer_transaction(self) -> None:
        """Open the shared viewer/handoff barrier. Captures the safe intent BEFORE
        any viewer assignment or snapshot refresh (v1.2 §2.1 step 1)."""
        if self._viewer_txn is not None:
            return
        ctx = self._capture_query_context()
        ctx["invalidated"] = False
        self._viewer_txn = ctx
        self._guard_enter()

    def _set_viewer(self, new_id: str) -> None:
        """Internal owner of the viewer write (never a test acceptance entry)."""
        ctx = self._viewer_txn if self._viewer_txn is not None else self._capture_query_context()
        ack_ok = self._invalidate_global_query(
            "viewer_change", keep_open=ctx.get("was_open", False)
        )
        # v1.2 §2.1 step 3 (A4/F2): assert Store/model is empty AND the REAL
        # synchronous same-thread receiver completed (wrote the matching epoch
        # ack) BEFORE the new viewer identity can be observed. Otherwise fail
        # closed and do NOT publish the new viewer. Self-ack is not sufficient;
        # a persistent outstanding receiver-clear obligation (unacknowledged
        # Close/failure) is NOT discharged by the now-empty Store.
        if self._global_query_result != {} or not ack_ok:
            self._query_open = False
            self._query_active_id = ""
            self._pending_auto_refresh = None
            if self._viewer_txn is not None:
                self._viewer_txn["failed"] = True
            return
        self._query_open = bool(ctx.get("was_open"))
        self._query_active_id = ctx.get("query_id", "") if ctx.get("was_open") else ""
        self._viewer_id = new_id
        if ctx.get("was_open") and ctx.get("query_id"):
            self._pending_auto_refresh = ctx["query_id"]
        else:
            self._pending_auto_refresh = None

    def _end_viewer_transaction(self, success: bool = True) -> None:
        """Release the guard and, iff the transaction succeeded, mutation and
        snapshot publication completed and the window was OPEN, automatically
        reread the same recognized query unfiltered for the NEW viewer
        (v1.2 §2.1 step 5). Success/failure gated (F4): a failed mutation/snapshot
        or an explicit Close leaves the window empty and CLOSED with no old-data
        restore and no auto-reopen.
        """
        if self._viewer_txn is None:
            return
        txn = self._viewer_txn
        cancelled = bool(txn.get("cancelled"))
        failed = bool(txn.get("failed")) or not success
        pending = self._pending_auto_refresh
        if pending is None and txn.get("was_open") and txn.get("invalidated"):
            pending = txn.get("query_id") or None
        self._pending_auto_refresh = None
        self._viewer_txn = None
        self._guard_exit()
        if failed or cancelled:
            self._close_query_window()
            if failed and not cancelled:
                # Safe shell failure feedback; no old DTO restoration (F4).
                self._raise_feedback(self._feedback(
                    False, gui_text("feedback.query.failed"), "error"))
            return
        if pending:
            result = self._run_global_query(pending, "", "", keep_open=True)
            # F4: a failed automatic refresh (invalid viewer / system / shell
            # failure) closes the now-empty window and routes safe query-error
            # feedback (never a silent failure or restored old data).
            if not self._result_opens(result):
                self._raise_feedback(self._feedback(
                    False, self._safe_error_message(result), "error"))

    @staticmethod
    def _result_opens(result: Dict[str, Any]) -> bool:
        """True iff the DTO is a publishable overlay outcome (v1.2 ②).

        ``OK``/``EMPTY`` or a record-scoped ``DENIED record_unavailable`` keep the
        query window OPEN; every other failure leaves it empty + CLOSED (F4).
        """
        if not isinstance(result, dict):
            return False
        state = result.get("result_state")
        codes = {err.get("code") for err in (result.get("errors") or [])
                 if isinstance(err, dict)}
        return state in ("OK", "EMPTY") or (
            state == "DENIED" and "record_unavailable" in codes
        )

    @staticmethod
    def _safe_error_message(result: Dict[str, Any]) -> str:
        """Resolve a safe localized failure copy from a DTO's ``message_key``
        (never a raw backend string; falls back to the generic query-error copy)."""
        if isinstance(result, dict):
            key = result.get("message_key") or ""
            if key:
                text = gui_text(key)
                if text != key:
                    return text
        fallback = gui_text("feedback.query.failed")
        return fallback if fallback != "feedback.query.failed" else ""

    def _close_query_window(self) -> None:
        """Force the retained-open query window empty and CLOSED (F4).
        No old DTO/model restoration; emits a synchronous close invalidation."""
        self._guard_enter()
        try:
            self._invalidate_global_query("failure", keep_open=False)
            self._query_open = False
            self._query_active_id = ""
            self._pending_auto_refresh = None
        finally:
            self._guard_exit()

    def _run_global_query(
        self, query_id: str, filter_text: str = "", record_id: str = "", keep_open: bool = False
    ) -> Dict[str, Any]:
        """Synchronous clear-before-read + publish of one safe DTO.

        Captures viewer/epoch before the read and discards a stale result whose
        viewer/epoch changed during the synchronous read (F2). A non-opening
        outcome empties and CLOSES the window with no visible overlay and no
        old-data restore (F4).
        """
        self._guard_enter()
        try:
            self._invalidate_global_query("query", keep_open=keep_open)
            viewer = self._viewer_id
            epoch = self._query_epoch
            result = self._adapter.get_global_query_result(
                self._viewer_id, query_id, filter_text, record_id
            )
            # F2: reject a stale result bound to an older viewer/epoch.
            if self._query_epoch != epoch or self._viewer_id != viewer:
                return {}
            if not isinstance(result, dict):
                result = {}
            result_state = result.get("result_state")
            opens = self._result_opens(result)
            if opens:
                self._global_query_result = result
                self._query_open = True
                self._query_active_id = query_id
                self.queryResultChanged.emit()
            else:
                # Failure / unavailable: EMPTY cache + CLOSED — never a retained
                # ERROR/DENIED DTO in the Store/bound model — and no visible
                # overlay / old-data restore (F4). The safe failure DTO is still
                # returned to the caller for feedback + evidence.
                self._global_query_result = {}
                self._query_open = False
                self._query_active_id = ""
                self.queryResultChanged.emit()
                self.queryInvalidated.emit(False)
            return result
        finally:
            self._guard_exit()

    @Slot(result=dict)
    def refreshSnapshot(self) -> dict:
        """Refresh the shell snapshot from authoritative API DTO."""
        self._guard_enter()
        try:
            self._invalidate_global_query("refresh", keep_open=False)
        finally:
            self._guard_exit()
        self._refresh_snapshot()
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self._refresh_revenue_view()
        self._refresh_forum_view()
        self._refresh_combat_view()
        self._refresh_resolution_view()
        feedback = self._feedback(True, gui_text("feedback.snapshot.refreshed"), "success")
        self._raise_feedback(feedback)
        return feedback

    @Slot(str, result=bool)
    def switchViewer(self, new_viewer_id: str) -> bool:
        """切换 viewer（用于玩家交接遮罩确认后）"""
        self._begin_viewer_transaction()
        txn_ok = False
        try:
            self._reset_phase_caches()
            self._set_viewer(new_viewer_id)
            self._refresh_snapshot()
            self._refresh_mortality_view()
            self._refresh_population_view()
            self._refresh_senate_view()
            self._refresh_revenue_view()
            self._refresh_forum_view()
            self._refresh_combat_view()
            self._refresh_resolution_view()
            self.currentPlayerChanged.emit()
            txn_ok = True
        finally:
            self._end_viewer_transaction(txn_ok)
        return True

    # =======================================================================
    # S-B Group 2/4 — Handoff authority state machine (Store publication side)
    # =======================================================================
    # Frozen design: G2-Handoff-Authority-State-Machine / G2-R2-Handoff-Witness /
    # G2-Active-Seat-Read-Write-Guard. The Core owns the current actor/phase; this
    # Store owns only the projected DTO / render transaction. Lifecycle:
    #
    #   ACTIVE -> MASKED_PENDING_HANDOFF -> ACTIVATE -> (ACTIVE | MASKED_FAILURE)
    #
    # A barrier provider (the production GameShell / GuiApp) is REQUIRED for the
    # masked path; without one the historical synchronous Query-ack-gated handoff
    # runs unchanged (EOR20261011-01 preserved). The masked path never publishes
    # the next seat before the explicit 「接管」 (confirmHandoffAsync), keeps a
    # 100% opaque full-window cover through a provider barrier, and fails closed
    # when any witness is missing.

    @Slot(object)
    def setHandoffBarrierProvider(self, provider) -> None:
        """Bind the production barrier/witness provider (GameShell-backed).

        Absent -> the masked machine is inert and the historical synchronous
        handoff is used (no behaviour change for the CLI/historical suite)."""
        self._barrier_provider = provider

    @Slot()
    def clearHandoffBarrierProvider(self) -> None:
        self._barrier_provider = None

    def _provider_call(self, name: str, *args) -> bool:
        """Invoke a provider witness method; missing method / exception / falsy
        return => False (fail-closed). No witness is ever invented locally."""
        fn = getattr(self._barrier_provider, name, None)
        if not callable(fn):
            return False
        try:
            return bool(fn(*args))
        except Exception:
            logger.exception("handoff barrier provider call failed: %s", name)
            return False

    # -- F4: resumable real-frame gates (R2 §1/§4) --------------------------
    #: gate kind -> the provider's async real-frame method.
    _ASYNC_GATE_METHOD = {
        "arm": "arm_barrier_async",
        "publish": "publish_under_mask_async",
        "unmask": "request_unmask_async",
    }

    def _begin_frame_gate(self, kind: str, txn_id: str, resume) -> bool:
        """Begin a real-frame gate. Returns ``True`` when the provider supports the
        async gate and it was begun (the transaction SUSPENDS until the frame
        receipt); ``False`` to fall back to the historical synchronous provider
        call (legacy fakes / CLI).

        ``resume(ok)`` runs on the GUI thread when the immutable frame receipt
        arrives; a stale/old-txn/old-generation receipt is discarded.
        """
        fn = getattr(self._barrier_provider,
                     self._ASYNC_GATE_METHOD.get(kind, ""), None)
        if not callable(fn):
            return False
        self._async_gate = {"txn_id": txn_id, "kind": kind, "resume": resume}
        try:
            fn(txn_id, self._on_frame_receipt)
        except Exception:
            logger.exception("async frame gate could not begin: %s", kind)
            self._async_gate = None
            return False
        return True

    def _on_frame_receipt(self, txn_id: str, kind: str, ok) -> None:
        """Frame-receipt callback from the bridge: resume the matching suspended
        continuation exactly once. Stale / unmatched receipts are discarded."""
        gate = self._async_gate
        if gate is None or gate["txn_id"] != txn_id or gate["kind"] != kind:
            return
        self._async_gate = None
        gate["resume"](bool(ok))

    def _masked_pending_feedback(self, txn_id: str) -> Dict[str, Any]:
        """Returned when the transaction has SUSPENDED on a real-frame gate;
        ``accepted`` is NOT success (completion arrives via ``handoffFinished``)."""
        return self._feedback(True, "交接处理中", "info",
                              data={"accepted": True, "txn_id": txn_id,
                                    "pending": True})

    def _finish_activation(self, done, result: Dict[str, Any]) -> None:
        self._activation_result = result
        if done is not None:
            done(result)

    def _emit_seat(self) -> None:
        self.seatLifecycleChanged.emit()
        self.handoffMaskChanged.emit()

    @Property(str, notify=seatLifecycleChanged)
    def seatLifecycle(self) -> str:
        return self._seat_lifecycle

    @Property(int, notify=seatLifecycleChanged)
    def seatEpoch(self) -> int:
        return self._seat_epoch

    @Property(bool, notify=handoffMaskChanged)
    def handoffMaskVisible(self) -> bool:
        """True while the opaque full-window cover must be present."""
        return self._seat_lifecycle != SEAT_ACTIVE or self._reveal_pending

    @Property(bool, notify=seatLifecycleChanged)
    def handoffBusy(self) -> bool:
        return self._handoff_busy

    @Property(str, notify=handoffPendingFactionChanged)
    def handoffPendingFactionName(self) -> str:
        """Safe faction display name ONLY (never a player name / raw player_* id)."""
        return self._pending_faction_name

    # -- W2a startup page (neutral 1H+AI) -----------------------------------
    # These read the LIVE Core state (never ``_snapshot``, which is emptied by
    # ``_neutralize_public_projection`` before the startup page is shown).
    @Property(str, notify=startupChanged)
    def startupMode(self) -> str:
        """``single_human`` when EXACTLY one actual HUMAN player exists."""
        return self._startup_mode

    @Property(str, notify=startupChanged)
    def startupYearText(self) -> str:
        turn = getattr(self._state, "turn", None)
        year = getattr(turn, "year", None) if turn is not None else None
        if year is None:
            return "—"
        try:
            value = int(year)
        except (TypeError, ValueError):
            return "—"
        if value < 0:
            return gui_text("startup.year.bc", year=abs(value))
        return gui_text("startup.year.ad", year=value)

    @Property(str, notify=startupChanged)
    def startupTreasuryText(self) -> str:
        value = getattr(self._state, "treasury", None)
        if value is None:
            return "—"
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return "—"

    @Property(str, notify=startupChanged)
    def startupTerritoryText(self) -> str:
        try:
            province = self._state.get_province(0)
        except Exception:
            return "—"
        if province is None:
            return "—"
        name = getattr(province, "name", None)
        if not isinstance(name, str) or not name.strip():
            return "—"
        raw_name = name.strip()
        # Only canonical, registered names are translated. Every other legal
        # non-empty real name is shown verbatim (F1: never suppress real data).
        key = {
            "意大利": "startup.province.0.name",
            "Italy": "startup.province.0.name",
        }.get(raw_name)
        if key is None:
            return raw_name
        localized = gui_text(key)
        return localized if localized and localized != key else raw_name

    @Property(str, notify=startupChanged)
    def startupTerritorySuffix(self) -> str:
        """Localized homeland suffix, ONLY for the capital/home province (id 0)."""
        try:
            province = self._state.get_province(0)
        except Exception:
            return ""
        if province is None or getattr(province, "province_id", None) != 0:
            return ""
        return gui_text("startup.territory.suffix")

    def _on_gui_locale_changed(self) -> None:
        """Re-emit startup values so QML re-reads locale-formatted text."""
        self.startupChanged.emit()

    @Property(bool, notify=seatLifecycleChanged)
    def handoffCanRetry(self) -> bool:
        return self._seat_lifecycle == SEAT_MASKED_FAILURE

    @Property(bool, notify=seatLifecycleChanged)
    def handoffCanExit(self) -> bool:
        return self._seat_lifecycle in (SEAT_MASKED_PENDING, SEAT_MASKED_FAILURE)

    @Property(str, notify=seatLifecycleChanged)
    def handoffFailureKind(self) -> str:
        return self._handoff_failure_kind

    @Property(bool, notify=seatLifecycleChanged)
    def handoffAcceptingTakeover(self) -> bool:
        """True only while an explicit 「接管」 is legal (MASKED_PENDING_HANDOFF)."""
        return self._seat_lifecycle == SEAT_MASKED_PENDING

    def _safe_faction_name(self, player_id: str) -> str:
        """Core-authoritative safe faction display name for a pending target.

        Resolved from the Core faction record (never a public B snapshot/view
        getter). Missing/blank/unknown target -> "" (fail closed; never guess a
        receiver and never fall back to a raw id)."""
        if not player_id:
            return ""
        player = self._state.get_player(player_id)
        if player is None or not getattr(player, "faction_id", None):
            return ""
        faction = self._state.get_faction(player.faction_id)
        name = getattr(faction, "name", "") if faction is not None else ""
        return name or ""

    def _neutralize_public_projection(self) -> None:
        """Clear every public/private projected model so no stale viewer residue
        is visible or accessible while masked (no source-state mutation).

        W2b (FC-712-17/20) — additive only: the SESSION_DISPLAY faction style
        map is part of the projection and is cleared here too (it used to
        survive every neutralization as an accidental global surface).

        R03 — the per-resource clear set is now driven by the SAME activation
        inventory as staging/apply (``attr`` + ``neutral_value``), so every
        declared resource is neutralized by construction. The non-resource
        transient fields below are not staged projections and stay explicit.
        """
        for resource in self._ACTIVATION_INVENTORY:
            setattr(self, resource["attr"],
                    dict(resource["neutral_value"])
                    if isinstance(resource["neutral_value"], dict)
                    else resource["neutral_value"])
        self._population_vote_submitting = False
        self._forum_result = {}
        self._forum_step_override = ""
        self._combat_result = {}
        self._revenue_result = {}
        self._mortality_result = {}
        self._selected_phase_summary = {}
        self._senate_submit_errors = []
        self._senate_submit_errors_by_war = {}
        self._senate_submit_errors_by_scope = {}
        self._senate_drafts = {}
        self._senate_finalization_warning = ""
        self._emit_inventory_notifications()
        self.phaseChanged.emit()

    @classmethod
    def _inventory_by_publish_order(cls) -> tuple:
        """The inventory in PUBLIC notification order (declared, not implied)."""
        return tuple(sorted(cls._ACTIVATION_INVENTORY,
                            key=lambda entry: int(entry.get("publish_order", 99))))

    def _emit_inventory_notifications(self) -> None:
        """R03 — emit every declared ``notify`` signal exactly once, in order.

        The notification set/order comes from the inventory declaration; two
        resources sharing a signal (``factionStyleMap`` -> ``snapshotChanged``)
        emit it once. Subscribers can therefore never observe a half-assigned
        frame, and a new resource cannot be published silently.
        """
        emitted = set()
        for resource in self._inventory_by_publish_order():
            name = resource["notify"]
            if name in emitted:
                continue
            emitted.add(name)
            getattr(self, name).emit()

    #: Internal helper commands each top-level GUI command may invoke under the
    #: non-exported transaction-local continuation scope (DG-03 §3.4). The scope
    #: never widens into a reusable token and authorizes only these names for the
    #: one owning dispatch.
    #:
    #: FC-D1-02 (D1 rework): each masked owning command's helper set is EXACTLY the
    #: internal guarded-boundary closure of that command (no fewer — a missing
    #: label is a DENIED internal call; no more — an unreachable label is an
    #: over-authorization surface). ``get_candidates`` is intentionally ABSENT:
    #: every internal candidate read now uses the service-private
    #: ``population_api._get_candidates_impl`` (FC-D1-01), so the PUBLIC guarded
    #: read boundary is never reached inside the continuation scope. The AI-drain
    #: sub-boundaries (``campaign`` / ``vote``) are reachable via the owning
    #: command's automatic continuation (``continue_after_command`` /
    #: ``resolve_population_slice``) and are therefore enumerated.
    _LEASE_HELPERS = {
        "submit_population_votes": frozenset({
            "begin_population_phase", "batch_vote", "complete_population_player",
            "resolve_population_slice",
            "process_population_disbandments", "resolve_election",
            "campaign", "vote",
        }),
        "resolve_population_slice": frozenset({
            "begin_population_phase", "process_population_disbandments",
            "resolve_election", "campaign", "vote",
        }),
        # D2 — forum substep FINISH owning commands (FC-D2-03/05): the transaction
        # records the seat's lawful finish, drives the scheduled-AI sub-boundaries
        # and (via the coordinator) selects the next actor, all under ONE masked
        # handoff transaction. ``open_market`` / ``resolve_forum`` are performed as
        # the SAME seat's follow-up AFTER same-seat recovery (outside the
        # continuation scope), so they are not helpers here.
        "doCompleteForumStep": frozenset({
            "retire_figure",
        }),
        "doResolveForum": frozenset({
            "recruit_figure", "place_bid", "buy_land", "vote_triumph",
        }),
    }

    #: D4/D6 I1 (FC-D46-01, PC-RA-05): the INDEPENDENT new-normal-root registry
    #: (the five §1.1 owning commands). It is kept strictly SEPARATE from the
    #: legacy ``_LEASE_HELPERS`` four-root map (byte-for-byte unchanged): the two
    #: key sets MUST be disjoint, there is no default union / wildcard, and the
    #: recovery root is in NEITHER normal registry. Each value is the root's
    #: internal guarded-boundary closure E (design §4.1.2).
    _PHASE_ROLE_LEASE_HELPERS = {
        "advance_forum_phase": frozenset({
            "begin_population_phase", "archive_office_holders",
            "convert_battlefield_commanders", "process_population_disbandments",
            "campaign", "vote", "resolve_election",
        }),
        "advance_population_phase": frozenset({
            "auto_submit_proposals", "apply_auto_tribune_vetoes",
            "finalize_senate_if_ready", "assign_governors",
        }),
        "propose_many": frozenset({
            "auto_submit_proposals", "apply_auto_tribune_vetoes",
            "finalize_senate_if_ready", "assign_governors",
        }),
        "vote": frozenset({
            "auto_submit_proposals", "apply_auto_tribune_vetoes",
            "finalize_senate_if_ready", "assign_governors",
        }),
        "veto": frozenset({
            "auto_submit_proposals", "apply_auto_tribune_vetoes",
            "finalize_senate_if_ready", "assign_governors",
        }),
    }

    @classmethod
    def _helpers_for_owning_command(cls, command: Optional[str]) -> frozenset:
        """FC-D46-01: the ONLY owning-command helper lookup. Exact legacy map
        first, then the independent new-normal-root registry; a root in NEITHER
        resolves to the empty set (unknown -> refuse, never a default union /
        wildcard). The legacy four roots keep their EXACT prior behaviour."""
        if command is None:
            return frozenset()
        helpers = cls._LEASE_HELPERS.get(command)
        if helpers is not None:
            return helpers
        return cls._PHASE_ROLE_LEASE_HELPERS.get(command, frozenset())

    def _begin_masked_seat_transition(self, command_id: str,
                                      lease_command: Optional[str] = None,
                                      payload: Any = None,
                                      cont: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """R2 steps 1-4: acquire the EXACT one-use command lease for the single
        authorized command, SUSPEND the service authority, arm the opaque barrier,
        clear the query via the REAL receiver obligation, neutralize projections,
        and finally ATOMICALLY consume the lease into the transaction-local
        continuation scope immediately BEFORE the dispatch (DG-03 §3.2–§3.4).

        Returns the txn dict on success, or ``None`` after entering
        MASKED_FAILURE (fail-closed). The exact authorized command is dispatched by
        the caller only after this returns non-None."""
        txn_id = uuid.uuid4().hex
        # W3 / W-04: only the in-scope owning commands require a recorded
        # delivery envelope for their bounded retry.
        self._delivery_required_command = (
            str(command_id) if command_id in (
                "advancePopulation", "doSubmitSenateProposals",
                "doSubmitSenateVotes", "doSubmitSenateVetoes",
                "submitPopulationVotes",
                "advance_population_phase", "propose_many", "vote", "veto",
            ) else "")
        # R05 (FC-712-18): a freshness-dependent WRITE is refused BEFORE any side
        # effect — no lease is issued, no barrier is armed, no Core command runs,
        # no receipt/RNG is produced. The predicate is dependency-related: ANY
        # REQUIRED resource served from last_good blocks (never just the style
        # map). The bounded recovery is a fresh refresh / activation.
        stale = self._stale_write_dependencies()
        if stale:
            logger.warning("write refused: stale projection (%s)", stale)
            self._fail_masked(FAIL_BEFORE_COMMIT, txn_id)
            return None
        seat_epoch = self._seat_epoch + 1
        self._seat_txn = {
            "txn_id": txn_id,
            "seat_epoch": seat_epoch,
            "command_id": command_id,
            "armed": False,
            "cleared": False,
        }
        txn = self._seat_txn
        self._committed_receipt = None
        self._handoff_failure_kind = ""
        self._handoff_failure_route = RECOVER_ROUTE_ACTIVATION
        self._handoff_busy = True
        self._seat_lifecycle = SEAT_BUSY
        self._emit_seat()
        # Suspend the PUBLIC projection immediately (R2 §4 step 1: no stale viewer
        # residue is visible or accessible while the seat is BUSY — the public
        # getters return neutral for the whole masked transaction, including the
        # async window between arming and the real frame receipt).
        self._neutralize_public_projection()
        # SB-V03/DG-03: the SERVICE owns the authoritative lifecycle/epoch. Issue
        # the EXACT one-use lease for the one authorized command (only after its
        # successful prior ACTIVE current-seat authorization), then TRULY suspend
        # public read/write BEFORE the barrier/dispatch (a revoked/masked seat
        # denies). An un-registered CLI/historical state issues no lease.
        lease_id = ""
        if lease_command:
            lease = session_access.authorize_and_lease(
                self._state, command=lease_command, actor=self._viewer_id,
                payload_digest=session_access.payload_digest_of(
                    payload if payload is not None else {}),
                session_id=session_access._state_identity(self._state),
                txn_id=txn_id)
            if lease is not None:
                lease_id = lease.lease_id
                self._seat_txn["lease_id"] = lease_id
        session_access.suspend_hotseat_session(self._state, lifecycle_epoch=seat_epoch)
        # 1. arm barrier BEFORE any dispatch/publication. With an async-capable
        #    provider the arm gate SUSPENDS the transaction on the real frame
        #    receipt (``cont`` resumes later); the legacy synchronous provider
        #    completes inline (unchanged behaviour).
        if cont is None:
            if not self._provider_call("arm_barrier", txn_id):
                self._fail_masked(FAIL_BEFORE_COMMIT, txn_id)
                return None
            if not self._after_barrier_armed(txn_id, lease_command, lease_id):
                return None
            return txn

        def after_arm(ok):
            if not ok:
                self._fail_masked(FAIL_BEFORE_COMMIT, txn_id)
                cont(txn, False, self._handoff_failure_feedback())
                return
            if not self._after_barrier_armed(txn_id, lease_command, lease_id):
                cont(txn, False, self._handoff_failure_feedback())
                return
            cont(txn, True, None)

        if self._begin_frame_gate("arm", txn_id, after_arm):
            return txn                          # suspended: awaits the real frame
        if not self._provider_call("arm_barrier", txn_id):
            self._fail_masked(FAIL_BEFORE_COMMIT, txn_id)
            cont(txn, False, self._handoff_failure_feedback())
            return txn
        after_arm(True)
        return txn

    def _after_barrier_armed(self, txn_id: str, lease_command: Optional[str],
                             lease_id: str) -> bool:
        """R2 steps 2-4: real Query receiver obligation + projection neutralization
        + atomic lease consumption immediately BEFORE the dispatch. Returns False
        (and fails closed) when any step fails."""
        self._seat_txn["armed"] = True
        self._guard_enter()
        try:
            ack_ok = self._invalidate_global_query("handoff", keep_open=False)
        finally:
            self._guard_exit()
        if not ack_ok:
            self._fail_masked(FAIL_BEFORE_COMMIT, txn_id)
            return False
        self._seat_txn["cleared"] = True
        self._neutralize_public_projection()
        if lease_id:
            helpers = self._helpers_for_owning_command(lease_command)
            if lease_command == "advance_population_phase":
                # W-01/W-07 / A-W3-08: the entry continuation's AI proposal
                # executor delegates to the propose_many OWNER publication, which
                # must be reachable inside the SAME owning dispatch (exactly once).
                # The frozen helper registry above stays byte-identical.
                helpers = frozenset(set(helpers) | {"propose_many"})
            reason = session_access.consume_command_lease(
                self._state, lease_id=lease_id, helpers=helpers)
            if reason is not None:
                self._fail_masked(FAIL_BEFORE_COMMIT, txn_id)
                return False
        return True

    def _dispatch_owning(self, txn: Dict[str, Any], command: str, fn, *args):
        """R3b F2: dispatch the ONE owning top-level command under the private
        transaction-local continuation NESTING. The nesting (possession) is opened
        ONLY around this single dispatch and closed immediately after, so a public
        call outside this window cannot borrow the live continuation scope."""
        session_access.begin_dispatch_nesting(
            self._state, txn_id=txn["txn_id"], command=command,
            dispatch_epoch=txn["seat_epoch"],
            helpers=self._helpers_for_owning_command(command))
        try:
            return fn(*args)
        finally:
            session_access.end_dispatch_nesting(self._state)

    def _stage_activation(self, target_id: str, epoch: int) -> Optional[Dict[str, Any]]:
        """R2 step 7 — build the DECLARED inventory (FC-712-17) into a PRIVATE
        staged bundle through the internal neutral activation reservation.

        For every declared resource:

          * the read is the real API boundary, with the target presented as the
            viewer (target-aware);
          * ``success is not True``, a malformed payload, or a schema violation
            is a FAILURE (never a legal empty);
          * ``success is True`` + ``{}`` IS a legal empty projection;
          * a failed REQUIRED resource refuses the WHOLE bundle (``None``), so
            no partial first frame can ever be published.

        The bundle is tagged (session / scope / target / seat_epoch /
        core_revision / publication_revision) after the reads, and those tags are
        re-validated at publish time.
        """
        registered = session_access.is_hotseat_registered(self._state)
        capability = None
        if registered:
            txn_id = (self._seat_txn or {}).get("txn_id", "")
            capability = session_access.issue_activation_reservation(
                self._state, target_id, epoch, txn_id=txn_id)
            if capability is None:
                return None
            # R3b F3: the private staging READ requires the presented capability;
            # the reservation can no longer be borrowed by naming the target.
            session_access.begin_staging_nesting(self._state, capability)
        try:
            staged: Dict[str, Any] = {
                "target_id": target_id,
                "seat_epoch": int(epoch),
                "txn_id": (self._seat_txn or {}).get("txn_id", ""),
                "resources": {},
            }
            for resource in self.activation_inventory():
                rid = resource["resource_id"]
                source = self._resolve_source(resource["source"])
                if rid == "factionStyleMap":
                    # FC-712-20: target-aware guarded read.
                    envelope = self._adapter.read_envelope(
                        source, self._state, viewer_player_id=target_id)
                else:
                    envelope = self._adapter.read_envelope(
                        source, self._state, target_id)
                ok, data = self._read_outcome(envelope)
                if ok and not resource["validator"](data):
                    ok = False
                if not ok:
                    if resource["required"]:
                        logger.warning(
                            "activation staging refused: resource=%s required=%s",
                            rid, True)
                        return None
                    staged["resources"][rid] = resource["neutral_value"]
                    continue
                staged["resources"][rid] = data
            # Tags are bound AFTER the reads (a staging read may legitimately
            # advance a phase marker); they describe the bundle this transaction
            # is allowed to publish.
            staged["tags"] = self._activation_tags(target_id, epoch)
            return staged
        finally:
            session_access.end_staging_nesting(self._state)
            if registered:
                session_access.end_activation_reservation(self._state)

    @staticmethod
    def _resolve_source(source: str):
        """Resolve ``"<module>.<attr>"`` to the LIVE API attribute (so a
        boundary-level fault injection or a real code change is always honoured;
        never a captured reference)."""
        module_name, _, attr = str(source).partition(".")
        module = importlib.import_module("src.api." + module_name)
        return getattr(module, attr)

    def _activation_tags(self, target_id: str, epoch: int) -> Dict[str, Any]:
        """The six tags every staged resource is bound to (FC-712-17)."""
        try:
            revision = int(session_access.core_business_revision(self._state))
        except Exception:  # pragma: no cover - defensive
            revision = -1
        try:
            session_id = session_access._state_identity(self._state)
        except Exception:  # pragma: no cover - defensive
            session_id = ""
        return {
            "session": session_id,
            "scope": "activation",
            "target": target_id,
            "seat_epoch": int(epoch),
            "core_revision": revision,
            "publication_revision": int(epoch),
        }

    def _tags_current(self, bundle: Dict[str, Any],
                      target_id: Optional[str]) -> bool:
        """True iff ``bundle`` is publishable into the CURRENT epoch.

        A bundle staged for another target, another seat epoch, another
        publication revision, another session, or another transaction is
        refused — a late/foreign callback can never overwrite a newer epoch.

        R02: ALL SIX declared tags are validated. ``scope`` must be the one
        activation scope and ``core_revision`` must equal the CURRENT Core
        business revision (both were written by ``_activation_tags`` but never
        read before R2, so a bundle staged before a business revision advance
        could still publish). Missing/wrong values fail closed.
        """
        tags = bundle.get("tags")
        if not isinstance(tags, dict):
            return False
        if tags.get("scope") != "activation":
            return False
        try:
            if int(tags.get("core_revision", -1)) != int(
                    session_access.core_business_revision(self._state)):
                return False
        except (TypeError, ValueError):
            return False
        except Exception:  # pragma: no cover - defensive
            return False
        expected_target = target_id or tags.get("target", "")
        if tags.get("target") != expected_target:
            return False
        try:
            if int(tags.get("seat_epoch", -1)) != int(bundle.get("seat_epoch", -2)):
                return False
            if int(tags.get("seat_epoch", -1)) != int(self._seat_epoch):
                return False
            if int(tags.get("publication_revision", -1)) != int(self._seat_epoch):
                return False
        except (TypeError, ValueError):
            return False
        try:
            if tags.get("session") != session_access._state_identity(self._state):
                return False
        except Exception:  # pragma: no cover - defensive
            return False
        live_txn = (self._seat_txn or {}).get("txn_id", "")
        if live_txn and bundle.get("txn_id") != live_txn:
            return False
        return True

    def _bundle_publishable(self, bundle: Dict[str, Any],
                            target_id: Optional[str]) -> bool:
        """Whole-package validation before ANY public assignment."""
        resources = bundle.get("resources")
        if not isinstance(resources, dict):
            return False
        for resource in self.activation_inventory():
            rid = resource["resource_id"]
            if rid not in resources:
                if resource["required"]:
                    return False
                continue
            if not resource["validator"](resources[rid]):
                return False
        return self._tags_current(bundle, target_id)

    def _apply_staged(self, staged: Dict[str, Any], *,
                      target_id: Optional[str] = None) -> bool:
        """Atomically publish the staged (private) bundle to the public models.

        D13：`target_id`（可选，默认 None 保持旧调用语义）是本次成功 final-reveal
        的显式新 publication viewer——`_viewer_id = target_id` 发生在本方法之后，
        因此换席判定不得依赖仍是旧值的 `_viewer_id`。

        W2b (FC-712-17): the WHOLE package is validated first (every REQUIRED
        resource present + schema-valid + tags current). Only then are the
        assignments made, ``_viewer_id`` is moved to the new publication viewer,
        and every notification is emitted — so no subscriber can observe a
        half-assigned frame. Returns ``False`` (and publishes nothing) when the
        bundle is not publishable.

        R03: assignments, the last_good snapshot and the notification order are
        ALL derived from the activation inventory (``attr`` / ``publish_order``).
        The legacy FLAT bundle branch is CLOSED: a flat mapping carries no
        tags/REQUIRED proof, so it can never bypass the whole-package gate.
        """
        bundle = staged if isinstance(staged, dict) else {}
        if not self._bundle_publishable(bundle, target_id):
            logger.warning("staged bundle refused at publish time")
            return False
        resources = bundle.get("resources") or {}
        inventory = self.activation_inventory()
        for resource in inventory:
            setattr(self, resource["attr"],
                    resources.get(resource["resource_id"],
                                  resource["neutral_value"]))
        # FC-712-20: the successful publication viewer is assigned BEFORE any
        # notification, so no subscriber sees "new data + old viewer".
        if target_id:
            self._viewer_id = target_id
        # A complete fresh bundle satisfies every freshness obligation.
        # The bundle IS the private last_good for this viewer, so a later
        # same-seat DENIED refresh can be served from it (never from
        # another seat's cache: the viewer is part of the entry).
        for resource in inventory:
            value = getattr(self, resource["attr"])
            if isinstance(value, dict):
                self._last_good_views[resource["resource_id"]] = {
                    "viewer": self._viewer_id,
                    "data": value,
                }
        self._stale_resources.clear()
        self._deferred_public_refresh = False
        # D13：在 senateViewChanged 发出前完成同步（先改状态，后通知）。
        self._sync_ai_proposer_guard(self._senate_view,
                                     target_id=target_id or self._viewer_id)
        new_current = self._snapshot.get("current_phase_id") or "mortality"
        self._selected_phase_id = new_current
        self._selected_phase_summary = self._summary_from_phase(
            self._phase_by_id(new_current))
        self._emit_inventory_notifications()
        self.phaseChanged.emit()
        self.phaseStepsChanged.emit()
        self.currentPlayerChanged.emit()
        return True

    @staticmethod
    def _typed_delivery_error(code: str, stage: str,
                              committed: Optional[bool] = True
                              ) -> Dict[str, Any]:
        """W-11 / §9.2 + AC-W3-19: a typed diagnostic; ``committed`` is the
        PROVEN state.

        The commit state is TRI-STATE (G3-delta §7.1/§9.1): ``True`` = a proven
        commit, ``False`` = a proven non-commit, and ``None`` = UNPROVEN — the
        ``committed`` key is then OMITTED so an unknown commit can be neither
        swallowed by the ``True`` default nor fabricated as ``False``.
        """
        from src.api import session_turn_service
        record = session_turn_service.delivery_error(
            code, stage=stage,
            committed=(True if committed is None else bool(committed)),
            retry_class=session_turn_service.DELIVERY_RETRY_NONE)
        if committed is None:
            record.pop("committed", None)
        return record

    def _delivery_fail(self, txn_id: str, err: Dict[str, Any],
                       done: Optional[Any] = None) -> Dict[str, Any]:
        """S1/FC-712-02: a typed delivery failure — fail closed, remain masked,
        retain the committed receipt. Never fall back to the same seat."""
        self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
        result = self._feedback(False, "交付协议校验失败，本回合未切换", "error",
                                data={"delivery_error": err or {}})
        if done is not None:
            done(result)
        return result

    def _settle_seat_after_success(self, txn_id: str,
                                   next_actor_id: Optional[str],
                                   done: Optional[Any] = None,
                                   delivery: Optional[Dict[str, Any]] = None,
                                   legacy: Optional[Dict[str, Any]] = None,
                                   ) -> Dict[str, Any]:
        """R2 steps 5+: decide pending vs same-seat and stage privately (no
        pre-confirm publication of the next seat).

        W3 / §3: when a typed delivery is presented it is the ONLY receiver truth —
        validated against the REAL Core current player / actual ``PlayerType``. The
        legacy mapping is passed ONLY to the validator for cross-checking; it never
        selects a receiver. A missing receiver is a typed failure; there is NO
        ``None -> same-seat`` fallback.

        Out-of-scope legacy flows (population ``next_player`` / forum substeps) do
        not yet emit an envelope and keep their already-derived actor: this branch
        is explicitly NOT a senate/population phase-entry receiver source.
        """
        # The dispatched command's success auto-refresh may have repopulated the
        # viewer (still A) projection; re-neutralize so no stale viewer residue is
        # visible while masked/pending.
        self._neutralize_public_projection()
        # D15-DIAG: read-only snapshot of the settle gate's own inputs (no token /
        # lease / handle / any credential). Only the fail-closed branches below
        # emit it; the SUCCESS path logs nothing.
        try:
            _diag_core = self._state.get_current_player().player_id
        except Exception:  # pragma: no cover - defensive
            _diag_core = None
        _diag_env = delivery if isinstance(delivery, dict) else {}
        _diag_next = _diag_env.get("next")
        if not isinstance(_diag_next, dict):
            _diag_next = {}
        _diag = {
            "core_current": _diag_core,
            "envelope_actor": _diag_next.get("actor_player_id"),
            "envelope_outcome": _diag_env.get("outcome"),
            "envelope_controller": _diag_next.get("controller"),
            "command_id": str((self._seat_txn or {}).get("command_id") or ""),
            "txn_id": str(txn_id or ""),
        }
        if delivery is not None:
            from src.api import session_turn_service
            verdict = session_turn_service.validate_delivery_result(
                self._state, delivery, viewer_id=self._viewer_id, legacy=legacy)
            if not verdict.get("ok"):
                _diag_err = verdict.get("error") or {}
                logger.warning(
                    "settle gate refused delivery: code=%s stage=%s",
                    _diag_err.get("code"), _diag_err.get("stage"),
                    extra=dict(_diag,
                               code=str(_diag_err.get("code") or ""),
                               stage=str(_diag_err.get("stage") or "")))
                return self._delivery_fail(
                    txn_id, verdict.get("error") or {}, done)
            # Only a VALIDATED envelope is recorded for a later bounded retry.
            self._last_delivery = {
                "delivery": delivery,
                "txn_id": txn_id,
                "scope_id": str(delivery.get("scope_id") or ""),
                "viewer": self._viewer_id,
            }
            outcome = delivery.get("outcome")
            nxt = delivery.get("next") or {}
            if outcome == session_turn_service.DELIVERY_OUTCOME_RESOLVED \
                    and nxt.get("controller") == session_turn_service.CONTROLLER_AI:
                logger.warning(
                    "settle gate refused delivery: code=%s stage=%s",
                    "DELIVERY_INVALID", "terminal",
                    extra=dict(_diag, code="DELIVERY_INVALID",
                               stage="terminal"))
                return self._delivery_fail(
                    txn_id,
                    session_turn_service.delivery_error(
                        "DELIVERY_INVALID", stage="terminal",
                        detail="an AI owner is not an ACTIVE seat"),
                    done)
            next_actor_id = nxt.get("actor_player_id")
        else:
            self._last_delivery = None
        if not next_actor_id:
            from src.api import session_turn_service
            _diag_code = session_turn_service.DELIVERY_MISSING_RECEIVER
            logger.warning(
                "settle gate refused delivery: code=%s stage=%s",
                _diag_code, "settle",
                extra=dict(_diag, code=str(_diag_code), stage="settle"))
            return self._delivery_fail(
                txn_id,
                session_turn_service.delivery_error(
                    session_turn_service.DELIVERY_MISSING_RECEIVER,
                    stage="settle",
                    detail="a successful command must deliver its receiver"),
                done)
        # Same HUMAN (explicitly delivered): recover the same seat at a new epoch
        # without an artificial 「接管」.
        if next_actor_id == self._viewer_id:
            return self._activate_seat(txn_id, self._viewer_id, same_seat=True,
                                       done=done)
        faction = self._safe_faction_name(next_actor_id)
        if not faction:
            # Invalid/stale/missing target -> fail closed (never guess a receiver).
            self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
            from src.api import session_turn_service
            result = self._handoff_failure_feedback(
                delivery_error=session_turn_service.delivery_error(
                    session_turn_service.DELIVERY_MISMATCH,
                    stage="target_faction", committed=True,
                    detail="the delivered target has no real faction"))
            if done is not None:
                done(result)
            return result
        self._pending_player_id = next_actor_id
        self._pending_faction_name = faction
        self._pending_token = uuid.uuid4().hex
        self._seat_lifecycle = SEAT_MASKED_PENDING
        self._handoff_busy = False
        if self._seat_txn is not None:
            # The transaction's OWN recorded target (bounded retry checkpoint).
            self._seat_txn["target_id"] = next_actor_id
        if not self._provider_call("show_pending", txn_id, faction):
            # Missing pending witness -> fail closed (SB-V05).
            self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
            result = self._handoff_failure_feedback()
            if done is not None:
                done(result)
            return result
        self._emit_seat()
        self.handoffMaskPending.emit(faction)
        self.handoffPendingFactionChanged.emit()
        logger.info("handoff pending", extra={"txn_id": txn_id, "seat_epoch": self._seat_epoch + 1})
        result = self._feedback(True, "等待下一位玩家接管", "success",
                                data={"accepted": True, "txn_id": txn_id})
        if done is not None:
            done(result)
        return result

    def _activate_seat(self, txn_id: str, target_id: str,
                       same_seat: bool = False,
                       done: Optional[Any] = None,
                       commit_proven: Optional[bool] = True) -> Dict[str, Any]:
        """R2 steps 6-8 (F4 async): stage the target's DTOs privately, await the
        PUBLICATION-UNDER-MASK real frame, commit the authority, await the
        FINAL-REVEAL real frame, and ONLY THEN run the visibility commit (publish
        the staged bundle + issue the fresh public handle + ACTIVE + ``True``).

        Public getters remain neutral through the whole ACTIVATE phase: no public
        backing model is filled and no public property signal is emitted until the
        final frame receipt. A denied/empty read, a missing frame, or an unmask
        miss fails closed (no fresh handle) (SB-V04).
        """
        self._activation_result = None

        def _fail_activation(stage: str = "settlement_exception",
                             code: str = "SEAT_PUBLICATION_FAILED"
                             ) -> Dict[str, Any]:
            """ONE joint classifier shared by EVERY exit of this activation.

            A-W3-13 / AC-W3-19 (§9.1) / W3-C1-B: the commit context is the
            TRI-STATE ``commit_proven``, evaluated IDENTICALLY at the early exits
            (``activation_txn`` / ``core`` / ``staging`` / ``freshness``) and at
            the late ones (``publish_frame`` / ``unmask_frame`` / ``apply`` /
            ``settlement_exception``). A PROVEN non-commit -- and equally an
            UNPROVEN dispatch -- is NEVER reported as ``after_commit`` and never
            seals a recovery mandate; ``commit_proven is None`` keeps the
            ``committed`` key OMITTED (never a fabricated boolean, and never the
            ``committed=True`` default leaking into a pre-commit refusal).
            """
            kind = (FAIL_BEFORE_COMMIT
                    if commit_proven is None or not commit_proven
                    else FAIL_AFTER_COMMIT)
            self._fail_masked(kind, txn_id)
            result = self._handoff_failure_feedback(
                delivery_error=self._typed_delivery_error(
                    code, stage, committed=commit_proven))
            self._finish_activation(done, result)
            return result

        if self._seat_txn is None:
            # The transaction record is GONE, so this activation can never prove a
            # commit: the guard carries the CALLER's exact context and fails
            # closed (it must never fall back to the ``committed=True`` default).
            return _fail_activation("activation_txn")
        self._seat_lifecycle = SEAT_ACTIVATE
        self._handoff_busy = True
        if self._seat_txn is not None:
            # The transaction's OWN recorded target (a bounded retry re-validates
            # this, never the Core cursor).
            self._seat_txn["target_id"] = target_id
        self._emit_seat()
        # Recheck the Core target before the stage commit (R3b F5: the SAME-seat
        # recovery path also validates the current target). This is a NEGATIVE
        # read-back of the delivered target, never a new target source (§9 core).
        current = self._state.get_current_player()
        current_id = getattr(current, "player_id", None)
        if current_id != target_id:
            return _fail_activation("core", code="DELIVERY_MISMATCH")
        new_epoch = self._seat_epoch + 1
        # 1. PRIVATE staging under the internal neutral activation capability; no
        #    public getter is exposed and a denied/empty read fails closed.
        staged = self._stage_activation(target_id, new_epoch)
        if staged is None:
            return _fail_activation("staging")
        # F4 / D-W3-D07 / A-W3-05: the ONE full private rebuild above is the only
        # path that can clear a stale REQUIRED projection. Freshness is now
        # evaluated AFTER the rebuild and ONLY for this activation/publication
        # (a cross-seat MASKED_PENDING publishes nothing and is never blocked).
        for rid in self._required_resource_ids():
            if rid in (staged.get("resources") or {}):
                self._stale_resources.pop(rid, None)
        still_stale = self._stale_write_dependencies()
        if still_stale:
            # W3-C1-B: the staleness DECISION above is untouched (AC11 owns that
            # surface); only the FAILURE CLASSIFICATION is routed through the
            # joint classifier, so a FALSE recovery branch is never
            # ``after_commit`` and seals nothing.
            logger.warning("activation refused: projection still stale (%s)",
                           still_stale)
            return _fail_activation("freshness", code="STALE_REQUIRED_RESOURCE")

        def after_unmask(ok):
            if not ok:
                self._reveal_pending = False
                _fail_activation("unmask_frame")
                return
            # ---- visibility commit (only after the final-reveal real frame) ---
            # W2b (FC-712-17): whole-package validation + atomic publication. A
            # bundle that is not publishable (missing REQUIRED / schema / stale
            # tag / foreign txn) publishes NOTHING and keeps the seat masked.
            if not self._apply_staged(staged, target_id=target_id):
                self._reveal_pending = False
                _fail_activation("apply")
                return
            self._viewer_id = target_id
            self._reveal_pending = False
            session_access.issue_fresh_handle(self._state)
            self._seat_lifecycle = SEAT_ACTIVE
            self._handoff_busy = False
            self._handoff_failure_kind = ""
            self._handoff_failure_route = RECOVER_ROUTE_ACTIVATION
            self._pending_player_id = ""
            self._pending_faction_name = ""
            self._pending_token = ""
            self._seat_txn = None
            self._last_delivery = None
            self._delivery_required_command = ""
            session_access.clear_command_lease(self._state)
            self._emit_seat()
            self.handoffFinished.emit(txn_id, True)
            logger.info("handoff activated", extra={"txn_id": txn_id,
                                                    "seat_epoch": self._seat_epoch})
            self._finish_activation(done, self._feedback(
                True, "已接管本席", "success",
                data={"accepted": True, "txn_id": txn_id, "activated": True}))

        def after_publish(ok):
            if not ok:
                _fail_activation("publish_frame")
                return
            # AUTHORITY COMMIT strictly AFTER the under-mask publication frame and
            # strictly BEFORE any public pixel/handle: record ACTIVE(B) WITHOUT a
            # fresh public handle so no read/write can observe B before the reveal.
            self._seat_epoch = new_epoch
            session_access.commit_hotseat_principal(self._state, target_id, new_epoch)
            self._reveal_pending = True
            self._emit_seat()
            # (b) final-reveal frame gate.
            if self._begin_frame_gate("unmask", txn_id, after_unmask):
                return                  # suspended: awaits the final real frame
            if not self._provider_call("request_unmask", txn_id):
                self._reveal_pending = False
                _fail_activation("unmask_frame")
                return
            after_unmask(True)

        # (a) publication-under-mask frame gate: the staged bundle is bound under
        #     the still-opaque cover; the public getters remain neutral.
        if not self._begin_frame_gate("publish", txn_id, after_publish):
            after_publish(True)
        if self._activation_result is not None:
            return self._activation_result
        return self._masked_pending_feedback(txn_id)

    @staticmethod
    def _is_masked_continuation_failure(feedback: Any) -> bool:
        """SD-R02 / SD1-V01 / R1-01 (§1.1.R): True iff ``feedback`` is the coordinator's
        AI-drain continuation MASKED_FAILURE (a masked safe failure), never a
        public DENIED / ordinary business refusal.

        R1-01 (S-D-1-R2) — the recognizer REQUIRES an EXPLICIT failure
        discriminant AND BOTH markers of the ACTUAL producer envelope:

        * ``feedback`` must be a ``dict`` whose ``feedback["success"]`` is the
          explicit boolean ``False``. A truthy ``success`` — and equally a
          missing / ``None`` / empty / non-boolean ``success`` — is REJECTED:
          "reject truthy success" is not enough, because an absent or malformed
          outcome cannot affirm post-commit continuation provenance.
        * the masked evidence must carry BOTH real post-commit producer markers
          (``session_api.submit_population_votes`` for N7-R and the senate AI
          vote drain for N10-R; the Adapter preserves ``data`` / ``errors``
          verbatim)::

              success = False
              data    = {"status": "masked_failure", "resolved": False,
                         "retryable": True, "reason": <reason>, ...}
              errors  = [{"code": "AI_DRAIN_MASKED_FAILURE", ...}]

          i.e. BOTH ``data.status == MASKED_CONTINUATION_STATUS`` AND a typed
          ``errors[].code == MASKED_CONTINUATION_ERROR_CODE`` must be present.
          THE REQUIREMENT IS NOT RELAXED: neither marker alone, and never a
          boolean-only ``masked_failure`` key, is sufficient evidence.

        A shape it does not recognise — an ordinary non-mutating business
        refusal, an activation failure, or a malformed/partial envelope — is NOT
        a continuation failure (never a silent default to ``continuation``).
        """
        if not isinstance(feedback, dict) or feedback.get("success") is not False:
            return False
        data = feedback.get("data")
        if not (isinstance(data, dict)
                and data.get("status") == MASKED_CONTINUATION_STATUS):
            return False
        errors = feedback.get("errors")
        if not isinstance(errors, (list, tuple)):
            return False
        for err in errors:
            if (isinstance(err, dict)
                    and err.get("code") == MASKED_CONTINUATION_ERROR_CODE):
                return True
        return False

    def _fail_masked(self, kind: str, txn_id: str = "",
                     route: str = RECOVER_ROUTE_ACTIVATION) -> None:
        """Fail closed: keep/re-arm the neutral cover, revoke the pending token,
        drop the pending target metadata + the one-use lease, fail the SERVICE
        authority, never publish and emit ``handoffFinished(txn, False)``.

        ``route`` is the SD-R02 (§1.1.R) safe, exclusive failure-origin token; it
        is copied to the overlay so the single bounded failure action can be
        shown. It is never player copy and is not an authorization predicate."""
        if not txn_id and self._seat_txn:
            txn_id = self._seat_txn.get("txn_id", "")
        self._handoff_failure_kind = kind
        self._handoff_failure_route = route
        self._seat_lifecycle = SEAT_MASKED_FAILURE
        self._handoff_busy = False
        self._pending_token = ""
        # SB-V06: clear the stale pending target metadata (no stale label retained).
        self._pending_player_id = ""
        self._pending_faction_name = ""
        self.handoffPendingFactionChanged.emit()
        if self._seat_txn is not None:
            self._seat_txn["failed"] = True
        # SB-V03: the service stays suspended/failed (public reads/writes deny) and
        # the one-use command lease is destroyed (no repeat-command capability).
        session_access.fail_hotseat_session(self._state)
        session_access.clear_command_lease(self._state)
        # D4/D6 I2-R1 §2b (FC-D46-04/seal): a PROVEN POST-COMMIT failure is the ONLY
        # point that seals the current ARMED recovery mandate FAILED_RECOVERABLE, so
        # the public recovery chain (Store doRecoverContinuation -> Adapter -> public
        # guard) can be driven in the I1/I2 semantics. The old lease/scope/handle are
        # destroyed ABOVE (unchanged); the mandate is NOT a lease and survives the
        # failure (PC-RA-02) — but only for a real post-commit failure. A pre-commit
        # failure (no commit happened) seals NOTHING (no legitimate recovery source).
        if kind == FAIL_AFTER_COMMIT:
            session_access.seal_recovery_mandate_for_failure(self._state)
        # SB-V04.4 (D): a PRE-commit failure must ALSO neutralize every exposed
        # model (the old after_commit-only guard left the old A backing models
        # populated/accessible when arming failed). Never leave stale residue.
        self._neutralize_public_projection()
        self._provider_call("show_failure", txn_id, kind, route)
        self._emit_seat()
        self.handoffFinished.emit(txn_id, False)

    def _masked_business_rejection(self, txn_id: str, feedback: Dict[str, Any],
                                   done: Optional[Any] = None) -> Dict[str, Any]:
        """A legitimate business refusal did NOT mutate: recover the SAME seat
        through the SAME fresh-EPOCH activation protocol (DG-03 §3.3A / D) — never
        a re-stage at the old epoch. Rebuild the private bundle, commit the same
        principal at a NEW epoch, publish under the mask, request the unmask
        witness, then issue the fresh handle. A failed unmask stays fail-closed
        and is a PRE-COMMIT failure (never ``after_commit``).

        AC-W3-19 (§9.1) / W3-C1-C: when that recovery fails, the caller gets the
        ORIGINAL refusal with its FOUR public fields byte-faithful (``success`` /
        ``message`` / ``errors`` / ``data`` — value, key presence and type) and the
        typed ``{code, stage, committed:false}`` record on the PRIVATE carrier
        (``_w3_recovery_diagnostic`` / the private ``_activation_result``), never
        injected into the rejected object.
        """
        def _after(_activation_result):
            if isinstance(_activation_result, dict) \
                    and _activation_result.get("success"):
                self._w3_recovery_diagnostic = None
                self._raise_feedback(feedback)
                if done is not None:
                    done(feedback)
                return
            # The refusal did not commit (commit_proven=False); its same-seat
            # recovery did not complete either.
            # W3-C1-C (AC-W3-19 §9.1): the ORIGINAL refusal is returned with its
            # FOUR public fields byte-faithful (``success`` / ``message`` /
            # ``errors`` / ``data`` — value, key presence AND type). The recovery
            # diagnostic is NEVER written into the rejected object: no
            # ``data["delivery_error"]`` injection, no ``None -> {}`` rewrite and no
            # overwrite of a producer's own record. It lives ONLY on the private
            # carrier below (and on the existing private ``_activation_result``).
            typed = None
            if isinstance(_activation_result, dict):
                activation_data = _activation_result.get("data")
                if isinstance(activation_data, dict):
                    typed = activation_data.get("delivery_error")
            if not isinstance(typed, dict):
                typed = self._typed_delivery_error(
                    "SEAT_PUBLICATION_FAILED", "business_rejection",
                    committed=False)
            self._w3_recovery_diagnostic = {
                "code": str(typed.get("code") or ""),
                "stage": str(typed.get("stage") or ""),
                "committed": typed.get("committed"),
                "txn_id": txn_id,
                "delivery_error": dict(typed),
            }
            self._raise_feedback(feedback)
            if done is not None:
                done(feedback)
        self._activate_seat(txn_id, self._viewer_id, same_seat=True, done=_after,
                            commit_proven=False)
        return feedback

    def _senate_settlement_pending(self) -> bool:
        """True iff the REAL all-ballots/ready predicate says the senate can be
        finalised (the exact predicate the server-side finalization guard uses).

        Read-only coordinator probe; it never writes the ledger/cursor and never
        derives readiness from the Store's cached DTO.
        """
        try:
            from src.api import session_turn_service
            return bool(session_turn_service.phase_ready(self._state, "senate"))
        except Exception:  # pragma: no cover - defensive
            logger.exception("senate readiness probe failed")
            return False

    def _converge_senate_settlement(self) -> bool:
        """item3 §2a S3/S4 (G5 I2-R3 REWORK): restore the LEGACY settlement
        convergence INSIDE the owning-dispatch scope.

        The legacy synchronous branches call ``resolve_senate`` after a vote
        (zero-passed / resolver-backed ``veto_control_mode == "NONE"``) and
        unconditionally after a HUMAN veto. The masked branches used to RETURN
        before those blocks, so with a barrier provider bound (the real GUI path,
        ``app.py:286``) the senate was never finalised (deadlock).

        ``senate_api.resolve_senate`` is the compatibility alias of the canonical
        owner writer ``finalize_senate_if_ready``; the owning-scope helper
        registry grants the CANONICAL label (not the retired alias label), so the
        Store calls the SAME writer directly. It is self-gated by the server's
        real readiness predicate and REFUSES otherwise, so no phase is ever
        resolved early (legacy parity: resolve only after all ballots / the veto
        decision).

        Must be invoked from INSIDE ``_dispatch_owning`` (the continuation scope
        only exists there); never from the seat-settle step.
        """
        if not self._senate_settlement_pending():
            return False
        from src.api import senate_api
        feedback = self._adapter.call(senate_api.finalize_senate_if_ready, self._state)
        if not feedback.get("success"):
            # Legacy behaviour surfaces the refusal but keeps the committed
            # command's result (never a second business decision).
            logger.info("senate settlement convergence refused: %s",
                        feedback.get("message", ""))
            return False
        return True

    def _settle_after_senate_command(self, txn_id: str, feedback: Dict[str, Any],
                                     done: Optional[Any] = None) -> Dict[str, Any]:
        """item3 §2a S5 (Errata E1/E2, design §3.3): terminal-aware settlement for
        a committed senate owning command.

        The senate itself is settled INSIDE the same masked transaction, by the
        in-scope convergence (``_converge_senate_settlement``, S3/S4) run by the
        owning dispatch; this helper must never settle the seat alone. It consumes
        ONLY the typed ``delivery`` envelope the owning command returned (the
        command's built-in continuation output, passed through by ``senate_api``):

        * no envelope -> typed ``DELIVERY_MISSING_RECEIVER / settle / true``;
        * otherwise the envelope's own ``next``/``terminal`` decides the seat (the
          validator rejects a forged/stale/AI-seat terminal). The legacy
          ``awaiting_player_id`` / ``actor`` / ``status`` / ``controller`` fields
          are NEVER a receiver source (L3/L6 retired).

        It never recomputes G, never reads a DTO backwards, and never uses
        ``cursor_restored`` as an activation credential.
        """
        data = feedback.get("data") if isinstance(feedback, dict) else None
        if not isinstance(data, dict):
            data = {}
        delivery = data.get("delivery") if isinstance(data.get("delivery"), dict) \
            else None
        if delivery is None:
            # W-05 / L3+L6: the legacy ``awaiting_player_id`` / ``actor`` /
            # ``status`` / ``controller`` fallbacks are GONE. A committed owning
            # command without its envelope is a typed missing-receiver failure
            # (AC-W3-10), never a same-seat guess.
            from src.api import session_turn_service
            return self._delivery_fail(
                txn_id,
                session_turn_service.delivery_error(
                    session_turn_service.DELIVERY_MISSING_RECEIVER,
                    stage="settle", committed=True,
                    detail="a successful senate command must deliver its receiver"),
                done)
        return self._settle_seat_after_success(
            txn_id, next_actor_id=None, done=done, delivery=delivery,
            legacy=data)

    def _masked_senate_owning_flow(self, command_id: str, lease_command: str,
                                   dispatch, converge=None, *,
                                   ai_proposer_origin: Optional[Any] = None
                                   ) -> Dict[str, Any]:
        """item3 §2a (S1–S4/S6): run a senate owning command through the SAME
        masked seat-handoff machine the population/forum paths use (mirrors
        ``_masked_forum_finish``).

        Under ONE masked transaction the seat is suspended, the owning command is
        dispatched inside the private owning-dispatch nesting (which is what makes
        the item3 owning-possession gate TRUE, so the command's built-in
        continuation can reach the UNIQUE senate terminal), and then settled via
        :meth:`_settle_after_senate_command` (S5).

        ``converge`` (S3/S4, optional) runs INSIDE the same owning-dispatch scope
        after a successful command — it restores the legacy ``resolve_senate``
        settlement convergence (zero-passed / NONE-veto / HUMAN veto) so the
        senate is finalised in the SAME masked transaction, never only the seat.
        It is invoked while the continuation scope is live because the canonical
        owner writer is only authorized there.

        * a post-commit AI-drain continuation MASKED_FAILURE -> ``_fail_masked``
          with ``route=RECOVER_ROUTE_CONTINUATION`` (S6 — the bounded continuation
          recovery, never an activation retry);
        * an ordinary non-mutating business refusal -> same-seat recovery;
        * an unexpected exception -> fail closed (after-commit mask).

        Only entered when a barrier provider is bound (production async host); the
        legacy synchronous path stays byte-for-byte unchanged for every other
        caller.
        """
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if self._seat_lifecycle != SEAT_ACTIVE or self._handoff_busy:
            return self._feedback(False, "当前无法执行本席操作", "error")
        holder = {"r": None}

        def done(result):
            holder["r"] = result

        def cont(txn, ok, fail_result):
            txn_id = txn["txn_id"]
            if not ok:
                done(fail_result)
                return
            try:
                def _owning_dispatch():
                    dispatched = dispatch()
                    if (converge is not None
                            and isinstance(dispatched, dict)
                            and dispatched.get("success")):
                        converge()
                    return dispatched
                feedback = self._dispatch_owning(txn, lease_command, _owning_dispatch)
                self._committed_receipt = feedback
                if not feedback.get("success"):
                    if self._is_masked_continuation_failure(feedback):
                        self._fail_masked(FAIL_AFTER_COMMIT, txn_id,
                                          route=RECOVER_ROUTE_CONTINUATION)
                        done(self._handoff_failure_feedback())
                        return
                    # D13（Option 4）：只有真实 typed seat `DENIED` + 有效 AI origin
                    # 才立 UI-local 锁；普通校验/已提交 → 可重试，不锁、不贴授权失败。
                    blocked = (ai_proposer_origin is not None
                               and self._is_ai_proposer_seat_denied(feedback))
                    if blocked:
                        self._senate_ai_proposer_blocked = True
                        self._senate_ai_proposer_blocked_reason = (
                            self.AI_PROPOSER_BLOCK_REASON)
                        self._senate_ai_proposer_block_key = ai_proposer_origin
                        self.senateViewChanged.emit()

                    def _after_rejection(_result):
                        # 只在本事务的真实同席激活 **成功** 后重发原结构化错误并
                        # 消费 reason（原 message/data/errors 不改写）。
                        if (blocked
                                and self._seat_lifecycle == SEAT_ACTIVE
                                and isinstance(self._activation_result, dict)
                                and self._activation_result.get("success")
                                and self._senate_ai_proposer_block_key == ai_proposer_origin
                                and self._senate_ai_proposer_origin() == ai_proposer_origin):
                            self._apply_senate_submit_feedback(feedback)
                            self._raise_feedback(self._feedback(
                                False, self._senate_ai_proposer_blocked_reason, "error"))
                            self.senateViewChanged.emit()
                        if done is not None:
                            # AC-W3-19 (§9.1): on a FAILED same-seat recovery the
                            # result is the original refusal + the typed record;
                            # never re-send only the bare refusal.
                            done(_result if isinstance(_result, dict) else feedback)

                    self._masked_business_rejection(txn_id, feedback,
                                                    done=_after_rejection)
                    return
                # E-D13-4.2：成功清锁必须**归属于该锁的同一 owner**（origin 三元
                # = session/step/viewer）。同 owner → 清；不同 owner 或无法证明
                # （origin 为 None）→ 保锁（fail-closed）。禁止「任意成功即清」。
                if (ai_proposer_origin is not None
                        and self._senate_ai_proposer_block_key is not None
                        and ai_proposer_origin == self._senate_ai_proposer_block_key):
                    self._clear_ai_proposer_guard()
                self._settle_after_senate_command(txn_id, feedback, done=done)
            except Exception:
                logger.exception("masked senate owning flow failed")
                # AC-W3-19 / G3-delta §9.1: an unexpected DISPATCH exception cannot
                # prove whether the command committed. The commit state is
                # UNPROVEN: keep the neutral mask on the GENERIC (never
                # after_commit) route — no recovery mandate is sealed, nothing is
                # replayed — and carry the typed diagnostic with the ``committed``
                # key OMITTED (never a fabricated true/false).
                self._fail_masked(FAIL_BEFORE_COMMIT, txn_id)
                done(self._handoff_failure_feedback(
                    delivery_error=self._typed_delivery_error(
                        "COMMIT_STATUS_UNPROVEN", "dispatch", committed=None)))

        txn = self._begin_masked_seat_transition(
            command_id, lease_command=lease_command, payload={}, cont=cont)
        if txn is None:
            return self._handoff_failure_feedback()
        if holder["r"] is not None:
            return holder["r"]
        return self._masked_pending_feedback(txn["txn_id"])

    def _handoff_failure_feedback(self,
                                  delivery_error: Optional[Dict[str, Any]] = None
                                  ) -> Dict[str, Any]:
        kind = self._handoff_failure_kind or FAIL_AFTER_COMMIT
        if kind == FAIL_AFTER_COMMIT:
            msg = "操作已记录，界面尚未准备好。请重试进入回合。"
        else:
            msg = "暂未进入回合，请重试。"
        feedback = self._feedback(False, msg, "error")
        if delivery_error:
            # W-11 / §9.2: an ADDITIVE typed diagnostic on the Store-private
            # feedback (the original message/errors/failureKind stay byte-equal).
            feedback["data"] = {"delivery_error": delivery_error}
        return feedback

    @Slot(str, result=dict)
    def confirmHandoffAsync(self, pending_token: str) -> dict:
        """Explicit 「接管」 activation (R2 step 6). The pending token is single-use
        and compared to the current private pending target; the raw id/epoch are
        never parameters. ``accepted`` is NOT success."""
        if self._seat_lifecycle != SEAT_MASKED_PENDING:
            return {"accepted": False, "txn_id": "", "reason": "not_pending"}
        if not pending_token or pending_token != self._pending_token:
            # Wrong/stale/duplicate confirmation -> structured refusal, no change.
            return {"accepted": False, "txn_id": self._seat_txn.get("txn_id", "")
                    if self._seat_txn else "", "reason": "denied"}
        txn_id = self._seat_txn.get("txn_id", "") if self._seat_txn else ""
        target = self._pending_player_id
        self._pending_token = ""  # single-use
        self._activate_seat(txn_id, target)
        return {"accepted": True, "txn_id": txn_id}

    @Slot(result=dict)
    def requestTakeover(self) -> dict:
        """QML 「接管」 intent — the Store supplies its PRIVATE pending token, so no
        raw token/epoch ever reaches QML (R2). Delegates to confirmHandoffAsync."""
        return self.confirmHandoffAsync(self._pending_token)

    @Slot(result=dict)
    def retryHandoff(self) -> dict:
        """Bounded recovery from MASKED_FAILURE: re-validate the EXACT envelope
        this transaction recorded and re-arm with a fresh R2 reservation/token.
        Never reads the Core cursor as a target, never replays A's action or the
        already-consumed AI turns (W-04 / A-W3-03 / D-W3-D08)."""
        if self._seat_lifecycle != SEAT_MASKED_FAILURE:
            return {"accepted": False, "txn_id": "", "reason": "not_failed"}
        from src.api import session_turn_service
        recorded = self._last_delivery if isinstance(self._last_delivery, dict) else None
        if not recorded and not self._delivery_required_command:
            # Out-of-scope legacy transaction (startup / population / forum): its
            # own recorded target is the bounded retry checkpoint (never Core).
            recorded_target = str((self._seat_txn or {}).get("target_id") or "")
            if not recorded_target:
                return {
                    "accepted": False, "txn_id": "", "reason": "no_delivery",
                    "delivery_error": session_turn_service.delivery_error(
                        session_turn_service.DELIVERY_MISSING_RECEIVER,
                        stage="retry", committed=True,
                        detail="no recorded envelope or transaction target"),
                }
            recorded = {"delivery": {"next": {"actor_player_id": recorded_target}}}
        if not recorded:
            # AC-W3-08: no recorded envelope -> typed STOP, zero activation.
            return {
                "accepted": False, "txn_id": "", "reason": "no_delivery",
                "delivery_error": session_turn_service.delivery_error(
                    session_turn_service.DELIVERY_MISSING_RECEIVER,
                    stage="retry", committed=True,
                    detail="no recorded delivery envelope to re-validate"),
            }
        delivery = recorded.get("delivery") or {}
        if self._delivery_required_command:
            verdict = session_turn_service.validate_delivery_result(
                self._state, delivery, viewer_id=self._viewer_id, legacy=None)
            if not verdict.get("ok"):
                return {"accepted": False, "txn_id": "", "reason": "delivery_invalid",
                        "delivery_error": verdict.get("error") or {}}
        target = (delivery.get("next") or {}).get("actor_player_id")
        if not target:
            return {
                "accepted": False, "txn_id": "", "reason": "no_receiver",
                "delivery_error": session_turn_service.delivery_error(
                    session_turn_service.DELIVERY_MISSING_RECEIVER,
                    stage="retry", committed=True,
                    detail="the recorded envelope has no receiver"),
            }
        holder = {"r": None}

        def cont(txn, ok, fail_result):
            txn_id = txn["txn_id"]
            if not ok:
                holder["r"] = {"accepted": False, "txn_id": txn_id, "reason": "barrier"}
                return
            if not target or target == self._viewer_id:
                self._activate_seat(
                    txn_id, self._viewer_id, same_seat=True,
                    done=lambda r: holder.__setitem__(
                        "r", {"accepted": True, "txn_id": txn_id}))
                return
            faction = self._safe_faction_name(target)
            if not faction:
                self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
                holder["r"] = {"accepted": False, "txn_id": txn_id, "reason": "target"}
                return
            self._pending_player_id = target
            self._pending_faction_name = faction
            self._pending_token = uuid.uuid4().hex
            self._seat_lifecycle = SEAT_MASKED_PENDING
            self._handoff_busy = False
            if not self._provider_call("show_pending", txn_id, faction):
                self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
                holder["r"] = {"accepted": False, "txn_id": txn_id, "reason": "pending"}
                return
            self._emit_seat()
            self.handoffMaskPending.emit(faction)
            self.handoffPendingFactionChanged.emit()
            holder["r"] = {"accepted": True, "txn_id": txn_id}

        txn = self._begin_masked_seat_transition("retry", cont=cont)
        if txn is None:
            return {"accepted": False, "txn_id": "", "reason": "barrier"}
        if holder["r"] is not None:
            return holder["r"]
        return {"accepted": True, "txn_id": txn["txn_id"], "pending": True}

    @Slot(result=dict)
    def doRecoverContinuation(self) -> dict:
        """``grContinuationRecover`` — bounded S-C continuation recovery (AI-drain only).

        Authorized ONLY in MASKED_FAILURE for an AI-drain continuation failure;
        mutually exclusive with ``grHandoffRetry`` (activation-only) and
        ``grResolutionRetrySettlement`` (resolution-entry only). Delegates to the
        coordinator's recovery control, which resumes only outstanding scheduled-AI
        work; the committed HUMAN command is never resubmitted (same-revision DK
        replay denied). Registration in the frozen ``G2-R5`` §6 inventory is a
        separate governance follow-on, not part of this slice.
        """
        if self._seat_lifecycle != SEAT_MASKED_FAILURE:
            return self._feedback(False, "当前无待恢复的继续处理", "warning")
        # D4/D6 I1 (PC-RA-01/05, §5): the Store sends a PRIVATE, no-argument
        # intent. It supplies NO mandate id and NO viewer string, and it NEVER
        # calls the coordinator directly: the intent still routes through the
        # public Adapter -> public guard, and the service-private possession is
        # presented by the trusted routing layer. A seat that holds a sealed
        # recovery mandate takes the new authority path; every legacy
        # (mandate-less) seat keeps the unchanged S-C continuation route
        # (RA Delta §1.1 EXCLUDE).
        if session_access.has_failed_recoverable_mandate(self._state):
            return self._dispatch_recovery_authority_intent()
        feedback = self._adapter.recover_continuation("")
        self._raise_feedback(feedback)
        return feedback

    def _dispatch_recovery_authority_intent(self) -> dict:
        """Broker the sealed-mandate recovery as a no-arg private intent.

        The service mints the single-use attempt cap (only when the permitted
        resume-kind is determinate; a multi-kind mandate needs the real owner
        checkpoint, wired in I2) and the trusted routing layer arms the private
        possession around the ONE dispatch; the public Adapter -> public guard
        then adjudicates. The Store never mints/consumes a cap and never calls
        the coordinator directly.
        """
        handle = session_access.current_recovery_invocation(self._state)
        # D4/D6 I2-R3 item3 §5.2 (Errata E5): the resume-kind is resolved by the
        # coordinator-owned owner checkpoint via the trusted Adapter (read-only),
        # NOT by the I1 cardinality proxy (``determinate_recovery_resume_kind``
        # is permanently None for every multi-kind admission row). The Store
        # still sends a no-argument private intent and never picks a kind; the
        # resolver membership-validates the derived kind against the mandate.
        kind = self._adapter.recovery_resume_kind()
        if handle is None or kind is None:
            # Fail closed: no possession, or a resume-kind that requires the I2
            # owner checkpoint -> no brokered recovery (never a direct call).
            feedback = self._feedback(False, "当前无待恢复的继续处理", "warning")
            self._raise_feedback(feedback)
            return feedback
        capability = session_access.issue_recovery_attempt(
            self._state, resume_kind=kind)
        if capability is None:
            feedback = self._feedback(False, "当前无待恢复的继续处理", "warning")
            self._raise_feedback(feedback)
            return feedback
        session_access.begin_recovery_nesting(self._state, capability)
        try:
            feedback = self._adapter.recover_continuation("")
        finally:
            session_access.end_recovery_nesting(self._state)
        self._raise_feedback(feedback)
        return feedback

    @Slot(result=dict)
    def requestHandoffExit(self) -> dict:
        """Bounded safe-exit request from the masked overlay (SB-V06).

        Allowed only in MASKED_PENDING / MASKED_FAILURE; it never bypasses
        activation. R2 §4 step 8: exit/shutdown INVALIDATES the transaction and all
        issued handles BEFORE the host tears the window down; the production host
        connects ``handoffExitRequested`` to the existing safe application exit.
        """
        if self._seat_lifecycle not in (SEAT_MASKED_PENDING, SEAT_MASKED_FAILURE):
            return {"success": False, "reason": "not_allowed"}
        self._invalidate_handoff_for_exit()
        self.handoffExitRequested.emit()
        return {"success": True}

    def _invalidate_handoff_for_exit(self) -> None:
        """R2 §4 step 8: exit/shutdown invalidates the txn + every handle. No
        public projection survives; the seat stays neutral (MASKED_FAILURE) so a
        restored/re-entered window must re-arm before showing any data."""
        self._pending_token = ""
        self._pending_player_id = ""
        self._pending_faction_name = ""
        if self._seat_txn is not None:
            self._seat_txn["failed"] = True
        self._seat_txn = None
        session_access.revoke_hotseat_session(self._state)
        session_access.clear_command_lease(self._state)
        self._seat_lifecycle = SEAT_MASKED_FAILURE
        self._handoff_busy = False
        self._neutralize_public_projection()
        self.handoffPendingFactionChanged.emit()
        self._emit_seat()

    def _begin_neutral_startup(self, first_human_id: str) -> None:
        """E — neutral startup (R2 §3 / SB-V04 startup): enter a neutral
        MASKED_PENDING instead of publishing the factory-chosen actor. ONLY the
        validated safe faction name + neutral reserved slot are exposed until an
        explicit first-HUMAN 「接管」 (``requestTakeover``) completes the
        transaction. No startup publish."""
        txn_id = uuid.uuid4().hex
        self._seat_txn = {
            "txn_id": txn_id,
            "seat_epoch": self._seat_epoch + 1,
            "command_id": "startup",
            "armed": True,
            "cleared": True,
        }
        human_count = sum(
            1 for p in self._state.get_all_players()
            if getattr(p, "player_type", None) == PlayerType.HUMAN
        )
        self._startup_mode = "single_human" if human_count == 1 else "multi_human"
        # PC712-03 / W2a: a single-HUMAN startup page carries NO faction
        # identity. 3H keeps the existing safe faction name byte-for-byte.
        faction = ("" if self._startup_mode == "single_human"
                   else self._safe_faction_name(first_human_id))
        self._pending_player_id = first_human_id
        self._pending_faction_name = faction
        self._pending_token = uuid.uuid4().hex
        self._seat_lifecycle = SEAT_MASKED_PENDING
        self._handoff_busy = False
        self._handoff_failure_kind = ""
        self._handoff_failure_route = RECOVER_ROUTE_ACTIVATION
        # The service authority is suspended: no read/write publishes before the
        # explicit first-HUMAN takeover.
        session_access.suspend_hotseat_session(
            self._state, lifecycle_epoch=self._seat_epoch + 1)
        self._neutralize_public_projection()
        if self._startup_mode == "single_human":
            self._provider_call("show_pending", txn_id, faction,
                                self._startup_mode)
        else:
            # 3H: keep the historical two-argument provider call.
            self._provider_call("show_pending", txn_id, faction)
        self._emit_seat()
        self.startupChanged.emit()
        self.handoffMaskPending.emit(faction)
        self.handoffPendingFactionChanged.emit()

    def _masked_do_complete_player(self) -> dict:
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        # SB-V03: transaction-exclusive entry check (only from ACTIVE).
        if self._seat_lifecycle != SEAT_ACTIVE or self._handoff_busy:
            return self._feedback(False, "当前无法执行本席操作", "error")
        # Determine the ONE exact command to dispatch BEFORE suspension so the
        # exact one-use lease binds it (DG-03 §3.2).
        all_humans_complete = self._adapter.all_human_population_votes_complete()
        lease_command = ("resolve_population_slice" if all_humans_complete
                         else "next_player")
        holder = {"r": None}

        def done(result):
            holder["r"] = result

        def cont(txn, ok, fail_result):
            txn_id = txn["txn_id"]
            if not ok:
                done(fail_result)
                return
            try:
                if all_humans_complete:
                    feedback = self._dispatch_owning(
                        txn, lease_command, self._adapter.resolve_election)
                    self._committed_receipt = feedback
                    if not feedback.get("success"):
                        # SD-R02 (§1.1.R): an AI-drain continuation masked failure
                        # is routed as ``continuation`` so the overlay offers ONLY
                        # the bounded continuation recovery (never activation retry).
                        if self._is_masked_continuation_failure(feedback):
                            self._fail_masked(FAIL_AFTER_COMMIT, txn_id,
                                              route=RECOVER_ROUTE_CONTINUATION)
                            done(self._handoff_failure_feedback())
                            return
                        self._masked_business_rejection(txn_id, feedback, done=done)
                        return
                    self._settle_seat_after_success(
                        txn_id, next_actor_id=None, done=done,
                        delivery=(feedback.get("data") or {}).get("delivery"))
                    return
                feedback = self._dispatch_owning(
                    txn, lease_command, self._adapter.next_player, self._viewer_id)
                self._committed_receipt = feedback
                if not feedback.get("success"):
                    # SD-R02 (§1.1.R): route an AI-drain continuation masked
                    # failure to the continuation recovery (not activation retry).
                    if self._is_masked_continuation_failure(feedback):
                        self._fail_masked(FAIL_AFTER_COMMIT, txn_id,
                                          route=RECOVER_ROUTE_CONTINUATION)
                        done(self._handoff_failure_feedback())
                        return
                    self._masked_business_rejection(txn_id, feedback, done=done)
                    return
                new_id = (feedback.get("data") or {}).get("new_player_id")
                self._settle_seat_after_success(
                    txn_id, next_actor_id=new_id, done=done,
                    delivery=(feedback.get("data") or {}).get("delivery"))
            except Exception:
                logger.exception("masked doCompletePlayer failed")
                self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
                done(self._handoff_failure_feedback())

        txn = self._begin_masked_seat_transition(
            "doCompletePlayer", lease_command=lease_command, payload={}, cont=cont)
        if txn is None:
            return self._handoff_failure_feedback()
        if holder["r"] is not None:
            return holder["r"]
        return self._masked_pending_feedback(txn["txn_id"])

    def _masked_submit_population_votes(self, selections: dict) -> dict:
        if not self._viewer_id:
            return self._feedback(False, "Not initialized", "error")
        # SB-V03: transaction-exclusive entry check (only from ACTIVE).
        if self._seat_lifecycle != SEAT_ACTIVE or self._handoff_busy:
            return self._feedback(False, "当前无法执行本席操作", "error")
        if self._population_vote_submitting:
            return self._feedback(False, "投票正在提交，请稍候", "warning")
        self._population_vote_submitting = True
        self.populationVoteSubmittingChanged.emit()
        holder = {"r": None}

        def done(result):
            holder["r"] = result

        def _clear_busy():
            self._population_vote_submitting = False
            self.populationVoteSubmittingChanged.emit()

        def cont(txn, ok, fail_result):
            txn_id = txn["txn_id"]
            if not ok:
                _clear_busy()
                done(fail_result)
                return
            try:
                feedback = self._dispatch_owning(
                    txn, "submit_population_votes",
                    self._adapter.submit_population_votes, self._viewer_id,
                    dict(selections))
                self._committed_receipt = feedback
                _clear_busy()
                if not feedback.get("success"):
                    # SD-R02 (§1.1.R): the population AI-drain continuation masked
                    # failure (N7-R) is routed as ``continuation`` so the overlay
                    # offers ONLY the bounded continuation recovery.
                    if self._is_masked_continuation_failure(feedback):
                        self._fail_masked(FAIL_AFTER_COMMIT, txn_id,
                                          route=RECOVER_ROUTE_CONTINUATION)
                        done(self._handoff_failure_feedback())
                        return
                    self._masked_business_rejection(txn_id, feedback, done=done)
                    return
                data = feedback.get("data", {}) or {}
                awaiting = data.get("awaiting_player_id")
                self._settle_seat_after_success(
                    txn_id, next_actor_id=awaiting, done=done,
                    delivery=data.get("delivery"))
            except Exception:
                logger.exception("masked submitPopulationVotes failed")
                _clear_busy()
                self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
                done(self._handoff_failure_feedback())

        txn = self._begin_masked_seat_transition(
            "submitPopulationVotes", lease_command="submit_population_votes",
            payload=dict(selections), cont=cont)
        if txn is None:
            _clear_busy()
            return self._handoff_failure_feedback()
        if holder["r"] is not None:
            return holder["r"]
        return self._masked_pending_feedback(txn["txn_id"])

    def _masked_forum_finish(self, command_id: str, substep: str) -> dict:
        """D2 (FC-D2-03/04/05): finish ONE forum substep through the SAME masked
        seat-handoff machine the population path uses.

        Under ONE masked transaction: suspend the seat (``_begin_masked_seat_transition``
        -> ``suspend_hotseat_session``), dispatch the owning finish (record the
        seat's lawful ledger finish + drive the scheduled-AI forum sub-boundaries +
        ask the coordinator for the next actor), then settle:
          * a next HUMAN B -> ``MASKED_PENDING_HANDOFF`` (explicit 「接管」 ->
            ``commit_hotseat_principal(B)`` + fresh handle);
          * no next HUMAN  -> same-seat recovery, then the recovered seat's own
            follow-up (``open_market`` / ``resolve_forum``).
        The cursor move and the seat-authority move are therefore ALWAYS paired —
        there is NO observable window with cursor=B / principal=A, and NO stale
        viewer read (the old ``_refresh_forum_view`` after a bare cursor move is
        gone, FC-D2-04).
        """
        if not self._viewer_id:
            return {"success": False, "message": "Not initialized"}
        if self._seat_lifecycle != SEAT_ACTIVE or self._handoff_busy:
            return self._feedback(False, "当前无法执行本席操作", "error")
        holder = {"r": None}

        def done(result):
            holder["r"] = result

        def _owner_finish(_command_id, _substep):
            # The public finish must pass the ONE controlled seat authority BEFORE
            # any ledger/receipt mutation (R11-F03); under the continuation scope
            # this owning command label is the authorized dispatch.
            denied = self._authorize_public_finish(_command_id)
            if denied is not None:
                return None, denied
            _rec = self._record_forum_ledger_finish(
                self._viewer_id, _substep, f"{_command_id}:{_substep}")
            if not _rec.get("success"):
                return None, self._feedback(False, "完成未记录（请重试）", "warning")
            self._process_ai_factions_forum(_substep)
            return self._advance_forum_to_next_human(_substep), None

        def cont(txn, ok, fail_result):
            txn_id = txn["txn_id"]
            if not ok:
                done(fail_result)
                return
            try:
                outcome, rejection = self._dispatch_owning(
                    txn, command_id, _owner_finish, command_id, substep)
                if rejection is not None:
                    self._masked_business_rejection(txn_id, rejection, done=done)
                    return
                # D16 (FC-D16-03/05/07): the selection result is a TYPED three-value
                # result. Only SUBSTEP_COMPLETE may run the same-seat follow-up; a
                # BLOCKED / malformed result is a NEUTRAL post-commit failure (the
                # own-seat finish above really happened) — never a business rejection
                # and never a fabricated handoff target.
                status = outcome.get("status") if isinstance(outcome, dict) else None
                if status not in ("NEXT_HUMAN", "SUBSTEP_COMPLETE"):
                    self._last_delivery = None
                    self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
                    if isinstance(outcome, dict) and outcome.get("error"):
                        done(self._handoff_failure_feedback(
                            delivery_error=outcome["error"]))
                    else:
                        done(self._handoff_failure_feedback(
                            delivery_error={"code": "COMMIT_STATUS_UNPROVEN",
                                            "stage": "forum_select"}))
                    return
                next_actor = outcome.get("actor") if status == "NEXT_HUMAN" else None
                if next_actor and next_actor != self._viewer_id:
                    self._settle_seat_after_success(
                        txn_id, next_actor_id=next_actor, done=done)
                    return

                def _after_same_seat(result):
                    if self._seat_lifecycle != SEAT_ACTIVE:
                        done(result)
                        return
                    done(self._forum_substep_followup(substep))

                self._settle_seat_after_success(
                    txn_id, next_actor_id=self._viewer_id, done=_after_same_seat)
            except Exception:
                logger.exception("masked forum finish failed")
                self._fail_masked(FAIL_AFTER_COMMIT, txn_id)
                done(self._handoff_failure_feedback())

        txn = self._begin_masked_seat_transition(
            command_id, lease_command=command_id, payload={}, cont=cont)
        if txn is None:
            return self._handoff_failure_feedback()
        if holder["r"] is not None:
            return holder["r"]
        return self._masked_pending_feedback(txn["txn_id"])

    def _forum_substep_followup(self, substep: str) -> dict:
        """The recovered SAME seat's follow-up after a forum substep finish with NO
        next HUMAN (no cursor move): open the market once every retirement is
        finished, or settle the market (``resolve_forum``). These run OUTSIDE the
        masked continuation scope, as the (now authoritative) same seat."""
        if substep == "retirement":
            feedback = self._adapter.open_forum_market(self._viewer_id)
            if feedback.get("success"):
                self._forum_step_override = "market"
            self._refresh_forum_view()
            self._raise_feedback(feedback)
            return feedback
        feedback = self._adapter.resolve_forum()
        if feedback.get("success"):
            self._forum_result = feedback
            self._forum_step_override = "resolution"
        self._raise_feedback(feedback)
        self._refresh_snapshot()
        self._refresh_forum_view()
        return feedback

    @Slot(str)
    def logUiEvent(self, message: str):
        """QML 记录 UI 事件"""
        logger.info(f"[UI] {message}")

    # -----------------------------------------------------------------------
    # 内部刷新
    # -----------------------------------------------------------------------
    def _on_refresh(self):
        """API 操作成功后自动刷新。

        FC-712-20 (W2b): while the seat is NOT ACTIVE (busy / masked / pending /
        failure) NO public refresh runs. A masked owning command must not
        republish the old viewer's models (or reload a style map) under the
        cover; the request is deferred and satisfied by the complete private
        activation bundle, which is the only publication point of the target's
        first frame.
        """
        if self._seat_lifecycle != SEAT_ACTIVE:
            self._deferred_public_refresh = True
            logger.info("public refresh deferred: seat lifecycle=%s",
                        self._seat_lifecycle)
            return
        self._guard_enter()
        try:
            self._invalidate_global_query("refresh", keep_open=False)
        finally:
            self._guard_exit()
        self._refresh_snapshot()
        # Belt-and-suspenders: detect year advance outside normal path
        if not self._state.get_phase_result("mortality"):
            self._reset_phase_caches()
        self._refresh_mortality_view()
        self._refresh_population_view()
        self._refresh_senate_view()
        self._refresh_revenue_view()
        self._refresh_forum_view()
        self._refresh_combat_view()
        self._refresh_resolution_view()
        # Auto-settlement trigger: resolution phase, not yet resolved, not currently resolving
        if (self._selected_phase_id == "resolution"
                and not self._resolution_view.get("resolved", False)
                and not self._resolution_resolving):
            self._executeResolution()

    def _refresh_snapshot(self):
        self._snapshot = self._publish_private_read(
            "snapshot", self._adapter.get_snapshot_envelope(self._viewer_id))
        self._refresh_faction_style_map()
        new_current = self._snapshot.get("current_phase_id", "mortality")
        if not self._selected_phase_id or self._selected_phase_id != new_current:
            self._selected_phase_id = new_current
        self._selected_phase_summary = self._summary_from_phase(
            self._phase_by_id(self._selected_phase_id)
        )
        self.snapshotChanged.emit()
        self.phaseChanged.emit()
        self.currentPlayerChanged.emit()
        self.phaseStepsChanged.emit()

    def _refresh_population_view(self):
        self._population_view = self._publish_private_read(
            "population", self._adapter.get_population_view_envelope(self._viewer_id))
        self.populationViewChanged.emit()
        self.phaseStepsChanged.emit()

    def _refresh_mortality_view(self):
        self._mortality_view = self._publish_private_read(
            "mortality", self._adapter.get_mortality_view_envelope(self._viewer_id))
        self.mortalityViewChanged.emit()
        self.phaseStepsChanged.emit()

    def _refresh_senate_view(self):
        # R01 (W2b): the senate projection is consumed through the SAME private
        # last_good/stale pipeline as every other REQUIRED resource. The D13
        # observation seam is PRESERVED (``adapter.get_senate_view``); the
        # production adapter now returns the RAW envelope there, so a DENIED /
        # malformed read is never mistaken for an authoritative EMPTY. A bare
        # projection installed on that seam (D13 witness style) is still honoured
        # as a successful read.
        raw = self._senate_read()
        view = self._publish_private_read(
            "senate", self._normalise_read_seam(raw))
        self._senate_view = view
        # D13：仅 ACTIVE 且新 DTO 有效时同步（masked/denied/空 refresh 保锁）；
        # 先改状态，后通知。成功 masked API 自动刷新返回空 DTO 不得清锁。
        if self._seat_lifecycle == SEAT_ACTIVE:
            self._sync_ai_proposer_guard(view)
        self.senateViewChanged.emit()
        self.phaseStepsChanged.emit()

    def _senate_read(self) -> Any:
        """R01 — read the senate projection with the envelope preserved.

        The production path uses ``get_senate_view_envelope`` (DENIED/malformed
        never collapse to ``{}``). The D13 OBSERVATION SEAM is preserved: when a
        caller installs its own ``adapter.get_senate_view`` (an instance-level
        override, exactly how the frozen D13 witnesses inject a controlled
        projection), that bare projection is authoritative-by-contract and is
        normalised to a success envelope here.
        """
        if "get_senate_view" in vars(self._adapter):
            return self._normalise_read_seam(
                self._adapter.get_senate_view(self._viewer_id))
        return self._adapter.get_senate_view_envelope(self._viewer_id)

    @staticmethod
    def _normalise_read_seam(raw: Any) -> Dict[str, Any]:
        """R01 — normalise one value coming from a legacy read seam.

        A mapping WITHOUT a ``success`` key is a bare projection (the historical
        ``get_*_view``/D13 seam contract) and is authoritative by contract; every
        other value is handed to ``_read_outcome`` unchanged, so a DENIED, a
        malformed envelope or a legal ``success/{}`` keep their exact meaning.
        """
        if isinstance(raw, dict) and "success" not in raw:
            return {"success": True, "message": "bare projection",
                    "data": raw, "errors": []}
        return raw

    def _refresh_revenue_view(self):
        self._revenue_view = self._publish_private_read(
            "revenue", self._adapter.get_revenue_view_envelope(self._viewer_id))
        self.revenueViewChanged.emit()
        self.phaseStepsChanged.emit()

    def _refresh_forum_view(self):
        self._forum_view = self._publish_private_read(
            "forum", self._adapter.get_forum_view_envelope(self._viewer_id))
        if self._forum_step_override and self._forum_view.get("resolved"):
            self._forum_step_override = "resolution"
        self.forumViewChanged.emit()
        self.phaseStepsChanged.emit()

    def _refresh_combat_view(self):
        self._combat_view = self._publish_private_read(
            "combat", self._adapter.get_combat_view_envelope(self._viewer_id))
        self.combatViewChanged.emit()
        self.phaseStepsChanged.emit()

    def _refresh_resolution_view(self):
        self._resolution_view = self._publish_private_read(
            "resolution", self._adapter.get_resolution_view_envelope(self._viewer_id))
        self.resolutionViewChanged.emit()

    def _executeResolution(self):
        """自动结算：进入 resolution 阶段时触发，防重复。"""
        if self._resolution_resolving:
            logger.info("Resolution already resolving, skipping")
            return
        if not self._viewer_id:
            logger.warning("Cannot execute resolution: no viewer_id")
            return

        # D12 / W1（A5）：仅在座位 ACTIVE 且 handle 未 revoked 时自动结算。
        # masked-refresh 瞬间 handle 已被 suspend（revoked=True）；此时**不调用**
        # API，保持现状等待下一次 ACTIVE refresh（不改 masked / staging / reveal）。
        if self._seat_lifecycle != SEAT_ACTIVE:
            logger.info("Resolution deferred: seat lifecycle=%s",
                        self._seat_lifecycle)
            return
        if session_access.is_hotseat_registered(self._state):
            ctx = session_access.current_caller_context(self._state)
            if ctx is None or ctx.revoked:
                logger.info("Resolution deferred: seat handle not active")
                return

        self._resolution_resolving = True
        self.resolutionViewChanged.emit()
        self.phaseChanged.emit()  # 同步通知 advance 按钮绑定
        try:
            feedback = self._adapter.execute_phase("resolution", self._viewer_id)
            if feedback.get("success"):
                # 结算成功：刷新快照和 resolution view
                self._refresh_snapshot()
                self._refresh_resolution_view()
                self.phaseChanged.emit()
            else:
                logger.warning(f"Resolution execution failed: {feedback.get('message')}")
                self._refresh_resolution_view()
            self._raise_feedback(feedback)
        finally:
            self._resolution_resolving = False
            self.resolutionViewChanged.emit()
            self.phaseChanged.emit()  # 同步通知 advance 按钮绑定

    def _senate_friendly_feedback_copy(self, items) -> str:
        """R8（SA §5.3）：结构化 error_items → 人话摘要（去 machine code / field token）。

        以 code 为内部查表键；未知/legacy code → 安全通用文案（原消息只留证据，不直出）。
        """
        parts = []
        for item in items or []:
            code = str((item or {}).get("code") or "")
            msg = self._SENATE_FRIENDLY_MESSAGES.get(code)
            if msg is None:
                msg = "配置未能提交，请检查标记字段后重试"
            elif code == "LEGION_POOL_EXCEEDED":
                details = (item or {}).get("details") or {}
                if details.get("requested_total") is not None and details.get("available_total") is not None:
                    msg += "（请求 %s / 可用 %s" % (details.get("requested_total"),
                                                   details.get("available_total"))
                    if details.get("reduce_by") is not None:
                        msg += " → 请减少 %s" % details.get("reduce_by")
                    msg += "）"
            msg += "。"
            if msg not in parts:
                parts.append(msg)
        return "；".join(parts) if parts else "配置未能提交，请检查标记字段后重试。"

    def _raise_senate_feedback(self, feedback: dict):
        """R8（SA §5.3）：Senate 调用点**只读展示副本**——人话摘要经 `feedbackRaised` 发出。

        **不改** 原 `feedback` 返回、错误对象、日志与其它阶段原行为：失败且有结构化
        `error_items` → code→人话；否则（Store 本地 guard 等）保留已人话的 `feedback_message`。
        """
        if feedback.get("success"):
            self._raise_feedback(feedback)
            return
        items = feedback.get("error_items")
        if items:
            fmsg = self._senate_friendly_feedback_copy(items)
        else:
            fmsg = str(feedback.get("feedback_message") or feedback.get("message") or "")
        if fmsg:
            self.feedbackRaised.emit(feedback.get("feedback_type", "error"), fmsg)

    def _raise_feedback(self, feedback: dict):
        ftype = feedback.get("feedback_type", "info")
        fmsg = feedback.get("feedback_message", "")
        if fmsg:
            self.feedbackRaised.emit(ftype, fmsg)

    def _phase_by_id(self, phase_id: str) -> Dict[str, Any]:
        for phase in self.phaseNavigation:
            if phase.get("id") == phase_id:
                return phase
        return {}

    def _summary_from_phase(self, phase: Dict[str, Any]) -> Dict[str, Any]:
        if not phase:
            return self._snapshot.get("selected_phase_summary", {})
        implemented = phase.get("implemented", False)
        return {
            "id": phase.get("id", ""),
            "name": phase.get("name", ""),
            "subtitle": phase.get("subtitle", ""),
            "description": phase.get("description", ""),
            "implemented": implemented,
            "interaction_mode": phase.get("interaction_mode", "interactive" if implemented else "placeholder"),
            "actionable": phase.get("actionable", False),
            "handoff_task": phase.get("handoff_task", ""),
            "name_key": phase.get("name_key", ""),
            "subtitle_key": phase.get("subtitle_key", ""),
            "description_key": phase.get("description_key", ""),
            "status_key": phase.get("status_key", ""),
            "status_text": gui_text("phase.status.actionable") if phase.get("actionable", False) else (
                gui_text("phase.status.readonly") if phase.get("interaction_mode") == "readonly" else (
                    gui_text("phase.status.ready") if implemented else gui_text("phase.status.placeholder")
                )
            ),
            "disabled_reason": phase.get("disabled_reason") or gui_text(
                "phase.disabled.placeholder",
                handoff_task=phase.get("handoff_task", "后续任务"),
            ),
        }

    def _feedback(
        self,
        success: bool,
        message: str,
        feedback_type: str,
        data: Any = None,
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "message": message,
            "data": data,
            "errors": [] if success else [message],
            "feedback_type": feedback_type,
            "feedback_message": message,
        }
