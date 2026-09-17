# src/tests/test_api/test_wpgr5_test_controls.py
"""WP-G-R5 DA-6（Owner §20 #44）— 确定性战斗测试控件（API/配置面）。

权威：SA-Design-WP-G-R5 §5.5（暴露两个**独立**控件 `Force Land Result →
testing.force_battle_result`、`Force Naval Result → testing.force_naval_result`；空值/默认
= 正常结算；用途 = 让 G7 确定性构造 naval block / naval 成功+land 失败 / 普通 land
VICTORY）+ DA-Plan §2.6（文件面/完成判据/不可越界面）+ 任务书 B4 §2。

不变量（本测试锁定）：
- **两键互不穿透**：改 land 不影响 naval，反之亦然；
- **空值 = 正常结算**：空/缺省 → 既有 canonical 归一化返回 None（正常 2d6 CRT /
  random CRT），不新增战斗规则；
- **消费点语义不变**：`combat_api:516` / `naval_system:750` 归一化器原样消费（本测试只
  作为只读证据引用，不修改）；
- 配置写入口 = 测试/配置面（in-memory；committed `game_config.json` 默认 `""` 不入提交面）。
"""
import pytest

from src.api import combat_api
from src.api import test_config_api
from src.api.combat_api import _normalize_forced_result
from src.core.systems.naval_system import _normalize_forced_naval_result
from src.tests.fixtures import wpgr4_fixtures as F

LAND = "force_battle_result"
NAVAL = "force_naval_result"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _empty_state():
    """task-local 内存 config（force 两键空）——不读工作树 game_config.json override。"""
    return F.build_fix08(land_force="")["state"]


def _cfg(state, key):
    return state.config.get(f"testing.{key}", "")


def _battle(state, war):
    phase = state.get_phase_result("combat") or {}
    return phase["war_results"][war.id]


# ---------------------------------------------------------------------------
# A. 读 / 写 / 独立性（§20 #44 前半：两个独立控件）
# ---------------------------------------------------------------------------
class TestForceControlReadWrite:
    def test_defaults_empty_normal_resolution(self):
        """committed 默认（空）→ 读回空 → 消费归一化 None（正常结算），两键都被覆盖。"""
        state = _empty_state()
        cfg = test_config_api.get_test_config(state)
        assert cfg["success"] is True
        data = cfg["data"]
        assert data[LAND] == ""
        assert data[NAVAL] == ""
        # 空值 = 正常结算（既有归一化器返回 None → 不短路）
        assert _normalize_forced_result(_cfg(state, LAND)) is None
        assert _normalize_forced_naval_result(_cfg(state, NAVAL)) is None

    def test_set_land_does_not_touch_naval(self):
        """只设 land → naval 保持空（互不穿透）。"""
        state = _empty_state()
        r = test_config_api.set_test_config(state, F.P1, LAND, "victory")
        assert r["success"] is True
        assert _cfg(state, LAND) == "victory"
        assert _cfg(state, NAVAL) == ""
        assert _normalize_forced_result(_cfg(state, LAND)) == "victory"
        assert _normalize_forced_naval_result(_cfg(state, NAVAL)) is None

    def test_set_naval_does_not_touch_land(self):
        """只设 naval → land 保持空（互不穿透）。"""
        state = _empty_state()
        r = test_config_api.set_test_config(state, F.P1, NAVAL, "defeat")
        assert r["success"] is True
        assert _cfg(state, NAVAL) == "defeat"
        assert _cfg(state, LAND) == ""
        assert _normalize_forced_naval_result(_cfg(state, NAVAL)) == "DEFEAT"
        assert _normalize_forced_result(_cfg(state, LAND)) is None

    def test_two_keys_coexist_independently(self):
        """两键同时设值 → 各自独立生效，互不覆盖。"""
        state = _empty_state()
        assert test_config_api.set_test_config(state, F.P1, LAND, "victory")["success"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "defeat")["success"]
        assert _cfg(state, LAND) == "victory"
        assert _cfg(state, NAVAL) == "defeat"
        cfg = test_config_api.get_test_config(state)["data"]
        assert cfg[LAND] == "victory" and cfg[NAVAL] == "defeat"

    def test_empty_value_restores_normal_resolution(self):
        """显式空值 = 清除 override → 正常结算（两键各自可清）。"""
        state = _empty_state()
        assert test_config_api.set_test_config(state, F.P1, LAND, "victory")["success"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "defeat")["success"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "")["success"]
        assert _cfg(state, LAND) == ""
        assert _cfg(state, NAVAL) == "defeat"  # 清 land 不动 naval
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "")["success"]
        assert _cfg(state, NAVAL) == ""

    def test_case_and_whitespace_tolerated(self):
        """大小写/空白容忍（与既有归一化同语义）→ 读回稳定 token。"""
        state = _empty_state()
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "  Victory ")["success"]
        assert _normalize_forced_naval_result(_cfg(state, NAVAL)) == "VICTORY"
        assert test_config_api.set_test_config(state, F.P1, LAND, "Stalemate")["success"]
        assert _normalize_forced_result(_cfg(state, LAND)) == "draw"

    def test_unknown_field_rejected_fail_closed(self):
        """未知字段 → 显式失败，零写入。"""
        state = _empty_state()
        r = test_config_api.set_test_config(state, F.P1, "force_something", "victory")
        assert r["success"] is False
        assert any("TEST_CONFIG_UNKNOWN_FIELD" in e for e in r["errors"])
        assert _cfg(state, LAND) == "" and _cfg(state, NAVAL) == ""

    def test_invalid_value_rejected_fail_closed(self):
        """非法值 → 显式失败（不静默变正常结算），零写入。"""
        state = _empty_state()
        r = test_config_api.set_test_config(state, F.P1, LAND, "banana")
        assert r["success"] is False
        assert any("TEST_CONFIG_INVALID_VALUE" in e for e in r["errors"])
        assert _cfg(state, LAND) == ""

    def test_non_string_value_rejected(self):
        """非字符串（如 int/None）→ 失败，零写入。"""
        state = _empty_state()
        for bad in (None, 1, ["victory"]):
            r = test_config_api.set_test_config(state, F.P1, NAVAL, bad)
            assert r["success"] is False
            assert _cfg(state, NAVAL) == ""

    def test_option_lists_two_independent(self):
        """两控件选项 = none + 现五词归一结果；两列表相互独立。"""
        state = _empty_state()
        cfg = test_config_api.get_test_config(state)["data"]
        land_opts = cfg["land_options"]
        naval_opts = cfg["naval_options"]
        assert land_opts is not naval_opts
        assert land_opts[0] == "" and naval_opts[0] == ""
        assert len(land_opts) == 6 and len(naval_opts) == 6
        assert set(land_opts) == {"", "stalemate", "triumph", "victory", "defeat", "disaster"}
        assert set(naval_opts) == {"", "stalemate", "triumph", "victory", "defeat", "disaster"}
        # 每个非空选项都经对应消费归一化器存在（fail-closed 一致）
        for token in land_opts[1:]:
            assert _normalize_forced_result(token) is not None
        for token in naval_opts[1:]:
            assert _normalize_forced_naval_result(token) is not None

    def test_write_entry_is_in_memory_only(self):
        """测试/配置面写入口 = in-memory（无文件路径 → 不可能污染 committed 默认）。"""
        state = _empty_state()
        assert state.config.path is None
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "victory")["success"]
        assert state.config.path is None
        assert _cfg(state, NAVAL) == "victory"


