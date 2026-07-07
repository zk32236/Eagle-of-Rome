# CURRENT_STATE — EOR 产品当前状态

- 最后更新：2026-07-06
- 责任角色：PM / SA
- 依据来源：项目进度记录.md、后续任务池.md、架构收口 Sprint 任务包.md、Git log、产品目录审计

---

## 1. 当前版本

- **Git HEAD：** `2c2de94e0d8931325d737f5957c6d18569275557`
- **最近提交：** `Update PM progress for GUI-P0-03B closeout`
- **Python：** 3.12.3（WSL2）
- **GUI 框架：** PySide6 6.8.3 / Qt 6.8.3
- **架构状态：** 架构收口 Sprint 已全部完成（AS-P0-01~04），进入 GUI-P0-03 阶段对齐 Sprint

---

## 2. 已完成模块

### 架构与系统层（AS）

| 模块 | 任务 | 状态 |
|------|------|------|
| PoliticalSystem | AS-P0-01 — 政治系统从分散收束到系统层 | ✅ DONE（CONDITIONAL_PASS） |
| EconomicService | AS-P0-02 — 收入结算迁移至服务层 | ✅ DONE（PASS） |
| 私有字段访问收束 | AS-P0-03 — 第一批私有字段公共接口 | ✅ DONE（CONDITIONAL_PASS） |
| 广场土地交易 API 化 | AS-P0-04 — 消除数据流尾巴 | ✅ DONE（PASS） |
| API Response 统一 | AS-P1-01 — 统一 API 返回结构 | ✅ DONE（PASS） |

### GUI 层

| 模块 | 任务 | 状态 |
|------|------|------|
| MVP0.7 可玩 GUI 原型 | GUI-P0-01 — PySide6 + QML 骨架 + 人口垂直切片 | ✅ DONE（PASS） |
| GUI 主壳与阶段导航 | GUI-P0-02A — OPC 前代主壳骨架 | ✅ DONE（PASS, R1 included） |
| 天命 + 人口 GUI | GUI-P0-02B — 两阶段 GUI 闭环 | ✅ DONE（PASS） |
| 元老院只读状态+导航 | GUI-P0-02C-1 — Senate 只读页 | ✅ DONE（PASS） |
| OPC 主壳骨架落地 | GUI-P0-03A — OPC 五区主壳 + 查询浮窗 | ✅ DONE（PASS） |
| GuiApiAdapter 第一批 | GUI-P0-03B — 只读查询 + DTO + 权限过滤 | ✅ DONE（PASS） |

### 缺陷修复

| 缺陷 | 状态 |
|------|------|
| BUG-P0-20260623 Forum current player sync | ✅ DONE（PASS） |

---

## 3. 进行中的工作

### TASK-001 / 元老院阶段 GUI 对齐（待正式转换）

| 项目 | 内容 |
|------|------|
| 目标编码 | **GUI-P0-03F**（元老院阶段） |
| 当前状态 | 6 个 QML 文件已修改（PhaseRail / GameShell / TopStatusBar / BottomQueryBar / SenateStage / ContextPanel），7/7 测试通过。**未提交，等待用户重启游戏验收。** |
| 停止原因 | 上一 session 显示 bug 中断；用户尚未在 IDE 中重启验证 |

### GUI-P0-03C 天命阶段 GUI 对齐

| 项目 | 内容 |
|------|------|
| 状态 | PM 任务意图包已创建，**待批准** |
| 文件 | `02_项目任务书/GUI-P0-03C 天命阶段GUI对齐 PM任务意图包.md` |
| 主要差距 | 圆形按钮→矩形、ContextPanel 缺推进按钮、死亡详情单事件视图、边距压缩 |

---

## 4. 待创建任务

| 编码 | 阶段 | 优先级 | 计划 |
|------|------|--------|------|
| GUI-P0-03D | 人口阶段 (Population) | P0 | 次步 |
| GUI-P0-03E | 广场阶段 (Forum) | P0 | 次步 |
| GUI-P0-03G | 战争阶段 (War) | P0 | 后续 |
| GUI-P0-03H | 收入阶段 (Revenue) | P0 | 后续 |
| GUI-P0-03I | 决算阶段 (Budget) | P0 | 后续 |

---

## 5. 技术债务与未解决问题

| 编号 | 说明 | 优先级 | 来源 |
|------|------|--------|------|
| TD-AS-P0-01-01 | 自动提案生成规则迁移 | P1 | AS-P0-01 |
| TD-AS-P0-01-02 | PoliticalSystem 文档与函数索引同步 | P2 | AS-P0-01 |
| TD-AS-P0-01-03 | 历史私有字段访问清理 | P2 | AS-P0-01 |
| TD-AS-P0-03-01 | Contract 生命周期私有访问清理 | P1/P2 | AS-P0-03 |
| TD-AS-P0-03-02 | 场景加载与死亡资产回收私有访问清理 | P1/P2 | AS-P0-03 |
| TD-AS-P0-03-03 | 调试工具与测试夹具私有访问清理 | P2 | AS-P0-03 |
| TD-AS-P0-03-04 | AS-P0-03 新增公共接口函数索引同步 | P1 文档 | AS-P0-03 |

---

## 6. 当前已知风险

| 风险 | 严重度 | 说明 |
|------|--------|------|
| 工作区脏状态 | 🟡 中 | 448 个文件处于未提交修改状态（含 CODEX 遗留 + 我们修改的 6 个 QML），TASK-001 修改尚未 commit |
| 测试环境 | 🟢 低 | `tests/` 目录在 WSL2 中不存在（测试在 Windows 原生 Python 中运行），本次 session 暂未找到测试路径 |
| GUI-P0-03C 任务未批准 | 🟡 中 | 任务意图包已创建但尚未批准，无法进入 SA 审查和 DA 开发 |
| 双目录规范初建 | 🟢 低 | 产品目录与项目资产目录的归属边界仍在试运行磨合中 |

---

## 7. 当前 Sprint 焦点

**阶段 GUI 对齐 Sprint（GUI-P0-03C → I）**

逐个阶段将现有 QML 页面与 V3.23 原型对齐：
- 当前：**GUI-P0-03C 天命阶段**（任务待批准）
- 下一候选：**GUI-P0-03D 人口阶段**
- 排队中：**GUI-P0-03F 元老院阶段**（原 TASK-001，代码已改待验收）
