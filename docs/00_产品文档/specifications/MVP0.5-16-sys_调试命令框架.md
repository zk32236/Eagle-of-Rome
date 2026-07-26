# MVP0.5-16-sys — 调试命令框架

> **功能简述：** 调试专用命令集（debug_war/debug_fleet 等舰队和战争内省命令、调试建造/指派命令），辅助开发与测试

## 1. 功能目的

调试命令框架为开发者提供一组不干扰正常游戏流程的内省和操作命令，用于：
- **快速诊断**：查看战争、舰队等实体的内部状态字段（正常接口不暴露）
- **快速建造**：跳过正常船坞建造流程，直接创建可用舰队
- **快速指派**：直接指派舰队到战争，绕过正常海战任务流程
- **建造检查**：手动触发舰队建造完成检测，加速测试周期

所有调试命令通过 CommandRegistry 自动注册，集成在 CLI 中，与普通命令调用方式一致。

## 2. 玩家/系统行为

### 2.1 系统行为

调试命令框架不自动执行，完全由用户（开发者/测试者）在 CLI 中手动触发。所有命令都扩展自 `Command` 基类，与 `CommandRegistry` 集成：

1. **自动注册**：`func_debug.py` 中的命令类在 `CommandRegistry` 扫描时被自动发现并注册
2. **执行方式**：用户在 CLI 中输入命令名和参数，注册器查找到对应类并实例化执行

### 2.2 玩家行为（开发者）

提供以下 6 个命令：

#### 2.2.1 `debug_fleet` / `df` — 舰队内省

显示指定舰队的内部状态，包括：
- 舰队名称、编号、类型、状态
- 指挥官 ID、经验值、基础战力、老兵标记
- 指派战争 ID、任务类型
- 目标战争 ID（建造时设定）
- 建造起始/结束回合
- 关联合同 ID
- 被摧毁回合

**用法**：`debug_fleet <fleet_id>` 或 `df <fleet_id>`

#### 2.2.2 `debug_war` / `dw` — 战争内省

显示指定战争的内部状态，包括：
- 名称、ID、状态、类型
- 指挥官 ID、指派军团数、指派舰队 ID
- 在 `active_wars` / `truce_wars` / `threats` 列表中的存在标记
- 和约对象、停战结束回合、威胁等级
- 海战需求标记、敌方海军当前值
- 原指挥官 ID、指挥官指派回合

**用法**：`debug_war <war_id>` 或 `dw <war_id>`

#### 2.2.3 `build_fleet` / `bf` — 调试建造舰队

跳过正常建造流程，直接创建一支舰队：
- 默认类型为 `trireme`，可选 `quadrireme` / `quinquereme`
- 可选指定指挥官
- 检查技术解锁（`pyrrhic_war_won`）
- 检查国库资金是否充足（按配置 `fleet_types[type].build_cost`）
- 直接扣款并创建可用舰队（状态 `AVAILABLE`，无建造期）

**用法**：`build_fleet [fleet_type] [commander_id]` 或 `bf [fleet_type] [commander_id]`

**前置条件**：`state.pyrrhic_war_won == True`

#### 2.2.4 `assign_fleet` / `af` — 调试指派舰队到战争

直接将舰队指派到指定战争：
- 检查舰队存在且状态为 `AVAILABLE`
- 检查战争存在且需要海战（`naval_required == True`）
- 调用 `naval_system.assign_fleet_to_war()`
- 可选指定指挥官

**用法**：`assign_fleet <fleet_id> <war_id> [commander_id]` 或 `af <fleet_id> <war_id> [commander_id]`

#### 2.2.5 `show_fleets` / `fl` — 显示所有舰队状态

列出所有舰队的概览信息：
- ID、名称、类型、状态（带表情符号）
- 指挥官名、战力值
- 异常安全：个人指挥官或战力获取失败时友好显示 `?`

**用法**：`show_fleets` 或 `fl`

#### 2.2.6 `process_fleet_construction` / `pfc` — 手动触发舰队建造检查

手动调用 `naval_system.process_fleet_construction()`，检查是否有在本回合完工的舰队建造。

**用法**：`process_fleet_construction` 或 `pfc`

### 2.3 输出格式

所有调试命令输出到 stdout，格式自由（非结构化文本）。失败时打印 `❌` 前缀错误信息，成功时打印 `✅` 或 `🔍` 前缀。

### 2.4 权限

当前版本无权限校验——所有调试命令对任何用户开放（仅可通过 CLI 访问，最终用户不直接接触调试 CLI）。

## 3. 核心规则

### 3.1 命令定义规范

每个调试命令类必须：
- 继承 `Command`（`sys_base.py`）
- 声明类属性 `name`（主名）、`aliases`（别名列表）、`description`（帮助文本）
- 实现 `execute(args: List[str]) -> bool` 方法

### 3.2 DebugFleetCommand 字段映射

