# MVP0.4-03-sys — 核心数据系统 审计报告

> **审计目标：** 验证 Spec 和 Technical Mapping 文档与实际代码的一致性、准确性和完整性
> **审计日期：** 2026-07-14
> **审计基准代码：** MVP 0.7.x 分支
> **审计范围：** Spec + Mapping vs 源代码

---

## 1. 事实性错误（🔴 严重）

### 1.1 Mapping 中 figure.py 文件大小和行号全面失准

| 项目 | Mapping 声称 | 实际代码 | 偏差 |
|------|-------------|---------|------|
| 文件大小 | "图 1-254 行" | **660 行** | 全文件约 2.6 倍于声称 |
| `_land_private` 声明 | 第 104–109 行 | 第 192 行 | 偏差约 85 行 |
| `update_influence()` | 第 162–194 行 | 第 229–254 行 | 偏差约 65 行 |
| `__post_init__` | 第 195 行 | 第 256 行 | 偏差 61 行 |
| 临时影响力方法 | 第 152–160 行 | 第 207–221 行 | 偏差约 55 行 |
| `add_wealth()` / `add_popularity()` | 第 222–227 行 | 第 385–389 行 | 偏差约 163 行 |
| `can_sell_land()` / `sell_land()` | 第 241–251 行 | 第 415–437 行 | 偏差约 174 行 |
| `get_office_influence_bonus()` | 第 362–377 行 | 第 622–629 行 | 偏差约 260 行 |
| `load_config()` | 第 380–391 行 | 第 631–641 行 | 偏差约 251 行 |
| MVP 0.5 属性访问器 | 第 394–413 行 | 第 643–660 行 | 偏差约 249 行 |

- **严重程度：** 🔴 严重
- **影响：** 所有行号引用均不可用；开发人员在代码审查或故障排查时无法信任文档中的行号
- **修复建议：** 对整个 Mapping 的 "关键模块与文件" 节进行全面行号重新索引。每次代码更新后需同步更新。

---

### 1.2 Mapping 中 game_state.py 文件大小失准

| 项目 | Mapping 声称 | 实际代码 | 偏差 |
|------|-------------|---------|------|
| 文件大小 | "全文件约 550 行" | **1415 行** | 实际 2.57 倍 |
| `_treasury` / `_national_public_land` | 第 74–77 行 | 第 48–49 行（`__init__` 内） | 偏差约 25 行 |
| `add_figure_wealth()` | 第 228–246 行 | 第 707–724 行 | 偏差约 480 行 |
| `add_faction_treasury()` | 第 248–264 行 | 第 744–757 行 | 偏差约 496 行 |
| `treasury` property + setter | 第 269–282 行 | 第 774–784 行 | 偏差约 505 行 |
| `add_national_public_land()` | 第 284–287 行 | 第 787–790 行 | 偏差约 503 行 |
| `sync_italy_public_land()` | 第 284–287 行（合并呈现） | 第 1284 行 | 偏差约 1000 行 |
| `mark_member_dead()` | 第 354–394 行 | 第 958–1000 行 | 偏差约 604 行 |
| `add_pending_land_act()` | 第 341–346 行 | 第 1119–1126 行 | 偏差约 778 行 |
| `pending_land_sale_quota` | 第 396–398 行 | 第 1010–1023 行 | 偏差约 614 行 |
| `_pending_land_acts` 声明 | 第 88–93 行 | 第 70 行（`__init__` 内） | 偏差约 18 行 |
| `_public_land_total` | 第 85 行 | 第 67 行（`__init__` 内） | 偏差约 18 行 |

- **严重程度：** 🔴 严重
- **影响：** game_state.py 自 Mapping 初始编写后经历了大量扩展（战争系统、天命系统、玩家系统、城市系统等）；所有行号引用彻底失效
- **修复建议：** 全面重索引 game_state.py 部分；考虑拆分行号引用为方法签名而非具体行号

---

### 1.3 Mapping 中 economic_service.py 文件大小失准

| 项目 | Mapping 声称 | 实际代码 | 偏差 |
|------|-------------|---------|------|
| 文件大小 | "全文件约 280 行" | **486 行** | 实际 1.74 倍 |
| `settle_revenue_phase()` | 第 18–88 行 | 第 17–67 行 | 偏差约 1 行（较接近） |
| `deduct_national_opex()` | 第 114–159 行 | 第 129–157 行 | 偏差约 15 行 |
| `collect_public_land_income()` | 第 161–192 行 | 第 159–193 行 | 偏差约 2 行（较接近） |
| `collect_private_land_income()` | 第 194–238 行 | 第 195–235 行 | 偏差约 1 行（较接近） |
| `collect_contract_revenues()` | 第 240–266 行 | 第 237–260 行 | 偏差约 3 行（较接近） |

