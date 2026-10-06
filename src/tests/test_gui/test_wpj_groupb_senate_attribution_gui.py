# src/tests/test_gui/test_wpj_groupb_senate_attribution_gui.py
"""WP-J Group B-2 (J-AC-02) — SenateStage 保民官否决归属文案绑权威 veto_control_mode。

RENDER + 静态绑定断言（FC-B10/B12/B13）：
- tribuneActionText() 输入 = sessionStore.senateVetoControlMode（权威 actor/source）
- 不再由 canManuallySelectSenateVeto（可用性位）派生（本缺陷根因）
- HUMAN→「判定否决 → 公示结果」/ AI→「AI判定否决 → 公示结果」/ NONE→「无保民官，跳过否决」
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import Property, Signal  # noqa: E402

from src.tests.test_gui.test_senate_r1_gui import (  # noqa: E402
    FakeSenateStore,
    _load_senate_stage,
    _all_items,
)
from src.tests.test_gui.test_wpcr1_placement_accordion import _real_senate_options  # noqa: E402

SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")

HUMAN_COPY = "判定否决 → 公示结果"
AI_COPY = "AI判定否决 → 公示结果"
NONE_COPY = "无保民官，跳过否决"


class _FakeStoreWithVetoMode(FakeSenateStore):
    """FakeSenateStore + 权威 veto actor/source 只读属性（FC-B09）。"""

    vetoModeChanged = Signal()

    def __init__(self, options, veto_mode, parent=None):
        super().__init__(options, parent=parent)
        self._veto_mode = veto_mode

    @Property(str, notify=vetoModeChanged)
    def senateVetoControlMode(self):
        return self._veto_mode


def _find_text(root, text):
    for item in _all_items(root):
        if item.property("text") == text:
            return item
    return None


# ---------------------------------------------------------------------------
# 静态绑定断言（源码级：改绑权威 mode；不派生自可用性位）
# ---------------------------------------------------------------------------

def test_source_tribune_action_text_binds_authoritative_mode():
    src = open(SENATE_QML, encoding="utf-8").read()
    start = src.index("function tribuneActionText()")
    end = src.index("}", src.index("return \"AI", start))
    block = src[start:end]
    code = "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("//"))
    assert "sessionStore.senateVetoControlMode" in code, \
        "归属文案必须绑定权威 veto_control_mode（FC-B10）"
    assert "canManuallySelectSenateVeto" not in code, \
        "归属文案不得派生自可用性位（本缺陷根因；FC-B12）"
    assert "current_step" not in code, "不得由 current_step 推断 actor（FC-B12）"


# ---------------------------------------------------------------------------
# 三分支渲染（离线帧）—— 单一 engine 复用（多引擎加载 segfault 保护）：
# 切换 mode 属性 + emit senateViewChanged → QML 绑定重估（真实 binding，非直置）。
# ---------------------------------------------------------------------------

_ENGINE_KEEPALIVE = []
_LOADED = {}


def _get_stage():
    if "root" not in _LOADED:
        store = _FakeStoreWithVetoMode(_real_senate_options(), "HUMAN")
        engine, root, _warnings = _load_senate_stage(store)
        _ENGINE_KEEPALIVE.append(engine)
        _LOADED.update(store=store, root=root)
    return _LOADED["store"], _LOADED["root"]


def _set_mode(mode):
    from src.tests.test_gui.test_senate_r1_gui import _get_app
    store, root = _get_stage()
    store._veto_mode = mode
    store.vetoModeChanged.emit()
    _get_app().processEvents()
    return root


def test_human_attribution_copy():
    root = _set_mode("HUMAN")
    assert _find_text(root, HUMAN_COPY) is not None, "HUMAN → 判定否决 → 公示结果"
    assert _find_text(root, "AI" + HUMAN_COPY) is None, "HUMAN 不得塌「AI判定」"


def test_ai_attribution_copy():
    root = _set_mode("AI")
    assert _find_text(root, AI_COPY) is not None, "AI → AI判定否决 → 公示结果"
    assert _find_text(root, HUMAN_COPY) is None


def test_none_attribution_copy():
    root = _set_mode("NONE")
    assert _find_text(root, NONE_COPY) is not None, "NONE → 无保民官，跳过否决（不空白）"
    assert _find_text(root, HUMAN_COPY) is None
    assert _find_text(root, AI_COPY) is None


def test_human_copy_persists_independent_of_availability_bit():
    """HUMAN 文案不依赖可用性位：即 canManuallySelectSenateVeto=False，仍为人类文案。"""
    store, _root = _get_stage()
    assert store.canManuallySelectSenateVeto is False  # FakeSenateStore 默认 False
    root = _set_mode("HUMAN")
    assert _find_text(root, HUMAN_COPY) is not None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
