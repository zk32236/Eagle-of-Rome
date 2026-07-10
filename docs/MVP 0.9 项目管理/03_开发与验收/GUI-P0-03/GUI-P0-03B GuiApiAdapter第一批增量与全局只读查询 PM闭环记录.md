# GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 PM闭环记录

- 日期：2026-07-05
- 记录人：项目经理 PM
- 任务编号：GUI-P0-03B
- 任务名称：GuiApiAdapter第一批增量与全局只读查询
- SA Decision：PASS
- 项目负责人手工 GUI 验证：通过
- Git 提交：`c03763f GUI-P0-03B add readonly global queries`
- 推送状态：`main -> origin/main`

## 一、完成内容

GUI-P0-03B 已完成第一批全局只读查询能力补齐，在 GUI-P0-03A 主壳和查询浮窗基础上，建立了更清晰的 `GuiApiAdapter` / `GuiSessionStore` 查询边界。

已完成内容包括：

- 新增薄只读 API：`src/api/gui_query_api.py`。
- `GuiApiAdapter` 新增统一查询 wrapper。
- `GuiSessionStore.doGlobalQuery()` 改为委托 Adapter/API，不再在 Store 内拼装 Core/System 查询明细。
- 首批真实/只读查询接入：游戏状态、派系信息、战争列表、军团状态。
- 其余底部按钮保持统一占位 DTO。
- 查询浮窗继续使用 GUI-P0-03A/R1 的 `QueryResultOverlay.qml`。

## 二、架构边界确认

SA 验收确认：

- 查询路径保持 `QML -> GuiSessionStore -> GuiApiAdapter -> gui_query_api/session snapshot`。
- 信息隔离：viewer 派系显示自身金库；其他派系仅显示公开摘要。
- 战争/军团查询使用公共 getter，不直读私有容器。
- 未发现 `game_api.execute_phase`、`game_api.execute_turn`、`CombatCommand` 或 phase command 调用。
- 未发现 `._active_wars`、`._threats`、`._truce_wars`、`._legions` 直读。
- QML i18n 硬编码扫描无新增散落 UI 文案匹配。

## 三、测试与验证

CGT 测试/扫描结果由 SA 采信：

| 项目 | 结果 |
|---|---|
| `test_gui_query_api.py` | 6 passed |
| `test_adapter.py` | 11 passed |
| `test_qml_startup.py` | 7 passed |
| `test_gui` | 30 passed |
| full `src\tests` | 773 passed |
| `git diff --check` | passed，仅 CRLF 提示 |

项目负责人真实 GUI 手工验证：通过。

## 四、PM 判断

GUI-P0-03B 可以正式关闭。该任务完成了底部查询栏从“骨架/占位”到“第一批安全只读查询”的过渡，也为后续元老院、广场、战争、收入等阶段视图提供了可复用的查询 API/Adapter 模式。

建议下一步进入：`GUI-P0-03C 元老院交互化第一段`。

推荐 03C 仅聚焦元老院交互化的第一段：提案列表、提案详情、可提案类型/参数 DTO、候选总督 API 响应结构收束。暂不在 03C 中完成提案创建、投票、否决和结算闭环；这些应留给 03D。

## 五、遗留与注意事项

- 底部查询栏仍有部分按钮保持占位 DTO，后续可随阶段视图逐步接入。
- 完整 i18n 语言包仍属于后续 P3/收尾，但新增 UI 文案继续保持集中管理。
- 版本规划 Excel 仍有项目负责人本地修改：`docs/MVP 0.9 项目管理/01_需求与版本规划/EOR MVP 1.0 目标版本规划 V1.1.xlsx`。本任务和本记录不纳入该 Excel。