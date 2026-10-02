# MVP0.5-20-sys — 元老院系统 API 映射

> **技术映射 — Senate API**  
> **版本：** v1.5  
> **日期：** 2026-08-23（v1.0 初版 2026-07-26）  

---

## 1. 代码目录
```
src/api/senate_api.py           # 元老院 API 入口
src/core/systems/               # 下游系统（resolve_senate 等）
src/phase/phase_senate.py       # CLI 阶段命令（已委托至 API）
```

## 2. API 方法清单

### 2.1 `assign_governors() -> list[dict]`
- **用途：** 总督候选人筛选与分配（C-10a, Wave-03）
- **CLI 来源：** `phase_senate.py` ~L1441-1540
- **逻辑：** 遍历无总督行省 → 筛选候选人 → 分配 → 更新实体
- **返回：** `[{province_id, governor_id, name, assigned_at}]`
- **边界：** 无行省需分配 → 返回空列表

### 2.2 `process_war_takeover(republic_state) -> dict`
- **用途：** 处理战争接管逻辑（C-10c, Wave-03）
- **CLI 来源：** `phase_senate.py` ~L905-991
- **逻辑：** 检查接管条件 → 执行接管 → 更新实体
- **返回：** `{takeover_executed: bool, war_id, affected_provinces, result_details}`
- **边界：** 条件不满足 → 返回 `takeover_executed=False`

### 2.3 `auto_vote(state, player_id, proposals, vote_decider=None) -> dict`
- **用途：** AI 派系自动投票（C-10e, Wave-04 Finale）
- **CLI 来源：** `phase_senate.py` ~L1033-1060, ~L1320-1336
- **逻辑：** 验证派系 → 跳过已投票提案 → 使用 vote_decider 决策
- **返回：** `{voted: [], skipped: [], errors: [], summary: str}`
- **边界：** 玩家已投票 → 跳过；无效派系 → 报错
- **R1（WP-D-R1，v1.4）vote 决策持久化契约：** 同一会期内 `proposal_id × faction_id` 的 AI 决策
  **created once → persisted → reused**——首次消费（Veto 资格判定或最终结算，先到者）经
  `calculate_vote_result`（political_system.py:371 起）`record_senate_vote(source="ai")` 写回
  `game_state._senate_pending["vote_source"]` 注册表；后续消费方（`_passed_proposals_for_veto` /
  `resolve_senate`，含每次新建 decider 的调用）读同一存储，**AI 不重掷**（决策计数 == 活跃 AI
  派系数，Veto+resolve 后不增）。human 票权威优先（`record_senate_vote` 默认 source="human"，
  重复投票返回 False 幂等契约不变——C3）。provenance：结构化 `log_event`
  `type="senate_vote_decision"` + `{proposal_id, faction_id, vote, vote_source=human|ai,
  decision_state=created|reused}`（AU-R1-02c/06a）。

## 3. 调用链
```
phase_senate.py (CLI) → senate_api.py (API) → 对应 Core/Entity
```

## 4. 提案链值域改接（GUI-BETA-R1 WP-C-R1，2026-08-22）

### 4.1 新增 helper（`senate_api.py`，`_build_proposal_options` 之前）
- `_budget_range_for_contract(state, contract) -> dict|None` — 权威预算值域 `{min, max, step, default}`，锚 `contract.base_cost`：PUBLIC_WORKS `min=1T（绝对）/ max=base×150%`；TAX_FARMING `min=base×75% / max=base×200%`；`step=1`；`default=base`。config 缺 `economic_rules.senate_budget` → None（防御，不伪造 20-200）。
- `_legion_options_for_war(state, war) -> dict|None` — 权威军团值域 `{min, max, default, allowed}`：`min=1 / default=4 / max=可用池（len(get_available_legions())）/ allowed=[1..pool]`。config 缺 `economic_rules.senate_war_legions` → None（防御，不伪造 [2,4,6,8,10]）。

### 4.2 `_build_proposal_options` 改接（FC-01/FC-03 数据源）
- war 分支：`params.legions` = config 派生 default（=4，不再硬编码 6）；extra 携带 `legion_options`（QML ComboBox model 来源）；detail「征召 N 个军团」N 取 default。
- budget 分支：`params.modified_budget` = budget_range.default；extra 携带 `budget_range`（QML Slider from/to/step/value 来源）。

### 4.3 `auto_submit_proposals` 同值域改接（P1-a）
- war 分支（原 L708-709/720）：不再读 `testing.min/max_legions`；改读 `_legion_options_for_war` 派生 `[min .. min(remaining, pool)]`，循环外 `remaining = len(get_available_legions())` 成功提案后递减（多战争总和守恒）；`remaining < 1` 跳过宣战。
- budget 分支（原 L822-825）：不再读 code-default `public_work_budget_margin_range`；改读 `_budget_range_for_contract` 派生 `[min, max]` 随机。
- `process_war_takeover` 执行期征召（D-2）：`recruit_count` 不再读 `testing.min/max_legions`，改读 config 派生 `[senate_war_legions.min .. 可用池]`。

### 4.4 `_populate_proposal` 权威谓词 chokepoint（`political_system.py`，GUI + AI 双路径同经）
- budget 分支：contract 不存在→拒绝；非 int→拒绝；<min→拒绝；>max→拒绝；step 不齐→拒绝（affordability 不拦截，决算期破产链不变）。
- war 分支：war 不存在→拒绝；非 int→拒绝；<min(1)→拒绝；>pool→拒绝；多战争总和 > 可用池→拒绝「可用军团不足」。
- helper 经函数内 lazy import 共享（D-1：`political_system` 不在模块顶层 import `senate_api`，避免循环导入）。

## 5. WP-D Senate Proposal Flow 契约（GUI-BETA-R1 WP-D，2026-08-23）

> 本节落 WP-D（GUI-BETA-004/013/023 + 019 residual + Consul/Tribune Authority P1×2）最终实现契约。
> 权威语义来源：Grill-Lite v1.1（D-01~D-10）+ ODR-WP-D-01（CLOSED——方案 B + 防线 1/2）。
> 所有 file:line 锚以最终 commit `4d09b17` 工作树实证为准（不凭报告转述）。

### 5.1 Consul Proposal Authority 契约（四层守卫）

