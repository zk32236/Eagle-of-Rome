# MVP0.5-07 — 战斗阶段（自动战斗）— 技术映射

## 1. 代码目录
```
src/api/combat_api.py           # 战斗 API（含 S1 共享用例 auto_resolve_combat）
src/ui/gui/api_adapter.py       # GUI Adapter（委托 auto_resolve_combat）
src/ui/gui/session_store.py     # SessionStore（doAdvanceSenate → 触发 AI 自动战斗）
src/ui/qml/                     # QML 战斗界面
```

## 2. 触发路径

### 2.1 AI 自动战斗触发
```
doAdvanceSenate()                    # session_store.py
  → adapter.advance_senate(viewer_id) # 推进到 Combat 阶段
  → if currentPlayerId != viewer_id:  # AI 玩家
      → adapter.auto_resolve_combat(viewer_id)  # 委托给共享用例
          → combat_api.auto_resolve_combat(state, viewer_id)
```

### 2.2 GUI 玩家交互
```
玩家在 CombatStage QML 中选择战争
  → doSelectWar(war_id)                # session_store.py
    → adapter.call(combat_api.select_war, ...)
  → 玩家选择进攻/防御/侦查
    → doCombatAction(action)
      → adapter.do_combat_action(...)
  → 确认战果
    → doConfirmBattleResult()
      → adapter.confirm_battle_result(...)
  → 推进
    → doAdvanceCombat()
      → adapter.advance_combat(...)
```

### 2.3 CLI 战斗触发（S1 适配后）
```
combat 命令                             # phase_combat.py
  → CombatCommand.execute()
    → combat_api.auto_resolve_combat(state, player_id)
    → 打印返回 DTO 中的战斗结果
```

## 3. S1 变更摘要

### 3.1 变更前
- GUI `adapter.auto_resolve_combat()` 包含独立 for-loop 编排（select_war → do_combat_action → confirm → advance）
- GUI 与 CLI 为两套平行战斗结算体系
- Adapter 自行处理战争循环

### 3.2 变更后
- Adapter 不再保留 for-loop，直接委托 `combat_api.auto_resolve_combat()`
- CLI 同样委托给同一 API 函数
- 停战条约和指挥官返程归入共享用例

### 3.3 受影响文件
| 文件 | 变更 |
|:-----|:------|
| `api_adapter.py` | `auto_resolve_combat()` 简化为单行委托 |
| `combat_api.py` | 新增 `auto_resolve_combat()` + `_generate_peace_treaty()` + `_process_commanders_returning()` |
| `phase_combat.py` | `execute()` 改为委托共享用例；保留私有方法供测试引用 |
| `session_store.py` | 触发路径不变（doAdvanceSenate → adapter.auto_resolve_combat） |

## 4. DTO 结构（CombatView + auto_resolve 结果）

### 4.1 get_combat_view DTO
```python
{
    "phase_id": "combat",
    "current_step": "select" | "action" | "result" | "advance",
    "active_wars": [WarCard],   # 活跃战争卡片
    "resolved_war_cards": [],   # 已结算战争
    "battle_results": [],       # 当前战果
    "can_advance": bool,
    "actionable": bool,
    ...
}
```

### 4.2 auto_resolve_combat DTO
见 `MVP0.4-XX_战斗系统.md §3.2`

## 5. 当前局限与后续
- 共享用例仅用于 `auto_resolve`（AI 自动）路径；玩家交互路径仍使用原始 `select_war → do_combat_action → confirm → advance` 各步骤
- S2 将类似的统一模式应用到 Resolution 阶段
- 如果后续需要玩家交互路径也使用共享用例，需扩展 `auto_resolve_combat` 以支持增量/单场模式

## 6. WP-E 更新（2026-08-23，GUI-BETA-R1）

### 6.1 `_war_card` 新字段（E-G7-11）

`combat_api._war_card`（:47-76）新增：

```python
{
    ...既有字段,
    "truce_end_turn": war.truce_end_turn,
    "truce_remaining_turns": max(0, war.truce_end_turn - state.turn.turn_number)
        if war.truce_end_turn else None,
}
```

- state 参数已在 `_war_card` 签名内，权威计算（禁 QML 猜测，R-05）；
  `truce_end_turn` 为 None → `truce_remaining_turns` 为 None → CombatStage TRUCE_LOCKED 卡
  「⏳ 和约剩余 X 回合」行不显示。
- TRUCE_LOCKED 卡新增倒计时行（CombatStage.qml），DTO 直读。

### 6.2 TRUCE 卡军团投影边界（E-POST-R1-07P）

- 投影链：`_war_card` legions_assigned/legion_numbers（直读 war 实体）→ CombatStage.qml:552-557。
- 实体镜像方向验证：展示 = 权威实体；mobilized=0 案例——实体 `legions_assigned > 0` 而展示 0
  → 投影 bug（WP-E 内修）；实体本身 0 → 底层状态错（WP-G traceability 移交，禁 QML 掩盖）。
- traceability：`03-da-evidence/traceability/wpe-slice9-legion-projection-2026-08-23.md`。

## 7. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-23 | GUI-BETA-R1 WP-E（Slice 11 PU-04）：新增 §6 —— `_war_card` TRUCE 剩余回合字段（E-G7-11）+ TRUCE 卡军团投影边界（07P） |
| v1.0 | 2026-07-12 | 初版 |
