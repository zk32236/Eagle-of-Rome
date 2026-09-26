# MVP0.5-17-sys — 自动招募/庆典/淘汰决策器（技术映射）

## 1. 代码目录
```
src/core/deciders/recruitment_decider.py, festival_decider.py, retirement_decider.py
src/core/deciders/impl/auto_recruitment_decider.py, auto_festival_decider.py, auto_retirement_decider.py
```

## 2. 关键方法
- `AutoRecruitmentDecider.decide_bids()` — 随机出价招募
- `AutoFestivalDecider.decide_festivals()` — 随机庆典花费
- `AutoRetirementDecider.decide_whom_to_retire()` — 概率淘汰

> **入参对齐（WP-I 2026-09-26）：** 招募决策器的 `vacancies` 由处理器传入 = 该派系
> **权威剩余招募槽位**（`GameState.get_remaining_recruitment_slots()`）；不再使用固定容量参数。
> 决策器策略零改（`selected = eligible[:vacancies]`）。

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-09-26 | WP-I：`vacancies` 入参对齐权威剩余招募槽位（策略不变） |
| v1.0 | 2026-07-13 | 初版 |
