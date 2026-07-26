# MVP0.4-03-sys — 核心数据系统

> **功能简述：** GameState 游戏状态管理、Figure（人物）实体、Faction（派系）实体、
> Province（行省）实体、Curia（广场人物池）、Player（玩家）实体、Contract（合同）实体、
> City（城市）实体，以及游戏状态序列化/反序列化、实体生命周期管理。
>
> **覆盖范围：** 本模块是所有高阶系统（经济、政治、合同、军事、海军、战争、天命、城市）的
> 底层数据基础设施，提供统一的容器、序列化、配置接入与实体操作接口。

---

## 1. 功能目的

### 1.1 什么是核心数据系统

核心数据系统是《Eagle of Rome》所有计算的底层数据容器。它由一个单入口 `GameState` 实例
持有所有实体集合（人物、派系、行省、合同、城市、玩家等），并提供统一的 CRUD、序列化、
日志、配置读取与阶段执行跟踪能力。

### 1.2 核心设计原则

1. **单容器模式：** `GameState` 是所有数据的唯一权威来源。`reset()` 完整重置所有集合。
2. **实体解耦：** 各实体（`Figure`、`Faction`、`Province` 等）作为独立数据类，通过
   `GameState` 注册表统一管理。
3. **序列化全覆盖：** `to_dict()` / `from_dict()` / `load_from_dict()` 覆盖所有实体的
   存档读写。
4. **配置注入：** 所有经济规则参数通过 `Config` 实例读取，支持运行时覆盖和测试用工厂方法
   `create_for_testing()`。
5. **日志追踪：** `log_event()` 统一记录所有关键操作，支持配置文件日志和内存日志。

### 1.3 实体关系图（逻辑）

```
GameState (全局容器)
├── _members: Dict[int, Figure]          — 所有人物（存活+死亡）
├── _factions: Dict[str, Faction]        — 所有派系
├── _provinces: Dict[int, Province]      — 所有行省
├── _contracts_dict: Dict[int, Contract] — 所有合同
├── _cities: Dict[int, City]             — 所有城市（MVP 0.7+）
├── _players: Dict[str, Player]          — 所有玩家
├── _curia: Curia                        — 广场等待人物池
├── _war_system: WarSystem               — 战争系统
├── _military_system: MilitarySystem     — 军事系统
├── _naval_system: NavalSystem           — 海军系统
│
├── _treasury: int                       — 国家国库
├── _national_public_land: int           — 国家公地（意大利行省同步）
├── _public_land_total: int              — 行省注册表公地之总和
├── _turn: GameTurn                      — 当前回合状态
├── _treasury_deficit_turns: int         — 国库赤字连续回合数
└── _pending_land_acts / _pending_land_sale_quota  — 待执行土地法案/配额
```

---

## 2. 玩家/系统行为

### 2.1 游戏阶段中的核心数据流转

| 阶段 | GameState 操作 | Figure 操作 | Faction 操作 | Province 操作 |
|------|---------------|------------|-------------|---------------|
| **初始化** | `reset()` → 创建所有实体集合、载入战争数据 | 工厂方法创建人物并 `add_member()` | `add_faction()` 注册派系 | `add_province()` 注册行省 |
| **广场阶段** | `add_forum_action()` 记录招募/竞标/凯旋投票 | 招募出价、合同竞标 | 派系招募、合同竞标 | — |
| **收入阶段** | `EconomicService.settle_revenue_phase()` 国库增减 | `add_wealth()` 私地收益累加 | `treasury` 增长（抽成+津贴） | — |
| **人口阶段** | `record_population_campaign/vote()` | 庆典花费、投票权计算 | — | — |
| **元老院阶段** | `add_senate_proposal()` / `record_senate_vote()` | 提案表决（影响力为权重） | `get_senate_influence()` 投票权重 | — |
| **决议阶段** | `clear_pending_land_acts()`、衰减结算 | `decay_temp_influence_tasks()`、`update_influence()` | `update_total_land()` | — |
| **人物死亡** | `mark_member_dead()` 回收土地/财富 | `is_dead = True`，土地/财富归零 | 移除成员ID；领袖重新选举 | — |
| **序列化/存档** | `to_dict()` / `load_from_dict()` 全状态读写 | `to_dict()` / `from_dict()` | `to_dict()` / `from_dict()` | `to_dict()` / `from_dict()` |

### 2.2 实体生命周期

