# MVP0.7-06 — 国泰民安

> **功能简述：** 天命阶段"国泰民安"事件触发后，平息已征服行省的民怨和所有战争的威胁等级。

## 1. 功能目的

模拟罗马治下和平（Pax Romana）的理想状态。平息行省不满情绪和外部军事威胁。

## 2. 核心规则

### 2.1 作用范围

| 目标 | 条件 | 效果 |
|------|------|------|
| 已征服行省 | `conquered == True` 且 `grievance > 0` | `grievance = 0` |
| 未征服行省 | `conquered == False` | 不受影响 |
| 威胁战争 | `threat_level > 0` | `threat_level = 0` |

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-06_国泰民安.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent A | 初版创建 |
