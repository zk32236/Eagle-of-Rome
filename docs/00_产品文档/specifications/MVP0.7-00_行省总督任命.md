# MVP0.7-00 — 行省总督任命

> **功能简述：** 行省总督的提名、元老院审批、候任交接全流程——涵盖 proconsul（前执政官）和 propraetor（前大法官）两类总督

## 1. 功能目的

在罗马共和时期，行省总督（Governor）由卸任执政官或大法官担任，负责行省的行政管理、司法审判和军事指挥。本功能实现：
- 元老院阶段执政官可提名总督候选人
- 候选人必须具有相应的卸任官职资格（ex-consul → proconsul，ex-praetor → propraetor）
- 提名经元老院表决通过后生效
- 候任总督在征召/任命回合即离开罗马（`is_absent = True`）
- 总督交接在决算阶段完成

## 2. 玩家/系统行为

### 2.1 总督候选人资格

资格规则：
- 必须为 **存活** 人物
- 必须 **不在出征/缺席中**（`not is_absent`）
- 当前官职必须为 **已卸任状态**（`office is None` 或 `startswith("ex-")`）
- 历史任期记录中必须有 **完整的相应官职任期**（`end_turn is not None`）
- 按 **卸任时间倒序** 排序（最近卸任者优先）

### 2.2 总督类型映射

| 行省类型 | 总督官职 | 候选人资格 |
|---------|---------|-----------|
| `proconsul` | 前执政官行省 | 卸任执政官（`ex-consul`） |
| `propraetor` | 前大法官行省 | 卸任大法官（`ex-praetor`） |

### 2.3 元老院提名提案

在元老院阶段 `_handle_step_1`（提案环节），执政官可提出 `governor` 类型提案：

### 2.4 AI自动提名

`_auto_generate_proposals()` 中自动提名流程：
1. 获取所有已征服行省（排除 `province_id == 0` 的意大利本土）
2. 按 `governor_type` 分为 proconsul 和 propraetor 两组
3. 分别获取合格候选人列表
4. 按卸任时间排序，优先分配最近卸任者
5. 随机分配行省（`random.shuffle`），按顺序匹配候选人和行省

### 2.5 总督交接完成

`Province.complete_governor_transition()` 在决算阶段调用：
- `governor_designate_id → governor_id`
- 清理临时记录

## 3. 核心规则

### 3.1 总督任命流程

```
行省空缺 → 执政官提名候选人 → 元老院提案 → 表决通过 → set_governor_designate → 决算阶段完成交接
```

### 3.2 唯一性约束

一个候选人不能同时被任命为两个行省的总督。

## 4. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-00_行省总督任命.md)

## 5. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Worker L | 初版创建 |
