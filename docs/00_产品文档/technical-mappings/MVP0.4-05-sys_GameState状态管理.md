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
| v1.2 | 2026-09-27 | WP-O O-S3：死亡同步 hook + 纠正态往返 + snapshot/restore additive `commander_status`（DA-Execute） |
