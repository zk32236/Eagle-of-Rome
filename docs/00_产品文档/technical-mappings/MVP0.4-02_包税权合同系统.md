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

## 5. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-07-25 | 新增包税合同生成调用链 + forum_api 引用 |
| v1.0 | 2026-07-12 | 初版 |
