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

> **EOR20261012-01（2026-10-12）投票入口语义：** 每派系对该 war 只能表达**赞成（`vote=True`）或反对（`vote=False`）**二者之一；`vote=False` 为既有合法形参（写面 `vote_triumph(...bool)` + append 语义**零改**）。GUI 提供**显式二选控件（赞成 / 反对）**（S-2 Owner 确认，消除歧义）。**无「弃权」态**：未投票的派系在结算中计为**反对**（见 §2.3/§3.4）。

### 2.3 凯旋结算（广场阶段·公示环节）

在公示结算 `forum_api.resolve_forum()` 中：

1. 从 `_forum_pending["triumph_votes"]` 提取投票数据，按战争分组
2. 对每场符合条件的 resolved 战争：
   - 指挥官已死亡 → 清空 `soldier_share`，标记凯旋失效（**全池回罗马国库**，OD-04）
   - 全体有投票权派系影响力之和 = 0（**无有效投票**）→ 清空 `soldier_share`，标记凯旋失效（**全池回罗马国库**，OD-04）
   - 否则 → 计算**全体有投票权派系**（全体注册派系）影响力；支持率 = **支持派系影响力之和** / **全体有投票权派系影响力之和**（**未投派系计入分母 = 反对**）；每 war/派系只按**最后一条有效票**计一次（重复投票以最新为准）
   - 支持率 > 50% → **凯旋批准**，执行 2.4
   - 支持率 ≤ 50% → **凯旋否决**，输出否决信息（**全池回罗马国库**，OD-04）；含**全员未投**（支持率 0%）与**全员反对**（支持率 0%）
3. 结算后清空 `war.soldier_share = 0`（每条清池路径均**守恒**：转为临时政治影响力 或 回罗马国库）

### 2.4 凯旋批准后的效果（临时影响力）

凯旋批准后：

1. `war.set_triumph_approved(True)` 标记战争已批准
2. 计算每回合临时影响力：
   - `duration = config["combat_rules.triumph_veteran_duration"]`（默认 5 回合）
   - `per_turn = war.soldier_share // duration`
   - 如果 `per_turn > 0`，调用 `commander.add_temp_influence_task(per_turn, duration)`；**取整余项 `pool − per_turn×duration` 回罗马国库**（OD-04，FC-15）
   - 如果 `per_turn == 0`（`pool < duration`）→ **全池回罗马国库**
3. 临时影响力在后续回合自动衰减，5 回合后归零

> **EOR20261009-03（OD-04，FC-15）守恒计量：** 凯旋通过 → `per_turn×duration + refund == pool`；否决/无票/失效/小池 → `refund == pool`。池 = **抽象士兵/老兵政治支持**（非现金）；域概念名 `veteran_support_pool`（别名 `soldier_share`）。

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

- 支持率 = (支持派系的影响力总和) / (**全体有投票权派系**的影响力总和)
- **全体有投票权派系** = 全体注册派系（`state.factions`）；**分母包含未投派系**
- **未投 = 反对**：未投票派系计入分母、不计入分子；**不存在「弃权」态**
- 每 war/派系只按**最后一条有效票**计入（重复投票以最新为准；每派系每 war 至多计一次）
- 支持率 > 50% → 批准；支持率 ≤ 50% → 否决
- 使用派系总影响力（派系内所有存活人物影响力之和）作为权重
- 全体有投票权派系影响力之和 = 0 → 「无有效投票」（全池回罗马国库）

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
| 全员未投（正分母、零赞成） | 支持率 0% → **凯旋否决**（非「无有效投票」）；全池回罗马国库 |
| 全体有投票权派系影响力之和 = 0 | 无有效投票 → 清空 soldier_share，标记凯旋失效（全池回罗马国库） |
| `per_turn = 0`（soldier_share < duration） | 不添加临时影响力任务；**全池回罗马国库**（OD-04，守恒） |
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
| 5 | 无投票记录（正分母、零赞成） | 支持率 0.0% → **凯旋否决**（非失效）；soldier_share 清零（全池回罗马国库） |
| 5b | 全体有投票权派系影响力之和 = 0 | 无有效投票；soldier_share 清零（全池回罗马国库） |

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
- **「老兵战利品分配」退域历史（J-D06 / ESC-D-01，append-only）**：WP-J Group D 时点 source-first 核为 producer 未实现的业务/经济语义（无人口阶段扣除 / 无否决回国库）⇒ 当时不属呈现面，不呈现、不 QML 自造。
- **【EOR20261009-03 修订（OD-04，2026-10-11）】** 上述退域事实保留为历史；**新 Owner 决定**（OD-04=B + 追加规则）冻结：`soldier_share` = 抽象士兵/老兵政治支持池（域概念名 `veteran_support_pool`），**凯旋被否决/无票/指挥官失效/小池/余项 → 该池金额回罗马国库**（守恒）；经济 owner 实现 = `forum_api.resolve_forum` 结算侧新增写入（不改投票 REST/交互语义）。

## ESC-WPJ-G7Q1-01 同步注记（2026-10-10，DA-Execute；append-only，目标锚点 §2.5）

> 权威：SA-Development-Task-ESC-WPJ-G7Q1-01（G3 FROZEN）/ FC-ESC-01..06。凯旋 share/vote/reward 规则与判定逻辑**零改**（GAME_RULE_CHANGE=NO）。

