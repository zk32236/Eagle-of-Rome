# MVP0.7-04 — 海军与海战-P0（含技术解锁）

> **功能简述：** Fleet 实体全生命周期、NavalSystem 管理、海战 CRT 判定（简化版）、技术解锁条件（皮洛士战争胜利后方可建造舰队）、舰队维护费与解散

## 1. 功能目的

海军是罗马军事力量的重要组成部分。本功能实现技术解锁、舰队管理、海战判定、维护费与解散全流程。

## 2. 核心规则

### 2.1 舰队类型配置

| 类型 | 建造费用 | 建造时间 | 维护费 | 基础战力 |
|------|---------|---------|-------|---------|
| trireme | 40 | 1 回合 | 120 | 3 |
| quadrireme | 120 | 2 回合 | 200 | 4 |
| quinquereme | 160 | 3 回合 | 320 | 5 |

### 2.2 海战判定（冻结矩阵，G1-09/10/16，WP-G GC）

```
舰队战力（单舰） = _strength_base + _experience + commander.martial
指挥官 martial 权威 = War Commander（war.commander_id，G1-20）
total = 2d6 + 罗马海军战力 - war.enemy_naval_current
```

CRT 结果：TRIUMPH/VICTORY/STALEMATE/DEFEAT/DISASTER（阈值/骰子区间与陆战 CRT 一致，零改）

**五结果矩阵（D 件 §1）：**

| 海军结果 | 舰队损失 | Sea Control | 本场陆战 | 战争 |
|:--|:--|:--|:--|:--|
| **TRIUMPH** | 0 | acquired | 允许 | 继续陆战 |
| **VICTORY** | 0 | acquired | 允许 | 继续陆战 |
| **STALEMATE** | 0 | 未获控 | 阻断 | 继续 |
| **DEFEAT** | 随机 ceil(N/2) DESTROYED | 未获控 | 阻断 | 继续 |
| **DISASTER** | 全部参战舰队 DESTROYED | 未获控 | 阻断 | 继续 |

**海军门槛状态机（G1-09/R-04/R-05/R-06，canonical 单一门 = `combat_api.do_combat_action`）：**

```
naval_required == false → 无海军门，直接陆战
naval_required == true:
  未获控（sea_control_acquired == false）→ 必须先海战
    TRIUMPH/VICTORY → sea_control_acquired = true → 本场陆战允许
    STALEMATE/DEFEAT/DISASTER → 陆战不执行（R-05）→ 军团保持 ACTIVE+assigned
      （G1-15 零陆战伤亡）→ 战争继续，等待下次登陆机会
  已获控（sea_control_acquired == true）→ 跳过海战，直接陆战（R-06 禁重复海战）
```

**Sea Control 持久（G1-16 / K 件）：**

```
War.sea_control_acquired: bool（权威字段，默认 False；唯一 True 写入点 = resolve_naval_battle
TRIUMPH/VICTORY 分支；False 清理 = clear_sea_control，随战争正式结束接线，owner = GD）

获控持久至该战争正式结束；期间同战未来战斗跳过海战（R-06）；
若陆战 STALEMATE/DEFEAT/DISASTER → 战争继续 → 制海权保持 acquired。
替代旧 `_sea_control_ratio`（dormant float，禁作获控判定）。
```

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-04_海军与海战.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Worker K | 初版创建 |
| v1.1 | 2026-08-31 | DA Sub-Agent (WP-G GC) | 冻结语义落地（G1-09/10/16/20）：§2.2 补五结果矩阵（STALEMATE 0 损、DEFEAT ceil(N/2) 随机无放回）；海军门槛状态机（naval_required 门 / STALEMATE-DEFEAT-DISASTER 阻断陆战 / TRIUMPH-VICTORY 获控）；Sea Control 持久契约（sea_control_acquired 权威字段替代 _sea_control_ratio）；舰队战力 martial 权威 = War Commander |
