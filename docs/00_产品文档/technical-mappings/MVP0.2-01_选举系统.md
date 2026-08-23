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
    "votes":     List[Tuple[str, str, int]],        # [(player_id, office, figure_id)] v2.1: 移除 choice, 改为 3-tuple
    "committed_batches": Set[str],                 # 已提交的 campaign 批量批次签名（幂等守卫）
    "committed_vote_batches": Set[str],            # [WP-02b v2.1] 已提交的 vote 批量批次签名（幂等守卫）
}
```

### ABSTAIN Sentinel（WP-02b v2.1, FC-03）

- **唯一表达：** `figure_id = 0` 表示弃权
- ABSTAIN entry 持久化写入 vote records（参与 `len(my_votes)` 计算）
- 在 `resolve_election()` 中，`fig_id == 0` 的条目跳过不计入加权计票
- 已移除：`choice` 字段（FOR/AGAINST/ABSTAIN）、`figure_id = -1`、省略 entry、`null`

### 按玩家投票完成状态（WP-02b）

- `_vote_completed_by_player: Dict[str, bool]` — 与 campaign 的 `_batch_completed_by_player` 独立隔离
- p1 完成不推进 p2；p2 失败不回退 p1

## 5. 配置项

| 配置路径 | 默认值 | 说明 |
|---------|--------|------|
| `candidates_per_election.consul` | 2 | 候选人数量 |
| `testing.auto_population` | false | 自动模式 |
| `political_rules.min_ages.*` | 30-42 | 各官职最低年龄 |
| `political_rules.office_cooldowns.*` | 2-10 | 各官职冷却年数 |

## 7. v2.1 投票批量事务调用链 (WP-02b v2.1)

### 7.1 `batch_vote()` 调用链

```text
population_api.batch_vote(state, player_id, entries)
  → DTO 校验: _validate_vote_json_container / _validate_vote_dto_types
  → Batch 完整性校验 (FC-01): 恰好 5 office, 重复检查 (FC-04)
  → Entry DTO: {office: str, figure_id: int}, figure_id=0=ABSTAIN (FC-03)
  → population_service.check_and_commit_vote(state, player_id, validated_entries, signature)
      ├─ Phase 1: 幂等检查 → state.has_committed_vote_batch(sig)  (FC-06)
      ├─ Phase 2: Lock guard → state.try_acquire_batch_guard()  (FC-07)
      ├─ Phase 3: 快照 → state.snapshot_vote_state()
      ├─ Phase 4: 写入投票记录 → state.record_population_vote(player_id, office, figure_id)
      │             v2.1: 通过 record_population_vote() 写入，修复 office="" bug
      ├─ Phase 5: 写入 committed marker → state.record_committed_vote_batch(sig)  (FC-06)
      ├─ Phase 6: 设置 player completion → state.set_vote_completed(player_id, True)  (FC-05)
      ├─ 异常回滚: restore_vote_state / remove_committed_vote_batch / set_vote_completed(original)
      └─ finally: state.release_batch_guard()
```

> v2.1 关键变更：Phase 7（inline resolve_election）已移除。结算由 `resolve_population_slice()` 在所有玩家完成后统一触发（FC-09）。

### 7.2 Entry DTO v2.1

| 操作 | 方法 |
|------|------|
| 设置 | `set_vote_completed(player_id, value)` |
| 读取 | `get_vote_completed(player_id) → bool` |
| 清理 | `clear_population_pending()` 同步清空 |

### 7.3 GUI/Session 投票提交调用链（WP-02b v3.0）

```text
PopulationStage.qml selectedVotes（0～5 个已选 office key）
  → sessionStore.submitPopulationVotes(selectedVotes)
  → api_adapter.submit_population_votes(player_id, selected_by_office)
  → session_api.submit_population_votes(state, player_id, selected_by_office)
      ├─ 校验 selection map：仅允许已知 office；value 为严格正整数
      ├─ 按固定五 office 顺序物化 5 条 entry；缺 key → figure_id=0
      ├─ population_api.batch_vote(...)（后端 FC-01 五条契约不放松）
      ├─ batch 失败 → 零 handoff、零 resolve
      ├─ 尚有未完成人类玩家 → handoff；status=awaiting_players
      └─ 全部人类玩家完成 → resolve_population_slice()；status=resolved
```

- GUI 不提供显式弃权控件；`figure_id=0` 只由 Session 对缺失 key 物化，QML 不传 `0`、`null`、`choice` 或部分 backend DTO。
- QML 选择使用 clone-and-reassign 更新 `selectedVotes`，确保属性通知；Store 以 `populationVoteSubmitting` 防重复提交并在 handoff/resolved 后刷新权威视图。
- 庆典赞助区与投票区使用 `ScrollBar.AsNeeded` 保证内容溢出时可达；这些 UI 行为不替代 backend 幂等、`frozenset` 签名或 `threading.Lock` guard。
- FC-09 保持：GUI、Store batch 层、Adapter batch 层与 Core 均不直接结算；Session 只通过 `resolve_population_slice()` 进入选举结算。

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
      ├─ Phase 2: 运行时 Lock guard
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
| `_batch_guard_lock` | `threading.Lock` | ❌ | 运行时互斥，`to_dict()` 不输出；`load_from_dict()` 始终创建新 Lock |
| `_batch_commit_in_progress` | `bool` | ❌ | 已移除，由 Lock 的 `acquire()`/`release()` 代替 |

### 6.4 Save/Load 行为

```
to_dict():
  _batch_completed_by_player: {p1: True, p2: False, ...}  # 序列化
  _batch_guard_lock: 不输出                                    # 不序列化

