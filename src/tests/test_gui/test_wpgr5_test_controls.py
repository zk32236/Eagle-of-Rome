# src/tests/test_gui/test_wpgr5_test_controls.py
"""WP-G-R5 DA-6（Owner §20 #44）→ **WP-G-R6 DA-5 B3 迁移版** — 确定性战斗测试控件测试面。

权威（迁移后）：SA-Design-WP-G-R6 v1.1 **§D.5**（生产 TestConfig 退场 / 内部面保留）+ DA-Plan
WP-G-R6 §2「DA-5」**B3 段** + AC-21 / AC-22。原 SA-Design-WP-G-R5 §5.5 / DA-Plan §2.6 的
**生产面**约束已被 R6 §D.5 supersede。

**本批（DA-5 B3）迁移说明（不是删除套件）**：
- DA-5 B1 已把生产 TestConfig 全链退场：`TestConfigDialog.qml` **物理删除**、
  `CombatStage.qml` 入口/宿主移除、`GuiSessionStore` 的 force 缓存/属性/Slot 移除（AC-21）。
  故原「**生产必须宿主 Dialog / 必须暴露 Store 属性**」断言已 **superseded**。
- 本文件把 superseded 断言**改写为「生产不可达」**断言（文件不存在 / 生产 QML 零引用 /
  Store 无该属性与 Slot）—— 逐条旧→新见 `03-da-evidence/DA-R6/DA-5-B3-Report-2026-09-19.md`。
- 原「两键独立 / 空值 = 正常结算 / 非法值 fail-closed」的**配置层不变量一条未删**，改在
  **保留的内部接缝**（`src/api/test_config_api.py`，R6 §D.5 明定保留）上复核（AC-22）。
- 用例数量 **10 → 10**（零删除、零难用例删除）；并行证据 = `test_api/test_wpgr5_test_controls.py`
  （15 绿）+ `test_api/test_wpgr6_test_controls_internal.py`（7 绿）。

DA 侧只出 DATA/静态面证据（Store 可达性 + QML 源码引用），**不伪造渲染断言**（RENDER 归 G5/SO）。
"""
import os

from src.api import session_api
from src.api import test_config_api
from src.tests.fixtures import wpgr4_fixtures as F
from src.ui.gui.session_store import GuiSessionStore

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
DIALOG_QML = os.path.join(QML_DIR, "components", "TestConfigDialog.qml")
COMBAT_QML = os.path.join(QML_DIR, "stages", "CombatStage.qml")

LAND = "force_battle_result"
NAVAL = "force_naval_result"

# AC-21：DA-5 B1 已从生产 Store 移除的属性 / Slot（迁移后必须**全部不可达**）。
REMOVED_STORE_SURFACE = (
    "forceBattleResult",
    "forceNavalResult",
    "forceBattleResultOptions",
    "forceNavalResultOptions",
    "doSetForceBattleResult",
    "doSetForceNavalResult",
    "testConfigView",
)
# 原 Dialog 的合并 override 禁令（SA §5.5 / DA-Plan §2.6）→ 迁移为「生产 QML 不得重新引入」。
BANNED_MERGED = ("sessionStore.forceResult(", "combined_force", "override_all",
                 "force_both_result")
# 原 Dialog 的本地推导禁令（A-I18）→ 迁移为「保留的 TestConfig 面不得本地推导」。
BANNED_DERIVATION = ("warCards", "reinforcement_n", "legion_pool", "threat_level")


def _make_store():
    result = session_api.create_gui_prototype_session()
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    state.set_current_player(viewer_id)
    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    return store, state, viewer_id


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _production_qml_files():
    """生产 QML 资源目录下的全部 `.qml` 文件（退场的 Dialog 不在其中）。"""
    files = []
    for root, _dirs, names in os.walk(QML_DIR):
        for name in names:
            if name.endswith(".qml"):
                files.append(os.path.join(root, name))
    return files


def _cfg(state, key):
    return state.config.get(f"testing.{key}", "")


