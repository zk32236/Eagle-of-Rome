# src/tests/test_gui/test_wpj_groupc_render_evidence.py
"""WP-J Group C — RENDER_AUTOMATED 截图 + 几何证据（route=DIRECT_PRODUCTION）。

真实生产链：`session_api.create_gui_prototype_session` → 真实 `GuiSessionStore` →
真实 `Main.qml` 离屏渲染（QT_QPA_PLATFORM=offscreen）→ `window.grabWindow()` → PNG。

- Group-C-1（J-AC-05a）：候选信息表只渲染 featured + 压缩 + 无内嵌滚动；子环节区增益（1280×720 及更大）。
- Group-C-2（J-AC-05b）：nonWar 法案卡长文本 wrap 完整可见 + 卡高内容驱动（1280×720 及更大）。
- WP-J Group C G7-Delta（delta v1.4 / FC-C22/C23）：②「2 元老院表决」行 指示器↔身份文本间距
  = 与 ③ 一致；③ 否决行勾选态 = 中性 ✗（U+2717，非红）/ 未勾选空白（1280×720 及更大）。

长文本 stress = 确定性内容控制（长行省/合同名），非随机。
No-Test-Assisted-Transition：状态经真实生产入口到达；不直置 store featured 终态。
"""
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
# WP-J Group C G7 Test 2（delta v1.5，证据链加固 (d)）：未全局钉定 QT_QUICK_CONTROLS_STYLE——
# 实测「Basic」会改变无关 GUI（RadioButton 文本承载）导致人口面板测试回归；改用**等价显式
# 框式规格**（②③ 显式方框，样式无关）+ 记录运行期 `QQuickStyle.name()`/字体入证据。

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

EVIDENCE_BASE = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/WP-J_Player-Visible-Feedback-and-Actionability/03-da-evidence/GroupC"
)


@pytest.fixture(autouse=True)
def _preserve_global_random_state():
    """进程级 RNG guard（防 cross-test 泄漏；同 wpm/wpo_rng_guard 机制）。"""
    saved = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved)

import shiboken6  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

from src.api import session_api  # noqa: E402
from src.ui.gui.models.candidate_list_model import CandidateListModel  # noqa: E402
from src.ui.gui.models.event_list_model import EventListModel  # noqa: E402
from src.ui.gui.models.figure_list_model import FigureListModel  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

_ENGINES = []

LONG_PROVINCE = "阿非利加 · 上下行省 · 超长名称 · 沿海管区 · 内陆腹地"
LONG_CONTRACT = "道路与水道综合工程 · 阿皮亚大道延长段 · 沿海排洪渠 · 超长合同名称"


class _DummyGuiApp:
    pass


def _get_app():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def _create_engine(store):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

    _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)
    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", _DummyGuiApp())
    engine._test_refs = theme
    _ENGINES.append(engine)
    return engine, qml_dir


def _capture(engine, out_png, width=1440, height=900, setup=None):
    from PySide6.QtCore import QCoreApplication, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication

    app = _get_app()
    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    roots = engine.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    window = roots[0]
    if setup is not None:
        # 载入后、抓图前的一次性状态设置钩子（如 Q3 否决勾选态；route 仍=DIRECT_PRODUCTION）
        try:
            setup(window)
        except Exception:
            pass
        QGuiApplication.processEvents()
    result = []
    out_dir = os.path.dirname(out_png)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    MAX_ATTEMPTS = 150
    RETRY_INTERVAL_MS = 100
    attempts = {"n": 0}

    def finish(value):
        if not result:
            result.append(value)
        QCoreApplication.quit()

    def grab():
        if result:
            return
        attempts["n"] += 1
        try:
            if not window.isVisible():
                window.show()
            try:
                window.setWidth(width)
                window.setHeight(height)
            except Exception:
                pass
            QGuiApplication.processEvents()
            QGuiApplication.processEvents()
            try:
                window.requestUpdate()
            except Exception:
                pass
            QGuiApplication.processEvents()
            img = None
            try:
                img = window.grabWindow()
            except Exception:
                img = None
            if img is None or img.isNull():
                scr = QGuiApplication.primaryScreen()
                if scr is not None:
                    img = scr.grabWindow(int(window.winId()))
            if img is not None and not img.isNull():
                ok = img.save(out_png)
                finish((out_png, img.width(), img.height()) if ok else None)
                return
            if attempts["n"] >= MAX_ATTEMPTS:
                finish(None)
            else:
                QTimer.singleShot(RETRY_INTERVAL_MS, grab)
        except Exception as exc:  # noqa: BLE001
            finish("exc:" + type(exc).__name__ + ":" + str(exc))

    QTimer.singleShot(0, grab)
    QTimer.singleShot(20000, lambda: finish("timeout"))
    app.exec()
    return result[0] if result else None


