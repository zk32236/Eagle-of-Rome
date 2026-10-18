"""D12 / W1 — 决算授权上下文显式传递（R2 最终版，RED-first）。

基线缺陷链（0c4e9356）：
- ``game_api.execute_phase`` 的外层 ``@guarded`` 从 kwargs 取走 ``caller_context``
  完成授权后，因签名未声明该形参而不再向内转发（``forward_cc=False``）；
- ``ResolutionCommand.execute`` 调 ``execute_resolution(self.state)`` 无上下文 →
  内层 ``@guarded`` 必然 DENY；
- 内层 DENIED 被压成 ``print(...) + False``，``execute_phase`` 再用 stdout 重建
  envelope（``errors=[]``）→ 界面拿不到任何 typed 失败信息。

R2 追加：
- B-01：真实 ``MortalityCommand``（bool 返回）经 ``execute_phase`` 携带 context
  不得触发 ``'bool' object has no attribute 'get'``；
- B-02：未注册 CLI 的 ``execute_phase`` message 必须与 ``ResolutionCommand.execute``
  的 stdout 逐字节相等；
- B-04：``execute_turn`` 必须把 keyword-only context 转发到 resolution。

本文件只走**真实授权链**（``register_hotseat_session``），不 mock 授权。
"""
import random

import pytest

from src.api import game_api
from src.api import resolution_api
from src.api import session_access
from src.api import session_api
from src.ui.commands.phase_resolution import ResolutionCommand


def _make_ready_state(start_phase="combat"):
    """建一个 combat 已执行、resolution 未执行的原型会话。"""
    result = session_api.create_gui_prototype_session(start_phase=start_phase)
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    players = list(result["data"]["human_players"])
    assert players, "原型会话必须至少有一个真人座位"
    player_id = players[0]
    state.set_current_player(player_id)
    state.mark_phase_executed("combat")
    return state, players, player_id


@pytest.fixture
def registered():
    """已注册 Hot-seat 会话 + 合法 opaque handle。"""
    state, players, player_id = _make_ready_state()
    session_access.register_hotseat_session(state, player_id)
    ctx = session_access.current_caller_context(state)
    assert ctx is not None
    assert ctx.revoked is False
    return state, players, player_id, ctx


@pytest.fixture
def cli_state():
    """未注册（CLI / 历史）会话：必须与基线逐字节等价。"""
    state, players, player_id = _make_ready_state()
    assert session_access.is_hotseat_registered(state) is False
    return state, players, player_id


def _codes(result):
    return [e.get("code") for e in (result.get("errors") or [])
            if isinstance(e, dict)]


def _mark_pre_resolution_phases(state):
    for phase in ("mortality", "revenue", "forum", "population", "senate",
                  "combat"):
        state.mark_phase_executed(phase)


# ---------------------------------------------------------------------------
# AC-W1-01 — 已注册 + ACTIVE + 合法 context：成功且决算落盘
# ---------------------------------------------------------------------------
def test_registered_active_context_executes_resolution(registered):
    state, _players, player_id, ctx = registered

    result = game_api.execute_phase(state, "resolution", player_id,
                                    caller_context=ctx)

    assert result["success"] is True, result
    assert _codes(result) == []
    assert state.is_phase_executed("resolution") is True


def test_registered_active_context_records_resolution_dto(registered):
    state, _players, player_id, ctx = registered

    game_api.execute_phase(state, "resolution", player_id, caller_context=ctx)

    assert state.get_phase_result("resolution") is not None


def test_registered_active_context_reaches_inner_api(registered):
    """成功路径必须真的穿过内层 guarded 边界（而不是空 DTO 冒充）。"""
    state, _players, player_id, ctx = registered

    result = game_api.execute_phase(state, "resolution", player_id,
                                    caller_context=ctx)

    assert result["success"] is True, result
    # 内层真实结算产物存在（DTO 由 resolution_api 构建）
    assert state.get_phase_result("resolution")
    assert result["data"]["phase"] == "resolution"


# ---------------------------------------------------------------------------
# AC-W1-02 — 已注册 + 缺 context：typed DENIED，零业务副作用
# ---------------------------------------------------------------------------
def test_missing_context_is_denied(registered):
    state, _players, player_id, _ctx = registered

    result = game_api.execute_phase(state, "resolution", player_id)

    assert result["success"] is False
    assert _codes(result) == ["DENIED"]


def test_missing_context_has_no_business_side_effect(registered):
    state, _players, player_id, _ctx = registered

    game_api.execute_phase(state, "resolution", player_id)

    assert state.is_phase_executed("resolution") is False
    assert state.get_phase_result("resolution") is None


def test_missing_context_carries_a_message(registered):
    state, _players, player_id, _ctx = registered

    result = game_api.execute_phase(state, "resolution", player_id)

    errors = [e for e in (result.get("errors") or []) if isinstance(e, dict)]
    assert errors and errors[0].get("message")


# ---------------------------------------------------------------------------
# AC-W1-03 — 直接调内层 API（无 context）：DENIED，不被吞成空 DTO
# ---------------------------------------------------------------------------
def test_inner_api_without_context_is_denied(registered):
    state, _players, _player_id, _ctx = registered

    result = resolution_api.execute_resolution(state)

    assert result["success"] is False
    assert _codes(result) == ["DENIED"]
    assert result.get("data") is None
    assert state.is_phase_executed("resolution") is False


