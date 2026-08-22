# MVP0.5-20-sys — 元老院系统 API 映射

> **技术映射 — Senate API**  
> **版本：** v1.0  
> **日期：** 2026-07-26  

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

## 5. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.2 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 提案链值域改接（_budget_range_for_contract/_legion_options_for_war helper + FC-01/FC-03 数据源 + auto_submit P1-a 同值域 + _populate_proposal 权威谓词 + process_war_takeover 执行期征召） |
| v1.1 | 2026-07-26 | 新增 auto_vote() 方法（Wave-04 Finale, C-10e） |
| v1.0 | 2026-07-26 | 初版 — Wave-03 senate_api assign_governors + process_war_takeover |