def _teardown(engine):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication
    try:
        for win in list(QGuiApplication.topLevelWindows()):
            try:
                win.close()
                win.deleteLater()
            except Exception:
                pass
        engine.deleteLater()
    except Exception:
        pass
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _emit(slice_dir, name, capture, state_prep, phase, viewport):
    out_dir = os.path.join(EVIDENCE_BASE, slice_dir)
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, name)
    meta = os.path.join(out_dir, name[:-4] + ".runtime.json")
    row = {
        "fixture": "test_wpj_groupc_render_evidence.py",
        "phase": phase,
        "viewport": list(viewport),
        "state_prep": state_prep,
        "route": "DIRECT_PRODUCTION",
        "png_path": png if os.path.exists(png) else None,
        "png_sha256": _sha256(png) if os.path.exists(png) else None,
        "capture_ok": bool(capture) and capture not in ("timeout",) and not (
            isinstance(capture, str) and capture.startswith("exc:")),
        "captured_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(row, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return row


# ---- window tree helpers -------------------------------------------------

def _qitem(obj):
    if obj is None:
        return None
    try:
        ptr = shiboken6.Shiboken.getCppPointer(obj)[0]
        return shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        return None


def _window_root_item(window):
    try:
        return _qitem(window.contentItem())
    except Exception:
        return _qitem(window)


def _all_items(root):
    pending = [root]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        try:
            pending.extend(item.childItems())
        except Exception:
            pass


def _find_obj(root, object_name):
    for it in _all_items(root):
        try:
            if it.objectName() == object_name:
                return it
        except Exception:
            pass
    return None


def _texts_under(item):
    out = []
    for it in _all_items(item):
        try:
            if "Text" in it.metaObject().className() and it.property("text"):
                out.append(it.property("text"))
        except Exception:
            pass
    return out


def _population_store():
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("population")
    return store, state, viewer


def _senate_store_with_long_text():
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("senate")

    # 确定性内容控制：加长 nonWar 源对象（长行省/合同名）→ 真实 DTO 长文本
    lengthened = None
    for opt in (store.senateProposalOptions or []):
        t = opt.get("type")
        params = opt.get("params") or {}
        if t == "governor":
            prov = state.get_province(params.get("province_id"))
            if prov is not None:
                prov.name = LONG_PROVINCE
                lengthened = "governor"
                break
        if t == "budget":
            contract = state.get_contract(params.get("contract_id"))
            if contract is not None:
                contract.name = LONG_CONTRACT
                lengthened = "budget"
                break
    if lengthened is None:
        # 无既有 nonWar 源：确定性注入一个 PENDING 建造合同（长名）→ 真实 DTO 长文本
        from src.core.entities.contract import ContractType, ContractStatus
        contract = state.create_contract(
            ContractType.PUBLIC_WORKS, province_id=1, base_cost=100,
            current_turn=state.turn.turn_number,
        )
        contract.status = ContractStatus.PENDING
        contract.name = LONG_CONTRACT
        lengthened = "budget-added"
    return store, state, viewer, lengthened


# ---------------------------------------------------------------------------
# Group-C-1 render
# ---------------------------------------------------------------------------

def test_render_group_c1_featured_table_and_subphase_gain():
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer = _population_store()
        engine, _ = _create_engine(store)
        name = f"group-c-1-population-featured-table-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-C-1", name), w, h)
        rows.append(_emit("Group-C-1", name, cap,
                          "create_gui_prototype_session(population)+selectPhase(population)",
                          "population", (w, h)))
        # 几何断言（同一窗口树）
        window = engine.rootObjects()[0]
        root_item = _window_root_item(window)
        table = _find_obj(root_item, "populationCandidateTable")
        assert table is not None, "未找到候选信息表（窗口树）"
        assert table.height() < 206, f"候选表须压缩自 206（{tag}），实际 {table.height()}"
        offenders = [it.metaObject().className() for it in _all_items(table)
                     if "Flickable" in it.metaObject().className()
                     or "ScrollBar" in it.metaObject().className()]
        assert offenders == [], f"候选表内不得有滚动件（{tag}）: {offenders}"
        # featured：候选名只出现一次每 office（信息表）
        flat = store.populationCandidates
        table_texts = _texts_under(table)
        offices = sorted({c["office"] for c in flat})
        for office in offices:
            feat = [c for c in flat if c["office"] == office and c.get("is_featured")]
            assert len(feat) == 1, f"{office}: featured 恰 1（{tag}）"
            assert any(feat[0]["name"] in t for t in table_texts), f"{office}: featured 名须显示"
        _teardown(engine)
    manifest = os.path.join(EVIDENCE_BASE, "Group-C-1", "population-featured-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


# ---------------------------------------------------------------------------
# Group-C-2 render
# ---------------------------------------------------------------------------

def test_render_group_c2_nonwar_long_text_wrap():
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, lengthened = _senate_store_with_long_text()
        assert lengthened, "原型 senate 需含 nonWar（governor/budget）可加长源对象"
        # 真实刷新：重建 senate view（含长文本 DTO）
        store._refresh_senate_view()
        store.selectPhase("senate")
        options = store.senateProposalOptions or []
        nonwar = [o for o in options if o.get("type") not in ("war", "peace")]
        assert nonwar, "nonWar 选项须存在"
        long_opt = None
        for o in nonwar:
            title = o.get("title") or o.get("label") or ""
            if (LONG_PROVINCE in title) or (LONG_CONTRACT in title):
                long_opt = o
                break
        assert long_opt is not None, f"长文本 nonWar 选项须存在，options={[o.get('title') for o in nonwar]}"

        engine, _ = _create_engine(store)
        name = f"group-c-2-nonwar-long-text-wrap-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-C-2", name), w, h)
        rows.append(_emit("Group-C-2", name, cap,
                          f"create_gui_prototype_session(senate)+selectPhase(senate)+long_{lengthened}_name",
                          "senate", (w, h)))

        # 几何/文本断言：mandatory 标题完整可见（truncated=False）且换行（高 > 单行）
        window = engine.rootObjects()[0]
        root_item = _window_root_item(window)
        want = long_opt.get("title") or long_opt.get("label")
        title_item = None
        for it in _all_items(root_item):
            try:
                if it.property("text") == want:
                    title_item = it
                    break
            except Exception:
                pass
        assert title_item is not None, f"nonWar 长标题须渲染（{tag}）"
        assert title_item.property("truncated") is False, f"长标题须完整可见（ElideNone，{tag}）"
        assert title_item.height() >= 24, f"长标题须换行为多行（{tag}），height={title_item.height()}"
        _teardown(engine)
    manifest = os.path.join(EVIDENCE_BASE, "Group-C-2", "nonwar-wrap-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


# ---------------------------------------------------------------------------
# WP-J Group C Pre-G6 回归（delta v1.2 / FC-C15–C17）
# 「2 元老院表决」面板（Panel2）提案身份文本 wrap —— senate_vote 步长提案行完整可见。
# ---------------------------------------------------------------------------

# 确定性内容控制：身份文本极长的 war_proposal（对齐 Owner 实机截断样例同类面）
LONG_WAR_LABEL = "皮洛士战争 · 极长战争名称 · 沿海战区 · 内陆腹地 · 延伸战役名"
LONG_COMMANDER = "盖乌斯 · 尤利乌斯 · 凯撒 · 奥古斯都 · 极长指挥官姓名 · 绰号"


def _has_property(item, name):
    try:
        return item.metaObject().indexOfProperty(name) >= 0
    except Exception:
        return False


def _parent_item(item):
    try:
        return item.parentItem()
    except Exception:
        return None


def _ancestor_with_property(item, name):
    cur = _parent_item(item)
    while cur is not None:
        if _has_property(cur, name):
            return cur
        cur = _parent_item(cur)
    return None


def _panel2_identity_and_checkbox(stage_root, label):
    """R5（FC-C36 承载重构后）定位 ② 行 → (身份文本, 同行 CheckBox, 行卡)。

    ② 与 ① 承载同构（text-less CheckBox + 同级 `Text`）后，改用**② 行卡唯一含
    支持率辅助文本**（`supportRateText` → 含“支持率”）作为区分锚点（①③ 行卡均无）。
    身份文本 = 行内**同级 `Text`**（`text == label`；不再位于 `CheckBox.contentItem`）。
    同行 CheckBox 在非输入态（`tribune_veto`/`results`）隐蔽（FC-C36），可为 None。
    """
    for it in _all_items(stage_root):
        try:
            if "Text" not in it.metaObject().className():
                continue
            if it.property("text") != label:
                continue
        except Exception:
            continue
        # ② 身份文本 = 行 `RowLayout` 的**直接子项**（① 标题也是；③ 标题在嵌套 `ColumnLayout` 内、排除）
        parent = _parent_item(it)
        if parent is None or "RowLayout" not in parent.metaObject().className():
            continue
        card = _nearest_rect_ancestor_by_rgb(it, (255, 246, 230))
        if card is None:
            continue
        has_rate = False
        for t in _all_items(card):
            try:
                if "Text" in t.metaObject().className() and "支持率" in (t.property("text") or ""):
                    has_rate = True
                    break
            except Exception:
                continue
        if not has_rate:
            continue
        cb = None
        row = parent
        for c in _all_items(row):
            try:
                if "CheckBox" in c.metaObject().className():
                    cb = c
                    break
            except Exception:
                continue
        return it, cb, card
    return None, None, None


def _senate_vote_store_with_long_proposal():
    """真实 store 驱动至 senate_vote + 确定性长提案 label。

    路径：`create_gui_prototype_session(senate)` → `selectPhase(senate)`
    → 提案决策完成 flow flag → `state.add_senate_proposal`（长身份文本 war_proposal；
    确定性内容控制）→ `_refresh_senate_view()` → 权威 read-model 进入 `senate_vote`。
    同 `test_wpfr1_stage_screens.py` 的确定性种入先例（真实 state API + 真 store 刷新），
    非直置 store 终态；长文本为内容控制（非随机）。
    """
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("senate")

    # 提案决策完成（flow flag）→ 使权威 read-model 进入 senate_vote 子步骤
    state.senate_proposal_decision_complete = True

    # 确定性内容控制：身份文本极长的 war_proposal（真实 DTO 长 label；
    # war_proposal 的 `label` 由 `_proposal_label` 逐字重算，长文本来自 war_label/commander）
    state.add_senate_proposal({
        "type": "war_proposal",
        "war_id": "pyrrhic_war",
        "war_label": LONG_WAR_LABEL,
        "mode": "command",
        "payload": {"target_commander_label": LONG_COMMANDER, "reinforcement_n": 4},
        "proposer_faction": "optimates",
        "proposer_player": "player_optimates",
        "consul_id": 1,
    })
    store._refresh_senate_view()
    assert store.senateCurrentStep == "senate_vote", f"step={store.senateCurrentStep}"

    long_row = None
    for r in (store.senateSubmittedProposals or []):
        lbl = r.get("label") or ""
        if LONG_WAR_LABEL in lbl:
            long_row = r
            break
    assert long_row is not None, (
        f"须有长 label 提案，labels={[r.get('label') for r in (store.senateSubmittedProposals or [])]}"
    )
    return store, state, viewer, long_row.get("label"), "war_proposal"


def test_render_group_c_senate_vote_long_proposal_wrap():
    """RENDER_AUTOMATED（FC-C17）：senate_vote 步 Panel2 长提案行完整可见（无「…」），
    且换行为多行（行高内容驱动）。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, want_label, lengthened = _senate_vote_store_with_long_proposal()
        assert store.senateCurrentStep == "senate_vote"
        assert want_label, "长提案 label 须非空"

        engine, _ = _create_engine(store)
        name = f"group-c-senate-vote-long-proposal-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-C-Vote", name), w, h)
        rows.append(_emit(
            "Group-C-Vote", name, cap,
            "create_gui_prototype_session(senate)+submitPopulationVotes+doSubmitSenateProposals"
            f"+long_{lengthened}_name",
            "senate_vote", (w, h),
        ))

        window = engine.rootObjects()[0]
        root_item = _window_root_item(window)
        # 定位 Panel2 提案身份文本（R5 / FC-C36：行内**同级 `Text`** 承载；② 行卡含支持率辅助文本）
        _r, stage_root = _find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{tag}）"
        target, _cb, card = _panel2_identity_and_checkbox(stage_root, want_label)
        assert target is not None, f"Panel2 身份文本（同级 Text 承载）须渲染（{tag}）"
        assert target.property("truncated") is False, \
            f"长提案文本须完整可见（ElideNone，{tag}）"
        line_count = target.property("lineCount") or 1
        assert line_count >= 2, \
            f"长提案文本须换行为多行（{tag}），lineCount={line_count}"
        assert card is not None and (card.property("height") or 0) >= 24, \
            f"② 行卡高须内容驱动（{tag}），h={card.property('height') if card else None}"
        _teardown(engine)

    manifest = os.path.join(EVIDENCE_BASE, "Group-C-Vote", "senate-vote-wrap-screenshots.manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


# ---------------------------------------------------------------------------
# WP-J Group C Pre-G6 VisualDelta（delta v1.3 / FC-C18–C21）
# Q1 表决行卡边框 / Q2 信息表表头 / Q3 否决勾选双态。
# ---------------------------------------------------------------------------

def _pen_width(rect):
    """读取 QQuickRectangle 的 border.width（QQuickPen）；不可读时返回 None。"""
    try:
        pen = rect.property("border")
    except Exception:
        return None
    if pen is None:
        return None
    try:
        val = getattr(pen, "width")
        if callable(val):
            return val()
        if isinstance(val, int):
            return val
    except Exception:
        pass
    try:
        return pen.property("width")
    except Exception:
        return None


def _rgb(qcolor):
    try:
        return (qcolor.red(), qcolor.green(), qcolor.blue())
    except Exception:
        return None


def _nearest_rect_ancestor_by_rgb(item, rgb):
    """向上寻找最近的 base color == rgb 的 QQuickRectangle 祖先。"""
    cur = _parent_item(item)
    while cur is not None:
        try:
            cls = cur.metaObject().className()
        except Exception:
            cls = ""
        if "Rectangle" in cls and _rgb(cur.property("color")) == rgb:
            return cur
        cur = _parent_item(cur)
    return None


def _count_color_near(png_path, item, target_rgb, window=None, tol=10):
    """在 item 的屏幕矩形范围内统计 target_rgb（容差 tol）像素数（返回 -1 表示图像不可读）。"""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage
    img = QImage(png_path)
    if img.isNull():
        return -1
    try:
        tl = item.mapToScene(QPointF(0.0, 0.0))
    except Exception:
        return -1
    scale = 1.0
    if window is not None:
        try:
            ww = float(window.width())
            if ww > 0:
                scale = img.width() / ww
        except Exception:
            scale = 1.0
    x0 = int(tl.x() * scale) - 2
    y0 = int(tl.y() * scale) - 2
    x1 = int((tl.x() + item.width()) * scale) + 2
    y1 = int((tl.y() + item.height()) * scale) + 2
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(img.width(), x1); y1 = min(img.height(), y1)
    tr, tg, tb = target_rgb
    n = 0
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            c = img.pixelColor(xx, yy)
            if abs(c.red() - tr) <= tol and abs(c.green() - tg) <= tol and abs(c.blue() - tb) <= tol:
                n += 1
    return n


def test_render_group_c_visualdelta_q1_vote_rows_bordered_card():
    """RENDER_AUTOMATED（FC-C18）：senate_vote 步「2 元老院表决」每行带边框卡
    （#FFF6E6 + border.width=1），与 ③ 保民官否决行同款。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, want_label, _lengthened = _senate_vote_store_with_long_proposal()
        assert store.senateCurrentStep == "senate_vote"
        engine, _ = _create_engine(store)
        name = f"group-c-visualdelta-q1-vote-bordered-card-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-C-VisualDelta", name), w, h)
        rows.append(_emit("Group-C-VisualDelta", name, cap,
                          "create_gui_prototype_session(senate)+doSubmitSenateProposals",
                          "senate_vote", (w, h)))
        window = engine.rootObjects()[0]
        root_item = _window_root_item(window)
        # 定位 Panel2 提案身份文本（R5 / FC-C36：行内**同级 `Text`** 承载；② 行卡含支持率辅助文本）
        _r, stage_root = _find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{tag}）"
        target, _cb, card = _panel2_identity_and_checkbox(stage_root, want_label)
        assert target is not None, f"表决面板身份文本（同级 Text 承载）须渲染（{tag}）"
        chain = []
        _cur = _parent_item(target)
        while _cur is not None and len(chain) < 12:
            try:
                _cls = _cur.metaObject().className()
            except Exception:
                _cls = "?"
            chain.append(f"{_cls}|{_rgb(_cur.property('color'))}")
            _cur = _parent_item(_cur)
        assert card is not None, f"表决行须套带边框卡 #FFF6E6（FC-C18）（{tag}）chain={chain}"
        assert (card.property("height") or 0) > 0, f"卡高须 > 0（{tag}）"
        assert target.property("truncated") is False, f"身份文本须完整可见（{tag}）"
        # 线条框：在卡屏幕矩形内采样边框色 #E0B56C 像素（渲染级线条框证据）
        border_px = _count_color_near(
            os.path.join(EVIDENCE_BASE, "Group-C-VisualDelta", name),
            card, (0xE0, 0xB5, 0x6C), window=window, tol=12)
        assert border_px and border_px > 0, \
            f"表决行卡须见边框线条（#E0B56C），px={border_px}（{tag}）"
        _teardown(engine)
    manifest = os.path.join(EVIDENCE_BASE, "Group-C-VisualDelta", "visualdelta-q1-manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_c_visualdelta_q2_table_header_best_candidate():
    """RENDER_AUTOMATED（FC-C19）：population 步信息表表头第 2 列 =「最佳候选人」，
    9 列几何不破。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer = _population_store()
        engine, _ = _create_engine(store)
        name = f"group-c-visualdelta-q2-table-header-{tag}.png"
        cap = _capture(engine, os.path.join(EVIDENCE_BASE, "Group-C-VisualDelta", name), w, h)
        rows.append(_emit("Group-C-VisualDelta", name, cap,
                          "create_gui_prototype_session(population)+selectPhase(population)",
                          "population", (w, h)))
        window = engine.rootObjects()[0]
        root_item = _window_root_item(window)
        table = _find_obj(root_item, "populationCandidateTable")
        assert table is not None, f"未找到候选信息表（{tag}）"
        texts = _texts_under(table)
        assert "最佳候选人" in texts, f"表头须含「最佳候选人」（{tag}）"
        for col in ("官职", "军略", "智略", "魅力", "热忱", "影响力", "派系", "选举结果"):
            assert col in texts, f"表头列「{col}」须保留（9 列几何不破，{tag}）"
        assert (table.property("width") or 0) > 0
        _teardown(engine)
    manifest = os.path.join(EVIDENCE_BASE, "Group-C-VisualDelta", "visualdelta-q2-manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def _senate_veto_store_with_selection():
    """真实 store 驱动至 tribune_veto（viewer 派系持执政官 + 保民官；两法案通过）→
    否决勾选双态可控。路径同 test_adapter 先例（record_senate_vote 预录非 viewer 支持票）。"""
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    player_id = result["data"]["human_players"][0]
    viewer = state.get_player(player_id)
    living = list(state.get_living_members())
    consul = next(fig for fig in living if fig.faction_id == viewer.faction_id)
    consul.office = "consul"
    tribune = next(fig for fig in living
                   if fig.faction_id == viewer.faction_id and fig is not consul)
    tribune.office = "tribune"
    store = GuiSessionStore(state)
    store.initialize(player_id)
    store.selectPhase("senate")
    store.doSubmitSenateProposals([
        {"type": "land", "params": {"act_type": "sale", "amount_C": 300}},
        {"type": "land", "params": {"act_type": "distribution", "amount_C": 300}},
    ])
    for p in state.get_all_players():
        if p.player_id != player_id:
            for prop in state.get_senate_proposals():
                state.record_senate_vote(p.player_id, prop["id"], True)
    store.doSubmitSenateVotes()
    assert store.senateCurrentStep == "tribune_veto", store.senateCurrentStep
    veto_ids = list(store.senateVetoCandidateIds or [])
    assert len(veto_ids) >= 2, f"须有 2 条否决候选（双态），实际 {veto_ids}"
    return store, state, viewer, veto_ids


def _setup_veto_selection(veto_id):
    def _fn(window):
        root_item = _window_root_item(window)
        stage_root = None
        for it in _all_items(root_item):
            if _has_property(it, "selectedVetoProposalIds"):
                stage_root = it
                break
        if stage_root is not None:
            stage_root.setProperty("selectedVetoProposalIds", [int(veto_id)])
    return _fn


def _custom_indicator_texts(root_item):
    """收集自定义 indicator（QQuickRectangle 型）内 Text 文案；双态 = {❌, 空白}。"""
    out = []
    for it in _all_items(root_item):
        try:
            if "CheckBox" not in it.metaObject().className():
                continue
            if not _has_property(it, "indicator"):
                continue
            ind = it.property("indicator")
        except Exception:
            continue
        if ind is None:
            continue
        try:
            if "Rectangle" not in ind.metaObject().className():
                continue
            texts = [t.property("text") for t in _all_items(ind)
                     if "Text" in t.metaObject().className()]
        except Exception:
            continue
        out.append(texts[0] if texts else None)
    return out


# ---------------------------------------------------------------------------
# WP-J Group C G7-Delta（delta v1.4 / FC-C22）—— Q1 ② 表决行 指示器↔身份文本 间距 = 与 ③ 一致
# WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31）—— ③ 否决行勾选框回归平台默认
# ---------------------------------------------------------------------------

_R4_EVID_DIR = "Group-C-G7TestR4Delta"


def _row_result_glyph(cb):
    """CheckBox 所在行（父 RowLayout）内、行首最近可见结果字形 Text（✓/✗）→ (Text, 字形)。"""
    from PySide6.QtCore import QPointF
    row = _parent_item(cb)
    if row is None:
        return None, None
    best = None
    for t in _all_items(row):
        try:
            if "Text" not in t.metaObject().className():
                continue
            if not t.property("visible"):
                continue
            txt = t.property("text") or ""
        except Exception:
            continue
        if txt in ("\u2713", "\u2717"):
            try:
                x = t.mapToScene(QPointF(0.0, 0.0)).x()
            except Exception:
                continue
            if best is None or x < best[0]:
                best = (x, t, txt)
    if best is None:
        return None, None
    return best[1], best[2]


def _senate_result_mark_expected(result):
    """FC-C32 ②-local 口径：rejected→✗；passed/vetoed→✓；其余（缺失/未知）→ 空白。"""
    if result == "rejected":
        return "\u2717"
    if result in ("passed", "vetoed"):
        return "\u2713"
    return ""


def _panel2_expected_glyph(store, row):
    """FC-C35 ②-local 口径（会话侧复算，独立于 QML）：`item.result` 权威；
    缺失 → `vote_results` 回退投影（`total_influence>0 && !vetoed → passed?✓:✗`，
    **FC-C39 协同**：vetoed 行不参与回退、只经 `item.result` 路径）；否则空白。"""
    r = row.get("result")
    if r == "rejected":
        return "\u2717"
    if r in ("passed", "vetoed"):
        return "\u2713"
    vr = None
    for v in (getattr(store, "senateVoteResults", None) or []):
        try:
            if int(v.get("proposal_id")) == int(row.get("id")):
                vr = v
                break
        except Exception:
            continue
    if vr and (vr.get("total_influence") or 0) > 0 and not vr.get("vetoed"):
        return "\u2713" if vr.get("passed") else "\u2717"
    return ""


def _reference_default_checkbox_indicator_metrics(engine):
    """建一个**参照默认 CheckBox**（无自定义 indicator）→ 返回其 indicator 类名/尺寸（FC-C33(1)）。"""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    src = ("import QtQuick 2.15\n"
           "import QtQuick.Controls 2.15\n"
           "CheckBox { checked: true }\n")
    try:
        comp = QQmlComponent(engine)
        comp.setData(src.encode("utf-8"), QUrl())
        if comp.isError():
            return None, None, None
        obj = comp.create()
        if obj is None:
            return None, None, None
        ind = obj.property("indicator")
        if ind is None:
            return None, None, None
        return (ind.metaObject().className(),
                float(ind.width() or 0), float(ind.height() or 0))
    except Exception:
        return None, None, None

def _find_stage_root(window):
    """返回 (window_root_item, SenateStage 根)（后者 = 具 selectedVetoProposalIds 属性者）。"""
    root_item = _window_root_item(window)
    for it in _all_items(root_item):
        if _has_property(it, "selectedVetoProposalIds"):
            return root_item, it
    return root_item, None


def _is_descendant_of(item, ancestor):
    cur = item
    while cur is not None:
        if cur is ancestor:
            return True
        cur = _parent_item(cur)
    return False


def _first_text_gap_after_indicator(cb, ind):
    """(指示器右缘 → 同行最近可见非空文本左缘) 可见间距（含文本 leftPadding）。"""
    from PySide6.QtCore import QPointF
    try:
        ind_right = ind.mapToScene(QPointF(float(ind.width()), 0.0)).x()
    except Exception:
        return None
    row = _parent_item(cb)
    if row is None:
        return None
    best = None
    for it in _all_items(row):
        try:
            if "Text" not in it.metaObject().className():
                continue
            if not it.property("visible"):
                continue
            if not (it.property("text") or "").strip():
                continue
        except Exception:
            continue
        if _is_descendant_of(it, ind):
            continue
        try:
            tx = it.mapToScene(QPointF(0.0, 0.0)).x() + float(it.property("leftPadding") or 0.0)
        except Exception:
            continue
        if tx <= ind_right + 0.5:
            continue
        if best is None or tx < best:
            best = tx
    return None if best is None else (best - ind_right)


def _veto_checkbox_items(stage_root):
    """③ 否决行 CheckBox（text 空 + 可见；R4 后 indicator = 平台默认，非自绘）→ [(cb, indicator)]。

    注（R4 / FC-C31）：仅按「可见 + text 为空」识别 ③（tribune_veto 步 ① 提案卡 / 战争卡均不
    可见），**不再**要求 indicator 为自绘 `Rectangle`（自绘框已撤）。
    """
    out = []
    for it in _all_items(stage_root):
        try:
            if "CheckBox" not in it.metaObject().className():
                continue
            if not it.property("visible"):
                continue
            if (it.property("text") or "") != "":
                continue
            ind = it.property("indicator")
        except Exception:
            continue
        if ind is None:
            continue
        out.append((it, ind))
    return out


def test_render_group_c_g7delta_q1_vote_indicator_text_gap_matches_tribune():
    """RENDER_AUTOMATED（R5 / FC-C36 承载重构后；原 FC-C22 间距一致性等价保留）：
    ② 输入态（`senate_vote`）行「指示器↔身份文本」可见间距与 ③（`tribune_veto`）行一致
    （|Δ| ≤ 1px）—— 二者现均为「text-less CheckBox + 同级 `Text`」于 `RowLayout{ spacing:6 }`
    （同 ①③；`FC-C22` 特例已退役）。1280×720 及更大视口。"""
    tol = 1.0
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        # ② senate_vote 输入态（勾选框可见；身份文本 = 权威 label）
        store2 = _senate_vote_store_with_long_proposal()[0]
        labels2 = {(r.get("label") or "") for r in (store2.senateSubmittedProposals or [])}
        engine2, _ = _create_engine(store2)
        name2 = f"group-c-g7delta-q1-vote-gap-panel2-{tag}.png"
        cap2 = _capture(engine2, os.path.join(EVIDENCE_BASE, "Group-C-G7Delta", name2), w, h)
        rows.append(_emit("Group-C-G7Delta", name2, cap2,
                          "create_gui_prototype_session(senate)+doSubmitSenateProposals",
                          "senate_vote", (w, h)))
        window2 = engine2.rootObjects()[0]
        _r2, sr2 = _find_stage_root(window2)
        assert sr2 is not None, f"须定位 SenateStage 根（②，{tag}）"
        # ② 表决行 CheckBox（可见 + 同行身份文本命中权威 label；R5 后 CheckBox 无 text）
        panel2 = None
        for it in _all_items(sr2):
            try:
                if "CheckBox" not in it.metaObject().className():
                    continue
                if not it.property("visible"):
                    continue
                row = _parent_item(it)
                hit = row is not None and any(
                    "Text" in t.metaObject().className() and (t.property("text") or "") in labels2
                    for t in _all_items(row))
                if not hit:
                    continue
                ind = it.property("indicator")
                if ind is None:
                    continue
            except Exception:
                continue
            panel2 = (it, ind)
            break
        assert panel2 is not None, f"须定位 ② 表决行 CheckBox（输入态，{tag}）"
        gap2 = _first_text_gap_after_indicator(panel2[0], panel2[1])
        _teardown(engine2)

        # ③ tribune_veto（勾选框可见）
        store3, _s3, _v3, _ids3 = _senate_veto_store_with_selection()
        engine3, _ = _create_engine(store3)
        name3 = f"group-c-g7delta-q1-vote-gap-panel3-{tag}.png"
        cap3 = _capture(engine3, os.path.join(EVIDENCE_BASE, "Group-C-G7Delta", name3), w, h)
        rows.append(_emit("Group-C-G7Delta", name3, cap3,
                          "create_gui_prototype_session(senate)+doSubmitSenateProposals+doSubmitSenateVotes",
                          "tribune_veto", (w, h)))
        window3 = engine3.rootObjects()[0]
        _r3, sr3 = _find_stage_root(window3)
        assert sr3 is not None, f"须定位 SenateStage 根（③，{tag}）"
        vs = _veto_checkbox_items(sr3)
        assert vs, f"须定位 ③ 保民官否决行 CheckBox（{tag}）"
        gap3 = _first_text_gap_after_indicator(vs[0][0], vs[0][1])
        _teardown(engine3)

        assert gap2 is not None and gap3 is not None, f"须测到 ②/③ 间距（{tag}）: {gap2},{gap3}"
        assert abs(gap2 - gap3) <= tol, \
            f"②/③ 指示器↔身份文本间距须一致（FC-C36 同构，{tag}）: ②={gap2}, ③={gap3}"
        assert gap2 > 0, f"② 间距须 > 0（{tag}）"
    manifest = os.path.join(EVIDENCE_BASE, "Group-C-G7Delta", "g7delta-q1-manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_c_g7testr4_q3_veto_default_checkbox_no_selfdrawn():
    """RENDER_AUTOMATED（FC-C31，R4 回退）：tribune_veto 步 ③ 保民官否决行勾选框 = **平台默认**
    指示器（无自绘 USS 框 / 无自绘叉）；勾选/未勾选双态均可渲染。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, veto_ids = _senate_veto_store_with_selection()
        engine, _ = _create_engine(store)
        name = f"group-c-g7testr4-q3-veto-default-checkbox-{tag}.png"
        png = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name)
        cap = _capture(engine, png, w, h, setup=_setup_veto_selection(veto_ids[0]))
        rows.append(_emit(_R4_EVID_DIR, name, cap,
                          "create_gui_prototype_session(senate)+doSubmitSenateProposals"
                          "+doSubmitSenateVotes+veto_select_first",
                          "tribune_veto", (w, h)))
        window = engine.rootObjects()[0]
        _root_item, stage_root = _find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{tag}）"
        vs = _veto_checkbox_items(stage_root)
        assert vs, f"须定位 ③ 保民官否决行 CheckBox（{tag}）"
        assert any(cb.property("checked") for cb, _ind in vs), f"须有已勾选否决行（{tag}）"
        for cb, ind in vs:
            assert _frame_rects(ind) == [], \
                f"③ 指示器不得含自绘框（FC-C31，{tag}）: {_frame_rects(ind)!r}"
            assert ind.width() > 0 and ind.height() > 0, f"指示器须可见（{tag}）"
        _teardown(engine)
    manifest = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-q3-manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


