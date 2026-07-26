# MVP0.5-18-sys — 状态查询命令扩展

> **功能简述：** 游戏状态查询命令集（status/spl/spr/sf/fs/prov/contracts）以及完整的 API 层架构，实现 UI/游戏逻辑分离，支持分类状态查询（玩家、人物、行省、军团、派系、财政等）

---

## 第一部分：状态查询系统

### 1. 功能目的

状态查询系统为玩家（CLI 终端）和 GUI 提供统一的只读游戏状态信息访问入口。其设计目标包括：

1. **分类查询**：按不同业务域（财政、人物、派系、行省、合同等）提供专用查询命令，避免一次性输出过载
2. **概要/详情分级**：无参数时显示概要列表，指定 ID 时显示单条详细记录
3. **错误友好**：对无效参数（非整数 ID、越界 ID、不存在的 ID）给出明确错误提示
4. **i18n 就绪**：所有输出文本通过 `i18n.get()` 格式化，支持中/英文切换
5. **结构化数据**：每个查询同时返回格式化文本（`message`）和结构化数据（`data`），供 GUI 直接消费
6. **调试友好**：错误时输出 `success`/`message`/`errors` 三元组，便于 CLI 和自动化测试统一处理

### 2. 玩家/系统行为

#### 2.1 玩家行为（CLI 命令）

| 命令 | 别名 | 无参行为 | 有参行为 |
|------|------|----------|----------|
| `status` | `sts` | 显示国库、存活人物数、派系数、当前回合年份 | 不接受参数；参数将被忽略 |
| `status_public_land` | `spl` | 显示国家公地总量、单价、总价值、税率、年收益、当前国库 | 不接受参数 |
| `status_private_land` | `spr` | 显示所有存活人物的私地信息（含总计行） | 不接受参数 |
| `status_figure` | `sf` | 显示所有存活人物摘要（单行格式） | 显示指定人物的完整详细信息 |
| `factions` | `fs` | 显示所有活跃派系金库、成员数、总/平均影响力 | 不接受参数 |
| `province` | `prov` | 显示所有已征服行省概要 | 显示指定行省的完整详细信息 |
| *commands* 🚧 | *contracts* 🚧 | *合同查询（关联 MVP0.5-02/03，通过 `contract_api.py` 的 `get_contracts_status()` 实现）* — 🚧 API 已就绪，命令类暂未注册 | |

#### 2.2 系统行为

1. **命令注册**：所有状态查询命令在 `func_status.py` 中定义，通过 `Command` 基类的 `name`/`aliases` 元数据注册
2. **API 委托**：每个命令的 `execute()` 方法委托给对应的 API 模块函数，不直接访问 `GameState` 的私有字段
3. **API 返回**：所有 API 函数返回统一格式的字典 `{"success": bool, "message": str, "data": Any, "errors": List[str]}`
4. **i18n 格式化**：所有输出文本通过 `src.core.i18n` 模块的 `i18n.get()` 格式化（支持动态参数插值）
5. **数据提取**：API 模块中的 `_extract_*_data()` 私有函数负责从实体对象提取结构化数据，供 GUI 消费

### 3. 核心规则

#### 3.1 命令注册规则

- 每个命令类必须继承 `Command`（在 `sys_base.py` 中定义），实现 `execute(args)` 方法
- `name` / `aliases` / `description` 为类变量，通过元数据自动注册
- 命令通过 `__init__(self, state)` 接收 `GameState` 实例

#### 3.2 查询规则

- **存活检查**：所有人物查询默认仅返回 `is_dead=False` 的存活人物
- **征服检查**：行省查询中，`province.conquered == False` 的行省不被列在概要中，单行省详情返回特定错误信息
- **ID 校验**：人物 ID 必须为整数且在 `[1, MAX_MEMBER_ID=300]` 范围内（🔄 待实现：当前仅校验整数类型，运行时依赖 `get_member()` 隐式过滤越界 ID）
- **无数据处理**：当查询结果为空时（如无存活人物、无已征服行省），返回特定占位信息
- **总计行**：财务类概要（如私地信息）末尾附加计算结果汇总行

#### 3.3 格式规则

