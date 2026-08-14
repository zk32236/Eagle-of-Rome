# GUI UI Contract 模板

> v0.1 讨论稿
> 来源：EOR_UI_API_Mapping.md + GUI_CONTROL_MAPPING_MATRIX.md
> 受众：PM、SA、GUI Review、Visual Acceptance
> 用途：定义页面结构、信息层级、必须存在的视觉元素、布局约束、视觉实现约束

---

## 使用说明

- SA 在输出 Development Task 时，为每个新 GUI 组件填写此模板
- 模板定义了 QML 组件需要满足的视觉契约：布局、尺寸、颜色、字体、间距
- PM 按此模板确认信息层级和内容完整性
- GUI Review / Visual Acceptance 按此模板验收视觉实现
- 模板应作为 Development Task 的附录

---

## 模板

### 组件基本信息

```yaml
组件名称: <组件英文名，如 StageHeader>
所属阶段/页面: <如 Forum Stage / Main Layout>
设计参考: <HTML Prototype 文件名 + 区域>
```

### 视觉约束（Visual Constraints）

| 项目 | 值 | 参考来源 |
|------|----|---------|
| 组件尺寸 | `width: parent.width`, `height: 48px` | Design Bible / 原型 |
| 内边距 | `padding: 12px` | Design Bible |
| 背景色 | `theme.panelBg` / `#FFF5E6` | Design Bible |
| 边框 | `border: 1px solid theme.panelBorder` | Design Bible |
| 圆角 | `radius: 8` | Design Bible |
| 字体 | `font.pixelSize: 14` | Design Bible（0.9rem ≈ 14px） |

### 信息层次（Information Hierarchy）

| 层级 | 视觉元素 | 说明 | 优先级 |
|------|---------|------|--------|
| `<如 Primary>` | `<如标题文字>` | <内容说明> | P0 |
| `<如 Secondary>` | `<如状态指示>` | <内容说明> | P1 |
| `<如 Tertiary>` | `<如辅助图标>` | <内容说明> | P2 |

### 必须存在的视觉元素（Mandatory Visual Elements）

| 元素 | 类型 | 必须条件 | 验收标准 |
|------|------|---------|---------|
| `<元素名>` | `text` / `icon` / `image` / `shape` | `<什么条件下必须显示>` | `<可检查的视觉标准>` |

---

## 填写示例（以 StageHeader 为例）

```yaml
组件名称: StageHeader
所属阶段/页面: Main Layout (Header Bar)
设计参考: EOR_GUI_Prototype.html → Header 区域
```

### Visual Constraints

| 项目 | 值 |
|------|----|
| 组件尺寸 | `height: 64px`, `width: parent.width` |
| 内边距 | `padding: {left: 24, right: 24}` |
| 背景色 | `theme.headerBg` / `#1A1A2E` |
| 边框 | `border: none` |
| 圆角 | `radius: 0` |
| 导航文字 | `font.family: "Cinzel"`, `font.pixelSize: 14`, `color: theme.gold` |

### Information Hierarchy

| 层级 | 视觉元素 | 说明 | 优先级 |
|------|---------|------|--------|
| Primary | `stageName` (text) | 当前阶段名称 | P0 |
| Secondary | `roundInfo` (text) | 当前轮次标签 | P1 |
| Tertiary | stage indicators (dots) | 阶段进度指示 | P2 |

### Mandatory Visual Elements

| 元素 | 类型 | 必须条件 | 验收标准 |
|------|------|---------|---------|
| Logo "[R] EAGLE OF ROME" | text | 始终显示 | 左侧对齐，Cinzel 字体 |
| 当前阶段名称 | text | 始终显示 | 居中，白色，pixelSize 16 |
| 阶段进度指示器 | dots | 有多个阶段时 | 圆点间距 8px |

---

> 本模板基于现有 EOR_UI_API_Mapping.md 和 GUI_CONTROL_MAPPING_MATRIX.md 的字段结构提取。
