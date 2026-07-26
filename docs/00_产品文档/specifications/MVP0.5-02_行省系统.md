# MVP0.5-02 — 行省系统

> **功能简述：** 行省实体数据结构（总督/基建/民怨/征服状态）、数据配置化和序列化

## 1. 功能目的

1. **行省实体建模** — 将罗马共和国的行省制度抽象为游戏中的 `Province` 实体，覆盖土地（公地/私地）、民怨、总督、基础设施等核心属性
2. **数据配置化** — 行省初始数据通过 JSON 配置文件加载（`data/cards/provinces.json`），支持场景定制和扩展
3. **序列化与持久化** — 行省对象支持完整的 `to_dict() / from_dict()` 序列化，可作为存档子系统的一部分持久化游戏状态
4. **功能基础底座** — 为后续功能（MVP0.7 总督任命、行省扩张、起义机制、包税合同、基建系统）提供统一的 Province 数据底座

## 2. 玩家/系统行为

### 2.1 行省状态的查询

**玩家行为：**
- 输入 `province`（或别名 `prov`）命令查看所有已征服行省的概要信息
- 输入 `province <行省ID>`（如 `province 1`）查看指定行省的详细信息

**系统行为：**
- 无参数时，调用 `province_api.get_province_info(state, None)`，返回所有 `conquered == True` 的行省概要列表
- 有参数时，先校验行省ID的整数性，然后查询具体行省详情：
  - 行省不存在 → 返回 `"❌ 行省ID {id} 不存在"`
  - 行省未征服 → 返回 `"❌ 行省ID {id} 尚未征服"`
  - 存在且已征服 → 返回完整详情页，包含：
    - **基本信息：** 名称、ID、总土地、公地、私地
    - **总督信息：** 总督类型（proconsul/propraetor）、现任总督姓名及上任时间、候任总督（若有）
    - **民怨等级：** 0（安居乐业）~3（平民起义）
    - **包税合同：** 合同ID、中标者、税率、剩余年限、年净收入
    - **公共工程合同：** 合同ID、承建者、预算、剩余年限、质保剩余
    - **控制派系：** 占领该行省的派系名

### 2.2 行省数据的加载

**场景加载时**（`ScenarioLoader.load_scenario`）：
1. 从 `data/cards/provinces.json` 读取行省配置数组
2. 对每个配置项创建 `Province` 实例
3. 通过 `state.add_province(province)` 注册到 GameState
4. 强制将意大利行省（ID=0）的 `conquered` 设为 `True`
5. 调用 `_assign_initial_governors()` 为已征服行省分配初始总督

### 2.3 行省的序列化

**存档时：** GameState 的 `to_dict()` 方法遍历 `_provinces` 字典，调用每个 Province 的 `to_dict()` 序列化为嵌套字典。

**读档时：** GameState 的 `load_from_dict()` 方法遍历存档数据中的 `_provinces` 键，调用 `Province.from_dict(prov_data)` 重建 Province 实例。

### 2.4 合同与行省的绑定

系统在竞标结算时自动维护行省与合同的双向绑定：
- 包税合同中标 → `province.bind_tax_contract(contract_id)`
- 公共工程合同中标 → `province.bind_project_contract(contract_id)`
- 旧合同到期/被替换 → `province.unbind_tax_contract()` / `province.unbind_project_contract()`

### 2.5 征服触发

战争胜利时（`WarSystem.resolve_war()`），检查 `war.unlocked_provinces` 列表：
- 对列表中每个行省，调用 `state.conquer_provinces(war_id)`
- 设置 `province._conquered = True`, `province.set_grievance(3)`
- 记录日志事件

## 3. 核心规则

