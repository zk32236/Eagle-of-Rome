# src/core/entities/curia.py

from typing import List, Optional, Dict
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

    def __repr__(self) -> str:
        counts = {}
        for f in self.available_figures:
            tier = f.class_tier.value
            counts[tier] = counts.get(tier, 0) + 1
        count_str = ", ".join([f"{k}:{v}" for k, v in counts.items()])
        return f"Curia({len(self.available_figures)} figures: {count_str})"