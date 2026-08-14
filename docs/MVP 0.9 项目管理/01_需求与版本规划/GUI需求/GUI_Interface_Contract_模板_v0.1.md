# GUI Interface Contract 模板

> v0.1 讨论稿
> 来源：EOR_UI_API_Mapping.md + GUI_CONTROL_MAPPING_MATRIX.md
> 受众：DA、Backend Integration、QML Implementation
> 用途：定义 QML ↔ 后端的绑定契约：Property、Signal、Model、Backend Binding、Method

---

## 使用说明

- SA 在输出 Development Task 时，为每个新 GUI 组件填写此模板
- 模板定义了 QML 组件需要暴露的所有接口：属性绑定、信号绑定、模型绑定、方法调用
- DA 按此模板实现 QML ↔ 后端集成
- Backend Integration 按此模板完成服务层对接
- QML Implementation 按此模板编码组件接口
- 模板应作为 Development Task 的附录

---

## 模板

### 组件基本信息

```yaml
组件名称: <组件英文名，如 StageHeader>
所属阶段/页面: <如 Forum Stage / Main Layout>
设计参考: <HTML Prototype 文件名 + 区域>
```

### 属性绑定（Properties）

| QML 属性名 | 类型 | 后端路径 | 方向 | 默认值 | 备注 |
|-----------|------|---------|------|--------|------|
| `exampleTitle` | `string` | `sessionStore.currentStage.name` | 读 | `""` | 标题文字 |
| `exampleCount` | `int` | `sessionStore.someModel.count` | 读 | `0` | 数量显示 |
| `exampleEnabled` | `bool` | — | 写（QML 本地） | `true` | 按钮启用状态 |
| `exampleColor` | `color` | — | 写（固定值） | `theme.header` | 颜色绑定 |

**方向说明：**
- `读` = QML 从后端模型/Store 读取
- `写` = QML 本地维护，不联动后端
- `读写` = 双向绑定
- `固定值` = 固定色值/常量

### 信号绑定（Signals）

| QML 信号 | 参数 | 后端响应 | 备注 |
|---------|------|---------|------|
| `onClicked` | — | `sessionStore.doSomething()` | 按钮点击 |
| `onTextChanged` | `newText` | `sessionStore.updateField(newText)` | 输入框内容变化 |
| `onSelectionChanged` | `selectedIndex` | `sessionStore.selectItem(selectedIndex)` | 列表选择变化 |

### 模型绑定（Models）

| QML 模型名 | 类型 | 后端路径 | 角色名 | 备注 |
|-----------|------|---------|--------|------|
| `exampleModel` | `ListModel` / `QAbstractListModel` | `sessionStore.someListModel` | `name`, `value`, `isActive` | 列表数据 |
| `exampleTableModel` | `QAbstractTableModel` | `sessionStore.someTableModel` | 按列定义 | 表格数据 |

### 方法调用（Methods）

| QML 调用 | 后端方法 | 参数 | 返回值 | 备注 |
|---------|---------|------|--------|------|
| `sessionStore.submit()` | `SomeService.submit(data)` | `data: dict` | `bool` | 提交数据 |
| `sessionStore.refresh()` | `SomeService.getData()` | — | `dict` | 刷新数据 |

---

## 填写示例（以 StageHeader 为例）

```yaml
组件名称: StageHeader
所属阶段/页面: Main Layout (Header Bar)
设计参考: EOR_GUI_Prototype.html → Header 区域
```

### Properties

| QML 属性名 | 类型 | 后端路径 | 方向 | 默认值 |
|-----------|------|---------|------|--------|
| `stageName` | `string` | `sessionStore.currentStage.name` | 读 | `""` |
| `roundInfo` | `string` | `sessionStore.currentRound.label` | 读 | `""` |
| `stages` | `var` | `sessionStore.stageProgression.stages` | 读 | `[]` |
| `currentIndex` | `int` | `sessionStore.stageProgression.currentIndex` | 读 | `0` |
| `headerBg` | `color` | — | 固定值 | `theme.header` |
| `logoText` | `string` | — | 固定值 | `"[R] EAGLE OF ROME"` |

### Signals

| QML 信号 | 参数 | 后端响应 |
|---------|------|---------|
| `onStageClicked` | `stageIndex: int` | `sessionStore.stageProgression.jumpTo(stageIndex)` |

---

> 本模板基于现有 EOR_UI_API_Mapping.md 和 GUI_CONTROL_MAPPING_MATRIX.md 的字段结构提取。