load_from_dict(data):
  _batch_completed_by_player = data.get("_batch_completed_by_player", {})
  _batch_guard_lock = threading.Lock()  # 全新实例，始终未锁定
```

### 6.5 故障语义

| 条件 | 响应 |
|:-----|:-----|
| 幂等（相同签名） | `success=True, already_committed=True, campaign_count=0` |
| 并发争用（guard 忙） | `success=False, errors[0].code=BATCH_BUSY, data.retryable=True` |
| getter 故障 | `success=False, errors[0].code=GETTER_FAILURE` (不回滚，不覆盖既有状态) |
| 非法 DTO | `success=False, failed_entries=[{reason, index, figure_id, amount}]` |
| 任意写入异常 | 完整回滚 + guard 释放 + 结构化 failure |

## 8. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.9 | 2026-08-23 | DA-Exec (WP-E Slice 11 PU-04) | 新增 §9：candidate supply 来源补注（E-G7-09 veteran supply，资格契约 REVIEWED-NO-CHANGE）+ Population 转换公示时序（门控 total>0，E-ODR-04） |
| v1.8 | 2026-08-09 | DA-Exec (AC-12 M2-BUG3 R2) | §7 实现落地：`set_vote_completed`/`get_vote_completed` API 从设计目标→磁盘实现（game_state.py）；`resolve_population_slice` 增加 once guard（get_phase_result 防重复结算，保全两阶段模式）；`doResolveElection` 调用链切换到 `resolve_population_slice`（FC-09 满足）；turn_order 保持全序（含 AI）供 drain 遍历 |
| v1.7 | 2026-08-02 | DA-Exec (WP-02b v3.0) | 新增 §7.3 GUI selection map → Session 固定五条 → handoff/resolve_population_slice 单一调用链；明确无显式弃权控件、clone-and-reassign、submitting 与双区 AsNeeded scrollbar |
| v1.6 | 2026-08-01 | DA-Exec (WP-02b v2.1) | v2.1 返工：移除 choice 枚举，vote 记录改为 3-tuple；ABSTAIN=figure_id=0 (FC-03)；修复 office="" bug（通过 record_population_vote 写入）；移除 inline resolve_election（FC-09）；新增 FC-01 batch 完整性、FC-04 重复 office 拒绝；更新 §4, §7 |
| v1.5 | 2026-07-31 | DA-Exec (WP-02b V4 Pro) | 新增 batch_vote() 批量投票原子提交 + ABSTAIN 枚举 + vote completion 按玩家隔离 + check_and_commit_vote() 事务调用链 (§4, §7) |
| v1.4 | 2026-07-30 | DA-Exec (WP-02a ATTEMPT-3) | 补齐 v3 事务/completion/persistence/guard/save-load/check_and_commit() 调用链 (§6) |
| v1.3 | 2026-07-30 | DA-Exec (WP-02a) | 新增 `batch_campaign()` 批量原子提交；新增 `committed_batches` 幂等守卫字段 |
| v1.2 | 2026-07-17 | Audit Sub-Agent | 行数修正 |
| v1.0 | 2026-07-13 | 初版 | — |

## 9. WP-E 更新（2026-08-23）

### 9.1 candidate supply 来源补注（E-G7-09）

- **市场资深贵族供给（veteran supply）**：市场生成链（`figure_generation_system`
  共享核心循环）每回合注入 1-2 名 ex-consul/ex-praetor 贵族（`forum_rules.veteran_supply`，
  见 `technical-mappings/MVP0.5-07_人物类型系统.md §4`）→ 高阶官职（consul/censor）
  候选供给从 T1 起不再依赖前任选举胜者归档，消除「无存活 ex-consul → censor 零候选」
  的冻结规则不可避免空池。
- **REVIEWED-NO-CHANGE（资格契约段）**：`can_hold_office`（figure.py:307-402）资格
  契约**零改动**——注入者与归档者同权经 `get_candidates` read-model
  （population_api.py:844-905）处理；注入保证的是「市场每回合产出合格者」，派系门槛
  （faction_id ≠ None）仍由真实招募链（`recruit_figure` + `resolve_forum`）满足，
  无候选 read-model 补丁（R-14 合规，非 spawn hack）。
- 8 回合证据：`03-da-evidence/runtime/wpe-eg7-09-*-with-injection-8turns-2026-08-23.md`
  （稀疏供给 censor 零候选 1 → 0；富供给全官职零候选 == 0）。

### 9.2 Population 转换公示时序（E-ODR-04）

- `PopulationStage.qml:186` 门控由 `populationResolved && total > 0` 改为 `total > 0`——
  战场指挥官转换（`convert_battlefield_commanders`，population_api.py:1064-1145）
  结果在选举解析前即公示（banner 上移至阶段顶部公告区）；数据源不变
  （`begin_population_phase` phase result 权威输出），零转换逻辑复制；
  转换缺失 → 无 fallback 文案（fail-closed，E-13 分类：转换逻辑缺陷 → WP-E 内修正；
  War lifecycle 缺陷 → WP-G 移交）。
- phase-result 生命周期：`begin_population_phase` 幂等（`resolve_population_slice`
  once guard），转换结果跨 refresh 稳定直读存储结果。
