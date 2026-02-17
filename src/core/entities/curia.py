# src/core/entities/curia.py

from typing import List, Optional, Dict
from dataclasses import dataclass, field
# 修改导入：从绝对导入改为相对导入
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

    # 等待中的人物
    available_figures: List[Figure] = field(default_factory=list)

    # 历史记录（已招募的人物）
    recruited_history: List[Dict] = field(default_factory=list)

    def add_figure(self, figure: Figure):
        """添加人物到等待区"""
        figure.is_available = True
        figure.faction_id = None  # 无派系归属
        self.available_figures.append(figure)

    def remove_figure(self, figure_id: int) -> Optional[Figure]:
        """从等待区移除人物（被招募）"""
        for idx, fig in enumerate(self.available_figures):
            if fig.id == figure_id:
                figure = self.available_figures.pop(idx)
                figure.is_available = False
                return figure
        return None

    def get_available_by_tier(self, tier: str) -> List[Figure]:
        """按阶层筛选人物"""
        return [f for f in self.available_figures
                if f.class_tier.value == tier]

    def get_all_available(self) -> List[Figure]:
        """获取所有可用人物"""
        return self.available_figures.copy()

    def is_empty(self) -> bool:
        """检查是否为空"""
        return len(self.available_figures) == 0

    def record_recruitment(self, figure: Figure, faction_id: str, turn: int):
        """记录招募历史"""
        self.recruited_history.append({
            "figure_id": figure.id,
            "figure_name": figure.name,
            "faction_id": faction_id,
            "turn": turn,
            "tier": figure.class_tier.value
        })

    def __repr__(self) -> str:
        counts = {}
        for f in self.available_figures:
            tier = f.class_tier.value
            counts[tier] = counts.get(tier, 0) + 1

        count_str = ", ".join([f"{k}:{v}" for k, v in counts.items()])
        return f"Curia({len(self.available_figures)} figures: {count_str})"