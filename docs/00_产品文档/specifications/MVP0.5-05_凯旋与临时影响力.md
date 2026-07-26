# MVP0.5-05 — 凯旋与临时影响力

> **功能简述：** 对结束战争的有功指挥官投票授予凯旋式，批准后授予临时影响力加成

## 1. 功能目的

凯旋式（Triumph）是罗马共和国对结束战争的有功指挥官的最高荣誉。该机制允许各派系在广场阶段对符合条件的凯旋进行投票表决，批准后指挥官获得持续的临时影响力加成（而非一次性奖励），体现凯旋带来的长期政治声望提升。

## 2. 玩家/系统行为

### 2.1 凯旋条件判定

1. 一场战争必须满足以下条件才可进入凯旋投票：
   - 战争状态为 **RESOLVED**（已结束）
   - `war.soldier_share > 0`（士兵分红为正，即战争有战利品）
   - `war.triumph_commander_id is not None`（已指定凯旋指挥官）
   - 指挥官存活且未死亡

2. 符合条件的凯旋信息在以下环节显示：
   - 广场阶段 UI_03-0（公告环节）：显示 `🏆 <指挥官名> 的凯旋等待投票`
   - 广场阶段 UI_03-2（市场环节）：显示同样信息，并提示可 `vote yes/no`

### 2.2 凯旋投票（广场阶段·市场环节）

各派系在广场阶段的市场环节（step 2）对凯旋进行投票：

1. **AI 模式**：通过 `AutoTriumphDecider.decide_triumph()` 自动决定
   - 读取配置 `combat_rules.triumph_approval_chance`（默认 0.5）
   - 随机值 < 此概率时产生 `vote=True`（批准），否则 `vote=False`（否决）
   - 投票记录为 `(war_id, faction_id, vote)` 存储在 `_forum_pending["triumph_votes"]`
2. **手动模式（人类玩家）**：玩家输入 `vote yes` 或 `vote no`
   - 调用 `forum_api.vote_triumph()` 校验权限和战争有效性
   - 校验通过后记录投票，输出 `✅ 已记录对 <指挥官名> 凯旋的 支持/反对 投票`
   - 无效战争输出错误提示

### 2.3 凯旋结算（广场阶段·公示环节）

在公示结算 `forum_api.resolve_forum()` 中：

1. 从 `_forum_pending["triumph_votes"]` 提取投票数据，按战争分组
2. 对每场符合条件的 resolved 战争：
   - 指挥官已死亡 → 清空 `soldier_share`，标记凯旋失效
   - 无有效投票 → 清空 `soldier_share`，标记凯旋失效
   - 有投票 → 计算各派系总影响力，计算支持率（支持影响力 / 总影响力）
   - 支持率 > 50% → **凯旋批准**，执行 2.4
   - 支持率 ≤ 50% → **凯旋否决**，输出否决信息
3. 无论批准与否，结算后清空 `war.soldier_share = 0`

### 2.4 凯旋批准后的效果（临时影响力）

凯旋批准后：

1. `war.set_triumph_approved(True)` 标记战争已批准
2. 计算每回合临时影响力：
   - `duration = config["combat_rules.triumph_veteran_duration"]`（默认 5 回合）
   - `per_turn = war.soldier_share // duration`
   - 如果 `per_turn > 0`，调用 `commander.add_temp_influence_task(per_turn, duration)`
3. 临时影响力在后续回合自动衰减，5 回合后归零

### 2.5 凯旋式执行（人口阶段·公告环节）

在人口阶段 `PopulationCommand._process_legion_disbandment_and_triumphs()` 中：

1. 遍历所有 resolved 战争，检查 `war.triumph_approved`
2. 如果已批准且指挥官存活 → 输出 `🏛️ <指挥官名> 的军团举行凯旋式！`
3. 调用 `war.set_triumph_approved(False)` 重置标记（避免重复）
4. 然后处理军团解散

## 3. 核心规则

### 3.1 凯旋条件

| 条件 | 说明 |
|------|------|
| 战争状态 | `WarStatus.RESOLVED`（已结束） |
| 士兵分红 | `war.soldier_share > 0` |
| 凯旋指挥官 | `war.triumph_commander_id is not None`（必须明确指定） |
| 指挥官状态 | 存活且未死亡 |

### 3.2 自动投票概率

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `combat_rules.triumph_approval_chance` | `0.5` (50%) | AI 派系投票批准的概率 |

