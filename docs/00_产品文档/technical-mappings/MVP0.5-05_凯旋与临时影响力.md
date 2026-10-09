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

## WP-J Group B 同步注记（2026-10-06，DA-Execute；append-only）

> 权威：WP-J Group B SA-Development-Task v1.3（G3 FROZEN）§3.3/§4/§5.1；Owner 2026-10-06 16:43 S-2 最小规则。

- **链路（③ J-AC-03，additive 只读）**：`forum_api.get_forum_view()` → `_triumph_war_rows()`（逐行增 `action:{state,reason}` + `viewer_vote`，FC-B01–B03/B18）→ `session_store.forumTriumphWars`（只读透传，零本地缓存）→ `ForumStage.qml` 凯旋行 `MarketActionRow`（`enabledAction = action.state=="actionable" && viewer_vote===null`；文本 = `viewer_vote!=null?「已投」:(actionable?「赞成」:「不可投」）`）→ `onTriggered` 复用既有 `session_store.doVoteTriumph(war_id, true)`。
- **最小交互提交链（不变）**：单击「赞成」→ `forum_api.vote_triumph(state, player_id, war_id, True)` → `add_forum_action("triumph_votes", (war_id, faction_id, True))`（bool + append 语义**零改**）→ 刷新后行呈「已投」 disabled（重复点击无效）。
- **单一谓词**：`action.state=="actionable"` iff 权威 `vote_triumph` 在当前态会接受（`_check_player_permission` ∧ `_triumph_eligibility`）∧ 市场子环节窗口开放 ∧ ¬resolved；`reason` 词表 {ok,not_current_player,not_phase,vote_window_closed,resolved} 保留于 DTO、界面不呈现（Owner 16:43）。QML/Store 不得重算（FC-B06）。Q1 = CLOSED（Owner 16:07，不新增窗口强校验）。

## WP-J Group D 同步注记（2026-10-09，DA-Execute；append-only）

> 权威：WP-J Group D SA-Development-Task v1.1（G3 FROZEN）§5.1–§5.2/§9.2；对应规格 MVP0.5-05 §2.5 注记。

- **人口侧链路（J-AC-04a，additive 只读）**：`state.get_phase_result("population_disbandment")`（`war_system.process_triumph_and_disbandment().triumphs` + `legions` + `naval_system.disband_unused_fleets().fleets`）→ `session_api.get_population_view().population_outcome`（FC-D01/FC-D02，shape `{triumphs, legions{resolved_wars.total, deescalated.total}, fleets}`）→ `session_store.populationOutcome`（只读透传，零缓存）→ `PopulationStage.qml` **既有 `populationAnnouncement` 框内**追加行（凯旋仪式已举行 / 战后军团·停战降级军团·闲置舰队计数）。
- **否决呈现撤销**：`resolve_forum()` **不**新增 `triumph_outcomes`（v1.0 additive 撤销）；写语义 = Group B 冻结原样。
- **零业务重建**：QML/Store 逐字消费权威值，无重算（FC-D08）。

### WP-J Group D 版本日志（append-only）

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.3 | 2026-10-09 | DA-Execute (WP-J Group D) | 人口公示框内战后反馈行读取链路（`population_outcome` → `populationOutcome` → QML 既有框内追加；additive 只读）+ 否决呈现撤销（`resolve_forum()` 零改） |

## 版本日志（append-only）

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-10-06 | DA Sub-Agent (WP-J Group B) | ③ 行 action/viewer_vote 读取链路 + 最小交互提交链（WP-J Group B / J-AC-03；additive read-model，写语义零改） |
