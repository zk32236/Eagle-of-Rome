# MVP0.4-02 — 包税权合同系统（技术映射）

## 1. 代码目录
```
src/core/entities/contract.py         # Contract 实体
src/core/game_state.py                # 合同容器
src/core/service/economic_service.py  # 收入结算
src/ui/commands/func_contracts.py     # CLI 命令
src/api/contract_api.py               # API 层
```

## 2. 关键类
- `Contract` — 实体，状态: PENDING→BUDGETED→ACTIVE→COMPLETED/EXPIRED
- `ContractType` — TAX_FARMING / PUBLIC_WORKS / FLEET_CONSTRUCTION

## 3. 核心规则
竞标: 最高出价者中标（包税），最低出价者中标（工程）

## 4. 包税合同生成调用链（Wave-01 更新）

### 4.1 广场阶段续约 + 新合同
```
CLI phase_forum._generate_contracts()
  → forum_api.generate_contracts(state)        # [NEW] API 层入口
    ├─ 续约：遍历 state.contracts
    │   ├─ 包税 ACTIVE + remaining_years==1 + 已征服 + 无PENDING
    │   │   → state.create_contract(TAX_FARMING, ...)
    │   └─ 工程 COMPLETED + warranty_remaining==1 + 已征服 + 无PENDING
    │       → state.create_contract(PUBLIC_WORKS, ...)
    ├─ 新合同：遍历 state.get_all_provinces()
    │   ├─ 包税：已征服非意大利 + land_public>0 + 无ACTIVE/PENDING/BUDGETED
    │   └─ 工程：已征服或意大利 + land_public>0 + 无非EXPIRED/COMPLETED
    └─ 舰队建造→ naval_system.generate_construction_contracts()
```

### 4.2 关键文件
| 文件 | 路径 | 角色 |
|:-----|:-----|:-----|
| `forum_api.py` | `src/api/` | API 层入口（所有合同生成业务逻辑） |
| `phase_forum.py` | `src/ui/commands/` | CLI shell（仅打印） |
| `naval_system.py` | `src/core/systems/` | 舰队建造合同委托（未修改） |

### 4.3 预算权威值域（GUI-BETA-R1 WP-C-R1，ODR-ED-01）
- **config：** `economic_rules.senate_budget` → `tax_farming_min_ratio=0.75` / `tax_farming_max_ratio=2.0`（min=base_cost×75% / max=base_cost×200%）/ `step=1`；default=base_cost（沿用现状）。
- **派生：** `senate_api._budget_range_for_contract(state, contract)` 产出 per-contract `{min, max, step, default}`；SenateStage FC-03 Slider from/to/stepSize/value 读 `budget_range`。
- **谓词：** `political_system._populate_proposal` budget 分支权威拒绝（非 int / <min / >max / step 不齐）；affordability 不拦截。

## 5. WP-E-R3 viewer bid 与 Revenue ledger（2026-08-24）

- HUMAN/AI/CLI 继续汇入同一 `forum_api.place_bid`，新写保持 7 元组；winner 与合同状态机零改。
- `get_forum_view.viewer_contract_bids` 将 legacy 4/5/7 元组正规化为 `{contract_id, figure_id, amount, profit_rate, status}`，且只暴露 viewer 派系。
- HUMAN 必须显式选择 actor；pending 与 success/rejection 页内可见，refresh/re-entry 由 viewer DTO 恢复，不依赖 QML 本地成功标记。
- Revenue 的 ACTIVE 包税 `treasury_gain` 每合同恰一次进入 `accounting_window.treasury_ledger_rows`；人物 `net_profit` 与派系会员税标记为非国库 basis。

## 6. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.4 | 2026-08-24 | WP-E-R3：viewer-scoped normalized bid DTO、显式 actor/反馈、包税国库 ledger 来源 |
| v1.3 | 2026-08-23 | GUI-BETA-R1 WP-E（Slice 11 PU-04）：tax-farming 收入确定性证明映射（E-G7-12）——**零代码变更**；权威路径 = `src/core/service/economic_service.py` `collect_contract_revenues`（:247-270）仅对 ACTIVE 合同计收；确定性证据 = 三态回归测试（no-contract / active / expiry-removal）+ 证明矩阵（`03-da-evidence/runtime/wpe-eg7-12-taxfarming-proof-matrix-2026-08-23.md`）；同 state 重入 → 同 rows |
| v1.2 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 包税预算权威值域（senate_budget tax_farming 比率 + _budget_range_for_contract + _populate_proposal 谓词） |
| v1.1 | 2026-07-25 | 新增包税合同生成调用链 + forum_api 引用 |
| v1.0 | 2026-07-12 | 初版 |