### 3.1 行省属性表

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `province_id` | `int` | — | 行省唯一标识（0=意大利本土，1=西西里，2=撒丁-科西嘉，依次类推） |
| `name` | `str` | — | 行省名称 |
| `total_land` | `int` | — | 总土地（公地+私地） |
| `land_public` | `int` | `total_land * 0.6` | 公地数量，未指定时按 6:4 比例自动计算 |
| `land_private` | `int` | `total_land * 0.4` | 私地数量 |
| `tax_base` | `int` | `0` | 税基（收入计算的基础值） |
| `grievance` | `int` | `0` | 民怨等级，有效值 `[0, 3]`，通过 `set_grievance()` 设置，超出范围抛 `ValueError` |
| `tax_contract_id` | `Optional[int]` | `None` | 绑定的包税合同ID |
| `project_contract_id` | `Optional[int]` | `None` | 绑定的公共工程合同ID |
| `has_project` | `bool` | `False` | 是否有工程合同 |
| `turns_since_last_land_distribution` | `int` | `0` | 自上次分地以来的回合数（意大利本土用） |
| `governor_id` | `Optional[int]` | `None` | 现任总督的人物ID |
| `old_governor_id` | `Optional[int]` | `None` | 被替换的旧总督ID（本轮临时记录） |
| `governor_since` | `int` | `0` | 总督开始任职的回合号 |
| `governor_type` | `str` | `"proconsul"` | 行省总督类型：`"proconsul"`（前执政官行省）或 `"propraetor"`（前大法官行省） |
| `governor_designate_id` | `Optional[int]` | `None` | 候任总督ID（元老院提名通过后设置，决算阶段交接） |
| `conquered` | `bool` | `False` | 是否已征服（MVP 0.7-2 新增） |
| `country_id` | `int` | `0` | 归属国家（0=罗马） |
| `development_level` | `int` | `0` | 开发度（预留） |
| `infrastructure` | `Dict[str, int]` | `{"roads": 0, "aqueducts": 0, "ports": 0, "walls": 0}` | 四大基础设施等级字典 |
| `resources` | `List[str]` | `[]` | 资源列表 |
| `culture` | `str` | `"latin"` | 主流文化 |
| `religion` | `str` | `"roman_polytheism"` | 主流宗教 |
| `event_flags` | `Dict[str, Any]` | `{}` | 事件标记（如起义标记 `"rebellion_active": True`） |
| `governor_traits_effect` | `Dict[str, Any]` | `{}` | 总督特质影响（预留） |
| `loyalty` | `int` | `100` | 忠诚度（预留，值域待定） |
| `garrison` | `Dict[str, Any]` | `{}` | 驻军信息（预留） |
| `adjacent_provinces` | `List[int]` | `[]` | 相邻行省ID列表（城市系统扩展） |
| `city_ids` | `List[int]` | `[]` | 行省辖下城市ID列表（城市系统扩展） |

### 3.2 土地分配规则

创建 Province 时，若 `land_public` 和 `land_private` 未显式指定，按 **6:4** 比例自动拆分：
```python
self._land_public = int(total_land * 0.6)   # 公地
self._land_private = int(total_land * 0.4)  # 私地
```
调整土地分配通过 `update_land_type(public_change, private_change)` 方法，保证非负。

### 3.3 总督任期规则

| 方法 | 功能 |
|------|------|
| `set_governor(new_id, turn)` | 设置总督（将当前总督移入 `old_governor_id`） |
| `set_governor_designate(new, old)` | 设置候任总督和旧总督记录 |
| `clear_governor_designate()` | 清空候任记录 |
| `complete_governor_transition(turn, promote_designate=True)` | 完成交接：候任 → 现任，返回 `(old_gov_id, designate_id)` |

交接流程：
1. **元老院阶段：** 提案通过后调用 `set_governor_designate(candidate_id, old_gov_id)` → 记录候任总督
2. **决算阶段：** 调用 `complete_governor_transition(turn)` → `designate_id → governor_id`，临时记录清空

### 3.4 民怨规则

- 值域：`[0, 1, 2, 3]`，分别对应"安居乐业"、"怨声载道"、"民不聊生"、"平民起义"
- 通过 `set_grievance(value)` 设置，非 `[0,3]` 整数抛 `ValueError`
- 新征服行省初始民怨为 `3`
- 起义战争胜利后民怨归零
- 分地执行后意大利本土民怨归零

