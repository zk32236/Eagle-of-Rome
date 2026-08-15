"""Regression test — WP-05V G5 senate layout fix.

Guards the DA layout fix for the two G5 visual defects:
1. Result-state overflow: header + result area + three-column panel must fit
   inside the stageContent slot (no clipping past the container).
2. Candidate crowding: GovernorAppointmentPanel must be hidden in the results
   step (redundant with the result summary) so column 1 fits.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, qmlRegisterType

from src.api import session_api
from src.ui.gui.models.candidate_list_model import CandidateListModel
from src.ui.gui.models.event_list_model import EventListModel
from src.ui.gui.models.figure_list_model import FigureListModel
from src.ui.gui.session_store import GuiSessionStore


def _drive_to_results(store):
    """Mirror _fixture_senate_v4_result using production APIs only."""
    from src.core.deciders.impl.auto_peace_treaty_decider import AutoPeaceTreatyDecider
    from src.core.entities.contract import ContractType

    state = store._state
    ws = state.get_war_system()
    ws.check_triggers(-282)
    ws.check_triggers(-279)
    state.conquer_provinces("first_punic_war")
    war_fpw = ws.get_war_by_id("first_punic_war")
    treaty = AutoPeaceTreatyDecider().decide_treaty(war_fpw, "STALEMATE", state)
    ws.enter_truce(war_fpw, treaty)
    state.create_contract(ContractType.PUBLIC_WORKS, 1, 120, state.turn.turn_number)
    state.create_contract(ContractType.TAX_FARMING, 1, 80, state.turn.turn_number)
    store.selectPhase("population")
    selection_map = {}
    for office in ("consul", "censor", "praetor", "quaestor", "tribune"):
        for c in store.populationCandidates:
            if c.get("office") == office:
                selection_map[office] = int(c.get("id"))
                break
    store.submitPopulationVotes(selection_map)
    store.selectPhase("senate")
    proposals = store.senateProposalOptions or []
    if proposals:
        store.doSubmitSenateProposals(proposals)
    store.doSubmitSenateVotes()
    store.doSubmitSenateVetoes([])


def test_senate_results_layout_fits_stage_content():
    app = QGuiApplication.instance() or QGuiApplication([])
    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    store = GuiSessionStore(result["data"]["state"])
    store.initialize(result["data"]["human_players"][0])

    qml_dir = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
    engine = QQmlApplicationEngine()
    engine.addImportPath(qml_dir)
    qmlRegisterType(FigureListModel, "EOR.Models", 1, 0, "FigureListModel")
    qmlRegisterType(CandidateListModel, "EOR.Models", 1, 0, "CandidateListModel")
    qmlRegisterType(EventListModel, "EOR.Models", 1, 0, "EventListModel")

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(qml_dir, "theme", "Theme.qml")))
    theme = theme_component.create()
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("sessionStore", store)
    engine.rootContext().setContextProperty("guiApp", None)

    engine.load(QUrl.fromLocalFile(os.path.join(qml_dir, "Main.qml")))
    QGuiApplication.processEvents()
    root = engine.rootObjects()[0]

    _drive_to_results(store)
    store.selectPhase("senate")
    QGuiApplication.processEvents()
    assert store.senateCurrentStep == "results"

    senate = root.findChild(QObject, "senateStage")
    assert senate is not None
    stage_height = senate.property("height")
    assert stage_height > 0

    # The three SenateWorkPanel columns must not overflow the senate stage.
    work_panels = [
        child for child in senate.findChildren(QObject)
        if child.metaObject().className() == "SenateWorkPanel"
    ]
    assert len(work_panels) == 3, f"expected 3 SenateWorkPanel, got {len(work_panels)}"

    # A panel overflows if its bottom edge exceeds the stage height (+1px slack).
    for panel in work_panels:
        y = panel.property("y")
        h = panel.property("height")
        assert y + h <= stage_height + 1, \
            f"column overflows stage: y={y} h={h} stage={stage_height}"

    # Governor panel must be hidden in the results step (redundant with summary).
    gov_panels = [
        child for child in senate.findChildren(QObject)
        if child.metaObject().className().startswith("GovernorAppointmentPanel")
    ]
    for panel in gov_panels:
        assert panel.property("visible") is False, "governor panel should be hidden in results"