### 3.3 临时影响力计算

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `combat_rules.triumph_veteran_duration` | `5` | 临时影响力持续的回合数 |

计算公式：`per_turn = soldier_share // duration`

### 3.4 投票结算规则

- 支持率 = (支持的影响力总和) / (所有参与投票派系的影响力总和)
- 支持率 > 50% → 批准
- 支持率 ≤ 50% → 否决
- 使用派系总影响力（派系内所有存活人物影响力之和）作为权重

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 已结束战争列表 | `WarSystem.get_resolved_wars()` | 遍历已结束战争 |
| 凯旋投票记录 | `_forum_pending["triumph_votes"]` | `(war_id, faction_id, bool)` 格式 |
| 批准概率 | `config["combat_rules.triumph_approval_chance"]` | AI 决策器使用 |
| 临时影响力回合数 | `config["combat_rules.triumph_veteran_duration"]` | 添加临时任务使用 |
| 派系影响力 | `faction.get_members().influence` 求和 | 计算支持率 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 凯旋审批结果 | `resolve_forum()` 返回消息 | 批准/否决信息 |
| 凯旋式执行 | 人口阶段控制台输出 | 显示凯旋举行 |
| 临时影响力任务 | `Figure._temp_influence_tasks` | 每回合的临时加成 |
| `war.triumph_approved` | War 对象 | 标记凯旋已批准 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `War.triumph_commander_id` | 定义凯旋的指挥官 |
| `War.soldier_share` | 士兵分红数，决定影响力大小 |
| `War.triumph_approved` | 标记已批准的凯旋 |
| `Figure.add_temp_influence_task()` | 添加临时影响力任务 |
| `Figure._temp_influence_tasks` | 存储临时影响力任务列表 |
| `AutoTriumphDecider` | AI 派系凯旋投票决策器 |
| `TriumphDecider` (ABC) | 凯旋决策器抽象接口 |

## 5. 状态与边界

### 5.1 凯旋投票有效条件

- 战争必须为 RESOLVED 状态
- `soldier_share` 必须 > 0
- `triumph_commander_id` 必须不为 None
- 指挥官必须存活
- 玩家必须在正确的回合发出投票请求

### 5.2 无效场景

| 场景 | 处理 |
|------|------|
| 无 resolved 战争 | 凯旋投票环节跳过，显示"无待投票的凯旋" |
| all_resolved 无适合凯旋的战争 | 市场环节不显示凯旋信息 |
| 指挥官在结算时已死亡 | 清空 soldier_share，标记凯旋失效 |
| 无任何派系投票 | 清空 soldier_share，标记凯旋失效 |
| `per_turn = 0`（soldier_share < duration） | 不添加临时影响力任务 |
| 手动模式尝试投票给非凯旋战争 | API 返回错误 `error_not_triumph_war` |
| 战争不存在 | API 返回错误 `war_not_found` |

### 5.3 多个战争

- 同一回合可同时存在多个战争的凯旋投票
- 各战争独立投票、独立结算
- 人口阶段依次处理所有已批准的凯旋

### 5.4 重复处理防护

- 结算后 `soldier_share` 清零，防止下次循环重复处理
- 人口阶段执行后 `triumph_approved` 重置为 False
- 临时影响力任务由 `Figure` 内部管理，不会重复添加

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 凯旋批准：支持率 > 50% | 凯旋批准，添加 temp_influence_tasks（per_turn = soldier_share // 5） |
| 2 | 凯旋否决：支持率 ≤ 50% | 凯旋否决，不添加 temp_influence_tasks |
| 3 | 指挥官死亡时 | soldier_share 清零，凯旋标记失效 |
| 4 | 多个战争同时审批 | 各战争独立处理，各自添加临时影响力 |
| 5 | 无投票记录 | soldier_share 清零，凯旋失效 |

## 7. 历史演化与证据

- 历史审计入口：HF-041（自动凯旋审批）
- 历史名称：凯旋与临时影响力
- 首次实现版本：MVP 0.5
- 演化：最初在 MVP 0.5 实现自动凯旋决策器 + 广场阶段投票。MVP 0.7 扩展了人口阶段的凯旋执行（`_process_legion_disbandment_and_triumphs`）和临时影响力的持续性管理。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-05_凯旋与临时影响力.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent E | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
