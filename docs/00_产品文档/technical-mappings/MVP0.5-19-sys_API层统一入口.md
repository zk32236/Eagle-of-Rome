# MVP0.5-19-sys — API层统一入口（技术映射）

## 1. 代码目录
```
src/api/                 # 14个API模块
src/api/__init__.py      # api_response() 统一格式
```

## 2. API模块清单
game_api, figure_api, faction_api, province_api, contract_api, player_api,
population_api, forum_api, senate_api, combat_api, mortality_api, revenue_api,
session_api, gui_query_api

## 3. forum_api 新增接口（Wave-01 Forum Init）

### 3.1 `generate_figures(state: GameState) -> dict`
- **用途:** 广场阶段初始化人物生成
- **内部委托:** `figure_generation_system.generate_figures(state)`
- **返回:** `api_response(True, data={"figures": [figure_data...]})`
- **figure_data 结构:** id, name, class_tier, martial, intelligence, charisma, zeal, age, is_hero, hero_type

### 3.2 `generate_contracts(state: GameState) -> dict`
- **用途:** 广场阶段初始化合同生成（续约+新合同+舰队委托）
- **内部逻辑:**
  1. 包税续约（remaining_years==1, 已征服, 无重复PENDING）
  2. 工程续约（warranty_remaining==1, 已征服, 无重复PENDING）
  3. 新包税合同（已征服非意大利, land_public>0, 无ACTIVE/PENDING/BUDGETED）
  4. 新工程合同（已征服或意大利, land_public>0, 无非EXPIRED/COMPLETED）
  5. 舰队建造 → `naval_system.generate_construction_contracts()`
  6. 舰队补充 → `naval_system.generate_replacement_contracts()`
- **返回:** `api_response(True, data={"contracts": [contract_data...]})`
- **contract_data 结构:** id, name, contract_type, contract_type_label, province_id, base_cost, expected_profit, duration_years, status, is_renewal, is_fleet

### 3.3 调用链变更 (Wave-01)
- CLI `phase_forum._generate_new_figures()` → **委托至** `forum_api.generate_figures()` → `figure_generation_system.generate_figures()`
- CLI `phase_forum._generate_contracts()` → **委托至** `forum_api.generate_contracts()`
- `open_market()` 的 `_generate_market_figures()` → **委托至** `figure_generation_system.generate_market_figures()`

### 3.4 Canonical Forum Init (GUI-BETA-R1 WP-C, 2026-08-21)

#### 3.4.1 `initialize_forum_turn(state: GameState) -> dict` [NEW]
- **用途:** 广场回合 canonical 初始化，**exactly-once/回合**（GUI/CLI/AI 三路径共用入口）
- **副作用顺序（固定）:** ① war `check_triggers(year)` + `escalate_threats()`（015）→ ④ `naval_system.process_fleet_construction(turn)` → ③ `generate_figures()`（含 hero 消费，009）→ ② `generate_contracts()`（014）→ ⑤ `check_province_unrest()`
- **守卫:** `_forum_pending["forum_initialized"]`（list-flag，复刻 market_opened）；已置位 → `data={}` no-op
- **ODR-04:** 入口调 `_reconcile_stale_hero_markers()`——hero_to_spawn 带 `spawn_turn` 且==当前回合才消费；无戳/旧回合 → 丢弃
- **返回:** `{war_events, completed_fleets, figures, contracts, unrest}`

#### 3.4.2 调用链变更 (WP-C)
- `open_market()`：`_generate_market_figures()` → **替换为** `initialize_forum_turn()`（generated_figures 行形 `_available_figure_row` 不变，ODR-05；`market_opened` 步态标记保留）
- `resolve_forum()`：函数体首行新增 `execute_land_acts(state)`（resolution-time 幂等 hook，CLI 显式调用保留不 double-execute）
- `get_forum_view()`：新增 `"war_threats": _war_threat_rows(state)`（016；与 Senate `get_threat_wars()` 同 war.id；无威胁空数组）
- CLI `phase_forum._execute_normal()`：原 4 个 init 调用合并为单次 `initialize_forum_turn()`，`_war_events`/民变/舰队/figures/contracts 全部消费 init 结果打印（壳方法保留）

