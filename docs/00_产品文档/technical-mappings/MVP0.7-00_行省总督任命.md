# MVP0.7-00 — 行省总督任命（技术映射）

## 1. 代码目录
```
src/core/entities/province.py         # 总督字段+交接方法
src/core/systems/political_system.py  # 资格校验+提案执行
src/ui/commands/phase_senate.py       # 提名UI + AI自动提名
```

## 2. 关键方法
- `get_eligible_governor_candidates()` — 资格校验
- `set_governor_designate()` — 设置候任总督
- `complete_governor_transition()` — 决算阶段交接

## 4. 已知差异（2026-07-26）

| 维度 | 产品文档描述 | 代码当前行为 |
|:-----|:------------|:-------------|
| 任命方式 | 玩家提名 → 元老院提案 → 投票 → 通过后上任（§2.3/§3.1） | `senate_api.assign_governors()` (L969) 自动匹配候选人 → 直接 `set_governor_designate()`，**跳过提案和投票流程** |
| AI 行为 | 通过生成提案走投票流程 | 直接调用自动分配函数，不走提案流程 |

**处理决定（Owner 2026-07-26）：** 保留当前自动分配功能。代码与文档的差异已记录为遗留问题，待后续统一修复。

## 5. 版本日志
| 版本 | 日期 | 摘要 |
| v1.1 | 2026-07-26 | 补充已知差异（代码自动分配 vs 文档提案流程） |
| v1.0 | 2026-07-12 | 初版 |
