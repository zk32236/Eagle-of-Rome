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

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-07-26 | 新增 auto_vote() 方法（Wave-04 Finale, C-10e） |
| v1.0 | 2026-07-26 | 初版 — Wave-03 senate_api assign_governors + process_war_takeover |