- **Core 单一谓词：** `political_system.py:741-747` `_is_eligible_consul(member)` = `office=="consul"` + 未死亡 + 未 absent（单一事实源，消除 GUI/Core 双判定）。
- **执政官查找：** `political_system.py` `_find_consul_for_faction` —— 主循环消费谓词；fallback（R2 收敛：保留 leader 存在性 + faction 归属检查，资格判定统一委托 `_is_eligible_consul` 单一谓词，原四条件内联退役），任一不满足 → `return None` **fail-closed**（非执政官派系不再误判通过，P1 根因消除）。
- **API 委托（R2 收敛）：** `senate_api.get_senate_view` 能力位由 `PoliticalSystem.resolve_proposal_control` 单一 resolver 产出（`mode=="HUMAN"` → viewer_has_consul）；`_viewer_eligible_consul` 独立重算已**退役删除**（FACT-1）。
- **GUI 门禁：** `SenateStage.qml:693` 提案 CheckBox `enabled: sessionStore.canCreateSenateProposal`；提交按钮 `SenateStage.qml:885` `enabled: (canCreateSenateProposal || canTriggerAIProposer) && !hasZeroValueLandSelection()`（非执政官可经主按钮触发 AI proposer——frozen §11 Scenario B，偏离 D-7）。
- **R1（v1.4）参数控件 authority 门控（AU-R1-03a，AC-R1-03 BLOCKER）：** 非执政官 viewer 除勾选外，**参数编辑控件一律按 `sessionStore.canCreateSenateProposal` 门控**——disclosure 三角 MouseArea（SenateStage.qml:724-731）`enabled: canCreateSenateProposal`（面板不可展开）；军团 ComboBox（:764-766）`enabled: canCreateSenateProposal && legion_options 存在`；预算 Slider（:795-797）`enabled: canCreateSenateProposal && budget_range 存在`；land Slider（:829）`enabled: canCreateSenateProposal`。API 保持 fail-closed 不动（仅回归，test_senate_authority.py）。
- **R1（v1.4）collapse 契约（AU-R1-04a，AC-R1-04）：** `setProposalSelected`（:268-274）内联驱动 `expandedBillKeys`——checked → 自动展开 / unchecked → 折叠（checkbox 为控制交互，无陈旧参数面板残留，G7 #8 反例闭合）；三角 `toggleBillExpanded`（:310-315）保留为手动覆盖（两状态恒一致）。
- **AI 路由：** `session_store.py:1255-1267` `doSubmitSenateProposals` —— viewer_has_consul → `propose_many`（0…N）；非执政官 → `adapter.call(senate_api.auto_submit_proposals, state)`（AI 为决策者；复用 adapter 统一反馈映射，不新增 api_adapter 方法，偏离 D-8）。
- **API 负向：** 未授权手动提案 mutation fail-closed（`propose` 经 `_populate_proposal` 权威谓词；测试 test_senate_authority.py）。

### 5.2 Senate DTO capability 字段（get_senate_view data，senate_api.py:459 起）

| 字段 | 语义 | 来源（senate_api.py，R2 收敛后） |
|:--|:--|:--|
| `viewer_has_consul` | viewer 派系存在 eligible 执政官 | `resolve_proposal_control(viewer).mode == "HUMAN"`（单一 resolver） |
| `can_select_proposal` | viewer 可手选/配置提案（R2-A-2：补 actionable + step==proposal guard，与 can_create_proposal 三重 guard 对齐） | `actionable && step==proposal && viewer_has_consul` |
| `can_create_proposal` | 可提交 = actionable + step==proposal + viewer_has_consul | `can_create` |
| `can_trigger_ai_proposer` | 非执政官派系可触发 AI proposer（R2-D-3 收严：严格 mode=="AI"；NONE → False） | `actionable && step==proposal && proposal_control.mode=="AI"` |
| `can_veto` / `can_auto_veto` / `viewer_has_tribune` | Tribune 否决权 authority 态（R2-D-3 收严：严格 mode==HUMAN/AI；NONE → 双 False，fail-closed） | `resolve_veto_control(viewer)`（详见 MVP0.5-09 v1.2） |
| `proposal_control_mode` / `veto_control_mode` | HUMAN\|AI\|NONE provenance（AC-R2-11） | resolver 直出 |
| `proposal_actor` / `veto_actor` | 权威 office holder id（或 None） | resolver 直出 |
| `authority_reason` | `{"proposal": str, "veto": str}` JSON dict（D-2 形状） | resolver 直出 |

SessionStore 透传（session_store.py:355-363 / :400-402）：`canSelectSenateProposal` / `canTriggerAIProposer` / `senatePublicAnnouncement`。

### 5.3 Zero-Proposal 生命周期（propose_many 空批合法 + senate_proposal_decision_complete）

- **人类空批：** `senate_api.py:738-769` `propose_many` —— 空批 = 合法政治决策「本会期不提交法案」→ `senate_proposal_decision_complete = True`（:744）+ success；非空批成功路径同样置位（:762，供 step 区分「未决策」vs「已决策为空」）。
- **AI 空批：** `senate_api.py:771-1030` `auto_submit_proposals` —— 成功返回前置 `senate_proposal_decision_complete = True`（:1024；0 提案也合法，D-05/D-09）。
- **状态存储：** `game_state.py:264-270` `senate_proposal_decision_complete` property（存 `_senate_pending["decision_complete"]`，__init__ :134-141）；随 `clear_senate_pending`（:250-256）自动重置；to_dict :751-753 / load_from_dict :907-913 / create_for_testing 三处同步。
- **step 推导：** `senate_api.py:505` 读取 + :565-571 —— `not decision_complete` → proposal；decision_complete 且无 proposals → **results**（Path A：0 提案跳过 vote/veto 空结算）；否则 vote → veto。
- **空结算 hook：** `session_store.py:1269-1279` —— 提交后 created 空且 submitted 空 → `adapter.resolve_senate()`（Path A 全链：resolve → record_phase_result → advance 可过，P2-01）。

### 5.4 AI proposer 0…N + 空批

- **执政官查找（`senate_api.py:795-800`）：** 主循环校验 `office=="consul" + 未 absent + 未死亡`；fallback 校验 leader 同条件（全局执政官语义）。
- **提案生成 0…N：** war（威胁 + 军团值域）/ peace / governor / budget / land（land 决策器默认 populares→distribution、optimates→sale）；无适用对象或决策器拒绝 → 0 提案，仍 success + decision_complete。
- **空批不阻断阶段推进（D-09）：** 旧规则「phase cannot advance before a valid proposal exists」已被「proposal decision complete，结果可合法为 ∅」替代（Grill-Lite §14.2）。

### 5.5 Public Announcement DTO（公示）

- **组装：** `senate_api.py:1147-1160` `resolve_senate` → `phase_data["public_announcement"] = {enacted_proposals: [{proposal_id, type, title, key_parameters}], direct_actions}`；随 `record_phase_result("senate")` 持久化。
- **准入规则（D-06）：** 仅 **final enacted** 进公示；rejected/vetoed 留在 Proposal/Vote/Veto history，**不进公示**。
- **key_parameters（D-08，senate_api.py:102-127）：** land→`{act_type, amount_C, percent}`；war→`{war_id, legions}`；budget→`{contract_id, modified_budget}`；governor→`{province_id, candidate_id}`；peace→`{war_id}`。值全部来自 authoritative proposal dict（禁 QML 推导）。
- **回读：** `get_senate_view`（senate_api.py:572）`public_announcement` 经 result_data 回读；SessionStore `senatePublicAnnouncement`（session_store.py:400-402，回退 `{}`）。
- **渲染：** `SenateStage.qml:127-156`（`_announcementEnactedText` / `_directActionText`）+ 结果面板 `:452-473`（「✅ 最终通过」+「⚡ 直接生效」区块；rejected 维持既有 veto 区展示，D-06 分离语义）。

