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

## 3. 版本日志 | v1.0 | 2026-07-13 | 初版 |
