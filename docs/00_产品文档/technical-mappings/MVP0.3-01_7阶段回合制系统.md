# MVP0.3-01 — 7阶段回合制系统（技术映射）

## 1. 代码目录

```
src/
├── core/
│   ├── game_state.py                 # GameState：阶段标记、年份推进、阶段结果存储
│   └── localization.py               # TerminologyService：阶段名称本地化
├── ui/
│   └── commands/
│       ├── func_turn_control.py      # 回合控制命令：NextCommand / TurnCommand / StepCommand
│       ├── phase_mortality.py        # 1/7 死亡率阶段
│       ├── phase_revenue.py          # 2/7 收入阶段
│       ├── phase_forum.py            # 3/7 广场阶段
│       ├── phase_population.py       # 4/7 人口阶段
│       ├── phase_senate.py           # 5/7 元老院阶段
│       ├── phase_combat.py           # 6/7 战斗阶段
│       ├── phase_resolution.py       # 7/7 决议阶段
│       └── sys_base.py               # Command 基类
```

## 2. 关键模块

| 文件 | 行数 | 功能角色 |
|------|------|---------|
| `game_state.py` | 1415 | **核心状态** — 阶段标记、推进、结果 |
| `func_turn_control.py` | 231 | **控制命令** — Next/Turn/Step 命令 |

## 3. 核心类

### 3.1 GameState 阶段方法

```python
is_phase_executed(phase_name) → bool
mark_phase_executed(phase_name)
record_phase_result(phase_id, result)
get_phase_result(phase_id) → Any
advance_year()
```

### 3.2 阶段顺序

```python
PHASE_SEQUENCE = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]
```

## 4. 人口阶段（Phase 4）事务细化（WP-02b）

人口阶段包含三个子步骤：campaign（庆典）→ vote（投票）→ results（公示结算）。

### vote 子步骤事务

- **入口:** `population_api.batch_vote()` → `population_service.check_and_commit_vote()`
- **原子性:** 同一批次所有投票（含弃权 ABSTAIN）全有或全无
- **按玩家隔离:** `_vote_completed_by_player[player_id]` 独立于 `_batch_completed_by_player`（campaign completion）
- **幂等:** 同签名重复调用 → ALREADY_COMMITTED 零写入
- **并发:** Lock guard → BUSY retryable (FC-07 G5-R2: 全路径统一为 threading.Lock, 同线程重入→BUSY)
- **结算:** 由 `resolve_population_slice()` 在所有玩家完成后统一触发 `resolve_election()`（FC-09）；batch_vote 内不触发结算
- **GUI:** `sessionStore.batchVote(entries)` → 单批入口，移除旧逐项 doVote 循环

## 5. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-08-01 | DA-Exec G5-R1 | §4 删除「batch内自动结算」旧说法，对齐 FC-09（resolve_population_slice 统一触发） |
| v1.1 | 2026-07-31 | DA-Exec (WP-02b V4 Pro) | 新增人口阶段 vote 子步骤事务描述：batch_vote 原子提交 + ABSTAIN + per-player completion + resolution 自动触发 (§4) |
| v1.0 | 2026-07-12 | Document Officer Worker L | 初版创建 |
