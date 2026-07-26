# Feature → Code 一级映射索引

> 生成日期：2026-07-12
> 生成角色：Code Alignment Sub-Agent
> 范围：所有 35 个 COMPLETE / CONFIRMED COMPLETE 游戏功能 + 13 个 -sys 系统能力
> 代码库：`src/` (Eagle of Rome)

---

## 说明

- **Code Entry** = 该功能的主逻辑入口文件
- **Related Modules** = 被调用的其他相关文件
- **Status**:
  - `FOUND` — 主入口明确，核心逻辑集中
  - `MULTIPLE` — 逻辑分布在多个同等重要的文件中
  - `NOT FOUND` — 找不到任何相关代码

---

## 一、游戏功能（已完成）

### MVP 0.2

| Feature ID | Feature | Code Entry | Related Modules | Status | Notes |
|---|---|---|---|---|---|
| MVP0.2-01 | 选举系统 | src/core/systems/political_system.py | src/core/entities/figure.py, src/ui/commands/phase_population.py, src/core/deciders/vote_decider.py, src/core/deciders/impl/auto_vote_decider.py | MULTIPLE | PoliticalSystem 封装投票核心规则；phase_population.py 触发选举流程 |
| MVP0.2-02 | 术语隔离系统 | src/core/localization/term_mapping.py | src/core/localization/__init__.py, src/ui/commands/sys_config.py | FOUND | TermSet 预设体系 + TerminologyService |

### MVP 0.3

| Feature ID | Feature | Code Entry | Related Modules | Status | Notes |
|---|---|---|---|---|---|
| MVP0.3-01 | 7阶段回合制系统 | src/core/game_state.py | src/ui/commands/func_turn_control.py, src/ui/debug_cli.py | FOUND | GameState 管理阶段执行标记（_executed_phases、is_phase_executed）; turn_control 推进回合并执行各阶段 |
| MVP0.3-02 | 战争系统（战斗CRT + 战争走向） | src/core/systems/war_system.py | src/core/entities/war.py, src/ui/commands/phase_combat.py | FOUND | 战争牌堆管理、CRT 结算、战争推进 |
| MVP0.3-03 | 军团系统 | src/core/entities/legion.py | src/core/systems/military_system.py, src/ui/commands/phase_combat.py | MULTIPLE | Legion 实体定义 + MilitarySystem 征召/解散/恢复 |
| MVP0.3-04 | 场景加载器 | src/core/scenario_loader.py | src/ui/commands/func_load.py | FOUND | 配置化场景加载、行省数据初始化 |

### MVP 0.4

| Feature ID | Feature | Code Entry | Related Modules | Status | Notes |
|---|---|---|---|---|---|
| MVP0.4-01 | 土地交易系统 | src/core/service/land_trading_service.py | src/ui/commands/func_land.py | FOUND | 核心交易逻辑在 Service, CLI 包装在 func_land |
| MVP0.4-02 | 包税权合同系统 | src/core/entities/contract.py | src/ui/commands/func_contracts.py, src/api/contract_api.py | FOUND | Contract 实体定义+状态管理; contracts 命令展示和操作 |

### MVP 0.5