| 实体 | 创建 | 存活期操作 | 移除/销毁 | 序列化 |
|------|------|-----------|-----------|--------|
| Figure | 工厂方法 `create_nobile/eques/plebeian` | 财富/土地/影响力变迁、官职记录、合同持有 | `mark_member_dead()` | `to_dict()` / `from_dict()` |
| Faction | `Faction(id, name)` + `add_faction()` | 成员增减、金库管理、领袖更新、土地同步 | 成员全部死亡后无活跃成员 | `to_dict()` / `from_dict()` |
| Province | `Province(province_id, name, total_land)` + `add_province()` | 总督任命、合同绑定/解绑、土地类型调整、征服 | — | `to_dict()` / `from_dict()` |
| Contract | `create_contract()` 或 `create_tax_farming/create_public_works` | 竞标、中标、执行收入/付款、工程质保递减 | `mark_complete()` / `terminate()` / `advance_warranty()` | `to_dict()` / `from_dict()` |
| City | `create_city()` | 基础设施设置 | — | `to_dict()` / `from_dict()` |
| Player | `Player(player_id, faction_id)` + `add_player()` | 回合切换、在线状态 | `remove_player()` | `to_dict()` / `from_dict()` |
| Curia | `Curia()` 无参构造 | `add_figure()` / `remove_figure()` | `clear()` | 无独立序列化（作为 GameState 内部状态管理） |
| War | `WarSystem.load_wars_from_json()` | 状态迁移（INACTIVE→THREAT→ACTIVE→TRUCE→RESOLVED/DEFEATED） | 状态迁移 | `to_dict()` / `from_dict()` |
| Legion / Fleet | `MilitarySystem` / `NavalSystem` 管理 | 征召/指派/召回/解散/摧毁 | `mark_destroyed()` | `to_dict()` / `from_dict()`（通过各自的系统） |
| SeaZone | 硬编码构造（预留） | 舰队驻扎、制海权变更 | — | `to_dict()` / `from_dict()` |

### 2.3 序列化/反序列化流程

**存档路径（to_dict → 输出）：**
```
GameState.to_dict()
  ├── 基础字段：treasury, national_public_land, turn, executed_phases, phase_results
  ├── entity 集合：members, factions, provinces, contracts_dict, cities
  ├── 子系统：naval_system
  ├── 天命系统：active_events, hero_spawned_this_turn, hero_to_spawn, spawned_hero_ids
  ├── 玩家系统：players, current_player_id, turn_order, population_pending
  └── 杂项：contract_id_counter, treasury_deficit_turns, pending_land_acts, pyrrhic_war_won, ...
```

**读档路径（load_from_dict → 输入）：**
```
GameState.load_from_dict(data)
  ├── reset() 清空所有状态
  ├── 恢复基础字段（treasury, national_public_land, turn 等）
  ├── 恢复 members（遍历 _members → Figure.from_dict()）
  ├── 恢复 factions（遍历 _factions → Faction.from_dict()）
  ├── 恢复 provinces（遍历 _provinces → Province.from_dict()）
  ├── 恢复 contracts_dict（遍历 _contracts_dict → Contract.from_dict()）
  ├── 恢复 cities（遍历 _cities → City.from_dict()）
  ├── 恢复 players（遍历 _players → Player.from_dict()）
  ├── 恢复 naval_system（_naval_system.load_from_dict()）
  ├── 调用 _update_global_public_land() 重算公地汇总一致性
  └── 恢复天命系统字段、turn_order、population_pending 等
```

---

## 3. 核心规则

### 3.1 影响力计算公式

详见 [之前的章节保留]
（从原 Spec 第 3.1 节完整保留，包含 base/family_bonus/office_bonus/temp_influence 公式、
各官职加成表、临时任务衰减逻辑、更新时机）

### 3.2 土地所有权规则

（保留原第 3.2 节全文：人物私地、国家公地、派系总土地、行省土地分割、sync_italy_public_land）

### 3.3 金钱流转规则

（保留原第 3.3 节全文：人物财富、派系金库、国家国库、收入来源与支出路径）

### 3.4 行省总督任期与交接生命周期

**总督任命流程：**
1. **任命候任总督：** `Province.set_governor_designate(new_governor_id, old_governor_id)`
   — 在元老院阶段设置候任总督及本轮将被替换的旧总督
2. **总督交接执行：** `Province.complete_governor_transition(turn, promote_designate=True)`
   — 在决议阶段执行：将 `governor_designate_id` 写入正式 `governor_id`，记录 `governor_since`，
     清理临时字段
