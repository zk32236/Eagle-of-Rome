# MVP0.5-03 — 公共工程合同（技术映射）

## 1. 代码目录
```
src/core/entities/contract.py          # Contract 实体
src/core/systems/political_system.py   # 预算提案
src/ui/commands/phase_senate.py        # 提案环节
src/ui/commands/phase_revenue.py       # 收入结算
src/api/contract_api.py                # 合同 API
```

## 2. 关键方法
- `create_public_works()` — 创建工程合同
- `mark_winner()` — 竞标中标 (仅BUDGETED)
- `mark_complete()` — 施工完成
- `advance_warranty()` — 质保递减

## 3. 工程合同生成调用链（Wave-01 更新）

### 3.1 广场阶段续约 + 新合同
```
CLI phase_forum._generate_contracts()
  → forum_api.generate_contracts(state)        # [NEW] API 层入口
    ├─ 续约：
    │   └─ PUBLIC_WORKS COMPLETED + warranty_remaining==1 + 已征服 + 无PENDING
    │       → state.create_contract(PUBLIC_WORKS, province_id, budget, turn)
    │       → contract.name = "{province.name}工程"
    ├─ 新合同：
    │   └─ (已征服 或 province_id==0) + land_public>0 + 无非EXPIRED/COMPLETED
    │       → budget = int(land_value * infra_rate * (1 + budget_margin))
    │       → state.create_contract(PUBLIC_WORKS, province_id, budget, turn)
    └─ 舰队建造→ naval_system 委托（未修改）
```

### 3.2 关键文件
| 文件 | 路径 | 角色 |
|:-----|:-----|:-----|
| `forum_api.py` | `src/api/` | API 层入口（续约/新合同业务逻辑） |
| `phase_forum.py` | `src/ui/commands/` | CLI shell（仅打印） |
| `contract.py` | `src/core/entities/` | Contract 实体 + 生命周期（未修改） |
| `naval_system.py` | `src/core/systems/` | 舰队建造合同委托（未修改） |

### 3.3 预算权威值域（GUI-BETA-R1 WP-C-R1，ODR-ED-01）
- **config：** `economic_rules.senate_budget` → `public_works_min=1`（绝对 1T）/ `public_works_max_ratio=1.5`（max=base_cost×150%）/ `step=1`；default=base_cost（沿用现状）。
- **派生：** `senate_api._budget_range_for_contract(state, contract)` 产出 per-contract `{min, max, step, default}`；SenateStage FC-03 Slider from/to/stepSize/value 读 `budget_range`（config 缺 key → 禁用+「值域待定义」，不伪造 20-200）。
- **谓词：** `political_system._populate_proposal` budget 分支权威拒绝（非 int / <min / >max / step 不齐）；affordability 不拦截（提交期无国库限制，决算期破产链不变）。

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.3 | 2026-08-23 | GUI-BETA-R1 WP-E（Slice 11 PU-04）：`place_bid` 防重（E-G7-07）——同 (contract_id, figure_id) 已出价 → 显式拒绝「该人物已对本合同出价」（pending 恰一条，恰一次契约；双路反馈已存在） |
| v1.2 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 预算权威值域（senate_budget config + _budget_range_for_contract + _populate_proposal 谓词 + FC-03 Slider 改接） |
| v1.1 | 2026-07-25 | 新增工程合同生成调用链 + forum_api 引用 |
| v1.0 | 2026-07-12 | 初版 |
