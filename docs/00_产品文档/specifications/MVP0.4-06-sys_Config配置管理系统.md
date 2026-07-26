# MVP0.4-06-sys — Config 配置管理系统

> **功能简述：** 游戏配置的集中管理：经济/战斗/政治/测试各域配置项、配置文件读写、默认值回退

## 1. 功能目的

Config 配置管理系统为整个游戏提供统一的配置查询接口，将原本散落在各模块中的硬编码默认值集中管理。通过 JSON 配置文件加载用户自定义配置，支持深度合并、点号路径访问和运行期重载，确保配置系统的灵活性和可维护性。

核心设计目标：
- **集中管理**：所有配置归口到 Config 类，减少模块间硬编码依赖
- **安全回退**：配置文件缺失/格式错误时自动使用内置默认值，不导致系统崩溃
- **结构化访问**：点号路径语法简化嵌套配置的读取
- **运行时热重载**：无需重启游戏即可重新加载配置
- **数据安全**：通过深拷贝防止外部篡改内部状态

## 2. 玩家/系统行为

### 2.1 系统行为

1. **初始化加载**
   - GameState 初始化时创建 Config 实例，传入配置文件路径（可选）
   - 若未指定路径或路径无效/文件不存在/JSON 格式错误，自动回退到内置默认配置
   - 控制台输出警告信息（`⚠️ 配置文件不存在` / `⚠️ 配置文件JSON解析错误` 等）
   - 加载的配置通过深合并与默认配置合并：用户配置覆盖默认值，未指定的字段保持默认

2. **配置访问**
   - 游戏逻辑通过 `config.get("section.key.subkey")` 点号路径获取配置值
   - 路径不存在时返回 `None` 或调用方指定的默认值
   - 各模块通过 GameState 封装方法间接访问常用配置（如 `get_economic_rule()`）

3. **运行时重载**
   - 通过 `config.reload()` 方法重新读取配置文件
   - 重载成功时更新当前配置；失败时保留原配置并返回 `False`
   - 无配置路径的实例调用 `reload()` 始终返回 `False`

4. **数据保护**
   - `to_dict()` 返回配置的深拷贝，外部修改不影响内部状态
   - `DEFAULTS` 类属性为只读模板，实例通过深拷贝使用

### 2.2 玩家行为

玩家通过 `reload` 命令（命令行）触发配置重载：
- 输入 `reload` → 调用 `Config.reload()` → 输出 `✅ 配置重载成功` 或 `⚠️ 配置重载失败，保持原配置`
- 输入 `terms [preset]` → 切换术语预设（独立于 Config，使用 TerminologyService）

## 3. 核心规则

### 3.1 配置加载优先顺序

```
内置 DEFAULTS → JSON 配置文件 → 用户通过配置文件覆盖
```

优先级：用户配置文件中的字段 > DEFAULTS 中的字段。深度合并时，嵌套字典按 key 递归合并，非字典值直接覆盖。

### 3.2 默认配置结构

```python
{
    "logging": {
        "enabled": True,
        "file_path": "logs/game.log",
        "max_bytes": 10485760,
        "backup_count": 3,
        "log_level": "INFO"
    },
    "political_rules": {
        "leader_cooldown_years": 10,
        "leaders_per_election": 2,
        "office_cooldowns": {"consul": 5, "praetor": 5, ...},
        "offices_per_election": {"consul": 2, "praetor": 2, ...},
        "min_ages": {"consul": 40, "praetor": 35, ...},
        "candidates_per_election": {"consul": 3, ...},
        "voting": {"finalist_count": 2, "tiebreaker": "highest_influence"}
    },
    "mortality_rules": {
        "event_deck": [...],
        "event_draw_count": 1,
        "death_count": 2
    },
    "economic_rules": {
        "base_tax": 100,
        "faction_stipend": 10,
        "legion_recruit_cost": 10,
        ...
    },
    "combat_rules": {
        "triumph_threshold": 12,
        "victory_threshold": 6,
        ...
    },
    "terminology_preset": "original"
}
```

### 3.3 错误处理

| 错误类型 | 系统行为 |
|----------|----------|
| 文件不存在 (`FileNotFoundError`) | 回退默认配置，控制台打印 `⚠️ 配置文件不存在` |
| JSON 解析错误 (`json.JSONDecodeError`) | 回退默认配置，控制台打印 `⚠️ 配置文件JSON解析错误` |
| 内容非字典 (`TypeError`) | 回退默认配置，控制台打印 `⚠️ 配置文件格式错误` |
| 权限不足 (`PermissionError`) | 回退默认配置，控制台打印 `⚠️ 配置文件权限不足` |
| 其他未知异常 | 回退默认配置，控制台打印 `⚠️ 配置文件加载未知错误` |