- **严重程度：** 🔴 严重
- **影响：** 整体行号严重低估，但 EconomicService 的核心方法行号偏差较小，部分方法较准确
- **修复建议：** 更新文件大小描述和全部行号；新增方法（`_settle_tax_farming_contract`、`_settle_public_works_contract`、`process_contract_warranty` 等）需补充

---

### 1.4 Mapping 中 political_system.py 文件大小失准

| 项目 | Mapping 声称 | 实际代码 | 偏差 |
|------|-------------|---------|------|
| 文件大小 | "全文件约 380 行" | **789 行** | 实际 2.08 倍 |

- **严重程度：** 🔴 严重
- **影响：** 严重低估；Mapping 中未提供具体行号引用，但文件大小描述严重误导
- **修复建议：** 更新为 789 行；考虑补全具体方法行号

---

### 1.5 Mapping 中 entities.py 的行号引用全面失准

**Faction 类：**
| Mapping 声称 | 实际代码 |
|-------------|---------|
| "第 60–168 行：Faction 类" | `@dataclass class Faction` 约在 78 行；`to_dict()` 在第 85 行；`get_senate_influence()` 在第 111 行|
| "第 136–145 行：`get_senate_influence()`" | 实际第 111 行 |
| "第 97–108 行：`to_dict() / from_dict()`" | 实际第 85–109 行 |
| "第 116–122 行：`get_total_influence()`" | 实际第 132 行 |
| "第 155–162 行：`get_leader() / update_faction_leader()`" | 实际第 153–173 行（跨度更大） |
| "第 169–189 行：MVP 0.5 新增——`update_total_land()`" | 实际第 178–207 行 |
| "第 192–207 行：`total_land` / `province_owned` / `knight_contract_count`" | 实际第 209–220 行 |

**Province 类（entities.py 内过渡定义）：**
| Mapping 声称 | 实际代码 |
|-------------|---------|
| "第 214–282 行：Province 类" | 实际从约 270 行到 **553 行**（类定义 + 全部属性和方法） |
| "第 243–249 行：land_public / land_private 初始化" | 实际第 300–308 行 |
| "第 332–336 行：`update_land_type()`" | 实际第 455–458 行 |
| "第 244–248 行：可见 `_land_public`、`_land_private` 字段" | 实际第 359–363 行 |

- **严重程度：** 🔴 严重
- **影响：** 所有 entities.py 行号引用失效
- **修复建议：** 全面重索引

---

## 2. 遗漏/缺失（🟡 中等 / 🔵 轻微）

### 2.1 🟡 Spec 公式符号精确度

- **位置：** Spec §6 AC-05
- **问题：** Spec 描述的公式为 `int(1000 * 10 * 0.01 * 0.02) = 2`
- **实际代码：** `economic_service.py:167` 使用 `int(round(...))` 而非 `int(...)`
- **影响：** 当前值因结果恰好为整数（2.0）而不产生差异，但若配置值改变可能造成计算结果不一致
- **修复建议：** Spec 公式更新为 `int(round(1000 × 10 × 0.01 × 0.02)) = 2`，或加注释说明使用 `int(round())`

### 2.2 🟡 AC-05 与 AC-07 测试引用冲突

- **位置：** Spec §6 AC-05 和 AC-07
- **问题：** AC-05 和 AC-07 均引用 `test_phase_revenue.py::test_national_opex_deduction` 作为测试文件。该函数主要测试国家运营费（AC-07），其中国家公地收益（AC-05）仅作为积分结算的副产物出现
- **实际：** 针对私地收益、运营费的单元测试位于 `test_economic_service.py`；整体结算测试在 `test_phase_revenue.py`
- **修复建议：**
  - AC-05 应指向 `test_economic_service.py::test_collect_public_land_income`（若存在）或 `test_phase_revenue.py::test_national_opex_deduction` + 说明公地收益是其中一部分
  - AC-07 应指向 `test_economic_service.py::test_deduct_national_opex_uses_conquered_provinces_only` 作为单元测试 + `test_phase_revenue.py::test_national_opex_deduction` 作为集成测试

### 2.3 🟡 AC-07 运营费测试值不匹配

- **位置：** Spec §6 AC-07 条件部分
- **问题：** AC-07 条件说"两个已征服行省各 total_land=1000/2000"并预期 `opex=90`
- **实际代码：** `test_economic_service.py::test_deduct_national_opex_uses_conquered_provinces_only` 使用**1个**已征服行省（total_land=1000），预期 **opex=30**（`data["amount"] == 30`）
- **两者关系：** Spec 描述的是集成测试条件（RevenueCommand），但引用的测试是经济服务的单元测试，两者不符
- **修复建议：** 明确区分：AC-07 单元测试为 `economic_service.py`（opex=30），集成验证在 `test_phase_revenue.py::test_national_opex_deduction`（opex=90）

