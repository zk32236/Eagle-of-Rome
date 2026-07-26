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

## 4. Wave-03 新增方法

### 4.1 `assign_rebellion_commanders() -> list[dict]`
- **用途：** 为所有活跃起义指派指挥官（C-10b）
- **CLI 来源：** `phase_senate.py` L1348-1408
- **返回：** `[{rebellion_id, commander_id, name, assigned_at}]`
- **日志：** DBUG（每起义/每选择）+ INFO（指派）

### 4.2 `auto_recruit_and_assign() -> list[dict]`
- **用途：** 自动征召军团并指派至战区（C-10d）
- **CLI 来源：** `phase_senate.py` L1642-1708
- **返回：** `[{legion_id, legion_name, assigned_to, assigned_at}]`
- **日志：** DBUG（需求评估/征召）+ INFO（指派结果）

## 5. Wave-04 Finale 新增方法

### 5.1 `process_triumph_and_disbandment() -> dict`
- **用途：** 人口阶段结束后处理军团解散与凯旋式（C-E1）
- **CLI 来源：** `phase_population.py` ~L514-565
- **逻辑：**
  1. 遍历所有活跃战争
  2. 对胜利战争：触发凯旋式（增加 commander 人气/影响力）
  3. 对所有战争：解散多余军团（保留 minimum_garrison）
- **返回：** `{triumphs: [{war_id, commander_id, popularity_gain, influence_gain}], disbandments: [{legion_id, reason}], summary: str}`
- **日志：** DBUG（凯旋条件/解散决策）+ INFO（执行结果）

## 6. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.2 | 2026-07-26 | 追加 process_triumph_and_disbandment() 方法（Wave-04 Finale, C-E1） |
| v1.1 | 2026-07-26 | 追加 assign_rebellion_commanders() + auto_recruit_and_assign() 方法（Wave-03） |
| v1.0 | 2026-07-12 | 初版 |