| Feature ID | Feature | Code Entry | Related Modules | Status | Notes |
|---|---|---|---|---|---|
| MVP0.5-01 | 国家公地系统 | src/core/game_state.py | src/ui/commands/func_status.py (StatusPublicLandCommand) | FOUND | GameState 管理 _national_public_land / _public_land_total |
| MVP0.5-02 | 行省系统 | src/core/entities/province.py | src/core/scenario_loader.py | FOUND | Province 实体, 含总督、土地划分、征服等全部字段 |
| MVP0.5-03 | 公共工程合同 | src/core/entities/contract.py | src/core/systems/political_system.py, src/ui/commands/phase_senate.py | MULTIPLE | Contract（PUBLIC_WORKS）+ Senate 预算审批 |
| MVP0.5-04 | 舰队建造合同 | src/core/systems/naval_system.py | src/core/entities/contract.py, src/core/entities/fleet.py | FOUND | NavalSystem.generate_construction_contracts + Fleet 实体 |
| MVP0.5-05 | 凯旋与临时影响力 | src/core/deciders/impl/auto_triumph_decider.py | src/ui/commands/phase_forum.py, src/ui/commands/phase_population.py | FOUND | 自动凯旋决策器 + 在 Forum/Population 阶段触发 |
| MVP0.5-06 | 派系资金抽成系统 | src/core/entities/entities.py | src/core/game_state.py, src/core/service/economic_service.py | MULTIPLE | Faction.treasury + 税收阶段按比例向派系抽成 |
| MVP0.5-07 | 人物类型系统（ClassTier） | src/core/entities/figure.py | — | FOUND | ClassTier 枚举 + Figure 类 |
| MVP0.5-08 | 影响力/权力等级系统 | src/core/entities/figure.py | — | FOUND | Figure.influence, update_influence, 等级计算 |
| MVP0.5-09 | 保民官否决权 | src/core/deciders/tribune_veto_decider.py | src/core/deciders/impl/auto_tribune_veto_decider.py, src/ui/commands/phase_senate.py | FOUND | TribuneVetoDecider 核心逻辑 + SenateCommand 集成 |
| MVP0.5-10 | 土地法案（分地/买地） | src/ui/commands/phase_senate.py | src/core/deciders/land_proposal_decider.py, src/core/deciders/impl/auto_land_proposal_decider.py | MULTIPLE | 在元老院阶段作为土地法案提案; 有手动/自动决策器 |
| MVP0.5-11 | 私人土地交易自动化 | src/core/deciders/impl/auto_land_trade_decider.py | src/core/service/land_trading_service.py | FOUND | 自动决策器调用 LandTradingService |

### MVP 0.7

| Feature ID | Feature | Code Entry | Related Modules | Status | Notes |
|---|---|---|---|---|---|
| MVP0.7-00 | 行省总督任命 | src/core/entities/province.py | src/ui/commands/phase_senate.py | MULTIPLE | Province 存储总督字段; Senate 阶段提出/审批总督任命 |
| MVP0.7-01 | 谈判与合约（宣战/停战/和约） | src/core/deciders/peace_treaty_decider.py | src/core/deciders/impl/auto_peace_treaty_decider.py, src/ui/commands/phase_combat.py, src/ui/commands/phase_resolution.py | MULTIPLE | 战斗阶段谈判停战; 决议阶段检查和约到期; PeaceTreatyDecider 核心逻辑 |
| MVP0.7-02 | 行省扩张 | src/core/entities/province.py | src/core/systems/war_system.py | FOUND | Province 新增 conquered / country_id 等扩展字段 |
| MVP0.7-03 | 国库运营费 | src/core/service/economic_service.py | — | FOUND | EconomicService.deduct_national_opex() |
| MVP0.7-04 | 海军与海战-P0（含技术解锁） | src/core/systems/naval_system.py | src/core/entities/fleet.py, src/ui/commands/phase_combat.py | MULTIPLE | 海军系统管理舰队建造/战斗; Fleet 实体 |
| MVP0.7-05 | 风调雨顺-P0（天命事件） | src/core/service/mortality_service.py | src/core/i18n.py | FOUND | MortalityService.apply_bountiful_harvest() |
| MVP0.7-06 | 国泰民安-P0（天命事件） | src/core/service/mortality_service.py | src/core/game_state.py | FOUND | 天命事件卡 "bountiful_harvest" 处理 |
| MVP0.7-07 | 天降猛男-P0（天命事件） | src/core/service/mortality_service.py | src/core/scenario_loader.py | FOUND | 英雄事件加载和处理 |
| MVP0.7-08 | 无妄天灾-P0（天命事件） | src/core/service/mortality_service.py | src/ui/commands/phase_mortality.py | FOUND | 灾害事件加载和处理 |
| MVP0.7-09 | 行省起义-P0 | src/core/systems/war_system.py | src/core/entities/province.py, src/core/entities/war.py | FOUND | WarSystem.create_rebellion_war() |
| MVP0.7-10 | 战争卡-大规模战争 | src/core/systems/war_system.py | src/core/entities/war.py, src/core/scenario_loader.py | FOUND | 战争牌堆加载、抽取、威胁推进 |
| MVP0.7-11 | 封装单人CLI指令（CLI-UI框架） | src/ui/commands/ | src/ui/debug_cli.py, src/ui/commands/sys_registry.py, src/ui/commands/sys_base.py | MULTIPLE | 全部 Command 子类 + 注册/执行框架 |
| MVP0.7-12 | 多玩家支持 | src/core/entities/player.py | src/api/player_api.py, src/ui/commands/func_player.py, src/core/game_state.py | MULTIPLE | Player 实体 + PlayerAPI + 多人轮流 |
| MVP0.7-20 | 多玩家信息隔离 | src/core/game_state.py | src/core/entities/player.py | FOUND | GameState 实例隔离 + Player 实体 |
| MVP0.7-27 | 人才市场（人物招募池） | src/core/entities/curia.py | src/ui/commands/phase_forum.py, src/ui/commands/func_forum.py | FOUND | Curia 实体管理待招募人物; Forum 阶段招募 |