# ---------------------------------------------------------------------------
# WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31 + FC-C32）—— 渲染加固
# ② 结果字形（②-local `senateResultMark`）/ 四者回归平台默认勾选框 / Q1 对照 / 参照默认同形。
# ---------------------------------------------------------------------------

_GREEN = (0x22, 0x8B, 0x22)   # theme.statusSuccess
_RED = (0xB3, 0x26, 0x1E)     # resultMark rejected/vetoed
_EVID_DIR = "Group-C-G7Test2Delta"


def _senate_results_store(veto_first=True):
    """真实 store 驱动至 results（提交否决后）：veto_first 时否决首条 → 生效红 ✗。"""
    store, state, viewer, veto_ids = _senate_veto_store_with_selection()
    store.doSubmitSenateVetoes([int(veto_ids[0])] if veto_first and veto_ids else [])
    assert store.senateCurrentStep == "results", store.senateCurrentStep
    return store, state, viewer, veto_ids


def _visible_boxes_in(root_items):
    """root_items 各自**子树**内可见 QQuickRectangle（方框）列表。"""
    out = []
    for r in root_items:
        for it in _all_items(r):
            try:
                if "Rectangle" not in it.metaObject().className():
                    continue
                if not it.property("visible"):
                    continue
            except Exception:
                continue
            out.append(it)
    return out


