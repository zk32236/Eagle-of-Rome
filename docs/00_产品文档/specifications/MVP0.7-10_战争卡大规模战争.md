# MVP0.7-10 — 战争卡-大规模战争

> **功能简述：** 战争卡配置、JSON 数据加载、洗牌抽牌机制、按年份触发威胁、威胁自动升级

## 1. 功能目的

战争卡是游戏战争系统的数据驱动核心。通过 JSON 文件配置每一场战争，实现按历史年份触发威胁、自动升级和爆发。

## 2. 核心规则

### 2.1 战争牌堆生命周期

```
[wars.json] → load_wars_from_json() → _war_deck (INACTIVE)
  ↓ check_triggers(year >= start_year)
_threats (THREAT, level=1)
  ↓ escalate_threats() 每回合+1
_threats (level=2) → level=3 → _active_wars (ACTIVE)
  ↓ resolve_war(victory)
_war_discard (RESOLVED/DEFEATED)
```

### 2.2 威胁升级阶梯

| 等级 | 名称 | 行为 |
|------|------|------|
| 1 | 外交冲突 | 系统输出威胁消息 |
| 2 | 大军压境 | 继续升级警告 |
| 3+ | 战争爆发 | 自动激活为 ACTIVE |

### 2.3 默认战争回退

当 JSON 加载失败时创建 3 个默认测试战争（Gallic Raiders/Pirate Fleet/Provincial Revolt）。

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-10_战争卡大规模战争.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Worker K | 初版创建 |
