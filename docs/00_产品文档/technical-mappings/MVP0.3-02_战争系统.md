# MVP0.3-02 — 战争系统（技术映射）

## 1. 代码目录
```
src/core/systems/war_system.py, naval_system.py
src/core/entities/war.py, legion.py
src/core/deciders/peace_treaty_decider.py, impl/auto_peace_treaty_decider.py
src/ui/commands/phase_combat.py
```

## 2. 关键模块
- `war_system.py` — 战争激活、结算、指派、停战、惩罚
- `war.py` — War 实体 + WarStatus/WarType 枚举
- `phase_combat.py` — 战斗阶段命令 + CRT + 草案生成

## 3. 核心算法
CRT 判定: combat_total = 2d6 + commander.martial + sum(legion_strengths) - war.strength
结果: DISASTER / TRIUMPH / VICTORY / STALEMATE / DEFEAT

## 4. Wave-03 新增方法

### 4.1 `assign_rebellion_commanders() -> list[dict]`
- **用途：** 为所有活跃起义指派指挥官（C-10b）
- **CLI 来源：** `phase_senate.py` L1348-1408
- **返回：** `[{rebellion_id, commander_id, name, assigned_at}]`
- **日志：** DBUG（每起义/每选择）+ INFO（指派）

### 4.2 `auto_recruit_and_assign() -> list[dict]`
- **用途：** 自动征召军团并指派至战区（C-10d）
- **CLI 来源：** `phase_senate.py` L1642-1708
- **返回：** `[{legion_id, legion_name, assigned_to, assigned_at}]`
- **日志：** DBUG（需求评估/征召）+ INFO（指派结果）

## 5. Wave-04 Finale 新增方法

### 5.1 `process_triumph_and_disbandment() -> dict`
- **用途：** 人口阶段结束后处理军团解散与凯旋式（C-E1）
- **CLI 来源：** `phase_population.py` ~L514-565
- **逻辑：**
  1. 遍历所有活跃战争
  2. 对胜利战争：触发凯旋式（增加 commander 人气/影响力）
  3. 对所有战争：解散多余军团（保留 minimum_garrison）
- **返回：** `{triumphs: [{war_id, commander_id, popularity_gain, influence_gain}], disbandments: [{legion_id, reason}], summary: str}`
- **日志：** DBUG（凯旋条件/解散决策）+ INFO（执行结果）

## WP-G-R4 同步注记（2026-09-09，DA-R4-B3；append-only）

> 权威：SA-Design-WP-G-R4 v1.7（FROZEN）§2/§4/§5；对应规格 MVP0.3-02 §2.3/§2.7/§3.2 注记。
>
> - **resolve_war 兼容参数/unknown 边界**：`resolve_war(war_id, victory, *, combat_result=None)`；
>   显式非 victory/triumph 或与 victory=False 矛盾 → ValueError 零 mutation；legacy bool-only 成功
>   → `combat_result=None/result_identity_source=legacy_unspecified/resolution_kind=successful_war_resolution`
>   + 中性 `war_resolved` 事件（不伪造 combat_triumph/victory）。
> - **DTO persistence/Store/CombatStage/event 链（引用规格 MVP0.7-04 §2.2 R4 注记 schema §5）**：
>   ATTACK v2 envelope → `_persist_combat_envelope`（pending_result + war_results[id] deepcopy，
>   battled 恰一次）→ get_combat_view battle_results/war cards → Store
>   combatBattleResultDetail/combatResolvedWarCards 透传 → CombatStage resultBox 与
>   WarCard.cardResult 共用同一 stage renderer（naval/land 并列 executed；未执行固定文案/无
>   ||0 fallback/缺失→未记录）；`combat_action_resolved` summary event（turn/phase/war_id/
>   action_status/naval/land/outcome/schema_version）。

## 6. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.5 | 2026-09-09 | WP-G-R4 B3：resolve_war 显式 combat_result/legacy unknown 边界 + v2 DTO persistence→Store→CombatStage 两结果区消费链 + summary event（DA-R4-B3） |
| v1.4 | 2026-08-29 | WP-F 003（S1-7）：`_war_card` 增 `commander_faction_id`（commander.faction_id，无指挥官 → None）；CombatStage 指挥官 label 经 FactionStyle 着色 |
| v1.3 | 2026-08-23 | GUI-BETA-R1 WP-E（Slice 11 PU-04）：①TRUCE 剩余回合 DTO（combat_api.py `_war_card` 新增 `truce_end_turn` / `truce_remaining_turns` 权威计算）；②`_forum_war_events` 保留载体（forum_api.py `initialize_forum_turn` 写入 war_events，`get_forum_view` 暴露 `war_events` / `has_active_war`=ws.get_active_wars() 权威）；③TRUCE 卡军团投影边界（展示=实体镜像；实体错 → WP-G traceability 移交，禁 QML 掩盖） |
| v1.2 | 2026-07-26 | 追加 process_triumph_and_disbandment() 方法（Wave-04 Finale, C-E1） |
| v1.1 | 2026-07-26 | 追加 assign_rebellion_commanders() + auto_recruit_and_assign() 方法（Wave-03） |
| v1.0 | 2026-07-12 | 初版 |
## WP-O 同步注记（2026-09-27，DA-Execute WP-O/O-S3；append-only）

