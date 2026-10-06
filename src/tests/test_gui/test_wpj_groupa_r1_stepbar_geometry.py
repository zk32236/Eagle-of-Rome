# src/tests/test_gui/test_wpj_groupa_r1_stepbar_geometry.py
"""WP-J Group-A R1 / J-AC-12 (FC-14) — 步骤条节点条几何（内容紧凑左对齐 + 固定 gapStep）。

层级：DATA（几何谓词 + 视口无关）。

契约（冻结设计 R1 §4 FC-14 / §5.1）：
- 唯一权威 = Product GUI Layout Contract Phase1 v3.25.1 §4.2「StageInstructionSlot (Step Bar): Gap 7px」。
- `stepRow` 仅锚 left + verticalCenter（**去 right 锚** → 禁拉伸铺满）；节点间 = `gapStep = 7px`。
- 几何谓词：相邻节点 `node[i+1].x − (node[i].x + node[i].width) == 7`。
- 视口无关：`gapStep(1280×720) == gapStep(1440×900) == 7`（Owner R-1 几何谓词）。

RED（实现前）：`stepRow` 锚 left+right 且 spacing=4 → 相邻间距 ≠ 7（或被拉伸）→ 失败。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import shiboken6  # noqa: E402
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
STEPBAR_QML = os.path.join(QML_DIR, "components", "StepBar.qml")

GAPSTEP = 7

# 代表性 slot 内容宽（视口 1280/1440 减去 StageDesktop 侧列后的近似），仅用于验证「视口无关」。
_SLOT_WIDTHS = (1100, 1260)


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _create_stepbar(steps, width):
    app = _get_app()
    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    engine.rootContext().setContextProperty("theme", theme)
    engine._test_refs = theme

    comp = QQmlComponent(engine)
    comp.loadUrl(QUrl.fromLocalFile(STEPBAR_QML))
    assert not comp.isError(), comp.errorString()
    bar = comp.createWithInitialProperties({"steps": steps})
    assert bar is not None, comp.errorString()
    bar.setWidth(width)
    bar.setHeight(50)
    app.processEvents()
    app.processEvents()
    return engine, bar


def _qitem(obj):
    if obj is None:
        return None
    try:
        ptr = shiboken6.Shiboken.getCppPointer(obj)[0]
        return shiboken6.Shiboken.wrapInstance(ptr, QQuickItem)
    except Exception:
        return None


def _all_items(root):
    pending = [_qitem(root)]
    while pending:
        item = pending.pop()
        if item is None:
            continue
        yield item
        pending.extend(item.childItems())


def _nodes(bar):
    nodes = []
    for item in _all_items(bar):
        try:
            if item.objectName() == "stepNode":
                nodes.append(item)
        except Exception:
            pass
    # 保持视觉顺序（RowLayout 位置序）
    nodes.sort(key=lambda it: float(it.x()))
    return nodes


def _gaps(nodes):
    return [
        float(nodes[i + 1].x()) - (float(nodes[i].x()) + float(nodes[i].width()))
        for i in range(len(nodes) - 1)
    ]


_FORUM_STEPS = [
    {"key": "retirement", "label": "解雇成员", "state": "current"},
    {"key": "market", "label": "市场（招募·竞标·认购·凯旋）", "state": "todo"},
]
_SENATE_STEPS = [
    {"key": "proposal", "label": "执政官提案", "state": "current"},
    {"key": "senate_vote", "label": "元老表决", "state": "todo"},
    {"key": "tribune_veto", "label": "保民官否决", "state": "todo"},
]


def test_stepbar_gap_is_fixed_gapstep_two_nodes():
    """FC-14：2 节点（Forum 型）相邻间距 == gapStep(7)。"""
    _engine, bar = _create_stepbar(_FORUM_STEPS, 1260)
    nodes = _nodes(bar)
    assert len(nodes) == 2, f"应渲染 2 个步骤节点，实际 {len(nodes)}"
    gaps = _gaps(nodes)
    assert len(gaps) == 1
    assert abs(gaps[0] - GAPSTEP) <= 0.75, f"节点间距应 == {GAPSTEP}，实际 {gaps}"


def test_stepbar_gap_is_fixed_gapstep_three_nodes():
    """FC-14：3 节点（Senate 型）相邻间距均 == gapStep(7)。"""
    _engine, bar = _create_stepbar(_SENATE_STEPS, 1260)
    nodes = _nodes(bar)
    assert len(nodes) == 3
    for g in _gaps(nodes):
        assert abs(g - GAPSTEP) <= 0.75, f"节点间距应 == {GAPSTEP}，实际 {_gaps(nodes)}"


def test_stepbar_compact_left_aligned():
    """FC-14：内容紧凑左对齐（首节点 x≈0；内容右缘 ≤ 容器宽 → 余量为右侧留白）。"""
    _engine, bar = _create_stepbar(_SENATE_STEPS, 1260)
    nodes = _nodes(bar)
    assert float(nodes[0].x()) <= 0.75, "首节点应左对齐"
    right_edge = float(nodes[-1].x()) + float(nodes[-1].width())
    assert right_edge <= 1260 + 0.5, "内容不得溢出容器"


def test_stepbar_gapstep_viewport_independent():
    """FC-14 / Owner R-1：gapStep 视口无关 —— 1280 型 == 1440 型 == 7。"""
    measured = {}
    for width in _SLOT_WIDTHS:
        _engine, bar = _create_stepbar(_SENATE_STEPS, width)
        nodes = _nodes(bar)
        gaps = _gaps(nodes)
        assert gaps, "无相邻节点"
        measured[width] = gaps
        for g in gaps:
            assert abs(g - GAPSTEP) <= 0.75, f"@{width}: 间距应 == {GAPSTEP}，实际 {gaps}"
    # 两视口逐间距相等（不随宽度变化）
    a = measured[_SLOT_WIDTHS[0]]
    b = measured[_SLOT_WIDTHS[1]]
    assert len(a) == len(b)
    for ga, gb in zip(a, b):
        assert abs(ga - gb) <= 0.01, f"间距随视口变化：{a} vs {b}"


def test_stepbar_single_node_no_leading_gap():
    """FC-14 / checklist #3：单节点（Mortality 型）无前导空隙，左对齐。"""
    _engine, bar = _create_stepbar(
        [{"key": "execute", "label": "执行天命", "state": "current"}], 1260
    )
    nodes = _nodes(bar)
    assert len(nodes) == 1
    assert float(nodes[0].x()) <= 0.75