3. **旧总督记录：** `old_governor_id` 用于记录本轮前总督，供系统查询变更历史
4. **官方交接清除：** `clear_governor_designate()` 可清除候任记录

**总督类型：**
- `governor_type`：字符串枚举，默认 `"proconsul"`（前执政官总督）、`"propraetor"`（前大法官总督）

### 3.5 合同生命周期

```
PENDING → BUDGETED (元老院预算拨款) → ACTIVE (竞标中标) → COMPLETED → EXPIRED (质保期满)
                                                        → EXPIRED (中止)
```

- **创建：** `GameState.create_contract()` 分配唯一 `contract_id`，状态为 `PENDING`
- **预算拨款：** `PoliticalSystem.execute_passed_proposal()` 将合同状态改为 `BUDGETED`
- **竞标：** `GameState.place_bid()` 记录出价；`resolve_auction()` 根据类型选择最高/最低价
- **中标：** `Contract.mark_winner(winner_id, turn, profit_base)` 设定授予信息，状态变为 `ACTIVE`
- **执行：** 包税合同 → `record_tax_collection(amount)`；公共工程 → `record_works_payment(amount)`
- **完结：** `mark_complete(turn)` → 进入 `COMPLETED`；工程合同通过 `advance_warranty()` 递减质保期
  至 0 后进入 `EXPIRED`；`terminate()` 直接进入 `EXPIRED`

**合同类型：**
- `TAX_FARMING`：行省包税权，最高价中标，利润率由加价比例决定
- `PUBLIC_WORKS`：公共工程建设，最低价中标，记录施工周期和质保期
- `FLEET_CONSTRUCTION`：舰队建造合同（MVP 0.7-4 扩展），中标后通知 `NavalSystem`

### 3.6 人物资格检查

`Figure.can_hold_office(office_type, current_turn, config)` 检查链：

1. 当前持有非「ex-」官职 → 失败
2. 目标官职等级等于 0（未知） → 失败
3. 目标官职等级低于当前官职等级 → 失败（不可就低于当前等级者）
4. 历史有过更高等级官职（监察官除外） → 失败
5. 年龄不足最低要求 → 失败
6. 已任相同官职 → 失败
7. 仍在冷却期内 → 失败
8. 前置官职缺失（执政官需曾任大法官等） → 失败
9. 保民官仅限骑士和平民 → 条件检查

**历史官职记录：** 通过 `add_office_history(office_type, start_turn, end_turn)` 追加
`OfficeTerm` 对象到 `office_history` 列表，当前任期记录 `is_active=True`。

---

## 4. 输入、输出与依赖

### 4.1 输入来源（上游依赖）

| 数据来源 | 具体数据 | 写入位置 |
|---------|---------|---------|
| 人物工厂方法 | 初始 wealth/popularity/class_tier/family_prestige | `Figure` 实例 |
| 入口初始化 | 国库、国家公地、行省、战争数据 | `GameState` |
| Config / `get_economic_rule()` | 经济规则参数 | 配置层 |
| 公职系统 (`political_system.py`) | 官职任命 → office influence bonus | `Figure.office` |
| 临时任务系统 | `_temp_influence_tasks` | `Figure` |
| 合同系统 | 包税/工程利润 → figure.wealth / faction / treasury | `EconomicService` |
| 战争系统 | 征服行省、赔款 → treasury / province | `GameState.conquer_provinces()` |
| 广场人物池 | 新人物进入 Curia → 可供招募 | `Curia.add_figure()` |
| 客户端/命令行 | 玩家操作指令 → 写入 `_forum_pending` / `_senate_pending` / `_population_pending` | `GameState` |

### 4.2 输出依赖（下游消费者）

| 消费方 | 使用内容 | 读取途径 |
|--------|---------|---------|
| PoliticalSystem | figure.influence, faction.get_senate_influence() | 投票权重 |
| Faction.leader | max(living, key=lambda m: m.influence) | 领袖更新 |
| EconomicService | figure.wealth, land_private, faction.treasury, state.treasury | 收入结算 |
| LandTradingService | figure.land_private, figure.wealth, figure.influence | 土地交易 |
| 死亡系统 | mark_member_dead() 财富/土地回收 | GameState |
| 元老院提案 | budget/land_act → treasury/national_public_land | GameState |
| MilitarySystem | figure.martial, figure.office (指挥官资格) | 指挥官指派 |
| NavalSystem | contract (舰队建造), figure | 舰队管理 |
| 天命系统 | figure / war / province 数据 | 事件触发判断 |
| City 系统 | province.city_ids, City | 城市化 |

