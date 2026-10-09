# src/tests/test_gui/test_wpj_groupc_population_table.py
"""WP-J Group C-1 (J-AC-05a) — 候选信息表只渲染 featured + 压缩 + 去内嵌滚动。

- FC-C03：`candidateTable` 每 office 恰渲染 1 行 = featured；投票列表仍列全部（不改）。
- FC-C04：featured 行强制字段齐（此处验证候选名渲染存在）。
- FC-C05：表高确定性压缩（< 206）；**无内嵌 Flickable/ScrollBar**。
- FC-C06：归还高度给 ①庆典/②投票子环节区；完成按钮固定于滚动区之外。

No-Test-Assisted-Transition：featured 经真实 `create_gui_prototype_session` → 真实 Store 到达。
"""
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402
import shiboken6  # noqa: E402
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402

from src.api import session_api  # noqa: E402
from src.ui.gui.session_store import GuiSessionStore  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
POP_QML = os.path.join(QML_DIR, "stages", "PopulationStage.qml")
OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")


@pytest.fixture(autouse=True)
def _preserve_global_random_state():
    saved = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved)


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


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


def _find_obj(root, object_name):
    for item in _all_items(root):
        if item.objectName() == object_name:
            return item
    return None


def _texts_under(item):
    return [it.property("text") for it in _all_items(item)
            if "Text" in it.metaObject().className() and it.property("text")]


def _ancestor_class_names(item):
    names = []
    cur = item
    while cur is not None:
        try:
            names.append(cur.metaObject().className())
        except Exception:
            pass
        cur = cur.parentItem()
    return names


def _load_population(width=1440, height=900):
    app = _get_app()
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]
    state.set_current_player(viewer)
    store = GuiSessionStore(state)
    store.initialize(viewer)
    store.selectPhase("population")

    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)
    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("theme", theme)
    engine._test_refs = (store, theme)
    engine.load(QUrl.fromLocalFile(POP_QML))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "PopulationStage loaded with no root object"
    root = roots[0]
    root.setWidth(width)
    root.setHeight(height)
    app.processEvents()
    return engine, root, store


# ---------------------------------------------------------------------------
# 静态绑定断言：表消费 featured + 去内嵌滚动
# ---------------------------------------------------------------------------

def test_source_table_consumes_featured_and_drops_inner_scroll():
    src = open(POP_QML, encoding="utf-8").read()
    assert "function featuredRows(" in src, "缺 featured 行投影函数（FC-C03）"
    assert "is_featured" in src, "候选表须消费 producer is_featured（FC-C03）"
    assert "contentHeight: candidateRows.implicitHeight" not in src, \
        "候选表内嵌 Flickable/滚动须移除（FC-C05）"


# ---------------------------------------------------------------------------
# 渲染层：每 office 恰 1 featured 行；无内嵌 Flickable；表高 < 206
# ---------------------------------------------------------------------------

def test_candidate_table_renders_only_featured_and_compressed():
    _engine, root, store = _load_population()
    table = _find_obj(root, "populationCandidateTable")
    assert table is not None, "未找到候选信息表"
    # FC-C05：无内嵌 Flickable/ScrollBar
    offenders = [it.metaObject().className() for it in _all_items(table)
                 if "Flickable" in it.metaObject().className()
                 or "ScrollBar" in it.metaObject().className()]
    assert offenders == [], f"FC-C05 违规：候选表内仍有滚动件 {offenders}"

    # FC-C05：确定性压缩（< 206）
    assert table.height() < 206, f"表高须压缩自 206，实际 {table.height()}"
    assert table.height() > 0

    # FC-C03：每 office 恰 1 行 featured（候选名只出现 1 次于信息表）
    flat = store.populationCandidates
    table_texts = _texts_under(table)
    for office in OFFICES:
        rows = [c for c in flat if c["office"] == office]
        featured = [c for c in rows if c.get("is_featured")]
        if not rows:
            assert "无候选人（空缺）" in table_texts, f"{office}: vacant 占位缺失"
            continue
        assert len(featured) == 1, f"{office}: producer featured 恰 1"
        name = featured[0]["name"]
        assert any(name in t for t in table_texts), f"{office}: featured 候选名须显示"
        # 非 featured 候选不得在信息表出现（候选名 Text 为 RichText HTML，按子串匹配）
        for c in rows:
            if not c.get("is_featured"):
                assert not any(c["name"] in t for t in table_texts), \
                    f"{office}: 非 featured 候选不得显示 {c['name']}"


def test_vote_panel_still_lists_all_candidates():
    """FC-C03：投票选择列表仍列全部合法候选（信息表变化不影响投票面）。"""
    _engine, root, store = _load_population()
    vote_panel = _find_obj(root, "populationVotePanel")
    assert vote_panel is not None, "未找到投票面板"
    vote_texts = _texts_under(vote_panel)
    flat = store.populationCandidates
    for office in OFFICES:
        rows = [c for c in flat if c["office"] == office]
        for c in rows:
            # RadioButton text = "<name> (<faction_short>)"；按名字子串匹配
            assert any(c["name"] in t for t in vote_texts), \
                f"{office}: 投票列表须包含候选 {c['name']}"


def test_subphase_panels_absorb_freed_height():
    """FC-C06：候选表归还高度给 ①②子环节区（panel 内容可视区增高）。"""
    _engine, root, store = _load_population()
    table = _find_obj(root, "populationCandidateTable")
    campaign = _find_obj(root, "populationCampaignFlickable")
    vote = _find_obj(root, "populationVoteFlickable")
    assert campaign is not None and vote is not None, "缺子环节内容 Flickable"
    freed = 206 - table.height()
    assert freed >= 20, f"候选表须实质压缩以归还高度（freed={freed}）"
    assert campaign.height() > 0 and vote.height() > 0
    # 两面板 Rectangle 承接 RowLayout(fillHeight) 归还的高度：等分且填满 RowLayout
    campaign_panel = campaign.parentItem().parentItem()
    vote_panel = vote.parentItem().parentItem()
    row_layout = campaign_panel.parentItem()
    assert abs(campaign_panel.height() - vote_panel.height()) <= 2, "①②面板等分（fillHeight）"
    assert abs(row_layout.height() - campaign_panel.height()) <= 2, \
        "面板须 fillHeight 承接归还高度"


def test_completion_buttons_outside_scroll():
    _engine, root, _store = _load_population()
    for label in ("⬻️ 完成庆典", "⬻️ 完成投票"):
        found = None
        for it in _all_items(root):
            if "Text" in it.metaObject().className() and it.property("text") == label:
                found = it
                break
        assert found is not None, f"未找到完成按钮文案 {label!r}"
        names = _ancestor_class_names(found)
        offenders = [n for n in names if "ScrollView" in n or "Flickable" in n]
        assert offenders == [], f"{label!r} 位于滚动容器内（UI-P09(c)）: {offenders}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
