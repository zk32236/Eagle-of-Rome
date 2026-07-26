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

## 6. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.3 | 2026-07-26 | 新增 senate_api assign_governors / process_war_takeover + war_system 引用（Wave-03） |
| v1.2 | 2026-07-26 | 新增 check_province_unrest / execute_land_acts API + 调用链 |
| v1.1 | 2026-07-25 | 新增 generate_figures/generate_contracts API + 调用链说明 |
| v1.0 | 2026-07-17 | 初版 |
