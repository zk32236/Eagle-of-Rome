# 任务书 — GUI-P0-02-H0.3

**任务编号：** GUI-P0-02-H0.3  
**任务名称：** Phase 1 Visual Regression Fix — Central Content Opacity & Layout Reset  
**任务类型：** Visual Calibration  
**优先级：** P0  
**目标版本：** Phase 1 视觉可达标  

---

## 一、任务背景

H0.2 视觉校准后，实测截图（`GUI acutal phase 1 - 4.PNG`）与设计目标（`GUI design - Phase 1.PNG`）仍存在显著差距。GPT 出具的差异报告 `EOR_GUI_Visual_Diff_Report_Phase1.md` 明确了 20 项差异，其中 4 项 P0 阻塞级问题集中在：

1. **中央内容大面积淡化/透明** — 阶段编号、标题、步骤条接近不可读
2. **垂直布局错误** — 内容被分散到中部/底部，顶部近乎空白

根因推断（差异报告 §3）：
- 父容器可能设置了 `opacity < 1`
- 当前阶段可能误继承 `enabled: false` 或 locked/inactive 状态
- `ColumnLayout` 可能使用了 `space-between` 或错误的 `fillHeight`
- 文本颜色使用了浅色值（适用于深色背景），但容器为象牙白

## 二、任务目标

1. 修复中央区内容透明度/禁用态继承 — **P0**
2. 恢复 header → instruction → content → action 垂直顶部流式布局 — **P0**
3. 步骤条恢复清晰可见，位于标题下方 — **P0**
4. 信息卡归位到步骤条下方，不独占顶部 — **P1**
5. 主按钮宽度缩减至接近目标（约 180×34）— **P1**
6. 玩家信息区修截断 — **P1**
7. 底部查询按钮顺序恢复目标顺序 — **P1**
8. 顶栏稳定度/战争数值补齐 — **P2**
9. 右侧日志区压缩冗余 — **P2**
10. 左栏内边距微调 — **P2**

## 三、依据文档

| 文档 | 用途 |
| --- | --- |
| `EOR_GUI_Development_Governance_v1.0.md` | GUI 开发治理、视觉不回退、截图门禁 |
| `EOR_GUI_SA-DA_开发任务书规范模板_v1.2.md` | 任务书规范 |
| `GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md` | 布局契约 |
| `EOR_GUI_Design_Guidelines_Codex_v4.0_v3.25.1_baseline.md` | 产品视觉基线 |
| `EOR_GUI_Visual_Diff_Report_Phase1.md` | 本任务差异来源 |
| `GUI design - Phase 1.PNG` | 设计目标截图 |
| `GUI acutal phase 1 - 4.PNG` | 当前实测截图 |

## 四、目标截图与当前实测截图

- **目标截图：** `C:\Users\Kerl\Downloads\GUI design - Phase 1.PNG`
- **实测截图：** `C:\Users\Kerl\Downloads\GUI acutal phase 1 - 4.PNG`
- **注意：** 子代理截图存在中文乱码，仅布局粗验。正式视觉验收由人工在 IDE 中完成。

## 五-七、保持项 / 允许改项 / 禁止改项 / 风险项

| 类型 | 区域 | 要求 |
| --- | --- | --- |
| 保持项 | A 顶栏 | 62px 高度、分块 HUD、栏位顺序、无硬编码稳定度 |
| 保持项 | B 左栏 | 92px 宽度、7 pill 按钮、深墨背景 (`#14110D`) |
| 保持项 | E 底栏 | 62px 高度、12 查询入口、icon + text 形态 |
| 保持项 | H0/H0.1 测试基线 | GUI startup 7/7, full regression ≥ 773 |
| 保持项 | H0 槽位结构 | StageDesktop 四槽位启用、MortalityStage 无平行槽位 |
| 允许改项 | C 中央桌面 | 修复 opacity/disabled 继承、垂直布局重排、padding |
| 允许改项 | C-1 header | badge/title/desc 颜色和层级 |
| 允许改项 | C-2 instruction | 步骤条显隐和位置 |
| 允许改项 | C-3 content | 空状态卡位置和边距 |
| 允许改项 | C-4 action slot | 按钮宽度缩减至 180 |
| 允许改项 | D 右栏 | EventLog 间距压缩、玩家区截断修复 |
| 允许改项 | E 底栏 | 按钮顺序恢复目标顺序 |
| 允许改项 | A 顶栏 | 补齐稳定度/战争数值显示 |
| 允许改项 | B 左栏 | 内部边距微调 |
| 禁止改项 | Core/System/Service/Entity | 不得修改 |
| 禁止改项 | Store/API | 不得扩展接口或新增字段 |
| 禁止改项 | 五区主尺寸 | 不得改变 A-F 区域位置/尺寸契约 |
| 禁止改项 | 其他阶段 | 不得修改/涉及 Population/Senate 等阶段 |
| 禁止改项 | 整体配色 | 不得更换深墨/朱红/象牙白体系 |
| 风险项 | C 区布局 | 重排垂直布局时可能破坏 H0 槽位结构 |
| 风险项 | F 主按钮 | 防止按钮底部锚定被破坏 |

## 八、A-F 区域要求

C 区是重点。目标结构应为：

```
中央桌面 (StageDesktop)
├─ stageHeaderSlot: #1/7 badge → 阶段标题 → 阶段说明 (顶部流式)
├─ stageInstructionSlot: 步骤条 执行天命 → 查看事件结果
├─ stageContentSlot: 空状态提示信息卡
├─ 留白
└─ stageActionSlot: 执行天命按钮 (底部居中, 180×34)
```

## 九、布局契约与槽位要求

保持 H0 槽位结构不变。
- `StageHeaderSlot`: visible=true, opacity=1.0, 徽章/标题/说明不透明
- `StageInstructionSlot`: visible=true, opacity=1.0, 步骤条清晰
- `StageContentSlot`: 空状态卡顶部对齐，不漂浮在中心
- `StageActionSlot`: 按钮底部居中，宽度 180

## 十、Store/API 绑定要求

本次不新增绑定。仅修复已有绑定的显示问题：
- `sessionStore.stability` → 稳定度数值（已有字段）
- `sessionStore.warCount` → 战争数值（已有字段）
- `sessionStore.mortalityEvents` → 事件列表（已有）

## 十一、视觉不回退要求

修复 C 区时必须确保：
- A/B/E 区不产生新回退
- H0 槽位结构不破坏
- 测试基线不降

## 十二、测试要求

```bash
python3 -m pytest src/tests/test_gui/test_qml_startup.py -v  # 7 passed
python3 -m pytest src/tests/ -q  # ≥773 passed
```

## 十三、截图与验收证据要求

- 子代理截图（中文乱码）→ 仅布局粗验
- 正式视觉验收 → 人工本机截图
- A-F 差异表 → 必须提交

## 十四、验收标准

| 类型 | 要求 |
| --- | --- |
| 视觉验收 | C 区 header/step/content/action 完整可见，不透明 |
| 不回退验收 | A/B/E 区无新回退 |
| 架构验收 | QML → Store 层，不越界 Core |
| 测试验收 | GUI startup 7/7, regression ≥ 773 |
| 证据验收 | A-F 差异表、修改清单、测试结果 |

## 十五、交付物

1. 修改文件清单
2. 修复摘要（逐项对应差异报告 ID）
3. A-F 区域差异表
4. GUI startup 测试 7/7
5. 回归测试 ≥ 773
6. 截图可读性说明
7. 未解决问题清单