## 4. forum_api 新增接口 (Wave-02 Province & Land)

### 4.1 `check_province_unrest() -> dict`
- **用途:** 行省民变检测（C-09c）
- **内部委托:** `ProvinceUnrestSystem.check_and_trigger_unrest()`
- **返回:** `{rebellions: [...], province_updates: [{id, name, grievance, reason}]}`

### 4.2 `execute_land_acts(republic_state) -> dict`
- **用途:** 执行土地分配命令（C-09d）
- **内部逻辑:** 分析所有待执行土地法案 → 更新实体
- **返回:** `{act_id: result, ...}`

### 4.3 调用链变更 (Wave-02)
- CLI `phase_forum._update_civil_unrest()` → **委托至** `forum_api.check_province_unrest()`
- CLI `phase_forum._execute_land_distribution()` → **委托至** `forum_api.execute_land_acts()`
- CLI `phase_senate._process_land_proposals()` → **委托至** `senate_api.auto_submit_proposals()`

## 5. senate_api 新增接口（Wave-03 Senate & Military）

### 5.1 `assign_governors() -> list[dict]`
- **用途：** 总督候选人筛选与分配（C-10a）
- **CLI 来源：** `phase_senate.py` ~L1441-1540
- **返回：** `[{province_id, governor_id, name, assigned_at}]`

### 5.2 `process_war_takeover(republic_state) -> dict`
- **用途：** 处理战争接管逻辑（C-10c）
- **CLI 来源：** `phase_senate.py` ~L905-991
- **返回：** `{takeover_executed: bool, war_id, affected_provinces, result_details}`

### 5.3 war_system 新增方法（Wave-03，由 CLI→API 下沉调用）

| 方法 | 用途 | 缺口 |
|:-----|:-----|:----:|
| `assign_rebellion_commanders()` | 起义指挥官指派 | C-10b |
| `auto_recruit_and_assign()` | 军团征召与指派 | C-10d |

详见 `MVP0.3-02_战争系统.md` v1.1。

## 6. Wave-04 Finale 新增接口

### 6.1 `population_api.convert_battlefield_commanders(state: GameState) -> dict`
- **用途：** 人口阶段结束后，将战场指挥官（执政官→资深执政官、执法官→资深执法官）转入行省总督状态（C-E2）
- **CLI 来源：** `phase_population.py` ~L567-600
- **逻辑：** 扫描存活成员中离任的执政官/执法官 → 记录 office history → 转换官职 → 更新 influence
- **返回：** `{converted: [{figure_id, old_office, new_office, province_id}], summary: str}`
- **处理边界：** 无离任指挥官 → 返回空列表；指挥官无战争 → fallback to current_turn-1

### 6.2 `senate_api.auto_vote(state: GameState, player_id: str, proposals: list, vote_decider=None) -> dict`
- **用途：** AI 派系自动对元老院提案进行投票（C-10e）
- **CLI 来源：** `phase_senate.py` ~L1033-1060, ~L1320-1336
- **逻辑：** 验证派系 → 跳过已投票提案 → 使用 vote_decider 决策（默认 AutoSenateVoteDecider）
- **返回：** `{voted: [], skipped: [], errors: [], summary: str}`
- **处理边界：** 玩家已投 → 跳过；无效派系 → 报错；无提案 → 空结果

### 6.3 `GameState.check_victory_conditions() -> dict`
- **用途：** 决算阶段检查胜利/失败条件（C-08-01）
- **CLI 来源：** `phase_resolution.py` → `resolution_api.execute_resolution()`
- **src（Core 层，非 API 模块，但作为调用链统一入口列于此）**
- **检查项：**
  1. 国库连续赤字（`treasury_deficit_turns >= national_opex_deficit_limit`）
  2. 军团全军覆没（所有 legion status == DESTROYED）
  3. 行省大范围暴动（grievance >= 3 的行省 > 50%）
  4. 派系独裁（单派系影响力 >= 70%）
  5. 意大利本土民怨（province(0).grievance >= 3）
  6. 元老院主导派系（影响力占比最高派系）
- **返回：** `{game_over: bool, conditions: [{type, triggered, details, critical}], summary: {top_faction, share}}`

