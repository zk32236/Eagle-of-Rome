# MVP0.5-08 — 影响力/权力等级系统 Technical Mapping

## 1. 代码目录
```
src/core/entities/figure.py  # Figure: influence, rank, update_influence(), temp_influence_tasks
```

## 2. 核心公式
influence = base + family_bonus + office_bonus + temp_influence
base = land_private×10 + veterans×10 + popularity
family_bonus = family_prestige×10

## 3. 关键方法
- `update_influence()` — 重新计算影响力
- `add_temp_influence_task()` — 添加临时任务
- `decay_temp_influence_tasks()` — 衰减

## 4. 版本日志 | v1.0 | 2026-07-12 | 初版 |