### 2.4 🟡 economy_sys.py 为空文件

- **位置：** Spec §1.3、§4.2 和 Mapping §1
- **问题：** `src/core/systems/economy_sys.py` 为 **0 行空文件**，但 Spec 在"系统定位"和"输出依赖"中将其列为经济系统
- **实际：** 所有结算逻辑已迁移至 `EconomicService`（`service/economic_service.py`），`economy_sys.py` 为历史遗留空壳
- **修复建议：**
  - Spec §4.2 "输出依赖"中应将 `EconomicService` 列为消费方，而非 `economy_sys.py`
  - Mapping §1 代码目录中应标注 `economy_sys.py` 状态为"已废弃/空壳"

### 2.5 🔵 AC-10 测试文件映射不完整

- **位置：** Spec §6 AC-10
- **问题：** AC-10 预期 `faction.get_senate_influence(state) == 100`，测试映射为 `test_phase_senate.py`
- **实际：** `test_phase_senate.py` 主要测试元老院提案流程，并未提供直接针对 `get_senate_influence()` 的独立单元测试
- **修复建议：** 在 `test_entities.py` 中补充 `get_senate_influence()` 单元测试，或调整 AC-10 的测试映射说明

### 2.6 🔵 `_update_global_public_land()` 未在文档中提及

- **位置：** Mapping §5.1 数据结构中未包含 `_public_land_total` 的更新机制
- **问题：** `GameState._public_land_total` 由私有方法 `_update_global_public_land()` 维护（遍历行省注册表），在线路"添加行省→更新全局公地总数"中起关键作用
- **实际：** 该方法和 `_public_land_total` 间的依赖关系在 Mapping 中完全缺失
- **修复建议：** 在 Mapping §5.1 中对 `_public_land_total` 增加说明其更新机制

### 2.7 🔵 `add_member()` 方法提及

- **位置：** Mapping §4.1 中未列出 `Figure.add_member()`（实际在 figure.py 第 224 行）
- **注意：** 该方法在 `Figure` 类中注册 `_state`，用于影响力变化日志
- **修复建议：** 可在相关调用链中补充说明

---

## 3. 表述准确度（🔵 轻微 / 🟡 中等）

### 3.1 🟡 Spec 4.2 中 "proposal" 拼写错误

- **位置：** Spec §4.2（输出依赖），元老院提案行
- **问题：** `proposal` 拼写为 `proposal`（少了一个 `s`）
- **原文：** `preposal中的budget/land_act`
- **修复建议：** 修正为 `proposal`

### 3.2 🟡 Mapping §4.2 运营费测试代码路径与真实代码不符

- **位置：** Mapping §7.2（运营费测试）
- **问题：** 代码路径显示：
  ```
  assert data["amount"] == 30  # 1000 * 10 * 0.003
  assert state.treasury == 970
  ```
  但 Mapping 说该测试与 Spec AC-07 对应（AC-07 期望 opex=90），实际上此代码对应的是 `test_economic_service.py::test_deduct_national_opex_uses_conquered_provinces_only`（1个行省，opex=30）
- **修复建议：** 在 Mapping 中标注此代码路径来自单元测试（1 province），并补充集成测试代码路径

### 3.3 🔵 entities.py 中 Province 注释与实际不符

- **位置：** Mapping §2.2 / §3 和 entities.py 源代码
- **问题：** entities.py 第 270 行注释 `⚠️注意：此类定义已废弃，请勿在此添加新功能！` 和 "行省实体的正式定义位于 src/core/entities/province.py 中"
- **实际：** `province.py` 确实存在（392 行），但同时 entities.py 中的 Province 类仍在使用，两个文件中的 Province 类是**独立的两个类**（不存在继承关系）
- **修复建议：** 在 Mapping 和 Spec 中澄清两个 Province 类的关系，说明目前在使用的到底是哪个

### 3.4 🔵 Spec §3.3 中公地收益公式表述

- **位置：** Spec §3.3 最末行
- **问题：** 公地收益公式为 `public_land_income_rate × national_public_land_tax_rate × land_price × national_land`
- **实际代码：** `economic_service.py:160-167` 使用 `int(round(national_land * land_price * public_income_rate * national_tax_rate))`，乘法顺序不影响结果但文档顺序为 `rate × tax_rate × price × land` 与代码的 `land × price × rate × tax_rate` 顺序不同
- **修复建议：** 统一公式表述顺序；不需要改变数值结果，但保持一致性更好

### 3.5 🔵 Figure 的 `add_member` 方法

