# MVP0.4-05-sys — GameState状态管理 Technical Mapping

> **功能简述：** 全局游戏状态单例管理

## 1. 代码目录
待代码审计。

## 2. 关键模块
- `src/core/game_state.py` — 全局游戏状态单例；`_forum_pending` 持久化字典（含 `forum_initialized` canonical init 守卫 key，2026-08-21 WP-C 新增，复刻 `market_opened`；`clear_forum_pending` L482 全 key 跨回合重置；`to_dict`/`load_from_dict` 自动序列化/补齐）

## 3. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-21 | GUI-BETA-R1 WP-C: `_forum_pending` 新增 `forum_initialized` key（__init__/load_from_dict 默认字面量 + required_forum_keys 补齐 + create_for_testing 三处） |

## WP-O 同步注记（2026-09-27，DA-Execute WP-O/O-S3；append-only）

> 权威：SA-Design WP-O v1.0（`075f873b…`）§B1/§B3。

- **同步死亡 hook**：`GameState.mark_member_dead` 于实际死亡/领导权变更之后、成功返回之前调用 WarSystem 单一 owner 解绑死者指挥官绑定（缺失 WarSystem = 合法 no-op；不吞错误、不因不完整清理返回 True；无外部 I/O）。
- **重复死亡**：已死/缺失 figure → `False`（现行为保留），零二次国库/土地转移与二次领域 mutation。
- **纠正态往返链**：`to_dict` → fresh `load_from_dict`：keys/version 不变；现任/资产镜像 null、历史 id 保留。
- **快照/回滚 additive**：`snapshot_war_resolution_domains` 捕获 `War.commander_status`；`restore_war_resolution_domains` 精确恢复 —— 失败 Senate 边界事务（`WarResolutionTransaction`）回滚时 `killed` 与 null current/镜像一并恢复（**内部字段，非存档 schema 变更**；无 `MVP0.7-24` Save/Load 功能变更）。

### 版本日志
| 版本 | 日期 | 摘要 |
|:--|:--|:--|
| v1.3 | 2026-10-06 | WP-J Group A R1：`mark_member_dead` 资产回收额供数同源注记（`wealth_confiscated`(T)/`land_confiscated`(C)，生产者按人捕获；`bool` 契约不变） |
| v1.2 | 2026-09-27 | WP-O O-S3：死亡同步 hook + 纠正态往返 + snapshot/restore additive `commander_status`（DA-Execute） |

## WP-J Group A R1 同步注记（2026-10-06，DA-Execute WP-J R1；append-only）

> 权威：SA-Development-Task-WP-J-GroupA-R1 v3.2（R1b，FROZEN）§5.2；Owner R-4 = Option 1。

- **写点（本域，未改）**：`GameState.mark_member_dead` 内部转账 = `add_treasury(member.wealth)`（`transfer_wealth and
  member.wealth > 0`）/ `add_national_public_land(member._land_private)`（`transfer_land`，`land > 0`）；
  并 `print` CLI 明细。**方法签名/`bool` 返回/守卫不变**。
- **供数（上游 Mortality 域）**：`core/service/mortality_service.py::_handle_death_event` 在调用前按人捕获
  `wealth_confiscated = victim.wealth if >0 else 0` / `land_confiscated = victim._land_private if >0 else 0`
  写入 `figure_death` impact；与上述转账**同源**。
- **消费（GUI 只读）**：`stages/MortalityStage.qml` 渲染条件子行（存在且 ≥1）；缺/0 不渲染；零重算（J-D02）。
