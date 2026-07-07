# PM 任务意图包 — GUI Phase A 展示层重建

**任务编号:** GUI-P0-04A
**任务名称:** 展示层组件化重建 — Phase A（基础组件）
**类型:** PM 任务意图包
**日期:** 2026-07-06
**状态:** 已批准

---

## 1. 任务摘要

将当前 Stage 内部的重复 UI 代码（阶段 header / 步骤条 / 按钮 / 信息框）提取为 4 个独立可复用 QML 组件。
仅涉及 `stages/` 和 `components/` 目录。Shell、Theme、Python 层不变。

## 2. 业务理由

- 当前 ~805 行重复 UI 代码在 7 个阶段之间散布
- 4/7 阶段仍为空白占位符，每新建一个需重新造所有 UI 元素
- 不修这个下层结构，每补一个阶段就要重复造一遍，无法 scale

## 3. 范围 (IN SCOPE)

| 项目 | 说明 |
|------|------|
| `components/StageHeader.qml` | 新建：阶段标识 + 标题 + 描述 |
| `components/StepRail.qml` | 新建：步骤指示条，数据驱动 |
| `components/UnifiedButton.qml` | 新建：三态按钮（primary/small/disabled） |
| `components/InfoBox.qml` | 新建：四类信息框（info/warning/success/error） |
| `stages/MortalityStage.qml` | 修改：用新组件替换内联代码 |
| `stages/PopulationStage.qml` | 修改：用新组件替换内联代码 |
| `stages/SenateStage.qml` | 修改：用新组件替换内联代码 |

## 4. 范围 (OUT OF SCOPE)

| 项目 | 理由 |
|------|------|
| Python core / systems / API / session_store | 限制令第 1 条 |
| Main.qml / GameShell | 限制令第 2 条 |
| TopStatusBar / PhaseRail / ContextPanel / BottomQueryBar | 限制令第 2 条 |
| Theme.qml / GuiText.qml | 不属于 Stage 展示层 |
| 4 个空阶段 UI | Phase B/C 目标，非 Phase A |
| 颜色硬编码消除 | Phase C 目标 |

## 5. 架构影响

```
Before:                              After:
MortalityStage.qml                   MortalityStage.qml
├── Rectangle (header) 25行   →      ├── StageHeader { badge, title, desc } 1行
├── Rectangle (steps) 30行    →      ├── StepRail { steps, current, completed } 1行
├── Rectangle (button) 15行   →      ├── UnifiedButton { text, primary, onClicked } 1行
├── Rectangle (info-box) 10行 →      └── InfoBox { text, type } 1行
└── Rectangle (更多按钮) 15行 →
                                    4 个新组件文件
                                    3 个 Stage 文件缩减
                                    未来 4 个 Stage 可直接引用
```

## 6. 风险分析

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 组件接口设计不合理导致返工 | 🟡 | 严格对照 v3.23 HTML 原型规范 |
| 组件间间距/对齐偏移 | 🟡 | 每个组件替换后立即视觉验证 |
| 组件不够通用需重复修改 | 🟡 | 保持接口尽可能小；可后续扩展 |
| SessionStore 依赖导致 Stage 绑定复杂 | 🟢 | 组件保持 stateless，由 Stage 传 props |

## 7. 验收标准

- [ ] 4 个新组件文件存在于 `components/` 目录
- [ ] 每个组件使用 Theme.qml color tokens（非硬编码色值）
- [ ] MortalityStage header/步骤/按钮/信息框改用组件引用
- [ ] PopulationStage header 改用组件引用
- [ ] SenateStage header + 步骤条 改用组件引用
- [ ] 不修改 GameShell / TopStatusBar / PhaseRail / ContextPanel / BottomQueryBar
- [ ] 不修改任何 Python 文件
- [ ] 不修改 Theme.qml / GuiText.qml
- [ ] 全量回归 773/773 通过

## 8. 实施顺序

```
Step 1: StageHeader.qml → MortalityStage 验证
Step 2: StepRail.qml → MortalityStage 验证
Step 3: UnifiedButton.qml → MortalityStage 验证
Step 4: InfoBox.qml → MortalityStage 验证
Step 5: PopulationStage + SenateStage 引用
Step 6: 全量回归
```

## 9. 交付物

```
docs/MVP 0.9 项目管理/03 开发任务书/
  └── GUI-P0-03D 展示层组件化重建 PhaseA PM意图包.md   ← 本文件
```

## 10. 审批记录

| 角色 | 姓名 | 日期 | 决定 |
|------|------|------|------|
| PO | 克劳狄乌斯 | 2026-07-06 | ✅ 批准，三项限制 |
| DA | 奥古斯都 | 2026-07-06 | 建议重建，已审 |
