# MVP0.7-00 — 行省总督任命（技术映射）

## 1. 代码目录
```
src/core/entities/province.py         # 总督字段+交接方法
src/core/systems/political_system.py  # 资格校验+提案执行
src/ui/commands/phase_senate.py       # 提名UI + AI自动提名
```

## 2. 关键方法
- `get_eligible_governor_candidates()` — 资格校验
- `set_governor_designate()` — 设置候任总督
- `complete_governor_transition()` — 决算阶段交接

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
