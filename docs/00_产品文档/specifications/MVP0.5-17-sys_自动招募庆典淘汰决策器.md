# MVP0.5-17-sys — 自动招募/庆典/淘汰决策器

> **功能简述：** 为自动模式提供 AI 决策逻辑，自动决定派系在广场阶段的招募出价、庆典花费和人物淘汰

## 1. 功能目的

自动决策器是游戏自动模式的核心引擎，为 AI 玩家提供智能决策能力。此机制确保：

1. **自动招募**：根据派系资金和广场可用人物，自动决定出价金额和招募对象
2. **自动庆典**：根据人物财富和候选人列表，自动决定为哪些候选人举办庆典及花费多少
3. **自动淘汰**：根据派系成员状态和条件，自动决定淘汰哪些不需要的人物
4. **游戏平衡**：通过概率和配置参数，确保 AI 玩家行为合理且具有多样性

## 2. 玩家/系统行为

### 2.1 自动招募决策器

**文件：** `src/core/deciders/impl/auto_recruitment_decider.py`

**触发时机：** 广场阶段市场环节（步骤2）

**决策逻辑：**

```python
def decide_bids(self, faction: Faction, available_figures: List[Figure],
                vacancies: int, state: GameState) -> Dict[int, int]:
    """
    返回该派系对人物的出价映射：{figure_id: bid_amount}
    """
    # 1. 检查资金和空缺
    if faction.treasury <= 0 or vacancies <= 0:
        return {}

    # 2. 筛选可招募人物（排除被本派系遗弃的人物）
    eligible = [fig for fig in available_figures
                if getattr(fig, 'abandoned_by', None) != faction.id]

    if not eligible:
        return {}

    # 3. 随机打乱候选人顺序
    random.shuffle(eligible)

    # 4. 选择前 N 个（N = 空缺数）
    selected = eligible[:vacancies]

    # 5. 随机出价（1 ~ faction.treasury）
    bids = {}
    for fig in selected:
        amount = random.randint(1, faction.treasury)
        bids[fig.id] = amount

    return bids
```

**关键规则：**

- **资金检查**：派系国库资金 ≤ 0 或空缺数 ≤ 0 时，不出价
- **候选人筛选**：排除 `abandoned_by == faction.id` 的人物（已被遗弃）
- **随机顺序**：使用 `random.shuffle()` 打乱候选人顺序，确保公平性
- **随机出价**：出价金额为 1 ~ 国库资金之间的随机整数

### 2.2 自动庆典决策器

**文件：** `src/core/deciders/impl/auto_festival_decider.py`

**触发时机：** 人口阶段庆典环节（步骤1）

**决策逻辑：**

```python
def decide_festivals(self, faction: Faction, candidates: List[Figure], state: GameState) -> Dict[int, int]:
    """
    返回该派系中人物举办庆典的花费映射：{figure_id: amount}
    """
    min_age = state.config.get("political_rules.min_festival_age", 30)
    decisions = {}

    for fig in candidates:
        # 1. 跳过已死亡人物
        if fig.is_dead:
            continue

        # 2. 跳过年龄不足的人物
        if fig.age < min_age:
            continue

        # 3. 跳过已有官职的人物（排除战场指挥官）
        if fig.office is not None and not fig.office.startswith("ex-"):
            continue

        # 4. 跳过财富不足的人物
        if fig.wealth <= 0:
            continue

        # 5. 随机决定是否举办庆典
        amount = random.randint(1, fig.wealth)
        decisions[fig.id] = amount

    return decisions
```

**关键规则：**

- **年龄限制**：最低年龄 `min_festival_age`（默认 30 岁）
- **官职限制**：跳过已有官职的人物（`office` 不以 "ex-" 开头）
- **财富限制**：人物财富 ≤ 0 时，不举办庆典
- **随机决策**：人物财富决定最大花费，随机决定是否举办

### 2.3 自动淘汰决策器

**文件：** `src/core/deciders/impl/auto_retirement_decider.py`

**触发时机：** 广场阶段裁员环节（步骤1）

**决策逻辑：**

```python
def decide_whom_to_retire(self, faction: Faction) -> Optional[int]:
    """
    决定抛弃哪个人物，返回人物ID；若无可抛弃人物，返回None。
    """
    # 1. 概率检查（默认 30% 概率淘汰）
    chance = self.state.config.get("political_rules.retirement_chance", 0.3)
    random_val = random.random()

    if random_val >= chance:
        return None  # 未命中概率，不淘汰

    # 2. 获取派系成员
    members = faction.get_members(self.state)

    # 3. 筛选可淘汰人物
    eligible = [
        m for m in members
        if not m.is_faction_leader           # 不是派系领袖
           and not (m.office and not m.office.startswith("ex-"))  # 不是现任官员
           and not m.has_active_contract     # 没有活跃合同
    ]

    if not eligible:
        return None  # 无可淘汰人物

    # 4. 随机选择一个
    chosen = random.choice(eligible)

    return chosen.id
```

**关键规则：**

- **概率控制**：默认 30% 概率淘汰（可配置 `retirement_chance`）
- **排除条件**：
  - 派系领袖（`is_faction_leader == True`）
  - 现任官员（`office` 不以 "ex-" 开头）
  - 有活跃合同（`has_active_contract == True`）
