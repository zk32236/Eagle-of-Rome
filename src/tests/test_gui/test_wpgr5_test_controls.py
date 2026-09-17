# src/tests/test_gui/test_wpgr5_test_controls.py
"""WP-G-R5 DA-6（Owner §20 #44）— 确定性战斗测试控件（Store/DTO + QML 静态面）。

权威：SA-Design-WP-G-R5 §5.5 + §5.1（QML 只消费能力/DTO，零推导；A-I18）+ DA-Plan §2.6。

形态说明：§6.2 证据分类把 §20 #44 归 **RENDER_AUTOMATED**（SO native Qt 渲染复核）。
DA 侧只出 DATA/静态面证据（Store 读写 + QML 源码绑定），**不伪造渲染断言**：
- Store 面：两键独立读写、空值=正常结算、失败不动值；
- QML 面：宿主组件存在且暴露**两个独立**控件（两个 ComboBox / 两个独立属性 / 两个独立
  Slot），不合并为单一跨阶段 override。
"""
import os

from src.api import session_api
from src.ui.gui.session_store import GuiSessionStore

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
DIALOG_QML = os.path.join(QML_DIR, "components", "TestConfigDialog.qml")
COMBAT_QML = os.path.join(QML_DIR, "stages", "CombatStage.qml")


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


class TestTestConfigStoreSurface:
    """Store 面：两键独立读模型 + 独立写 Slot（空值 = 正常结算）。"""

    def test_defaults_and_options_exposed(self):
        store, _, _ = _make_store()
        assert store.forceBattleResult == ""
        assert store.forceNavalResult == ""
        land_opts = store.forceBattleResultOptions
        naval_opts = store.forceNavalResultOptions
        assert land_opts[0] == "" and naval_opts[0] == ""
        assert "victory" in land_opts
        assert "victory" in naval_opts
        assert store.testConfigView.get("force_battle_result") == ""

    def test_apply_land_does_not_touch_naval(self):
        store, state, _ = _make_store()
        r = store.doSetForceBattleResult("victory")
        assert r["success"] is True
        assert store.forceBattleResult == "victory"
        assert store.forceNavalResult == ""
        assert state.config.get("testing.force_naval_result", "") == ""

    def test_apply_naval_does_not_touch_land(self):
        store, state, _ = _make_store()
        r = store.doSetForceNavalResult("defeat")
        assert r["success"] is True
        assert store.forceNavalResult == "defeat"
        assert store.forceBattleResult == ""
        assert state.config.get("testing.force_battle_result", "") == ""

    def test_clear_one_key_keeps_other(self):
        store, _, _ = _make_store()
        assert store.doSetForceBattleResult("victory")["success"]
        assert store.doSetForceNavalResult("disaster")["success"]
        assert store.doSetForceBattleResult("")["success"]
        assert store.forceBattleResult == ""
        assert store.forceNavalResult == "disaster"

    def test_invalid_value_fails_without_write(self):
        store, _, _ = _make_store()
        r = store.doSetForceNavalResult("banana")
        assert r["success"] is False
        assert store.forceNavalResult == ""


class TestTestConfigQmlSurface:
    """QML 面：宿主组件 + 两个独立控件绑定（静态事实，非渲染断言）。"""

    def test_host_component_exists_and_is_dialog(self):
        assert os.path.isfile(DIALOG_QML), DIALOG_QML
        src = _read(DIALOG_QML)
        assert "Dialog {" in src
        assert 'objectName: "testConfigDialog"' in src

    def test_two_independent_controls(self):
        src = _read(DIALOG_QML)
        assert src.count("ComboBox {") == 2
        assert 'objectName: "forceLandResultCombo"' in src
        assert 'objectName: "forceNavalResultCombo"' in src
        # 各自绑定各自的只读属性 + 各自的写 Slot（无合并/无穿透）
        assert "sessionStore.forceBattleResultOptions" in src
        assert "sessionStore.forceNavalResultOptions" in src
        assert "sessionStore.doSetForceBattleResult(" in src
        assert "sessionStore.doSetForceNavalResult(" in src
        # 两控件 label 分离（land/naval 两键独立暴露，D7 非缺陷）
        assert "forceBattleResult" in src and "forceNavalResult" in src

    def test_no_merged_cross_stage_override(self):
        """不得把两键合并为单一跨阶段 override（SA §5.5 / DA-Plan §2.6 不可越界面）。"""
        src = _read(DIALOG_QML)
        for banned in ("sessionStore.forceResult(", "combined_force", "override_all",
                       "force_both_result"):
            assert banned not in src

    def test_qml_zero_derivation(self):
        """QML 只消费 Store 能力/DTO：无本地 N 上限推导 / 无强制分类推导（A-I18）。"""
        src = _read(DIALOG_QML)
        for banned in ("warCards", "reinforcement_n", "legion_pool", "threat_level"):
            assert banned not in src

    def test_combat_stage_hosts_test_config_dialog(self):
        """宿主挂载点：Combat 阶段提供 Configure/Test 入口（G7 可达）。"""
        src = _read(COMBAT_QML)
        assert "TestConfigDialog {" in src
        assert 'objectName: "testConfigDialog"' in src
        assert "testConfigDialog.open()" in src
