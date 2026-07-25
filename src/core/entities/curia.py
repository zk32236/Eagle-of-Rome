# src/core/entities/curia.py

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from .figure import Figure


@dataclass
class Curia:
    """
    广场等待区（Curia）

    存放等待被招募的人物：
    - 新出现的人物（Forum Phase 生成）
    - 被派系开除的人物
    - 从其他派系转投的人物（预留）
    """

    available_figures: List[Figure] = field(default_factory=list)
    recruited_history: List[Dict] = field(default_factory=list)

    def add_figure(self, figure: Figure):
        figure.is_available = True
        figure.faction_id = None
        self.available_figures.append(figure)

    def remove_figure(self, figure_id: int) -> Optional[Figure]:
        for idx, fig in enumerate(self.available_figures):
            if fig.id == figure_id:
                figure = self.available_figures.pop(idx)
                figure.is_available = False
                return figure
        return None

    def get_available_by_tier(self, tier: str) -> List[Figure]:
        return [f for f in self.available_figures if f.class_tier.value == tier]

    def get_all_available(self) -> List[Figure]:
        return self.available_figures.copy()

    def is_empty(self) -> bool:
        return len(self.available_figures) == 0

    def record_recruitment(self, figure: Figure, faction_id: str, turn: int):
        self.recruited_history.append({
            "figure_id": figure.id,
            "figure_name": figure.name,
            "faction_id": faction_id,
            "turn": turn,
            "tier": figure.class_tier.value
        })

    def clear(self):
        """清空所有等待人物（注意：调用者需同时从全局成员中移除）"""
        self.available_figures.clear()

    # ==================== 序列化方法 ====================

    def to_dict(self) -> Dict[str, Any]:
        """将 Curia 序列化为字典。串行化时只存人物ID，反序列化时由 GameState 解析引用。"""
        import copy
        return {
            "available_figure_ids": [f.id for f in self.available_figures],
            "recruited_history": copy.deepcopy(self.recruited_history),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Curia":
        """从字典重建 Curia 对象。

        Note: available_figures 不会被立即填充，而是存储 pending ID 列表。
        调用方（如 GameState.load_from_dict）需在成员加载完成后二次解析。
        """
        import copy
        curia = cls()
        curia.recruited_history = copy.deepcopy(data.get("recruited_history", []))
        curia._pending_figure_ids = list(data.get("available_figure_ids", []))
        return curia

    def __repr__(self) -> str:
        counts = {}
        for f in self.available_figures:
            tier = f.class_tier.value
            counts[tier] = counts.get(tier, 0) + 1
        count_str = ", ".join([f"{k}:{v}" for k, v in counts.items()])
        return f"Curia({len(self.available_figures)} figures: {count_str})"