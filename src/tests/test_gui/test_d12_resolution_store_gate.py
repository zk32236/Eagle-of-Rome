"""D12 / W1 — Store 自动结算的 ACTIVE 生命周期门（A5）+ 失败反馈信号（AC-07）。

``_on_refresh`` 在**每次**成功 API 调用后同步回调（``api_adapter.py:143-145``）；
masked handoff 的 dispatch 返回时 handle 已被 ``suspend_hotseat_session`` 置
``revoked=True``。若该瞬间 ``selected_phase_id == "resolution"`` 且未结算，
``_executeResolution`` 会以 SUSPENDED 座位发起调用 → 假 DENIED。

A5 只加**只读**生命周期门：非 ACTIVE（或 handle 已 revoked）时不调用 API，
不改 masked / staging / reveal 逻辑。

R2 追加：AC-07 动态断言——Store 失败时 ``feedbackRaised`` 必须携带
``feedback_message``（含错误 code / message），不得静默。
"""
import pytest

from src.api import session_access
from src.api import session_api
from src.ui.gui.session_store import (
    GuiSessionStore,
    SEAT_ACTIVE,
    SEAT_BUSY,
    SEAT_MASKED_FAILURE,
    SEAT_MASKED_PENDING,
)


def _make_store():
    result = session_api.create_gui_prototype_session(start_phase="combat")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    players = list(result["data"]["human_players"])
    player_id = players[0]
    state.set_current_player(player_id)
    store = GuiSessionStore(state)
    store.initialize(player_id)
    return store, state, player_id


def _install_spy(store):
    """记录 ``adapter.execute_phase`` 是否被调用（唯一允许的 spy）。"""
    calls = []

    def fake_execute_phase(phase_id, player_id):
        calls.append((phase_id, player_id))
        return {
            "success": True,
            "message": "ok",
            "data": {},
            "errors": [],
            "feedback_type": "success",
            "feedback_message": "ok",
        }

    store._adapter.execute_phase = fake_execute_phase
    return calls


@pytest.mark.parametrize("lifecycle", [SEAT_BUSY, SEAT_MASKED_PENDING,
                                       SEAT_MASKED_FAILURE])
def test_non_active_lifecycle_does_not_call_api(lifecycle):
    store, _state, _player_id = _make_store()
    calls = _install_spy(store)
    store._seat_lifecycle = lifecycle

    store._executeResolution()

    assert calls == []


def test_active_lifecycle_still_calls_api():
    store, _state, player_id = _make_store()
    calls = _install_spy(store)
    store._seat_lifecycle = SEAT_ACTIVE

    store._executeResolution()

    assert calls == [("resolution", player_id)]


def test_revoked_handle_does_not_call_api():
    """座位标签仍是 ACTIVE、但服务端 handle 已 revoked（masked 瞬间）。"""
    store, state, player_id = _make_store()
    session_access.register_hotseat_session(state, player_id)
    session_access.suspend_hotseat_session(state)
    ctx = session_access.current_caller_context(state)
    assert ctx is not None and ctx.revoked is True
    assert store._seat_lifecycle == SEAT_ACTIVE

    calls = _install_spy(store)
    store._executeResolution()

    assert calls == []


def test_gate_is_read_only():
    """门只读：不得改变 masked/staging 状态，也不得留下 resolving 标记。"""
    store, _state, _player_id = _make_store()
    _install_spy(store)
    store._seat_lifecycle = SEAT_MASKED_PENDING
    busy_before = store._handoff_busy
    txn_before = store._seat_txn

    store._executeResolution()

    assert store._seat_lifecycle == SEAT_MASKED_PENDING
    assert store._handoff_busy == busy_before
    assert store._seat_txn is txn_before
    assert store._resolution_resolving is False


def test_failure_raises_feedback_signal_with_error_message():
    """AC-07：失败时 ``feedbackRaised`` 必须带错误 code/message。"""
    store, _state, _player_id = _make_store()
    store._seat_lifecycle = SEAT_ACTIVE
    store._adapter.get_resolution_view = lambda viewer_id: {}

    error_text = "决算失败：DENIED — 当前座位无权执行决算"

    def fake_execute_phase(phase_id, player_id):
        return {
            "success": False,
            "message": error_text,
            "data": None,
            "errors": [{
                "code": "DENIED",
                "scope": "phase",
                "field": None,
                "details": {},
                "message": error_text,
            }],
            "feedback_type": "error",
            "feedback_message": error_text,
        }

    store._adapter.execute_phase = fake_execute_phase
    received = []
    store.feedbackRaised.connect(lambda ftype, message: received.append(
        (ftype, message)))

    store._executeResolution()

    assert received, "失败必须发出 feedbackRaised"
    ftype, message = received[-1]
    assert ftype == "error"
    assert "DENIED" in message
    assert "无权执行" in message
    assert store._resolution_resolving is False