### 6.4 `resolution_api.execute_resolution(state: GameState, player_id: Optional[str] = None) -> dict`
- **用途：** 决算阶段共享用例（S2），CLI 和 GUI 的唯一结算入口
- **类型：** 阶段级公共用例
- **执行顺序：**
  1. 前置检查（combat 已执行、resolution 未执行）
  2. `state.check_victory_conditions()` — 胜利条件检查
  3. `ms.process_legion_recovery(turn_number)` — 军团恢复
  4. `state.clear_active_events()` — 清除本回合事件
  5. `state.mark_phase_executed("resolution")` — 标记阶段已执行
  6. `state.record_phase_result("resolution", dto)` — 记录决算 DTO
- **不负责：** 推进到下一年度（`advance_year()` 是独立的 Player Command）
- **CLI 入口：** `ResolutionCommand.execute()` → `resolution_api.execute_resolution()`
- **GUI 入口：** `session_store._executeResolution()` → `adapter.execute_phase("resolution", ...)` → `game_api.execute_phase()` → `ResolutionCommand.execute()` → `resolution_api.execute_resolution()`
- **返回（api_response 格式）：**
  ```python
  {
      "success": bool,
      "message": str,
      "data": ResolutionResultDTO({
          "year": int,
          "year_display": str,
          "victory": dict,               # check_victory_conditions 的原样结果
          "legion_recovery": dict,         # {recovered, recovered_ids, details}
          "key_events": List[str],         # 触发的胜利条件 + 军团恢复事件
          "events_cleared": bool,
      })
  }
  ```
- **错误处理：**
  - `combat_not_executed`: `success=False`
  - `resolution_already_executed`: `success=False`（幂等保护）
  - 未知异常: `success=False` + traceback

### 6.5 `ResolutionResultDTO` 展示（ResolutionStage.qml）
- **数据来源：** `sessionStore.resolutionResults` → `session_api.get_resolution_view()` → `_build_resolution_results()`
- **新增字段（由 execute_resolution 存储的 phase result 提供）：**
  - `results.victory` — 胜利/失败条件
  - `results.legion_recovery` — 军团恢复摘要
  - `results.key_events` — 关键事件列表
  - `results.events_cleared` — 事件清除标记
- **QML 展示：** `ResolutionStage.qml` summaryPanel 底部三个只读行（胜利条件 / 军团恢复 / 关键事件）

## 7. population_api 新增接口 (WP-02b Vote Batch v2.1)

### 7.1 `population_api.batch_vote(state: GameState, player_id: str, entries: list) -> dict`
- **用途:** 人口阶段投票批量原子提交（取代逐项 doVote）
- **内部委托:** `population_service.check_and_commit_vote()` → GameState 事务 API
- **entries 格式 (v2.1):** `[{"office": str, "figure_id": int}]`；office=合法公职名；figure_id=0=弃权(ABSTAIN, FC-03)
- **v2.1 变更:** 移除 choice 字段；新增 office 字段（必填）；移除 inline resolve_election（FC-09）
- **返回:** `api_response(success, message, data={vote_count, offices_voted, already_committed, retryable}, errors=[])`
- **幂等 (FC-06):** signature = `(player_id, frozenset((office, figure_id) for each entry))`；同签名重复 → `already_committed=true, vote_count=0`
- **重入/并发 (FC-07):** 同线程重入 → BUSY；并发 → 一个 ACQUIRED 其余 BUSY；guard 使用 threading.Lock（非可重入）
- **事务:** snapshot → write (via record_population_vote) → marker → completion；异常完整回滚 + guard 释放
- **前置条件 (FC-01):** batch 必须恰好包含 5 条 entry（每 office 一条）；空/部分 → structured failure, zero write
- **重复 office (FC-04):** 同批重复 → DUPLICATE_OFFICE structured failure, zero write
- **结算 (FC-09):** 由 resolve_population_slice() 在所有玩家完成后统一触发；batch_vote 内不触发
- **调用方:** CLI `phase_population._vote_all()`；旧 GUI `sessionStore.batchVote(entries)` → `api_adapter.batch_vote()` 仅保留兼容，PopulationStage v3.0 正式路径见 §7.3

