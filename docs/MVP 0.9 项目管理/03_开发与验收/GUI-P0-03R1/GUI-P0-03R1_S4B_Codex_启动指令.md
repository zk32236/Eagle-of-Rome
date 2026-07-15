# GUI-P0-03R1_S4B_Codex_启动指令

日期：2026-07-16
适用对象：新的 Codex 主会话
任务阶段：GUI-P0-03R1 / S4B / ForumStage 市场环节 GUI 对齐
执行方式：主会话内角色切换，不调用 multi_agent_v1 子代理
流程要求：必须遵循 EOR GUI 开发流程包 V2.2

---

## 1. 启动结论

本轮新 Codex 会话应直接接续 GUI-P0-03R1 的 S4B，不需要重新评估 Phase 3 全局方案。

本任务属于正式 GUI 返工流程，必须遵循 EOR GUI 开发流程包 V2.2。若流程包与本启动指令发生冲突，以 PM 已确认的 S4B 产品决策和禁改范围为准，并在实施报告中记录偏差。

S4A 已完成并归档为本地 git 提交：

```text
e4c3f3d GUI-P0-03R1 S4A fix forum retire list layout
```

S4A 解决的是 Phase 3A/3B 左侧“解雇成员”列表重叠问题。
S4B 需要解决的是 Phase 3B 右侧“市场环节”GUI 与 v3.25.1 设计目标不对齐的问题。

---

## 2. 必读文件

新会话开始前应优先阅读以下文件：

1. `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_Codex_工作进展交接报告_2026-07-15.md`
2. `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_ForumStage_Phase3A3B_最终SA开发任务书.md`
3. `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_S2_ForumStage_A-F差异表.md`
4. `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_S2_ForumStage_VisualLayoutContract.md`
5. `docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_S4A_ForumStage_LeftList_DA实施报告.md`
6. `src/ui/gui/qml/stages/ForumStage.qml`

如需确认当前仓库状态，可执行：

```text
git status --short
```

但不得把与 S4B 无关的既有改动纳入本轮提交。

---

## 3. 本轮目标

S4B 的目标是：

只修正 ForumStage 中 Phase 3B 市场环节的 GUI 表达，使其在真实游戏数据下尽量贴近 v3.25.1 设计目标。

重点对象：

- 右侧市场卡片。
- 市场环节标题与结构。
- 人才市场列表显示。
- Pending Contract / 预算表决合同区域。
- 公地认购区域。
- 凯旋投票区域。
- 市场底部“提交下注 / 完成下注”按钮状态。
- 市场卡片内容滚动。

---

## 4. 可改范围

优先只允许修改：

```text
src/ui/gui/qml/stages/ForumStage.qml
```

如确实发现 GUI 绑定缺少必要字段，必须先输出 GAP 说明并等待 PM 确认，不得直接扩大修改范围。

---

## 5. 禁止范围

本轮默认禁止修改：

```text
src/core/
src/api/
src/ui/gui/api_adapter.py
src/ui/gui/session_store.py
src/ui/gui/qml/shell/GameShell.qml
src/ui/gui/qml/shell/ContextPanel.qml
src/ui/gui/qml/shell/TopStatusBar.qml
src/ui/gui/qml/shell/BottomQueryBar.qml
src/ui/gui/qml/shell/PhaseRailIcon.qml
```

也禁止：

- 重写 ForumStage 整页结构。
- 回滚或覆盖 S4A 左侧列表修复。
- 使用假数据替代真实游戏数据。
- 为贴图而改变 CORE 游戏规则。
- 把市场逻辑提前暴露到解雇阶段。

---

## 6. 已确认产品决策

S4B 必须遵守以下 PM 决策：

1. 市场环节使用真实游戏数据，不使用视觉校准假数据。
2. 人才市场新人不应在解雇前提前公开；如果 CORE 当前逻辑是在市场阶段生成新人，GUI 应尊重该逻辑。
3. 第一回合可能没有正式招标合同，但应显示 Pending Contract / 待元老院预算表决合同信息。
4. 第一回合可能没有公地认购，但公地认购区块位置应保留，可显示空态或禁用态。
5. 凯旋投票区块应保留；无可投票内容时显示空态或禁用态。
6. 市场阶段玩家可以配置招募、竞标、认购、凯旋投票等操作。
7. 市场区域底部应有“提交下注”按钮。
8. 所有玩家下注完成后，按钮变为“完成下注”且不可操作。
9. 全部玩家完成后，才允许通过右侧 ContextPanel 的“推进到下一阶段”进入人口阶段。
10. 步骤条只保留两个编号：
    - `1 解雇成员`
    - `2 市场（招募·竞标·认购·凯旋）`
11. 市场环节标题使用：`市场（招募·竞标·认购·凯旋）`。

---

## 7. S4B 建议验收标准

完成后至少满足：

1. Phase 3A 左侧解雇列表不回归，无文字/按钮重叠。
2. Phase 3B 右侧市场卡片标题、分区和按钮语义与产品决策一致。
3. 人才市场有真实数据时可显示多条人物，不重叠，不越界。
4. Pending Contract / 预算表决合同区域存在。
5. 公地认购区域存在。
6. 凯旋投票区域存在。
7. 市场内容超出高度时可滚动。
8. 市场底部按钮按状态显示“提交下注”或“完成下注”。
9. 不修改 CORE/API/Store/Adapter/Shell。
10. GUI 测试通过。

建议测试：

```text
py -3.10 -m pytest -p no:cacheprovider src\tests\test_gui\test_qml_startup.py -q
py -3.10 -m pytest -p no:cacheprovider src\tests\test_gui -q
```

---

## 8. 交付要求

S4B 完成后应输出：

1. 修改后的 `ForumStage.qml`。
2. S4B DA 实施报告：

```text
docs/MVP 0.9 项目管理/03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_S4B_ForumStage_MarketPanel_DA实施报告.md
```

报告至少包括：

- 修改范围。
- 未修改范围。
- 已遵守的产品决策。
- 测试结果。
- 尚待人工视觉验收项。
- 是否建议归档 git。

---

## 9. 执行提醒

新会话执行时必须遵守 GUI 开发流程包 V2.2 的基本门禁：

1. 不调用子代理，采用主会话内 PM/SA/DA 角色切换。
2. 开发前先阅读 PM 意图包、SA 任务书、A-F 差异表和本启动指令。
3. 开发前确认可改范围与禁改范围。
4. 小任务不拆分时，也要在报告中说明“不拆分，直接进入 DA”。
5. 完成后输出 DA 实施报告。
6. Git 归档前必须单独确认。

本轮的关键不是“更像设计图”，而是：

在真实游戏数据、真实阶段状态、真实交互边界下，让市场环节的 GUI 结构稳定、可读、可验收。

如遇到设计图与游戏真实数据冲突，应优先尊重游戏真实数据，并把差异写入实施报告。