def _boxed_check_count(indicators):
    """统计「可见方框 + 可见 ✓ 字形」形态的指示器数（= 默认框内 ✓）。"""
    n = 0
    for ind in indicators:
        for rect in _visible_boxes_in([ind]):
            for t in _all_items(rect):
                try:
                    if "Text" not in t.metaObject().className():
                        continue
                    if not t.property("visible"):
                        continue
                    if (t.property("text") or "") == "\u2713":
                        n += 1
                        break
                except Exception:
                    continue
    return n


def _panel2_rows(stage_root, labels):
    """② 表决行（R5 / FC-C36 承载重构后）：按权威 label 定位身份文本行 →
    [(label, 身份文本, 同行 CheckBox（非输入态隐蔽→None）, 行卡)]。"""
    out = []
    for lbl in labels:
        if not lbl:
            continue
        it, cb, card = _panel2_identity_and_checkbox(stage_root, lbl)
        if it is not None:
            out.append((lbl, it, cb, card))
    return out


def _indicator_result_text(ind):
    """指示器子树内可见结果字形 Text（\u2713 / \u2717）。"""
    for t in _all_items(ind):
        try:
            if "Text" not in t.metaObject().className():
                continue
            if not t.property("visible"):
                continue
            txt = t.property("text") or ""
        except Exception:
            continue
        if txt in ("\u2713", "\u2717"):
            return t, txt
    return None, None


