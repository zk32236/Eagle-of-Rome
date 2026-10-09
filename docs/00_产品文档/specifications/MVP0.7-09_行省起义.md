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
| v1.1 | 2026-10-09 | DA-Execute (WP-J Group D) | §1/§2.1 追加注记：Forum 回合初始化产出的起义事件经只读载体投影为公告框内警示行（additive 只读；仅显示，不重开创建/招募规则） |
| v1.0 | 2026-07-12 | Document Officer Sub-Agent F | 初版创建 |

## WP-J Group D 同步注记（2026-10-09，DA-Execute；append-only，目标锚点 §1/§2.1）

> 权威：WP-J Group D SA-Development-Task v1.1（G3 FROZEN）§5.4；FC-D09–FC-D12。起义创建/招募/民怨规则**零改**（GAME_RULE_CHANGE=NO）。

- **广场阶段起义警示呈现**：权威 producer `forum_api.check_province_unrest()`（`initialize_forum_turn` 内调用，产出 `rebellions:[{id,name,province_id,province_name}]`）被 `initialize_forum_turn()` 之后**只读捕获**入 `GameState._forum_rebellion_events`（镜像 `_forum_war_events`）→ `forum_api.get_forum_view().rebellion_events` → `session_store.forumRebellionEvents` → `ForumStage.qml` **既有公告框 `announceArea` 内**追加行「⚠️ 起义爆发：<province_name>（<name>）」（FC-D09/FC-D10）。高度公式/空态条件 additive 纳入 rebellion。
- **仅新触发起义**（不含 war_threats/升级）；**不自造**生命周期时点（J-D04/FC-D11）；**不含**军团池变化展示（⑥b NO-CHANGE，FC-D12）；**不重开**起义创建/招募规则。