### 4.3 配置依赖

（保留原第 4.3 节 YAML 配置清单，补充以下新增键）

```yaml
# 新增：军事维护费
legion_maintenance_base: 2
veteran_maintenance_bonus: 1

# 新增：舰队类型维护费
fleet_types:
  trireme:
    maintenance_cost: 5
    strength_base: 3

# 新增：政治规则冷却期
political_rules:
  leader_cooldown_years: 10
  office_cooldowns:
    consul: 10
    praetor: 5
    quaestor: 2
    censor: 8
    aedile: 4
  offices_per_election:
    consul: 2
    praetor: 2
    quaestor: 2
    censor: 1
    aedile: 2
  min_ages:
    consul: 40
    praetor: 35
    quaestor: 30
    censor: 42
    aedile: 36
  candidates_per_election:
    consul: 2
    praetor: 2
    quaestor: 2
    censor: 2
    tribune: 2
  voting:
    finalist_count: 2
    tiebreaker: highest_influence
```

---

## 5. 状态与边界

### 5.1 数据一致性保障

（保留原第 5.1 节的 4 条：派系总土地、国家公地与意大利同步、影响力派生关系、死亡回收）

**新增：**
5. **全局公地汇总一致性：** 每次新增行省（`add_province()`）或反序列化后，自动调用
   `_update_global_public_land()` 遍历所有行省的 `land_public` 并累加至 `_public_land_total`
6. **合同绑定排他性：** `bind_tax_contract()` / `bind_project_contract()` 在已有合同绑定时抛出
   `ValueError`；`unbind_*` 解除绑定
7. **总督指派排他性：** 一个行省在同一时间只有一位正式总督（`governor_id`）和一位候任总督
   （`governor_designate_id`），交接后自动清除

### 5.2 负数保护

（保留原第 5.2 节表格，并补充）

| 字段 | 保护机制 | 说明 |
|------|---------|------|
| `Figure.popularity` | `add_popularity()` `max(0, ...)` | 仅此方法修改时保护 |
| `Figure._land_private` | `can_sell_land()` 检查 | `sell_land()` 预检 |
| `Province._land_public / _land_private` | `update_land_type()` 内 `max(0, ...)` | 自动截断 |
| `Province._grievance` | `set_grievance()` 验证 | `0 ≤ grievance ≤ 3` 范围验证，否则 ValueError |
| `Figure.wealth` | 无自动保护 | 调用方需确保非负逻辑 |
| `Faction.treasury` | 无自动保护 | 调用方检查 |
| `GameState._treasury` | 无自动保护 | `_treasury_deficit_turns` 跟踪负值回合 |

### 5.3 边界条件

（保留原第 5.3 节全部 6 条边界条件）

**新增：**
7. **人物ID管理：** `allocate_id()` 在 `[1, MAX_MEMBER_ID]` 范围内分配；`MAX_MEMBER_ID = 300`；
   预分配ID可传入 `preferred_id`
8. **天命池：** `_mortality_pool` 初始化为 `list(range(1, 301))` + random.shuffle，
   抽取完重置
9. **合同ID计数器：** 从 1 递增，`_contract_id_counter` 在序列化/反序列化中保持一致
10. **城市ID计数器：** 同合同机制，`_city_id_counter` 在 `add_city()` 中确保 `city_id ≥ counter`
11. **派系领袖选举时机：** `update_faction_leader()` 在影响力变化后手动调用，不清除旧领袖标记
    前会重置所有成员标记

### 5.4 已知代码问题

> **注意：** 以下问题基于代码审计发现，记录在此供后续修复参考。

- **`Figure.add_member()` 方法错误：** figure.py 中存在 `def add_member(self, member: Figure)` 方法，
  该方法访问 `self._used_ids` 和 `self._members`，但 `Figure` 类中不存在这两个属性
  （它们是 `GameState` 的属性）。此方法在任何调用中都会触发 `AttributeError`。
  正确的 `add_member()` 存在于 `GameState` 类中。

- **`Figure` 缺少 `to_dict()` / `from_dict()` 方法：** `Figure` 是 `@dataclass` 但没有定义
  `to_dict()` 或 `from_dict()`。`GameState.to_dict()` 在序列化 `_members` 时调用
  `member.to_dict()`，`GameState.load_from_dict()` 调用 `Figure.from_dict()`，
  两者都会触发 `AttributeError`。**所有包含人物的存档操作均会崩溃。**

