"""
src/ui/gui/README.md
GUI 模块说明文档
"""
# EOR GUI 模块

## 架构

```
GUI (QML)
  -> GuiApp (app.py)         应用壳层
  -> GuiSessionStore         唯一状态存储，只读属性
  -> GuiApiAdapter           API 调用 + 响应验证
  -> Session API / Population API  ...  -> Core
```

## 目录结构

- `app.py` — 应用主类，初始化 PySide6，注册 QML 类型，加载 Main.qml
- `session_store.py` — GUI 会话存储，QML 通过只读属性访问
- `api_adapter.py` — 统一 API 适配器，处理 success/message/data/errors
- `controllers/` — 阶段控制器（当前仅人口阶段）
- `models/` — QAbstractListModel 子类（人物、候选人、事件）
- `qml/` — QML 界面文件
  - `Main.qml` — 根入口
  - `shell/` — GameShell、导航、状态栏、反馈区、遮罩
  - `stages/` — 阶段面板（人口阶段庆典/投票/结果）
  - `components/` — 可复用组件（按钮、表格、弹窗、步进器）
  - `theme/` — Theme.qml 颜色令牌

## 启动

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" "C:\Users\Kerl\PycharmProjects\Eagle of Rome\gui_main.py"
```

## 依赖

```
PySide6==6.8.3
pytest-qt==4.4.0
```

## 权限与信息隔离

- 每次操作后从 `session_api.get_session_snapshot()` 重新刷新
- QML 不直接访问 `GameState`、Entity 或 System
- 玩家交接时先清空旧敏感模型，再显示遮罩

## WP-G-R4 注记（2026-09-09，DA-R4-B3；append-only）

- **Combat 结果 DTO v2（权威 schema 见 `docs/00_产品文档/technical-mappings/MVP0.3-02_战争系统.md`
  R4 注记与 MVP0.7-04 规格 R4 注记）**：每次 ATTACK 单一 finalized envelope
  （`schema_version=2`，`naval/land` 并列强类型 `executed`；未执行 stage 只写
  executed/status/reason——omitted keys 非 0 占位）。Store 只读透传（combatBattleResultDetail /
  combatResolvedWarCards 与 API DTO 逐项相同），不做字段重建。
- **readiness 拒绝**：`NAVAL_NOT_READY` → Store 只读 refresh + 结构化 feedback，不把失败 data
  写进结果当 battle victory/defeat。
- **QML 两结果区（resultBox + WarCard.cardResult）**共用同一 stage renderer（纯 display）：
  Naval executed → 海战结果/舰队损失/海权阶段结果；Land executed → 陆战结果/骰子/攻防/
  损失/战利品；Land 未执行固定「陆战: 未执行 — 海战门未通过」；NOT_READY 只示「海军未就绪」；
  Naval bypass 说明原因不渲染作海战胜利；无 ||0 fallback、executed 缺失 → 「未记录」；
  整次 action 一个确认钮（无二次确认）。真实 Qt 渲染证据归 SO Work Order
  WP-G-R4-NATIVE-QT-DUAL-STAGE-CAPTURE。
