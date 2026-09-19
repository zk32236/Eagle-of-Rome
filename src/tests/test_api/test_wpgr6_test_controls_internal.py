# src/tests/test_api/test_wpgr6_test_controls_internal.py
"""WP-G-R6 DA-5 B2（SA-Design v1.1 §D.5 / AC-22）— 内部 force 接缝保留证据（S1 / S2）。

**本文件非玩家面**：只消费内部接缝（构造期 config 注入 + 内部 test API），
不新增任何生产/GUI/Store/Adapter 入口（R6-R14 / R6-ODR-06）。

接缝：
- **S1（构造期注入）**：`wpgr4_fixtures` 的 `_combat_war_state` / `build_fix08` 经
  `GameState.create_for_testing(config)` 在**构造期**把 `testing.force_battle_result`
  / `testing.force_naval_result` 写入内 config；消费链 = `combat_api._normalize_forced_result`
  （combat_api.py:516）/ `naval_system._normalize_forced_naval_result`（naval_system.py:750）。
- **S2（运行期内部 test API）**：`src/api/test_config_api.py` 的 `set_test_config` /
  `get_test_config`（in-memory `state.config`，fail-closed）。

AC-22 锁定不变量：
- 两键**互不穿透**（land / naval 各自独立）；
- **空值 = 正常结算**（`""` 不短路，消费归一化器返回 None）；
- **三场景构造可复现**（S1 与 S2 两条接缝各自独立可用）。
"""
from src.api import combat_api
from src.api import test_config_api
from src.api.combat_api import _normalize_forced_result
from src.core.systems.naval_system import _normalize_forced_naval_result
from src.tests.fixtures import wpgr4_fixtures as F

LAND = "force_battle_result"
NAVAL = "force_naval_result"


def _cfg(state, key):
    return state.config.get(f"testing.{key}", "")


def _battle(state, war):
    phase = state.get_phase_result("combat") or {}
    return phase["war_results"][war.id]


# ---------------------------------------------------------------------------
# S1 — 构造期 config 注入（GameState.create_for_testing）
# ---------------------------------------------------------------------------
class TestS1ConstructionInjection:
    def test_s1_naval_force_injected_at_construction(self):
        """S1：构造期注入 naval force → create_for_testing 内 config 生效 → 确定性 naval block。"""
        ctx = F.build_fix03(naval_force="STALEMATE", land_force="TRIUMPH")
        state, war = ctx["state"], ctx["war"]
        # 构造期已写入内 config（不经 S2 / Store / QML）
        assert _cfg(state, NAVAL) == "STALEMATE"
        assert _cfg(state, LAND) == "TRIUMPH"
        assert _normalize_forced_naval_result(_cfg(state, NAVAL)) == "STALEMATE"
        res = combat_api.auto_resolve_combat(state, F.P1)
        assert res["success"], res.get("message")
        env = _battle(state, war)
        assert env["action_status"] == "naval_blocked"
        assert env["result_stage"] == "naval"
        assert env["naval"]["result"] == "STALEMATE"
        # land 键虽已注入 TRIUMPH，但 naval 门阻断 → 不执行（S1 注入不穿透门控）
        assert env["land"]["executed"] is False
        assert env["land"]["status"] == "NOT_EXECUTED"

    def test_s1_land_force_injected_at_construction(self):
        """S1：构造期注入 land force（非海军 War）→ 普通 land VICTORY。"""
        ctx = F.build_fix08(land_force="VICTORY")
        state, war = ctx["state"], ctx["war"]
        assert _cfg(state, LAND) == "VICTORY"
        assert _cfg(state, NAVAL) == ""  # naval 键未被 land 注入穿透
        res = combat_api.auto_resolve_combat(state, F.P1)
        assert res["success"], res.get("message")
        env = _battle(state, war)
        assert env["land"]["executed"] is True
        assert env["land"]["result"] == "victory"

    def test_s1_empty_force_is_normal_resolution(self):
        """S1：构造期空值 → 两键 "" → 正常结算（归一化器 None，不短路）。"""
        ctx = F.build_fix05(naval_force="", land_force="")
        state, war = ctx["state"], ctx["war"]
        assert _cfg(state, NAVAL) == "" and _cfg(state, LAND) == ""
        assert _normalize_forced_naval_result(_cfg(state, NAVAL)) is None
        assert _normalize_forced_result(_cfg(state, LAND)) is None
        res = combat_api.auto_resolve_combat(state, F.P1)
        assert res["success"], res.get("message")
        env = _battle(state, war)
        # 正常随机 CRT 值域（未强制；海战胜负决定 land 是否执行）
        assert env["naval"]["result"] in (
            "TRIUMPH", "VICTORY", "STALEMATE", "DEFEAT", "DISASTER")
        assert env["action_status"] in ("naval_blocked", "land_resolved")
        if env["action_status"] == "naval_blocked":
            assert env["land"]["executed"] is False
        else:
            assert env["land"]["executed"] is True
            assert env["land"]["result"] in (
                "triumph", "victory", "draw", "defeat", "disaster")


# ---------------------------------------------------------------------------
# S2 — 运行期内部 test API（set_test_config / get_test_config）
# ---------------------------------------------------------------------------
class TestS2RuntimeInternalApi:
    def test_s2_write_one_key_keeps_other(self):
        """S2：写一键不动另一键（两键互不穿透）。"""
        state = F.build_fix08(land_force="")["state"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "victory")["success"]
        assert _cfg(state, NAVAL) == "victory"
        assert _cfg(state, LAND) == ""
        assert test_config_api.set_test_config(state, F.P1, LAND, "defeat")["success"]
        assert _cfg(state, LAND) == "defeat"
        assert _cfg(state, NAVAL) == "victory"  # 仍保留

    def test_s2_clear_one_key_keeps_other(self):
        """S2：清除一键保留另一键（空值 = 正常结算）。"""
        state = F.build_fix08(land_force="")["state"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "victory")["success"]
        assert test_config_api.set_test_config(state, F.P1, NAVAL, "defeat")["success"]
        assert test_config_api.set_test_config(state, F.P1, LAND, "")["success"]
        assert _cfg(state, LAND) == ""
        assert _cfg(state, NAVAL) == "defeat"
        assert _normalize_forced_result(_cfg(state, LAND)) is None  # 空 → 正常结算

    def test_s2_invalid_value_zero_write(self):
        """S2：非法值 / 非字符串 / 未知字段 → fail-closed，零写入。"""
        state = F.build_fix08(land_force="")["state"]
        for field, bad in ((LAND, "banana"), (NAVAL, 1), (NAVAL, None),
                           (NAVAL, ["victory"]), ("force_something", "victory")):
            r = test_config_api.set_test_config(state, F.P1, field, bad)
            assert r["success"] is False
        assert _cfg(state, LAND) == "" and _cfg(state, NAVAL) == ""

    def test_s2_get_exposes_two_independent_option_lists(self):
        """S2：get_test_config 暴露两键值 + 各自独立 options（QML 只消费、零推导）。"""
        state = F.build_fix08(land_force="")["state"]
        data = test_config_api.get_test_config(state)["data"]
        assert data[LAND] == "" and data[NAVAL] == ""
        assert data["land_options"] is not data["naval_options"]
        assert data["land_options"][0] == "" and data["naval_options"][0] == ""