- **单行摘要格式**：人物摘要使用 `{status_emoji}{tier_emoji} ID:{id} {name} ({faction}) 影响力:{influence} 财富:{wealth} 人气:{popularity} 私地:{land} 老兵:{veterans} 官职:{office}` 格式
- **详情格式**：人物详情展示所有字段（包括影响力分项明细=私地×10+老兵×10+人气+家族×10+官职加成、公职历史、合同IDs、缺席状态等）

---

## 第二部分：API 层架构

### 1. 功能目的

API 层是 CLI 命令层与核心游戏逻辑之间的中间层，设计目标为：

1. **UI/游戏逻辑分离**：CLI 命令（`src/ui/commands/`）和 GUI（`src/api/session_api.py` + `gui_query_api.py`）均通过 API 层访问游戏逻辑，不直接操作 `GameState` 私有字段
2. **统一响应格式**：所有 API 函数返回 `{"success": bool, "message": str, "data": Any, "errors": List[str]}` 字典
3. **业务域划分**：按业务域（游戏全局、人物、派系、行省、合同、人口、元老院、战斗、收入、天命、广场、玩家、会话、GUI 查询）分散到独立模块
4. **权限检查**：修改类 API（如 `execute_phase`、`next_player`）检查 `is_current_player()`，查询类 API 不检查权限
5. **日志记录**：关键操作通过 `state.log_event()` 记录游戏事件日志
6. **GUI 安全过滤**：`session_api.py` 提供按 viewer 玩家的派系过滤的信息快照，防止信息泄露

### 2. 玩家/系统行为

#### 2.1 系统行为（通用 API 规则）

- 每个 API 模块接受 `GameState` 实例作为第一个参数
- 查询类 API 无权限检查，只读返回
- 修改类 API 检查 `player_id == state._current_player_id`（测试模式可通过 `testing.bypass_player_check` 跳过）
- 所有 API 函数返回 `api_response()` 标准格式
- 异常捕获：健壮的 API 函数（特别是 `session_api.py`、`senate_api.py`、`combat_api.py`）在顶层用 `try/except Exception` 包裹，返回含 `errors` 的失败响应，避免 GUI 崩溃

#### 2.2 阶段生命周期 API

每个可操作阶段（天命、收入、广场、人口、元老院、战斗）提供三个标准 API 方法：

| 方法 | 职责 | 权限要求 |
|------|------|----------|
| `get_*_view(state, viewer_player_id)` | 返回阶段只读 DTO，包含阶段状态、可执行动作、当前进度 | 无（仅检查 viewer 是否存在） |
| `execute_*_phase(state, viewer_player_id)` | 执行业务逻辑，记录 `phase_result` | 必须是当前玩家 |
| `advance_*_phase(state, viewer_player_id)` | 确认阶段结果，标记 `phase_executed`，推进到下一阶段 | 必须是当前玩家 |

例外：广场阶段分步骤（`retire_figure` → `open_market` → `recruit_figure`/`place_bid`/`buy_land`/`vote_triumph` → `resolve_forum` → `advance_forum_phase`），提供更细粒度的 API。

#### 2.3 API 模块列表

| 模块 | 文件 | 主要 API 函数 | 类别 |
|------|------|--------------|------|
| **game_api** | `src/api/game_api.py` | `get_status_summary()`, `get_public_land_info()`, `execute_phase()`, `execute_turn()`, `advance_year()` | 查询 + 修改 |
| **figure_api** | `src/api/figure_api.py` | `get_figure_info()`, `get_private_land_info()` | 查询 |
| **faction_api** | `src/api/faction_api.py` | `get_factions_status()` | 查询 |
| **province_api** | `src/api/province_api.py` | `get_province_info()` | 查询 |
| **contract_api** | `src/api/contract_api.py` | `get_contracts_status()` | 查询 |
| **player_api** | `src/api/player_api.py` | `get_players()`, `get_current_player()`, `next_player()` | 查询 + 修改 |
| **population_api** | `src/api/population_api.py` | `campaign()`, `vote()`, `get_candidates()`, `resolve_election()` | 查询 + 修改 |
| **forum_api** | `src/api/forum_api.py` | `get_forum_view()`, `retire_figure()`, `recruit_figure()`, `place_bid()`, `buy_land()`, `vote_triumph()`, `resolve_forum()`, `advance_forum_phase()` | 查询 + 修改 |
| **senate_api** | `src/api/senate_api.py` | `get_senate_view()`, `propose()`, `vote()`, `veto()`, `resolve_senate()`, `advance_senate_phase()` | 查询 + 修改 |
| **combat_api** | `src/api/combat_api.py` | `get_combat_view()`, `select_war()`, `do_combat_action()`, `confirm_battle_result()`, `advance_combat()` | 查询 + 修改 |
| **mortality_api** | `src/api/mortality_api.py` | `get_mortality_view()`, `execute_mortality_phase()`, `advance_mortality_phase()` | 查询 + 修改 |
| **revenue_api** | `src/api/revenue_api.py` | `get_revenue_view()`, `execute_revenue_phase()`, `advance_revenue_phase()` | 查询 + 修改 |
| **session_api** | `src/api/session_api.py` | `create_gui_prototype_session()`, `get_session_snapshot()`, `get_population_view()`, `complete_population_player()`, `resolve_population_slice()` | 查询 + 修改 |
| **gui_query_api** | `src/api/gui_query_api.py` | `get_global_query_result()`（支持 game_status / faction_info / war_list / legion_status 4 种完整查询 + 8 种占位查询） | 查询 |

