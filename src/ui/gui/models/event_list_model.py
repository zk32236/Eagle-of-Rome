"""
src/ui/gui/models/event_list_model.py
事件/反馈列表模型 — 供 QML 底部反馈区使用。
"""
from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex


class EventListModel(QAbstractListModel):
    """事件/反馈列表模型。"""

    _ROLE_MAP = {
        0x0300: b"timestamp",
        0x0301: b"type",
        0x0302: b"message",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def append(self, event_type: str, message: str):
        import datetime
        self.beginInsertRows(QModelIndex(), len(self._items), len(self._items))
        self._items.append({
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            "type": event_type,
            "message": message,
        })
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
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
