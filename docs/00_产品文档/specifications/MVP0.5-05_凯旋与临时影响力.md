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

## WP-G-R4 同步注记（2026-09-09，DA-R4-B3；append-only，目标锚点 §2.1/§3.1/§4.3）

> 权威：SA-Design-WP-G-R4 v1.7（FROZEN）§4.3/§8.1 T10；凯旋 share/vote/reward 规则零改。
>
> - **VICTORY 与 TRIUMPH 均按当前四条件 eligible**（RESOLVED + soldier_share>0 +
>   triumph_commander_id 存在 + commander 存活）：ordinary VICTORY 保留政治凯旋资格，
>   不加「CRT 必须 TRIUMPH」门（R4-07）。`triumph_commander_id` = ceremony candidate，
>   不是 CRT 身份证据（R4-08：不从候选反推战斗结果）。
> - **CRT 身份与 ceremony 分离**：战斗结果身份（combat_victory / combat_triumph）由
>   `resolve_war(..., combat_result=...)` 显式 carrier 携带（legacy bool-only 调用 = 中性
>   `war_resolved`/unknown，不推断 CRT）；事件/phase DTO 保存本次 CRT。
> - **Forum 公开 seam**：get_forum_view（triumph_wars 行）→ vote_triumph → resolve_forum
>   恰一次；批准后 soldier_share 消费归零、二次 resolve 无二次奖励（J 链同 run 断言）。

## WP-J Group B 同步注记（2026-10-06，DA-Execute；append-only，目标锚点 §2.1/§2.2/§3.1）

> 权威：WP-J Group B SA-Development-Task v1.3（G3 FROZEN）§3.3/§4/§5.1/§9；Owner 2026-10-06 16:43 S-2 最小规则；凯旋 share/vote/reward 规则零改。
>
> - **Forum 公开 seam 增 additive 只读字段**：`forum_api.get_forum_view().triumph_wars[]` 逐行新增
>   `action:{state:"actionable"|"readonly", reason}`（单一权威动作可用性投影，FC-B01–B03；`reason` 词表
>   {ok,not_current_player,not_phase,vote_window_closed,resolved} 内部保留、界面不呈现）与
>   `viewer_vote: null|true|false`（FC-B18，viewer 派系对该 war 的最新票）。
> - **GUI 最小规则（③，Owner 16:43）**：凯旋行按钮**三态**——`actionable ∧ 未投` → 「赞成」（可点）；
>   点击 → 既有 `vote_triumph(war_id, True)` → 刷新后**即灰化（disabled）**「已投」（重复点击无效，UI 消除重复投票）；
>   其余 `readonly` → **灰化（disabled）+ 统一「不可投」**（不解释原因）。**无弹窗 / 无赞成·反对二选 / 无二次确认**。
>   QML 逐字消费 producer 投影（零业务重建，FC-B06），不再以 `marketUnlocked/canExecuteForum/forumResolved` 重算可用性。
> - **Q1（投票窗口）** = Owner 16:07 **CLOSED / NO-CHANGE**（市场子环节；不新增 `vote_triumph` 窗口强校验）。
> - **写语义零改**：`vote_triumph` bool + append 记录语义不变。

## WP-J Group D 同步注记（2026-10-09，DA-Execute；append-only，目标锚点 §2.5/§4.2/§5.4）

> 权威：WP-J Group D SA-Development-Task v1.1（G3 FROZEN）§5.1–§5.3/§6；S-2 Owner 确认（2026-10-09）。凯旋 share/vote/reward 规则与判定逻辑**零改**（GAME_RULE_CHANGE=NO）；`resolve_forum()` 写语义保持 Group B 冻结原样（**不新增** `triumph_outcomes`）。