### 5.6 参数连续性（Proposal→Vote→Veto→Result）

- 提案 payload 于 `_populate_proposal`（political_system.py:797 起）冻结：land amount_C / war legions / budget modified_budget / governor candidate / peace war_id。
- label 为权威摘要载体（senate_api.py:60-85）：land「卖地法案 — 出售 N C（约 M%）」；war/budget 同源含参。
- Vote/Veto 阶段复用 submitted_proposals + label（QML `voteParamDescription` land/war/budget 分支置空 = label 为准，SenateStage.qml:360-365）。
- Announcement key_parameters 值来自 authoritative proposal/result DTO（禁 QML 重推导，023 连续性满足）。
- **R1（v1.4）vote 决策持久化契约（AU-R1-02a/b/c，AC-R1-02 BLOCKER）：**
  - 根因（R1-02）：`calculate_vote_result`（political_system.py:371）`:372` 每次调用新建 decider、`:404` AI 票内联计算**未写回** → Veto（`_passed_proposals_for_veto`）与 resolve 两消费方重掷翻票。
  - 修复：`:404` else 分支 `decide_vote` 后立即 `record_senate_vote(player_id, proposal_id, support, source="ai")` 持久化；后续消费（含新建 decider 的调用）读同一存储 → 同一 support/oppose。human 票路径不变（source="human"）。
  - 幂等（C3）：`record_senate_vote` 重复返回 False 契约保持；AI 写回不覆盖 human 票；`vote_source` 注册表随 `clear_senate_votes` / `clear_senate_pending` 镜像清除（无跨会话泄漏）；to_dict/load_from_dict 存档往返（旧存档缺键 → 空 dict 向后兼容）。
  - provenance（AU-R1-02c/06a）：结构化 `log_event` `type="senate_vote_decision"` + `{proposal_id, faction_id, vote, vote_source, decision_state}`（created=首次 AI 决策即持久化；reused=复用既有存储）。

### 5.8 R2 Senate Authority Consolidation（GUI-BETA-R1 WP-D-R2，2026-08-23，v1.5）

> 单一 authority root 收敛（R2-A Proposal Authority + R2-B Tribune Veto Authority + shared root）。
> 冻结语义来源：SA Design（02-SA-Design-WP-D-R2）+ G3 DESIGN_FROZEN（C1~C8）+ Task Package v1.0（§10/§11）。

**① 单一 authority resolver（唯一权威解析路径，消费者只读结果禁独立重算）：**

```text
PoliticalSystem.resolve_proposal_control(viewer_player_id) -> {mode: HUMAN|AI|NONE, actor, authority_reason}
PoliticalSystem.resolve_veto_control(viewer_player_id)     -> {mode: HUMAN|AI|NONE, actor, authority_reason}
  missing_viewer / missing_faction → NONE（fail-closed，D-R2-05）
  faction 内 eligible office      → HUMAN（human_eligible_consul / human_eligible_tribune）
  全局 eligible office（AI 语义）  → AI（ai_eligible_consul / ai_eligible_tribune）
  否则                            → NONE（no_eligible_consul / no_eligible_tribune）
收敛 helper：_find_any_eligible_consul / _find_tribune_for_faction / _find_any_eligible_tribune
（退役 ≥10 处内联 duplicate：C2 fallback 四条件 / C3 auto_submit_proposals / C4 phase_senate /
 C5 takeover_war / T2 _current_tribune 薄委托 / T3 record_veto / T5 _get_tribune /
 _viewer_eligible_consul 删除 / _viewer_has_tribune 删除 / DTO 独立组合——C4）
```

**② `apply_auto_tribune_vetoes` 人类 guard（R2-B-1，C2）：**

```text
签名 + viewer_player_id: Optional[str] = None；guard 置于 decider 构造（:437）之前：
  resolve_veto_control(viewer) == HUMAN → WARNING 日志（type=tribune_veto_human_guard）+
  api_response(False, "人类保民官拥有否决权，AI 否决不可执行", {vetoed:[], decisions:[]})
  → AutoTribuneVetoDecider 零构造零调用（spy/call-count 硬证据）
viewer_player_id=None（CLI auto 模式）→ 行为不变（FACT-8 向后兼容）
```

**③ `can_select_proposal` 三重 guard（R2-A-2，C5）：** `actionable && step==proposal && viewer_has_consul`（对齐 can_create_proposal）。

**④ office 清档↔结算耦合闭合（R2-A-1，C1）：** `resolve_population_slice`（session_api.py）结算尾段以幂等 `begin_population_phase`（population_entry marker 守卫，archive→convert 全序 P1-1b）替代独立 `convert_battlefield_commanders` 调用——archive 无条件先于 `resolve_election`，消除「resolve 前未清档」的间歇 stale office 窗口（R2-04 根因）；conversion DTO 形状保持 `{converted, total}`；顶部 :523 阶段门控保留（互补且幂等，无双重归档）。

**⑤ HUMAN vs AI 路由边界（生产入口）：**

```text
入口                             路由（R2 收敛后）
get_senate_view                  能力位 + provenance 全由 resolver 单一产出
create_proposal                   _find_consul_for_faction（fail-closed 保留，谓词收敛）
record_veto                       _find_tribune_for_faction（fail-closed 保留，T3 收敛）
apply_auto_tribune_vetoes         R2-B-1 guard（viewer HUMAN → 零调用）+ _current_tribune（薄委托）
auto_submit_proposals             _find_any_eligible_consul（C3 收敛；:1034 AI takeover 触发点保留 → WP-G）
doSubmitSenateVetoes（store）     读 resolver-backed veto_control_mode：HUMAN→submit / AI→apply_auto（直传 viewer_id，guard 双层兜底）/ NONE→resolve 直结——不信任 cached can_auto_veto（R2-B-2，C3）
doSubmitSenateProposals（store）  读 viewer_has_consul（resolver 单一产出）路由
can_trigger_ai_proposer / can_auto_veto  严格 mode=="AI"（D-3：NONE → 双 False，fail-closed）
```

### 5.7 Takeover Direct Action（独立于 vote/veto 链）

> **R2 范围声明：** war/truce/takeover 生命周期语义不属于 WP-D-R2（Task Package §4/§0 路由 WP-G）；R2 仅将 `takeover_war` 的资格判定收敛为 `_is_eligible_consul` 谓词委托（C5，行为等价），`:1034 execute_ai_takeover_direct_action` 触发点一字不动。

