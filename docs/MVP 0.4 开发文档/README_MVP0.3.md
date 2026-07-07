# Eagle of Rome - MVP 0.3

## 版本信息
- **版本号**: MVP 0.3
- **代号**: Seven Phases & War System
- **发布日期**: 2024
- **开发状态**: 核心机制完成，可游玩测试

---

## 项目概述

《Eagle of Rome》是一款基于经典桌游《罗马共和》(The Republic of Rome) 的电子实现，采用Python开发，支持术语隔离架构和模块化扩展。

### 核心特性
- **7阶段回合制**: 完整还原桌游回合流程
- **战争系统**: 动态战争卡、军团管理、战斗推算
- **术语隔离**: 支持多种历史语境（拉丁/英文/中文）
- **模块化架构**: ECS-like设计，易于扩展

---

## 系统要求

### 运行环境
- **Python**: 3.8+
- **操作系统**: Windows / macOS / Linux
- **依赖**: 仅标准库（无第三方依赖）

### 安装运行
```bash
# 1. 解压项目
cd EagleOfRome_MVP0.3

# 2. 运行游戏
python main.py

# 3. 加载场景测试
> load
> help
```

---

## 版本功能清单

### ✅ 已完成 (MVP 0.3)

#### 1. 核心阶段系统 (7 Phases)
| 阶段 | 功能描述 | 状态 |
|------|---------|------|
| Mortality | 死亡判定、人口池抽取 | ✅ |
| Revenue | 税收、军团维护费 | ✅ |
| Forum | 战争激活、预警显示 | ✅ |
| Population | 国家状态、军团解散建议 | ✅ |
| Senate | 选举、投票、领袖更替 | ✅ |
| Combat | 战斗推算、CRT结果 | ✅ |
| Resolution | 年度总结、胜利检查 | ✅ |

#### 2. 战争系统 (War System)
- ✅ 战争卡JSON配置 (`data/cards/wars.json`)
- ✅ 5张测试战争卡（First Punic War, Pyrrhic Invasion等）
- ✅ 战争牌堆管理（抽取、激活、弃牌）
- ✅ 战争属性：强度、海军需求、奖励/惩罚
- ✅ 拖延惩罚：动乱增加、国库消耗
- ✅ 战争状态追踪：活跃/已解决/失败

#### 3. 军团系统 (Legion System)
- ✅ 10军团池（Legio I-X）
- ✅ 军团状态：未征召/活跃/老兵/解散
- ✅ 征召机制：10金币/军团
- ✅ 解散机制：批量解散、国库压力自动解散
- ✅ 维护费：2金币/军团/回合，老兵+1
- ✅ 老兵晋升：战斗胜利后晋升（战力+1）
- ✅ 军团指派：支持增援、多战争分配

#### 4. 战斗系统 (Combat System)
- ✅ 简化CRT（Combat Resolution Table）
- ✅ 战斗计算：2d6 + 战力 - 敌军强度
- ✅ 结果类型：灾难/失败/僵持/胜利/凯旋
- ✅ 海陆协同：海军需求检查、不足惩罚
- ✅ 伤亡处理：将领阵亡/逃跑/被俘
- ✅ 战后处理：军团召回、战争结算

#### 5. 术语隔离 (Terminology Isolation)
- ✅ 4套术语集：
  - `original`: 英文原版（Senate/Senators/Talents）
  - `historical_roman`: 拉丁术语（Senatus/Patres/Talenta）
  - `generic_latin`: 通用拉丁（Curia/Nobiles/Denarii）
  - `chinese_historical`: 中文历史（元老院/元佬/塔兰特）
- ✅ 运行时切换：`terms [preset]`

#### 6. 游戏机制
- ✅ 强制准备检查：无指挥官/军团时阻止Combat
- ✅ 状态追踪：指挥官伤亡状态（killed/fled/captured）
- ✅ 自动跳过：无战争时Combat自动完成
- ✅ 年度推进：完整7阶段后才能进入下一年

---

## 操作指南

### 基础命令
```
load              # 加载测试场景
status            # 显示游戏状态
help              # 显示帮助
exit              # 退出游戏
```

