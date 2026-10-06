# MVP0.4-05-sys — GameState状态管理

> **功能简述：** 全局游戏状态单例管理：阶段数据、玩家列表、事件存储、序列化支持

## 1. 功能目的
待编写。

## 2. 玩家/系统行为
待编写。

## 3. 核心规则
待编写。

## 4. 输入、输出与依赖
待编写。

## 5. 状态与边界
待编写。

## 6. 验收标准
待编写。

## 7. 历史演化与证据
- 历史审计入口：
- 历史名称：
- 首次实现版本：

## 8. 技术架构映射
- [Technical Mapping](../technical-mappings/MVP0.4-05-sys.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-10-06 | DA-Execute (WP-J Group A R1) | 追加 §10：`mark_member_dead` 资产回收额（财富→国库 T；私地→国家公地 C）经生产者按人供数（`wealth_confiscated`/`land_confiscated`，同源）；`bool` 返回契约不变 |

## 10. WP-J Group A R1 同步注记（2026-10-06，DA-Execute WP-J R1；append-only）

> 权威：SA-Development-Task-WP-J-GroupA-R1 v3.2（R1b，FROZEN）§5.2（FC-15/FC-09）；Owner R-4 = Option 1。

- **`mark_member_dead(member_id, transfer_land, transfer_wealth) -> bool` 契约不变**（成功/缺失/已死
  仍返回 `True`/`False`；combat 指挥官阵亡、CLI 阵亡、既有测试仍消费该 `bool`）。
- **资产回收额语义（供数来源）**：财富回收额 = `member.wealth`（`>0` 守卫）→ `add_treasury`；
  土地回收额 = `member._land_private`（`>0` 守卫）→ `add_national_public_land`。生产者
  `MortalityService._handle_death_event` 在调用 `mark_member_dead` **之前**按人捕获上述两值，写入
  `figure_death` impact 的 `wealth_confiscated:int`（T）/ `land_confiscated:int`（C）——与 CLI `print`
  明细**同源**（同一实体/时刻/`>0` 守卫）。GUI 侧仅渲染（存在且 ≥1；缺/0 不渲染；禁重算）。