def test_inner_api_with_context_executes(registered):
    state, _players, _player_id, ctx = registered

    result = resolution_api.execute_resolution(state, caller_context=ctx)

    assert result["success"] is True, result
    assert _codes(result) == []
    assert state.is_phase_executed("resolution") is True


# ---------------------------------------------------------------------------
# AC-W1-04 — 错座位 / 错 epoch：DENIED，零副作用
# ---------------------------------------------------------------------------
def test_wrong_viewer_seat_is_denied(registered):
    state, players, _player_id, ctx = registered

    result = game_api.execute_phase(state, "resolution", "player_observer",
                                    caller_context=ctx)

    assert result["success"] is False
    assert _codes(result) == ["DENIED"]
    assert state.is_phase_executed("resolution") is False


def test_wrong_epoch_context_is_denied(registered):
    state, _players, player_id, ctx = registered
    forged = session_access.HotseatContext(
        session_id=ctx.session_id,
        principal_player_id=ctx.principal_player_id,
        epoch=ctx.epoch + 1,
        lifecycle=ctx.lifecycle,
        revoked=False,
        handle_id=ctx.handle_id,
    )

    result = game_api.execute_phase(state, "resolution", player_id,
                                    caller_context=forged)

    assert result["success"] is False
    assert _codes(result) == ["DENIED"]
    assert state.is_phase_executed("resolution") is False


# ---------------------------------------------------------------------------
# B-01 — 真实 bool Command（MortalityCommand）经 execute_phase 不得误当 dict
# ---------------------------------------------------------------------------
def test_mortality_bool_command_with_context_does_not_crash():
    state, _players, player_id = _make_ready_state(start_phase="mortality")
    session_access.register_hotseat_session(state, player_id)
    ctx = session_access.current_caller_context(state)
    assert ctx is not None and ctx.revoked is False

    result = game_api.execute_phase(state, "mortality", player_id,
                                    caller_context=ctx)

    assert result["success"] is True, result
    assert _codes(result) == []
    assert state.is_phase_executed("mortality") is True


# ---------------------------------------------------------------------------
# AC-W1-06 — 未注册 CLI：envelope 形状 / bool 语义与基线一致
# ---------------------------------------------------------------------------
def test_unregistered_cli_envelope_shape(cli_state):
    state, _players, player_id = cli_state

    result = game_api.execute_phase(state, "resolution", player_id)

    assert result["success"] is True, result
    assert set(result.keys()) == {"success", "message", "data", "errors"}
    assert result["data"] == {"phase": "resolution"}
    assert isinstance(result["message"], str)
    assert result["errors"] == []
    assert state.is_phase_executed("resolution") is True


def test_cli_message_equals_execute_stdout(capsys):
    """B-02：execute_phase(None) 的 message 必须逐字节等于 execute 的 stdout。"""
    # 方案 B：固定种子构造两个等价会话。GameState 内含 Logger，deepcopy
    # 不可用；scenario_loader 使用未播种 random，故两次构造前同时播种。
    random.seed(20261018)
    state, _players, player_id = _make_ready_state()
    assert session_access.is_hotseat_registered(state) is False
    random.seed(20261018)
    state2, _players2, player_id2 = _make_ready_state()
    assert player_id2 == player_id
    capsys.readouterr()  # 丢弃两会话构造期的初始化打印，只比较 execute 输出

    ok = ResolutionCommand(state).execute([])
    assert ok is True
    direct_stdout = capsys.readouterr().out

    result = game_api.execute_phase(state2, "resolution", player_id2)
    capsys.readouterr()  # 清空 execute_phase 的 Tee 输出

    assert result["success"] is True, result
    assert result["message"] == direct_stdout.strip()


def test_command_execute_keeps_bool_contract(cli_state):
    state, _players, player_id = cli_state

    ok = ResolutionCommand(state).execute([])

    assert ok is True
    assert state.is_phase_executed("resolution") is True


# ---------------------------------------------------------------------------
# 幂等 / 重复执行：结构化入口不重新结算
# ---------------------------------------------------------------------------
def test_repeat_execution_is_not_successful(registered):
    state, _players, player_id, ctx = registered
    first = game_api.execute_phase(state, "resolution", player_id,
                                   caller_context=ctx)
    assert first["success"] is True, first

    second = game_api.execute_phase(state, "resolution", player_id,
                                    caller_context=ctx)

    assert second["success"] is False
    assert second["errors"], "重复执行必须带 typed error，不得静默成功"
    assert state.is_phase_executed("resolution") is True


# ---------------------------------------------------------------------------
# B-04 — execute_turn 的 keyword-only caller_context 正/反例
# ---------------------------------------------------------------------------
def test_execute_turn_forwards_context_to_resolution(registered):
    state, _players, player_id, ctx = registered
    _mark_pre_resolution_phases(state)

    result = game_api.execute_turn(state, player_id, caller_context=ctx)

    assert result["success"] is True, result
    assert state.is_phase_executed("resolution") is True


def test_execute_turn_without_context_is_denied(registered):
    state, _players, player_id, _ctx = registered
    _mark_pre_resolution_phases(state)

    result = game_api.execute_turn(state, player_id)

    assert result["success"] is False
    assert _codes(result) == ["DENIED"]
    assert state.is_phase_executed("resolution") is False
