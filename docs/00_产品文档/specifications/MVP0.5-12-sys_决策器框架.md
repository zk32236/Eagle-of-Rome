# MVP0.5-12-sys — 决策器框架

> **功能简述：** 决策器基类体系 + 自动/手动/骨架决策器结构

## 1. 功能目的

决策器框架（Decider Framework）是 Eagle of Rome 中**人工智能代理（AI 玩家）** 与**手动玩家**的统一决策入口。所有需要"智能决策"的行为——投票、竞标、招募、宣战、停战等——均通过决策器接口抽象，使：

1. 游戏核心逻辑与"谁做决策"解耦
2. AI 玩家的决策逻辑可以独立扩展/替换
3. 手动玩家可通过注入 `Manual` 决策器在未来获得交互式决策能力
4. 自动化测试可通过 Mock 决策器控制行为

## 2. 架构体系

### 2.1 三层架构

```
抽象基类 (deciders/*.py)
    │  ABC: 定义决策接口和参数/返回值类型
    │
    ├── 自动实现 (deciders/impl/auto_*.py)
    │       默认/标准实现：按配置概率 + 随机逻辑
    │
    └── 手动骨架 (deciders/manual_*.py)
            交互式实现骨架（当前为占位，返回 None）
```

### 2.2 依赖注入模式

所有使用决策器的命令类均通过**构造注入**接收决策器实例，并设置默认值：

```python
class SenateCommand(Command):
    def __init__(self, state,
                 vote_decider=None,          # 默认: AutoSenateVoteDecider()
                 land_proposal_deciders=None, # 默认: [AutoLandProposalDecider(...)]
                 takeover_decider=None,       # 默认: AutoWarTakeoverDecider()
                 veto_decider=None):          # 默认: AutoTribuneVetoDecider()
```

相同模式应用于：
- `CombatCommand`（`src/ui/commands/phase_combat.py`）— `PeaceTreatyDecider` 注入
- `ForumCommand`（`src/ui/commands/phase_forum.py`）— `RetirementDecider`、`RecruitmentDecider`、`BidDecider`、`LandTradeDecider`、`TriumphDecider` 注入
- `PopulationCommand`（`src/ui/commands/phase_population.py`）— 通过 `auto_processor` 使用 `FestivalDecider`、`VoteDecider`

## 3. 决策器清单

### 3.1 选举投票决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `vote_decider.py` | 25 | `VoteDecider.decide_vote(office, candidates, faction, state) → Optional[int]` |
| `impl/auto_vote_decider.py` | 50 | 优先选择本派系候选人中影响力(influence)最高者，无本派系候选人则随机选择 |
| — | — | 无 Manual 实现 |

**用途：** 人口阶段（Population Phase）各公职选举投票。

### 3.2 合同竞标决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `bid_decider.py` | 39 | `BidDecider` — 三种出价方法（tax/works/fleet） |
| `impl/auto_bid_decider.py` | 135 | 自动竞标：根据财富、利润率计算出价 |
| `manual_bid_decider.py` | 33 | 手动骨架（返回 None） |

**用途：** 广场阶段（Forum Phase）包税/工程/舰队合同竞标。

### 3.3 土地法案决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `land_proposal_decider.py` | 15 | `LandProposalDecider.decide_proposal(faction_id, state)` → `Optional[Tuple[str, float]]` |
| `impl/auto_land_proposal_decider.py` | 55 | 按概率和比例范围自动提案 |

**用途：** 元老院阶段土地法案提案。

### 3.4 土地交易决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `land_trade_decider.py` | 13 | `LandTradeDecider.decide_trade(state)` → `Optional[Tuple[int, int, int]]` |
| `impl/auto_land_trade_decider.py` | 64 | 自动交易：随机选择贵族→骑士交易 |
| `manual_land_trade_decider.py` | 8 | 手动骨架（返回 None） |

**用途：** 私人土地交易自动化。

### 3.5 停战草案决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `peace_treaty_decider.py` | 33 | `PeaceTreatyDecider.decide_treaty(war, result, state)` → `Optional[Dict]` |
| `impl/auto_peace_treaty_decider.py` | 42 | 按战斗结果和赔款公式生成草案 |

**用途：** 战斗阶段停战草案生成。

### 3.6 预算决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `budget_decider.py` | 17 | `BudgetDecider` — 决定提交哪些合同以及表决结果 |
| `impl/auto_budget_decider.py` | 82 | 自动预算决策器 |

**用途：** 元老院阶段预算合同表决。

### 3.7 庆典决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `festival_decider.py` | 21 | `FestivalDecider.decide_festivals(faction, candidates, state)` → `Dict[int, int]` |
| `impl/auto_festival_decider.py` | 47 | 自动庆典决策器 |

**用途：** 广场阶段庆典举办决策。

### 3.8 招募决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `recruitment_decider.py` | 23 | `RecruitmentDecider.decide_bids(faction, available, vacancies, state)` → `Dict[int, int]` |
| `impl/auto_recruitment_decider.py` | 63 | 自动招募决策器 |
| `manual_recruitment_decider.py` | 16 | 手动骨架（返回空字典） |

**用途：** 广场阶段人物招募出价。

### 3.9 淘汰决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `retirement_decider.py` | 13 | `RetirementDecider.decide_whom_to_retire(faction)` → `Optional[int]` |
| `impl/auto_retirement_decider.py` | 63 | 自动淘汰决策器 |
| `manual_retirement_decider.py` | 9 | 手动骨架（返回 None） |

**用途：** 派系人物淘汰决策。

