# PM 指令说明 — EOR GUI 重设计交付

> 目录: `E:\OpenClaw\EOR\`
> 日期: 2026-07-05

---

## 背景

本轮 GUI 设计由 Augustus（奥古斯都）完成，对 CODEX 之前实现的只读版 GUI 进行了全面升级。现移交 PM 处理意图包装和任务拆分。

## 交付物清单

| # | 文件 | 页数/行数 | 作用 |
|---|------|----------|------|
| 1 | `EOR_GUI_Prototype_v3.23.html` | 交互原型 | 打开浏览器即可操作，直观展示最终效果 |
| 2 | `EOR_GUI设计文档.md` | ~620 行（V2.0） | UI 设计规范：布局、交互、多玩家、颜色、i18n |
| 3 | `EOR_UI_API_Mapping.md` | ~430 行（V2.0） | 数据契约：每个 UI 控件对应的 API、参数、返回值 |

附带参考：
- `GUI_Code_Alignment_Audit.md` — 代码对齐审计，标注了哪些已有/待新增

## PM 任务

### 1. 阅读设计文档和原型

打开 `EOR_GUI_Prototype_v3.23.html` 浏览器预览，对照 `EOR_GUI设计文档.md` 理解每个阶段：
- 每个阶段公示区 + 子环节面板的结构
- 多玩家轮流、AI 后台的流程（§2）
- 角色锁定机制（执政官/保民官）
- 死锁逃生出口
- i18n 要求（§4.6）

### 2. 输出意图包给 SA

意图包应包含：

```
a. 哪些是全新模块（需 CGT 从零开发）
   - 战斗阶段 GUI 视图（无现有代码）
   - 收入阶段 GUI 视图（无现有代码）
   - 广场阶段 GUI 视图（CLI 已有，GUI 无）

b. 哪些是增量修改（在现有基础上改）
   - 元老院 GUI：只读版 → 交互版（现有 get_senate_view 复用）
   - 人口 GUI：现有的 controller 需补充多玩家轮流
   - GuiApiAdapter 新增 ~18 个方法封装（详细签名见 UI-API Mapping）

c. 优先级建议
   P0: GuiApiAdapter 增量 + 元老院交互化（复用最多）
   P1: 战斗视图 + 广场视图
   P2: 收入视图 + 决算优化
   P3: i18n 语言包 + 多玩家最终调试
```

### 3. 交接给 SA

PM 意图包 + `EOR_UI_API_Mapping.md` → SA 生成任务书 → CGT 按任务书开发。

**SA 重点关注 UI-API Mapping 中的「操作映射」表和「GuiApiAdapter 增量开发清单」**，这是技术接口的核心。

---

## 架构不变

向 CGT 明确：本次**不修改**后端架构。

| 保留 | 修改 |
|------|------|
| API 层（mortality_api / senate_api / forum_api 等） | GUI 视图层（HTML/PySide QML） |
| CLI 命令层（phase_*.py） | GuiApiAdapter（新增方法） |
| Core Systems / Entities | PopulationController 调整 |
| Session Store / Game State | 新建 combat / forum / revenue 适配器 |
