"""
src/ui/gui/models/figure_list_model.py
人物列表模型 — 供 QML ListView 使用。
"""
from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex


class FigureListModel(QAbstractListModel):
    """本派系人物列表模型。"""

    _ROLE_MAP = {
        0x0100: b"id",
        0x0101: b"name",
        0x0102: b"wealth",
        0x0103: b"popularity",
        0x0104: b"influence",
        0x0105: b"office",
        0x0106: b"is_faction_leader",
        0x0107: b"class_tier",
        0x0108: b"age",
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
