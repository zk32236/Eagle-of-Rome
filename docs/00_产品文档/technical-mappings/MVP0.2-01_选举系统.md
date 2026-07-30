# MVP0.2-01 — 选举系统（Technical Mapping）

> **功能简述：** 选举系统 — 罗马共和国年度公职选举的完整流程

## 1. 代码目录

```
src/
├── api/
│   └── population_api.py          # 选举核心 API（campaign, vote, get_candidates, resolve_election）
├── core/
│   ├── deciders/
│   │   ├── vote_decider.py          # 投票决策器接口
│   │   ├── festival_decider.py      # 庆典决策器接口
│   │   └── impl/
│   │       ├── auto_vote_decider.py     # 自动投票决策器实现
│   │       └── auto_festival_decider.py # 自动庆典决策器实现
│   ├── entities/
│   │   ├── figure.py                # 人物实体（影响力计算、任职资格检查、社会阶层）
│   │   └── entities.py              # Faction 实体（派系统计）GameTurn
│   ├── systems/
│   │   └── political_system.py      # 政治系统（元老院提案，不直接涉及选举）
│   └── game_state.py                # 游戏状态（选举临时数据管理）
├── ui/
│   ├── commands/
│   │   └── phase_population.py      # 人口阶段 UI 命令（4 步骤状态机）
│   └── processors/
│       └── auto_player_processor.py # AI 玩家庆典/投票自动化处理器
```

## 2. 关键模块

### 2.1 UI 层 — `phase_population.py` (670行)

方法: `execute()`, `_handle_step_0~3()`, `_remove_office_holders()`, `_convert_battlefield_commanders()`, `_campaign_all()`, `_vote_all()`

### 2.2 API 层 — `population_api.py`

方法: `campaign()` [DEPRECATED], `batch_campaign()` [新增—批量原子提交], `vote()`, `get_candidates()`, `resolve_election()`

### 2.3 实体层 — `figure.py`

方法: `can_hold_office()`, `get_qualification_attribute()`, `update_influence()`

## 3. 核心算法

### 3.1 候选人提名

选举顺序: consul → censor → praetor → quaestor → tribune，按资格属性降序取前 N 名。

### 3.2 选举计票

加权投票：各候选人得分 = Σ 支持者派系影响力总和，平局随机。

## 4. 数据结构

### 选举临时数据

```python
{
    "campaigns": List[Tuple[str, int, int]],       # [(player_id, figure_id, amount)]
    "votes":     List[Tuple[str, str, int]],       # [(player_id, office, figure_id)]
    "committed_batches": Set[str],                 # [新增] 已提交的批量批次签名（幂等守卫）
}
```

## 5. 配置项

| 配置路径 | 默认值 | 说明 |
|---------|--------|------|
| `candidates_per_election.consul` | 2 | 候选人数量 |
| `testing.auto_population` | false | 自动模式 |
| `political_rules.min_ages.*` | 30-42 | 各官职最低年龄 |
| `political_rules.office_cooldowns.*` | 2-10 | 各官职冷却年数 |

## 6. v3 事务/持久化/Guard 调用链 (WP-02a ATTEMPT-3)

### 6.1 `check_and_commit()` 完整调用链