---

## 二、系统能力（System Capability）

| Feature ID | Feature | Code Entry | Related Modules | Status | Notes |
|---|---|---|---|---|---|
| MVP0.4-03-sys | 核心数据系统（影响力/金钱/土地） | src/core/game_state.py | src/core/entities/figure.py, src/core/entities/entities.py, src/core/entities/province.py | MULTIPLE | 分散在各实体中; GameState 为核心容器 |
| MVP0.4-04-sys | Command命令体系架构 | src/ui/commands/ | src/ui/commands/sys_base.py, src/ui/commands/sys_registry.py | MULTIPLE | Command 抽象基类 + 注册中心; 所有命令文件 |
| MVP0.4-05-sys | GameState状态管理 | src/core/game_state.py | — | FOUND | 全局状态容器 |
| MVP0.4-06-sys | Config配置管理系统 | src/core/config.py | src/core/game_state.py | FOUND | Config 类，支持默认值回退、点号路径访问、运行时重载 |
| MVP0.5-12-sys | 决策器框架 | src/core/deciders/ | src/core/deciders/bid_decider.py, src/core/deciders/vote_decider.py 等 | MULTIPLE | 决策器基类 + 自动/手动实现 |
| MVP0.5-13-sys | 阶段前置检查机制 | src/core/game_state.py | src/ui/commands/phase_*.py | MULTIPLE | is_phase_executed() + 各阶段 execute() 守卫 |
| MVP0.5-14-sys | 结构化调试日志系统 | src/core/game_state.py | src/ui/debug_cli.py | FOUND | _setup_logging, log_event |
| MVP0.5-15-sys | 游戏输出与日志规范 | src/core/i18n.py | src/ui/utils.py | MULTIPLE | i18n 文本 + 输出辅助 |
| MVP0.5-16-sys | 调试命令框架 | src/ui/commands/func_debug.py | src/ui/commands/sys_registry.py | FOUND | DebugFleetCommand, DebugWarCommand 等 |
| MVP0.5-17-sys | 自动招募/庆典/淘汰决策器 | src/core/deciders/impl/ | src/core/deciders/recruitment_decider.py, retirement_decider.py, festival_decider.py | MULTIPLE | auto_*.py 自动决策器实现 |
| MVP0.5-18-sys | 状态查询命令扩展 | src/ui/commands/func_status.py | src/api/game_api.py, src/api/figure_api.py, src/api/faction_api.py, src/api/province_api.py | MULTIPLE | 状态查询命令调用多个 API |
| MVP0.5-19-sys | API层统一入口 | src/api/ | src/api/__init__.py | MULTIPLE | 全部 API 模块 |
| MVP0.7-28-sys | Curia广场等待区实体 | src/core/entities/curia.py | src/ui/commands/phase_forum.py, src/ui/commands/func_forum.py | FOUND | Curia dataclass (人员池) |

---

## 三、Superseded（已废弃）

| 原功能编码 | 原功能名称 | Code Entry | Notes |
|---|---|---|---|
| HF-021 | Debug CLI（旧） | src/ui/debug_cli.py | 已被 MVP0.7-11 的 Command 体系替代; 保留作为兼容入口 |

---

## 统计

| 类别 | 总数 | FOUND | MULTIPLE | NOT FOUND |
|---|---|---|---|---|
| 游戏功能 (COMPLETE) | 35 | 26 | 9 | 0 |
| 系统能力 (-sys) | 13 | 5 | 8 | 0 |
| **合计** | **48** | **31** | **17** | **0** |

> 所有 48 个 Feature 均至少找到一个代码入口文件。无 NOT FOUND。