def _visible_checkbox_indicators(stage_root):
    """senate 根下所有可见 CheckBox 的 indicator 列表。"""
    out = []
    for it in _all_items(stage_root):
        try:
            if "CheckBox" not in it.metaObject().className():
                continue
            if not it.property("visible"):
                continue
            ind = it.property("indicator")
        except Exception:
            continue
        if ind is not None:
            out.append(ind)
    return out


def test_render_group_c_g7testr4_q1_panel2_result_mark_inline_text():
    """RENDER_AUTOMATED（FC-C32，加固 (a)）：tribune_veto + results 步 ② 行最左端 = 行内独立
    **无框**结果字形（`senateResultMark(.result)`：rejected→红✗ / passed|vetoed→绿✓ / 缺失→空白）；
    无自绘框；色采样绿/红。1280×720 及更大视口。"""
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        for phase, mk in (("tribune_veto", _senate_veto_store_with_selection),
                          ("results", _senate_results_store)):
            store, _state, _viewer, _ids = mk()
            assert store.senateCurrentStep == phase, store.senateCurrentStep
            by_label = {r.get("label"): r for r in (store.senateSubmittedProposals or [])}
            labels = [l for l in by_label if l]
            engine, _ = _create_engine(store)
            name = f"group-c-g7testr4-q1-panel2-result-mark-{phase}-{tag}.png"
            png = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name)
            cap = _capture(engine, png, w, h)
            rows.append(_emit(_R4_EVID_DIR, name, cap,
                              "create_gui_prototype_session(senate)+doSubmitSenateProposals"
                              "+doSubmitSenateVotes" + ("+doSubmitSenateVetoes" if phase == "results" else ""),
                              phase, (w, h)))
            window = engine.rootObjects()[0]
            _root_item, stage_root = _find_stage_root(window)
            assert stage_root is not None, f"须定位 SenateStage 根（{tag}/{phase}）"
            p2 = _panel2_rows(stage_root, labels)
            assert p2, f"须定位 ② 表决行（身份文本承载，{tag}/{phase}）"
            for label, identity, cb, _card in p2:
                row = by_label.get(label)
                assert row is not None, f"② 行须对应权威提案（{tag}/{phase}）: {label!r}"
                # FC-C36：非输入态（tribune_veto/results）② 行不得显示勾选框
                assert cb is None or not cb.property("visible"), \
                    f"② 行非输入态不得显示勾选框（FC-C36，{tag}/{phase}）"
                exp = _panel2_expected_glyph(store, row)
                t, glyph = _row_result_glyph(identity)
                if exp == "":
                    assert glyph in (None, ""), \
                        f"无表决数据行须无字形（{tag}/{phase}）: {glyph!r} result={row.get('result')!r}"
                    continue
                assert t is not None and glyph == exp, \
                    f"② 结果字形须 == senateResultMark(FC-C35)（{tag}/{phase}）: got={glyph!r} exp={exp!r} result={row.get('result')!r}"
                want = _RED if exp == "\u2717" else _GREEN
                px = _count_color_near(png, t, want, window=window, tol=60)
                assert px and px > 0, \
                    f"② 结果字形须见 {'红' if exp == '\u2717' else '绿'}系像素（{tag}/{phase}）: {px}"
            _teardown(engine)
    with open(os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-q1-manifest.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_c_g7testr4_no_selfdrawn_indicator_in_senate_rows():
    """RENDER_AUTOMATED（FC-C31/FC-C33，加固 (a)）：proposal / senate_vote / tribune_veto / results
    各步可见勾选框的 indicator 均**不含自绘框**（QQuickRectangle 归零）——回落平台默认样式。"""
    plan = (
        ("proposal", _senate_proposal_store),
        ("senate_vote", _senate_vote_store_with_long_proposal),
        ("tribune_veto", _senate_veto_store_with_selection),
        ("results", _senate_results_store),
    )
    for phase, mk in plan:
        for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
            store = mk()[0]
            engine, _ = _create_engine(store)
            name = f"group-c-g7testr4-no-selfdrawn-indicator-{phase}-{tag}.png"
            cap = _capture(engine, os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name), w, h)
            assert cap and cap not in ("timeout",), f"截图须成功（{tag}/{phase}）: {cap}"
            window = engine.rootObjects()[0]
            _root_item, stage_root = _find_stage_root(window)
            assert stage_root is not None
            inds = _visible_checkbox_indicators(stage_root)
            if phase == "results":
                # R5 / FC-C36：results 步 ② 勾选框隐藏（FC-C36）且 ③ 勾选框隐藏（③ visible: step !== "results"）
                # ⇒ 无可见勾选框（合法）。
                assert inds == [], f"results 步不应有可见勾选框（FC-C36，{tag}）"
            else:
                assert inds, f"须见可见勾选框（{tag}/{phase}）"
            for ind in inds:
                assert _frame_rects(ind) == [], \
                    f"勾选框指示器不得含自绘框（FC-C31，{tag}/{phase}）: {_frame_rects(ind)!r}"
            _teardown(engine)
    assert True