### 3.10 凯旋决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `triumph_decider.py` | 15 | `TriumphDecider.decide_triumph(war, commander, state)` → `bool` |
| `impl/auto_triumph_decider.py` | 29 | 自动凯旋审批 |
| `manual_triumph_decider.py` | 9 | 手动骨架（返回 False） |

**用途：** 人口阶段凯旋审批。

### 3.11 保民官否决决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `tribune_veto_decider.py` | 17 | `TribuneVoteDecider.decide_veto(issue, tribune_id, state)` → `bool` |
| `impl/auto_tribune_veto_decider.py` | 29 | 自动否决决策器 |

**用途：** 元老院阶段保民官否决。

### 3.12 元老院投票决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `senate_vote_decider.py` | 17 | `SenateVoteDecider.decide_vote(issue, faction, state)` → `bool` |
| `impl/auto_senate_vote_decider.py` | 78 | 通用自动投票：支持宣战/和约/预算/土地法案/总督任命 |

**用途：** 元老院阶段各类提案的派系投票。

### 3.13 宣战决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `war_decider.py` | 25 | `WarProposalDecider.decide_proposal(war, state)` + `WarVoteDecider.decide_vote(war, faction, state)` |
| `impl/auto_war_decider.py` | 60 | 自动宣战决策器 |

**用途：** 元老院阶段战争威胁提案。

### 3.14 战争接管决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `war_takeover_decider.py` | 15 | `WarTakeoverDecider.decide_takeover(war, new_consul, old_commander, state)` → `bool` |
| `impl/auto_war_takeover_decider.py` | 47 | 自动接管决策器 |

**用途：** 新执政官接管前任遗留战争的决策。

### 3.15 舰队解散决策器

| 文件 | 行数 | 接口 |
|------|------|------|
| `fleet_disband_decider.py` | 15 | `FleetDisbandDecider.should_disband_fleet(fleet, state)` → `bool` |
| `impl/auto_fleet_disband_decider.py` | 48 | 仅当无海战需求时解散 |

**用途：** 舰队维护/解散决策。

## 4. 代码行数统计

| 类别 | 文件数 | 总行数 |
|------|--------|--------|
| 抽象基类 | 15 | 309 |
| 自动实现 (impl/auto_*) | 15 | 892 |
| 手动骨架 (manual_*) | 5 | 75 |
| **合计** | **35** | **1263** |

## 5. 输入、输出与依赖

### 5.1 通用设计模式

**输入：** 领域对象（Faction, Figure, War, Contract 等）+ GameState（配置/数据）
**输出：** 决策结果（bool, int, Dict, Tuple 等），或 None 表示不采取动作
**无副作用：** 决策器不应修改游戏状态，仅返回决策结果

### 5.2 依赖关系

| 依赖 | 说明 |
|------|------|
| `GameState` | 所有决策器依赖游戏状态读取配置和数据 |
| `Faction` | 派系实体（投票/财务/成员） |
| `Figure` | 人物实体（属性/官职/财富） |
| `War` | 战争实体（强度/持续回合/状态） |
| `Contract` | 合同实体（类型/价格/利润） |
| `Config` | 配置系统（概率/阈值/乘数） |

## 6. 自动模式与手动模式切换

通过 `testing.auto_forum`、`testing.budget_always_pass`、`testing.war_always_pass` 等配置项控制：

```python
# 示例：控制元老院自动投票
always_pass = state.config.get("testing.budget_always_pass", False)
```

- 开启 `testing.auto_forum`：广场阶段所有派系决策使用 `Auto*` 实现
- 开启 `testing.budget_always_pass` / `testing.war_always_pass`：元老院合同/战争投票默认通过
- 未来可通过注入 `Manual*` 决策器完全接管所有决策

未来可通过注入 `Manual*` 决策器完全接管所有决策。

## 7. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | `AutoPeaceTreatyDecider` 在 VICTORY 时返回正赔款 | 赔款公式正确 |
| 2 | `AutoLandProposalDecider` 按配置概率触发 | 概率和比例范围从配置读取 |
| 3 | `AutoSenateVoteDecider` 提案发起派系自动支持 | 返回 True |
| 4 | `AutoBidDecider` 根据财富和利润率出价 | 出价不超过财富 |
| 5 | `AutoRetirementDecider` 选择最弱人物淘汰 | 返回非领袖/非执政官人物 |
| 6 | `AutoFleetDisbandDecider` 无海战需求时解散 | 所有非建造中舰队被解散 |

完整测试见 `src/tests/test_deciders/` 目录。

## 8. 历史演化

- 首次实现版本：MVP 0.5
- 扩展：MVP 0.7 新增 `PeaceTreatyDecider`、`WarTakeoverDecider`、`FleetDisbandDecider` 等
- `Manual*` 骨架在 MVP 0.7 中创建，为手动交互预留接口
- `AutoSenateVoteDecider` 在 MVP 0.7 元老院重建中扩展支持多种提案类型

## 9. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-12-sys_决策器框架.md)

## 10. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-13 | Document Officer (DA) | 初版创建 |
| v1.1 | 2026-07-13 | Audit Subagent (DS) | 审计修正：更新 AutoVoteDecider 算法描述（从 class_tier/martial/popularity 改为 influence）；修正行数统计（基类 296/自动 892/手动 75，合计 35 文件 1263 行）；修正注入点路径（src/ui/commands/）和决策器清单；修正 testing.auto_senate 为 auto_forum/budget_always_pass/war_always_pass；修正注入分布表 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
