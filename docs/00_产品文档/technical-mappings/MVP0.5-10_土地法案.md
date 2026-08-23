# MVP0.5-10 — 土地法案（技术映射）

> **版本：** v1.2
> **日期：** 2026-08-23（v1.0 初版 2026-07-13）

## 1. 代码目录
```
src/core/deciders/land_proposal_decider.py, impl/auto_land_proposal_decider.py
src/core/systems/political_system.py  # _populate_proposal 权威校验 + execute_passed_proposal() 执行
src/api/forum_api.py                  # execute_land_acts() — 土地分配API (Wave-02)
src/api/senate_api.py                 # auto_submit_proposals() / _build_proposal_options() / propose_many()
src/ui/gui/qml/stages/SenateStage.qml # land amount_C Slider 控件
src/ui/commands/phase_forum.py        # → 委托 forum_api.execute_land_acts() (Wave-02)
src/ui/commands/phase_senate.py       # → 委托 senate_api (Wave-02)
data/config/game_config.json          # economic_rules.senate_land（default_percent / step）
```

## 2. 关键方法
- `auto_land_proposal_decider.decide_proposal()` — 自动提案决策器（返回 `(act_type, percent)`，由 senate_api 换算为 amount_C）
- `_populate_proposal()` land 分支（political_system.py:889-909）— **amount_C 唯一权威输入** + 值域校验 + percent 派生
- `execute_passed_proposal()` land 分支（political_system.py:475-490）— **消费 amount_C**（不再 percent 二次重推）
- `_build_proposal_options()` land 分支（senate_api.py:240-255）— GUI 提案选项（默认 amount_C）
- `_proposal_label()` land 分支（senate_api.py:80-84）— 权威摘要「卖地法案 — 出售 N C（约 M%）」

## 3. amount_C 唯一权威主输入（GUI-BETA-R1 WP-D，2026-08-23）

> 冻结语义：Grill-Lite v1.1 **D-01**（Land Proposal Authoritative Input）——土地数量 C 是提交到
> authoritative proposal payload 的主参数；百分比仅作派生显示，不得成为独立可编辑 authoritative input。

### 3.1 权威输入与派生
- **authoritative input = `amount_C`**（整数值；接受 int 或 float.is_integer()，非整值拒绝——political_system.py:899-901）
- **percent = 派生显示 / 连续性值** = `amount_C / national_public_land`（`_populate_proposal` 派生存入 `proposal["percent"]`，:908-909）
- **percent 不再作为独立输入参数接受**（D-01 canonical conversion；GUI/AI 均不得直接传 percent）

### 3.2 值域校验（political_system.py:891-906，GUI + AI 双路径同经权威谓词）
1. 缺 `act_type` 或 `amount_C` → 拒绝「土地法案需要 act_type 和 amount_C」
2. `act_type ∉ {sale, distribution}` → 拒绝
3. 非 integer-valued → 拒绝
4. `amount_C < 1` → 拒绝「土地数量必须至少为 1 C」
5. `amount_C > national_public_land` → 拒绝「土地数量超过国家公地总量」

### 3.3 AI 转换（senate_api.py:986-1014）
- AI 决策器返回 `(act_type, percent)` → `amount_C = max(1, int(national_public_land × percent))`（P2-04 clamp 防 0）
- `propose(..., act_type=act_type, amount_C=amount_C)`；created 记录 `{act_type, amount_C, percent}`

### 3.4 默认值与配置
- `economic_rules.senate_land = {default_percent: 0.10, step: 1}`（game_config.json:165-167）
- `_build_proposal_options` 默认 `default_amount_C = max(1, int(public_land × default_percent))`（senate_api.py:241-245，config 缺失回退 0.10）

## 4. Senate GUI→DTO→Core 全路径

```
SenateStage.qml land Slider（qml:812-836，id landSlider :829 —— from 1 / to modelData.public_land /
    stepSize 1 / value=params.amount_C；onValueChanged → setBillParam(billKey, "amount_C", Math.round(value))）
→ 显示「{amount_C} C（约 {percent}%）」派生展示（qml:822-826）
→ sessionStore.doSubmitSenateProposals（viewer_has_consul → senate_api.propose_many）
→ senate_api.propose_many → propose("land", act_type, amount_C)
→ political_system.create_proposal → _populate_proposal（权威校验 + percent 派生存储）
→ 表决 → 通过 → execute_passed_proposal（消费 amount_C）
```

- 提案选项 params：`{act_type, amount_C, percent}`（senate_api.py:249/:255）；root `public_land` 保留（R2-NEW-01 F2 root+nested 形状，不复现 RC-R2-01）
- QML `voteParamDescription` land 分支置空（SenateStage.qml:360-365）——label 已含参数为权威载体，与 war/budget 同源模式
- 禁 QML 伪造/硬编码：percent 仅派生展示，参数以 authoritative proposal dict 为准

## 5. 消费点（execute_passed_proposal，political_system.py:475-490）

| act_type | 消费 | 落点 |
|:--|:--|:--|
| `sale` | `state.set_pending_land_sale_quota(amount_C)`（:479-483） | 贵族买地法案待售公地配额 |
| `distribution` | `state.add_pending_land_act({type:"distribution", percent, amount: amount_C, description})`（:484-490） | Forum 阶段 `execute_land_acts()` 消费 |

**双事实源消除（P-6）：** 执行期不再 `int(national_land × percent)` 二次重推——amount_C 为唯一权威消费值，percent 仅作展示/连续性字段（D-01 第 5 条）。

## 6. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.2（R2 复核） | 2026-08-23 | GUI-BETA-R1 WP-D-R2 复核：**REVIEWED — NO CHANGE REQUIRED** —— authority 收敛（单一 resolver / R2-A Proposal Authority / R2-B Tribune Veto Authority）不触碰 land proposal 语义；amount_C 权威主输入 / percent 派生契约 / 值域校验 / 消费点全部不变（§3/§4/§5 零改动） |
| v1.2 | 2026-08-23 | GUI-BETA-R1 WP-D: amount_C 唯一权威主输入（percent 派生）+ 值域校验（integer-valued / 1..public_land）+ AI percent→amount_C 转换 + GUI→DTO→Core 全路径 + 消费点（sale→quota / distribution→pending act）——Trial Audit P1-PC-02/P1-PC-03 文档闭合 |
| v1.1 | 2026-07-26 | 土地分配 CLI→API 下沉：新增 forum_api.execute_land_acts() + senate_api 法案提交 |
| v1.0 | 2026-07-13 | 初版 |
