"""
src/ui/gui/controllers/population_controller.py
人口阶段控制器 — 桥接 Python 逻辑与 QML 面板。
业务规则仍在 API 层，控制器只负责编排和数据转换。
"""
from PySide6.QtCore import QObject, Signal, Property, Slot

from src.ui.gui.session_store import GuiSessionStore


class PopulationController(QObject):
    """人口阶段控制器，供 PopulationStage.qml 使用。"""

    viewChanged = Signal()
    selectedFigureChanged = Signal()
    selectedCandidateChanged = Signal()

    def __init__(self, store: GuiSessionStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._selected_figure_id = 0
        self._selected_candidate = None  # {office, figure_id, name}
        self._campaign_amount = 0

        # 连接 store 信号
        store.populationViewChanged.connect(self.viewChanged.emit)

    # -----------------------------------------------------------------------
    # 选中人物
    # -----------------------------------------------------------------------
    @Property(int, notify=selectedFigureChanged)
    def selectedFigureId(self) -> int:
        return self._selected_figure_id

    @selectedFigureId.setter
    def selectedFigureId(self, value: int):
        if self._selected_figure_id != value:
            self._selected_figure_id = value
            self.selectedFigureChanged.emit()

    @Property(int, notify=selectedFigureChanged)
    def campaignAmount(self) -> int:
        return self._campaign_amount

    @campaignAmount.setter
    def campaignAmount(self, value: int):
        if self._campaign_amount != value:
            self._campaign_amount = value
            self.selectedFigureChanged.emit()

    @Slot(int, int, result=dict)
    def confirmCampaign(self, figure_id: int, amount: int) -> dict:
        """确认举办庆典"""
        return self._store.doCampaign(figure_id, amount)

    # -----------------------------------------------------------------------
    # 选中候选人
    # -----------------------------------------------------------------------
    @Property(dict, notify=selectedCandidateChanged)
    def selectedCandidate(self) -> dict:
        return self._selected_candidate or {}

    @Slot(str, int, str)
    def selectCandidate(self, office: str, figure_id: int, name: str):
        self._selected_candidate = {
            "office": office,
            "figure_id": figure_id,
            "name": name,
        }
        self.selectedCandidateChanged.emit()

    @Slot(result=dict)
    def confirmVote(self) -> dict:
        """确认投票"""
        if not self._selected_candidate:
            return {"success": False, "message": "未选择候选人"}
        return self._store.doVote(
            self._selected_candidate["office"],
            self._selected_candidate["figure_id"]
        )

    # -----------------------------------------------------------------------
    # 完成操作
    # -----------------------------------------------------------------------
    @Slot(result=dict)
    def completePlayer(self) -> dict:
        return self._store.doCompletePlayer()

    @Slot(result=dict)
    def resolveElection(self) -> dict:
        return self._store.doResolveElection()
