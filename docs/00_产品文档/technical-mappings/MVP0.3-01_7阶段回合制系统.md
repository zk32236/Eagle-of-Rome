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
| v1.4 | 2026-08-24 | DA-Exec (WP-E-G7R) | §6.1 两段式 → 单命令；step_definitions 移除（preview 四类目替代）；resolved 单源化；新增 §7 Resolution Preview DTO（只读投影 + 零变异 + parity 契约） |
| v1.3 | 2026-08-23 | DA-Exec (WP-E Slice 11 PU-04) | 新增 §6：Resolution 四步事件身份 read-model + 两段式年度推进；市场生成段补注（veteran supply 注入） |
| v1.2 | 2026-08-01 | DA-Exec G5-R1 | §4 删除「batch内自动结算」旧说法，对齐 FC-09（resolve_population_slice 统一触发） |
| v1.1 | 2026-07-31 | DA-Exec (WP-02b V4 Pro) | 新增人口阶段 vote 子步骤事务描述：batch_vote 原子提交 + ABSTAIN + per-player completion + resolution 自动触发 (§4) |
| v1.0 | 2026-07-12 | Document Officer Worker L | 初版创建 |

## 6. WP-E 更新（2026-08-23）

### 6.1 Resolution 阶段：settlement read-model + 单命令年度推进（WP-E-G7R 修订）

- **read-model（`_resolution_settlement`，game_state.py）**：`_commit_settlement`
  在 A1~A7 apply 后、`_turn.advance_year()` 前承接 A5/A6/A7 返回值 + A3/A4 新形状，
  写入独立 read-model（settled_turn/settled_year/next_year/treasury_before/after /
governor_returns/contract_expiries/truce_expiries/decay）——`execute_resolution`
  入口（幂等 guard 之后）清除旧 settlement（新年度重入）。**read-model 不再参与
  `resolved` 门控，保留为 EC-10 preview=commit parity 比对源（内部）。**
- **step_statuses 移除（WP-E-G7R E-02）**：`get_resolution_view`（session_api.py）
  不再提供顺序 step_definitions/step_statuses；改由 `preview` 四信息类目
  （governor_returns/contract_expiries/truce_expiries/faction_influence）替代
  ——非顺序工作流，无 StepBar、无「决算完成」第五块、无 x/4 进度隐喻。
- **resolved 单源化（D2 §4.2）**：`resolved = is_phase_executed("resolution")`（删
  `or settlement is not None`）——advance 后 executed_phases 已清空 → resolved=False
  → 新年入口自动结算可靠触发（消除跨年毒化）；`results.settled` 键移除
  （D10 §3），treasury_before/after 降内部 parity/审计字段。
- **职责边界**：`execute_resolution`（resolution_api.py:21-93）= 业务执行
  （apply A1~A7）；`advance_year`（game_state.py:1341）= 年度滚轮；GUI 单命令
  （`doAdvanceResolution` session_store.py）：一键 → advance_year 恰好一次 →
  成功直接导航 mortality（E-05）；失败停留 resolution 可重试（EC-09）；
  finally 补发 phaseChanged（P0 notify 闭合）。

### 6.2 市场生成段补注（E-G7-09）

- 普通人物生成（Phase 2 广场/Forum）含 **veteran supply 注入**：每回合 1-2 名
  ex-consul/ex-praetor 贵族（`figure_generation_system` 共享核心循环 +
  `forum_rules.veteran_supply`，见 `MVP0.5-07_人物类型系统.md §4`）——
  市场总量不变（`new_figures_count`），hero 生成零注入。

## 7. Resolution Preview DTO（WP-E-G7R，Doc-6）

### 7.1 投影函数与调用链

`session_api._build_resolution_preview(state) -> dict`：只读 year-end 投影，
每次 `_refresh_resolution_view()` 重算（无状态、确定性、零变异——EC-01）。
直连 `state._plan_settlement()`（`game_state.py:1369-1383`）及各 `_plan_*`
（member_decay/contract_expiration/governor_transitions/truce_expiry）——
**共享规划语义（R-23），无第二套年终规划实现**。preview 只做只读字段读取与
命名富化，不触碰 `_apply_*` / `update_influence` 写调用。唯一判定谓词
（governor return guard = `old_fig is not None and not old_fig.is_dead`）为
1 行布尔，与 `_apply_governor_transitions` 同语义（parity 测试 EC-10 锁定）。

### 7.2 DTO 字段（四类目）

```python
{
  "governor_returns": [
    {"province_id": int, "province_name": str,
     "governor_name": str,        # 旧总督 formal name（将返回罗马者）
     "successor_name": Optional[str]}   # 若 designate 升任（E-03 附加行）
  ],
  "contract_expiries": [
    {"contract_id": int, "name": str, "contract_type": str}   # 身份行，非计数
  ],
  "truce_expiries": [
    {"war_name": str}
  ],
  "faction_influence": [
    {"faction_id": str, "faction_name": str,
     "influence_before": int, "influence_after": int, "influence_delta": int}
  ],
}
```

- `faction_influence` = **decay-only 聚合（ODR-C1）**：before = Σ 成员当前影响力
  （只读）；after = `figure._compute_influence` 纯函数以衰减目标值只读重算
  （veterans/popularity/temp_tasks 衰减；office/land/family 恒定）；
  delta = after − before。总督交接带来的影响力变化不并入（归属「总督返回」类目）。
- 每派系恒一行；全局空仅当 `state.factions` 为空（E-04 空态）。

### 7.3 契约

- **零变异（EC-01）**：调用前后 state 等价快照零变化（`test_preview_zero_mutation`）。
- **刷新稳定（EC-02）**：重复调用同结果（`test_preview_refresh_stable`）。
- **preview=commit parity（EC-10）**：preview 四类事实 == advance 后
  settlement/权威状态；faction 比较对象 = decay-only 分量（ODR-C1）
  （`test_preview_commit_parity`）。
- **挂载点**：`get_resolution_view` 返回体 `preview` 键（QML 消费
  `sessionStore.resolutionView.preview.*`）。