- **随机选择**：从可淘汰人物中随机选择一个

## 3. 核心规则

### 3.1 配置参数

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `political_rules.retirement_chance` | `float` | `0.3` | 淘汰概率（0-1） |
| `political_rules.min_festival_age` | `int` | `30` | 庆典最低年龄 |

### 3.2 决策器接口

所有决策器继承自抽象基类：

```python
# src/core/deciders/recruitment_decider.py
class RecruitmentDecider(ABC):
    @abstractmethod
    def decide_bids(self, faction: Faction, available_figures: List[Figure],
                    vacancies: int, state: GameState) -> Dict[int, int]:
        pass

# src/core/deciders/festival_decider.py
class FestivalDecider(ABC):
    @abstractmethod
    def decide_festivals(self, faction: Faction, candidates: List[Figure], state: GameState) -> Dict[int, int]:
        pass

# src/core/deciders/retirement_decider.py
class RetirementDecider(ABC):
    @abstractmethod
    def decide_whom_to_retire(self, faction: Faction) -> Optional[int]:
        pass
```

### 3.3 自动模式集成

**文件：** `src/ui/commands/phase_forum.py`

```python
# 初始化决策器
from src.core.deciders.impl.auto_recruitment_decider import AutoRecruitmentDecider
from src.core.deciders.impl.auto_festival_decider import AutoFestivalDecider
from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider

self.recruitment_decider = AutoRecruitmentDecider()
self.festival_decider = AutoFestivalDecider()
self.retirement_decider = AutoRetirementDecider()

# 调用决策器
bids = self.recruitment_decider.decide_bids(faction, available_figures, vacancies, state)
festivals = self.festival_decider.decide_festivals(faction, candidates, state)
retire_id = self.retirement_decider.decide_whom_to_retire(faction)
```

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 派系 | `Faction` | 当前派系对象 |
| 可用人物 | `List[Figure]` | 广场中的所有可用人物 |
| 空缺数 | `int` | 派系当前空缺数 |
| 候选人 | `List[Figure]` | 派系在当前回合所有官职中的候选人列表 |
| 派系成员 | `List[Figure]` | 派系所有成员列表 |
| 配置 | `Config` | 决策器参数（年龄、概率等） |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 招募出价 | `Dict[int, int]` | `{figure_id: bid_amount}` |
| 庆典花费 | `Dict[int, int]` | `{figure_id: amount}` |
| 淘汰人物ID | `Optional[int]` | `figure_id` 或 `None` |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `Faction.treasury` | 派系国库资金（招募出价上限） |
| `Figure.age` | 人物年龄（庆典年龄限制） |
| `Figure.office` | 人物官职（庆典/淘汰排除条件） |
| `Figure.wealth` | 人物财富（庆典花费上限） |
| `Figure.is_faction_leader` | 是否派系领袖（淘汰排除条件） |
| `Figure.has_active_contract` | 是否有活跃合同（淘汰排除条件） |
| `Config` | 决策器参数配置 |

## 5. 状态与边界

### 5.1 正常流程

**招募流程：**
1. 检查派系资金和空缺数
2. 筛选可招募人物
3. 随机打乱顺序
4. 选择前 N 个
5. 随机出价（1 ~ 国库资金）

**庆典流程：**
1. 遍历候选人列表
2. 跳过已死亡/年龄不足/已有官职/财富不足的人物
3. 随机决定是否举办庆典
4. 记录花费金额

**淘汰流程：**
1. 概率检查（30%）
2. 筛选可淘汰人物
3. 随机选择一个
4. 返回淘汰人物ID

### 5.2 边界情况

| 场景 | 处理 |
|------|------|
| 派系资金不足 | 不出价，返回空字典 |
| 无可招募人物 | 返回空字典 |
| 无候选人 | 返回空字典 |
| 无可淘汰人物 | 返回 `None` |
| 未命中淘汰概率 | 返回 `None` |

### 5.3 多派系

- 每个派系独立决策
- 派系间决策互不影响
- 每次决策结果随机（`random.randint`, `random.shuffle`, `random.choice`）

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 派系资金充足且有空缺 | 返回出价字典，金额为 1 ~ 国库资金随机数 |
| 2 | 派系资金不足或无空缺 | 返回空字典 |
| 3 | 候选人列表为空 | 返回空字典 |
| 4 | 人物财富充足且满足条件 | 随机决定是否举办庆典，花费为 1 ~ 财富随机数 |
| 5 | 人物财富不足或年龄不足 | 跳过该人物 |
| 6 | 淘汰概率未命中 | 返回 `None` |
| 7 | 可淘汰人物列表为空 | 返回 `None` |
| 8 | 随机顺序公平性 | 多次执行，候选人出现顺序随机分布 |

## 7. 历史演化与证据

- 首次实现版本：MVP 0.5
- 相关演化：与广场阶段（MVP0.5-06）、人口阶段（MVP0.5-08）联动
- 代码入口：`src/core/deciders/impl/auto_*.py`

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-17-sys_自动招募庆典淘汰决策器.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-13 | Document Officer (DA) | 初版创建 |
