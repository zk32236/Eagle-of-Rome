# MVP0.3-04 — 场景加载器

> **功能简述：** 场景数据加载、派系初始化、人物生成与官职分配、行省初始化、玩家创建的统一入口

## 1. 功能目的

场景加载器是游戏启动的必经入口，负责将 JSON 配置文件中定义的场景数据（派系、人物、国库、行省等）解析并注入到 `GameState` 中，构建完整的初始游戏世界。其核心目的包括：

- **配置化场景管理**：通过 JSON 文件定义不同测试/发布场景，避免硬编码启动参数
- **派系动态化**：支持任意数量和 ID 的派系配置，无需修改代码即可调整初始派系格局
- **人物自动化生成**：按派系分层生成贵族（Nobile）、骑士（Eques）、平民（Plebeian），并依据权力分配历史官职
- **行省数据加载**：从独立 JSON 文件加载行省定义，为行省系统奠定数据基础
- **总督初始化**：为已征服行省（意大利除外）分配具有对应公职历史的人物担任总督
- **玩家创建**：为每个派系创建 `Player` 实体，设定回合顺序和当前玩家

## 2. 玩家/系统行为

### 2.1 场景加载流程（系统行为）

入口：`ScenarioLoader.load_scenario(state, scenario_file)`

1. **状态重置**：调用 `state.reset()` 清空所有游戏状态
2. **配置加载**：
   - 尝试从 `data/scenarios/<scenario_file>` 读取 JSON 配置文件
   - 文件不存在或解析失败 → 使用 `_get_default_config()` 默认配置
   - 打印文件加载失败的警告信息
3. **回合与年份设置**：从配置读取 `start_year`（默认 -264），创建 `GameTurn(turn_number=1, year=start_year)`
4. **派系加载**：调用 `_load_factions()` 遍历配置中 `initial_state.factions` 数组，逐个创建 `Faction` 实体
5. **人物加载**：调用 `_load_figures()` 按每个派系分别生成指定数量的人物
6. **国库与公地初始化**：
   - 国库：`state.treasury = config["initial_state"]["treasury"]`（默认 100）
   - 国家公地：`state._national_public_land = state.config["economic_rules.initial_national_public_land"]`（默认 1000）
7. **派系领袖初始化**：调用 `_initialize_faction_leaders()` 为每个派系按影响力最高者标记领袖
8. **行省数据加载**：
   - 从 `data/cards/provinces.json` 加载所有行省定义
   - 为每个行省创建 `Province` 实体
   - 确保意大利行省（ID 0）的征服状态为 `True`（即使文件中为 `False`）
9. **总督初始化**：调用 `_assign_initial_governors()` 为已征服的行省分配总督
10. **玩家创建**：调用 `_create_players_from_factions()` 为每个派系创建 `Player`，设置回合顺序，设定当前玩家

### 2.2 动态派系与人物生成规则

人物生成配置位于 `config["initial_state"]["figure_generation"]["per_faction"]` 中，每个派系独立执行。

| 阶层 | 默认数量 | 默认年龄范围 | 生成方法 |
|------|:--------:|:------------:|----------|
| Nobile（贵族） | 3 | 35~50 | `Figure.create_nobile(id, faction_id, age)` |
| Eques（骑士） | 2 | 25~40 | `Figure.create_eques(id, faction_id, age)` |
| Plebeian（平民） | 1 | 25~35 | `Figure.create_plebeian(id, faction_id, age)` |

### 2.3 官职分配规则

贵族人物中，按影响力从高到低分配历史官职：

| 排序 | 官职 | 条件 | 额外属性增强 |
|:----:|------|------|-------------|
| 第1名 | 前执政官（Ex-Consul） | 影响力最高 | 魅力(Charisma) ≥ 8 |
| 第2名 | 前大法官（Ex-Praetor） | 影响力次高 | 智力(Intelligence) ≥ 8 |
| 第3名 | 前财务官（Ex-Quaestor） | 影响力第三高 | 战术(Martial) ≥ 7 |