- **`GameTurn` 缺少 `to_dict()` / `load_from_dict()` 方法：** `GameTurn` 是 `@dataclass`
  但没有定义序列化方法。`GameState.to_dict()` 中 `self._turn.to_dict()` 和
  `load_from_dict()` 中 `self._turn.load_from_dict()` 均无法工作。当前 `reset()` 将
  `self._turn` 设为 `None`，因此 `to_dict()` 返回 `None`（回合数据丢失），
  `load_from_dict()` 因空值检查永远不会恢复回合数据。

- **`GameState.resolve_auction()` 引用 `self.turn.turn_number` 空值崩溃：**
  `resolve_auction()` 中调用 `contract.mark_winner(... , self.turn.turn_number, 0)`，
  但 `self._turn`（即 `self.turn`）在 `reset()` 后恒为 `None`，
  触发 `AttributeError: 'NoneType' object has no attribute 'turn_number'`。
  任何调用 `resolve_auction()` 的路径都会崩溃。

---

## 6. 验收标准

### AC-01：影响力计算正确性
（保留原 AC-01，测试路径不变）

### AC-02：临时影响力添加与衰减
（保留原 AC-02，测试路径不变）

### AC-03：人物私地买卖
（保留原 AC-03，测试路径不变）

### AC-04：派系总土地同步
（保留原 AC-04，测试路径不变）

### AC-05：国家公地收益计算
（保留原 AC-05，测试路径不变）

### AC-06：私地收益累加
（保留原 AC-06，测试路径不变）

### AC-07：国家运营费扣除
（保留原 AC-07，测试路径不变）

### AC-08：行省公/私地更新与边界
（保留原 AC-08，测试路径不变）

### AC-09：死亡资产回收
（保留原 AC-09，表述更新如下）
- **条件：** figure 有 wealth=50, land_private=10, 国库=100, 国家公地=1000
- **预期：** 国库变为 150, 国家公地变为 1010, figure.wealth=0, figure.land_private=0,
  figure.is_dead=True（`mark_member_dead()` 调用后）
- **测试文件：** `tests/test_core/test_game_state.py` / `tests/test_core/test_phase_revenue_ext.py`
  （间接覆盖）

### AC-10：派系元老院影响力汇总
（保留原 AC-10）

### AC-11：土地交易后影响力自动更新
（保留原 AC-11）

### AC-12：临时影响力任务边界——零持续时间
（保留原 AC-12）

### AC-13：公/私地初始化比例
（保留原 AC-13）

### AC-14：行省全局公地汇总一致性
- **条件：** GameState 依次添加 Province(province_id=1, land_public=500)、
  Province(province_id=2, land_public=300)
- **预期：** `_public_land_total == 800`（自动由 `_update_global_public_land()` 维护）
- **测试文件：** `tests/test_core/test_game_state.py::TestGameStateMVP05::test_add_province_updates_public_land`

### AC-15：合同生命周期全流程（⚠️ 受代码 Bug C-03 影响）
- **条件：** 创建包税合同 → 拨款(BUDGETED) → 出价 → 中标(ACTIVE) → 执行 → 完结(COMPLETED)
- **预期：** 每一步状态转换严格按规则执行；合同中标后 `awarded_to`、`awarded_faction` 正确设置；
  工程合同 `advance_warranty()` 在质保期满后将状态转为 `EXPIRED`
- **代码限制：** `resolve_auction()` 因 `self.turn.turn_number` 空值崩溃，竞标路径受阻；
  修复后方可完整验证
- **测试文件：** `tests/test_core/test_entities.py::TestContract`

### AC-16：总督任期交接
- **条件：** 设置 `set_governor_designate(new=101, old=99)` → `complete_governor_transition(turn=15)`
- **预期：** `governor_id == 101`，`governor_since == 15`，`governor_designate_id == None`，
  `old_governor_id == None`
- **测试文件：** 待补充

### AC-17：人物资格检查
- **条件：** Figure 年龄 35，历史官职 `[Praetor]`，现任 `ex-praetor`
- **预期：** `can_hold_office("consul", current_turn=10, config)` 返回 `(True, "Eligible")`；
  `can_hold_office("censor", ...)` 因无 Consul 前置经历返回 `(False, "Requires prior Consul service")`
- **测试文件：** 待补充

