# src/tests/test_gui/test_population_archive_gui_path.py
"""
WP-A GUI 归档路径集成测试（AU-11）。

验证 GUI 人口阶段入口（get_population_view / submit_population_votes /
resolve_population_slice）通过 begin_population_phase 共享用例触发官职归档，
与 CLI 行为对齐；同阶段多次进入不重复归档（R3.3，multi-HUMAN handoff 安全）。
"""
import pytest

from src.api import session_api, population_api


def _make_population_session():
    """创建生产等价 population 阶段会话，返回 (state, viewer_id)。"""
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer_id = result["data"]["human_players"][0]
    return state, viewer_id


def _seed_current_consul(state):
    """在 state 中设置一个现任执政官（模拟上回合当选者），返回该人物。"""
    fig = next(f for f in state.get_living_members() if not f.is_absent)
    fig.office = "consul"
    fig.is_absent = False
    if fig.id not in state.turn.leader_ids:
        state.turn.leader_ids.append(fig.id)
    return fig


class TestPopulationArchiveGuiPath:
    """GUI resolve 路径归档 + 重复进入不重复归档。"""

    def test_gui_resolve_path_archives_office_holders(self):
        """GUI 完整流（get_population_view）后：现任者 ex-*、history 增长、marker 置位。"""
        state, viewer_id = _make_population_session()
        fig = _seed_current_consul(state)
        hist_before = len(fig.office_history)

        view = session_api.get_population_view(state, viewer_id)
        assert view.get("success"), view.get("message")

        assert fig.office == "ex-consul"
        assert len(fig.office_history) == hist_before + 1
        # marker 置位（幂等守卫）
        marker = state.get_phase_result("population_entry")
        assert isinstance(marker, dict) and "archived" in marker

    def test_gui_repeated_view_no_double_archive(self):
        """同阶段多次 get_population_view 不重复归档（multi-HUMAN handoff 安全）。"""
        state, viewer_id = _make_population_session()
        fig = _seed_current_consul(state)

        session_api.get_population_view(state, viewer_id)
        hist_after_first = len(fig.office_history)
        assert fig.office == "ex-consul"

        # 再次刷新（第二个 HUMAN 玩家打开视图 / 无头轮询）
        session_api.get_population_view(state, viewer_id)
        session_api.get_population_view(state, viewer_id)

        assert fig.office == "ex-consul"
        assert len(fig.office_history) == hist_after_first