### 7.2 `session_api.resolve_population_slice(state: GameState) -> dict`
- **用途:** 人口阶段选举结算统一触发（FC-09 G5-R1）
- **前置条件:** 所有人类玩家完成投票（AI 玩家自动完成）
- **未完成:** structured failure (code=VOTE_NOT_ALL_COMPLETE), zero phase result, zero office change
- **完成:** 调用 resolve_election() → 记录 phase result → 返回 election_results

### 7.3 `session_api.submit_population_votes(state, player_id, selected_by_office) -> dict`（WP-02b v3.0）

- **正式 GUI 调用链:** `PopulationStage.qml submitPopulationVotes(selectedVotes)` → `GuiSessionStore.submitPopulationVotes()` → `api_adapter.submit_population_votes()` → 本用例。
- **输入:** `selected_by_office` 为 0～5 个选择的 map；key 只能是固定五 office，value 必须是严格正整数。显式 `0`、`null`、`bool`、负数与未知 office 返回 structured failure、zero write。
- **FC-03 规范化:** Session 按 `consul → censor → praetor → quaestor → tribune` 固定顺序生成恰五条 backend entry；QML 缺失 key 在此物化为 `figure_id=0`。Backend `batch_vote()` 的五条/完整 office 契约不放松。
- **成功编排:** batch commit → next-player；仍有未完成人类玩家返回 `data.status=awaiting_players`、`awaiting_player_id`、`resolved=false`；全部人类玩家完成时仅调用 `resolve_population_slice()`，返回 `data.status=resolved`、`resolved=true` 与 `election_results`。
- **失败边界:** `batch_vote()` 失败不 handoff、不 resolve；Adapter/Store 不补 office、不物化 0、不判断全员、不直接调用 `resolve_election()`。
- **FC-06/07 保持:** backend signature 仍为 `(player_id, frozenset((office, figure_id) ...))`，guard 仍使用 `threading.Lock`；GUI submitting 仅防重复交互，不替代二者。

## 8. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.7 | 2026-08-01 | WP-02b G5-R1: §7 更新至 v2.1（{office, figure_id} DTO, 无 choice, 无 inline resolution, Lock 非可重入, FC-09 前置条件, resolve_population_slice 结算入口）；新增 §7.2 |
| v1.6 | 2026-07-31 | WP-02b: 新增 population_api.batch_vote() 批量投票原子提交接口 (§7) |
| v1.5 | 2026-07-27 | S2: 新增 resolution_api.execute_resolution 共享用例 + ResolutionResultDTO + ResolutionStage 展示区 + CombatStage 颜色补丁 |
| v1.4 | 2026-07-26 | 新增 population_api.convert_battlefield_commanders / senate_api.auto_vote / GameState.check_victory_conditions（Wave-04 Finale） |
| v1.3 | 2026-07-26 | 新增 senate_api assign_governors / process_war_takeover + war_system 引用（Wave-03） |
| v1.2 | 2026-07-26 | 新增 check_province_unrest / execute_land_acts API + 调用链 |
| v1.1 | 2026-07-25 | 新增 generate_figures/generate_contracts API + 调用链说明 |
| v1.0 | 2026-07-17 | 初版 |
| v1.8 | 2026-08-01 | EOR20260801-02 B2 Pilot (DA ATTEMPT-1): §7.1 FC-06 signature 从 tuple(sorted(...)) 修正为 frozenset(...)（对齐 Contract Freeze Table FC-06 冻结值）；CI-1 Frozen Value Preservation |
| v1.9 | 2026-08-02 | WP-02b v3.0: 新增 §7.3 Session selection-map 规范化、awaiting_players/resolved 响应与 PopulationStage → Store → Adapter → Session 正式调用链；旧 GUI batchVote 标记为兼容路径 |
| v2.0 | 2026-08-21 | GUI-BETA-R1 WP-C: 新增 §3.4 canonical init（initialize_forum_turn + ODR-04 归属校验 + forum_initialized exactly-once）；open_market 切换 init（ODR-05 行形不变）；resolve_forum 前置 execute_land_acts；get_forum_view 新增 war_threats（016） |
