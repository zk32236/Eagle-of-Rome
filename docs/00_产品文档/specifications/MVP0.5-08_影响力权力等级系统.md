# MVP0.5-08 — 影响力/权力等级系统

> **功能简述：** 人物影响力数值的计算公式、官职等级映射和影响力迭代机制

## 1. 功能目的

影响力（Influence）是游戏中对人物综合政治权力的量化度量。它由经济实力（私人土地、追随老兵）、人望（Popularity）、家族背景（家族声望 x10）、现任/前任官职加成、以及临时任务（如凯旋）共同决定。影响力是现代替投票权（Voting Power）的直接对应数值，是决定元老院表决、官职竞选、总督任命等政治博弈结果的核心指标。官职等级（Rank）提供人物的官职层级对照，用于竞选资格检查和权力递进规则。

## 2. 玩家/系统行为

### 2.1 系统行为（影响力计算）

系统在以下时机自动计算人物影响力：

1. **人物创建时**：通过 `__post_init__()` 自动调用 `update_influence()`，完成初始影响力计算
2. **每回合结算**：在决议阶段调用 `update_influence()`，更新影响力值
3. **属性变化时**：人物私有土地、老兵数量、人气、官职、临时影响力任务等发生变化后
4. **临时影响力衰减后**：决议阶段每回合处理临时影响力任务衰减

### 2.2 系统行为（影响力输出）

1. `Figure.update_influence()` 更新影响力并记录日志（DEBUG 级别）
   - 日志内容：人物名称、旧值→新值、各分项明细
   - 仅在 `_state` 非空且值变化时记录
2. `Figure.__repr__()` 显示影响力数值在人物摘要中
3. `figure_api.get_figure_info()` 返回影响力及其各分项

### 2.3 系统行为（官职等级）

1. `Figure.rank` 属性返回当前官职的等级数值（只读）
2. 等级用于 `can_hold_office()` 方法中的高官不降级规则：
   - 现任高阶官职不能竞选低阶官职
   - 曾担任高阶官职不能竞选低阶官职（监察官除外）
3. `get_seat_share()` 和 `get_voting_power()` 提供席位和投票权信息

### 2.4 系统行为（临时影响力任务）

1. `add_temp_influence_task(per_turn, duration)`：添加临时影响力任务，持续指定回合数
2. 每回合调用 `decay_temp_influence_tasks()`（通过 `_process_temp_influence_decay()`）：
   - 对所有任务的 `remaining` 减 1
   - 移除 `remaining <= 0` 的任务
3. `get_temp_influence()`：返回所有活跃任务提供的临时影响力总和
4. 临时影响力用于模拟凯旋、庆典等时效性政治事件

## 3. 核心规则

### 3.1 影响力计算公式

```
influence = base + family_bonus + office_bonus + temp_influence
```

| 组件 | 公式 | 说明 |
|------|------|------|
| **base** | `land_private × 10 + veterans × 10 + popularity` | 经济+人望基础 |
| **family_bonus** | `family_prestige × 10` | 家族声望加成（仅贵族） |
| **office_bonus** | `get_office_influence_bonus()` | 现任/前任官职加成 |
| **temp_influence** | `get_temp_influence()` | 临时影响力（任务总和） |

### 3.2 官职影响力加成

| 官职（现任） | 加成值 | 卸任（ex-）加成值 |
|-------------|--------|-----------------|
| dictator | 60 | ex-dictator: 30 |
| censor | 50 | ex-censor: 25 |
| consul | 40 | ex-consul: 20 |
| praetor | 30 | ex-praetor: 15 |
| tribune | 20 | ex-tribune: 10 |
| quaestor | 10 | ex-quaestor: 5 |
| proconsul | 0 | ex-proconsul: 20 |
| propraetor | 0 | ex-propraetor: 15 |

