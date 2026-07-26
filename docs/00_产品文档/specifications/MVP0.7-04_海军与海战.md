# MVP0.7-04 — 海军与海战-P0（含技术解锁）

> **功能简述：** Fleet 实体全生命周期、NavalSystem 管理、海战 CRT 判定（简化版）、技术解锁条件（皮洛士战争胜利后方可建造舰队）、舰队维护费与解散

## 1. 功能目的

海军是罗马军事力量的重要组成部分。本功能实现技术解锁、舰队管理、海战判定、维护费与解散全流程。

## 2. 核心规则

### 2.1 舰队类型配置

| 类型 | 建造费用 | 建造时间 | 维护费 | 基础战力 |
|------|---------|---------|-------|---------|
| trireme | 40 | 1 回合 | 120 | 3 |
| quadrireme | 120 | 2 回合 | 200 | 4 |
| quinquereme | 160 | 3 回合 | 320 | 5 |

### 2.2 海战判定

```
combat_strength = _strength_base + _experience + (commander.martial if commander else 0)
total = 2d6 + roman_naval_power - enemy_naval_power
```

CRT 结果：TRIUMPH/VICTORY/STALEMATE/DEFEAT/DISASTER

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-04_海军与海战.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Worker K | 初版创建 |