```
population_api.batch_campaign(state, player_id, entries)
  → _validate_json_container(entries)          # 拒绝 None/str/int/dict
  → _validate_dto_types(entries)               # 逐 entry 类型校验
  → _validate_business_rules(state, entries)   # 业务校验
  → population_service.check_and_commit(state, player_id, entries, signature)
      │
      ├─ Phase 1: 幂等检查
      │   └─ state.has_committed_batch(sig) → ALREADY_COMMITTED (零写入 success)
      │
      ├─ Phase 2: 运行时 RLock guard
      │   └─ state.try_acquire_batch_guard() → BATCH_BUSY (结构化 retryable failure)
      │
      ├─ Phase 2b: getter 安全读取 (AC-05b)
      │   ├─ state.get_population_campaigns() → len → original_campaigns_len
      │   └─ state.get_batch_completed(player_id) → original_batch_completed
      │   └─ getter 异常 → GETTER_FAILURE (不回滚，不覆盖既有状态，finally 释放 guard)
      │
      ├─ Phase 3: 快照
      │   └─ state.snapshot_campaign_figures(entries) → {fid: {wealth, popularity}}
      │
      ├─ Phase 4: 应用变更
      │   ├─ figure.wealth -= amount
      │   ├─ figure.popularity += amount
      │   └─ figure.update_influence()
      │
      ├─ Phase 5: 写入 campaign 记录
      │   └─ state.record_population_campaign(player_id, fid, amount)
      │
      ├─ Phase 6: 写入 committed marker
      │   └─ state.record_committed_batch(signature)
      │
      ├─ Phase 7: 设置当前玩家 completion (D-12 隔离)
      │   └─ state.set_batch_completed(player_id, True)
      │
      ├─ 异常 → 回滚
      │   ├─ state.restore_campaign_figures(snapshot) → 恢复 wealth/popularity，再调用 update_influence() 重算 influence
      │   ├─ state.truncate_population_campaigns(original_campaigns_len)
      │   ├─ state.remove_committed_batch(signature)  (若已写入)
      │   ├─ state.set_batch_completed(player_id, original_batch_completed)  (AC-03)
      │   └─ 返回结构化 failure + diagnostics
      │
      └─ finally: state.release_batch_guard()  (始终释放)
```

### 6.2 Completion 持久化 (D-12 玩家隔离)

| 操作 | 方法 | 说明 |
|:-----|:-----|:-----|
| 设置 | `set_batch_completed(player_id, value)` | 按 player_id 写入 `_batch_completed_by_player` dict |
| 读取 | `get_batch_completed(player_id) → bool` | 按 player_id 读取，默认 False |
| 清空 | `clear_all_batch_completed()` | 年度推进时清空所有玩家完成状态 |
| 序列化 | `to_dict()` → `_batch_completed_by_player` | dict 原样序列化 |
| 反序列化 | `load_from_dict(data)` | 从 key 恢复，缺失时默认空 dict |

### 6.3 Guard 持久化 (不持久化)

| 属性 | 类型 | 序列化 | 说明 |
|:-----|:-----|:------:|:-----|
| `_batch_guard_lock` | `threading.RLock` | ❌ | 运行时互斥，`to_dict()` 不输出；`load_from_dict()` 始终创建新 RLock |
| `_batch_commit_in_progress` | `bool` | ❌ | 已移除，由 RLock 的 `acquire()`/`release()` 代替 |

### 6.4 Save/Load 行为

```
to_dict():
  _batch_completed_by_player: {p1: True, p2: False, ...}  # 序列化
  _batch_guard_lock: 不输出                                    # 不序列化

load_from_dict(data):
  _batch_completed_by_player = data.get("_batch_completed_by_player", {})
  _batch_guard_lock = threading.RLock()  # 全新实例，始终未锁定
```

### 6.5 故障语义

| 条件 | 响应 |
|:-----|:-----|
| 幂等（相同签名） | `success=True, already_committed=True, campaign_count=0` |
| 并发争用（guard 忙） | `success=False, errors[0].code=BATCH_BUSY, data.retryable=True` |
| getter 故障 | `success=False, errors[0].code=GETTER_FAILURE` (不回滚，不覆盖既有状态) |
| 非法 DTO | `success=False, failed_entries=[{reason, index, figure_id, amount}]` |
| 任意写入异常 | 完整回滚 + guard 释放 + 结构化 failure |

## 7. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.4 | 2026-07-30 | DA-Exec (WP-02a ATTEMPT-3) | 补齐 v3 事务/completion/persistence/guard/save-load/check_and_commit() 调用链 (§6) |
| v1.3 | 2026-07-30 | DA-Exec (WP-02a) | 新增 `batch_campaign()` 批量原子提交；新增 `committed_batches` 幂等守卫字段 |
| v1.2 | 2026-07-17 | Audit Sub-Agent | 行数修正 |
| v1.0 | 2026-07-13 | 初版 | — |