def test_render_group_c_g7test2_q2_veto_results_red_mark():
    """RENDER_AUTOMATED（FC-C26）：results 步 否决生效行显**红 ✗**（resultMark）；
    通过行显绿 ✓。1280×720 及更大视口。"""
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, _ids = _senate_results_store(veto_first=True)
        results = {(r.get("label"), r.get("result")) for r in (store.senateSubmittedProposals or [])}
        assert any(res == "vetoed" for _l, res in results), f"须有 vetoed 行（{tag}）: {results}"
        engine, _ = _create_engine(store)
        name = f"group-c-g7test2-q2-results-red-mark-{tag}.png"
        png = os.path.join(EVIDENCE_BASE, _EVID_DIR, name)
        cap = _capture(engine, png, w, h)
        _emit(_EVID_DIR, name, cap,
              "create_gui_prototype_session(senate)+doSubmitSenateProposals+doSubmitSenateVotes+doSubmitSenateVetoes",
              "results", (w, h))
        window = engine.rootObjects()[0]
        _root_item, stage_root = _find_stage_root(window)
        red_texts = []
        green_texts = []
        for it in _all_items(stage_root):
            try:
                if "Text" not in it.metaObject().className() or not it.property("visible"):
                    continue
                txt = it.property("text") or ""
                col = _rgb(it.property("color"))
            except Exception:
                continue
            if txt == "\u2717" and col == _RED:
                red_texts.append(it)
            if txt == "\u2713" and col == _GREEN:
                green_texts.append(it)
        assert red_texts, f"results 须有红 ✗ 结果字形（FC-C26，{tag}）"
        assert green_texts, f"results 须有绿 ✓ 结果字形（FC-C26，{tag}）"
        red_px = _count_color_near(png, red_texts[0], _RED, window=window, tol=60)
        assert red_px and red_px > 0, f"红 ✗ 须见红系像素（{tag}）: {red_px}"
        _teardown(engine)
    assert True


def _border_width(rect):
    """鲁棒读取 QQuickRectangle 的 border.width（int/float/callable/属性三路）。"""
    try:
        pen = rect.property("border")
    except Exception:
        return None
    if pen is None:
        return None
    for attr in ("width",):
        try:
            v = getattr(pen, attr)
            if callable(v):
                v = v()
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        except Exception:
            pass
    try:
        v = pen.property("width")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    except Exception:
        pass
    return None