| 输出字段 | 代码属性 | 说明 |
|----------|----------|------|
| 名称 | `fleet.name` | 舰队名称 |
| 编号 | `fleet.number` | 舰队号码 |
| 类型 | `fleet.fleet_type` | 舰队类型（trireme 等） |
| 状态 | `fleet.status.value` | 状态枚举值 |
| 指挥官ID | `fleet.commander_id` | 关联人物 ID |
| 经验 | `fleet.experience` | 经验值 |
| 基础战力 | `fleet._strength_base` | 私有属性，基础战斗力量 |
| 是否老兵 | `fleet.is_veteran` | 老兵标记 |
| 指派战争ID | `fleet.assigned_war_id` | 已指派的战争 ID |
| 指派任务类型 | `fleet._assigned_mission_type` | 私有属性，任务类型 |
| 目标战争ID | `fleet._target_war_id` | 建造时设定的目标战争 ID |
| 建造开始回合 | `fleet.build_start_turn` | 建造起始回合 |
| 建造结束回合 | `fleet.build_end_turn` | 建造结束回合 |
| 关联合同ID | `fleet.contract_id` | 舰队建造合同 ID |
| 被摧毁回合 | `fleet.destroyed_turn` | 舰队被摧毁的回合 |

### 3.3 DebugWarCommand 字段映射

| 输出字段 | 代码属性 | 说明 |
|----------|----------|------|
| 状态 | `war.status.value` | 状态枚举值 |
| 类型 | `war.war_type.value` | 战争类型枚举值 |
| 指挥官ID | `war.commander_id` | 关联人物 ID |
| 指派军团数 | `war.legions_assigned` | 已指派军团数量 |
| 指派舰队ID | `war.assigned_fleet_ids` | 已指派舰队 ID 列表 |
| 在 active_wars | `war in ws._active_wars` | 是否在活跃战争列表 |
| 在 truce_wars | `war in ws._truce_wars` | 是否在停战列表 |
| 在 threats | `war in ws._threats` | 是否在威胁列表 |
| 和约 | `war.peace_treaty` | 和约对象 |
| 停战结束回合 | `war.truce_end_turn` | 停战到期回合 |
| 威胁等级 | `war.threat_level` | 威胁等级值 |
| 需要海战 | `war.naval_required` | 海战需求标记 |
| 敌方海军当前 | `war.enemy_naval_current` | 敌方当前海军力量 |
| 原指挥官ID | `war.original_commander_id` | 原始指挥官 ID |
| 指挥官指派回合 | `war.commander_assigned_turn` | 指挥官被指派的回合 |

### 3.4 BuildFleetCommand 前置条件

| 条件 | 说明 |
|------|------|
| `naval_system` 就绪 | `self.state.naval_system` 非 None |
| 技术解锁 | `self.state.pyrrhic_war_won == True` |
| 舰队类型有效 | 必须是 `trireme` / `quadrireme` / `quinquerere` 之一 |
| 舰队类型配置存在 | `config["economic_rules.fleet_types"][type]` 存在 |
| 国库资金充足 | `state.treasury >= config["build_cost"]` |

### 3.5 AssignFleetCommand 前置条件

| 条件 | 说明 |
|------|------|
| 舰队存在 | `fleet_id` 有效 |
| 舰队状态 | `fleet.status == FleetStatus.AVAILABLE` |
| 战争系统就绪 | `ws` 非 None |
| 战争存在 | `war_id` 有效 |
| 海战需求 | `war.naval_required == True` |

## 4. 输入、输出与依赖

### 4.1 输入

| 命令 | 参数 | 类型 |
|------|------|------|
| `debug_fleet` | `fleet_id: int` | 必选 |
| `debug_war` | `war_id: str` | 必选 |
| `build_fleet` | `fleet_type: str`（可选）, `commander_id: int`（可选） | 可选 |
| `assign_fleet` | `fleet_id: int`, `war_id: str`, `commander_id: int`（可选） | 必选+可选 |
| `show_fleets` | 无 | — |
| `process_fleet_construction` | 无 | — |

### 4.2 输出

| 命令 | 成功输出 | 失败输出 |
|------|----------|----------|
| `debug_fleet` | `🔍 舰队 <name> 内部状态：...` | `❌ 舰队 <id> 不存在` 等 |
| `debug_war` | `🔍 战争 <name> 内部状态：...` | `❌ 战争 <id> 不存在` 等 |
| `build_fleet` | `✅ 舰队 <name> 建造完成` | `❌ 海军系统未就绪` 等 |
| `assign_fleet` | `✅ 舰队 <name> 指派至战争 <name>` | `❌ 指派失败` 等 |
| `show_fleets` | `⚓ 舰队状态：...` 表格 | `📭 没有舰队` |
| `process_fleet_construction` | `✅ 舰队 <name> 建造完成` | `ℹ️ 没有舰队在本回合完工` |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `Command` (sys_base.py) | 命令抽象基类 |
| `CommandRegistry` (sys_registry.py) | 自动扫描注册 |
| `GameState.naval_system` | 海军系统实例 |
| `GameState.get_war_system()` | 战争系统实例 |
| `WarSystem.get_war_by_id()` | 按 ID 查找战争 |
| `NavalSystem.get_fleet()` | 按 ID 查找舰队 |
| `NavalSystem.get_all_fleets()` | 获取所有舰队 |
| `NavalSystem.process_fleet_construction()` | 检查完工建造 |
| `NavalSystem.assign_fleet_to_war()` | 指派舰队到战争 |
| `Fleet` 实体 | 舰队实体类 |
| `War` 实体 | 战争实体类 |
| `FleetStatus` 枚举 | 舰队状态枚举 |
| `Figure` (通过 get_living_member) | 指挥官验证 |