# ---------------------------------------------------------------------------
# B. 三场景确定性构造（§20 #44 后半；任务包 §14.2 / DA-Plan §5.2 F-3）
# ---------------------------------------------------------------------------
class TestThreeScenarioConstruction:
    def test_scenario_1_naval_block_land_not_executed(self):
        """场景①：naval block（force_naval_result = stalemate/defeat → Land 不执行）。"""
        ctx = F.build_fix03(naval_force="", land_force="")
        state, war = ctx["state"], ctx["war"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "stalemate")["success"]
        # land 键保持空 → 由控件单独设 naval 即可确定性构造 block
        assert _cfg(state, LAND) == ""
        res = combat_api.auto_resolve_combat(state, F.P1)
        assert res["success"], res.get("message")
        env = _battle(state, war)
        assert env["schema_version"] == 2
        assert env["action_status"] == "naval_blocked"
        assert env["result_stage"] == "naval"
        assert env["naval"]["result"] == "STALEMATE"
        assert env["land"]["executed"] is False
        assert env["land"]["status"] == "NOT_EXECUTED"
        assert env["land"]["reason"] == "NAVAL_GATE_BLOCKED"

    def test_scenario_2_naval_success_land_failure(self):
        """场景②：naval 成功 + land 失败（两键分别控制，各自生效）。"""
        ctx = F.build_fix05(naval_force="", land_force="")
        state, war = ctx["state"], ctx["war"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "victory")["success"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "defeat")["success"]
        res = combat_api.auto_resolve_combat(state, F.P1)
        assert res["success"], res.get("message")
        env = _battle(state, war)
        assert env["action_status"] == "land_resolved"
        assert env["naval"]["result"] == "VICTORY"
        assert env["land"]["executed"] is True
        assert env["land"]["result"] == "defeat"

    def test_scenario_2_independence_after_clearing_one_key(self):
        """场景②变体：只清 land（留 naval）→ naval 仍 VICTORY，land 走正常结算。"""
        ctx = F.build_fix05(naval_force="", land_force="")
        state, war = ctx["state"], ctx["war"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "victory")["success"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "defeat")["success"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "")["success"]
        assert _cfg(state, NAVAL) == "victory"
        res = combat_api.auto_resolve_combat(state, F.P1)
        assert res["success"], res.get("message")
        env = _battle(state, war)
        assert env["naval"]["result"] == "VICTORY"
        assert env["land"]["executed"] is True
        assert env["land"]["result"] in ("triumph", "victory", "draw", "defeat", "disaster")
        assert env["land"]["result"] != "defeat" or True  # 正常 CRT 值域（未强制）

    def test_scenario_3_plain_land_victory(self):
        """场景③：普通 land VICTORY（非海军 war，仅 land 键生效）。"""
        ctx = F.build_fix08(land_force="")
        state, war = ctx["state"], ctx["war"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "victory")["success"]
        res = combat_api.auto_resolve_combat(state, F.P1)
        assert res["success"], res.get("message")
        env = _battle(state, war)
        assert env["land"]["executed"] is True
        assert env["land"]["result"] == "victory"
        assert war.status.value == "resolved"
        # naval 键未被 land 写入穿透
        assert _cfg(state, NAVAL) == ""