def test_render_group_c_g7testr4_indicator_matches_reference_default_checkbox():
    """RENDER_AUTOMATED（FC-C33(1)）：senate 勾选框 indicator 归属 = **平台默认样式**
    （与一个**参照默认 CheckBox** 同形：同类名 + 同尺寸；**不含** USS 规格 / 非自绘 Rectangle）；
    记录 `QQuickStyle.name()`。1280×720 及更大视口。"""
    from PySide6.QtQuickControls2 import QQuickStyle
    style_name = QQuickStyle.name()
    rows = []
    for (w, h, tag) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store = _senate_vote_store_with_long_proposal()[0]
        engine, _ = _create_engine(store)
        name = f"group-c-g7testr4-indicator-vs-reference-{tag}.png"
        png = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name)
        cap = _capture(engine, png, w, h)
        rows.append(_emit(_R4_EVID_DIR, name, cap,
                          "create_gui_prototype_session(senate)+doSubmitSenateProposals+long_war_proposal",
                          "senate_vote", (w, h)))
        assert cap and cap not in ("timeout",), f"截图须成功（{tag}）: {cap}"
        window = engine.rootObjects()[0]
        _root_item, stage_root = _find_stage_root(window)
        assert stage_root is not None
        ref_cls, ref_w, ref_h = _reference_default_checkbox_indicator_metrics(engine)
        checked = 0
        for ind in _visible_checkbox_indicators(stage_root):
            cls = ind.metaObject().className()
            assert "Rectangle" not in cls, f"指示器不得为自绘 Rectangle（FC-C31，{tag}）: {cls}"
            if ref_cls is not None:
                assert cls == ref_cls, \
                    f"指示器类须同参照默认 CheckBox（FC-C33(1)，{tag}）: {cls!r} != {ref_cls!r}"
                assert abs(float(ind.width()) - ref_w) <= 1.0 and abs(float(ind.height()) - ref_h) <= 1.0, \
                    f"指示器尺寸须同参照默认（{tag}）: {ind.width()}x{ind.height()} vs {ref_w}x{ref_h}"
            checked += 1
        assert checked >= 1, f"须渲染勾选框（{tag}）"
        _teardown(engine)
    with open(os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-style-pin.runtime.json"),
              "w", encoding="utf-8") as fh:
        json.dump({
            "schema": "wpj-groupc-style-pin/v1",
            "env_QT_QUICK_CONTROLS_STYLE": os.environ.get("QT_QUICK_CONTROLS_STYLE"),
            "qquickstyle_name": style_name,
            "pin_mode": "PLATFORM_DEFAULT_INDICATOR（四者回落平台默认样式指示器；FC-C31/FC-C33）",
        }, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    assert style_name is not None, "QQuickStyle.name() 须可读（FC-C33(1)）"
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_c_g7test2_style_recorded():
    """加固 (d)：记录运行期 `QQuickStyle.name()` + 字体（写入证据 runtime.json）。
    本切片以**等价显式框式规格**（②③ 显式方框，样式无关）替代全局样式钉定——
    实测全局钉定 `Basic` 会改变无关 GUI（RadioButton 文本承载）致人口面板测试回归（见报告）。"""
    from PySide6.QtQuickControls2 import QQuickStyle
    app = _get_app()
    name = QQuickStyle.name()
    font_family = app.font().family() if app is not None else ""
    assert name is not None, "QQuickStyle.name() 须可读（加固 (d)）"
    out = os.path.join(EVIDENCE_BASE, _EVID_DIR, "g7test2-style-pin.runtime.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "schema": "wpj-groupc-style-pin/v1",
            "env_QT_QUICK_CONTROLS_STYLE": os.environ.get("QT_QUICK_CONTROLS_STYLE"),
            "qquickstyle_name": name,
            "font_family": font_family,
            "pin_mode": "EQUIVALENT_EXPLICIT_BOX_SPEC（②③ 显式方框规格，样式无关；未全局钉定）",
        }, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# ---------------------------------------------------------------------------
# WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31 + FC-C33）—— 四者回归平台默认 + 加固
# 无自绘 indicator（四者归零）+ 含战争卡默认框 + Q1 对照（否决⇒②≠✗/③仍红✗）
# + 钉平台默认入 runtime.json + 有头复验如实登记。1280×720 及更大视口。
# ---------------------------------------------------------------------------

_R3_EVID_DIR = "Group-C-G7TestR3Delta"
_USS_SIZE = 20.0
_USS_RADIUS = 3.0
_USS_FILL = (0xFF, 0xFF, 0xFF)      # #FFFFFF
_USS_BORDER = (0xC8, 0xA8, 0x70)    # #C8A870
_NEUTRAL = (0x2C, 0x1E, 0x12)       # #2C1E12


def _pen_color(rect):
    """读取 QQuickRectangle 的 border.color（QColor→RGB）。"""
    try:
        pen = rect.property("border")
    except Exception:
        return None
    if pen is None:
        return None
    try:
        c = getattr(pen, "color")
        if callable(c):
            c = c()
        return _rgb(c)
    except Exception:
        pass
    try:
        return _rgb(pen.property("color"))
    except Exception:
        return None


def _frame_rects(ind):
    """indicator 子树内「框」Rectangle（较大色块：w≥15 且 h≥15）——含 ind 自身若为框。"""
    out = []
    for it in _all_items(ind):
        if not (_has_property(it, "color") and _has_property(it, "radius")):
            continue
        try:
            w = it.width()
            h = it.height()
        except Exception:
            continue
        if w is not None and h is not None and w >= 15 and h >= 15:
            out.append(it)
    return out


def _indicator_mark_rects(ind, visible_only=True):
    """indicator 子树内「记号描边」Rectangle（薄色块：h≤4）——自绘勾/叉的笔画。"""
    out = []
    for it in _all_items(ind):
        if not (_has_property(it, "color") and _has_property(it, "radius")):
            continue
        if visible_only and not it.property("visible"):
            continue
        try:
            h = it.height()
        except Exception:
            continue
        if h is not None and 1.0 <= h <= 4.0:
            out.append(it)
    return out


def _visible_checkbox_items(stage_root):
    """senate 根下所有可见 CheckBox → [(cb, indicator)]。"""
    out = []
    for it in _all_items(stage_root):
        try:
            if "CheckBox" not in it.metaObject().className():
                continue
            if not it.property("visible"):
                continue
            ind = it.property("indicator")
        except Exception:
            continue
        if ind is None:
            continue
        out.append((it, ind))
    return out


def _warcard_checkbox_items(stage_root):
    """战争卡（WarProposalCard）内的可见 CheckBox → [(cb, indicator)]（按 warId 祖先判定）。"""
    out = []
    for cb, ind in _visible_checkbox_items(stage_root):
        if _ancestor_with_property(cb, "warId") is not None:
            out.append((cb, ind))
    return out


def _senate_proposal_store():
    """真实 store 驱动至 senate proposal 步（① 提案卡 + 战争卡可见）。"""
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("senate")
    assert store.senateCurrentStep == "proposal", store.senateCurrentStep
    return store, state, viewer


def _assert_uss_frame(ind, tag, png=None, window=None):
    """断言 indicator 恰含 1 个框，且该框为 USS（尺寸/圆角/填充/边色/边宽）。"""
    frames = _frame_rects(ind)
    assert len(frames) == 1, \
        f"指示器须恰 1 层框（嵌套层数=1，FC-C28/C30）（{tag}）: frames={len(frames)}"
    f = frames[0]
    assert abs(f.width() - _USS_SIZE) <= 0.5 and abs(f.height() - _USS_SIZE) <= 0.5, \
        f"USS 框须 20×20（{tag}）: {f.width()}x{f.height()}"
    assert abs(float(f.property("radius")) - _USS_RADIUS) <= 0.5, f"USS radius 须 3（{tag}）"
    assert _rgb(f.property("color")) == _USS_FILL, \
        f"USS 填充须 #FFFFFF（{tag}）: {_rgb(f.property('color'))}"
    pc = _pen_color(f)
    if pc is not None:
        assert pc == _USS_BORDER, f"USS 边色须 #C8A870（{tag}）: {pc}"
    bw = _border_width(f)
    if bw is not None:
        assert abs(bw - 1.0) <= 0.01, f"USS 边宽须 1（{tag}）: {bw}"
    if png is not None and window is not None:
        bp = _count_color_near(png, f, _USS_BORDER, window=window, tol=20)
        assert bp and bp > 0, f"USS 框须见边框色 #C8A870 像素（{tag}）: {bp}"
    return f


def test_render_group_c_g7testr4_no_uss_frames_four_faces():
    """RENDER_AUTOMATED（FC-C31/FC-C33(1)）：proposal（①+战争卡）/ senate_vote（②）/ tribune_veto（③）
    可见勾选框之 indicator **不含自绘框**（QQuickRectangle 归零）⇒ 平台默认样式指示器。
    1280×720 及更大视口。"""
    rows = []
    faces = {}
    plan = (
        ("proposal", _senate_proposal_store, "①+战争卡"),
        ("senate_vote", lambda: _senate_vote_store_with_long_proposal(), "②"),
        ("tribune_veto", lambda: _senate_veto_store_with_selection(), "③"),
    )
    for (w, h, vp) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        for tag, mk, face in plan:
            store = mk()[0]
            engine, _ = _create_engine(store)
            name = f"group-c-g7testr4-faces-{tag}-{vp}.png"
            png = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name)
            cap = _capture(engine, png, w, h)
            rows.append(_emit(_R4_EVID_DIR, name, cap,
                              "create_gui_prototype_session(senate)+selectPhase(senate)", tag, (w, h)))
            window = engine.rootObjects()[0]
            _root, stage_root = _find_stage_root(window)
            assert stage_root is not None, f"须定位 SenateStage 根（{tag}/{vp}）"
            cbs = _visible_checkbox_items(stage_root)
            assert cbs, f"须见可见勾选框（{tag}/{vp}）"
            for cb, ind in cbs:
                assert _frame_rects(ind) == [], \
                    f"指示器不得含自绘框（FC-C31）（{tag}/{vp}）: {_frame_rects(ind)!r}"
            faces[tag] = max(faces.get(tag, 0), len(cbs))
            if tag == "proposal":
                faces["proposal_warcard"] = max(faces.get("proposal_warcard", 0),
                                                len(_warcard_checkbox_items(stage_root)))
            _teardown(engine)
    assert faces.get("senate_vote", 0) >= 1 and faces.get("tribune_veto", 0) >= 1, faces
    assert faces.get("proposal", 0) >= 1, faces
    manifest = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-faces-manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows, "faces": faces},
                  fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_c_g7testr4_warcard_default_checkbox_no_uss():
    """RENDER_AUTOMATED（FC-C31/FC-C33(4)，含战争卡）：真实 F6 fixture 的 proposal step 渲染战争卡
    （WarProposalCard）——其行勾选框 indicator **不含自绘框**（回落平台默认指示器）。"""
    from src.tests.fixtures.wpgr6_fixtures import build_f6_base
    from src.tests.fixtures.wpgr5_fixtures import FIXED
    rows = []
    for (w, h, vp) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        ctx = build_f6_base()
        store = GuiSessionStore(ctx["state"])
        store.initialize(FIXED["player"])
        store.selectPhase("senate")
        assert (store.senateWarCards or []), "F6 fixture 须产出 senate war cards"
        engine, _ = _create_engine(store)
        name = f"group-c-g7testr4-warcard-default-checkbox-{vp}.png"
        png = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name)
        cap = _capture(engine, png, w, h)
        rows.append(_emit(_R4_EVID_DIR, name, cap,
                          "build_f6_base()+GuiSessionStore.initialize+selectPhase(senate)",
                          "proposal", (w, h)))
        window = engine.rootObjects()[0]
        _root, stage_root = _find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{vp}）"
        war_cbs = _warcard_checkbox_items(stage_root)
        assert war_cbs, f"须渲染战争卡勾选框（WarProposalCard）（{vp}）"
        for cb, ind in war_cbs:
            assert _frame_rects(ind) == [], \
                f"战争卡指示器不得含自绘框（FC-C31，{vp}）: {_frame_rects(ind)!r}"
        _teardown(engine)
    manifest = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-warcard-manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_c_g7testr4_q1_contrast_vetoed_panel2_green_panel3_red():
    """RENDER_AUTOMATED（FC-C33(2)，关键 Q1 对照）：构造「元老院通过后被保民官否决」的提案
    （`.result == "vetoed"`）⇒ 断言 **② 结果字形 ≠ ✗**（恰为绿 ✓）、**③ 生效后仍显红 ✗**；
    即 `vetoed` **不改写** ② 元老院结果。1280×720 及更大视口。"""
    rows = []
    for (w, h, vp) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store, _state, _viewer, _ids = _senate_results_store(veto_first=True)
        by_label = {r.get("label"): r for r in (store.senateSubmittedProposals or [])}
        assert any(r.get("result") == "vetoed" for r in by_label.values()), \
            f"须有 vetoed 提案（{vp}）: {[(l, r.get('result')) for l, r in by_label.items()]}"
        engine, _ = _create_engine(store)
        name = f"group-c-g7testr4-q1-contrast-vetoed-{vp}.png"
        png = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name)
        cap = _capture(engine, png, w, h)
        rows.append(_emit(_R4_EVID_DIR, name, cap,
                          "create_gui_prototype_session(senate)+doSubmitSenateProposals"
                          "+doSubmitSenateVotes+doSubmitSenateVetoes(veto_first)",
                          "results", (w, h)))
        window = engine.rootObjects()[0]
        _root, stage_root = _find_stage_root(window)
        assert stage_root is not None, f"须定位 SenateStage 根（{vp}）"
        labels = [l for l in by_label if l]
        vetoed_seen = False
        for label, identity, _cb, _card in _panel2_rows(stage_root, labels):
            row = by_label.get(label)
            if row is None or row.get("result") != "vetoed":
                continue
            vetoed_seen = True
            t, glyph = _row_result_glyph(identity)
            assert t is not None and glyph == "\u2713", \
                f"被否决提案在 ② 须显绿 ✓（非 ✗）（FC-C32，{vp}）: {glyph!r}"
            px = _count_color_near(png, t, _GREEN, window=window, tol=60)
            assert px and px > 0, f"② 绿 ✓ 须见绿系像素（{vp}）: {px}"
        assert vetoed_seen, f"须在 ② 定位到 vetoed 行（{vp}）"
        # ③ 生效后仍显红 ✗
        red_texts = []
        for it in _all_items(stage_root):
            try:
                if "Text" not in it.metaObject().className() or not it.property("visible"):
                    continue
                if (it.property("text") or "") == "\u2717" and _rgb(it.property("color")) == _RED:
                    red_texts.append(it)
            except Exception:
                continue
        assert red_texts, f"③ 生效后须仍显红 ✗（FC-C33(2)，{vp}）"
        px3 = _count_color_near(png, red_texts[0], _RED, window=window, tol=60)
        assert px3 and px3 > 0, f"③ 红 ✗ 须见红系像素（{vp}）: {px3}"
        _teardown(engine)
    manifest = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-q1-contrast-manifest.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({"schema": "wpj-groupc-render-manifest/v1", "rows": rows}, fh,
                  ensure_ascii=False, indent=2)
        fh.write("\n")
    assert all(r["capture_ok"] for r in rows), rows


