"""
src/ui/gui/models/candidate_list_model.py
候选人列表模型 — 供 QML ListView 使用。
"""
from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex


class CandidateListModel(QAbstractListModel):
    """候选人列表模型。"""

    _ROLE_MAP = {
        0x0200: b"id",
        0x0201: b"name",
        0x0202: b"faction_id",
        0x0203: b"faction_name",
        0x0204: b"office",
        0x0205: b"office_name",
        0x0206: b"martial",
        0x0207: b"intelligence",
        0x0208: b"charisma",
        0x0209: b"zeal",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def setData(self, items: list):
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        key = self._ROLE_MAP.get(role)
        if key:
            return item.get(key.decode(), "")
        return None

    def roleNames(self):
        return self._ROLE_MAP
