# 历史功能编码映射表

> **生成日期:** 2026-07-12
> **生成角色:** Document Officer
> **基线:** T03_Historical_Development_Audit_Report.md
> **状态:** FINAL

---

## 映射总表

| 审计ID | 正式功能编码 | 标准功能名称 | 历史别名 | 首次实现阶段 | 功能状态 | 编码处理 | 关键证据 |
|--------|------------|------------|---------|-------------|---------|---------|---------|
| HF-001 | **MVP0.3-01** | 7阶段回合制系统 | — | MVP 0.3 (2024) | CONFIRMED COMPLETE | NEWLY ASSIGNED | README_MVP0.3.md; MVP 0.5 增量开发报告(全系列) |
| HF-002 | **MVP0.4-04-sys** | Command命令体系架构 | Debug CLI合并 | MVP 0.4.5 | CONFIRMED COMPLETE | NEWLY ASSIGNED | 指令1-1完成总结.txt; 架构设计细化V1.2 |
| HF-003 | **MVP0.4-05-sys** | GameState状态管理 | — | MVP 0.4.5 | CONFIRMED COMPLETE | NEWLY ASSIGNED | 指令1-2完成报告.txt |
| HF-004 | **MVP0.4-06-sys** | Config配置管理系统 | — | MVP 0.4.5 | CONFIRMED COMPLETE | NEWLY ASSIGNED | 指令2完成报告.txt(20项测试) |
| HF-005 | **MVP0.2-02** | 术语隔离系统（Terminology） | 4套术语预设 | MVP 0.2 (Pre-2024) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-23(5/5); README_MVP0.3.md |
| HF-006 | **MVP0.3-04** | 场景加载器（Scenario Loader） | — | MVP 0.3 (2024) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-23; README_MVP0.3.md |
| HF-007 | **MVP0.3-02** | 战争系统（战斗CRT+战争走向） | 战争卡牌堆机制 | MVP 0.3 (2024) | CONFIRMED COMPLETE | NEWLY ASSIGNED | MANIFEST_MVP0.3.md; 增量开发报告02-28/03-01 |
| HF-008 | **MVP0.3-03** | 军团系统 | 25军团池 | MVP 0.3 (2024) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-28(恢复); 03-01(维护费) |
| HF-010 | **MVP0.4-03-sys** | 核心数据系统 | 影响力/金钱/土地 | MVP 0.4.5 | CONFIRMED COMPLETE | NEWLY ASSIGNED | 核心数据功能说明书.docx |
| HF-011 | **MVP0.5-01** | 国家公地系统 | — | MVP 0.5 (02-23) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-23 |
| HF-012 | **MVP0.5-02** | 行省系统 | — | MVP 0.5 (02-23) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-23 |
| HF-013 | **MVP0.4-01** | 土地交易系统 | `trade land`命令 | MVP 0.4 | CONFIRMED COMPLETE | NEWLY ASSIGNED | 指令16完成报告; mvp 0.4.3测试日志 |
| HF-014 | **MVP0.4-02** | 包税权合同系统 | — | MVP 0.4 | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-23/02-24; 功能说明书 |
| HF-015 | **MVP0.5-03** | 公共工程合同 | — | MVP 0.5 (02-24) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-24 |
| HF-016 | **MVP0.5-04** | 舰队建造合同 | — | MVP 0.5 (02-24) | CONFIRMED COMPLETE | NEWLY ASSIGNED | MOM 0326/0327; MVP 0.7 NavalSystem 完整实现 |
| HF-017 | **MVP0.2-01** | 选举系统 | Senate Election | MVP 0.2 (Pre-2024) | CONFIRMED COMPLETE | NEWLY ASSIGNED | Test Log mvp 0.2系列; 增量开发报告02-27 |
| HF-018 | **MVP0.7-01** | 谈判与合约（宣战/停战/和约） | 宣战提案/投票/执政官出征 | MVP 0.5 (02-27) | CONFIRMED COMPLETE | KEEP EXISTING | 增量开发报告02-27; ACT-01停战设计; DS027修复 |
| HF-019 | — | 独裁官机制 | — | — | PLANNED | NO FEATURE ID | 仅在待办清单出现 |
| HF-020 | — | 民变/民怨系统 | — | — | PLANNED | NO FEATURE ID | 设计讨论，无实施证据 |
| HF-021 | — | Debug CLI（旧） | 被HF-002替代 | MVP 0.3 (2024) | SUPERSEDED | NO FEATURE ID | MANIFEST_MVP0.3.md; MVP 0.4.5瘦身 |
| HF-022 | **MVP0.7-11** | 封装单人CLI指令 | CLI-UI框架 | MVP 0.7 | CONFIRMED COMPLETE | KEEP EXISTING | ACT-02全部阶段指令+阶段0-4完成报告 |
| HF-023 | **MVP0.7-12** + **MVP0.7-20** | 多玩家支持 + 多玩家信息隔离 | — | MVP 0.7 | CONFIRMED COMPLETE | KEEP EXISTING | DS033功能方案; MOM 0329 |
| HF-024 | **MVP0.5-19-sys** | API层统一入口 | — | MVP 0.7 | CONFIRMED COMPLETE | NEWLY ASSIGNED | ACT-06全部接口搬迁指令; 架构设计总览 |
| HF-025 | — | i18n 国际化支持 | — | — | PARTIALLY IMPLEMENTED | NO FEATURE ID | i18n.py有实现，硬编码未完成清除 |
| HF-026 | **MVP0.7-05~08** | 天命事件系统（4P0事件） | 死神来了/天降猛男 | MVP 0.5 (02-24) | CONFIRMED COMPLETE | KEEP EXISTING | 增量开发报告02-24; ACT-03 |
| HF-027 | **MVP0.5-05** | 凯旋与临时影响力 | TriumphDecider | MVP 0.5 (02-28) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-28/03-01 |
| HF-028 | **MVP0.7-04** | 海军与海战-P0 | 舰队系统 | MVP 0.7 | CONFIRMED COMPLETE | KEEP EXISTING | MVP 0.7-4战争模块说明书; ACT-04 |
| HF-029 | — | 技术债务管理（ACT-99） | — | MVP 0.7+ | CONFIRMED PARTIALLY | NO FEATURE ID | ACT-99目录(已解决部分P0) |
| HF-030 | **MVP0.5-12-sys** | 决策器框架 | VoteDecider/WarProposalDecider等 | MVP 0.5 (02-26~28) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-27/02-28 |
| HF-031 | **MVP0.5-07** | 人物类型系统（ClassTier） | class_tier字段+权限校验 | MVP 0.5 (02-25) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-25 |
| HF-032 | **MVP0.5-08** | 影响力/权力等级系统 | rank映射+公式 | MVP 0.5 (02-25) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-25(266 passed) |
| HF-033 | **MVP0.5-06** | 派系资金抽成系统 | faction_tax_rate: 0.1 | MVP 0.5 (02-25) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-25(§2.1) |
| HF-034 | **MVP0.5-16-sys** | 调试命令框架 | debug_war/debug_fleet | MVP 0.5 (03-02) | CONFIRMED COMPLETE | NEWLY ASSIGNED | func_debug.py |
| HF-035 | **MVP0.5-14-sys** | 结构化调试日志系统 | — | MVP 0.5 (03-02) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告03-02(四阶段) |
| HF-036 | **MVP0.5-15-sys** | 游戏输出与日志规范 | — | MVP 0.5 (03-02) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告03-02(格式/轮转) |
| HF-037 | **MVP0.5-13-sys** | 阶段前置检查机制 | is_current_player校验 | MVP 0.5 (02-23) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-23(§2.9) |
| HF-038 | **MVP0.7-02** | 行省扩张 | province.conquered + conquer_provinces | MVP 0.5 (03-02晚) | CONFIRMED COMPLETE | KEEP EXISTING | province.py; scenario_loader.py |
| HF-039 | **MVP0.5-18-sys** | 状态查询命令扩展 | spl/spr/sf/fs/prov | MVP 0.5 (02-23~27) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-23/02-26; func_status.py |
| HF-040 | **MVP0.5-09** | 保民官否决权 | Tribune Veto | MVP 0.5 (03-02) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告03-02(§2.5) |
| HF-041 | **MVP0.7-00** | 行省总督任命 | governor_id/designate/交接 | MVP 0.5 (03-02晚) | CONFIRMED COMPLETE | KEEP EXISTING | 增量开发报告03-02晚 |
| HF-042 | **MVP0.5-10** | 土地法案（分地/买地） | LandActDecider | MVP 0.5 (03-01) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告03-01(§2.4) |
| HF-044 | **MVP0.5-11** | 私人土地交易自动化 | LandTradeDecider | MVP 0.5 (03-01) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告03-01(§2.5) |
| HF-045 | **MVP0.5-17-sys** | 自动招募/庆典/淘汰决策器 | Recruitment/Festival/Retirement | MVP 0.5 (02-26~27) | CONFIRMED COMPLETE | NEWLY ASSIGNED | 增量开发报告02-26 |
| HF-046 | **MVP0.7-03** | 国库运营费 | National OPEX | MVP 0.7 | CONFIRMED COMPLETE | KEEP EXISTING | MVP 0.7-3设计说明书; 增量开发报告(392 passed) |
| HF-047 | **MVP0.7-09** | 行省起义-P0 | Province Rebellion | MVP 0.7 | CONFIRMED COMPLETE | KEEP EXISTING | 战争模块开发报告03-10 |
| HF-048 | — | 技术解锁机制 | 皮洛士战争→舰队 | MVP 0.7 | CONFIRMED COMPLETE | 合并至 MVP0.7-04 | 战争模块开发报告03-10子任务3 |
| HF-049 | **MVP0.7-27** | 人才市场（人物招募池） | Curia广场等待区实体 | MVP 0.7 | CONFIRMED COMPLETE | NEWLY ASSIGNED | 核心实体架构设计V2.0 §1.9 |