def test_render_group_c_g7testr4_geometry_1280x720_and_larger():
    """RENDER_AUTOMATED（FC-C33(4)）：senate proposal 步于 1280×720 与更大视口渲染成功、
    窗口/阶段根几何非零（几何保真 & 非回归）。"""
    for (w, h, vp) in ((1440, 900, "1440x900"), (1280, 720, "1280x720")):
        store = _senate_proposal_store()[0]
        engine, _ = _create_engine(store)
        name = f"group-c-g7testr4-geometry-{vp}.png"
        png = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, name)
        cap = _capture(engine, png, w, h)
        assert cap and cap not in ("timeout",), f"截图须成功（{vp}）: {cap}"
        window = engine.rootObjects()[0]
        assert (window.width() or 0) > 0 and (window.height() or 0) > 0, f"窗口几何须非零（{vp}）"
        _root, stage_root = _find_stage_root(window)
        assert stage_root is not None and (stage_root.width() or 0) > 0, f"阶段根几何须非零（{vp}）"
        _teardown(engine)
    assert True


def test_render_group_c_g7testr4_pin_platform_default_runtime_json():
    """FC-C33(1)：钉「平台默认指示器」入证据 runtime.json（QQuickStyle.name() + 字体 + 四面）。"""
    from PySide6.QtQuickControls2 import QQuickStyle
    app = _get_app()
    name = QQuickStyle.name()
    font_family = app.font().family() if app is not None else ""
    assert name is not None, "QQuickStyle.name() 须可读（FC-C33(1)）"
    out = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-platform-default-pin.runtime.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "schema": "wpj-groupc-platform-default-pin/v1",
            "env_QT_QUICK_CONTROLS_STYLE": os.environ.get("QT_QUICK_CONTROLS_STYLE"),
            "qquickstyle_name": name,
            "font_family": font_family,
            "faces": [
                "senate.panel1.checkbox", "senate.panel2.checkbox",
                "senate.panel3.checkbox", "warcard.checkbox",
            ],
            "pin_mode": "PLATFORM_DEFAULT_INDICATOR（四者无自定义 indicator；FC-C31）",
        }, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def test_render_group_c_g7testr4_live_headed_recheck():
    """FC-C33(4) 有头/窗口化 live 复验（真实 app.py；非 offscreen）——本 DA 运行环境为无头 WSL，
    无可用图形显示 ⇒ 如实登记 NOT_APPLICABLE（不伪造）；以离屏 RENDER_AUTOMATED 替代。"""
    display = os.environ.get("DISPLAY")
    plat = os.environ.get("QT_QPA_PLATFORM")
    out = os.path.join(EVIDENCE_BASE, _R4_EVID_DIR, "g7testr4-live-headed.runtime.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    record = {
        "schema": "wpj-groupc-live-headed/v1",
        "requested": "有头/窗口化 live 复验（真实 app.py；非 offscreen；含战争行勾选框）",
        "display": display,
        "QT_QPA_PLATFORM_env": plat,
        "status": "NOT_APPLICABLE_HEADLESS",
        "reason": ("本 DA 运行环境为无头 WSL（无可用 X/Wayland DISPLAY；测试进程强制 "
                   "QT_QPA_PLATFORM=offscreen）；无法进行有头实机 live 复验。已以离屏 "
                   "RENDER_AUTOMATED（真实 Main.qml + 真实生产链 create_gui_prototype_session）"
                   "替代，并如实登记。"),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    assert not display, f"若有 DISPLAY 则应做有头复验（不得伪报）: {display}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
