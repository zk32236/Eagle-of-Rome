# MVP0.5-10 — 土地法案（技术映射）

## 1. 代码目录
```
src/core/deciders/land_proposal_decider.py, impl/auto_land_proposal_decider.py
src/core/systems/political_system.py  # execute_passed_proposal()
src/api/forum_api.py                  # execute_land_acts() — 土地分配API (Wave-02)
src/api/senate_api.py                 # auto_submit_proposals() — 土地法案提交 (Wave-02)
src/ui/commands/phase_forum.py        # → 委托 forum_api.execute_land_acts() (Wave-02)
src/ui/commands/phase_senate.py       # → 委托 senate_api (Wave-02)
```

## 2. 关键方法
- `auto_land_proposal_decider.decide_proposal()` — 自动提案
- `execute_passed_proposal()` — 执行法案（设置配额/追加pending）

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-07-26 | 土地分配 CLI→API 下沉：新增 forum_api.execute_land_acts() + senate_api 法案提交 |
| v1.0 | 2026-07-13 | 初版 |
