# MVP0.5-08 — 影响力/权力等级系统 Technical Mapping

## 1. 代码目录
```
src/core/entities/figure.py  # Figure: influence, rank, update_influence(), temp_influence_tasks
```

## 2. 核心公式
influence = base + family_bonus + office_bonus + temp_influence
base = land_private×10 + veterans×10 + popularity
family_bonus = family_prestige×10

> **WP-E-G7R（2026-08-24）：公式已提取为模块级纯函数**
> `figure._compute_influence(land_private, veterans, popularity, family_prestige, office_bonus, temp_influence) -> int`
> ——`update_influence()` 内部改为调用该纯函数后再写 `_influence`（**对外行为逐字节零变化**）；
> resolution preview 派系聚合（`session_api._build_resolution_preview`）复用同一纯函数
> 做只读重算（decay-only，ODR-C1），杜绝第二套公式实现（R-23）。

## 3. 关键方法
- `update_influence()` — 重新计算影响力（内部调用 `_compute_influence` 纯函数，行为不变）
- `_compute_influence()` — **模块级纯函数（WP-E-G7R 新增）**：只读算术，零变异；
  update_influence 与 preview 共享
- `add_temp_influence_task()` — 添加临时任务
- `decay_temp_influence_tasks()` — 衰减

## 4. 版本日志
| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.1 | 2026-08-24 | DA-Exec (WP-E-G7R) | §2/§3：update_influence 公式提取为 _compute_influence 纯函数（行为零变化）；preview 派系聚合复用（R-23） |
| v1.0 | 2026-07-12 | — | 初版 |
