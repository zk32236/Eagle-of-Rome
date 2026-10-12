# MVP0.5-18-sys — 状态查询命令扩展（技术映射）

## 1. 代码目录
```
src/ui/commands/func_status.py    # 6个查询命令
src/api/game_api.py, figure_api.py, faction_api.py, province_api.py, contract_api.py
src/api/session_api.py, gui_query_api.py
src/ui/gui/qml/shell/BottomQueryBar.qml    # GUI 底栏 12 入口
src/ui/gui/qml/shell/GameShell.qml         # 同线程 Store dispatch + routing
src/ui/gui/session_store.py                # GuiSessionStore（globalQueryResult）
src/ui/gui/api_adapter.py                  # GuiApiAdapter（query sanitize）
src/ui/gui/qml/shell/QueryResultOverlay.qml # 查询结果 overlay
data/i18n/zh-CN.json, data/i18n/en-US.json # GUI 查询文案
```

## 2. 命令列表
- status/sts — 全局概要
- status_public_land/spl — 公地信息
- status_private_land/spr — 私地信息
- status_figure/sf — 人物查询
- factions/fs — 派系查询
- province/prov — 行省查询

## 3. GUI 只读查询调用链（EOR20261011-01 HELP-ENQURY-FUNCTION）
```
BottomQueryBar.qml  --signal queryRequested(queryId)-->  GameShell.qml
  --> GuiSessionStore（session_store.py）  (query slots + globalQueryResult)
  --> GuiApiAdapter.get_global_query_result(viewer_id, query_id, filter_text, record_id)
  --> gui_query_api.get_global_query_result(state, viewer_player_id, query_id, filter_text, record_id)
  --> QueryResultOverlay.qml  (h36 单一状态面 + 两轴 resultsScroll)
```
- **seam**：`src/api/gui_query_api.get_global_query_result`（薄、只读；不 import CLI、不改状态、不触发 RNG）。单兼容入口 `(state, viewer_player_id, query_id, filter_text="", record_id="")`。
- **Adapter**：`src/ui/gui/api_adapter.py::GuiApiAdapter.get_global_query_result`（保留 API 真值并**强制 sanitize**：畸形/未验证封装 → 固定安全枚举外壳，绝不转发原始后端文本）。
- **Store**：`src/ui/gui/session_store.py::GuiSessionStore`（只读 `globalQueryResult` 属性 + query slots + `queryResultChanged` / `queryInvalidated(keep_open)` 失效信号）。
- **overlay**：`src/ui/gui/qml/shell/QueryResultOverlay.qml`（h36 固定单一状态面（无滚区重复）；PT-01 列表表 / PT-02 详情 field→value；列/字段按 viewer 投影，FOREIGN 缺席不留空）。
- **12 入口（canonical 顺序）**：`faction_info` · `figure_search` · `game_status` · `faction_treasury` · `public_land` · `private_land` · `contract_status` · `province_info` · `war_list` · `legion_status` · `fleet_status` · `help`。

## 4. DTO / 字段读模型（冻结）
- **war_list**：权威 **18 键**公共战争读模型 + package **8 键**（= `ERRATUM WAR-S5-01`）；分组计数 `active`/`threat`/`truce`/`resolved`；指挥官 living-only。
- **legion_status**：九字段 `number,name,status,is_veteran,war_id,assigned,strength,cost,destroyed_turn`；计数 `total`/`active`/`available`/`assigned`/`destroyed`（= `ERRATUM LEGION-S5-01`）。
- **fleet_status**：五字段 `number,name,fleet_type,status,is_veteran`（收窄维持）。
- **land price**：OUT/DEFER（无独立单价查询）。
- 投影在 DTO 构建**之前**递归完成；未列字段**缺席**。

## 5. i18n key（命名空间）
- 标题：`query.<query_id>.title`
- 状态/消息：`query.<query_id>.message`（含 `query.figure_search.message`）
- 错误：`query.error.<code>`（`state_unavailable`/`viewer_unavailable`/`unknown_query`/`invalid_request`/`system_unavailable`/`record_unavailable`/`query_failed`/`query_unavailable`/`not_implemented`）
- 帮助：`query.help.guide.<id>` / `query.help.guide.<id>.value`
- 值/枚举：`query.value.*`、`query.bool.*`、`query.phase.*`、`query.office.*`、`query.item.*`、`query.figure.*`、`query.contract.{type,status}.*`、`query.war.status.*`、`query.legion.status.*`、`query.fleet.status.*`、`query.public_land.*`、`query.province.*`、`query.<query_id>.*`
- 目录：`data/i18n/zh-CN.json` + `data/i18n/en-US.json`（QML 经 `GuiText`/`L10n` 解析 `dto.*_key`，**不**硬编码）。

## 6. 版本日志
| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-17 | 系统 | 初版 |
| v1.1 | 2026-10-13 | DA-Execute（EOR20261011-01 DocSync） | 同步 GUI 只读查询链（seam/Adapter/Store/overlay）、12 入口、冻结字段读模型（war 18 键 / legion 九字段 / fleet 五字段 / land OUT-DEFER）与 i18n key 命名空间。 |