- **位置：** Mapping §3 关键类表格
- **问题：** `Figure` 类的核心属性表中未包含 `_state` 字段（第 196 行 `_state = None`），该字段用于影响力日志记录

---

## 4. 文档结构（🔵 轻微）

### 4.1 ✅ 整体结构符合要求

Spec 和 Mapping 的大体结构符合 README.md 定义的三层映射规范：
- Spec 覆盖功能目的、行为、核心规则、输入输出、状态边界、验收标准 ✓
- Mapping 覆盖代码目录、关键模块、关键类、关键函数、数据结构、调用关系、测试映射 ✓
- 两者通过 §8/§9 交叉引用链接 ✓

### 4.2 🔵 Mapping 中测试映射的格式不一致

- **位置：** Mapping §7.1
- **问题：** 单元测试表的 `覆盖点` 列包含行号引用（如 L24-30、L32-39），但未标注这些行号属于哪个文件版本。当前行号严重过时
- **修复建议：** 移除行号引用，或添加 git commit hash 作为锚点

### 4.3 🔵 Mapping 4.x 关键函数表格的行号引用不准确

- **位置：** Mapping §4.1, 4.2, 4.3 全部行号列
- **问题：** 如 `update_influence()` 标注为 `figure.py:162-194` 实际为 `figure.py:229-254`，函数签名的正确性（参数类型、返回值）是准确的，但行号不可靠
- **修复建议：** 
  - 短期：将行号标记为草稿状态（加 `*` 后缀）
  - 中期：重构为按方法签名定位，移除行号依赖

---

## 5. 完整性检查（🟡 中等）

### 5.1 🟡 测试覆盖缺口

以下验收标准在 Mapping 中缺少明确的测试映射：

| 验收标准 | 内容 | 现状 |
|---------|------|------|
| AC-09 | 死亡资产回收 | 映射缺失；`mark_member_dead()` 测试在 `test_game_state.py` 中（Mapping 已列出但无直接映射） |
| AC-10 | 派系元老院影响力汇总 | `test_phase_senate.py` 间接覆盖，但无直接断言 |
| AC-11 | 土地交易后影响力自动更新 | Mapping 中标注为 "代码路径确认" 而非 "测试验证" |
| AC-12 | 零持续时间临时任务 | Mapping 中缺失 |
| AC-13 | 公/私地初始化比例 | 映射正确指向 `test_entities.py::test_ent_001_province_creation` ✓ |

- **修复建议：** 为 AC-09, AC-10, AC-11, AC-12 补充单元测试或在 Mapping 中说明为何无需单独测试

### 5.2 🔵 xref 链接确认

- Spec §8 → Mapping：✅ 有效
- Mapping §8 → Spec：✅ 有效
- 版本日志格式：✅ 符合要求

---

## 6. 总结

### 🔴 必须立即修复（高优先级）

| # | 类型 | 位置 | 问题 | 修复方式 |
|---|------|------|------|---------|
| 1 | 事实性错误 | Mapping §2.1 | 所有 figure.py 行号全面失准 | 完全重索引行号 |
| 2 | 事实性错误 | Mapping §2.3 | game_state.py 行号全面失准 | 完全重索引行号 |
| 3 | 事实性错误 | Mapping §2.4 | economic_service.py 行号失准 | 更新行号和方法清单 |
| 4 | 事实性错误 | Mapping §2.6 | political_system.py 行号失准 | 更新行号和方法清单 |
| 5 | 事实性错误 | Mapping §2.2 | entities.py 行号全面失准 | 完全重索引行号 |

### 🟡 建议修复（中等优先级）

| # | 类型 | 位置 | 问题 |
|---|------|------|------|
| 6 | 遗漏 | Spec §6 AC-05 | 公式应明确为 `int(round(...))` |
| 7 | 遗漏 | Spec §6 AC-05/07 | 测试引用冲突，AC-05 和 AC-07 引用同一函数 |
| 8 | 遗漏 | Spec §1/4 | economy_sys.py 为空文件，文档需更新 |
| 9 | 表述 | Mapping §7.2 | 运营费测试代码路径不匹配 |

### 🔵 建议修复（低优先级）

| # | 类型 | 位置 | 问题 |
|---|------|------|------|
| 10 | 表述 | Spec §4.2 | `proposal` 拼写错误 |
| 11 | 遗漏 | Mapping §5.1 | `_update_global_public_land()` 未提及 |
| 12 | 结构 | Mapping §7.1 | 测试映射中的行号引用需移除或标注版本 |
| 13 | 表述 | Spec §3.3 | 公地收益公式乘法顺序不一致 |
| 14 | 完整性 | Mapping §3 | `Figure._state` 字段缺失 |

---

*审计结束。总计：5 个 🔴 严重问题，4 个 🟡 中等问题，5 个 🔵 轻微问题。*
