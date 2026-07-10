# GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 技术边界审查报告 - SA-01

## Decision

READY_FOR_TECH_TASK

## Reasons

- GUI-P0-03A 已完成 OPC 五区主壳、底部查询栏和查询浮窗，03B 可以在此基础上补齐第一批安全只读查询。
- 本轮应聚焦查询 DTO 与权限过滤，不应进入元老院、广场、战争、收入、决算等复杂业务动作。
- 当前 `GuiSessionStore._build_global_query_result()` 已承担部分 DTO 拼装，03B 应将这部分收束到 API/Adapter 边界，避免 Store 继续理解 Core/System 细节。
- `game_api.py` 当前仍导入 CLI phase command；03B 不应继续扩大 GUI 对 `game_api` 的依赖。建议新增薄的只读 `src/api/gui_query_api.py`，或等价只读 API 边界。

## Files reviewed

- `docs/MVP 0.9 项目管理/02_项目任务书/GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 PM任务意图包.md`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/shell/BottomQueryBar.qml`
- `src/ui/gui/qml/shell/QueryResultOverlay.qml`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/api/session_api.py`
- `src/api/game_api.py`
- `src/api/faction_api.py`
- `src/core/systems/war_system.py`
- `src/core/systems/military_system.py`
- `src/tests/test_gui/test_adapter.py`
- `src/tests/test_gui/test_qml_startup.py`

## Recommended GUI-P0-03B scope

本轮只做底部查询按钮第一批安全只读能力：

1. 新增或整理只读查询 API，推荐 `src/api/gui_query_api.py`。
2. `GuiApiAdapter` 增加统一查询 wrapper，例如 `get_global_query_result(viewer_id, query_id)`。
3. `GuiSessionStore.doGlobalQuery()` 改为委托 Adapter/API，不再在 Store 内拼装具体查询明细。
4. 查询浮窗继续复用 GUI-P0-03A/R1 的 `QueryResultOverlay.qml`。
5. 补齐 `游戏状态`、`派系信息`、`战争列表`、`军团状态` 四个按钮的真实或安全只读 DTO。
6. 其余 8 个按钮保留明确占位状态，不接入复杂业务。

## Query button implementation matrix

| 查询按钮 | 03B 状态 | 边界要求 |
| --- | --- | --- |
| 游戏状态 | 真实只读 | 使用新只读 API 汇总 year/turn/treasury/living_count/faction_count/current_phase，不继续扩大 `game_api` 依赖 |
| 派系信息 | 真实只读 | viewer 派系可显示 treasury；其他派系只能显示公开字段，不显示 treasury/private data |
| 战争列表 | 真实只读 | 通过 `WarSystem` 公共查询方法读取 active/threat/truce/resolved 摘要；不执行 combat |
| 军团状态 | 真实只读 | 通过 `MilitarySystem` 公共查询方法读取 legion status/counts；不征召、不解散、不分配 |
| 人物查询 | 占位 | 后续任务承接 |
| 派系金库 | 占位或 viewer-only alias | 不显示他派金库 |
| 公地信息 | 占位 | 后续任务可接 public land read-only |
| 私地信息 | 占位 | 需单独处理信息隔离 |
| 合同状态 | 占位 | 后续任务承接 |
| 行省信息 | 占位 | 后续任务承接 |
| 舰队状态 | 占位 | 后续任务承接 |
| 帮助 | 静态占位 | 仅集中化文案 |

## Required API/DTO boundaries

推荐新增：

```text
src/api/gui_query_api.py
```

建议接口：

```python
def get_global_query_result(state: GameState, viewer_player_id: str, query_id: str) -> dict:
    ...
```

返回结构必须保持：

```python
{
    "success": bool,
    "message": str,
    "data": {
        "id": str,
        "title_key": str,
        "status": "connected" | "readonly" | "placeholder",
        "message_key": str,
        "message_params": dict,
        "items": [
            {"label_key": str, "value": str | int | bool, "value_key": Optional[str], "meta": dict}
        ],
        "summary": dict
    },
    "errors": list
}
```

允许 CGT-01 在实现时保持 03A 当前 `title/message/items` 兼容字段，但必须加入稳定 key 或保持可迁移到 i18n 的结构。

## Information isolation rules

- `viewer_player_id` 必须参与查询 API，不能只按全局 state 裸查。
- viewer 派系 treasury 可以显示；其他派系 treasury 不得显示。
- 人物私产、私地、隐藏投票、竞标金额、未公开决策不得在本轮显示。
- 战争列表只显示公开摘要，不显示后续战斗内部随机/结算细节。
- 军团状态只读展示状态和分配摘要，不允许改变征召、解散或分配状态。

## Forbidden implementation paths

- GUI/QML/Store/Adapter 不得调用 CLI Command。
- 不得调用 `game_api.execute_phase()`、`game_api.execute_turn()`。
- 不得调用或导入 `CombatCommand`。
- 不得在 QML 或 Store 直接读取 `WarSystem`、`MilitarySystem`、Core entity 或私有字段。
- 不得继续把新的查询业务明细堆在 `GuiSessionStore._build_global_query_result()`。
- 不得接入任何复杂业务动作。

## Required tests

- `src/tests/test_gui/test_adapter.py -q`
- `src/tests/test_gui/test_qml_startup.py -q`
- `src/tests/test_gui -q`
- 若新增 `gui_query_api.py`，新增 `src/tests/test_api/test_gui_query_api.py -q`
- full `src/tests -q`
- `git diff --check`
- 边界扫描：`execute_phase|execute_turn|CombatCommand|phase_senate|phase_forum|phase_revenue|phase_combat`
- i18n 硬编码扫描：新增 QML 不得出现行内 UI 文案

## Risks

- `game_api.py` 仍有历史 API -> UI command 依赖，本轮不解决，但应避免进一步使用它作为 GUI 查询入口。
- 派系信息最容易误泄露他派金库，必须用测试覆盖。
- 战争和军团列表如果直接返回实体对象，会让 QML 依赖 Core 结构，必须转换为 DTO。

## CGT-01 task dispatch status

技术任务书已定稿，准备发布给 CGT-01。
