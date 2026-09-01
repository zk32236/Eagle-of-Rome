# MVP0.7-24 — 存档/读档

> **功能简述：** 游戏状态的保存和加载功能
> **状态：** PLANNED
> **版本：** v0.4

## 1. 功能目的

允许玩家在任意时点保存游戏进度，退出后通过读档恢复。

## 2. 核心规则

### 2.1 序列化格式

JSON 格式，包含 version/timestamp/turn/data 的包装对象。

### 2.2 关键缺口

| 实体 | to_dict | from_dict | 状态 |
|------|---------|-----------|------|
| Figure | ❌ 缺失 | ❌ 缺失 | 最优先 |
| GameTurn | ❌ 缺失 | ❌ 缺失 | 次优先 |
| Legion | ✅ 已有（WP-G GB：`to_dict`/`from_dict`，O 件 §4.4） | ✅ 已有 | 原语已提供；GameState 存档接线 = GD |
| War（含 `sea_control_acquired`） | ✅ 已有（WP-G GC：字段层，O 件 §2） | ✅ 已有 | 原语已提供；GameState 存档接线 = GD |
| Fleet（含 `_target_war_id` / `DISBANDED`） | ✅ 已有（WP-G GC：字段层，O 件 §2/§3） | ✅ 已有 | 原语已提供；GameState 存档接线 = GD |
| WarSystem | ❌ 缺失 | ❌ 缺失 | 中优先（GD） |

> **GC 新增持久契约（G1-12/G1-16，DI-5）：**
> - `War.sea_control_acquired`（制海权权威布尔）：`to_dict/from_dict` 已持久；旧存档缺键/None → False（`acquired is True` 容错；禁以 `_sea_control_ratio` 映射——dormant 字段不映射，N 件 §2）
> - `Fleet._target_war_id`（单战归属 provenance）：`to_dict/from_dict` 已持久；旧存档缺键 → None
> - `FleetStatus.DISBANDED`：新枚举值，旧存档无此值 → 原样加载；新存档值合法
> - **完整 GameState 存档接线（WarSystem/MilitarySystem 纳入序列化）= GD 首要动作**（O 件 §1 PARITY GAP）

### 2.3 Legion 序列化契约（WP-G GB，O 件 §4.4）

`Legion.to_dict()` 持久字段：

```
number / name / status（枚举 value）/ is_veteran / commander_id / war_id
battles_fought / battles_won / _destroyed_turn / _legion_type
```

`Legion.from_dict(data)` 退化路径（O 件 §3，禁旧存档加载崩溃）：

```
is_veteran 缺省 → False
未知 status 值 → 回退 UNRAISED
_destroyed_turn / _legion_type 缺省 → 0 / polybian
```

> **完整存档接线（GameState 纳入 MilitarySystem/WarSystem 序列化）= GD 首要动作**（O 件 §1 PARITY GAP：War/Legion 运行态当前存档丢失）。

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-24_存档读档.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v0.4 | 2026-08-31 | DA Sub-Agent (WP-G GD) | 存档接线完成（DI-1）：§2.2 缺口表 WarSystem/MilitarySystem/Legion/War/Fleet 行改为已接通；新增「GD 存档接线完成」注记段（GameState 纳入 `_war_system`/`_military_system` 序列化 + 旧存档退化路径 + S32 验收）；版本日志 |
| v0.1 | 2026-07-17 | Document Officer | 初始草案 |
| v0.2 | 2026-08-31 | DA Sub-Agent (WP-G GB) | Legion 序列化契约（O 件 §4.4）：`to_dict`/`from_dict` 字段清单 + 退化路径（is_veteran 缺省 False）；存档接线（GameState 纳入 WarSystem/MilitarySystem）标注为 GD 首要动作 |
| v0.3 | 2026-08-31 | DA Sub-Agent (WP-G GC) | 持久契约补充（DI-5）：`War.sea_control_acquired`（制海权权威，缺省 False）与 `Fleet._target_war_id`（单战归属，缺省 None）纳入序列化契约 + 退化路径；`FleetStatus.DISBANDED` 枚举容错；完整存档接线仍属 GD |
