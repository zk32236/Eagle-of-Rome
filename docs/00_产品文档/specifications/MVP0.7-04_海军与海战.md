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

### 2.2 海战判定（冻结矩阵，G1-09/10/16，WP-G GC）

```
舰队战力（单舰派生成分） = quality-adjusted 贡献 + experience + commander.martial
罗马海军战力（海战聚合权威，R3-G-04） = Σ package（_construction_package_id）聚合：
  nominal 快照 n_i → quality q=D/A（精确整数比，D=实际成本/A=基线，D=0→q=0 不 fallback）
  → raw=Σ(n_i×q) → upper cap=min(raw, 2×nominal_package) → package 级 round 一次 → 跨 package 求和
  → + Σ experience + Σ War Commander martial（每 Fleet 加一次）
指挥官 martial 权威 = War Commander（war.commander_id，G1-20）
total = 2d6 + 罗马海军战力 - war.enemy_naval_current
```

CRT 结果：TRIUMPH/VICTORY/STALEMATE/DEFEAT/DISASTER（阈值/骰子区间与陆战 CRT 一致，零改）

> **R3-G-04（2026-09-05）：** 舰队补充（replacement）权威见 MVP0.5-04 §2.3——**nominal 非 effective**：
> 只认同战 nominal 容量（quality/experience/martial 不决定 hull 数）；海战罗马方战力消费 package
> 聚合（§2.2 上式），CRT/Sea Control/伤亡矩阵零改。

**五结果矩阵（D 件 §1）：**

| 海军结果 | 舰队损失 | Sea Control | 本场陆战 | 战争 |
|:--|:--|:--|:--|:--|
| **TRIUMPH** | 0 | acquired | 允许 | 继续陆战 |
| **VICTORY** | 0 | acquired | 允许 | 继续陆战 |
| **STALEMATE** | 0 | 未获控 | 阻断 | 继续 |
| **DEFEAT** | 随机 ceil(N/2) DESTROYED | 未获控 | 阻断 | 继续 |
| **DISASTER** | 全部参战舰队 DESTROYED | 未获控 | 阻断 | 继续 |

**海军门槛状态机（G1-09/R-04/R-05/R-06，canonical 单一门 = `combat_api.do_combat_action`）：**

```
naval_required == false → 无海军门，直接陆战
naval_required == true:
  未获控（sea_control_acquired == false）→ 必须先海战
    TRIUMPH/VICTORY → sea_control_acquired = true → 本场陆战允许
    STALEMATE/DEFEAT/DISASTER → 陆战不执行（R-05）→ 军团保持 ACTIVE+assigned
      （G1-15 零陆战伤亡）→ 战争继续，等待下次登陆机会
  已获控（sea_control_acquired == true）→ 跳过海战，直接陆战（R-06 禁重复海战）
```

**Sea Control 持久（G1-16 / K 件）：**

```
War.sea_control_acquired: bool（权威字段，默认 False；唯一 True 写入点 = resolve_naval_battle
TRIUMPH/VICTORY 分支；False 清理 = clear_sea_control，随战争正式结束接线，owner = GD）

获控持久至该战争正式结束；期间同战未来战斗跳过海战（R-06）；
若陆战 STALEMATE/DEFEAT/DISASTER → 战争继续 → 制海权保持 acquired。
替代旧 `_sea_control_ratio`（dormant float，禁作获控判定）。
```

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-04_海军与海战.md)

## WP-G-R4 同步注记（2026-09-09，DA-R4-B3；append-only，目标锚点 §2.2）

> 权威：SA-Design-WP-G-R4 v1.7（FROZEN）§3/§5；冻结矩阵/CRT/伤亡/Sea Control 持久规则零改。
>
> - **readiness 前置 ≠ 海战失败**：`naval_required` 且未获控时若本战无 ready 舰队
>   （`NavalSystem.get_ready_fleets_for_war` 单一事实源：assigned 实体按 ID 去重、仅
>   `ON_MISSION`；非 effective/strength/nominal 阈值）→ `NAVAL_NOT_READY`，**不产生任何
>   battle 事实**（零 CRT/损失/Sea mutation/事件/duration/battled）。force DEFEAT/TRIUMPH
>   不能穿透 NOT_READY。技术性 NavalSystem 缺失 = fail-closed，不作合法 NOT_READY。
> - **one ATTACK 双阶段（dual stage）**：海军门通过后同一次 ATTACK 内 Naval 成功
>   （TRIUMPH/VICTORY 且真实获控）→ 自动执行 Land（无需玩家二次确认，R4-02）；
>   Naval STALEMATE/DEFEAT/DISASTER → Land `NOT_EXECUTED(NAVAL_GATE_BLOCKED)`。
> - **NOT_READY / block 零副作用**：不写 pending/war_results/battled/summary event；
>   auto/CLI 以独立 `unavailable_wars` 名单表达（非 battles）。
> - **海权 stage 快照 ≠ terminal live 值**：envelope 内 `naval.sea_control_acquired` 是
>   Naval 阶段结束快照；War RESOLVED 后 `war_outcome.sea_control_after` 可为 false，两字段
>   并列不矛盾（Land TRIUMPH 终结清海权不覆盖阶段快照）。
> - **结果 DTO v2**（`schema_version=2`，每次 ATTACK 单一 finalized envelope）：`naval/land`
>   并列强类型 `executed`；未执行 stage 只写 executed/status/reason（omitted keys，非 0 占位，
>   R4-05）；envelope deepcopy 持久 `pending_result` + `war_results[war_id]`，get_combat_view 三类
>   卡同回合附 result（TRUCE_LOCKED 卡亦保留双结果）；`combat_action_resolved` 纯观察 summary event。

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.3 | 2026-09-09 | DA Sub-Agent (WP-G-R4 B3) | R4 同步（FROZEN v1.7 §3/§5）：§2.2 追加注记——Naval readiness 单一事实源/NOT_READY 非 battle 零副作用、one ATTACK Naval 成功自动 Land、dual-stage v2 envelope（未执行 stage omitted keys）、海权 stage 快照与 terminal 值并列、TRUCE 卡双结果入镜；CRT/伤亡/Sea Control 持久规则零改（GAME_RULE_CHANGE=NO） |
| v1.2 | 2026-09-05 | DA Sub-Agent (WP-G-R3 B3) | R3-G-04 同步：§2.2 单舰战力表述改 quality-adjusted/package aggregate（nominal 快照 + q=D/A + raw→cap→round 一次；per-fleet 无 floor；D=0 不 fallback）+ 补「replacement 见 MVP0.5-04，nominal 非 effective」注；CRT/Sea Control/伤亡矩阵零改（GAME_RULE_CHANGE=NO） |
| v1.0 | 2026-07-12 | Document Officer Worker K | 初版创建 |
| v1.1 | 2026-08-31 | DA Sub-Agent (WP-G GC) | 冻结语义落地（G1-09/10/16/20）：§2.2 补五结果矩阵（STALEMATE 0 损、DEFEAT ceil(N/2) 随机无放回）；海军门槛状态机（naval_required 门 / STALEMATE-DEFEAT-DISASTER 阻断陆战 / TRIUMPH-VICTORY 获控）；Sea Control 持久契约（sea_control_acquired 权威字段替代 _sea_control_ratio）；舰队战力 martial 权威 = War Commander |