### 阶段命令
```
m, mortality      # 死亡阶段
r, revenue        # 收入阶段
f, forum          # 论坛阶段（战争激活）
p, population     # 人口阶段
s, senate         # 元老院阶段（选举）
c, combat         # 战斗阶段
x, resolution     # 决议阶段
```

### 军事命令
```
wars              # 显示战争状态
legions           # 显示军团状态
recruit           # 征召军团（支持批量）
assign            # 指派指挥官和军团（支持增援）
disband           # 解散军团（支持批量）
```

### 回合控制
```
turn              # 自动执行完整回合
step              # 逐步执行回合
next              # 进入下一年（检查阶段完成）
next force        # 强制进入下一年
```

### 术语切换
```
terms original           # 英文原版
terms historical_roman   # 拉丁术语
terms chinese_historical # 中文历史
```

---

## 游戏流程示例

```bash
# 启动游戏
> python main.py

# 加载场景
> load

# 执行阶段
> m        # Mortality
> r        # Revenue（扣除军团维护费）
> f        # Forum（可能激活战争）
> p        # Population（检查国家状态）
> s        # Senate（选举执政官）

# 如果有战争，必须准备
> recruit  # 征召军团
> assign   # 指派指挥官和军团

# 执行战斗
> c        # Combat（战斗推算）

# 结束回合
> x        # Resolution（年度总结）
> next     # 进入下一年
```

---

## 已知限制

### 当前版本 (MVP 0.3)
1. **AI系统**: 仅基础框架，派系投票为随机
2. **事件系统**: 仅框架，未实现完整事件卡
3. **图形界面**: 仅命令行界面（CLI）
4. **存档系统**: 未实现，仅内存状态
5. **多人游戏**: 仅单人热座模式

### 简化机制
- **CRT**: 使用简化版，非完整2d6查表
- **海军战斗**: 简化为数值检查，无独立海战
- **省份系统**: 未实现
- **法律系统**: 仅基础选举，无立法

---

## 文件结构

```
EagleOfRome_MVP0.3/
├── main.py                      # 程序入口
├── README.md                    # 本文件
│
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   ├── entities.py      # Senator, Faction, GameTurn
│   │   │   ├── war.py           # War, WarStatus, WarType
│   │   │   └── legion.py        # Legion, LegionStatus
│   │   ├── phases/
│   │   │   ├── __init__.py
│   │   │   ├── mortality_phase.py
│   │   │   ├── revenue_phase.py
│   │   │   ├── forum_phase.py
│   │   │   ├── population_phase.py
│   │   │   ├── senate_phase.py
│   │   │   ├── combat_phase.py
│   │   │   └── resolution_phase.py
│   │   ├── systems/
│   │   │   ├── __init__.py
│   │   │   ├── war_system.py    # 战争管理
│   │   │   └── military_system.py # 军团管理
│   │   ├── game_state.py        # 游戏状态
│   │   ├── scenario_loader.py   # 场景加载
│   │   └── localization.py      # 术语服务
│   └── ui/
│       ├── __init__.py
│       └── debug_cli.py         # 调试命令行
│
├── data/
│   ├── scenarios/
│   │   └── mvp_test.json        # 测试场景
│   ├── cards/
│   │   └── wars.json            # 战争卡配置
│   └── config.json              # 游戏配置
│
└── docs/                        # 文档目录（可选）
    ├── architecture.md
    └── changelog.md
```

---

## 开发团队

- **架构设计**: Claude (AI Assistant)
- **代码实现**: Kerl (Developer)
- **游戏设计**: Based on *The Republic of Rome* by Valley Games

---

## 许可证

本项目为学习研究用途，基于经典桌游机制实现。

---

## 更新日志

### MVP 0.3 (Current)
- 完成7阶段系统
- 实现战争系统（战争卡、激活、结算）
- 实现军团系统（征召、维护、战斗）
- 实现简化CRT战斗推算
- 实现术语隔离架构
- 实现强制军事准备检查

### MVP 0.2 (Previous)
- 基础3阶段（Mortality/Revenue/Senate）
- 术语隔离框架
- 基础选举系统

### MVP 0.1 (Initial)
- 项目框架搭建
- 实体定义（Senator, Faction）
- 基础游戏状态

---

## 联系方式

如有问题或建议，请通过项目仓库提交Issue。

---

**Enjoy the game! 🦅 SPQR**