### 3.5 基础设施规则

基础设施以 `Dict[str, int]` 字典存储，支持四大类型：
```python
{"roads": 等级, "aqueducts": 等级, "ports": 等级, "walls": 等级}
```
当前版本仅支持基础设施等级的设置和读取（`set_infrastructure(key, value)`），业务逻辑（如影响收入/防御）尚未实现。

### 3.6 序列化规则

**`to_dict()`：** 返回完整字段字典（含 MVP 0.5 + MVP 0.7-2 扩展 + 城市系统扩展），以 `snake_case` 键名。

**`from_dict(data)`：** 静态工厂方法，从字典重建 Province 实例。使用 `data.get()` 和默认值兼容缺失字段（向前兼容旧存档）。

### 3.7 合同绑定约束

| 方法 | 约束 |
|------|------|
| `bind_tax_contract(contract_id)` | 已存在包税合同（`tax_contract_id 不为 None`）时抛 `ValueError` |
| `bind_project_contract(contract_id)` | 已存在工程合同时抛 `ValueError` |
| `unbind_tax_contract()` | 清空包税合同ID |
| `unbind_project_contract()` | 清空工程合同ID并设置 `has_project = False` |

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 行省初始配置 | `data/cards/provinces.json` | 场景加载时读取 |
| 行省ID | `province <ID>` 命令参数 | 玩家查询指定行省 |
| 战争解锁列表 | `War.unlocked_provinces` | 战争胜利后触发征服 |
| 合同绑定/解绑 | 竞标结算系统 | 包税合同/工程合同中标 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 行省概要列表 | 玩家 CLI 控制台 | `province` 命令输出 |
| 行省详情页 | 玩家 CLI 控制台 | `province <ID>` 命令输出 |
| 存档字典 | `GameState.to_dict()` | 序列化为 JSON 存档 |
| 总督交接 | `Province.complete_governor_transition()` | 决算阶段执行 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| **Contract**（contract.py） | 行省绑定包税/工程合同，附属合同ID |
| **Figure**（figure.py） | 总督ID指向Figure实体 |
| **Faction**（entities.py） | 派系控制行省（`faction.province_owned`） |
| **ScenarioLoader**（scenario_loader.py） | 场景加载时读取 provinces.json 初始化行省 |
| **WarSystem**（war_system.py） | 战争胜利后通过 `conquer_provinces()` 触发行省征服 |
| **EconomicSystem**（economic_service.py） | 税收收入阶段使用行省公地计算税收 |
| **PoliticalSystem**（political_system.py） | 总督提名资格校验和提案执行 |
| **War**（war.py） | `unlocked_provinces` 指定征服目标行省 |

## 5. 状态与边界

### 5.1 行省数据的生命周期

```
场景加载
  ├─→ provinces.json → Province 实例
  ├─→ state.add_province() → GameState._provinces 字典
  │
  ├─→ 游戏进行中
  │     ├─→ 总督任命/交接（governor_id / designate_id 变化）
  │     ├─→ 合同绑定/解绑（tax_contract_id / project_contract_id 变化）
  │     ├─→ 民怨升降（grievance 变化）
  │     ├─→ 土地分配（land_public / land_private 变化）
  │     ├─→ 征服触发（conquered = True）
  │     └─→ 事件标记（event_flags 变化）
  │
  ├─→ 存档
  │     └─→ to_dict() → JSON
  │
  └─→ 读档
        └─→ from_dict() → Province 实例
```

### 5.2 边界与异常

