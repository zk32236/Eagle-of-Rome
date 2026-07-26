# MVP0.3-02 — 战争系统（技术映射）

## 1. 代码目录
```
src/core/systems/war_system.py, naval_system.py
src/core/entities/war.py, legion.py
src/core/deciders/peace_treaty_decider.py, impl/auto_peace_treaty_decider.py
src/ui/commands/phase_combat.py
```

## 2. 关键模块
- `war_system.py` — 战争激活、结算、指派、停战、惩罚
- `war.py` — War 实体 + WarStatus/WarType 枚举
- `phase_combat.py` — 战斗阶段命令 + CRT + 草案生成

## 3. 核心算法
CRT 判定: combat_total = 2d6 + commander.martial + sum(legion_strengths) - war.strength
结果: DISASTER / TRIUMPH / VICTORY / STALEMATE / DEFEAT

## 4. 版本日志
| v1.0 | 2026-07-12 | 初版 |
