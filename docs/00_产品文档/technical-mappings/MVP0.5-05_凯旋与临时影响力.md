# MVP0.5-05 — 凯旋与临时影响力 Technical Mapping

## 1. 代码目录
```
src/core/deciders/triumph_decider.py, impl/auto_triumph_decider.py
src/core/entities/figure.py       # add_temp_influence_task()
src/ui/commands/phase_forum.py    # 投票环节
src/ui/commands/phase_population.py # 凯旋执行
src/api/forum_api.py              # vote_triumph(), resolve_forum()
```

## 2. 关键方法
- `resolve_forum()` — 凯旋结算
- `add_temp_influence_task()` — 添加临时影响力
- `_process_legion_disbandment_and_triumphs()` — 人口阶段执行

## 3. 版本日志 | v1.0 | 2026-07-12 | 初版 |
