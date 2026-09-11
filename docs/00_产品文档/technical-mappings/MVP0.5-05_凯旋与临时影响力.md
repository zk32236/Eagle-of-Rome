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

## WP-G-R4 同步注记（2026-09-09，DA-R4-B3；append-only）

> 权威：SA-Design-WP-G-R4 v1.7（FROZEN）§4.3/§8.1 T10；对应规格 MVP0.5-05 §2.1/§3.1/§4.3 注记。
>
> - **Forum 公开 seams**：`get_forum_view`（triumph_wars 行：war_id/commander_id）→
>   `vote_triumph`（入口同源 `_triumph_eligibility`，alive 接受/dead/missing 拒绝零记录）→
>   `resolve_forum`（settlement：支持率>0.5 批准 + soldier_share 归零；二次 resolve 无二次奖励）。
> - **候选字段含义**：`war.triumph_commander_id` = ceremony candidate（非 CRT 身份证据）；
>   CRT identity（combat_victory/combat_triumph）由 combat envelope/event 独立携带，不从候选反推。
> - 版本行：| v1.1 | 2026-09-09 | WP-G-R4 B3：Forum 公开 seams/候选字段/CRT identity 与 ceremony 分离（DA-R4-B3） |