### 3. 核心规则

#### 3.1 API 响应格式 (`api_response()`)

```python
def api_response(success: bool, message: str = "", data: Any = None,
                 errors: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "success": success,      # bool: 操作是否成功
        "message": message,      # str: 人类可读的消息
        "data": data,            # Any: 结构化数据（DTO 或 None）
        "errors": errors or []   # List[str]: 错误详情列表
    }
```

#### 3.2 权限规则

| API 类别 | 权限检查 | 例外 |
|----------|----------|------|
| 只读查询 API（`get_*`） | 不检查 | 所有查询（包括 `get_players()`、`get_faction_info()` 等）均允许任意调用 |
| 全局修改 API（`execute_phase`、`execute_turn`、`advance_year`、`next_player`） | `is_current_player()` | `testing.bypass_player_check` 配置可跳过 |
| 阶段内修改 API（`campaign`、`vote`、`retire_figure`、`recruit_figure` 等） | `is_current_player()` + 人物派系归属检查 | 各函数额外检查 `bypass_permission` 参数 |
| 阶段结算 API（`resolve_forum`、`resolve_election`、`resolve_senate`） | 无玩家权限检查 | 仅检查阶段未结算 |

#### 3.3 数据结构 DTO 规则

- 查询类 API 的 `data` 字段返回结构化字典/列表，字段名与实体类属性名一致（snake_case）
- 敏感信息（他派系金库）仅在 viewer 为本派系时暴露（`session_api.py` 的 `get_session_snapshot()` 实现）
- `_extract_*_data()` 私有函数用于实体对象 → DTO 转换，避免直接暴露实体引用
- `session_api.py` 中的 `get_session_snapshot()` 构建完整 GUI 快照（含阶段导航、可执行动作、全局警告等）

### 4. 输入、输出与依赖

#### 4.1 API 层依赖关系

```
CLI (func_status.py, phase_*.py) ──→ API 层 (game_api, figure_api, ...) ──→ GameState + 实体层
GUI (echarts/命令行直接调用 session_api) ──→ API 层 ──→ GameState + 实体层

API 层内部依赖：
  game_api ──→ phase_*.py（阶段命令类）
  session_api ──→ population_api, player_api, faction_api, figure_api
  senate_api ──→ PoliticalSystem
  forum_api ──→ LandTradingService
  mortality_api ──→ MortalityService
  revenue_api ──→ EconomicService
```

#### 4.2 输入

- **CLI 路径**：用户输入的字符串参数列表（`args: List[str]`），在 Command 层完成基本类型转换
- **GUI 路径**：JSON 序列化的参数（`viewer_player_id`、`figure_id`、`amount` 等），在 API 层进行完整校验
- **GameState**：所有 API 函数接受 `state: GameState` 作为第一个参数

#### 4.3 输出

- **CLI 路径**：`api_response` 的 `message` 字段通过 `print()` 输出到终端
- **GUI 路径**：`api_response` 整体序列化为 JSON 返回
- **日志**：通过 `state.log_event()` 输出到文件日志和内存日志

#### 4.4 依赖

