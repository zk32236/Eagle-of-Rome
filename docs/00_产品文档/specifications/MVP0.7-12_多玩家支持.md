# MVP0.7-12 — 多玩家支持

> **功能简述：** 多玩家支持——Player 实体定义、多人轮流、API 接口

## 1. 功能目的

多玩家支持是游戏支持多人轮流/同时操作的基础设施。支持玩家实体定义、类型区分、回合轮流控制和权限校验。

## 2. 核心规则

### 2.1 Player 类型

| 类型 | 说明 |
|------|------|
| HUMAN | 人类玩家（交互操作） |
| AI | AI 玩家（自动完成） |
| OBSERVER | 观察者（只读） |

### 2.2 回合轮流

- `_turn_order` 仅含 HUMAN 玩家
- AI 玩家由 `AutoPlayerProcessor` 自动完成
- `next_player()` 在 `_turn_order` 中循环

### 2.3 权限校验

所有写操作（执行阶段、结束回合、投票等）前校验 `is_current_player()`。

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-12_多玩家支持.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-13 | Document Officer (DA) | 初版创建 |
