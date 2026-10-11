# MVP0.7-10 — 战争卡-大规模战争（技术映射）

## 1. 代码目录
```
src/core/systems/war_system.py   # load_wars_from_json(), check_triggers(), escalate_threats()
                                 # + compute_reward_settlement()/resolve_war() (EOR20261009-03)
src/core/entities/war.py         # War 实体 + 新字段（含 _reward_receipt）
data/cards/wars.json              # 战争卡数据（rewards.influence 权威来源）
```

## 2. 关键算法
威胁升级: THREAT level 1→2→3 → ACTIVE

## 2.1 战争卡 rewards / influence 处置（EOR20261009-03 / OD-05，FC-07）
- `War.calculate_rewards()` 返回卡 `rewards` 字典逐字副本（`treasury`/`land`/`family_prestige`/`influence`）。
- `rewards.influence` = **ACTIVE**：`WarSystem.resolve_war` 成功分支写入 `commander._war_reward_influence += rewards.influence` → `Figure.update_influence()`（`_compute_influence` 第 7 参数）。

## 3. 版本日志
| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | — | 初版 |
| v1.1 | 2026-10-11 | DA-Exec (EOR20261009-03 WRRI) | `rewards.influence` = ACTIVE（授予指挥官持久 `_war_reward_influence`）；§2.1 note |
