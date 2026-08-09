"""WP-02b v3.0 FV-22~FV-26 real Qt/QML interaction regressions."""
import os
import sys
from dataclasses import dataclass
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, QSize, Qt, QUrl, Slot
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest

from src.api import population_api, session_api
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.ui.gui.models.candidate_list_model import CandidateListModel
from src.ui.gui.models.event_list_model import EventListModel
from src.ui.gui.models.figure_list_model import FigureListModel
from src.ui.gui.session_store import GuiSessionStore


OFFICES = ("consul", "censor", "praetor", "quaestor", "tribune")
DENIED_UI_TEXT = (
    "不投（弃权）",
    "未选择的官职将自动记为弃权",
    "已选择 N/5",
)


class _DummyGuiApp(QObject):
    @Slot(str, result=bool)
    def confirmHandoff(self, next_player_id: str) -> bool:
        return bool(next_player_id)


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _process_events(rounds=4):
    assert rounds > 0
    for _ in range(rounds):
        QGuiApplication.processEvents()
        QTest.qWait(10)


def _add_deterministic_candidates(state, faction_id):
    """Add public-state fixture candidates covering all five cursus-honorum offices."""
    specs = [
        (9101, "praetor", "charisma"),
        (9102, "praetor", "charisma"),
        (9103, "consul", "zeal"),
        (9104, "consul", "zeal"),
        (9105, "quaestor", "intelligence"),
        (9106, "quaestor", "intelligence"),
        (9107, None, "martial"),
        (9108, None, "martial"),
    ]
    assert len(specs) == 8
    for figure_id, history, qualification in specs:
        assert state.get_member(figure_id) is None
        figure = Figure.create_nobile_with_history(
            figure_id,
            faction_id,
            previous_office=history,
            age=50,
        )
        setattr(figure, qualification, 100)
        state.add_member(figure)
    for figure_id in (9109, 9110):
        assert state.get_member(figure_id) is None
        figure = Figure.create_eques(figure_id, faction_id, 40)
        figure.martial = -100
        state.add_member(figure)

    result = population_api.get_candidates(state)
    assert result["success"] is True
    by_office = result["data"]
    assert len(by_office) == 5
    assert set(by_office) == set(OFFICES)
    assert all(len(by_office[office]) >= 1 for office in OFFICES)


@dataclass
class _Runtime:
    engine: QQmlApplicationEngine
    window: QWindow
    state: object
    store: GuiSessionStore
    viewer_id: str
    human_ids: list

    def close(self):
        self.window.close()
        _process_events(1)


def _build_runtime(*, campaign_done, one_human_with_ai=False,
                   hotseat_compat=False, compact=False):
    _app()
    result = session_api.create_gui_prototype_session(start_phase="population")
    assert result["success"] is True, result
    state = result["data"]["state"]
    human_ids = list(result["data"]["human_players"])
    assert len(human_ids) == 1
    viewer_id = human_ids[0]
    viewer = state.get_player(viewer_id)
    assert viewer is not None
    assert viewer.player_type == PlayerType.HUMAN

    _add_deterministic_candidates(state, viewer.faction_id)
    players = state.get_all_players()
    assert len(players) == 3
    assert [player.player_type for player in players] == [
        PlayerType.HUMAN, PlayerType.AI, PlayerType.AI
    ]
    all_player_ids = [player.player_id for player in players]

    # Compatibility fixture: recreate the former 3-HUMAN hot-seat state.
    # FV-26 then migrates that legacy shape back to production 1H+2AI.
    if hotseat_compat or one_human_with_ai:
        for player_id in all_player_ids[1:]:
            original = state.get_player(player_id)
            assert original is not None
            assert state.remove_player(player_id) is True
            state.add_player(Player(
                player_id=player_id,
                faction_id=original.faction_id,
                player_type=PlayerType.HUMAN,
            ))

        human_ids = list(all_player_ids)

    if one_human_with_ai:
        for player_id in human_ids[1:]:
            original = state.get_player(player_id)
            assert original is not None
            assert state.remove_player(player_id) is True
            state.add_player(Player(
                player_id=player_id,
                faction_id=original.faction_id,
                player_type=PlayerType.AI,
            ))
        players = state.get_all_players()
        assert len(players) == 3
        assert [player.player_type for player in players] == [
            PlayerType.HUMAN, PlayerType.AI, PlayerType.AI
        ]
        human_ids = [viewer_id]
    elif hotseat_compat:
        players = state.get_all_players()
        assert len(players) == 3
        assert all(player.player_type == PlayerType.HUMAN for player in players)

    state.set_turn_order(all_player_ids)
    assert state.set_current_player(viewer_id) is True
    state.set_batch_completed(viewer_id, campaign_done)

    store = GuiSessionStore(state)
    store.initialize(viewer_id)
    assert store.currentPhaseId == "population"
    assert store.selectedPhaseId == "population"
    assert store.populationCurrentStep == ("vote" if campaign_done else "campaign")

    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)
    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None
    gui_app = _DummyGuiApp()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", gui_app)
    engine._test_refs = (store, theme, gui_app)

    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    roots = engine.rootObjects()
    assert len(roots) == 1
    window = roots[0]
    assert isinstance(window, QWindow)
    window.resize(QSize(1000, 900) if compact else QSize(1440, 1400))
    window.show()
    _process_events(6)
    assert window.isVisible()

    runtime = _Runtime(engine, window, state, store, viewer_id, human_ids)
    stage = _find(runtime, "populationStage")
    assert stage.property("visible") is True
    offices = _variant(stage.property("offices"))
    assert isinstance(offices, list)
    assert offices == list(OFFICES)
    assert len(store.populationCandidates) >= 5
    return runtime