| 模块 | 依赖 |
|------|------|
| `game_api` | `src/core.game_state.GameState`, `src.core.i18n`, 所有 `phase_*.py` 命令类 |
| `figure_api` | `GameState`, `Figure`, `ClassTier`, `TerminologyService`, `i18n` |
| `faction_api` | `GameState`, `i18n` |
| `province_api` | `GameState`, `Contract`, `ContractType`, `i18n` |
| `population_api` | `GameState`, `Figure`, `ClassTier`, `i18n` |
| `forum_api` | `GameState`, `Contract`, `WarStatus`, `LandTradingService`, `Figure`, `ClassTier`, `i18n` |
| `senate_api` | `GameState`, `PoliticalSystem`, `Auto*Decider`, `i18n` |
| `combat_api` | `GameState`, `War`, `WarStatus`, `i18n` |
| `mortality_api` | `GameState`, `MortalityService` |
| `revenue_api` | `GameState`, `EconomicService` |
| `session_api` | `GameState`, `ScenarioLoader`, `population_api`, `player_api`, `faction_api`, `figure_api`, `AutoPlayerProcessor` + 各 `Auto*Decider` |
| `gui_query_api` | `GameState`, 无其他 API 模块依赖 |

### 5. 状态与边界

#### 5.1 状态变更点

| 状态变更 | 触发 API | 变更内容 |
|----------|----------|----------|
| 阶段推进 | `advance_*_phase()` | `mark_phase_executed()` + `get_phase_result()` 检查 |
| 回合推进 | `advance_year()` | `turn.advance_year()` + 清空 `executed_phases` 和 `phase_results` |
| 玩家切换 | `next_player()` | 更新 `_current_player_id` |
| 人物属性变更 | `campaign()` | 扣财富、加人气、更新影响力 |
| 广场操作 | `retire_figure()` / `recruit_figure()` 等 | 修改 `_forum_pending` |
| 选举 | `resolve_election()` | 分配官职、更新 `leader_ids` |
| 元老院 | `propose()` / `vote()` / `veto()` / `resolve_senate()` | 提案记录、投票记录、否决记录、法案执行 |
| 战斗 | `do_combat_action()` | 战争状态修改、战斗结果记录 |
| 收入结算 | `execute_revenue_phase()` | 国库/派系资金变更 |
| 天命事件 | `execute_mortality_phase()` | 人物死亡、事件效果应用 |

#### 5.2 边界条件

| 边界 | 处理方式 |
|------|----------|
| 空游戏状态（`state == None`） | 返回 `api_response(False, "无效的游戏状态")` |
| viewer 玩家不存在 | 返回 `api_response(False, "Viewer player not found")` |
| 查询不存在的人物 ID | 返回 `api_response(False, i18n.get("figure_not_found"))` |
| 查询未征服行省 | 返回 `api_response(False, i18n.get("province_not_conquered"))` |
| 重复投票 | 返回 `api_response(False, i18n.get("error_already_voted"))` |
| 非骑士竞标合同 | 返回 `api_response(False, i18n.get("error_not_knight"))` |
| 淘汰派系领袖 | 返回 `api_response(False, i18n.get("error_cannot_retire_leader"))` |
| 无候选人时选举结算 | 返回空结果 `api_response(True, "无投票记录")` |
| 非当前玩家执行修改操作 | 返回 `api_response(False, i18n.get("error_not_your_turn"))` |

### 6. 验收标准

#### 6.1 状态查询命令

1. **AC-Q01**：`status` 命令正确显示国库金额、存活人物数、派系数量、当前回合和年份
2. **AC-Q02**：`spl` 命令正确显示国家公地总量、单价、总价值、税率和年收益
3. **AC-Q13**：`func_status.py` 中的所有命令均委托给 API 模块，不直接访问 `GameState` 私有字段
4. **AC-Q14**：每个 API 查询函数返回正确的 `{"success": true, "message": str, "data": dict/list, "errors": []}` 格式

#### 6.2 API 层架构

1. **AC-A01**：所有 API 函数通过 `api_response()` 返回统一格式
2. **AC-A08**：`gui_query_api.get_global_query_result()` 支持 4 种完整查询 + 8 种占位查询

### 7. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-18-sys_状态查询命令扩展.md)

### 8. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-17 | 系统 | 初始创建 |