- **入口：** `senate_api.py:586-628` `takeover_war` —— 权限校验（faction 成员 office==consul + 未 absent + 未死亡，:625，fail-closed）→ 活跃外战 + 幂等校验 → `execute_war_takeover_direct` 直接执行。
- **记录：** 成功分支 `senate_api.py:665-672` `record_senate_direct_action({action_type:"takeover", war_id, war_name, commander_id, commander_name, legions})`。
- **存储：** `game_state.py:272-278` `record_senate_direct_action` / `get_senate_direct_actions`（`_senate_pending["direct_actions"]`，与 proposals 同生命周期，clear 自动重置，随 to_dict/from_dict 序列化）。
- **快照：** `political_system.py:296-308` resolve_senate 结算循环后、clear_senate_pending 前快照 → senate_api 组装公示（AU-5）。
- **view 透传：** `senate_api.py:571` `data.direct_actions` 实时 pending；结算后被清空，持久副本在 public_announcement。
- **链外性（D-02/D-07）：** 不创建 proposal、不进入 calculate_vote_result / record_veto / execute_passed_proposal；公示按「已生效事项」展示（⚡ 直接生效）。
- **R1（v1.4）Direct Action 独占性（AU-R1-05a/b/c，AC-R1-05 BLOCKER，G3 C1/C4）：**
  - **resolve_senate 零 takeover**：`resolve_senate`（core :251 / api :1080）的 `takeover_decider` 参数与隐藏 `process_war_takeover` 调用（原 :314）已移除——普通结算不再产生任何接管 mutation；重复 resolve 亦不能静默接管。
  - **AI 自动接管同语义路径**：`PoliticalSystem.process_war_takeover` 重构为 `execute_ai_takeover_direct_action`（Direct Action 语义）——判定 eligible 活跃外战（ACTIVE + 非起义 + 指挥官缺失/已死/absent proconsul-propraetor）→ 候选 Consul（consul 优先）→ `decider.decide_takeover`（AI 自动化决策保留）→ mutation 统一走 `execute_war_takeover_direct`（与 human 同路径，FC-05 原子性）。
  - **唯一触发点（C1，偏离 D-1 采纳）**：`auto_submit_proposals` 尾部（senate_api.py，GUI session_store:1265 / CLI phase_senate:1025 双入口共享同一活跃函数）——**严禁放回 resolve_senate**；auto_player_processor.py 为死代码（全仓零调用方）不选为触发点。CLI auto 模式经同入口继承 AI 接管（D-4 语义不回归）。
  - **provenance（C4）**：`record_senate_direct_action` payload 扩展为 10 字段——既有 6 字段（action_type/war_id/war_name/commander_id/commander_name/legions）+ `action:"takeover"`、`trigger_source:"human_explicit"|"ai_auto"`、`previous_status`、`resulting_status`（= war.status 执行前后值，takeover 不改 status → 均为 "active"，D-3 最小解释）；`get_senate_view` / `get_senate_direct_actions` 按 dict 透传不变 → 既有消费者零破坏。

### 5.7.1 WP-G-R7 同步注记（2026-09-20；append-only）

> **权威**：SA-Design-WP-G-R7-2026-09-20 §A/§B + R7 任务包 §6/§7/§13。**GAME_RULE_CHANGE = NO**（纯展示层闭合，零规则变更）。

**A. Direct Action 提交后的会期连续可见性（R7-A）**
- Submit 成功（direct-only 或混合包）→ 冻结 direct 决策按**稳定身份 `item_ref`** 保留**只读、会期连续可见**：
  - Store 新增只读 Property `session_store.senateConsulDirectDecisions`（顶层 DTO `consul_direct_decisions` 透传）；
  - `SenateStage.qml` 新增 step 无关只读区 `frozenDirectSection`（`senateFrozenDirectRow`，bounded ≤168，无输入控件 ⇒ 不可再 Submit）；
  - 呈现身份 = War label / Commander label / N（+ `authority_label` / `display_label`）；行内**无 `proposal_id`** ⇒ 不进 Vote / Veto 候选；
  - `awaiting_boundary → executed` **仅**由 `Senate→Combat` 边界 receipt（COMMITTED）驱动，Submit→边界之间**零军事 mutation**。
- 与 PA 结果面板同 producer（`_consul_direct_decision_rows`）⇒ Results/PA 同一身份（四跳 trace：draft.war_id → submit.war_id → view.item_ref → PA.item_ref）。
- **R7 不新增 Save/Load 范围**，不削弱既有重入身份。

**B. 提交校验失败恢复 UX（R7-B）**
- 失败 → **bounded** 呈现：固定 28px 单行状态条（`senateValidationStrip`）+ bounded `Dialog`（`senateValidationDialog`，modal / ESC / Close，内 `ScrollView`）——属 Overlay 层，**不 resize 主布局**；finalization warning 同规格 bounded（`senateFinalizationWarningStrip`）。
- 精确高亮：`invalid N` → 该卡 + N 字段（`warCardNField`）；`duplicate Commander` → 全部涉事卡 + Commander 字段（`warCardCommanderField`）；卡级块 bounded ≤120（`warCardErrorBlock`）。
- 错误色 = canonical `theme.statusError`（= 设计系统 `#C45151`）；不引第二套红。
- **草稿深值保留**（checked / mode / target Commander / N 逐字段相等，失败不 rebuild）；**零部分发布**（零 Senate 提案 + 零 direct 决策，Core 原子门未触）；就地改值 → 受影响卡红框清除（逐卡 ack，**不声明有效/通过**）→ 原地 Resubmit 成功，**无需**阶段/游戏重启或离开重入。

### 5.7.2 WP-G-R8 同步注记（2026-09-20；append-only）

> **权威**：SA-Design-WP-G-R8-2026-09-20（DESIGN FROZEN `9d8f7bdb…`）§4.1/§4.2/§5.2/§5.3 + R8 任务包。**GAME_RULE_CHANGE = NO**（纯展示层闭合）。

**A. 生命周期文案时点（R8-AC-01/02/03）**
- 提案期（`senateCurrentStep=="proposal"`）= 配置语义：路由文案「元老院表决」/「执政官直接行动」（**不含「决定」**）；`WarProposalCard.authorityLabel()`。
- Proposal Step Exit 后（`proposalStepDone`）frozen / 结果 direct 行呈现「执政官决定：<War>，由 <Commander> 指挥，增援 <N> 个军团」（`consulDecisionSummary`），身份取冻结 ledger 快照（`war_label`/`target_commander_label`/`reinforcement_n`）；frozen 区可见性谓词（`frozenDirectRows().length>0`）不变，仅标题随 step 切换。
- 执行状态 `consulExecutionStatus`：边界前「待战斗阶段执行（尚未执行）」；`execution=="executed"`（receipt COMMITTED）才「已执行」；UI 只读、不推断、不透传 producer `execution_label`。
- 数据面不变：`display_label`/`execution_label` 仍在 Store DTO 行内（诊断留 Store/日志）；UI 仅不再渲染。