> 权威：SA-Design WP-O v1.0（`075f873b…`）§B1/§B2；规格 `specifications/MVP0.3-02_战争系统.md` §「WP-O 同步注记」。

### 写侧 owner（唯一权威）
| 事实 | owner 文件 | 方法 |
|:--|:--|:--|
| 现任指挥官解绑 + `killed` + 返回指针 | `core/systems/war_system.py` | `clear_deceased_commander_bindings(member_id)`（经 `get_all_wars()`，**精确 id**；仅真实存在且已死的 Figure，缺失/存活 = no-op） |
| Legion 人物镜像清理 | `core/systems/military_system.py` | `clear_deceased_commander_bindings(member_id)`（窄，仅匹配死者） |
| Fleet 人物镜像清理 | `core/systems/naval_system.py` | `clear_deceased_commander_bindings(member_id)`（窄，仅匹配死者） |
| 死亡写点接线 | `core/game_state.py` | `mark_member_dead` 实际死亡后、成功返回前调用 WarSystem owner（缺失系统 = 合法 no-op） |
| 显式重绑复位 | `core/systems/war_system.py` / `political_system.py` | 成功 command 绑定存活 → `reset_commander_status_to_active()` |

### 读侧消费者（现任经 living 谓词 `GameState.get_living_member`）
`war_system.py`（describe_senate_war / get_war_by_commander(F-03) / get_active_wars_without_commander / get_wars_needing_reassignment）· `political_system.py`（_current_command_war_ids / build_war_card_views / build_commander_claims 保留支 / build_war_resolution_plan c0）· `api/combat_api.py`（_war_card / _compute_combat_result / _actionable_wars / auto_resolve 分区）· `api/gui_query_api.py`（_war_summary）· `api/senate_api.py`（auto_propose_all）· `core/game_state.py`（build_submission_context）· `ui/commands/func_military.py`。

### 回滚
`GameState.snapshot_war_resolution_domains` / `restore_war_resolution_domains` **additive** 捕获 `War.commander_status`（失败 Senate 命令回滚恢复 `killed`，与 null current/镜像同版）。

### 版本日志
| 版本 | 日期 | 摘要 |
|:--|:--|:--|
| v1.6 | 2026-09-27 | WP-O O-S3：非战斗死亡解绑写侧 owner + 读侧消费者表 + 回滚 additive `commander_status`（DA-Execute） |

## WP-J Group A R1 同步注记（2026-10-06，DA-Execute WP-J R1；append-only）

> 权威：SA-Development-Task-WP-J-GroupA-R1 v3.2（R1b，FROZEN）；对应规格 MVP0.3-02 R1 注记 + MVP0.3-01 R1 注记。

- **战斗步骤条读模型（镜像源 = 战争系统）**：`api/combat_api.py::get_combat_view` 的 `steps` 由固定 4 步改为
  **可执行战争「占位→实名」进度**：槽数 `max(3, N)`；`N = len(resolved_wars) + len(_actionable_wars) +
  len(无存活指挥官且 ∉ resolved_wars 的 active 战争)`（含 `_skip_all_unassigned` auto-skip；N>3 不封顶，
  镜像 `_build_war_slots`）；槽 k≤N 处理前 `「可执行战争k」`→处理后 `war name`（`resolved_wars[k-1]`，
  与 `_persist_combat_envelope` 追加序同源）；`current` = 最低序 todo；无 advance。
- **零写边界变更**：`select_war` / `do_combat_action` / `advance_combat` / `_skip_all_unassigned` / `_build_war_slots`
  行为不变；`war_slots` / `resolved_wars` / `war_results` DTO 不变。

### 版本日志（R1）
| 版本 | 日期 | 摘要 |
|:--|:--|:--|
| v1.7 | 2026-10-06 | WP-J Group A R1：combat `steps` = `max(3,N)` 可执行战争占位→实名进度（只读派生；与 `resolved_wars`/`_actionable_wars` 同源） |

## WP-K S1 同步注记（2026-10-11，DA-Execute WP-K S1；append-only，目标锚点 §3 核心算法）

> 权威：SA-Development-Task-WP-K-v1.4（FC-K-01…09）；对应规格 `specifications/MVP0.3-02_战争系统.md` §3.3/§3.5。

- **AI 军团增援 N 生产（单一 owner）**：`src/api/senate_api.py::reinforcement_n_target(state, war, remaining, pool)`——
  `N = clamp((E+u−1)//u, 1, min(remaining, pool))`；`pool==0 → 0`；`remaining<1 → 0`；
  敌强源不可读 → 返回 `None`（调用方跳过该战）。调用点 = `auto_submit_proposals` 4b′（consul_direct command）。
- **输入键**：`war.get_total_strength()`（`war.py`，陆战敌强）；`economic_rules.legion_strength_base`
  （`game_config.json` + `config.py DEFAULTS`，默认 2）。确定性（无 `random`）。
- **不变**：`reinforcement_range`（值域）/ `_validate_reinforcement_n`（fail-closed）/ 4a 宣战军团数
  （`senate_war_legions`）/ `commit_war_resolution` 唯一原子军事执行。

### 版本日志（S1）
| 版本 | 日期 | 摘要 |
|:--|:--|:--|
| v1.8 | 2026-10-11 | WP-K S1：AI 军团增援 N 敌强匹配（`reinforcement_n_target`；去 random）；键 `legion_strength_base` |
