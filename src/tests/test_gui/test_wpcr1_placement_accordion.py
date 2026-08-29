# src/tests/test_gui/test_wpcr1_placement_accordion.py
"""WP-C-R1 AU-14 NT-6: QML 对象树结构断言（016 placement + 014/015 控件值域 + accordion 时序）。

采用 QGuiApplication offscreen + QQmlComponent 加载 ForumStage.qml / SenateStage.qml，
注入 mock sessionStore，读取 QML 对象树断言（视觉子项遍历 childItems() 可穿透 Repeater 项）：

- T016-1: 顶部公示容器 objectName == "announceArea"
- T016-2: war-threat 渲染位于 announceArea（非 Market）
- T016-3: Market 无「⚔️ 战争威胁」SectionTitle（已移除）
- T016-5: 无 THREAT → 顶部 neutral 空态（不声称战争）
- T016-6: 顶部不残留硬编码「第一次布匿战争进行中」战争状态
- T016-10: 「西西里包税合同待竞标」静态文案保留（归 010/WP-F，R1 不越界）
- T015-3/13: ComboBox model == legion_options（[1..可用池]），default 选中 4
- T015-11: 无个体军团 ID 选择器（仅数量控件）
- T014-3: Slider from/to/stepSize/value == budget_range
- T-ACC-1/2/3 + T014-10: accordion 展开状态与选中集一致、控件可见、onSenateViewChanged 不丢展开
- T-R2-01~07: 真实 get_senate_view 生产链（root 级 legion_options/budget_range 契约 + SessionStore parity + QML 渲染 + round-trip）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import QObject, QUrl, Signal, Property, Slot, QMetaObject, Q_ARG, Q_RETURN_ARG, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem
import shiboken6
from unittest.mock import MagicMock

from src.core.game_state import GameState
from src.core.entities.contract import ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem


def _qitem(obj):
    """将 QObject 包装重包装为 QQuickItem（childItems/parentItem 遍历 Repeater 项需要）。"""
    if obj is None:
        return None
    try:
        ptr = shiboken6.Shiboken.getCppPointer(obj)[0]
        return shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        return None


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _load_qml(qml_file, store):
    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)

    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    # SenateStage 引用 theme 上下文属性（ForumStage 不用，注入无害）
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    ctx.setContextProperty("theme", theme)

    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "stages", qml_file)))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, f"{qml_file} loaded with no root object"
    engine._test_refs = (store, theme)
    return engine, roots[0]


def _normalize(value):
    """将 QML var 属性值归一化为 Python list。"""
    if value is None:
        return []
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    if isinstance(value, str):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _all_items(root):
    """深度优先遍历 QQuickItem 视觉子项（childItems 可穿透 Repeater 生成的项，findChildren(QObject) 不行）。"""
    pending = [_qitem(root)]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        pending.extend(item.childItems())


def _texts(root):
    return [str(i.property("text")) for i in _all_items(root) if isinstance(i.property("text"), str)]


def _is_descendant(child, ancestor):
    node = _qitem(child)
    anc = _qitem(ancestor)
    while node is not None:
        if node is anc:
            return True
        node = node.parentItem()
    return False


# ---------------------------------------------------------------------------
# ForumStage mock store
# ---------------------------------------------------------------------------

class _MockForumStore(QObject):
    forumViewChanged = Signal()

    def __init__(self, war_threats=None, parent=None):
        super().__init__(parent)
        self._war_threats = war_threats or []

    @Property(str, notify=forumViewChanged)
    def forumCurrentStep(self):
        return "market"

    @Property(bool, notify=forumViewChanged)
    def forumResolved(self):
        return False

    @Property(list, notify=forumViewChanged)
    def forumAvailableFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumMyFigures(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumPendingContracts(self):
        return []

    @Property(int, notify=forumViewChanged)
    def forumLandQuota(self):
        return 0

    @Property(list, notify=forumViewChanged)
    def forumTriumphWars(self):
        return []

    @Property(list, notify=forumViewChanged)
    def forumWarThreats(self):
        return self._war_threats

    @Property(dict, notify=forumViewChanged)
    def forumResult(self):
        return {}

    @Property(dict, notify=forumViewChanged)
    def forumView(self):
        return {}

    @Property(bool, notify=forumViewChanged)
    def canExecuteForum(self):
        return False

    @Property(bool, notify=forumViewChanged)
    def canAdvanceForum(self):
        return False

    @Slot("QVariant", result=dict)
    def doRecruitFigure(self, figure_id, amount):
        return {"success": False, "message": "no"}

    @Slot("QVariant", "QVariant", result=dict)
    def doPlaceBid(self, contract_id, amount):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doBuyLand(self, figure_id, amount):
        return {"success": False, "message": "no"}

    @Slot(result=dict)
    def doResolveForum(self):
        return {"success": False, "message": "no"}

    @Slot(result=dict)
    def doCompleteForumStep(self):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doRetireFigure(self, figure_id):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doVoteTriumph(self, war_id, approved):
        return {"success": False, "message": "no"}


_THREATS = [
    {"war_id": "pyrrhic_war", "name": "皮洛士战争", "threat_level": 2, "naval_required": False},
    {"war_id": "first_punic_war", "name": "第一次布匿战争", "threat_level": 3, "naval_required": True},
]


def test_forum_announce_area_object_name():
    """T016-1: 顶部公示容器 objectName == announceArea。"""
    store = _MockForumStore(_THREATS)
    _engine, root = _load_qml("ForumStage.qml", store)
    area = root.findChild(QObject, "announceArea")
    assert area is not None, "announceArea not found"
    assert root.objectName() == "forumStage"


def test_forum_war_threat_rendered_in_announce_area():
    """T016-2: war-threat 渲染位于 announceArea 内（非 Market）；内容来自 DTO 不重算。"""
    store = _MockForumStore(_THREATS)
    _engine, root = _load_qml("ForumStage.qml", store)
    area = root.findChild(QObject, "announceArea")
    assert area is not None
    block = root.findChild(QObject, "announceWarThreats")
    assert block is not None, "announceWarThreats block not found"
    # 块在 announceArea 子树内
    assert _is_descendant(block, area), "war-threat block must live inside announceArea"
    # 有威胁 → 块可见，空态不可见
    assert block.property("visible") is True
    empty = root.findChild(QObject, "announceWarThreatsEmpty")
    assert empty is not None
    assert empty.property("visible") is False
    # delegate Text 渲染 DTO 字段（name/threat_level/naval_required 直读，不重算）
    joined = " ".join(_texts(root))
    assert "皮洛士战争 · 威胁等级 2 · 陆战" in joined
    assert "第一次布匿战争 · 威胁等级 3 · 需海军" in joined


def test_forum_market_war_threat_section_removed():
    """T016-3: Market 无「⚔️ 战争威胁」SectionTitle（已移除）。"""
    store = _MockForumStore(_THREATS)
    _engine, root = _load_qml("ForumStage.qml", store)
    texts = _texts(root)
    assert not any(t == "⚔️ 战争威胁" for t in texts)
    assert not any("战争威胁" in t and "⚔" in t for t in texts), "Market war-threat SectionTitle must be removed"


def test_forum_war_threat_empty_state():
    """T016-5: 无 THREAT → 顶部 neutral 空态（不声称战争存在）。"""
    store = _MockForumStore([])
    _engine, root = _load_qml("ForumStage.qml", store)
    block = root.findChild(QObject, "announceWarThreats")
    empty = root.findChild(QObject, "announceWarThreatsEmpty")
    assert block is not None and empty is not None
    assert block.property("visible") is False
    assert empty.property("visible") is True
    assert "本回合无战争威胁" in str(empty.property("text"))


def test_forum_no_stale_hardcoded_war_state():
    """T016-6 + T016-10 + WP-F 010-02: 顶部不残留「第一次布匿战争进行中」；
    静态伪运行时文案「西西里包税合同待竞标」已删除（S3-2，R-10 只删不换）；「广场阶段开始。」保留。"""
    store = _MockForumStore([])
    _engine, root = _load_qml("ForumStage.qml", store)
    joined = " ".join(_texts(root))
    assert "第一次布匿战争进行中" not in joined, "hard-coded war-state must not remain in top area"
    assert "西西里包税合同待竞标" not in joined, "WP-F 010-02: static 西西里 contract copy removed (S3-2, R-10)"
    assert "广场阶段开始。" in joined, "WP-F 010-02: generic forum-phase lead-in retained"


# ---------------------------------------------------------------------------
# SenateStage mock store
# ---------------------------------------------------------------------------

class _MockSenateStore(QObject):
    senateViewChanged = Signal()

    def __init__(self, options, current_step="proposal", can_create=None, parent=None):
        super().__init__(parent)
        self._options = options
        self._current_step = current_step
        self._can_create = can_create  # AU-R1-03a：None = 沿用 current_step 推导（既有测试零改动）
        self._submitted = []
        self.submit_calls = 0
        self.last_proposals = None

    @Property(list, notify=senateViewChanged)
    def senateProposalOptions(self):
        return self._options

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self):
        return self._current_step

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self):
        return self._submitted

    @Property(list, notify=senateViewChanged)
    def senateTakeoverOptions(self):
        return []

    @Property(bool, notify=senateViewChanged)
    def canTakeoverSenateWar(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self):
        if self._can_create is not None:
            return self._can_create
        return self._current_step == "proposal"

    @Property(bool, notify=senateViewChanged)
    def canSelectSenateProposal(self):
        return self._current_step == "proposal"

    @Property(bool, notify=senateViewChanged)
    def canTriggerAIProposer(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVote(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canManuallySelectSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canAdvanceSenate(self):
        return False

    @Property(dict, notify=senateViewChanged)
    def senatePresidingOfficer(self):
        return {}

    @Property(list, notify=senateViewChanged)
    def senateSeatShares(self):
        return []

    @Property(dict, notify=senateViewChanged)
    def senateResult(self):
        return {}

    @Property(dict, notify=senateViewChanged)
    def senatePublicAnnouncement(self):
        return {}

    @Property(dict, notify=senateViewChanged)
    def governorAppointments(self):
        return {}

    @staticmethod
    def _variant_to_python(value):
        """QVariant→Python 转换（仿 session_store._variant_to_python，F-6 捕获 payload）。"""
        if hasattr(value, "toVariant"):
            return value.toVariant()
        if hasattr(value, "toPython"):
            return value.toPython()
        return value

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals):
        self.submit_calls += 1
        self.last_proposals = self._variant_to_python(proposals)
        return {"success": True, "message": "ok"}

    @Slot(result=dict)
    def doSubmitSenateVotes(self):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doSubmitSenateVetoes(self, proposal_ids):
        return {"success": False, "message": "no"}

    @Slot(str, result=dict)
    def doTakeoverWar(self, war_id):
        return {"success": True, "message": "ok"}


def _build_real_senate_state():
    """真实链 GameState 配方（DA-Plan §5.1）：THREAT war（w1）+ PENDING PUBLIC_WORKS 合同（base_cost=100）+ 权威值域 config。

    - senate_budget（ODR-ED-01）：PUBLIC_WORKS base=100 → budget_range {min:1, max:150, step:1, default:100}
    - senate_war_legions（ODR-ED-02）：MilitarySystem pool=25 → legion_options {min:1, max:25, default:4, allowed:[1..25]}
    - _executed_phases 置 {mortality,revenue,forum,population} → _infer_current_phase_id == "senate"
    """
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)
    consul = Figure(id=1, name="执政官", faction_id="optimates", age=40)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    state.add_member(consul)
    faction.member_ids.append(1)
    state._players = {"player1": MagicMock(player_id="player1", faction_id="optimates", player_type="human")}
    state._current_player_id = "player1"
    state.config.economic_rules.senate_budget = {
        "public_works_min": 1, "public_works_max_ratio": 1.5,
        "tax_farming_min_ratio": 0.75, "tax_farming_max_ratio": 2.0, "step": 1,
    }
    state.config.economic_rules.senate_war_legions = {"default": 4, "min": 1, "cap_mode": "available_pool"}
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    war = War(id="w1", name="皮洛士战争", war_type=WarType.FOREIGN, strength=5, naval_required=False)
    war.status = WarStatus.THREAT
    state.get_war_system()._threats.append(war)
    contract = state.create_contract(ContractType.PUBLIC_WORKS, province_id=1, base_cost=100, current_turn=1)
    contract.status = ContractStatus.PENDING
    state._executed_phases = {"mortality", "revenue", "forum", "population"}
    return state


def _real_senate_options():
    """真实 producer 派生（F-1）：senate_api.get_senate_view(state,"player1")["data"]["proposal_options"]。"""
    from src.api import senate_api
    state = _build_real_senate_state()
    view = senate_api.get_senate_view(state, "player1")
    assert view["success"], view.get("message")
    options = view["data"]["proposal_options"]
    assert options, "proposal_options must be non-empty"
    return options


def _options_with_ranges():
    """WP-C-R1 遗留 fixture 名：改为真实 producer 派生（结构性关闭手工 shape escape，DA-Plan §4）。"""
    return _real_senate_options()


def _key_set(root):
    return {str(k) for k in _normalize(root.property("selectedProposalKeys"))}


def test_senate_accordion_expansion_and_controls():
    """T-ACC-1/2/3 + T014-10 + F-3: 展开状态与选中集一致；war/budget 控件可见可用；onSenateViewChanged 不丢展开。"""
    options = _options_with_ranges()  # 真实 producer 派生（F-1）
    store = _MockSenateStore(options)
    _engine, root = _load_qml("SenateStage.qml", store)
    app = _get_app()

    war_options = [o for o in options if o["type"] == "war"]
    budget_options = [o for o in options if o["type"] == "budget"]
    assert len(war_options) == 1, "recipe must produce exactly 1 war option"
    assert len(budget_options) == 1, "recipe must produce exactly 1 budget option"
    lo = war_options[0]["legion_options"]
    br = budget_options[0]["budget_range"]

    # F-3 parity 增补：root 级元数据存在；params 无重复 range 元数据（producer 契约）
    assert "legion_options" in war_options[0] and "legion_options" not in war_options[0]["params"]
    assert "budget_range" in budget_options[0] and "budget_range" not in budget_options[0]["params"]

    # T-ACC-2: 展开状态 == 选中集（默认 war/budget，真实 producer 派生；land 不在默认选中集）
    keys = _key_set(root)
    assert keys == {o["key"] for o in options if o["type"] in ("war", "peace", "budget")}
    expanded = {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert expanded == keys

    # T-ACC-1/T014-10: 控件展开可见（仅有权值域者 enabled）
    combos = [c for c in _all_items(root) if "ComboBox" in c.metaObject().className() and c.property("enabled") is True]
    assert len(combos) == 1, f"expected exactly 1 enabled legion ComboBox, got {len(combos)} (T015-11)"
    combo = combos[0]
    assert combo.isVisible() is True
    # T015-13: default 选中 = legion_options.default（真实 producer，default=4 ∈ 池）
    assert str(combo.property("currentText")) == str(lo["default"])
    # T015-3: ComboBox model == legion_options.allowed（真实 producer 派生，pool=25）
    assert _normalize(combo.property("model")) == lo["allowed"]

    sliders = [s for s in _all_items(root)
               if "Slider" in s.metaObject().className()
               and "Groove" not in s.metaObject().className()
               and "Handle" not in s.metaObject().className()
               and s.property("enabled") is True
               and s.isVisible()]
    assert len(sliders) == 1, f"expected exactly 1 enabled budget Slider, got {len(sliders)}"
    slider = sliders[0]
    # T014-3: Slider from/to/stepSize/value == budget_range（真实 producer 派生，非硬编码）
    assert slider.property("from") == br["min"]
    assert slider.property("to") == br["max"]
    assert slider.property("stepSize") == br["step"]
    assert slider.property("value") == br["default"]

    # T-ACC-3: onSenateViewChanged 触发后不丢展开状态（选中集非空 → 仅重跑 expandCheckedBills）
    store.senateViewChanged.emit()
    app.processEvents()
    expanded2 = {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert expanded2 == keys
    assert combo.isVisible() is True

    # 折叠 → 控件不可见；再展开 → 恢复（accordion 交互保持）
    QMetaObject.invokeMethod(root, "toggleBillExpanded", Qt.DirectConnection, Q_ARG("QVariant", "war:w1"))
    app.processEvents()
    assert "war:w1" not in {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert combo.isVisible() is False
    QMetaObject.invokeMethod(root, "toggleBillExpanded", Qt.DirectConnection, Q_ARG("QVariant", "war:w1"))
    app.processEvents()
    assert "war:w1" in {str(k) for k in _normalize(root.property("expandedBillKeys"))}
    assert combo.isVisible() is True


def test_senate_no_individual_legion_selector():
    """T015-11 + F-4: 无个体军团 ID 选择器（仅数量 ComboBox；model == legion_options.allowed）。"""
    options = _options_with_ranges()
    store = _MockSenateStore(options)
    _engine, root = _load_qml("SenateStage.qml", store)
    combos = [c for c in _all_items(root) if "ComboBox" in c.metaObject().className() and c.property("enabled") is True]
    assert len(combos) == 1, "only one enabled legion-count ComboBox is allowed"
    lo = [o for o in options if o["type"] == "war"][0]["legion_options"]
    model = _normalize(combos[0].property("model"))
    assert model == lo["allowed"], "model must be legion_options.allowed (count range [1..pool]), not individual legion IDs"


def test_senate_unauthorised_viewer_controls_gated():
    """AU-R1-03a（AC-R1-03）：非执政官 viewer → 三角 MouseArea/军团 ComboBox/预算 Slider 全禁用。"""
    options = _options_with_ranges()  # 真实 producer 形状
    store = _MockSenateStore(options, can_create=False)
    _engine, root = _load_qml("SenateStage.qml", store)

    # 三角 MouseArea（width==18，billCard 表头）——非执政官禁用
    triangles = [i for i in _all_items(root)
                 if "MouseArea" in i.metaObject().className() and int(i.property("width")) == 18]
    assert len(triangles) >= 2, f"expected >=2 triangle MouseAreas, got {len(triangles)}"
    for tri in triangles:
        assert tri.property("enabled") is False, "non-consul viewer: disclosure triangle must be disabled"

    # 军团 ComboBox——非执政官禁用（原 enabled 仅值域存在判定）
    combos = [c for c in _all_items(root) if "ComboBox" in c.metaObject().className() and c.isVisible()]
    assert len(combos) == 1
    assert combos[0].property("enabled") is False, "non-consul viewer: legion ComboBox must be disabled"

    # 预算 Slider——非执政官禁用
    sliders = [s for s in _all_items(root)
               if "Slider" in s.metaObject().className()
               and "Groove" not in s.metaObject().className()
               and "Handle" not in s.metaObject().className()
               and s.isVisible()]
    assert len(sliders) == 1
    assert sliders[0].property("enabled") is False, "non-consul viewer: budget Slider must be disabled"


def test_senate_checkbox_drives_expansion():
    """AU-R1-04a（AC-R1-04）：checkbox 驱动展开/折叠——勾选 land:sale 自动展开、取消勾选折叠。"""
    options = _options_with_ranges()
    store = _MockSenateStore(options, can_create=True)
    _engine, root = _load_qml("SenateStage.qml", store)
    app = _get_app()

    def keys(prop):
        return {str(k) for k in _normalize(root.property(prop))}

    assert "land:sale" not in keys("expandedBillKeys")
    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", True))
    app.processEvents()
    assert "land:sale" in keys("expandedBillKeys"), "checked proposal must auto-expand"

    QMetaObject.invokeMethod(root, "setProposalSelected", Qt.DirectConnection,
                             Q_ARG("QVariant", "land:sale"), Q_ARG("QVariant", False))
    app.processEvents()
    assert "land:sale" not in keys("expandedBillKeys"), "unchecked proposal must collapse (G7 #8)"
    assert keys("expandedBillKeys") == keys("selectedProposalKeys"), "expansion must mirror selection"


# ---------------------------------------------------------------------------
# T-R2-01~07: 真实生产链测试（DA-Plan §5.2；AC-014-R2 / AC-015-R2）
# ---------------------------------------------------------------------------

def test_r2_01_producer_budget_shape():
    """T-R2-01 (AC-014-R2-1): 真实 get_senate_view：budget option root 含 budget_range dict；params 仅提交值。"""
    options = _real_senate_options()
    budget_options = [o for o in options if o["type"] == "budget"]
    assert len(budget_options) == 1
    bo = budget_options[0]
    assert bo["budget_range"] == {"min": 1, "max": 150, "step": 1, "default": 100}
    assert set(bo["params"].keys()) == {"contract_id", "modified_budget"}, "params 不得重复 range 元数据"
    assert "budget_range" not in bo["params"]


def test_r2_02_producer_war_shape():
    """T-R2-02 (AC-015-R2-1): 真实 get_senate_view：war option root 含 legion_options dict（含 allowed）；params 仅提交值。"""
    options = _real_senate_options()
    war_options = [o for o in options if o["type"] == "war"]
    assert len(war_options) == 1
    wo = war_options[0]
    lo = wo["legion_options"]
    assert isinstance(lo, dict), "legion_options 必须是 dict（含 allowed list）"
    assert lo["min"] == 1
    assert lo["default"] == 4
    assert lo["max"] == 25
    assert lo["allowed"] == list(range(1, 26))
    assert set(wo["params"].keys()) == {"war_id", "legions"}, "params 不得重复 range 元数据"
    assert "legion_options" not in wo["params"]


def test_r2_03_session_store_parity():
    """T-R2-03 (AC-014-R2-2/AC-015-R2-2): 真实 SessionStore pass-through — senateProposalOptions 逐项 == producer 输出。"""
    from src.ui.gui.session_store import GuiSessionStore
    state = _build_real_senate_state()
    options = _real_senate_options()
    store = GuiSessionStore(state)
    store.initialize("player1")
    passed = store.senateProposalOptions
    assert len(passed) == len(options)
    for prod, via in zip(options, passed):
        assert via["key"] == prod["key"]
        assert via["type"] == prod["type"]
        assert via["params"] == prod["params"], "params 嵌套不得被重排/增删"
        if prod.get("budget_range") is not None:
            assert via["budget_range"] == prod["budget_range"], "budget_range 必须仍在 root 且值一致"
        if prod.get("legion_options") is not None:
            assert via["legion_options"] == prod["legion_options"], "legion_options 必须仍在 root 且值一致"


def test_r2_04_slider_real_shape():
    """T-R2-04 (AC-014-R2-3): 真实 shape 加载 QML：budget Slider visible + enabled；from/to/stepSize/value == budget_range。"""
    options = _real_senate_options()
    store = _MockSenateStore(options)
    _engine, root = _load_qml("SenateStage.qml", store)
    br = [o for o in options if o["type"] == "budget"][0]["budget_range"]
    sliders = [s for s in _all_items(root)
               if "Slider" in s.metaObject().className()
               and "Groove" not in s.metaObject().className()
               and "Handle" not in s.metaObject().className()
               and s.isVisible()]
    assert len(sliders) == 1
    slider = sliders[0]
    assert slider.property("visible") is True
    assert slider.property("enabled") is True
    assert slider.property("from") == br["min"]
    assert slider.property("to") == br["max"]
    assert slider.property("stepSize") == br["step"]
    assert slider.property("value") == br["default"]


def test_r2_05_combo_real_shape():
    """T-R2-05 (AC-015-R2-3/4): 真实 shape 加载 QML：war ComboBox visible + enabled；model == legion_options.allowed；currentIndex 映射 params.legions。"""
    options = _real_senate_options()
    store = _MockSenateStore(options)
    _engine, root = _load_qml("SenateStage.qml", store)
    lo = [o for o in options if o["type"] == "war"][0]["legion_options"]
    combos = [c for c in _all_items(root) if "ComboBox" in c.metaObject().className() and c.isVisible()]
    assert len(combos) == 1
    combo = combos[0]
    assert combo.property("visible") is True
    assert combo.property("enabled") is True
    assert _normalize(combo.property("model")) == lo["allowed"]
    assert str(combo.property("currentText")) == str(lo["default"])


def _click_submit(engine, root):
    """在 QML 引擎内执行生产提交 JS：sessionStore.doSubmitSenateProposals(root.selectedProposals())（按钮 onClicked 同源）。"""
    from PySide6.QtQml import QQmlExpression
    ctx = engine.rootContext()
    ctx.setContextProperty("_r2root", root)
    expr = QQmlExpression(ctx, None, "sessionStore.doSubmitSenateProposals(_r2root.selectedProposals())")
    result = expr.evaluate()
    assert not expr.hasError(), expr.error()
    return result


def test_r2_06_budget_round_trip():
    """T-R2-06 (AC-014-R2-4, D-6 已修复): Slider 改值 120 → setBillParam → 生产提交 JS（捕获）→ 真实链提交成功。

    D-6 修复（2026-08-22 Owner 方案 A：谓词 int 容忍）：_populate_proposal 接受 int 或整数值 float
    （is_integer() 判据）。QML JS number（Math.round）跨槽边界仍产生 Python float（120.0），现视为合法；
    非整数值（120.5）仍拒收（test_political_system.py T014-7 负向矩阵保持，未修订）。
    本测试改为真实链成功路径断言：feedback["success"] 为真 + payload modified_budget == 120 + contract_id 不变。
    """
    from src.ui.gui.api_adapter import GuiApiAdapter
    options = _real_senate_options()
    store = _MockSenateStore(options)
    _engine, root = _load_qml("SenateStage.qml", store)
    app = _get_app()
    budget_options = [o for o in options if o["type"] == "budget"]
    br = budget_options[0]["budget_range"]
    assert br["min"] <= 120 <= br["max"]
    sliders = [s for s in _all_items(root)
               if "Slider" in s.metaObject().className()
               and "Groove" not in s.metaObject().className()
               and "Handle" not in s.metaObject().className()
               and s.isVisible()]
    assert len(sliders) == 1
    sliders[0].setProperty("value", 120)
    app.processEvents()
    _click_submit(_engine, root)
    captured = store.last_proposals
    assert captured is not None, "mock store must capture submitted payload"
    budget_row = [r for r in captured if r.get("type") == "budget"][0]
    modified = budget_row["params"]["modified_budget"]
    assert modified == 120, modified
    # D-6 边界现状：QML JS number（Math.round）跨槽边界仍为 Python float（120.0）——已获谓词 int 容忍
    assert float(modified).is_integer(), f"unexpected modified={modified!r}"
    # 真实链：api_adapter → propose_many → _populate_proposal 权威谓词（int 容忍后成功路径）
    state = _build_real_senate_state()
    adapter = GuiApiAdapter(state)
    feedback = adapter.submit_senate_proposals("player1", captured)
    assert feedback["success"], feedback
    proposals = state.get_senate_proposals()
    by_type = {p["type"]: p for p in proposals}
    assert by_type["budget"]["modified_budget"] == 120
    assert by_type["budget"]["contract_id"] == budget_options[0]["params"]["contract_id"]


def test_r2_07_legion_round_trip():
    """T-R2-07 (AC-015-R2-5): ComboBox 选 N=5 → setBillParam（与 onActivated 同源 JS）→ 生产提交 JS → payload legions == 5；war_id 不变。"""
    from src.ui.gui.api_adapter import GuiApiAdapter
    options = _real_senate_options()
    store = _MockSenateStore(options)
    _engine, root = _load_qml("SenateStage.qml", store)
    app = _get_app()
    war_options = [o for o in options if o["type"] == "war"]
    lo = war_options[0]["legion_options"]
    assert 5 in lo["allowed"]
    QMetaObject.invokeMethod(root, "setBillParam", Qt.DirectConnection,
                             Q_ARG("QVariant", "war:w1"), Q_ARG("QVariant", "legions"), Q_ARG("QVariant", 5))
    app.processEvents()
    _click_submit(_engine, root)
    captured = store.last_proposals
    assert captured is not None
    war_row = [r for r in captured if r.get("type") == "war"][0]
    assert war_row["params"]["legions"] == 5
    assert war_row["params"]["war_id"] == "w1"
    state = _build_real_senate_state()
    adapter = GuiApiAdapter(state)
    feedback = adapter.submit_senate_proposals("player1", captured)
    assert feedback["success"], feedback
    proposals = state.get_senate_proposals()
    by_type = {p["type"]: p for p in proposals}
    assert by_type["war"]["legions"] == 5
    assert by_type["war"]["war_id"] == "w1"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