**B. 诊断边界（R8-AC-04/05/08）**
- 玩家面零 raw diagnostic：移除 Dialog「机器详情」+ raw JSON 渲染、frozen 行 `item_ref` JSON、卡级展开 JSON（`errorDetailsText`/`errorDetailsExpanded`）；helper `senateErrorDetailLine`→人话、`senateErrorDetailExtra`→label 对象清单；label fallback 人话（「战争名称暂不可用」/「指挥官身份暂不可用」/「战争信息待更新」）。
- Store 只读薄封装 `_raise_senate_feedback`：Senate submit/advance/vote/veto/recovery 旁路 toast 人话化；原 `feedback` 返回 / 错误对象 / 日志 / 非 Senate 面不变。
- `senateErrorMachineJson()` 保留空实现（`return ""`）以兼容 R7 契约 `test_wpgr7_validation_ux::test_error_helpers_implemented`；**退役提议走 Test Amendment Route**（未获裁定前不删）。

**C. 布局不变量（R8-AC-06/07）**
- `SenateStage` 三面板行唯一高度算法：`Hrow=min(460, max(MIN_PANEL_ROW_H=360, U.h−28))`，`Layout.minimumHeight=preferredHeight=maximumHeight=Hrow`（禁 fillHeight 余量分配；step/内容/results 无关；旧 results `460→200` 条件高度删除）；同 `U` 跨 proposal/vote/veto/results 高差 ≤1px。
- Panel1 主 body 统一 scroll ownership：`senatePanel1BodyScroll`（`ScrollView`）覆盖 说明 + War Card Repeater + frozen direct 区 + nonWar/submitted 列；旧只包 nonWar 的局部 `ScrollView` 移除；真实可读 viewport = `Hrow−95 ≥ 265`；footer 提交按钮固定在 body 外（34）。
- 结果/PA 独立区 `senateResultsArea`：min=preferred=max=**132**（padding10 + 固定标题28 + gap6 + 结果滚动 78），绝不扣减 Hrow。
- 外层兜底 `senateOuterScroll`（U inset14 outer viewport）：余量 R<0 时可滚达整块面板/结果区；不承担 `panel.clip` 裁剪。
- Dialog 专用 envelope（L-D）：usable rect = window client rect inset16；`Dw=min(640, W.w−32)`、`Dh=min(440, W.h−32)`、居中；固定 header40/footer40、可滚正文；ESC + Close 双关闭；属 Overlay 层，不位移背景面板行。

**D. direct 不可表决（延续 R7/R8-AC-09）**：direct 决策行持续只读、不进 Vote/Veto 候选（`veto_candidate_ids` 永不含 direct）。

**GAME_RULE_CHANGE=NO**（纯展示层）。

### 5.7.3 WP-G-R9 同步注记（2026-09-26；append-only）

> **权威**：SA-Design-WP-G-R9-2026-09-26 v1.1（DESIGN FROZEN `9b36bd8e…`；§3 FC-R9-01…11 / §5 AC-R9-01…05 / §6.2 SECC / §7）+ G3-R9 Freeze Gate Record §2 + PM 补充裁定 ADDENDUM 01（`52362366…`）。**GAME_RULE_CHANGE = NO**（API 投影作用域收敛；不改 Store/QML/Core authority/战争规则/R8 冻结面）。

**A. 当前投影作用域收敛（R9 / FC-R9-01/02/04）**
- 变更点 = **仅 `get_senate_view` 顶层 direct 调用点** + 1 个 scope helper（`senate_api._current_canonical_direct_scope(state)`）；`scope guard` 仅此一处。
- `consul_direct_decisions` 顶层投影只接收**同时满足**下列 AND 条件的决策：① 该 direct 决策属于 canonical 当前会期；② 存在与其身份匹配（`package.senate_session_id == s`）且值有效的 current-turn PackageRecord；③ 该 PackageRecord 的 `submitted_at.turn` 完整、类型为整数（`bool` 非法）且 `== state.turn.turn_number`。
- 证明路径 = `get_senate_package_id_for_session(s) → get_senate_package_record(id)`；判定**只用 opaque session 与 package 元数据，不解析 session ID 文本**。缺 `state.turn` / 缺 `s` → 返回 `[]`。
- 通过 scope → 调原 `_consul_direct_decision_rows(state, s)` **原样透传**（不逐 War 查状态、不改 payload/item_ref/order、无 `proposal_id`）；不通过 → `[]`。
- **原 helper 与 `_build_public_announcement`（PA）语义不变；scope guard 仅顶层调用处；历史 PA 不清。**

**B. canonical 会期 / custom session / package turn 判据（R9 / FC-R9-02）**
- canonical 会期 = **由有效 PackageRecord 证明**的权威绑定会期；含 **opaque custom session**（要求身份匹配 + 有效 current-turn PackageRecord）。
- 不硬编码「所有会期 ID 必为 `turn-N`」；缺省生产会期 ID 仍为 `turn-{turn}`，但调用者可显式提供 session ID。
- 消费既有 `submitted_at.turn` 事实，**无新 schema / 持久字段 / 缓存 / 锁 / 公共 API / authority·route 变更**。

**C. 无包与坏包统一排除（ADDENDUM 01 支持边界，无歧义、不 fallback）（R9 / FC-R9-03）**
- **无 PackageRecord ⇒ 一律排除**（含 direct record 自身带有效 `turn`、或 `s` 恰等于 `turn-{current_turn}`）；**不设**前缀匹配、模糊解析或 `turn-{current}` 兜底 fallback。
- **PackageRecord 存在但 `submitted_at.turn` 缺失/非法/不匹配 ⇒ 一律排除，不 fallback 到无包规则。**
- 未知 custom ID → 返回 `[]`，**保留 ledger 不删**；需要恢复此类未证实记录须另裁，不猜。
- **性质声明（防假闭合）**：本边界 = 支持范围/兼容边界定义，**不声称已证实真实 legacy 回归**；正常 publish 总写 `submitted_at.turn`，正常新生产包不受损。ADDENDUM 01 消除「无包反而放行 / 有坏包却被拒」的不一致——两者**统一排除**。
- 七类 T03 参数化对照（current canonical valid / current custom valid ⇒ 保留；no-package canonical current、no-package canonical stale、坏包、unknown custom、SaveLoad 不可解析 ⇒ 排除）见 `03-da-evidence/R9/`。

**D. 只读与生命周期边界（R9 / FC-R9-04/06/10）**
- GET scope **纯读取**：不 `set_senate_session`、不清 pending、不删除 ledger、不重算/重执行 receipt、不改 completion/transaction/guard/奖励/军事绑定。旧 session 指针可保留于 state，不再作为当前投影的充分条件。
- `clear_senate_pending` 不清历史 ledger/session；重读/SaveLoad 以当前 turn 与既有 PackageRecord 重判；不新增持久 scope。
- authority 不变（THREAT/ACTIVE/TRUCE/approved temporary TRUCE/RESOLVED 路由继承 §5.7）；RESOLVED 无合法 Command/Takeover/Reassignment/Continue/Peace 配置入口。