历史官职记录通过 `add_office_history()` 写入。

### 2.4 私地分配规则

`_set_land_by_office()` 按人物的最高官职设置初始私地：

| 最高官职 | 私地数量 |
|----------|:--------:|
| Consul（执政官） | 3 |
| Praetor（大法官） | 2 |
| Quaestor（财务官） | 1 |
| 无历史官职的贵族 | 随机 1~3 |
| 骑士（Eques） | 0 |
| 平民（Plebeian） | 0 |

### 2.5 总督分配规则

`_assign_initial_governors()` 为每个已征服且非意大利的行省分配总督：

1. 跳过意大利（ID 0）和未征服行省（`conquered == False`）
2. 根据行省的 `governor_type` 确定需要的官职类型：
   - `"proconsul"` → 需要曾担任执政官（`office_type = "consul"`）的人物
   - `"propraetor"` → 需要曾担任大法官（`office_type = "praetor"`）的人物
3. 筛选候选人：存活、未缺席、无当前官职、且历史任期中有对应官职类型且已结束
4. 从候选人中随机选择一位
5. 分配效果：
   - 行省设置 `_governor_id` 和 `_governor_since`
   - 人物设置 `is_absent = True`、`office = province.governor_type`
   - 调用 `update_influence()` 更新影响力
6. 无合格候选人时跳过，打印 `⚠️` 提示

### 2.6 玩家创建与回合顺序

`_create_players_from_factions()` 按派系列表顺序创建玩家：

1. 遍历 `state.factions`，为每个派系创建一个 `Player`
   - `player_id = "player_{faction.id}"`
   - `player_type`: 派系 `is_player` 为 `True` 时为 `HUMAN`，否则为 `AI`
   - `is_online = False`
2. 设置回合顺序：`["player_{f1.id}", "player_{f2.id}", ...]`
3. 设定第一个玩家为当前玩家

### 2.7 CLI 加载命令

`LoadCommand`（`func_load.py`）封装了场景加载的用户接口：

1. 命令：`load [filename]`（别名 `l`）
2. 默认加载 `mvp_test.json`
3. 调用 `ScenarioLoader.load_scenario(state, scenario_file)`
4. 成功后打印：
   - 游戏启动时间戳
   - 横幅 "Eagle of Rome - MVP 0.5"
   - 开始年份显示（BC/AD）
   - 国库资金（Talents）
   - 已征服行省列表（意大利标注为"本土"）
5. 失败时：
   - `FileNotFoundError` → 打印场景文件不存在信息
   - 其他异常 → 打印错误信息并打印调用栈

### 2.8 内置派系详细信息显示

`_display_faction_details()` 在加载后输出：
- 当前年份、回合、阶段、国库
- 每个派系的前公职信息（由 `_get_ex_office_info()` 按三人互不重复规则查找）
- 派系领袖及其影响力
- 每个派系的成员列表（含状态图标、阶层图标、ID、姓名）
- 派系总影响力
- 进度条 `[░░░░░░░] 0/7`

## 3. 核心规则

### 3.1 加载顺序

加载流程不可逆，固定顺序为：
```
重置 → 配置 → 回合 → 派系 → 人物 → 国库 → 公地 → 领袖 → 行省 → 总督 → 玩家
```

### 3.2 配置优先级

```
显式 JSON 配置文件 > _get_default_config() 默认值
```

- JSON 文件需位于 `data/scenarios/` 目录
- 默认配置文件路径：`<project_root>/data/scenarios/<scenario_file>`
- 未指定文件或文件不存在时自动回退默认配置

### 3.3 人物生成规则

