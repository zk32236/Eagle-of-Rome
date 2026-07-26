# MVP0.7-10 — 战争卡-大规模战争（技术映射）

## 1. 代码目录
```
src/core/systems/war_system.py   # load_wars_from_json(), check_triggers(), escalate_threats()
src/core/entities/war.py         # War 实体 + 新字段
data/cards/wars.json              # 战争卡数据
```

## 2. 关键算法
威胁升级: THREAT level 1→2→3 → ACTIVE

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
