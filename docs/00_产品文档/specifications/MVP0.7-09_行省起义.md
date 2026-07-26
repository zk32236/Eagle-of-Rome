# MVP0.7-09 — 行省起义-P0

> **功能简述：** 行省民怨达到 3 级时自动触发起义战争，由总督镇压，胜利后民怨归零

## 1. 功能目的

行省起义是民怨机制的最终惩罚性结果。当行省（或意大利本土）的民怨（grievance）升级至 3 级时，自动创建并登记为活跃的起义战争。

## 2. 核心规则

### 2.1 起义触发条件

| 条件 | 说明 |
|------|------|
| 行省民怨 >= 3 | `province.grievance >= 3` |
| 未在起义中 | `not province.event_flags.get("rebellion_active")` |

### 2.2 起义战争配置

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `combat_rules.rebellion_strength` | `5` | 起义军基础战力 |
| `enable_threats` | `True` | 全局威胁/起义开关 |

### 2.3 起义战争胜利效果

| 效果 | 详情 |
|------|------|
| 民怨 | 归零 |
| 事件标记 | 清除 `rebellion_active` |
| 指挥官声望 | `family_prestige += 1` |
| 战利品 | 无 |

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-09_行省起义.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent F | 初版创建 |