### 3.4 深度合并规则

- 两个字典的嵌套字典按 key 递归合并
- 非字典值（字符串、整数、列表等）直接覆盖
- 用户配置中的新 key 直接添加到结果中
- 用户配置使用 `copy.deepcopy` 复制，防止引用污染

### 3.5 点号路径解析规则

- `"section.key.subkey"` → 逐级访问 `config["section"]["key"]["subkey"]`
- 空字符串 → 返回 `default`
- 中间节点不是字典 → 返回 `default`
- 路径中任一级别 key 不存在 → 返回 `default`

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 配置文件路径 | `GameState.__init__(config_path)` | JSON 格式文件路径 |
| JSON 文件内容 | 文件系统 | 用户配置，覆盖默认值 |
| 查询键 | 各模块调用 `config.get(key)` | 点号分隔的路径字符串 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 配置字典 | 调用方 | `get()` 返回配置值或默认值 |
| `to_dict()` 深拷贝 | 序列化/存档 | 配置的独立快照 |
| 控制台警告 | stdout | 加载失败时打印配置错误信息 |
| 重载结果 | stdout | `✅ 配置重载成功` / `⚠️ 配置重载失败` |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `json` | 标准库 — 读取 JSON 配置文件 |
| `copy` | 标准库 — 深拷贝保护 |
| `pathlib.Path` | 标准库 — 检查文件存在性 |
| `GameState._config` | 游戏状态持有 Config 实例并提供封装方法 |
| `sys_config.ReloadCommand` | UI 层命令，调用 `config.reload()` |

## 5. 状态与边界

### 5.1 有效状态

- Config 实例创建后始终持有有效配置（默认配置保底）
- `self._config` 始终为完整配置字典（含所有默认字段）
- `reload()` 失败时内部配置不变

### 5.2 边界条件

- **无路径创建**：`Config()` 使用纯默认配置，`path` 属性为 `None`，`reload()` 返回 `False`
- **空文件创建**：回退默认配置
- **深合并覆盖类型**：若用户配置中将字典值改为非字典（如 `"political_rules": "字符串"`），整节被直接覆盖，深层嵌套值丢失
- **路径中间非字典**：如 `"economic_rules.base_tax.nested"`，`base_tax` 为整数，返回 `None`
- **get 空字符串**：直接返回 default 值
- **并发安全**：Config 当前未实现线程安全，假定单线程调用

### 5.3 深拷贝保护

- `to_dict()` 返回 `copy.deepcopy(self._config)`，外部修改不影响内部
- `get()` 返回值类型视路径终点而定，可变类型（列表、字典）的修改不会影响内部（深拷贝贯穿整个加载流程）
- 直接访问 `_config` 属性不受保护（约定不直接操作）

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 配置文件不存在 | 使用默认配置，输出 `⚠️` 警告 |
| 2 | 路径为 `None` | 使用默认配置，`path` 属性为 `None` |
| 3 | JSON 解析错误 | 使用默认配置，输出 `⚠️` 警告 |
| 4 | 内容为非字典类型 | 使用默认配置，输出 `⚠️` 警告 |
| 5 | 点号路径 `"economic_rules.base_tax"` | 返回 100 |
| 6 | 点号路径不存在 | 返回 `None` |
| 7 | 点号路径中间非字典 | 返回 `None` |
| 8 | 空键 | 返回 `None`/默认值 |
| 9 | 深合并：覆盖部分配置 | 被覆盖的值变更，其他值保持默认 |
| 10 | 深合并：添加新键 | 新键在 `to_dict()` 中可见 |
| 11 | 深合并：覆盖字典为非字典类型 | 原嵌套值全部丢失 |
| 12 | `reload()` 成功 | 配置更新为新文件内容，返回 `True` |
| 13 | `reload()` 失败（文件已删除） | 配置不变，返回 `False` |
| 14 | 无路径实例 `reload()` | 返回 `False` |
| 15 | `to_dict()` 深拷贝隔离 | 修改返回的字典不影响内部配置 |
| 16 | 所有默认配置节存在 | `political_rules`, `mortality_rules`, `economic_rules`, `combat_rules` 均非空 |

## 7. 历史演化与证据

- 历史审计入口：HF-020
- 历史名称：游戏配置管理
- 首次实现版本：MVP 0.4
- 演化：最初从 `game_state.py` 的 `_load_config` 默认值中剥离独立。`Config` 类在 MVP 0.4 基线中作为可复用的独立模块设计，支持多实例隔离。后续 MVP 0.5 扩展了 `economic_rules` 和 `mortality_rules` 配置项，MVP 0.7 新增了 `combat_rules` 字段和海军相关经济配置。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.4-06-sys_Config配置管理系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent C | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
