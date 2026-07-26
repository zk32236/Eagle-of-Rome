# MVP0.7-08 — 无妄天灾

> **功能简述：** 天命阶段"无妄天灾"事件触发后，随机一座已征服行省遭受灾害，本回合该行省收入按损失比例减少。

## 1. 功能目的

模拟罗马行省遭受自然灾害（地震、洪水、瘟疫等）的随机事件。

## 2. 核心规则

### 2.1 损失计算

```
loss = base_loss × (1 - infrastructure_level × mitigation_factor)
loss = clamp(loss, 0.0, 1.0)
```

### 2.2 配置

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `mortality_rules.disaster_base_loss` | float | `0.5` | 兜底损失率 |

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-08_无妄天灾.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent A | 初版创建 |