- **GUI 面凯旋式执行时点对齐阶段入口（Step 0）**：GUI 人口阶段入口 `session_api.get_population_view()` 现于阶段门控块内调用 canonical `population_api.process_population_disbandments()`（§2.5 canonical；FC-ESC-01）⇒ 凯旋「已举行」与军团/舰队解散反馈在**进入人口阶段的一瞬间**（庆典之前）即可见，与 CLI `phase_population._handle_step_0` 同序。
- 结算侧调用**保留**为幂等安全网（marker `population_disbandment`）⇒ exactly-once；本件**不新增/不改**玩家可见文案，复用既有呈现行（FC-ESC-05）。

## EOR20261012-01 同步注记（2026-10-12，DA-Execute；append-only，目标锚点 §2.1/§2.2/§2.3/§3.4/§5.2/§6）

> 权威：SA-Development-Task EOR20261012-01 v1.1（G3 FROZEN，FC-01..FC-14）+ S-2（Owner 2026-10-12 显式二选）+ PM Erratum E1。**GAME_RULE_CHANGE=YES**（Owner ODR-EOR20261012-01-01/02）。

- **分母改全体有投票权派系（FC-01/FC-12）**：支持率分母 = Σ 全体注册派系（`state.factions`）存活成员影响力之和；**未投派系计入分母**。
- **未投 = 反对，无弃权（FC-02）**：无投票记录的派系计分母、不计分子。
- **最新唯一有效票（FC-14）**：每 `(war_id, faction_id)` 取 append 顺序下**最后一条**合法 bool 记录生效；每派系每 war 只计一次；与 `viewer_vote` 投影自然一致。写面 `vote_triumph(...bool)` + append 语义**零改**。
- **兜底（FC-06）**：分母 = 0（全体有投票权派系影响力之和为 0）→ 「无有效投票」全池回罗马国库；**分母 > 0 且无赞成票 → 支持率 0% → 否决**（不再走旧「无票即失效」early exit）。
- **阈值（FC-04）**：`support_rate > 0.5` 批准，不变。
- **GUI 显式二选（FC-13；重开并替代 WP-J Group B「无赞成·反对二选」冻结）**：凯旋行按 action×viewer_vote 六格呈现——`actionable ∧ 未投` → **[赞成][反对]** 两动作（分别写 `vote_triumph(war_id, True/False)`，刷新进入最新已投态）；`viewer_vote===true` → 灰化 disabled「**已投·赞成**」、`viewer_vote===false` → 灰化 disabled「**已投·反对**」（**已投优先**，readonly 不覆盖）；`null ∧ readonly` → 灰化 disabled「不可投」。QML 逐字消费 producer 投影（零业务重建）。
- **池守恒（FC-08）**：与 WRRI FC-15 一致；本件不动结算侧池处置路径（`_settle_veteran_pool`/`_refund_veteran_pool_to_treasury`）。

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.5 | 2026-10-12 | DA-Execute (EOR20261012-01) | 凯旋投票口径重构（Owner ODR-01/02）：分母 = 全体有投票权派系；未投 = 反对、无弃权；支持率按派系影响力加权；每 war/派系最新有效票（FC-14）；兜底分母=0 → 无有效投票、正分母零赞成 → 0% 否决（替代旧 early exit）；GUI 显式二选（赞成/反对，重开 WP-J Group B 冻结）；阈值 >50% 不变；写面 bool/append 零改；GAME_RULE_CHANGE=YES |
| v1.4 | 2026-10-10 | DA-Execute (ESC-WPJ-G7Q1-01) | §2.5 追加注记：GUI 面凯旋式执行/显示时点对齐阶段入口 Step 0（`get_population_view` 门控块，先于 `begin_population_phase`），与 CLI `_handle_step_0` 同序；结算侧幂等安全网保留；凯旋规则/文案零改（GAME_RULE_CHANGE=NO） |
| v1.3 | 2026-10-09 | DA-Execute (WP-J Group D) | §2.5 追加注记：人口阶段**既有公示框内**呈现权威凯旋「已举行」与军团/舰队解散计数（additive 只读投影 `population_outcome`；框高 additive）+ 否决不重复呈现；「老兵战利品分配」退域（ESC-D-01）；凯旋规则/`resolve_forum()` 写语义零改（GAME_RULE_CHANGE=NO） |
| v1.4 | 2026-10-11 | DA-Execute (EOR20261009-03 WRRI) | OD-04：`soldier_share`/`veteran_support_pool` 语义澄清 = 抽象政治支持；**否决/无票/失效/小池/余项 → 全池/余项回罗马国库**（守恒，FC-15）；保留 WP-J 退域历史（append-only）；变更 `resolve_forum` 结算侧写语义（不改投票交互）；GAME_RULE_CHANGE=YES（Owner OD-04） |
| v1.2 | 2026-10-06 | DA Sub-Agent (WP-J Group B) | ③ GUI 最小规则同步（FROZEN v1.3 / Owner 16:43）：§2.2 追加注记——凯旋行按钮三态（赞成/已投[灰disabled]/不可投[灰disabled]）、点击后即灰化无重复、不可投统一文案；additive 读模型 `triumph_wars[].action`/`.viewer_vote`；Q1 = CLOSED；`vote_triumph` bool/append 语义零改（GAME_RULE_CHANGE=NO） |
| v1.1 | 2026-09-09 | DA Sub-Agent (WP-G-R4 B3) | R4 同步（FROZEN v1.7 §4.3）：§2.1/§3.1/§4.3 追加注记——VICTORY/TRIUMPH 均按当前四条件可 eligible（ordinary VICTORY 保留仪式，无 CRT==TRIUMPH 门）；triumph_commander_id=ceremony candidate 非 CRT 证据；战斗身份 carrier 与 legacy unknown 中性事件；Forum 公开 vote/resolve 一次 + share 单次消费（GAME_RULE_CHANGE=NO） |
| v1.0 | 2026-07-12 | Document Officer Sub-Agent E | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