**实现逻辑**（`get_office_influence_bonus()`）：
- 若 `office` 以 `ex-` 开头 → 查 `EX_OFFICE_INFLUENCE_BONUS` 表
- 否则 → 查 `OFFICE_INFLUENCE_BONUS` 表
- 无官职（`office is None`）→ 返回 0

### 3.3 官职等级表

| 官职 | 等级值 | 说明 |
|------|--------|------|
| dictator | 6 | 独裁官（最高） |
| censor | 5 | 监察官 |
| consul | 4 | 执政官 |
| praetor | 3 | 大法官 |
| tribune | 2 | 保民官 |
| quaestor | 1 | 财务官（最低） |

`OFFICE_RANK.get(office, 0)`：未在表中的官职返回 0。

### 3.4 投票权与席位

| 属性 | 值 | 说明 |
|------|-----|------|
| `influence` | `self._influence` | 影响力 = 投票权 |
| `voting_power` | `self.influence` | 投票权直接对应影响力 |
| `seat_share` | `land_private + veterans` | 席位份额 = 私地 + 老兵 |

### 3.5 临时影响力任务机制

| 属性 | 类型 | 说明 |
|------|------|------|
| `_temp_influence_tasks` | `List[Dict]` | 活跃任务列表，每项含 `per_turn` 和 `remaining` |
| `per_turn` | `int` | 每回合增加的临时影响力值 |
| `remaining` | `int` | 剩余持续回合数 |

衰减规则：
- 每回合调用 `decay_temp_influence_tasks()`，所有任务 `remaining -= 1`
- `remaining > 0` 的任务保留，`<= 0` 的移除
- `update_influence()` 会包含临时影响力计算结果

### 3.6 可配置性

通过 `Figure.load_config(config)` 可覆盖主要数值：

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `political_rules.office_rank` | `OFFICE_RANK` | 覆盖官职称号表 |
| `political_rules.office_influence_bonus` | `OFFICE_INFLUENCE_BONUS` | 覆盖现任官职加成表 |
| `political_rules.ex_office_influence_bonus` | `EX_OFFICE_INFLUENCE_BONUS` | 覆盖卸任官职加成表 |
| `political_rules.family_prestige` | `FAMILY_PRESTIGE` | 覆盖家族声望表 |

### 3.7 影响力滞后更新

- 影响力在 `update_influence()` 调用后才更新 `self._influence` 内部变量
- `__post_init__` 中自动调用一次，保证创建后初始值正确
- 外部通过 `fig.influence` 属性（getter）读取 `self._influence`
- `influence` setter 直接设置值，不触发重新计算

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 私人土地 | `Figure._land_private` | 每单位贡献 10 基础影响力 |
| 老兵数量 | `Figure.veterans` | 每位老兵贡献 10 基础影响力 |
| 人气值 | `Figure.popularity` | 按值直接计入基础影响力 |
| 家族声望 | `Figure.family_prestige` | 声望 × 10 计入家族加成 |
| 当前官职 | `Figure.office` | 查 `OFFICE_INFLUENCE_BONUS` 或 `EX_OFFICE_INFLUENCE_BONUS` |
| 临时影响力任务 | `Figure._temp_influence_tasks` | 所有活跃任务的 `per_turn` 总和 |
| 配置覆盖 | `Figure.load_config(config)` | 从游戏 config 加载覆盖值 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| `Figure.influence` | 属性读取 | 当前影响力值 |
| `Figure.voting_power` | 属性读取 | 投票权（等同于 influence） |
| `Figure.rank` | 属性读取 | 官职等级值 |
| `Figure.get_seat_share()` | 方法返回值 | 席位份额（私地+老兵） |
| 日志事件 | debug 级别 | 影响力变化详情 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `Figure._land_private` | 私人土地值 |
| `Figure.veterans` | 老兵数量 |
| `Figure.popularity` | 人望值 |
| `Figure.family_prestige` | 家族声望 |
| `Figure.office` | 当前官职字符串 |
| `Figure.OFFICE_INFLUENCE_BONUS` | 类常量，现任官职加成表 |
| `Figure.EX_OFFICE_INFLUENCE_BONUS` | 类常量，卸任官职加成表 |
| `Figure.FAMILY_PRESTIGE` | 类常量，族名→声望映射 |
| `Figure.OFFICE_RANK` | 类常量，官职称号→等级映射 |
| `GameState.log_event()` | 日志记录（可选，通过 `_state` 连接） |

