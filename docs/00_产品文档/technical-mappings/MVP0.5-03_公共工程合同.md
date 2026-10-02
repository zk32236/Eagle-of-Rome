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

### 3.4 Fleet 建造合同四权威流（R3-G-03，2026-09-05）
```
political_system.execute_passed_proposal('budget')（Fleet 分支）：冻结 A=_original_budget、写 B=_approved_budget
  （即使未改金额）；base_cost 保持 B 投影；普通工程旧逻辑不变
→ forum_api.place_bid（Fleet：C=amount + 显式 construction_cost=D，8 元组 pending；admission 守卫
  C≤B / D≤C / D 非 bool 非负整数 / 新请求防重 / 显式 D 与显式 rate 冲突拒）
→ forum_api.resolve_forum（award 复检：按 pending faction_id 分组，不重放 current-player guard；
  失效候选过滤→最低价→平手；全失效 fail-closed 无 winner）
→ NavalSystem.on_contract_awarded：以最终 build_time 为唯一 N 同步 _construction_years/duration/
  remaining_years 与 annual C//N、D//N
→ EconomicService._settle_public_works_contract：Fleet 末期成本 D−(N−1)×annual_cost；payment 走既有
  C−total_spent 末期算法；C−D 毛利经既有 tax；普通工程/税零改
→ Contract.to_dict/from_dict：A/B/C/D + _target_war_id/_fleet_type/_build_time
```

### 3.5 基建统一为舰队式经济模型（WP-L L1，2026-10-02）
```
contract.py __post_init__：PUBLIC_WORKS（非 fleet）创建时 A=_original_budget 生成即设（base_cost 为基线）
post_init__ 另有 create_public_works() 显式 _original_budget=budget
→ forum_api.place_bid（PUBLIC_WORKS: fleet + 基建）：supports_d = PUBLIC_WORKS；显式 construction_cost=D
  校验（非 bool 非负整数 / D≤C / 显式 D 与显式 rate 冲突拒）；基建入队 8 元组
  (contract_id, figure_id, faction_id, amount, rate, construction, warranty, D)；ceiling=bid_ceiling()=B
  基建工期/质保由 D 驱动既有 cost-ratio 公式（quality=D/A）
→ political_system.execute_passed_proposal('budget')：PUBLIC_WORKS（非 fleet）分支写 B=_approved_budget
  （即使未改金额），A 冻结不被覆盖，base_cost=B 投影
→ forum_api.resolve_forum：基建 award 固化 _contract_price=C + _actual_cost=D（不重算）；
  warranty/construction 由 D/A 派生
→ EconomicService._settle_public_works_contract：基建末期成本尾差 D−(N−1)×annual_cost（D 已知时）
→ forum_api._pending_contract_rows：PUBLIC_WORKS 暴露 supports_construction_cost / baseline_construction_cost(A)
  / approved_budget(B) / bid_ceiling
→ ForumStage.qml：bidDialogSupportsD gating（经济块 + D 输入 ≥ PUBLIC_WORKS）；移除 equesBidOptions().length>0
```

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.5 | 2026-10-02 | WP-L L1：基建统一（A 生成即设 / B=PASS 写 / 显式 D 8 元组 / ceiling=B / quality=D/A / 成本尾差守恒）；无骑士非阻塞 UI（FC-L1-09/10） |
| v1.4 | 2026-09-05 | R3-G-03 同步：Fleet 四权威流（Senate B ceiling / A 不可重写 / 8-tuple 兼容 / 独立 AI rate / C-D 结算工期尾差，DA-R3-B3） |
| v1.3 | 2026-08-23 | GUI-BETA-R1 WP-E（Slice 11 PU-04）：`place_bid` 防重（E-G7-07）——同 (contract_id, figure_id) 已出价 → 显式拒绝「该人物已对本合同出价」（pending 恰一条，恰一次契约；双路反馈已存在） |
| v1.2 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 预算权威值域（senate_budget config + _budget_range_for_contract + _populate_proposal 谓词 + FC-03 Slider 改接） |
| v1.1 | 2026-07-25 | 新增工程合同生成调用链 + forum_api 引用 |
| v1.0 | 2026-07-12 | 初版 |