| 场景 | 行为 |
|------|------|
| 查询不存在的行省ID | 返回 `"❌ 行省ID {id} 不存在"` |
| 查询未征服的行省 | 返回 `"❌ 行省ID {id} 尚未征服"` |
| 民怨设为 0~3 之外的值 | `ValueError: Grievance must be between 0 and 3` |
| 重复绑定合同 | `ValueError: Province {id} already has a tax/project contract` |
| 意大利（ID=0）的初始化 | 场景加载器强制设置 `conquered = True` |
| 无总督行省 | `governor_id = None`，显示"❌ 无总督" |
| 无合同行省 | 显示"❌ 无包税/工程合同" |
| 总督交接时的 `promote_designate=False` | 可选参数，清空候任但不晋升 |

### 5.3 MVP 0.5 核心状态

| 状态 | 初始值 | 变化时机 |
|------|--------|---------|
| `governor_id` | JSON 配置或 None | 总督任命/交接 |
| `grievance` | JSON 配置值 | 征服（=3）、起义胜利（=0）、分地（=0） |
| `land_public` | JSON 配置或 6:4 比例 | `update_land_type()` |
| `conquered` | JSON 配置值 | 战争胜利（=True，不可逆） |

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|---------|
| 1 | 从 provinces.json 加载8个行省 | 所有行省正确创建并注册到 GameState |
| 2 | 意大利行省（ID=0）强制征服 | 场景加载后 `conquered == True` |
| 3 | `province` 命令（无参数）查询 | 返回所有已征服行省的概要列表 |
| 4 | `province 1` 查询西西里详情 | 返回完整的行省详情页，含总督、民怨、合同、派系信息 |
| 5 | `province 999` 查询不存在行省 | 返回 `"❌ 行省ID 999 不存在"` |
| 6 | `province 2` 查询未征服行省 | 返回 `"❌ 行省ID 2 尚未征服"` |
| 7 | Province to_dict → from_dict 往返 | 序列化后再反序列化，所有字段值保持一致 |
| 8 | set_grievance(4) | 抛出 `ValueError` |
| 9 | 重复绑定包税合同 | 第二次绑定抛出 `ValueError` |
| 10 | 总督交接完整流程 | `set_governor_designate` → `complete_governor_transition` → `governor_id` 正确更新 |
| 11 | 战争胜利后 `conquer_provinces` | 对应行省 `conquered=True`, `grievance=3` |
| 12 | 意大利行省土地同步 | `add_national_public_land()` 后意大利 `land_public` 同步更新 |
| 13 | Province 内部属性只读 | 通过 property 访问器读取，无 setter 的属性不可修改 |
| 14 | 未指定 `land_public/private` 时自动按 6:4 拆分 | `land_public = int(total_land * 0.6)`, `land_private = int(total_land * 0.4)` |
| 15 | 基础设施默认值 | 未指定 `infrastructure` 时初始化为 `{"roads":0, "aqueducts":0, "ports":0, "walls":0}` |

## 7. 历史演化与证据

- **历史审计入口：** `src/core/entities/province.py`（392行）、`src/api/province_api.py`（185行）
- **历史名称：** 无前身实体，直接以 `Province` 类命名
- **首次实现版本：** MVP 0.5（基础结构）、MVP 0.7-2（扩展字段：征服状态/开发度/基础设施/文化宗教/事件标记/总督特质/忠诚度/驻军）

### 代码注释标记

在 `province.py` 中，代码通过分段注释清晰标识了版本增量：
```python
# ---------- MVP 0.5 原有字段 ----------
# ---------- MVP 0.7-2 新增字段 ----------
# ---------- 城市系统扩展 ----------
```

### 关键代码提交

| 版本 | 核心增量 |
|------|---------|
| MVP 0.5 | Province 实体创建：ID/名称/土地/民怨/合同绑定/总督任期 |
| MVP 0.7-2 | 新增征服、开发度、基础设施、文化、宗教、事件、忠诚度、驻军字段 |
| 城市系统扩展 | `adjacent_provinces`、`city_ids`、`add_city_id()`/`remove_city_id()` |

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-02_行省系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-17 | Document Officer Sub-Agent | 从骨架填充为完整文档，基于 province.py (392行) 和 province_api.py (185行) 的实际代码 |