class TestTestConfigStoreSurface:
    """Store 面（已迁移）：生产 Store 属性/Slot **不可达**（AC-21）；两键独立 / 空值 /
    非法值 fail-closed 不变量在保留的内部接缝（`test_config_api`）上复核（AC-22）。"""

    def test_defaults_and_options_exposed(self):
        store, _, _ = _make_store()
        # AC-21：生产 Store 不再暴露任何 TestConfig 属性 / Slot
        for attr in REMOVED_STORE_SURFACE:
            assert not hasattr(store, attr), f"生产 Store 仍暴露 {attr}"
        # AC-22：保留的内部面仍暴露两键默认（空）+ 各自独立选项
        state = F.build_fix08(land_force="")["state"]
        cfg = test_config_api.get_test_config(state)
        assert cfg["success"] is True
        data = cfg["data"]
        assert data[LAND] == "" and data[NAVAL] == ""
        land_opts = data["land_options"]
        naval_opts = data["naval_options"]
        assert land_opts[0] == "" and naval_opts[0] == ""
        assert "victory" in land_opts
        assert "victory" in naval_opts
        assert land_opts is not naval_opts

    def test_apply_land_does_not_touch_naval(self):
        store, _, _ = _make_store()
        # AC-21：生产写 Slot / 只读属性均不可达
        assert not hasattr(store, "doSetForceBattleResult")
        assert not hasattr(store, "forceBattleResult")
        # AC-22：只设 land → naval 保持空（互不穿透）——在保留的内部面复核
        state = F.build_fix08(land_force="")["state"]
        r = test_config_api.set_test_config(state, F.P1, LAND, "victory")
        assert r["success"] is True
        assert _cfg(state, LAND) == "victory"
        assert _cfg(state, NAVAL) == ""

    def test_apply_naval_does_not_touch_land(self):
        store, _, _ = _make_store()
        assert not hasattr(store, "doSetForceNavalResult")
        assert not hasattr(store, "forceNavalResult")
        state = F.build_fix08(land_force="")["state"]
        r = test_config_api.set_test_config(state, F.P1, NAVAL, "defeat")
        assert r["success"] is True
        assert _cfg(state, NAVAL) == "defeat"
        assert _cfg(state, LAND) == ""

    def test_clear_one_key_keeps_other(self):
        store, _, _ = _make_store()
        assert not hasattr(store, "doSetForceBattleResult")
        assert not hasattr(store, "doSetForceNavalResult")
        state = F.build_fix08(land_force="")["state"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "victory")["success"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "disaster")["success"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "")["success"]
        assert _cfg(state, LAND) == ""
        assert _cfg(state, NAVAL) == "disaster"

    def test_invalid_value_fails_without_write(self):
        store, _, _ = _make_store()
        assert not hasattr(store, "doSetForceNavalResult")
        state = F.build_fix08(land_force="")["state"]
        r = test_config_api.set_test_config(state, F.P1, NAVAL, "banana")
        assert r["success"] is False
        assert _cfg(state, NAVAL) == ""


class TestTestConfigQmlSurface:
    """QML 面（已迁移）：生产 QML **不可达该 TestConfig 控件面**（文件已删 + 零引用）；
    两键独立性由保留的内部面承载。静态事实，非渲染断言。"""

    def test_dialog_component_retired_unreachable(self):
        # AC-21：退场 Dialog 物理删除 → 生产资源目录中不存在
        assert not os.path.exists(DIALOG_QML), DIALOG_QML
        # 且没有任何生产 QML 引用该组件（含宿主 / 装载）
        for path in _production_qml_files():
            assert "TestConfigDialog" not in _read(path), path

    def test_no_production_test_config_controls(self):
        # AC-21：生产 QML 不再暴露两个独立控件 / 其 Store 绑定
        banned_tokens = (
            'objectName: "forceLandResultCombo"',
            'objectName: "forceNavalResultCombo"',
            "sessionStore.forceBattleResultOptions",
            "sessionStore.forceNavalResultOptions",
            "sessionStore.doSetForceBattleResult(",
            "sessionStore.doSetForceNavalResult(",
        )
        for path in _production_qml_files():
            src = _read(path)
            for token in banned_tokens:
                assert token not in src, (path, token)
        # AC-22：两键独立性由保留的内部面承载（选项列表相互独立）
        state = F.build_fix08(land_force="")["state"]
        data = test_config_api.get_test_config(state)["data"]
        assert data["land_options"] is not data["naval_options"]

    def test_no_merged_cross_stage_override(self):
        """不得把两键合并为单一跨阶段 override（SA §5.5 / DA-Plan §2.6 不可越界面）。

        迁移：原断言面 = 已删的 Dialog 源码；迁移后 = 全生产 QML 不得**重新引入**合并 override。
        """
        for path in _production_qml_files():
            src = _read(path)
            for banned in BANNED_MERGED:
                assert banned not in src, (path, banned)

    def test_zero_derivation_retained_config_surface(self):
        """保留的 TestConfig 面只**消费**能力/DTO：无本地 N 上限 / 强制分类推导（A-I18）。

        迁移：原断言面 = 已删的 Dialog 源码；迁移后 = 保留的内部接缝
        （`test_config_api`）：选项为模块静态 DTO（与战局状态无关 → 零推导），且其源码不含
        任何 war / legion / threat 推导 token。
        """
        assert test_config_api.land_result_options() == [
            "", "stalemate", "triumph", "victory", "defeat", "disaster"]
        assert test_config_api.naval_result_options() == [
            "", "stalemate", "triumph", "victory", "defeat", "disaster"]
        src = _read(os.path.join(PROJECT_ROOT, "src", "api", "test_config_api.py"))
        for banned in BANNED_DERIVATION:
            assert banned not in src, banned

    def test_combat_stage_no_test_config_host_or_trigger(self):
        """AC-21：Combat 阶段**不再**提供 Configure/Test 入口或宿主（生产不可达）。

        迁移：原断言 = 「Combat 必须宿主 Dialog + open()」；迁移后 = 「宿主与触发器均不存在」。
        """
        src = _read(COMBAT_QML)
        assert "TestConfigDialog {" not in src
        assert 'objectName: "testConfigDialog"' not in src
        assert "testConfigDialog.open()" not in src
        assert 'objectName: "testConfigTriggerButton"' not in src