| 规则 | 说明 |
|------|------|
| 阶层配置 | 每个派系独立生成 Nobile×3、Eques×2、Plebeian×1（可配置） |
| 年龄范围 | 可配置，默认 Nobile 35-50、Eques 25-40、Plebeian 25-35 |
| 人物ID | 全局递增，从 1 开始 |
| 官职分配 | 贵族按权力排序前3名分别获得执政官/大法官/财务官历史 |
| 私地计算 | 按最高官职确定 0~3，骑士与平民始终为 0 |
| 影响力初始化 | 生成后统一调用 `update_influence()` |

### 3.4 派系初始化规则

| 规则 | 说明 |
|------|------|
| 国库 | 所有派系初始国库一致，从配置 `faction_initial_treasury` 读取（默认 10） |
| 成员列表 | 人物生成后自动加入 `faction.member_ids` |
| 领袖 | 按 `update_faction_leader()` 取派系中影响力最高的存活在罗马人物 |

### 3.5 行省与总督规则

| 规则 | 说明 |
|------|------|
| 行省数据源 | 独立文件 `data/cards/provinces.json` |
| 意大利特殊处理 | ID 0 的行省强制 `conquered = True` |
| 公/私地默认比例 | 未指定时按 `total_land × 0.6 / 0.4` 分配 |
| 总督分配合格条件 | 人物存活、未缺席、无当前官职、有对应官职历史且任期已结束 |
| 总督选择方式 | 随机选取一名合格候选人 |

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 场景配置 | `data/scenarios/<filename>.json` | 场景参数 JSON 文件 |
| 默认配置 | `_get_default_config()` | 回退默认值 |
| 行省数据 | `data/cards/provinces.json` | 行省定义 JSON 文件 |
| 文件名参数 | CLI 传入（默认 `"mvp_test.json"`） | 场景文件名 |
| 经济规则配置 | `state.config["economic_rules.*"]` | 派系初始资金、公地初始值 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| `GameState` | 内存状态 | 填充所有初始数据后的游戏状态 |
| 控制台打印 | stdout | 加载过程中的提示（含警告、总督分配信息） |
| CLI 横幅 | stdout | `LoadCommand.execute()` 输出的游戏启动信息 |

### 4.3 依赖

| 依赖模块 | 说明 |
|----------|------|
| `src.core.game_state.GameState` | 游戏状态容器，提供 `reset()`、`add_faction()`、`add_member()`、`add_province()`、`add_player()` 等 |
| `src.core.entities.figure.Figure` | 人物实体，提供工厂方法 `create_nobile()`、`create_eques()`、`create_plebeian()` |
| `src.core.entities.figure.ClassTier` | 社会阶层枚举（NOBILE / EQUES / PLEBEIAN） |
| `src.core.entities.entities.Faction` | 派系实体 |
| `src.core.entities.entities.GameTurn` | 回合状态 |
| `src.core.entities.province.Province` | 行省实体 |
| `src.core.entities.player.Player` / `PlayerType` | 玩家实体及类型 |

## 5. 状态与边界

### 5.1 正常加载状态

场景加载完成后，`GameState` 应包含：
- 已重置的干净状态（无残留数据）
- 1 个 `GameTurn` 对象（`turn_number=1`）
- N 个 `Faction` 对象（派系数量由配置决定）
- 每个派系：
  - N × 3 个 Nobile、N × 2 个 Eques、N × 1 个 Plebeian（默认）
  - 各人物的 `office_history` 中按权力排序分配历史官职
  - 各人物的 `_land_private` 按最高官职设定
  - 各人物的 `influence` 已更新
  - 有且仅有一个派系领袖（影响力最高者）
- M 个 `Province` 对象（由 provinces.json 决定）
  - 意大利（ID 0）`conquered = True`
  - 已征服且非意大利的行省有初始总督（若有合格候选人）
- N 个 `Player` 对象（每个派系一个）
- 回合顺序数组和当前玩家已设定

### 5.2 异常状态