**E. 历史 helper / 冻结面保留（R9 / FC-R9-04）**
- 原 `_consul_direct_decision_rows` 与 `_build_public_announcement` **保留、语义不变**；R9 仅在其顶层调用前增作用域门。
- 不改 §5.7.1（R7）/ §5.7.2（R8）既有语义与布局；不重写 §5.7 全篇；不传播 stale 行号。§2.2 `process_war_takeover` 等旧链已由 R5 supersede（见文末 R5 supersede 注记），本注记不改其旧义。

**F. RENDER/证据边界（R9 §6.1）**：CP1–4 实跑 + 两尺寸截图 = fresh G5 / Owner 义务；DA 不产截图、不冒充分级。

### 5.9 WP-F R2-01 Senate 中间投影 + Passed-Only 收敛（2026-08-30，v1.8）

> 冻结语义来源：WP-F-R2 Task Package v1.0（§5~§8）+ SA Design（02-sa-design/WP-F-R2/SA-Design-WP-F-R2-V4Pro.md §4~§7）+ G4 DA-Plan（D-1~D-4）。GAME_RULE_CHANGE = NO（阈值/权重/AI 投票/Tribune 权威全部不变）。

**① 中间 vote_results 投影（D-1 derive(A) 主案）：** `senate_api._build_vote_results_and_candidates(state)` 单一权威 producer——对每个已提交提案调 `calculate_vote_result`（复用唯一投票计算，零重算/零重掷），产出 `vote_results`（字段复用 resolve_senate 既有 schema：proposal_id/support_influence/oppose_influence/total_influence/passed/vetoed）+ `veto_candidate_ids`（passed 且未否决 id 集，即 `_passed_proposals_for_veto` 的 id 投影）。`get_senate_view` 在 `voted_all`（human 票冻结）后执行投影：

```text
投票完成（voted_all）→ 中间投影（Stage 2 支持率即时可读）
→ 按 len(veto_candidate_ids) 分流：
   >0 → current_step="tribune_veto"（Stage 3 仅渲染 passed 子集）
   ==0 → current_step="results"（zero-passed 收敛，跳过「否决空集」）
```

- **首次决策非重入（ODR-R2-1 冻结）：** 投影可能触发未投票派系首次 AI 决策并幂等持久化（source="ai"，与 resolve_senate 最终计算同源同果）；刷新/重进纯读已冻结票，零 decider 重入、零随机重估。若评审不接受 view 副作用 → persist(B) 兜底案（vote() 完成时持久化中间快照，view 纯读）。
- **DTO 新字段：** `get_senate_view` data dict 新增 `veto_candidate_ids`（list[int]，权威 passed-only 候选集）；`vote_results` 优先中间投影，非 voted_all / 结算后无 pending 提案时回退 phase_data 落盘值（R1 既有 results 展示行为不变）。
- **Store：** `session_store.senateVetoCandidateIds`（只读透传 DTO list，notify=senateViewChanged）。
- **QML：** Stage 2（元老院表决）delegate 追加支持率 Text（`supportRateText(voteResultFor(id))`，投票完成即显，纯展示除法禁阈值判定）；`vetoCandidateRows()` 改按 `senateVetoCandidateIds` 权威 id 映射 display rows（禁平行过滤/重算）。
- **zero-passed 结算（D-2）：** `session_store.doSubmitSenateVotes` 尾部——提交成功后若 `current_step=="results"` 且 senate_result 未落盘 → 自动 `adapter.resolve_senate()`（对齐 CLI 先例 phase_senate.py:495-506 零提案跳过 + doSubmitSenateVetoes 否决后无条件 resolve 先例）；无新按钮/无 API 语义变更。

**② record_veto fail-closed（D-3）：** `PoliticalSystem.record_veto` 对每个 proposal_id 增加四条件守卫——not submitted / vote not complete / Senate failed（passed==False）/ outside candidate set（passed-and-not-vetoed 判定合一）→ 跳过（零 `state.record_senate_veto` 调用，原语零改）+ `rejected_ids` 明细；全拒 → `success=False`（镜像 record_vote「全部未记录返 False」既有契约）；Tribune 权威（`_find_tribune_for_faction`）保留不变。

**③ 消费者收敛：** AI veto（`apply_auto_tribune_vetoes`）已消费 `_passed_proposals_for_veto` 天然 passed-only（零改）；human/API veto 经新 guard；DTO/Store/QML 经 `veto_candidate_ids` 单一 producer —— 全消费者同源，无第二投票/否决算法。

### 5.10 WP-M 主持单一权威收口（2026-09-28，v2.2）

> 冻结语义来源：WP-M SA-Design v1.5（FC-01…10 / D1–D8 / M-AC-01…07）+ Owner ODR-M-01/03 Q1–Q6。**GAME_RULE_CHANGE = YES**（新增权威产品语义）。

**① 元老院主持人单一权威（D2 / FC-01）：**

```text
GameState.get_presiding_officer() -> Optional[Figure]
  主持池 = {m ∈ state._members : not is_dead ∧ not is_absent ∧ office ∈ HOST_OFFICE_SET}
  HOST_OFFICE_SET = {consul, censor, praetor, quaestor, tribune}
  tie-break（四级，保证唯一）: rank↓ → influence↓ → (martial+intelligence+charisma+zeal)↓ → id↑
  空池 → None（合法，触发 D5 结构性跳过）
```

- 全局消费者**只读该符号、禁独立重算**（FC-06/D2.8）：`build_initial_info`/`get_senate_view` DTO `presiding_officer`、`resolve_proposal_control`、`submit_proposal_package`、`auto_submit_proposals`、CLI step0/step1、Store。
- 可用性谓词唯一权威 = `Figure.is_absent`（与 `_is_eligible_consul` 同源）；legacy `Figure.is_present` 不参与。
- 排除 `ex-*`/`office=None`/`proconsul`/`propraetor`/`dictator`。DEBUG log `type=presiding_officer_resolved`。

**② 提案授权 resolver 扩展（D3）：** `PoliticalSystem.resolve_proposal_control(viewer)` 优先级：
1 `missing_viewer` / 2 `missing_faction` / 3 faction 内 eligible consul → `HUMAN(human_eligible_consul)` / **4 host 存在且同派系 → `HUMAN(human_presiding_officer, actor=host.id)`** / 5 全局 eligible consul → `AI(ai_eligible_consul)` / **6 host 存在 → `AI(ai_presiding_officer, actor=host.id)`** / 7 否则 → **`NONE(no_eligible_host)`**（替代旧 `no_eligible_consul`）。
`authority_reason` 固定集合扩展为：`{missing_viewer, missing_faction, human_eligible_consul, human_presiding_officer, ai_eligible_consul, ai_presiding_officer, no_eligible_host}`。DEBUG log `type=proposal_control_host_fallback`。

