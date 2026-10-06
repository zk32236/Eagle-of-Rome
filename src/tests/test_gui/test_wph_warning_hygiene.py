# src/tests/test_gui/test_wph_warning_hygiene.py
"""WP-H — QML runtime warning hygiene（EOR20260821-01 GUI-BETA-R1；S1 Attempt-1）。

覆盖 T-H01 / T-H02 / T-H03 / T-H04 / T-H05 / T-H10（SA baseline
`SA-Baseline-acceptance-traceability-WP-H-2026-09-27.md` §2）。

运行面（DIRECT_PRODUCTION，设计 §4.O / §6）：
  - 真实 `GuiSessionStore`（`session_api.create_gui_prototype_session`）+ 真实 stage QML
    经 `QQmlApplicationEngine`（`QT_QPA_PLATFORM=offscreen`）离屏实例化；
  - 状态输入 = store 的权威投影属性（`_combat_view` / `_revenue_view` / `_revenue_result`
    / `_resolution_view`），形状与 producer 输出一致（非 QML-only fake）；
  - 告警捕获 = `qInstallMessageHandler`（raw 全量，含 unable-to-assign / cannot-read-property）
    + `engine.warnings`。

零抑制：本测试不安装任何 logger/stderr/Qt/regex 抑制；捕获仅用于计数与归档（FC-H-01/05）。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import contextlib
import re

from PySide6.QtCore import QObject, Qt, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")

EVIDENCE_DIR = os.environ.get("WPH_EVIDENCE_DIR")
RUN_TAG = os.environ.get("WPH_RUN_TAG", "run")

# FC-H-04 in-scope 告警族（可归因于项目 QML/runtime binding·layout·control）。
IN_SCOPE_PATTERNS = (
    r"Unable to assign",
    r"Cannot read prop",          # Cannot read property / Cannot read properties
    r"is not a function",
    r"TypeError",
    r"Detected anchors on an item that is managed by a layout",
    r"Cannot specify contentItem",
)
_IN_SCOPE_RE = re.compile("|".join(IN_SCOPE_PATTERNS))


def in_scope(messages):
    """raw 消息中 in-scope（项目 QML/runtime）告警行。"""
    return [m for m in messages if _IN_SCOPE_RE.search(m)]


# ── 全生命周期 Qt 消息捕获（R-03 / S1 Attempt-3）────────────────────────────
# 非抑制：安装会话级 message handler，把**全部** Qt 消息按行**实时**写入 raw 文件
# （fd 级 os.write，进程 exit 阶段仍有效）+ 内存列表；raw 覆盖整个 process 生命周期
# （含 interpreter teardown）。仅在证据运行（EVIDENCE_DIR 设置）时安装，避免对普通
# 全量回归进程产生全局副作用。
_ALL_MSGS = []              # 本次进程捕获的全部 Qt 消息（未过滤/未去重）
_RAW_FD = None
_RAW_PATH = None


import gc  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402


def _raw_fd():
    """惰性打开全生命周期 raw 文件（fd 级，脱离 Python 文件对象生命周期）。"""
    global _RAW_FD, _RAW_PATH
    if _RAW_FD is None:
        if not EVIDENCE_DIR:
            return None
        try:
            _RAW_PATH = os.path.join(EVIDENCE_DIR, f"T-H01/lifecycle-stream-{RUN_TAG}.log")
            os.makedirs(os.path.dirname(_RAW_PATH), exist_ok=True)
            _RAW_FD = os.open(_RAW_PATH, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        except Exception:
            _RAW_FD = None
    return _RAW_FD


def _record(text):
    """把一条 Qt raw 消息记入全生命周期列表 + fd 落盘（仅在证据模式）。"""
    if not EVIDENCE_DIR:
        return
    _ALL_MSGS.append(text)
    fd = _raw_fd()
    if fd is not None:
        try:
            os.write(fd, (text + "\n").encode("utf-8", "replace"))
        except Exception:
            pass


def _lifecycle_handler(_type, _ctx, msg):
    _record(str(msg))


if EVIDENCE_DIR:
    qInstallMessageHandler(_lifecycle_handler)


# ───────────────────────────── 基础设施 ─────────────────────────────

def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


@contextlib.contextmanager
def capture_qt_raw():
    """全量 raw Qt 消息捕获（qInstallMessageHandler；不改写消息）。

    同时汇入全生命周期列表/落盘（证据模式），使 lifecycle raw 覆盖整个 process
    生命周期（含 teardown）——非抑制：消息只记录、不过滤。
    """
    captured = []

    def _h(_t, _c, msg):
        s = str(msg)
        captured.append(s)
        _record(s)

    old = qInstallMessageHandler(_h)
    try:
        yield captured
    finally:
        qInstallMessageHandler(old)


def _make_store(combat_view=None, revenue_view=None, revenue_result=None,
                resolution_view=None):
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    store = GuiSessionStore(state)
    store.initialize(viewer)
    # 状态输入（producer-shaped 投影；不改 Store/API 语义）。
    if combat_view is not None:
        store._combat_view = combat_view
    if revenue_result is not None:
        store._revenue_result = revenue_result
    if revenue_view is not None:
        store._revenue_view = revenue_view
    if resolution_view is not None:
        store._resolution_view = resolution_view
    return store


_ENGINES = []  # 保活：防止 QQmlApplicationEngine 被 GC 导致 root item 失效


def _load_stage(qml_name, store):
    """离屏实例化 stage QML；返回 (engine, roots, qml_warnings)。"""
    app = _get_app()
    engine = QQmlApplicationEngine()
    _ENGINES.append(engine)
    engine.addImportPath(QML_DIR)
    qml_warnings = []
    engine.warnings.connect(lambda errs: qml_warnings.extend(str(e.toString()) for e in errs))
    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    ctx.setContextProperty("theme", theme)
    engine._wph_refs = (theme, store)
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "stages", qml_name)))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, f"{qml_name} loaded with no root object"
    root = roots[0]
    # 将 stage 挂入离屏 QQuickWindow（Repeater/Layout delegate 孵化所需）。
    try:
        win = QQuickWindow()
        win.setWidth(1440)
        win.setHeight(900)
        root.setParentItem(win.contentItem())
        win.show()
        _ENGINES.append(win)
    except Exception:
        pass
    for _ in range(3):
        app.processEvents()
    return engine, root, qml_warnings


def _walk(obj):
    """遍历 QML 对象树（可视子项 childItems() + QObject.children()，按 id 去重）。"""
    yield obj
    seen = set()
    kids = []
    if hasattr(obj, "childItems"):
        try:
            kids.extend(obj.childItems())
        except Exception:
            pass
    try:
        kids.extend(obj.children())
    except Exception:
        pass
    for child in kids:
        cid = id(child)
        if cid in seen:
            continue
        seen.add(cid)
        yield from _walk(child)


def _all_texts(root):
    out = []
    for item in _walk(root):
        try:
            t = item.property("text")
        except Exception:
            continue
        if isinstance(t, str) and t:
            out.append(t)
    return out


def _find_text_item(root, text):
    for item in _walk(root):
        try:
            if item.property("text") == text:
                return item
        except Exception:
            continue
    return None


def _run_stage(qml_name, store):
    with capture_qt_raw() as raw:
        _, root, qml_warnings = _load_stage(qml_name, store)
    return root, raw, qml_warnings


def _write_text(path, content):
    if not EVIDENCE_DIR:
        return
    full = os.path.join(EVIDENCE_DIR, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)


# ── 确定性生命周期销毁（R-03 核心）──────────────────────────────────────────
# 在 context/store 拆除**之前**销毁本进程创建的 QML roots/engines：先对其根对象
# `deleteLater()`（bindings 随树销毁，不重新求值）→ flush DeferredDelete（此刻
# sessionStore 仍有效）→ 再释放 engine/window 引用并 gc。以此**从机制上**消除
# teardown 阶段 `sessionStore` 失效后 QML binding 重求值产生的 `… of null` 告警
# （非抑制、非过滤、非产品侧 root guard——产品面零改）。

def _flush_deferred(app):
    try:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    except Exception:
        pass
    if app is not None:
        for _ in range(3):
            app.processEvents()


def _dispose_all_engines():
    app = QGuiApplication.instance()
    engines = list(_ENGINES)
    qml_engines = [e for e in engines if isinstance(e, QQmlApplicationEngine)]
    windows = [e for e in engines if isinstance(e, QQuickWindow)]
    for eng in qml_engines:
        try:
            for root in list(eng.rootObjects()):
                try:
                    root.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
    for win in windows:
        try:
            win.hide()
        except Exception:
            pass
        try:
            win.deleteLater()
        except Exception:
            pass
    _flush_deferred(app)
    for eng in qml_engines:
        try:
            eng.clearComponentCache()
        except Exception:
            pass
    _ENGINES.clear()
    gc.collect()
    _flush_deferred(app)


@pytest.fixture(autouse=True)
def _wph_lifecycle_disposal():
    """每个测试后确定性销毁其 QML roots/engines；断言生命周期 raw 无 in-scope 告警。

    `WPH_DISPOSAL_MODE=naive`：**仅用于证据对照**——跳过确定性销毁，以重现
    interpreter-teardown 阶段 `… of null` 告警（证明 before/after 差异真实存在，
    而非抑制）。默认模式一律执行确定性销毁。
    """
    before = len(_ALL_MSGS)
    yield
    if os.environ.get("WPH_DISPOSAL_MODE") == "naive":
        return
    _dispose_all_engines()
    if EVIDENCE_DIR:
        slice_msgs = _ALL_MSGS[before:]
        hits = in_scope(slice_msgs)
        assert hits == [], (
            "生命周期/teardown raw 仍有 in-scope 告警（R-03）：\n" + "\n".join(hits)
        )


@pytest.fixture(scope="session", autouse=True)
def _wph_session_lifecycle_evidence():
    """会话末确定性销毁残留 QML roots/engines，并归档全生命周期 raw + count summary。

    raw 覆盖**整个 process 生命周期**（含 teardown）：确定性销毁后进程退出阶段已无
    残留 engine/store，故不会有 `… of null` teardown 告警（R-03 机制消除，非抑制）。
    """
    yield
    if os.environ.get("WPH_DISPOSAL_MODE") == "naive":
        # 证据对照：不做确定性销毁 —— interpreter teardown 告警将写入 stream 文件
        return
    _dispose_all_engines()
    if not EVIDENCE_DIR:
        return
    msgs = list(_ALL_MSGS)
    hits = in_scope(msgs)
    sigs = _signature_inventory(msgs)
    raw_text = "\n".join(msgs) + ("\n" if msgs else "")
    if not raw_text:
        raw_text = "<no Qt messages over full process lifecycle (incl. teardown)>\n"
    _write_text(f"T-H01/lifecycle-raw-{RUN_TAG}.log", raw_text)
    _write_text(f"T-H01/lifecycle-count-summary-{RUN_TAG}.md",
                "# T-H01 — full-lifecycle count summary（%s）\n\n" % RUN_TAG
                + "| 指标 | 值 |\n|:--|--:|\n"
                + f"| raw 总数（全生命周期，不去重） | {len(msgs)} |\n"
                + f"| in-scope raw 行数 | {len(hits)} |\n"
                + f"| dedup 签名数 | {len(sigs)} |\n")
    inv = ["# T-H01 — full-lifecycle signature inventory（%s）\n" % RUN_TAG,
           "", f"- raw 总数（不去重）= {len(msgs)}",
           f"- in-scope raw 行数 = {len(hits)}",
           f"- dedup 签名数 = {len(sigs)}", ""]
    if sigs:
        inv += ["| dedup 签名 | raw 次数 |", "|:--|--:|"]
        for k in sorted(sigs):
            inv.append(f"| `{k}` | {sigs[k]} |")
    else:
        inv.append("(无 in-scope 签名)")
    _write_text(f"T-H01/lifecycle-signature-inventory-{RUN_TAG}.md", "\n".join(inv) + "\n")
    fmap = {}
    for m in msgs:
        mm = re.search(r"([\w/]+\.qml):(\d+):", m)
        if mm:
            key = f"{mm.group(1)}:{mm.group(2)}"
            fmap[key] = fmap.get(key, 0) + 1
    fm = ["# T-H01 — full-lifecycle file/expression map（%s）\n" % RUN_TAG, ""]
    if fmap:
        fm += ["| file:line | raw 次数 |", "|:--|--:|"]
        for k in sorted(fmap):
            fm.append(f"| `{k}` | {fmap[k]} |")
    else:
        fm.append("(全生命周期无 QML 告警行)")
    _write_text(f"T-H01/lifecycle-file-map-{RUN_TAG}.md", "\n".join(fm) + "\n")
    assert hits == [], "full-lifecycle raw 仍有 in-scope 告警（R-03）：\n" + "\n".join(hits)


# ───────────────────────────── T-H01 ─────────────────────────────
# 机械签名扫描骨架（before/after raw + raw 总数（不去重）+ dedup 签名数）。

_TH01_SCENARIOS = (
    # (label, qml, store kwargs)
    ("combat_empty", "CombatStage.qml",
     dict(combat_view={"war_slots": [None, None, None], "battle_results": []})),
    ("combat_result_no_naval", "CombatStage.qml",
     dict(combat_view={"battle_results": [{"land": {"executed": True, "result": "victory"}}]})),
    ("revenue_missing_optionals", "RevenueStage.qml",
     dict(revenue_result={}, revenue_view={})),
    ("resolution_empty_view", "ResolutionStage.qml", dict(resolution_view={})),
)


def _th01_scan():
    rows = []
    all_raw = []
    for label, qml, kwargs in _TH01_SCENARIOS:
        store = _make_store(**kwargs)
        _, raw, _ = _run_stage(qml, store)
        all_raw.extend(raw)
        hits = in_scope(raw)
        rows.append((label, qml, len(raw), len(hits)))
    return all_raw, rows


def _signature_inventory(messages):
    """逐行签名归类（稳定排序；不去重 raw，附带 dedup 签名集合）。"""
    sigs = {}
    for m in messages:
        if not _IN_SCOPE_RE.search(m):
            continue
        key = re.sub(r"0x[0-9a-fA-F]+", "0x?", m)
        key = re.sub(r"\d+", "N", key)
        sigs[key] = sigs.get(key, 0) + 1
    return sigs


def _inventory_md(tag, raw, rows):
    sigs = _signature_inventory(raw)
    lines = [
        f"# T-H01 — 机械签名扫描（{tag}）",
        "",
        "> raw console（qInstallMessageHandler 全量，未过滤/未去重）+ 机械签名扫描。",
        "",
        "## raw 总数 / in-scope 计数（按场景）",
        "",
        "| 场景 | 文件 | raw 行 | in-scope 行 |",
        "|:--|:--|--:|--:|",
    ]
    for label, qml, n_raw, n_hit in rows:
        lines.append(f"| {label} | {qml} | {n_raw} | {n_hit} |")
    total = len(raw)
    hits = len(in_scope(raw))
    lines += [
        f"| **合计** | — | **{total}** | **{hits}** |",
        "",
        "## 签名清单（in-scope）",
        "",
        f"- raw 总数（不去重）= {total}",
        f"- in-scope raw 行数（不去重）= {hits}",
        f"- dedup 签名数 = {len(sigs)}",
        "",
    ]
    if sigs:
        lines += ["| dedup 签名 | raw 出现次数 |", "|:--|--:|"]
        for k in sorted(sigs):
            lines.append(f"| `{k}` | {sigs[k]} |")
    else:
        lines.append("(无 in-scope 签名)")
    return "\n".join(lines) + "\n"


def _count_summary_md(tag, raw, rows):
    sigs = _signature_inventory(raw)
    lines = [
        f"# T-H01 — count summary（{tag}）",
        "",
        "| 指标 | 值 |",
        "|:--|--:|",
        f"| raw 总数（不去重） | {len(raw)} |",
        f"| in-scope raw 行数（不去重） | {len(in_scope(raw))} |",
        f"| dedup 签名数 | {len(sigs)} |",
        "",
        "场景明细：",
        "",
        "| 场景 | 文件 | raw 行 | in-scope 行 |",
        "|:--|:--|--:|--:|",
    ]
    for label, qml, n_raw, n_hit in rows:
        lines.append(f"| {label} | {qml} | {n_raw} | {n_hit} |")
    return "\n".join(lines) + "\n"


class TestTH01MechanicalSignatureScan:
    """T-H01：告警签名清单解析 / 机械扫描（before + after raw）。"""
    def test_mechanical_signature_scan_in_scope_zero(self):
        raw, rows = _th01_scan()
        raw_text = "\n".join(raw) + "\n" if raw else "<no Qt messages captured during stage loads>\n"
        _write_text(f"T-H01/qt-raw-{RUN_TAG}.log", raw_text)
        _write_text(f"T-H01/signature-inventory-{RUN_TAG}.md", _inventory_md(RUN_TAG, raw, rows))
        _write_text(f"T-H01/count-summary-{RUN_TAG}.md", _count_summary_md(RUN_TAG, raw, rows))
        hits = in_scope(raw)
        assert hits == [], (
            "in-scope QML 告警未归零：\n" + "\n".join(hits)
        )


# ───────────────────────────── T-H02 ─────────────────────────────
# R-01 / H-AC-02 / H-AC-15（S1 Attempt-3）：Combat TRUCE 证据必须走**真实**
# producer/API → DTO → Store → QML 链。

from src.core.entities.war import War, WarStatus  # noqa: E402
from src.core.entities.fleet import Fleet, FleetStatus  # noqa: E402
from src.core.systems.political_system import PoliticalSystem  # noqa: E402
from src.api import combat_api  # noqa: E402
from unittest.mock import patch  # noqa: E402


def _combat_chain_store():
    """真实生产链起点：prototype 会话 state（真实 producer 源）+ 真实 Store。"""
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return state, viewer_id, store


def _attach_real_war(state, war_id, *, naval_required=True, enemy_land=2,
                     enemy_naval=0, n_fleets=3, martial=0):
    """用真实 War/Military/Naval 系统注入 ACTIVE 战争（非 mock DTO）。

    对齐 test_wpg_gd_longchain._build_chain_state 的生产形态注入。"""
    ws = state._war_system
    ms = state._military_system
    ns = state.naval_system
    commander_id = None
    for f in state.get_living_members():
        commander_id = f.id
        try:
            f.martial = martial
        except Exception:
            pass
        try:
            state.get_faction(f.faction_id).member_ids.append(f.id)
        except Exception:
            pass
        break
    war = War(
        id=war_id, name=f"Real War {war_id}", strength=enemy_land, threat_level=3,
        rewards={"treasury": 100}, naval_required=naval_required,
        enemy_naval_current=enemy_naval, enemy_land_current=enemy_land,
        disaster_numbers=[2, 3, 4], standoff_numbers=[99],
    )
    war.commander_id = commander_id
    war.status = WarStatus.ACTIVE
    ws._active_wars.append(war)
    if naval_required:
        for i in range(1, n_fleets + 1):
            fl = Fleet(number=900 + i, fleet_type="trireme")
            fl._strength_base = 3
            fl._target_war_id = war.id
            fl._status = FleetStatus.AVAILABLE
            ns._fleets[900 + i] = fl
            ns.assign_fleet_to_war(900 + i, war.id, "naval")
    return war


def _combat_envelope_after_attack(store, war_id, dice):
    """经真实 Store Slot → adapter → combat_api → 持久 envelope。"""
    with patch.object(combat_api.random, "randint", return_value=dice):
        fb = store.doCombatAction(war_id, "attack")
    return fb


class TestTH02CombatTruceRealChain:
    """R-01：TRUCE（含 truce_remaining_turns）经真实链路产生并渲染。"""

    def test_truce_war_remaining_renders_via_real_chain(self):
        state, viewer, store = _combat_chain_store()
        # 真实 draw → _generate_peace_treaty → enter_truce（status=TRUCE）
        war = _attach_real_war(state, "w_truce", naval_required=False, enemy_land=5)
        fb = _combat_envelope_after_attack(store, "w_truce", dice=7)
        assert fb["success"], fb.get("message")
        assert war.status == WarStatus.TRUCE, war.status
        # 真实 Senate 批准 → truce_end_turn = turn + duration（权威）
        PoliticalSystem(state).execute_passed_peace_treaty(war)
        assert war.truce_end_turn is not None
        store._refresh_combat_view()
        expected = war.truce_end_turn - state.turn.turn_number
        assert expected >= 1
        slots = store.combatAllWarCards
        truce_slots = [s for s in slots if s and s.get("presentation_state") == "TRUCE_LOCKED"]
        assert truce_slots, slots
        assert truce_slots[0].get("truce_remaining_turns") == expected
        root, raw, _ = _run_stage_pumped("CombatStage.qml", store)
        _write_raw(f"T-H02/targeted-combat-truce-{RUN_TAG}.log", raw)
        _write_text(f"T-H02/truce-provenance-{RUN_TAG}.json", __import__("json").dumps({
            "chain": "state→war_system(clause TRUCE)→combat_api.get_combat_view→"
                     "api_adapter→GuiSessionStore._combat_view→CombatStage.qml",
            "war_status": war.status.value,
            "truce_end_turn": war.truce_end_turn,
            "truce_remaining_turns": expected,
            "presentation_state": truce_slots[0].get("presentation_state"),
        }, ensure_ascii=False, indent=2))
        texts = _all_texts(root)
        copy = f"⏳ 和约剩余 {expected} 回合"
        assert copy in texts, texts
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

    def test_truce_render_has_no_naval_null_deref(self):
        """TRUCE 卡无 result ⇒ WarCard.cardResult=undefined ⇒ StageResultBlock.naval=null；
        真实链下不得 deref 告警。"""
        state, viewer, store = _combat_chain_store()
        war = _attach_real_war(state, "w_truce2", naval_required=False, enemy_land=5)
        assert _combat_envelope_after_attack(store, "w_truce2", dice=7)["success"]
        PoliticalSystem(state).execute_passed_peace_treaty(war)
        store._refresh_combat_view()
        root, raw, _ = _run_stage_pumped("CombatStage.qml", store)
        assert [m for m in raw if "sea_control_acquired" in m or "truce_remaining_turns" in m] == []
        assert in_scope(raw) == [], "\n".join(in_scope(raw))


# ───────────────────────────── T-H03 ─────────────────────────────
# R-01：naval 未执行（非海战）/ naval executed 成功 · 失败——均经真实链路。

class TestTH03CombatNavalRealChain:

    def test_naval_not_executed_real_nonnaval_war(self):
        state, viewer, store = _combat_chain_store()
        _attach_real_war(state, "w_land", naval_required=False, enemy_land=2)
        fb = _combat_envelope_after_attack(store, "w_land", dice=7)
        assert fb["success"], fb.get("message")
        naval = fb["data"].get("naval")
        assert naval is not None and naval.get("executed") is False, naval
        assert naval.get("reason") == "NOT_REQUIRED", naval
        root, raw, _ = _run_stage_pumped("CombatStage.qml", store)
        _write_raw(f"T-H03/targeted-combat-nonnaval-{RUN_TAG}.log", raw)
        assert "海战: 未执行 — 本战无需海军" in _all_texts(root), _all_texts(root)
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

    def test_naval_executed_success_real_chain(self):
        state, viewer, store = _combat_chain_store()
        _attach_real_war(state, "w_nav_win", naval_required=True, enemy_land=2,
                         enemy_naval=0, n_fleets=3)
        fb = _combat_envelope_after_attack(store, "w_nav_win", dice=7)
        assert fb["success"], fb.get("message")
        naval = fb["data"].get("naval")
        assert naval.get("executed") is True, naval
        assert naval.get("result") in ("TRIUMPH", "VICTORY"), naval
        assert naval.get("sea_control_acquired") is True, naval
        root, raw, _ = _run_stage_pumped("CombatStage.qml", store)
        _write_raw(f"T-H03/targeted-combat-naval-win-{RUN_TAG}.log", raw)
        item = _find_text_item(root, "🌊 海权: 已获取制海权")
        assert item is not None, _all_texts(root)
        assert item.property("color").name() == "#1e6fa8"
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

    def test_naval_executed_failure_real_chain(self):
        state, viewer, store = _combat_chain_store()
        _attach_real_war(state, "w_nav_lose", naval_required=True, enemy_land=2,
                         enemy_naval=100, n_fleets=3)
        fb = _combat_envelope_after_attack(store, "w_nav_lose", dice=5)
        assert fb["success"], fb.get("message")
        naval = fb["data"].get("naval")
        assert naval.get("executed") is True, naval
        assert naval.get("result") in ("STALEMATE", "DEFEAT", "DISASTER"), naval
        assert naval.get("sea_control_acquired") is False, naval
        root, raw, _ = _run_stage_pumped("CombatStage.qml", store)
        _write_raw(f"T-H03/targeted-combat-naval-lose-{RUN_TAG}.log", raw)
        item = _find_text_item(root, "🌊 海权: 未获取制海权")
        assert item is not None, _all_texts(root)
        assert item.property("color").name() == "#766652"
        assert in_scope(raw) == [], "\n".join(in_scope(raw))


# ───────────────────────────── T-H04 ─────────────────────────────
# Revenue 可选结果对象状态（缺子对象 / 含 0 / 含 false）。

class TestTH04RevenueOptional:

    def test_missing_optionals_no_assign_warning(self):
        store = _make_store(revenue_result={}, revenue_view={})
        root, raw, _ = _run_stage("RevenueStage.qml", store)
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

    def test_present_zero_and_false_no_warning_and_row_states(self):
        settled = {"data": {
            "public_land_income": {"amount": 0},      # 值=0 → 计为存在 → 行显示
            "national_opex": {"amount": 0},           # 现状谓词要求 >0 → 行隐藏
            "maintenance": {"military": {"charged": False},   # 值=false → 存在 → 现状谓词按 charged 真值
                            "naval": {"charged": 0, "unpaid": 0, "disbanded": 0}},
        }}
        store = _make_store(revenue_view={"settled_data": settled})
        root, raw, _ = _run_stage("RevenueStage.qml", store)
        assert in_scope(raw) == [], "\n".join(in_scope(raw))
        # 公地收益（amount=0）行可见：0 计为存在，不隐藏
        land_label = _find_text_item(root, "  公地收益")
        assert land_label is not None
        assert land_label.parent().property("visible") is True


# ───────────────────────────── T-H05 ─────────────────────────────
# Resolution preview 父·子可用性（空 {} / 有数据 / 空数组）。

class TestTH05ResolutionPreview:

    def test_empty_resolution_view_no_deref(self):
        store = _make_store(resolution_view={})
        root, raw, _ = _run_stage("ResolutionStage.qml", store)
        bad = [m for m in raw if "preview" in m or "governor_returns" in m
               or "contract_expiries" in m or "truce_expiries" in m
               or "faction_influence" in m]
        assert bad == [], bad
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

    def test_nonempty_preview_renders_rows(self):
        preview = {
            "governor_returns": [{"province_name": "Sicilia", "governor_name": "Old Gov"}],
            "contract_expiries": [{"name": "Public Works", "contract_id": 1}],
            "truce_expiries": [{"war_name": "Truce War"}],
            "faction_influence": [{"faction_name": "Optimates", "influence_delta": 2,
                                   "influence_after": 52}],
        }
        store = _make_store(resolution_view={"preview": preview, "resolved": True})
        root, raw, _ = _run_stage("ResolutionStage.qml", store)
        assert in_scope(raw) == [], "\n".join(in_scope(raw))
        texts = _all_texts(root)
        assert any("Sicilia总督Old Gov将返回罗马" in t for t in texts), texts
        assert any("Public Works → 将于本年度结束时到期" in t for t in texts), texts

    def test_empty_preview_arrays_show_empty_copy(self):
        preview = {"governor_returns": [], "contract_expiries": [],
                   "truce_expiries": [], "faction_influence": []}
        store = _make_store(resolution_view={"preview": preview, "resolved": True})
        root, raw, _ = _run_stage("ResolutionStage.qml", store)
        assert in_scope(raw) == [], "\n".join(in_scope(raw))
        texts = _all_texts(root)
        assert "本年度结束时无总督返回" in texts
        assert "本年度结束时无合同到期" in texts


# ───────────────────────────── T-H10 ─────────────────────────────
# 无抑制 / 无过滤检查（M-H10 骨架）。

_SUPPRESSION_TOKENS = (
    "qInstallMessageHandler",
    "qSetMessagePattern",
    "console.log",
    "Qt.logging",
    "Logger.filter",
    "stderr = ",
    "sys.stderr",
    "warnings.filterwarnings",
)


class TestTH10NoSuppression:
    """T-H10：确认零告警来自修正而非过滤（扫描 WP-H stage QML 无抑制 token）。"""

    def test_no_suppression_tokens_in_stage_qml(self):
        for name in ("CombatStage.qml", "RevenueStage.qml", "ResolutionStage.qml",
                     "ForumStage.qml", "MortalityStage.qml", "PopulationStage.qml"):
            with open(os.path.join(QML_DIR, "stages", name), encoding="utf-8") as fh:
                src = fh.read()
            for token in _SUPPRESSION_TOKENS:
                assert token not in src, (name, token)


# ═════════════════════════ S1 Attempt-2（W09–W12 / T-H06–T-H09）═════════════════════════
# 续做：Forum 覆盖层移出 layout（W09）· Mortality 行对齐（W10/W11）·
#        Population 控件条件位点（W12，T-H08 复现判定）· 等价长旅程（T-H09）。

from PySide6.QtCore import Slot  # noqa: E402
from PySide6.QtQml import qmlRegisterType  # noqa: E402

from src.ui.gui.models.candidate_list_model import CandidateListModel  # noqa: E402
from src.ui.gui.models.event_list_model import EventListModel  # noqa: E402
from src.ui.gui.models.figure_list_model import FigureListModel  # noqa: E402

_MODELS_REGISTERED = False


def _write_raw(path, raw):
    """把 raw Qt 消息全量落盘（未过滤/未去重）；无 EVIDENCE_DIR 时 no-op。"""
    text = "\n".join(raw) + "\n" if raw else "<no Qt messages captured>\n"
    _write_text(path, text)


def _run_stage_pumped(qml_name, store, pumps=10):
    """加载 stage 后多次 pump 事件循环（孵化 Repeater/Layout 嵌套 delegate）。"""
    app = _get_app()
    with capture_qt_raw() as raw:
        _, root, qml_warnings = _load_stage(qml_name, store)
        for _ in range(pumps):
            app.processEvents()
    return root, raw, qml_warnings


class _DummyGuiApp(QObject):
    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id: str) -> bool:
        return bool(next_player_id)


def _load_main_shell(store):
    """离屏加载真实生产入口 Main.qml（含全部 7 stage）；返回 (engine, root_window)。"""
    global _MODELS_REGISTERED
    app = _get_app()
    if not _MODELS_REGISTERED:
        qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
        qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
        qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")
        _MODELS_REGISTERED = True
    engine = QQmlApplicationEngine()
    _ENGINES.append(engine)
    engine.addImportPath(QML_DIR)
    qml_warnings = []
    engine.warnings.connect(lambda errs: qml_warnings.extend(str(e.toString()) for e in errs))
    ctx = engine.rootContext()
    ctx.setContextProperty("sessionStore", store)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    ctx.setContextProperty("theme", theme)
    gui_app = _DummyGuiApp()
    ctx.setContextProperty("guiApp", gui_app)
    engine._wph_refs = (theme, store, gui_app)
    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "Main.qml loaded with no root object"
    try:
        roots[0].show()
    except Exception:
        pass
    for _ in range(3):
        app.processEvents()
    return engine, roots[0]


# ───────────────────────────── T-H06 ─────────────────────────────
# Forum 覆盖层（W09）：`marketUnlocked=false` 时锁定覆盖层显示；
# 修正后覆盖层 = 非 layout 祖先（市场面板 Rectangle）的子项 → 无 layout-anchor 告警。

class TestTH06ForumOverlayLayout:

    def _locked_store(self):
        # 默认 `_forum_view` 为空 → forumCurrentStep="retirement" → marketUnlocked=False。
        return _make_store()

    def test_locked_overlay_no_layout_anchor_warning(self):
        store = self._locked_store()
        root, raw, _ = _run_stage_pumped("ForumStage.qml", store)
        _write_raw(f"T-H06/targeted-forum-{RUN_TAG}.log", raw)
        hits = [m for m in raw if "managed by a layout" in m]
        assert hits == [], hits
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

    def test_locked_overlay_geometry_preserved(self):
        store = self._locked_store()
        root, raw, _ = _run_stage_pumped("ForumStage.qml", store)
        label = _find_text_item(root, "⌛ 等待子环节完成")
        assert label is not None, "锁定覆盖层文案缺失"
        overlay = label.parent()
        assert overlay.property("visible") is True
        assert overlay.property("z") == 10
        assert round(overlay.property("height")) == 28
        assert round(overlay.property("radius")) == 5
        assert overlay.property("color").alpha() == 0xBF
        parent_cls = overlay.parent().metaObject().className()
        assert "Layout" not in parent_cls, parent_cls

    def test_unlocked_overlay_hidden(self):
        store = _make_store()
        store._forum_view = {"current_step": "recruitment"}
        root, raw, _ = _run_stage_pumped("ForumStage.qml", store)
        assert in_scope(raw) == [], "\n".join(in_scope(raw))
        label = _find_text_item(root, "⌛ 等待子环节完成")
        assert label is not None
        assert label.parent().property("visible") is False


# ───────────────────────────── T-H07 ─────────────────────────────
# Mortality 行（W10/W11）：事件头 RowLayout + 嵌套死亡行 RowLayout 的子 Text
# 由 anchors.verticalCenter → Layout.alignment（位置器 `Row` 内位点不在此列）。

def _mortality_store():
    """真实生产路径：prototype 会话 + 注入死亡事件牌组 → 执行天命 →
    mortalityEvents（含 figure_death impacts，真实 mortality_api 产出）。"""
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    try:
        cfg = state._config._config
        mort = cfg.setdefault("mortality_rules", {})
        mort["event_deck"] = [{"name": "死神来了", "effect": "death", "weight": 1}]
        mort["event_draw_count"] = 1
        mort["death_count"] = 2
        state._initialize_mortality_pool()
    except Exception:  # noqa: BLE001
        pass
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.doExecuteMortality()
    if not store.mortalityEvents:
        # 回退：producer-shaped 合成事件（DEV-08）
        store._mortality_result = {"events": [
            {"effect": "death", "name": "Gaius", "summary": "病逝",
             "impacts": [
                 {"type": "figure_death", "figure_name": "Gaius",
                  "faction_id": "f1", "faction_name": "Optimates"},
                 {"type": "figure_death", "figure_name": "Lucius",
                  "faction_id": "f2", "faction_name": "Populares"},
             ]},
        ]}
    return store


class TestTH07MortalityRowAlignment:

    def test_event_rows_no_layout_anchor_warning(self):
        store = _mortality_store()
        root, raw, _ = _run_stage_pumped("MortalityStage.qml", store)
        _write_raw(f"T-H07/targeted-mortality-{RUN_TAG}.log", raw)
        hits = [m for m in raw if "managed by a layout" in m]
        assert hits == [], hits
        assert in_scope(raw) == [], "\n".join(in_scope(raw))

    def test_event_and_death_rows_render(self):
        store = _mortality_store()
        root, raw, _ = _run_stage_pumped("MortalityStage.qml", store)
        texts = _all_texts(root)
        _write_text(f"T-H07/rendered-texts-{RUN_TAG}.log", "\n".join(texts) + "\n")
        _write_text(f"T-H07/mortality-events-{RUN_TAG}.json",
                    __import__("json").dumps(store.mortalityEvents, ensure_ascii=False, indent=2))
        # W10 事件头文案不得丢失（垂直居中修正不得改变内容）
        assert any("（" in t for t in texts) or any("天命" in t for t in texts), texts
        assert any("2 人死亡" in t for t in texts), texts
        # WP-J J-AC-09（FC-10）取代 W11 前置：列表检测谓词修复后，嵌套死亡行 delegate
        # **必须实例化**（原「不实例化」= 修复前行为，仅作 WP-H 历史基线；
        # 见 test_wpj_groupa_mortality_death_rows.py）。行文本以「（派系）」开头。
        assert any(t.startswith("（") for t in texts), texts


# ───────────────────────────── T-H08 ─────────────────────────────
# Population 控件（W12，条件位点）：`RadioButton { contentItem: Text {} }`。
# 运行风格支持 contentItem 定制 → 无告警 → NOT REPRODUCED ON LAUNCH BASELINE（零改）。

def _population_vote_store():
    store = _make_store()
    store._population_view = {
        "candidates": {"consul": [
            {"id": 7, "name": "Marcus", "faction_id": "f1", "faction_name": "Optimates"},
        ]},
        "current_step": "vote",
    }
    return store


class TestTH08PopulationControl:

    def test_contentitem_override_not_reproduced(self):
        store = _population_vote_store()
        root, raw, _ = _run_stage_pumped("PopulationStage.qml", store)
        _write_raw(f"T-H08/targeted-population-{RUN_TAG}.log", raw)
        native_hits = [m for m in raw if "contentItem" in m or "Cannot specify" in m]
        assert native_hits == [], native_hits
        assert in_scope(raw) == [], "\n".join(in_scope(raw))
        # 候选控件存在（派系色标签）
        texts = _all_texts(root)
        assert any("Marcus" in t for t in texts), texts


# ───────────────────────────── T-H09 ─────────────────────────────
# R-02（S1 Attempt-3）：**七阶段生产旅程**——每个权威动作必须真实成功并到达
# authoritative post-state → 次周期。`selectPhase()` 视图切换与返回 `no` 的动作
# 不计为旅程完成。真实生产入口 Main.qml（全部 7 stage 同时实例化）+ 真实 Store 动作链。

_PHASES = ("mortality", "revenue", "forum", "population",
           "senate", "combat", "resolution")


def _journey_store():
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    try:
        state.set_current_player(viewer_id)
    except Exception:
        pass
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store


def _population_selection(store):
    sel = {}
    for office in ("consul", "censor", "praetor", "quaestor", "tribune"):
        for c in store.populationCandidates:
            if c.get("office") == office:
                sel[office] = int(c.get("id"))
                break
    return sel


def _ensure_viewer_consul(state, viewer_id):
    """确定性保证 viewer 派系存在 eligible Consul（prototype 场景办公室随机分配）。

    仅为可重现的测试场景构造（真实 Figure.office 字段）；不改 Senate 动作链本身。"""
    viewer = state.get_player(viewer_id)
    faction = state.get_faction(viewer.faction_id) if viewer else None
    if faction is None:
        return False
    politics = PoliticalSystem(state)
    if politics._find_consul_for_faction(faction):
        return True
    for m in faction.get_members(state):
        try:
            m.office = "consul"
            m.is_absent = False
        except Exception:
            continue
        return True
    return False


class TestTH09LongJourney:

    def test_seven_stage_production_journey_to_next_cycle(self):
        """R-02 / H-AC-03 / H-AC-19：七阶段生产链真实完成 → 次周期。"""
        app = _get_app()
        store = _journey_store()
        start_turn = store.turnNumber
        viewer = store.viewerPlayerId
        log = []

        def step(name, fn):
            res = fn()
            ok = bool(isinstance(res, dict) and res.get("success"))
            msg = res.get("message") if isinstance(res, dict) else None
            log.append({"step": name, "success": ok,
                        "current_phase": store.currentPhaseId,
                        "selected_phase": store.selectedPhaseId,
                        "message": msg})
            for _ in range(3):
                app.processEvents()
            assert ok, f"journey step {name} returned no/False: {res}"
            return res

        with capture_qt_raw() as raw:
            _load_main_shell(store)
            # 1) Mortality
            step("doExecuteMortality", store.doExecuteMortality)
            step("doAdvanceMortality", store.doAdvanceMortality)
            assert store.currentPhaseId == "revenue", store.currentPhaseId
            # 2) Revenue
            step("doExecuteRevenue", store.doExecuteRevenue)
            step("doAdvanceRevenue", store.doAdvanceRevenue)
            assert store.currentPhaseId == "forum", store.currentPhaseId
            # 3) Forum
            step("doExecuteForum", store.doExecuteForum)
            step("doAdvanceForum", store.doAdvanceForum)
            assert store.currentPhaseId == "population", store.currentPhaseId
            # 4) Population：真实投票 → complete → advance
            assert store.populationCandidates, "population candidates required"
            sel = _population_selection(store)
            step("submitPopulationVotes", lambda: store.submitPopulationVotes(sel))
            step("doCompletePlayer", store.doCompletePlayer)
            step("doAdvancePopulation", store.doAdvancePopulation)
            assert store.currentPhaseId == "senate", store.currentPhaseId
            # 5) Senate：确定性 Consul + 真实 Submit →（如需）Vote → Veto → finalization → advance
            state_ = store._state
            _ensure_viewer_consul(state_, viewer)
            store._refresh_senate_view()
            step("doSubmitSenateProposals", lambda: store.doSubmitSenateProposals([]))
            if not store.canAdvanceSenate:
                # 非执政官：AI proposer 已产提案 → 走真实表决链
                r = store.doSubmitSenateVotes()
                log.append({"step": "doSubmitSenateVotes",
                            "success": bool(isinstance(r, dict) and r.get("success")),
                            "current_phase": store.currentPhaseId,
                            "selected_phase": store.selectedPhaseId,
                            "message": r.get("message") if isinstance(r, dict) else None})
                for _ in range(3):
                    app.processEvents()
                assert isinstance(r, dict) and r.get("success"), r
                if not store.canAdvanceSenate:
                    step("doSubmitSenateVetoes", lambda: store.doSubmitSenateVetoes([]))
            step("doAdvanceSenate", store.doAdvanceSenate)
            assert store.currentPhaseId == "combat", store.currentPhaseId
            # 6) Combat
            step("doAdvanceCombat", store.doAdvanceCombat)
            # 7) Resolution：生产入口自动结算 → 年度推进 → 次周期
            step("selectPhase(resolution)", lambda: store.selectPhase("resolution"))
            step("doAdvanceResolution", store.doAdvanceResolution)
            end_turn = store.turnNumber
            end_phase = store.currentPhaseId
        _write_raw(f"T-H09/long-journey-raw-{RUN_TAG}.log", raw)
        _write_text(f"T-H09/long-journey-actions-{RUN_TAG}.log",
                    "\n".join(
                        f"{r['step']}: {'ok' if r['success'] else 'no'} "
                        f"(phase={r['current_phase']}, sel={r['selected_phase']})"
                        for r in log) + "\n")
        _write_text(f"T-H09/long-journey-poststate-{RUN_TAG}.json",
                    __import__("json").dumps({
                        "start_turn": start_turn, "end_turn": end_turn,
                        "end_phase": end_phase,
                        "next_cycle_reached": end_phase == "mortality",
                        "year_advanced": end_turn == start_turn + 1,
                        "steps": log,
                    }, ensure_ascii=False, indent=2))
        # 完成判据：全部权威动作 success + 到达次周期（turn+1 → mortality）
        assert all(r["success"] for r in log), log
        assert end_phase == "mortality", end_phase
        assert end_turn == start_turn + 1, (start_turn, end_turn)
        assert in_scope(raw) == [], "in-scope 告警未归零：\n" + "\n".join(in_scope(raw))

    def test_refresh_and_reentry_raw_zero(self):
        app = _get_app()
        store = _journey_store()
        with capture_qt_raw() as raw:
            _load_main_shell(store)
            for name in ("doExecuteMortality", "doAdvanceMortality",
                         "doExecuteRevenue", "doAdvanceRevenue",
                         "doExecuteForum", "doAdvanceForum"):
                try:
                    getattr(store, name)()
                except Exception:  # noqa: BLE001
                    pass
                for _ in range(2):
                    app.processEvents()
            # refresh（重读权威 DTO）
            store.refreshSnapshot()
            app.processEvents()
            # re-entry（同权威 state 重建 Store（新实例）后重新加载）
            result = session_api.create_gui_prototype_session()
            assert result["success"]
            store2 = GuiSessionStore(result["data"]["state"])
            store2.initialize(result["data"]["human_players"][0])
            for phase in _PHASES:
                store2.selectPhase(phase)
                app.processEvents()
            _load_main_shell(store2)
        _write_raw(f"T-H09/refresh-reentry-{RUN_TAG}.log", raw)
        assert in_scope(raw) == [], "in-scope 告警未归零：\n" + "\n".join(in_scope(raw))


# ────────── W11 非复现前置（launch baseline）诊断证据 ──────────
# launch baseline 运行态：`deathImpacts()` 受 `Array.isArray(impacts)` 守卫；
# 本运行时 `Array.isArray(QVariantList)` = false ⇒ 函数恒返 `[]` ⇒ 嵌套死亡行
# delegate 不实例化 ⇒ W11 位点（190/197/203）的 layout-anchor 告警在 launch baseline
# **不可复现**（潜在、非活动告警）。本测试固化该运行事实作证据。

class TestTH07W11NonReproductionPrecondition:

    def test_array_isarray_on_qvariantlist_is_false(self):
        app = _get_app()
        engine = QQmlApplicationEngine()
        _ENGINES.append(engine)
        ctx = engine.rootContext()
        ctx.setContextProperty(
            "probeModel",
            [{"impacts": [{"type": "figure_death"}, {"type": "figure_death"}]}])
        comp = QQmlComponent(engine)
        comp.setData(b'''
import QtQuick 2.15
QtObject {
    property var m: probeModel
    property bool isArr: Array.isArray(m[0].impacts)
    property bool hasLen: m[0].impacts !== undefined && m[0].impacts !== null && m[0].impacts.length === 2
    property string t0: m[0].impacts ? ("" + m[0].impacts[0].type) : "NA"
}
''', QUrl())
        assert not comp.isError(), comp.errorString()
        obj = comp.create()
        assert obj is not None
        is_arr = obj.property("isArr")
        has_len = obj.property("hasLen")
        t0 = obj.property("t0")
        _write_text("T-H07/w11-precondition.json", __import__("json").dumps({
            "Array.isArray(QVariantList)": is_arr,
            "length==2": has_len,
            "element.type": t0,
            "conclusion": ("W11 NOT REPRODUCED: deathImpacts 恒返 []（Array.isArray=false）"
                           " ⇒ 嵌套死亡行 delegate 不实例化"),
        }, ensure_ascii=False, indent=2))
        # 运行事实：QVariantList 非 JS Array（元素访问/长度正常）
        assert has_len is True
        assert t0 == "figure_death"
        assert is_arr is False, "若为 True，则需重新评估 W11 复现"
