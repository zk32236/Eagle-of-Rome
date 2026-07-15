# GUI-P0-03R1 ForumStage Phase 3A/3B 最终 SA 开发任务书

> 流程版本：PM→SA→DA v2.2-C1
> 任务编号：GUI-P0-03R1
> 任务名称：ForumStage Phase 3A/3B 可控返工
> 本轮 DA 子任务：S4A — 左侧解雇成员列表布局防重叠修复
> 状态：Ready for DA Sizing Check

---

## 1. 任务主类型

```text
Visual Calibration / Regression Fix
```

本轮只修一个主要区域：ForumStage 左侧解雇成员列表行布局与底部按钮固定。

不得混入：

- Store/API Binding
- Data DTO Fix
- 右侧市场卡片重写
- ContextPanel 状态逻辑
- 步骤条语义修改

## 2. 目标

修复 Phase 3A / 3B 中左侧解雇成员列表的严重视觉回归：人物姓名、属性、按钮重叠；确保列表可读、可滚动，底部完成按钮固定且不覆盖列表。

## 3. 依据文档

| 文档 | 路径 |
| --- | --- |
| PM Intent v2.2 | `02_项目任务书/GUI-P0-03R1_ForumStage_Phase3A3B_可控返工_PM意图包_v2.2.md` |
| S1 任务书骨架 | `03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_S1_ForumStage_任务书骨架_SA开发任务书.md` |
| S2 Visual/Layout Contract | `03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_S2_ForumStage_VisualLayoutContract.md` |
| S2 A-F 差异表 | `03_开发与验收/GUI-P0-03R1/GUI-P0-03R1_S2_ForumStage_A-F差异表.md` |

## 4. Phase Visual-State Contract 摘要

### Phase 3A 解雇阶段

- 步骤条：`✅ 公示区 → 1 解雇成员 → 2 市场（招募·竞标·认购·凯旋）`
- 当前可操作：左侧人物行解雇按钮、左侧卡片底部 `完成解雇`。
- 真实数据：左侧派系人物列表、身份/影响力、锁定状态。
- 禁止：为了贴设计图裁剪人物数量或伪造人物。

### Phase 3B 市场阶段

- 左侧解雇成员卡片进入完成态，但仍必须保持可读，不得重叠。
- 右侧市场卡片真实数据不在本刀处理范围。
- 市场按钮、ContextPanel 推进逻辑不在本刀处理范围。

## 5. Layout Contract 摘要

### 左侧解雇成员卡片

| 项目 | 契约 |
| --- | --- |
| 列表区域 | 独立滚动，占据卡片标题与底部按钮之间空间 |
| 行高 | 固定或最小高度，建议 `>= 44px` |
| 姓名列 | 占主要宽度，超长省略，不压按钮 |
| 属性列 | 固定宽度，不与姓名重叠 |
| 按钮列 | 固定宽度，位于右侧 |
| 锁定态 | 与解雇按钮共用同一按钮列宽度 |
| 底部按钮 | 固定在卡片底部，不随列表滚动，不覆盖列表行 |

## 6. 允许修改范围

| 类型 | 文件 |
| --- | --- |
| 修改 | `src/ui/gui/qml/stages/ForumStage.qml` |
| 修改/新增 | 与 ForumStage 结构相关的 GUI 测试（仅如已有对应测试需要更新） |

## 7. 禁止修改范围

- `src/core/`
- `src/api/`
- `src/ui/gui/session_store.py`
- `src/ui/gui/api_adapter.py`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- 右侧市场卡片业务逻辑
- 步骤条语义
- 顶栏、左侧 PhaseRail、底部查询栏

## 8. DA 实施要求

DA 只能执行以下 Step：

```text
Step 1：定位 ForumStage.qml 中左侧解雇成员列表行 delegate / layout。
Step 2：为人物行建立固定列布局：姓名列、属性列、按钮列。
Step 3：为列表区域建立滚动容器，底部完成按钮固定。
Step 4：确认锁定态和普通解雇按钮占用同一按钮列。
Step 5：运行 GUI startup / 相关聚焦测试。
Step 6：提交 Runtime Screenshot 和 Implementation Report。
```

## 9. 验收标准

| 编号 | 标准 |
| --- | --- |
| AC-01 | Phase 3A 左侧人物姓名、属性、按钮不重叠 |
| AC-02 | Phase 3B 左侧人物姓名、属性、按钮不重叠 |
| AC-03 | 长人物名不覆盖按钮，可省略或固定宽度显示 |
| AC-04 | 锁定态与解雇按钮列宽一致，布局不跳动 |
| AC-05 | 列表超过可用高度时滚动 |
| AC-06 | 完成解雇按钮固定在左卡片底部，不覆盖列表行 |
| AC-07 | 右侧市场卡片不因本刀发生布局或逻辑回退 |
| AC-08 | 未修改禁止范围文件 |
| AC-09 | GUI startup / 相关聚焦测试通过，或记录非本任务失败 |
| AC-10 | 提交 Runtime Screenshot；测试通过不得替代截图验收 |

## 10. 测试策略

建议 DA 执行：

```text
py -3.10 -m pytest -p no:cacheprovider src\tests\test_gui\test_qml_startup.py -q
py -3.10 -m pytest -p no:cacheprovider src\tests\test_gui -q
```

如修改测试或触及共享 QML，可补充完整回归。

## 11. 回滚计划

若修复后仍出现列表重叠或右侧市场回退：

1. 停止继续加码修补。
2. 回退本刀对 `ForumStage.qml` 的修改。
3. 记录 Runtime Screenshot。
4. 由 SA/PM 重新判断是否需要更细粒度 Layout Contract。

## 12. DA 交付件

DA 必须提交：

- `GUI-P0-03R1_S4A_ForumStage_LeftList_DA实施报告.md`
- Runtime Screenshot 路径
- 修改文件清单
- 测试结果
- Context Watermark

## 13. 直接退回条件

出现以下任一情况直接 RETURN：

- 人物姓名、属性、按钮仍重叠。
- 底部按钮覆盖列表行。
- 修改了禁止范围文件。
- 顺手修改右侧市场、DTO、ContextPanel 或步骤条。
- 未提交 Runtime Screenshot 却声明视觉通过。
