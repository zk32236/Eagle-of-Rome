# MVP0.4-04-sys — Command命令体系架构 Technical Mapping

## 1. 代码目录

| 目录 | 角色 |
|------|------|
| `src/ui/commands/` | 所有命令类 |
| `src/api/` | API 层 |
| `src/core/deciders/` | 决策器层 |

## 2. 关键文件
- `sys_base.py` (167行) — Command 基类
- `sys_registry.py` (120行) — 命令自动注册
- `phase_forum.py` (1601行) — 广场阶段状态机
- `phase_senate.py` (1855行) — 元老院阶段状态机
- `phase_population.py` (730行) — 人口阶段状态机（庆典批量提交 + 投票 + 选举）

## 3. 调用链

### 3.0 广场阶段 canonical init（GUI-BETA-R1 WP-C，2026-08-21）

```
phase_forum._execute_normal()（L1346 区）
  → forum_api.initialize_forum_turn(state)          # 合并原 4 个 init 调用（war/fleet/figures/contracts/unrest），exactly-once
    → _war_events / _init_unrest_data / figures / contracts 全部消费 init 结果打印（_print_init_figures / _print_init_contracts / _print_unrest_result）
  → _print_ui_03_0 民变块：_init_unrest_data 优先，None 时兑底直调 _update_civil_unrest()（直调测试零扰动）
  → _do_resolution：保留显式 execute_land_acts（展示）→ resolve_forum（内部 hook 幂等，不 double-execute）
壳方法保留：_update_war_system_silent / _generate_new_figures / _generate_contracts / _update_civil_unrest（生产不再调用，测试直调依赖）
```

### 3.1 庆典批量提交（WP-02a 原子事务）

```
phase_population.py:_campaign_all()
  → population_api.batch_campaign(state, player_id, entries)
    → _validate_json_container(entries)          # 拒绝 None/str/int/dict
    → _validate_dto_types(entries)               # 逐 entry 类型校验
    → _validate_business_rules(state, entries)   # 业务校验
    → population_service.check_and_commit(state, player_id, entries, signature)
      → GameState.try_acquire_batch_guard()       # RLock 运行时 guard
      → GameState.snapshot_campaign_figures()      # 快照
      → Figure 属性写入 + update_influence()       # 应用
      → GameState.record_population_campaign()     # 写入记录
      → GameState.record_committed_batch()         # 幂等签名
      → GameState.set_batch_completed(player_id)   # 完成标记（玩家隔离）
      → 异常 → GameState.restore_campaign_figures() + 回滚所有变更
      → finally → GameState.release_batch_guard()  # 保证释放
```

### 3.2 故障语义

| 条件 | 响应 |
|:-----|:-----|
| 幂等（相同签名） | `success=True, already_committed=True, campaign_count=0` |
| 并发争用（guard 忙） | `success=False, errors[0].code=BATCH_BUSY, data.retryable=True` |
| 非法 DTO | `success=False, failed_entries=[{reason, index, figure_id, amount}]` |
| 任意写入异常 | 完整回滚 + guard 释放 + 结构化 failure |

## 4. 版本日志
| 版本 | 日期 | 变更 |
|:---:|:---:|:---:|
| v1.0 | 2026-07-17 | 初版 |
| v1.1 | 2026-07-30 | DA-Exec (WP-02a v3) | 加入 phase_population.py，新增庆典批量提交原子事务调用链 |
| v1.2 | 2026-08-21 | GUI-BETA-R1 WP-C: 新增 §3.0 广场阶段 canonical init 调用链（_execute_normal 四调用合并为 initialize_forum_turn，打印消费 init 结果） |
