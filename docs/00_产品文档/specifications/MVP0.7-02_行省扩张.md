# MVP0.7-02 — 行省扩张

> **功能简述：** 战争胜利后可解锁新行省，标记征服状态并设置起始民怨

## 1. 功能目的

实现罗马通过战争扩张领土的机制。当战争胜利时，如果战争配置了 `unlocked_provinces` 列表，对应行省将被标记为 `conquered = True`（征服状态），并初始化高民怨（grievance = 3），体现新征服地区的治理难度。

## 2. 玩家/系统行为

### 2.1 系统行为

1. **战争结算阶段：** `WarSystem.resolve_war()` 胜利时，检查 `war.unlocked_provinces`
2. 如果有可征服行省，调用 `GameState.conquer_provinces(war.id)`
3. 设置 `province._conquered = True`，`province.set_grievance(3)`

### 2.2 征服触发条件

| 条件 | 说明 |
|------|------|
| 战争必须胜利 | `resolve_war(war_id, victory=True)` |
| 战争必须有 unlocked_provinces | 从 JSON 配置加载 |
| 行省不能已征服 | `province.conquered == False` |

### 2.3 征服效果

| 效果 | 值 | 说明 |
|------|-----|------|
| `conquered` | `True` | 标记征服状态 |
| `grievance` | `3` | 新征服行省民怨最高级 |

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-02_行省扩张.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent F | 初版创建 |
