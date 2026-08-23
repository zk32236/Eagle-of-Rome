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

## 6. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.6 | 2026-08-23 | GUI-BETA-R1 WP-E（Slice 11 PU-04）：土地法案 sale → quota + total 双写入（political_system.py:510 `set_turn_land_sale_total` 并行）与 Forum resolve 消费关系（quota=remaining 消费、total 本年度稳定展示）；**REVIEWED-NO-CHANGE**：rejected/vetoed 展示段（senate rejected_proposals_snapshot 已有事件身份，仅验证不改）+ SenateStage.qml 相关段落（见实施报告 §7） |
| v1.5 | 2026-08-23 | GUI-BETA-R1 WP-D-R2（Senate Authority Consolidation）: ①单一 authority resolver（resolve_proposal_control/resolve_veto_control，{mode,actor,authority_reason} HUMAN\|AI\|NONE + 三收敛 helper，退役 ≥10 处内联 duplicate）；②apply_auto_tribune_vetoes 人类 guard（viewer_player_id + fail-closed，decider 零构造零调用 + tribune_veto_human_guard 日志）；③can_select_proposal 三重 guard（R2-A-2）；④resolve_population_slice 尾部幂等 begin_population_phase（archive→convert→resolve 全序，R2-A-1）；⑤HUMAN vs AI 路由边界（store 读 veto_control_mode 不信任 cached can_auto_veto；can_trigger_ai/can_auto_veto 严格 mode==AI，D-3）+ provenance 5 字段（mode×2/actor×2/authority_reason dict） |
| v1.3 | 2026-08-23 | GUI-BETA-R1 WP-D: 新增 §5 Senate Proposal Flow 契约（Consul 四层守卫 + DTO capability 四字段 + Zero-proposal 生命周期 + AI 0…N/空批 + Public Announcement DTO + 参数连续性 + Takeover Direct Action）——Trial Audit P1-PC-02/P1-PC-03 文档闭合 |
| v1.2 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 提案链值域改接（_budget_range_for_contract/_legion_options_for_war helper + FC-01/FC-03 数据源 + auto_submit P1-a 同值域 + _populate_proposal 权威谓词 + process_war_takeover 执行期征召） |
| v1.1 | 2026-07-26 | 新增 auto_vote() 方法（Wave-04 Finale, C-10e） |
| v1.0 | 2026-07-26 | 初版 — Wave-03 senate_api assign_governors + process_war_takeover |