## 5. 状态与边界

### 5.1 错误输入处理

| 场景 | 处理方式 |
|------|----------|
| `debug_fleet` 无参数 | `❌ 请指定舰队编号` |
| `debug_fleet` 参数非整数 | `❌ 舰队编号必须为整数` |
| `debug_war` 无参数 | `❌ 请指定战争ID` |
| `build_fleet` 无效类型 | `❌ 无效舰队类型，可选：trireme, quadrireme, quinquereme` |
| `build_fleet` 指挥官参数非整数 | `❌ 指挥官ID必须为整数` |
| `build_fleet` 指挥官不存在 | `❌ 指挥官 <id> 不存在或已死亡` |
| `build_fleet` 国库不足 | `❌ 国库资金不足，需要 X，现有 Y` |
| `build_fleet` 技术未解锁 | `❌ 舰队技术尚未解锁（需要皮洛士战争胜利）` |
| `assign_fleet` 参数不足 | `❌ 用法: assign_fleet <fleet_id> <war_id> [commander_id]` |
| `assign_fleet` 舰队不存在 | `❌ 舰队 <id> 不存在` |
| `assign_fleet` 舰队不可指派 | `❌ 舰队当前状态 <status>，无法指派` |
| `assign_fleet` 战争不需要海战 | `❌ 战争 <name> 不需要海战` |
| `show_fleets` 海军系统未就绪 | `❌ 海军系统未就绪` |

### 5.2 异常安全

- `show_fleets` 对单个舰队战力计算进行 `try-except` 保护，单舰失败不影响整体列表显示
- `show_fleets` 顶层也有 `try-except`，最坏情况打印 `❌ 显示舰队时发生错误`
- 所有命令通过 `CommandRegistry.execute()` 的 `try-except` 统一兜底

### 5.3 命令名冲突

- `func_debug.py` 中的命令名/别名不得与其他模块冲突
- `CommandRegistry` 在注册时检测重复，发现冲突抛出 `ValueError`

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | `debug_fleet` 查看存在的舰队 | 正确显示 14+ 个内部状态字段 |
| 2 | `debug_fleet` 查看不存在的舰队 | `❌ 舰队 9999 不存在` |
| 3 | `debug_war` 查看存在的战争 | 正确显示 15+ 个内部状态字段 |
| 4 | `debug_war` 查看不存在的战争 | `❌ 战争 xxx 不存在` |
| 5 | `build_fleet trireme`（技术已解锁） | 舰队创建成功，国库扣除对应费用 |
| 6 | `build_fleet` 技术未解锁 | `❌ 舰队技术尚未解锁` |
| 7 | `build_fleet` 国库不足 | `❌ 国库资金不足` |
| 8 | `assign_fleet` 将可用舰队指派到海战战争 | 舰队状态变为 ON_MISSION |
| 9 | `assign_fleet` 舰队已在任务中 | `❌ 无法指派` |
| 10 | `assign_fleet` 战争不需海战 | `❌ 战争不需要海战` |
| 11 | `show_fleets` 有舰队 | 列出所有舰队，含状态表情符号 |
| 12 | `show_fleets` 无舰队 | `📭 没有舰队` |
| 13 | `process_fleet_construction` 有完工 | `✅ 舰队 xxx 建造完成` |
| 14 | `process_fleet_construction` 无完工 | `ℹ️ 没有舰队在本回合完工` |
| 15 | 所有命令通过 help 可见 | help 列表中包含 df, dw, bf, af, fl, pfc |

## 7. 历史演化与证据

- 历史审计入口：HF-036
- 历史名称：调试命令（Debug Commands）
- 首次实现版本：MVP 0.5 (2026-03-09)
- 演化：最初作为海军系统（MVP0.7-04）的测试配套引入。`DebugFleetCommand` 和 `DebugWarCommand` 提供深层内省能力，`BuildFleetCommand`/`AssignFleetCommand` 加快测试周期。`ShowFleetsCommand` 和 `ProcessFleetConstructionCommand` 在后续版本中补充。所有命令通过 `CommandRegistry` 自动注册，与 `func_debug.py` 文件一起纳入命令体系。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-16-sys_调试命令框架.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent C | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