@pytest.fixture
def runtime_factory(request):
    runtimes = []

    def factory(**kwargs):
        runtime = _build_runtime(**kwargs)
        runtimes.append(runtime)
        return runtime

    yield factory
    for runtime in reversed(runtimes):
        runtime.close()


def _visual_items(runtime):
    pending = [runtime.window.contentItem()]
    while pending:
        item = pending.pop()
        yield item
        pending.extend(item.childItems())


def _find(runtime, object_name):
    item = next(
        (candidate for candidate in _visual_items(runtime)
         if candidate.objectName() == object_name),
        None,
    )
    if item is None:
        item = runtime.window.findChild(QObject, object_name)
    assert item is not None, f"{object_name} not found"
    return item


def _variant(value):
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    elif hasattr(value, "toPython"):
        value = value.toPython()
    return value


def _selected_votes(runtime):
    stage = _find(runtime, "populationStage")
    selected = _variant(stage.property("selectedVotes"))
    assert isinstance(selected, dict), type(selected)
    return selected


def _candidate_rows(runtime):
    rows = list(runtime.store.populationCandidates)
    assert len(rows) >= 5
    by_office = {}
    for office in OFFICES:
        office_rows = [row for row in rows if row.get("office") == office]
        assert len(office_rows) >= 1, office
        by_office[office] = office_rows[0]
    assert len(by_office) == 5
    return by_office


def _candidate_control(runtime, row):
    figure_id = row["id"]
    office = row["office"]
    assert isinstance(figure_id, int) and figure_id > 0
    object_name = f"populationVoteCandidate_{office}_{figure_id}"
    item = next(
        (candidate for candidate in _visual_items(runtime)
         if candidate.objectName() == object_name),
        None,
    )
    if item is None:
        visual_items = list(_visual_items(runtime))
        candidate_names = sorted(
            obj.objectName()
            for obj in visual_items
            if "populationVoteCandidate_" in obj.objectName()
        )
        office_groups = {
            obj.objectName(): _variant(obj.property("rows"))
            for obj in visual_items
            if "populationVoteOffice_" in obj.objectName()
        }
        pytest.fail(
            f"{object_name} not found; instantiated={candidate_names}; "
            f"office_groups={office_groups}"
        )
    return item


def _scene_center(item):
    width = float(item.property("width"))
    height = float(item.property("height"))
    assert width > 0
    assert height > 0
    point = item.mapToScene(QPointF(width / 2.0, height / 2.0))
    return QPoint(round(point.x()), round(point.y()))


