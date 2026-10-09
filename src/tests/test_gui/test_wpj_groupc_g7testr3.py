# src/tests/test_gui/test_wpj_groupc_g7testr3.py
"""WP-J Group C G7 Test R3 Delta（FC-C28/FC-C29/FC-C30，方案甲）— **WITHDRAWN 守护断言**（R4 联动）。

> **R4 联动（**非** Test Amendment）：** Owner 2026-10-09 G7-Test-R4 Q2 裁定**放弃方案甲**
> （①②③ + 战争卡统一自绘 USS 勾选框）⇒ `FC-C28` / `FC-C29` / `FC-C30` = **WITHDRAWN**
> （受 `FC-C31` 取代；见 `02-sa-design/GroupC/WP-J-GroupC-G7TestR4Delta-v1.9-2026-10-09.md` §2.1）。
>
> 本文件原为 FC-C28/C29/C30 的源码级**正向**断言（要求四面存在自绘 `indicator` 与自绘勾/叉）。
> R4 后翻转为**反向守护**：断言 R3 自绘方案已**彻底移除**、不得回归。R4 正向契约断言
> （FC-C31/FC-C32）见 `test_wpj_groupc_g7testr4.py`；渲染层可比判据见
> `test_wpj_groupc_render_evidence.py`。

本文件 = R3 自绘方案的**撤回守护**（防回归）。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SENATE_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "stages", "SenateStage.qml")
WAR_QML = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "components", "WarProposalCard.qml")

# R3 方案甲（FC-C28/C29）引入物：自绘 USS 框 + 自绘勾/叉子图元（R4 后须全部归零）
USS_BORDER = 'border.color: "#C8A870"'


def _senate():
    return open(SENATE_QML, encoding="utf-8").read()


def _war():
    return open(WAR_QML, encoding="utf-8").read()


def test_r3_selfdrawn_indicator_fully_withdrawn():
    """FC-C28/C29 WITHDRAWN：SenateStage 与 WarProposalCard 均**不得**残留自定义 `indicator`。"""
    for name, src in (("SenateStage", _senate()), ("WarProposalCard", _war())):
        assert "indicator:" not in src, f"{name} 不得残留自绘 indicator（FC-C28/29 WITHDRAWN）"


def test_r3_uss_frame_spec_fully_withdrawn():
    """FC-C28 WITHDRAWN：USS 自绘框规格（#C8A870 边框 / 20×20）须四面包已归零。"""
    senate, war = _senate(), _war()
    assert USS_BORDER not in senate, "SenateStage 不得残留 USS 边框色（FC-C28 WITHDRAWN）"
    assert USS_BORDER not in war, "WarProposalCard 不得残留 USS 边框色（FC-C28 WITHDRAWN）"
    assert "implicitWidth: 20" not in senate, "SenateStage 不得残留自绘框 20×20（FC-C28 WITHDRAWN）"
    assert "implicitWidth: 20" not in war, "WarProposalCard 不得残留自绘框 20×20（FC-C28 WITHDRAWN）"


def test_r3_selfdrawn_check_cross_glyphs_withdrawn():
    """FC-C29 WITHDRAWN：自绘勾/叉子图元（对角旋转 Rectangle）须已归零。"""
    for name, src in (("SenateStage", _senate()), ("WarProposalCard", _war())):
        assert "rotation: 45" not in src and "rotation: -45" not in src, \
            f"{name} 不得残留自绘勾/叉子图元（FC-C29 WITHDRAWN）"


def test_r3_still_exactly_three_senate_checkboxes():
    """结构守恒：SenateStage 仍恰有 ①②③ 三处 CheckBox（移除自绘未增删勾选框）。"""
    src = _senate()
    assert src.count("CheckBox {") == 3, "①②③ 三处 CheckBox 结构不变"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
