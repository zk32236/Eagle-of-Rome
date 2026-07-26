# MVP0.5-09 — 保民官否决权 Technical Mapping

## 1. 代码目录
```
src/core/deciders/tribune_veto_decider.py, impl/auto_tribune_veto_decider.py
src/core/systems/political_system.py  # 否决验证与结算
src/ui/commands/phase_senate.py       # 否决环节 UI
```

## 2. 核心规则
否决概率: tribune_veto_chance = 0.2 (20%)
实现: random.random() < chance

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