**③ 提交门 + 主持人职能边界（D4）：** `PoliticalSystem.submit_proposal_package` 授权块：consul 缺失时回退 host（须同派系），否则 `SUBMIT_NOT_AUTHORIZED(details.reason="no_eligible_host")`；host 职能仅限提案主持（create/select/finish-empty/submit/AI proposer），**不含**军事指挥/`AUTHORITY_CONSUL_DIRECT` 战争直接决策/领袖位/否决/总督执行。**回退主持人提交任一 checked 且路由为 `AUTHORITY_CONSUL_DIRECT` 的 war_draft → 整包拒绝 `SUBMIT_NOT_AUTHORIZED(details.reason="host_no_direct_authority")`**（复用唯一 `classify_war_authority`，禁第二套路由）。既有 error code 集合不新增。DEBUG log `type=submit_host_direct_denied`。

**④ 无主持人结构性跳过（D5 / FC-09）：** `get_senate_view` 新增布尔 DTO `senate_no_host`（=host is None）；为 True 时 `proposal_control.mode=="NONE"`、`authority_reason=="no_eligible_host"`、`can_create=can_select=can_finish_empty=False`、`can_trigger_ai_proposer=False`、`proposal_selection_disabled_reason="元老院无在职主持官员"`、`can_advance=actionable`。`finalize_senate_if_ready` 空选择守卫**唯一豁免** = `get_presiding_officer() is None`；`advance_senate_phase` 无 host 且无 phase_result 时先触发 finalize 再执行边界。DEBUG log `type=senate_no_host_skip`。

**⑤ AI proposer / CLI host 化（D4.5 / D6）：** `auto_submit_proposals` 主持人查找由 `_find_any_eligible_consul` 改为 `get_presiding_officer`；无主持人 → `api_response(False, "没有可主持的官员，无法自动提交提案")`；host≠consul 时构造阶段跳过会路由到 `AUTHORITY_CONSUL_DIRECT` 的草案。CLI `phase_senate._handle_step_1` 主持/提交者查找统一经 `get_presiding_officer()`。

**⑥ DTO 新增字段：** `get_senate_view.data["senate_no_host"]`（bool）；`proposal_control_*`/`authority_reason.proposal` 值域随 D3 扩展。**零新增持久化**（FC-10：主持/授权为派生事实）。

### 5.11 WP-M-R1 R1-S1 NONE veto 步自动收敛（2026-10-02，append-only）

> 冻结语义来源：WP-M-R1 SA-Design v1.0（FC-R1-01…08 / R1-AC-01…08 / R1-SC-01…05；G3-delta）。**REGRESSION_CORRECTION = YES**（恢复 WP-M 既有冻结语义）；**GAME_RULE_CHANGE = NO**（阈值 / 投票 / Tribune 权威 / `resolve_veto_control` 全部不变）；**Authoritative Product Spec Impact = NOT REQUIRED**。

**语义增量：** 既有映射（§5.9 D-2）只描述 **zero-passed 收敛**（`current_step=="results"` + store 自动 resolve）。本件补齐 **NONE 终条件收敛**：投票完成后 `current_step=="tribune_veto"` **且** `veto_control_mode=="NONE"`（resolver `resolve_veto_control` 输出 = 无 eligible Tribune，`actor=None` / `authority_reason=="no_eligible_tribune"`）时，**同 owner 命令流**（`GuiSessionStore.doSubmitSenateVotes`）**自动收敛**——复用 canonical finalization（`GuiApiAdapter.resolve_senate` → `senate_api.resolve_senate` → `senate_api.finalize_senate_if_ready`），产出真实 `phase_result("senate"){success:true}`、`current_step=="results"`、`can_advance==True`、`canAdvanceSenate==True`；随后 `doAdvanceSenate` → `advance_senate_phase` 成功 → `next_phase_id=="combat"`。

```text
doSubmitSenateVotes（投票成功 + 视图刷新后）:
  if   current_step=="results"  and not senate_result:  → 既有 zero-passed 收敛（§5.9 D-2，逐字不变）
  elif current_step=="tribune_veto" and veto_control_mode=="NONE":  → NONE 终条件自动收敛（本件新增，复用 resolve_senate）
  （HUMAN/AI：mode ≠ NONE → 两分支均不命中 → 否决交互路径逐字不变）
```

**硬边界（FC-R1-01…08）：** ① 门禁**唯一** = resolver-backed `veto_control_mode=="NONE"`（**禁**以 `can_resolve` 或「`can_veto`/`can_auto_veto` 均 False」推断作门禁——`can_resolve` 对 HUMAN/AI 亦为 True，在本 WP **保持不变、维持为未消费的权威 DTO 字段**）；② `resolve_veto_control` / `senate_api.get_senate_view`（GET 保持纯只读）/ `SenateStage.qml`（零 QML diff）**一字不改**；③ 无 fake 按钮 / 不把 NONE 当 AI / 不造 Tribune；④ **无新增持久化**、不改 save/load；⑤ 收敛仅在命令流（`doSubmitSenateVotes` 单 owner），不在 GET 路径隐式写。

**单 owner / 落点：** `src/ui/gui/session_store.py` :: `GuiSessionStore.doSubmitSenateVotes`（既有 zero-passed 收敛块旁新增同 owner `elif` 条件；复用既有 `resolve_senate()`，不新增按钮 / 不改 DTO 派生 / 不改 Core resolver）。