### AC-18：序列化/反序列化完整性（⚠️ 受代码 Bug C-01 和 C-02 影响）
- **条件：** 设置完整游戏状态（含人物、派系、行省、合同、城市、玩家）→ `to_dict()` →
  `load_from_dict(to_dict_output)` → 读取各实体
- **预期：** 所有实体的所有字段与序列化前完全一致；`_public_land_total` 在反序列化后正确重算
- **代码限制：** Figure 缺少 `to_dict()`/`from_dict()` 且 GameTurn 缺少序列化方法，
  包含人物或回合数据的存档操作均会崩溃；修复后方可验证
- **测试文件：** 建议在 `tests/test_core/test_game_state.py` 中补充

### AC-19：国库赤字追踪
- **条件：** `treasury = -50`，调用 `increment_treasury_deficit_turns()` 连续 3 次
- **预期：** `treasury_deficit_turns == 3`；`reset_treasury_deficit_turns()` 后归零
- **测试文件：** 待补充

### AC-20：Curia 人物池管理
- **条件：** Curia 添加 3 个人物 → `remove_figure(figure_id)` 移除一个 → `get_all_available()` 返回剩余 2 个
- **预期：** 被移除的人物 `is_available` 变为 False；被添加的人物 `faction_id` 变为 None
- **测试文件：** 待补充

---

## 7. 历史演化与证据

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| MVP 0.4.3 | 2025-03 | 初始财富/国库/公地定义、Figure/Faction/GameTurn 基础结构 |
| MVP 0.4.4 | 2025-04 | 土地交易服务（LandTradingService） |
| MVP 0.4.5 | 2025-05 | 删除 Figure.power，引入 `_influence` 派生属性 + 公式 + 临时任务 |
| MVP 0.4.7 | 2025-06 | 死亡回收（wealth→treasury，land→national_public_land） |
| MVP 0.5 | 2025-Q3 | `_land_private` 独立化、Province 行省土地（6:4 比例）、Contract 合同、
  Faction 总土地/骑士合同计数、序列化全覆盖 |
| MVP 0.7-2 | 2026-Q1 | 行省征服属性（`conquered`）、开发度、文化/宗教、民怨范围约束、
  War `unlocked_provinces`、基础设施/资源/总督特质/驻军 |
| MVP 0.7-4 | 2026-Q1 | 海军系统、舰队建造合同（`_is_fleet_construction`）、SeaZone 海区、
  战争扩展（`enemy_naval_current`、制海权） |
| MVP 0.7-5~8 | 2026-Q1 | 天命系统事件/英雄生成、`active_events`、`hero_spawned_this_turn` |
| MVP 0.7 | 2026-Q1 | 城市系统 `City` 实体、`GameState._cities` 注册表 |
| MVP 0.7.11-12 | 2026-Q1 | 玩家系统 `Player` 实体、回合顺序、广场/人口/元老院阶段临时存储 |
| **v1.0** | **2026-07-17** | **完整审计：** 所有实体交叉验证、序列化全路径覆盖、总督生命周期、
  合同全生命周期、验收标准扩展至 20 条、代码问题记录 |
| **v1.1** | **2026-07-17** | **二次审计修复：** 修正配置默认值与代码一致、新增 3 条代码 Bug 记录、
  更新测试路径前缀、标注受影响的 AC |

---

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.4-03-sys_核心数据系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| 0.4.3 | — | — | 初始财富/国库/公地定义 |
| 0.4.4 | — | — | LandTradingService |
| 0.4.5 | — | — | 删除 Figure.power，引入 _influence |
| 0.4.7 | — | — | 死亡回收 |
| 0.5 | — | — | _land_private 独立化, Province, Contract, 序列化 |
| 0.7 | — | — | 城市系统, 天命系统, 海军系统, 玩家系统 |
| **1.0** | **2026-07-17** | **AI Sub-Agent** | **完整文档重构与审计：** 范围扩展至全部核心实体、
  验收标准 13→20 条、总督生命周期、合同全生命周期、序列化全路径、代码问题记录、
  所有字段与代码交叉验证 |
| **1.1** | **2026-07-17** | **AI Sub-Agent** | **二次审计修复：** 修正 §4.3 配置默认值与代码不一致（8 处差异）；
  新增已知代码问题 3 条（Figure/GameTurn 序列化缺失、resolve_auction 空值崩溃）；
  更新所有测试路径前缀为 `tests/`；标注 AC-15/AC-18 受代码 Bug 影响 |
