# MVP0.4-XX — 战斗系统（技术映射）

## 1. 代码目录
```
src/api/combat_api.py              # 战斗 API（视图、操作、推进、共享用例）
src/ui/commands/phase_combat.py    # CLI 战斗阶段命令
src/ui/gui/api_adapter.py          # GUI Adapter（委托给共享用例）
src/ui/gui/session_store.py        # GUI SessionStore（触发自动战斗）
src/core/systems/war_system.py     # 战争系统（激活、结算、停战）
src/core/entities/war.py           # War 实体
src/core/entities/legion.py        # Legion 实体（含战力计算）
```

## 2. 关键模块

### 2.1 `combat_api.py` — 战斗 API 层
- `get_combat_view(state, viewer_id)` → 战斗阶段只读 DTO（war_cards, current_step）
- `select_war(state, viewer_id, war_id)` → 选择战争（Player Command）
- `do_combat_action(state, viewer_id, war_id, action, auto=False)` → 执行战斗（scout/defence/attack）
- `confirm_battle_result(state, viewer_id)` → 确认战果
- `advance_combat(state, viewer_id)` → 推进战斗阶段
- **`auto_resolve_combat(state, player_id)` → S1 共享用例**（见 §3）

### 2.2 `phase_combat.py` — CLI 命令
- `CombatCommand.execute()` → 前置检查后委托给 `combat_api.auto_resolve_combat()`
- `_resolve_battle()` → 保留原始的逐场战斗方法（供直接调用场景使用）
- `_simplified_crt()` → CLI 独立 CRT 判定（S1 后仍保留供引用/测试）
- `_apply_battle_result()` → CLI 独立结果应用（保留供测试）
- `_maybe_generate_treaty()` → 停战草案生成（S1 后仍保留供引用）
- `_process_commanders_returning()` → 指挥官返程处理（S1 后委托给共享用例）

### 2.3 `api_adapter.py` — GUI Adapter
- `auto_resolve_combat(player_id)` → **S1**：委托给 `combat_api.auto_resolve_combat()`，不再保留 for-loop

## 3. S1 共享用例：`combat_api.auto_resolve_combat()`

### 3.1 签名
```python
def auto_resolve_combat(state: GameState, player_id: str) -> dict:
```

### 3.2 返回 DTO 结构
```python
{
    "success": bool,
    "message": str,
    "data": {
        "wars_resolved": int,         # 已结算战争数
        "active_war_count": int,      # 总活跃战争数
        "skipped_no_commander": int,  # 无指挥官跳过数
        "battles": [
            {
                "war_id": str,
                "war_name": str,
                "result": str,         # triumph/victory/draw/defeat/disaster
                "result_label": str,   # 中文标签（🏆 大胜！等）
                "dice": int,
                "total_attack": int,
                "enemy_defence": int,
                "total_score": int,
                "losses": int,
                "triumph": bool,
                "loot": int,
                "treasury_share": int,
                "commander_share": int,
                "faction_share": int,
                "soldier_share": int,
            }
        ],
        "treaties": [dict],           # 停战条约列表
        "commanders_returned": [dict], # 返回罗马的指挥官
        "completed": bool,            # combat 阶段是否完成
        "next_phase": str,            # 下一阶段 ID
    }
}
```

### 3.3 内部流程
1. 获取活跃战争列表
2. 分类：有指挥官 vs 无指挥官
3. 无指挥官战争 → `_skip_all_unassigned()` 标记为已跳过
4. 有指挥官战争 → 逐场：`select_war → do_combat_action(attack, auto=True) → _generate_peace_treaty → confirm_battle_result`
5. 指挥官返程处理：`_process_commanders_returning()`
6. 推进阶段：`advance_combat()`

### 3.4 CLI/GUI 统一后
- CLI `CombatCommand.execute()` → 委托给 `auto_resolve_combat()` → 显示返回 DTO
- GUI `adapter.auto_resolve_combat()` → 委托给 `auto_resolve_combat()`
- Adapter 不再保留 for-loop/子步骤编排
- 停战条约、指挥官返程归入共享用例

## 4. 关键差异对照（S1 前后）

| 维度 | S1 前 CLI | S1 前 GUI | S1 后（统一） |
|:-----|:----------|:----------|:-------------|
| 结果命名 | TRIUMPH/VICTORY/STALEMATE/DEFEAT/DISASTER | triumph/victory/draw/defeat/disaster | triumph/victory/draw/defeat/disaster |
| 战力公式 | ∑legion.get_combat_strength() | legions_assigned * 2 | legions_assigned * 2 |
| CRT 阈值 | ≥12/≥6/≥-3/<-3 | ≥10/≥5/≥0/<0 | API _compute_combat_result |
| 停战条约 | 独有 | 无 | 共享用例生成 |
| 指挥官返回 | 独有 | 无 | 共享用例处理 |

## 5. 测试映射
```
src/tests/test_api/test_combat_api.py           — 现有 combat_api 单元测试（13 项）
src/tests/test_api/test_combat_auto_resolve.py  — S1 共享用例测试（6 项）
src/tests/test_api/test_combat_cli_features.py  — CLI 特征冻结测试（25 项）
src/tests/test_api/test_combat_gui_features.py  — GUI 特征冻结测试（11 项）
src/tests/test_commands/test_phase_combat.py    — CLI 命令测试（S1 适配版）
src/tests/test_commands/test_phase_combat_naval.py — 海战测试（S1 适配版）
```

## 6. 对外依赖
- `WarSystem` — `get_active_wars()`, `get_war_by_id()`, `resolve_war()`, `enter_truce()`
- `MilitarySystem` — `get_legions_for_battle()`, `get_available_legions()`
- `GameState` — `is_current_player()`, `get_phase_result()`, `record_phase_result()`, `mark_phase_executed()`
- `AutoPeaceTreatyDecider` — `decide_treaty()`（用于停战条约生成）