- **人口阶段公示框内呈现**：`session_api.get_population_view()` 增 additive 只读字段 `population_outcome`（逐字投影权威 `state.get_phase_result("population_disbandment")`；回退 `population` 结果 `data.disbandment`）→ `session_store.populationOutcome` → `PopulationStage.qml` **既有公示框 `populationAnnouncement` 内**追加行「🏛️ 凯旋仪式：<commander_name>（<war_name>）已举行」（FC-D01/FC-D02/FC-D03）。框高 additive（基值 88，空 payload 回落，FC-D07）。
- **否决不在人口阶段重复呈现**（S-2 #2）：广场阶段已呈现「凯旋未获批准」；人口阶段仅呈现**已举行**（`triumphs[]` 权威谓词，FC-D03/FC-D04）。⇒ v1.0 拟增的结构化 `triumph_outcomes` **撤销**。
- **军团/舰队解散以权威计数呈现**（FC-D05）：`legions.resolved_wars.total` / `legions.deescalated.total` / `fleets.length`，仅显示已结束战争军团/闲置舰队行政退役**反馈**，**不改**解散时机（①d-2 / WP-G G1-14 冻结）。
- **「老兵战利品分配」= ROUTED_OUT（J-D06 / ESC-D-01）**：source-first 核为 producer 未实现的业务/经济语义（无人口阶段扣除 / 无否决回国库）⇒ 不属呈现面，**不呈现、不 QML 自造**。

## ESC-WPJ-G7Q1-01 同步注记（2026-10-10，DA-Execute；append-only，目标锚点 §2.5）

> 权威：SA-Development-Task-ESC-WPJ-G7Q1-01（G3 FROZEN）/ FC-ESC-01..06。凯旋 share/vote/reward 规则与判定逻辑**零改**（GAME_RULE_CHANGE=NO）。

- **GUI 面凯旋式执行时点对齐阶段入口（Step 0）**：GUI 人口阶段入口 `session_api.get_population_view()` 现于阶段门控块内调用 canonical `population_api.process_population_disbandments()`（§2.5 canonical；FC-ESC-01）⇒ 凯旋「已举行」与军团/舰队解散反馈在**进入人口阶段的一瞬间**（庆典之前）即可见，与 CLI `phase_population._handle_step_0` 同序。
- 结算侧调用**保留**为幂等安全网（marker `population_disbandment`）⇒ exactly-once；本件**不新增/不改**玩家可见文案，复用既有呈现行（FC-ESC-05）。

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.4 | 2026-10-10 | DA-Execute (ESC-WPJ-G7Q1-01) | §2.5 追加注记：GUI 面凯旋式执行/显示时点对齐阶段入口 Step 0（`get_population_view` 门控块，先于 `begin_population_phase`），与 CLI `_handle_step_0` 同序；结算侧幂等安全网保留；凯旋规则/文案零改（GAME_RULE_CHANGE=NO） |
| v1.3 | 2026-10-09 | DA-Execute (WP-J Group D) | §2.5 追加注记：人口阶段**既有公示框内**呈现权威凯旋「已举行」与军团/舰队解散计数（additive 只读投影 `population_outcome`；框高 additive）+ 否决不重复呈现；「老兵战利品分配」退域（ESC-D-01）；凯旋规则/`resolve_forum()` 写语义零改（GAME_RULE_CHANGE=NO） |
| v1.2 | 2026-10-06 | DA Sub-Agent (WP-J Group B) | ③ GUI 最小规则同步（FROZEN v1.3 / Owner 16:43）：§2.2 追加注记——凯旋行按钮三态（赞成/已投[灰disabled]/不可投[灰disabled]）、点击后即灰化无重复、不可投统一文案；additive 读模型 `triumph_wars[].action`/`.viewer_vote`；Q1 = CLOSED；`vote_triumph` bool/append 语义零改（GAME_RULE_CHANGE=NO） |
| v1.1 | 2026-09-09 | DA Sub-Agent (WP-G-R4 B3) | R4 同步（FROZEN v1.7 §4.3）：§2.1/§3.1/§4.3 追加注记——VICTORY/TRIUMPH 均按当前四条件可 eligible（ordinary VICTORY 保留仪式，无 CRT==TRIUMPH 门）；triumph_commander_id=ceremony candidate 非 CRT 证据；战斗身份 carrier 与 legacy unknown 中性事件；Forum 公开 vote/resolve 一次 + share 单次消费（GAME_RULE_CHANGE=NO） |
| v1.0 | 2026-07-12 | Document Officer Sub-Agent E | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
