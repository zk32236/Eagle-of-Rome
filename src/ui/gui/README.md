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