## 6. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v2.3 | 2026-10-02 | DA Sub-Agent (WP-M-R1 R1-S1) | NONE veto 步自动收敛：`GuiSessionStore.doSubmitSenateVotes` 投票完成后 `current_step=="tribune_veto"` 且 `veto_control_mode=="NONE"` → 复用 canonical finalization（`resolve_senate`）自动收敛 → results / canAdvanceSenate；HUMAN/AI 逐字不变；门禁唯一 = resolver-backed NONE（非 `can_resolve`）；零 QML diff / 无新增持久化。REGRESSION_CORRECTION=YES，GAME_RULE_CHANGE=NO。见 §5.11 |
| v2.2 | 2026-09-28 | DA Sub-Agent (WP-M M-S1) | 新增「§5.10 WP-M 主持单一权威收口」——`GameState.get_presiding_officer` D2 冻结定义（HOST_OFFICE_SET + 四级 tie-break）；`resolve_proposal_control` 新增 host 回退层（`human/ai_presiding_officer`，末层 `no_eligible_host`）；`submit_proposal_package` 授权块 host 回退 + direct 整包拒绝 `host_no_direct_authority`；`get_senate_view` 新增 `senate_no_host`；`finalize_senate_if_ready` 空选择守卫唯一豁免 host=None；`auto_submit_proposals`/CLI host 化。GAME_RULE_CHANGE=YES（ODR-M-01/03） |
| v2.1 | 2026-09-26 | DA Sub-Agent (WP-G-R9) | R9 同步：新增「§5.7.3 WP-G-R9 同步注记」——`get_senate_view` 顶层 direct 投影作用域收敛（`_current_canonical_direct_scope`；canonical 仅由有效 PackageRecord 证明 = 身份匹配 + `submitted_at.turn` 完整/整数/匹配当前回合；含 opaque custom session，不解析 session ID 文本）；无包/坏包**统一排除、不 fallback**（ADDENDUM 01 支持边界，不声称已证实真实 legacy 回归）；原 helper 与 PA 语义保留 / scope guard 仅顶层调用处 / 纯读取、无新 schema·持久字段·公共 API。GAME_RULE_CHANGE=NO |
| v2.0 | 2026-09-20 | DA Sub-Agent (WP-G-R8) | R8 同步：新增「§5.7.2 WP-G-R8 同步注记」——生命周期文案时点（配置→决定）/ 执行边界 / 诊断零 raw / 三面板几何不变量（`Hrow=min(460,max(360,U.h−28))`）/ Panel1 主 body scroll ownership / 结果区 bounded 132 / Dialog L-D envelope；`senateErrorMachineJson()` 保留空实现（Test Amendment Route）。GAME_RULE_CHANGE=NO（纯展示层） |
| v1.9 | 2026-09-20 | DA Sub-Agent (WP-G-R7) | Direct Action 提交后连续可见性 + 校验失败恢复 UX 同步（R7-A/R7-B）：新增「§5.7.1 WP-G-R7 同步注记」——冻结 direct 决策按 `item_ref` 会期连续只读可见（进 Results/PA 同身份 / 不进 Vote-Veto / 边界前零军事 mutation / awaiting→executed 仅 receipt）；校验失败 = bounded dialog + 精确卡/N/Commander 高亮 + 草稿保留 + 零发布 + 就地重提。GAME_RULE_CHANGE=NO（纯展示层） |
| v1.8 | 2026-08-30 | GUI-BETA-R1 WP-F-R2（R2-01）：①中间 vote_results 投影（`_build_vote_results_and_candidates`，voted_all 后，Stage 2 支持率即时可读，首次决策非重入）②`veto_candidate_ids` 权威 passed-only 候选集（DTO + `senateVetoCandidateIds` + QML 映射）③`record_veto` fail-closed 四条件 + `rejected_ids` + 全拒 success=False ④zero-passed 收敛（current_step=results + store 自动 resolve，D-2）；见 §5.9 |
| v1.6 | 2026-08-23 | GUI-BETA-R1 WP-E（Slice 11 PU-04）：土地法案 sale → quota + total 双写入（political_system.py:510 `set_turn_land_sale_total` 并行）与 Forum resolve 消费关系（quota=remaining 消费、total 本年度稳定展示）；**REVIEWED-NO-CHANGE**：rejected/vetoed 展示段（senate rejected_proposals_snapshot 已有事件身份，仅验证不改）+ SenateStage.qml 相关段落（见实施报告 §7） |
| v1.5 | 2026-08-23 | GUI-BETA-R1 WP-D-R2（Senate Authority Consolidation）: ①单一 authority resolver（resolve_proposal_control/resolve_veto_control，{mode,actor,authority_reason} HUMAN\|AI\|NONE + 三收敛 helper，退役 ≥10 处内联 duplicate）；②apply_auto_tribune_vetoes 人类 guard（viewer_player_id + fail-closed，decider 零构造零调用 + tribune_veto_human_guard 日志）；③can_select_proposal 三重 guard（R2-A-2）；④resolve_population_slice 尾部幂等 begin_population_phase（archive→convert→resolve 全序，R2-A-1）；⑤HUMAN vs AI 路由边界（store 读 veto_control_mode 不信任 cached can_auto_veto；can_trigger_ai/can_auto_veto 严格 mode==AI，D-3）+ provenance 5 字段（mode×2/actor×2/authority_reason dict） |
| v1.3 | 2026-08-23 | GUI-BETA-R1 WP-D: 新增 §5 Senate Proposal Flow 契约（Consul 四层守卫 + DTO capability 四字段 + Zero-proposal 生命周期 + AI 0…N/空批 + Public Announcement DTO + 参数连续性 + Takeover Direct Action）——Trial Audit P1-PC-02/P1-PC-03 文档闭合 |
| v1.2 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 提案链值域改接（_budget_range_for_contract/_legion_options_for_war helper + FC-01/FC-03 数据源 + auto_submit P1-a 同值域 + _populate_proposal 权威谓词 + process_war_takeover 执行期征召） |
| v1.1 | 2026-07-26 | 新增 auto_vote() 方法（Wave-04 Finale, C-10e） |
| v1.0 | 2026-07-26 | 初版 — Wave-03 senate_api assign_governors + process_war_takeover |

### 6.1 Senate GUI 颜色消费面（WP-F 003，2026-08-29）

```text
senate_view DTO faction 字段（既有，消费面）：
  presiding_officer.faction_name（主持行）
  seat_shares[].faction_name（席位占比行）
  governor_appointments.*.candidates[].faction_id/faction_name（总督候选人行）

颜色消费（SenateStage.qml）：
  本地 factionColor() 三分支硬编码（旧：Opt=#8B0000 / Pop=#006400 / Equ=#00008B）→ 删除
  → FactionStyle { id: factionStyle } 共享实例 → factionStyle.factionColor(faction_name)
  → map 驱动（config 全名键 optimates/populares/equites + f4/f5/f6 + fallback #3A3530）
GovernorAppointmentPanel.qml 同改（候选人行 :276）。
```

---

> **R5 supersede（2026-09-12，WP-G-R5 DA-7 文档同步 / append-only）：** 本文 §2.2 `process_war_takeover`、`takeover_war`、`execute_ai_takeover_direct_action` 与 AI 自动接管直连语义已由 WP-G-R5 冻结设计退役。R5 唯一整包 Submit 入口 = `senate_api.propose_many`（Core `PoliticalSystem.submit_proposal_package`）；唯一边界 mutation 入口 = `senate_api.advance_senate_phase`（Senate→Combat 整包原子事务 + receipt exactly-once）。出征任命/续战统一经 War Card（`get_senate_view`.`war_cards`）。旧单槽 reservation / mandatory takeover / 即时 Continue 均退役。证据：`WP-G-WarTruceTakeover/03-da-evidence/DA-R5-B5/Ledger-归零对照表.md`。

> **WP-O 同步注记（2026-09-27，DA-Execute WP-O/O-S3；append-only，目标锚点 §2 冻结上下文/保留 claim）：** 现任指挥官身份经单一 living 谓词 `GameState.get_living_member` 解析——新建冻结 SubmissionContext 的 current/return/资产镜像事实**省略死者现任**（None/空）；保留 claim 支（`build_commander_claims`）对失效选中目标**可见并 fail**（不静默丢弃）；plan c0/final 用 live（None/missing/dead ⇒ 无现任）。**已冻结的历史 snapshots/payload/labels 不可变**（历史死者名保留，不重写）。Plan/边界回滚 **additive** 捕获 `War.commander_status`（失败 Senate 命令回滚恢复 `killed`）。**GAME_RULE_CHANGE = NO**（authority/状态机零改）。