---

## 编码处理统计

| 编码处理 | 数量 | 说明 |
|---------|------|------|
| KEEP EXISTING | 9 | 已有正式编码冻结不动 |
| NEWLY ASSIGNED（游戏功能） | 19 | MVP0.2/0.3/0.4/0.5/0.7 新分配 |
| NEWLY ASSIGNED（系统功能 -sys） | 13 | 含 MVP0.4-03~06-sys + MVP0.5-12~19-sys + MVP0.7-28-sys |
| NO FEATURE ID | 7 | PLANNED无实施 / SUPERSEDED / PARTIALLY IMPLEMENTED |
| 合并至已有编码 | 1 | HF-048 → MVP0.7-04 合并 |
| **总计 HF-ID 扫描** | **49** | HF-001~049 |

---

## 编码分类汇总

| 分类 | 编码段 | 数量 | 说明 |
|------|--------|------|------|
| 游戏功能 — 已有冻结 | MVP0.7-xx | 15 | 产品能力 (含MVP0.9-01~23 PLANNED) |
| 游戏功能 — 新分配 | MVP0.2/0.3/0.4/0.5/0.7 | 20 | 含人才市场MVP0.7-27 |
| 系统功能 — 新分配 | MVP0.x-xx-sys | 13 | 含Curia技术实体MVP0.7-28-sys |
| 缺陷/修复 — 已有冻结 | MVP0.7-xx | 12 | 进TechDebt_Fix_Registry |
| 不分配编码 | — | 7 | PLANNED/SUPERSEDED等 |

> **注：** 本表为 HF-ID（审计临时编号）到正式产品编码（MVP0.x-xx / MVP0.x-xx-sys）的映射。所有已有正式编码（MVP0.7-xx 和 MVP0.9-xx）已冻结，状态为 FROZEN。