## 5. 状态与边界

### 5.1 正常状态

- 无官职时 `influence` 仅基于 `base + family_bonus + temp_influence`
- 有官职时额外叠加 `office_bonus`
- 卸任后（office 变为 `ex-xxx`）使用 `EX_OFFICE_INFLUENCE_BONUS` 表
- 影响力可为 0（基本不存在负值场景，所有分项非负）

### 5.2 边界情况

| 场景 | 结果 |
|------|------|
| 人物无土地、无老兵、无人气、无家族、无官职 | influence = 0 |
| 人物官职不在 `OFFICE_RANK` 中 | rank = 0 |
| 人物官职不在 `OFFICE_INFLUENCE_BONUS` 中 | office_bonus = 0（字典 `.get(office, 0)`） |
| `decay_temp_influence_tasks()` 时所有任务都已过期 | `_temp_influence_tasks` 清空 |
| 影响力大量增长（如执政官加成后） | 直接累加，无上下限限制 |
| 多个临时任务同时生效 | `get_temp_influence()` 使用 `sum()` 累计所有 `per_turn` |
| 卸任官职（ex-）不在 `EX_OFFICE_INFLUENCE_BONUS` 中 | 返回 0 |
| 通过 config 加载时配置缺失某一项 | 保留当前类常量值（使用 `.get(key, default)` 方式） |

### 5.3 影响力和投票权的关系

- `get_voting_power()` 始终返回 `self.influence`（即 `self._influence`）
- 当前设计中影响力直接等于投票权，无额外转换或调整
- 未来若有加权投票等规则，需在 `get_voting_power()` 或投票计算中增加调整逻辑

### 5.4 日志记录条件

`update_influence()` 仅在以下条件同时满足时才记录日志：
1. 人物已通过 `set_state(state)` 关联了 `GameState`（`self._state is not None`）
2. 新旧影响力值不同

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 私地=3、老兵=1、人气=5、无家族、无官职 | influence = 45 (30+10+5) |
| 2 | 私地=3、老兵=1、人气=5、家族声望=3（Julius）、无官职 | influence = 75 (45 + 30) |
| 3 | 上述状态 + 执政官（consul） | influence = 115 (75 + 40) |
| 4 | 上述状态 + 卸任执政官（ex-consul） | influence = 95 (75 + 20) |
| 5 | 添加临时影响力任务（per_turn=10, duration=3） | 任务期 influence+10，3回合后恢复 |
| 6 | 人物死亡后 | influence 数值保留，但不再参与投票 |
| 7 | `update_influence()` 前后值相同 | 不记录日志（无额外输出） |
| 8 | 通过 `load_config` 修改 `OFFICE_INFLUENCE_BONUS` | 影响力使用新配置值 |
| 9 | 无官职人物 | rank = 0 |
| 10 | 骑士创建（无家族声望） | family_bonus = 0 |

## 7. 历史演化与证据

- 历史审计入口：HF-017 / HF-040
- 历史名称：影响力/权力等级系统
- 首次实现版本：MVP 0.5 (2026-02-25)
- 演化：从 MVP 0.4 时代简化的影响力计算方法升级为结构化的多层级计算公式。临时影响力系统在 MVP 0.5-05（凯旋与临时影响力）中作为独立需求引入，通过 `_temp_influence_tasks` 机制实现。官职等级映射在选举系统和元老院系统中被广泛使用。`load_config` 机制为后续数值平衡（MVP 0.9-17）提供支持。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-08_影响力权力等级系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent B | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
