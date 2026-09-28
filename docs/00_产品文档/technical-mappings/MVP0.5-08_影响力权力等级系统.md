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

## 3.1 双排序显式分离（WP-M D1，2026-09-28）

> 权威契约：WP-M SA-Design v1.5 §4 D1。代码落点 `src/core/entities/figure.py`。

| 常量 | 语义 | 值 | 用途 |
|:---|:---|:---|:---|
| `Figure.OFFICE_RANK` | **权力顺序（高→低）** | `dictator=6 > consul=5 > censor=4 > praetor=3 > quaestor=2 > tribune=1` | 元老院主持序列（`GameState.get_presiding_officer`）；非降级资格。**数值 WP-M 不变** |
| `Figure.OFFICE_PROMOTION_ORDER`（新增） | **升级顺序（低→高）** | `tribune=1 < quaestor=2 < praetor=3 < consul=4 < censor=5` | cursus honorum 阶梯语义；**不得**用于主持序列 |
| `Figure.OFFICE_CURSUS_PREREQUISITE`（新增） | 由升级顺序派生的 cursus 前置映射 | `{praetor: quaestor, consul: praetor, censor: consul}` | `can_hold_office` 前置检查（行为等价重构）；**`OFFICE_RANK` 不得用于前置派生** |

- 两序不可混用；`OFFICE_PROMOTION_ORDER` 派生规则：位置 i≥3 的官职前置 = 阶梯 i-1 位；`{tribune, quaestor}` 无前置（tribune 仅阶层门控）。
- 结果与 WP-M 前实现逐字符等价（`praetor←quaestor` / `consul←praetor` / `censor←consul`）；既有资格测试保持绿。
- `Figure.OFFICE_INFLUENCE_BONUS`（影响力加成）为**独立轴**，与两序无关，WP-M 未改动。

## 4. 版本日志
| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-09-28 | DA-Exec (WP-M M-S1) | §3.1 双排序显式分离：`OFFICE_PROMOTION_ORDER`/`OFFICE_CURSUS_PREREQUISITE` 新增（行为等价重构），`OFFICE_RANK` 数值不变（D1） |
| v1.1 | 2026-08-24 | DA-Exec (WP-E-G7R) | §2/§3：update_influence 公式提取为 _compute_influence 纯函数（行为零变化）；preview 派系聚合复用（R-23） |
| v1.0 | 2026-07-12 | — | 初版 |