def _click(runtime, item):
    assert item.property("visible") is True
    assert item.property("enabled") is True
    point = _scene_center(item)
    assert 0 <= point.x() < runtime.window.width()
    assert 0 <= point.y() < runtime.window.height()
    QTest.mouseClick(
        runtime.window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    _process_events()


def _qml_signal_spy(obj, signature):
    if isinstance(signature, bytes):
        signature = signature.decode("ascii")
    index = obj.metaObject().indexOfSignal(signature)
    assert index >= 0, signature
    method = obj.metaObject().method(index)
    spy = QSignalSpy(obj, method)
    assert spy.isValid()
    return spy


def _visible_texts(runtime):
    stage = _find(runtime, "populationStage")
    texts = []
    objects = [stage] + stage.findChildren(QObject)
    assert len(objects) > 1
    for obj in objects:
        text = obj.property("text")
        visible = obj.property("visible")
        if isinstance(text, str) and text and visible is not False:
            texts.append(text)
    assert len(texts) > 0
    return texts


def _assert_denied_ui_absent(runtime):
    texts = _visible_texts(runtime)
    combined = "\n".join(texts)
    assert len(combined) > 0
    for denied in DENIED_UI_TEXT:
        assert denied not in combined


def _click_resolve(runtime):
    button = _find(runtime, "populationResolveButton")
    assert button.property("buttonEnabled") is True
    _click(runtime, button)


def test_fv22_vote_button_and_selected_votes_notifications(runtime_factory):
    locked = runtime_factory(campaign_done=False)
    locked_button = _find(locked, "populationResolveButton")
    assert _selected_votes(locked) == {}
    assert locked.store.canVote is False
    assert locked_button.property("buttonEnabled") is False

    runtime = runtime_factory(campaign_done=True)
    button = _find(runtime, "populationResolveButton")
    stage = _find(runtime, "populationStage")
    rows = _candidate_rows(runtime)
    assert runtime.store.canVote is True
    assert runtime.store.populationResolved is False
    assert runtime.store.populationVoteSubmitting is False
    assert _selected_votes(runtime) == {}
    assert button.property("buttonEnabled") is True
    changed = _qml_signal_spy(stage, b"selectedVotesChanged()")

    for expected_count, office in enumerate(OFFICES, start=1):
        before = changed.count()
        _click(runtime, _candidate_control(runtime, rows[office]))
        selected = _selected_votes(runtime)
        assert changed.count() == before + 1
        assert len(selected) == expected_count
        assert set(selected) == set(OFFICES[:expected_count])
        assert all(isinstance(value, int) and value > 0 for value in selected.values())
        assert button.property("buttonEnabled") is True
    assert changed.count() == 5
    _assert_denied_ui_absent(runtime)

    submitting_observation = []

    def observe_submitting(_player_id, _selections):
        _process_events(1)
        submitting_observation.append(button.property("buttonEnabled"))
        return {
            "success": False,
            "message": "fixture failure",
            "data": {},
            "errors": [{"code": "FIXTURE", "message": "fixture failure"}],
        }

    with patch.object(runtime.store._adapter, "submit_population_votes", side_effect=observe_submitting):
        response = runtime.store.submitPopulationVotes({})
    assert response["success"] is False
    assert submitting_observation == [False]
    assert runtime.store.populationVoteSubmitting is False

    runtime.state.record_phase_result("population", {
        "success": True,
        "message": "fixture resolved",
        "data": {"election_results": []},
    })
    runtime.store.refreshSnapshot()
    _process_events()
    assert runtime.store.populationResolved is True
    assert button.property("buttonEnabled") is False


def test_fv23_single_click_calls_store_once_and_normalizes_five_entries(runtime_factory):
    runtime = runtime_factory(campaign_done=True)
    rows = _candidate_rows(runtime)
    for office in ("consul", "praetor"):
        _click(runtime, _candidate_control(runtime, rows[office]))
    selected = _selected_votes(runtime)
    assert len(selected) == 2
    assert set(selected) == {"consul", "praetor"}

    with patch.object(
        runtime.store._adapter,
        "submit_population_votes",
        wraps=runtime.store._adapter.submit_population_votes,
    ) as adapter_spy, patch.object(
        session_api.population_api,
        "batch_vote",
        wraps=session_api.population_api.batch_vote,
    ) as backend_spy:
        _click_resolve(runtime)

    assert adapter_spy.call_count == 1
    assert backend_spy.call_count == 1
    call_args = backend_spy.call_args.args
    assert len(call_args) == 3
    entries = call_args[2]
    assert isinstance(entries, list)
    assert len(entries) == 5
    offices = [entry["office"] for entry in entries]
    assert len(offices) == 5
    assert len(set(offices)) == 5
    assert set(offices) == set(OFFICES)
    assert _selected_votes(runtime) == selected


def test_fv24_partial_selection_materializes_three_abstentions(runtime_factory):
    runtime = runtime_factory(campaign_done=True)
    _assert_denied_ui_absent(runtime)
    rows = _candidate_rows(runtime)
    chosen = {"consul": rows["consul"]["id"], "praetor": rows["praetor"]["id"]}
    assert len(chosen) == 2
    for office in chosen:
        _click(runtime, _candidate_control(runtime, rows[office]))

    with patch.object(
        session_api.population_api,
        "batch_vote",
        wraps=session_api.population_api.batch_vote,
    ) as backend_spy:
        _click_resolve(runtime)

    assert backend_spy.call_count == 1
    entries = backend_spy.call_args.args[2]
    assert len(entries) == 5
    by_office = {entry["office"]: entry["figure_id"] for entry in entries}
    assert len(by_office) == 5
    assert by_office["consul"] == chosen["consul"]
    assert by_office["praetor"] == chosen["praetor"]
    assert sum(1 for value in by_office.values() if value == 0) == 3
    assert sum(1 for value in by_office.values() if value > 0) == 2
    votes = [vote for vote in runtime.state.get_population_votes() if vote[0] == runtime.viewer_id]
    assert len(votes) == 5
    assert runtime.state.get_vote_completed(runtime.viewer_id) is True


def test_fv24_empty_selection_materializes_five_abstentions(runtime_factory):
    runtime = runtime_factory(campaign_done=True)
    _assert_denied_ui_absent(runtime)
    assert _selected_votes(runtime) == {}

    with patch.object(
        session_api.population_api,
        "batch_vote",
        wraps=session_api.population_api.batch_vote,
    ) as backend_spy:
        _click_resolve(runtime)

    assert backend_spy.call_count == 1
    entries = backend_spy.call_args.args[2]
    assert len(entries) == 5
    assert len({entry["office"] for entry in entries}) == 5
    assert set(entry["office"] for entry in entries) == set(OFFICES)
    assert all(entry["figure_id"] == 0 for entry in entries)
    votes = [vote for vote in runtime.state.get_population_votes() if vote[0] == runtime.viewer_id]
    assert len(votes) == 5
    assert all(vote[2] == 0 for vote in votes)
    assert runtime.state.get_vote_completed(runtime.viewer_id) is True


def _drag_up(runtime, flickable):
    width = float(flickable.property("width"))
    height = float(flickable.property("height"))
    assert width > 40
    assert height > 60
    top_left = flickable.mapToScene(QPointF(0, 0))
    x = round(top_left.x() + width / 2.0)
    start_y = round(top_left.y() + height - 15)
    end_y = round(top_left.y() + 15)
    start = QPoint(x, start_y)
    middle = QPoint(x, round((start_y + end_y) / 2.0))
    end = QPoint(x, end_y)
    assert 0 <= x < runtime.window.width()
    assert 0 <= end_y < start_y < runtime.window.height()
    QTest.mousePress(runtime.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(runtime.window, middle, delay=25)
    QTest.mouseMove(runtime.window, end, delay=25)
    QTest.mouseRelease(runtime.window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    _process_events()


def test_fv25_two_scrollbars_and_hidden_office_mouse_interaction(runtime_factory):
    runtime = runtime_factory(campaign_done=True, compact=True)
    campaign_flick = _find(runtime, "populationCampaignFlickable")
    vote_flick = _find(runtime, "populationVoteFlickable")
    campaign_bar = _find(runtime, "populationCampaignScrollBar")
    vote_bar = _find(runtime, "populationVoteScrollBar")
    pairs = ((campaign_flick, campaign_bar), (vote_flick, vote_bar))
    assert len(pairs) == 2
    for flickable, scrollbar in pairs:
        content_height = float(flickable.property("contentHeight"))
        viewport_height = float(flickable.property("height"))
        assert viewport_height > 0
        assert content_height > viewport_height
        size = float(scrollbar.property("size"))
        visual_size = float(scrollbar.property("visualSize"))
        details = {
            "name": scrollbar.objectName(),
            "content_height": content_height,
            "viewport_height": viewport_height,
            "size": size,
            "visual_size": visual_size,
            "visible": scrollbar.property("visible"),
            "width": scrollbar.property("width"),
            "height": scrollbar.property("height"),
        }
        assert 0.0 < size < 1.0, details
        assert 0.0 < visual_size < 1.0, details
        assert scrollbar.property("visible") is True, details

    rows = _candidate_rows(runtime)
    target = _candidate_control(runtime, rows["tribune"])
    flick_top_left = vote_flick.mapToScene(QPointF(0, 0))
    viewport_top = flick_top_left.y()
    viewport_bottom = viewport_top + float(vote_flick.property("height"))
    target_before = target.mapToScene(QPointF(0, float(target.property("height")) / 2.0)).y()
    assert target_before > viewport_bottom
    initial_content_y = float(vote_flick.property("contentY"))
    assert initial_content_y == 0.0

    for _ in range(6):
        _drag_up(runtime, vote_flick)
    QTest.qWait(500)
    _process_events(6)
    assert vote_flick.property("moving") is False
    assert vote_flick.property("flicking") is False
    final_content_y = float(vote_flick.property("contentY"))
    assert final_content_y > initial_content_y
    target_after = target.mapToScene(QPointF(0, float(target.property("height")) / 2.0)).y()
    assert viewport_top <= target_after <= viewport_bottom
    _click(runtime, target)
    selected = _selected_votes(runtime)
    assert len(selected) == 1
    assert set(selected) == {"tribune"}
    assert selected["tribune"] == rows["tribune"]["id"]
    assert target.property("checked") is True
    assert _find(runtime, "populationResolveButton").property("buttonEnabled") is True


def _removed_bug3_fv26_one_human_ai_click_resolves_once(runtime_factory):
    runtime = runtime_factory(campaign_done=True, one_human_with_ai=True)
    players = runtime.state.get_all_players()
    assert len(players) == 3
    assert [player.player_type for player in players] == [
        PlayerType.HUMAN, PlayerType.AI, PlayerType.AI
    ]
    assert _selected_votes(runtime) == {}

    with patch.object(
        population_api,
        "resolve_election",
        wraps=population_api.resolve_election,
    ) as resolve_spy:
        _click_resolve(runtime)

    assert resolve_spy.call_count == 1
    assert runtime.state.get_phase_result("population") is not None
    assert runtime.store.populationResolved is True
    results = runtime.store.populationElectionResults
    assert isinstance(results, list)
    assert len(results) > 0
    assert runtime.store.canAdvancePopulation is True
    announcement = _find(runtime, "populationAnnouncement")
    assert announcement.property("visible") is True


def test_fv26_multi_human_click_handoffs_without_resolve(runtime_factory):
    runtime = runtime_factory(campaign_done=True, hotseat_compat=True)
    players = runtime.state.get_all_players()
    assert len(players) == 3
    assert all(player.player_type == PlayerType.HUMAN for player in players)
    handoff_spy = QSignalSpy(runtime.store.handoffRequired)
    assert handoff_spy.isValid()

    with patch.object(
        population_api,
        "resolve_election",
        wraps=population_api.resolve_election,
    ) as resolve_spy:
        _click_resolve(runtime)

    assert resolve_spy.call_count == 0
    assert handoff_spy.count() == 1
    assert runtime.state.get_phase_result("population") is None
    assert runtime.state.get_current_player().player_id == runtime.human_ids[1]
    assert runtime.store.viewerPlayerId == runtime.human_ids[1]
    assert runtime.store.populationResolved is False
    assert runtime.store.canAdvancePopulation is False