| 条件 | 行为 |
|------|------|
| JSON 文件解析失败 | 回退默认配置，打印 `⚠️` 警告 |
| JSON 文件不存在 | 回退默认配置，打印 `⚠️` 警告 |
| 行省数据文件不存在 | 抛出 `FileNotFoundError`（不可回退） |
| CLI 加载时文件不存在 | `LoadCommand` 返回 `False`，打印 `❌` 错误 |
| 无派系配置 | 无派系则无人物、无玩家，但行省数据仍可加载 |
| 某行省无合格总督候选人 | 跳过该行省，打印 `⚠️` 提示，留空继续 |

### 5.3 边界条件

| 边界 | 处理方式 |
|------|----------|
| `per_faction` 配置为空或缺失 | 使用默认值 nobile=3, eques=2, pleb=1 |
| `figure_generation` 配置缺失 | 跳过人物生成（仍是默认配置的实例化） |
| 只有 1 个贵族 | 仅有第1名前执政官，无praetor/quaestor分配 |
| 只有 2 个贵族 | 仅有前执政官和前大法官，无前三分配 |
| 派系数量为 0 | `_create_players_from_factions()` 直接返回，无玩家创建 |
| provinces.json 中意大利 `conquered = False` | 强制设为 `True` |

### 5.4 重复加载

- `load_scenario()` 开头调用 `state.reset()`，确保重复加载不会叠加数据
- 人物 ID 重新从 1 开始计数

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 加载 `mvp_test.json` | 3 个派系按配置创建，is_player 标记正确 |
| 2 | 各派系人物数量 | 每个派系 3 贵族 + 2 骑士 + 1 平民 |
| 3 | 贵族最高权力者获执政官历史 | `office_history` 包含 "consul" |
| 4 | 贵族次高权力者获大法官历史 | `office_history` 包含 "praetor" |
| 5 | 贵族第三权力者获财务官历史 | `office_history` 包含 "quaestor" |
| 6 | 各人物私地按官职设定 | 执政官=3，大法官=2，财务官=1，骑士/平民=0 |
| 7 | 派系初始国库 | 统一等于配置的 `faction_initial_treasury`（默认 10） |
| 8 | 意大利行省始终为征服状态 | `italy.conquered == True` |
| 9 | 非意大利已征服行省获得总督 | 总督为有对应官职历史的人物 |
| 10 | 无合适总督时行省留空 | 无 `governor_id`，打印 `⚠️` 提示 |
| 11 | 玩家创建 | 每个派系对应一个 `Player`，回合顺序按派系列表 |
| 12 | 当前玩家 | 设置为第一个派系的玩家 |
| 13 | 无派系时无玩家创建 | 玩家列表为空，当前玩家为 `None` |
| 14 | 文件不存在时回退默认配置 | 使用默认场景启动 |
| 15 | CLI `load` 命令成功 | 打印横幅和时间戳信息 |
| 16 | CLI `load` 指定不存在文件 | 返回 `False`，打印错误信息 |
| 17 | 派系领袖标记 | 每个派系有且仅有一个 `is_faction_leader = True` 的人物 |

## 7. 历史演化与证据

- **历史审计入口**：
- **历史名称**：场景加载器
- **首次实现版本**：MVP 0.3
- **演化**：
  - MVP 0.3：基础场景加载、派系初始化、人物生成
  - MVP 0.4：配置化版本，支持动态派系数量、分层人物生成、按权力分配官职、官职对应私地
  - MVP 0.5：新增行省数据加载（`provinces.json`）、初始总督分配、`_create_players_from_factions()` 玩家创建系统
  - 当前版本（MVP 0.5+/0.7）：行省数据融入 Province 实体的扩展字段（开发度、文化、宗教等），总督分配使用 `governor_type` 字段
- **相关模块**：`func_load.py`（CLI 加载命令封装）

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.3-04_场景加载器.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent H | 初版创建（基于当前代码完整审计） |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
