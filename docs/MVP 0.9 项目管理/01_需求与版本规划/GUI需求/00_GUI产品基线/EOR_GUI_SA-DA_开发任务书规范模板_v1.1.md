# EOR GUI SA-DA 开发任务书规范模板 v1.1

日期：2026-07-11  
版本定位：替代 `EOR_GUI_DA_开发任务书规范模板_v1.0` 作为后续 GUI 任务书主规范  
适用对象：SA 编写 GUI 任务书、DA 执行 GUI 实现、Codex/OC 做 GUI 验收  
目标：将 v3.25.1 HTML 原型从“视觉参考”升级为“可执行布局契约”，降低 DA 自由解释空间。

## 一、升级原因

v1.0 已要求 SA 在 GUI 任务书中加入目标截图、固定视口、区域编号、视觉不可偏移清单和截图自查表。  
但 Phase 1 Visual Calibration 的实际执行结果仍然出现明显结构漂移：

- 顶栏被实现为一条扁平红条，缺少 v3.25.1 的分块 HUD 结构。
- 左侧阶段导航变成浅色空白栏和圆形图标，偏离目标的深色窄轨道按钮。
- 中央区域虽然变成大面积浅色，但顶部仍被深色公告区切开，没有形成完整象牙白阶段桌面。
- 右侧栏内容顺序与层级仍不稳定，事件日志占比过大。
- 底部查询栏更像临时工具条，缺少目标稿的按钮节奏和图标文字语义。

结论：仅靠自然语言描述和截图参考，不足以保证 DA 精准复刻 GUI。后续 SA 必须在任务书之前或任务书内提供工程化布局约束。

## 二、v1.1 新增硬规则

从本版本开始，GUI 任务书不得直接进入“按图实现”。必须先完成以下三件事：

1. 输出布局契约。
2. 输出静态 QML Shell 骨架。
3. 明确 DA 只能在指定槽位内填充内容和绑定 Store/API。

也就是说，DA 的角色从“自由搭建页面”调整为“在 SA 定义的结构内实现细节”。

## 三、GUI 任务分层

后续 GUI 任务必须拆成四层，不能混在一个大任务中交给 DA：

| 层级 | 名称 | 负责人 | 目标 | 是否允许接功能 |
| --- | --- | --- | --- | --- |
| L0 | 布局契约 | SA/OC | 从 HTML/截图提取区域尺寸、颜色、间距、锚点 | 否 |
| L1 | 静态 Shell 骨架 | SA/DA | 建立固定 QML 组件树和槽位 | 否 |
| L2 | 阶段内容填充 | DA | 在槽位内填充阶段 UI | 仅允许展示状态 |
| L3 | Store/API 绑定 | DA | 绑定按钮、状态、日志、错误反馈 | 是 |

如果 L0/L1 未完成，不应启动 L2/L3。

## 四、布局契约必填模板

SA 发布任何 GUI 页面任务前，必须提供 `GUI_LAYOUT_CONTRACT_<Phase>_v3.25.1.md`。

布局契约至少包含：

| 项目 | 必填内容 |
| --- | --- |
| 基准视口 | 例如 1440x900 |
| 页面总背景 | 颜色、边框、外边距 |
| A 顶栏 | x/y/height、左右边距、状态块数量、顺序、宽度规则 |
| B 左栏 | x/y/width/height、背景色、按钮尺寸、按钮间距、图标文字布局 |
| C 中央桌面 | x/y/width/height、背景色、边框、圆角、内部 padding |
| D 右栏 | x/y/width/height、分区顺序、每区标题和高度规则 |
| E 底栏 | x/y/height、按钮数量、按钮宽度、间距、图标文字关系 |
| F 主操作 | 所属区域、相对锚点、尺寸、启用/禁用表现 |
| 颜色 token | 背景、HUD、边框、标题、正文、强调、禁用 |
| 字体 token | 品牌、标题、正文、说明、数值、按钮 |
| 禁止偏移 | 哪些区域不得改变顺序、颜色、层级和锚点 |

布局契约中的尺寸可以是绝对值，也可以是相对公式，但必须能让 DA 在 QML 中直接落地。

示例写法：

```text
基准视口：1440x900
A 顶栏：x=14, y=12, w=1414, h=62
B 左栏：x=14, y=84, w=92, h=734
C 中央桌面：x=116, y=84, w=1018, h=734
D 右栏：x=1144, y=84, w=284, h=734
E 底栏：x=14, y=826, w=1414, h=62
F 主操作：归属 C，bottom=14，horizontalCenter=C.horizontalCenter
```

## 五、静态 QML Shell 骨架要求

SA/DA 必须先建立或确认以下 Shell 组件骨架：

```text
AppShell.qml
  TopStatusBar.qml
  PhaseRail.qml
  StageDesktop.qml
    StageHeaderSlot
    StageInstructionSlot
    StageContentSlot
    StageActionSlot
  RightStatusPanel.qml
    CurrentPhaseSection
    OperationSection
    ProgressSection
    PlayerSection
    EventLogSection
  BottomQueryBar.qml
```

骨架阶段只允许做：

- anchors
- width / height
- spacing
- padding
- background
- border
- radius
- font token
- color token
- slot 命名

骨架阶段不允许做：

- 阶段业务规则
- API 调用
- Core/System/Service 修改
- 随机事件逻辑
- 查询功能扩展
- 临时重排主区域

## 六、DA 槽位填充规则

DA 只能在 SA 指定槽位内填充内容。

| 槽位 | 允许内容 | 禁止内容 |
| --- | --- | --- |
| `StageHeaderSlot` | 阶段标题、阶段说明、阶段标识 | 改变中央桌面背景结构 |
| `StageInstructionSlot` | 步骤条、提示卡、操作说明 | 插入跨区域深色公告栏 |
| `StageContentSlot` | 阶段结果、表格、列表、空状态 | 改变主 Shell 布局 |
| `StageActionSlot` | 当前阶段主按钮、推进按钮 | 把主按钮放到 Shell 外部 |
| `CurrentPhaseSection` | 当前阶段名和说明 | 派系资源卡片替代当前阶段 |
| `OperationSection` | 当前可执行操作 | 业务规则判断 |
| `ProgressSection` | 流程进度、状态 | 阶段推进逻辑 |
| `PlayerSection` | 当前玩家、派系、人物数 | 跨玩家信息泄漏 |
| `EventLogSection` | GUI 事件日志 | 直接读取 Core 私有字段 |

## 七、GUI 任务书新增必填章节

后续 SA 编写 GUI 任务书时，在 v1.0 基础上必须新增以下章节：

### 1. 布局契约引用

必须写明：

- 布局契约文件路径
- 目标截图路径
- HTML 原型路径
- 基准视口
- 本任务允许偏移范围

示例：

```text
本任务必须遵守：
- GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md
- GUI design - Phase 1.PNG
- EOR_GUI_Prototype_v3.25.1.html

基准视口：1440x900
允许误差：主区域位置与尺寸误差不超过 8px；颜色必须使用 token，不允许近似自选。
```

### 2. Shell 骨架引用

必须写明本任务基于哪些 QML 骨架文件开发：

```text
本任务不得重建主布局，只允许在以下组件槽位内实现：
- StageDesktop.StageHeaderSlot
- StageDesktop.StageInstructionSlot
- StageDesktop.StageContentSlot
- StageDesktop.StageActionSlot
- RightStatusPanel.OperationSection
- RightStatusPanel.EventLogSection
```

### 3. 禁止重新组织主布局

必须写明：

```text
DA 不得改变 TopStatusBar、PhaseRail、StageDesktop、RightStatusPanel、BottomQueryBar 的父子关系、主锚点、区域顺序和主尺寸规则。
```

### 4. 像素级验收表

每个 GUI 任务必须附以下表格：

| 区域 | 契约值 | 实际值 | 误差 | 是否通过 |
| --- | --- | --- | --- | --- |
| A 顶栏 x/y/w/h |  |  |  |  |
| B 左栏 x/y/w/h |  |  |  |  |
| C 中央桌面 x/y/w/h |  |  |  |  |
| D 右栏 x/y/w/h |  |  |  |  |
| E 底栏 x/y/w/h |  |  |  |  |
| F 主操作位置 |  |  |  |  |

## 八、识图模型的正确使用位置

识图模型可以使用，但只作为辅助验收，不作为主实现路径。

推荐位置：

1. DA 提交截图后，使用识图模型生成差异清单。
2. SA/Codex 将差异映射回布局契约。
3. 只有当差异属于契约缺失时，才修改契约。
4. 如果契约已写明而 DA 未遵守，则直接返修。

不推荐：

- 每轮都把截图差异转成自然语言，让 DA 继续自由调整。
- 用识图模型替代布局契约。
- 用“看起来接近”作为验收结论。

## 九、Phase 1 下一步建议任务拆分

当前 Phase 1 不建议继续直接返修 QML。建议改为以下任务序列：

### GUI-P0-02-F：Phase 1 布局契约提取

目标：

- 从 v3.25.1 HTML 与目标截图中提取 1440x900 下的 A-F 区域布局参数。
- 输出 `GUI_LAYOUT_CONTRACT_Phase1_v3.25.1.md`。

禁止：

- 不改 QML。
- 不接 Store/API。
- 不改 Core/API。

交付：

- 布局契约文档。
- 目标截图区域标注说明。
- 颜色和字体 token 初表。

### GUI-P0-02-G：Phase 1 静态 QML Shell 骨架

目标：

- 按布局契约建立 Shell 主组件和槽位。
- 在 1440x900 下先实现静态视觉结构。

禁止：

- 不接阶段功能。
- 不实现随机事件。
- 不改变 Core/API。

交付：

- QML Shell 骨架文件。
- 1440x900 实际截图。
- 像素级验收表。

### GUI-P0-02-H：Phase 1 天命内容填充与 Store/API 绑定

目标：

- 在已固定 Shell 槽位内填充天命阶段内容。
- 绑定 `GuiSessionStore` 与 `GuiApiAdapter.doAdvanceMortality()`。

禁止：

- 不重排 Shell 主布局。
- 不改布局契约。
- 不绕过 Adapter/Store。

交付：

- 功能截图。
- 状态绑定表。
- 测试结果。

## 十、直接退回条件 v1.1

除 v1.0 退回条件外，新增：

1. 没有布局契约就进入 QML 编码。
2. 没有静态 Shell 骨架就直接接功能。
3. DA 修改了 Shell 主组件父子关系或主锚点。
4. DA 在未获授权的情况下改变 A-F 区域尺寸规则。
5. DA 只提交截图，不提交像素级验收表。
6. DA 以“视觉接近”为理由跳过契约差异。
7. SA 任务书未指定 DA 可填充的具体槽位。

## 十一、SA 发布前最终检查清单 v1.1

- [ ] 是否已有布局契约文件。
- [ ] 是否已有或要求先产出静态 QML Shell 骨架。
- [ ] 是否明确 DA 只能在指定槽位内开发。
- [ ] 是否禁止 DA 重排主 Shell。
- [ ] 是否给出基准视口和允许误差。
- [ ] 是否要求像素级验收表。
- [ ] 是否把识图模型定位为验收辅助，而非实现主路径。
- [ ] 是否将视觉校准任务与功能绑定任务分开。
- [ ] 是否保留 UI -> API -> Core/System/Service -> Entity 依赖方向。
- [ ] 是否禁止 QML 复制业务规则。

## 十二、一句话原则

v1.0 解决“SA 要把要求说清楚”。  
v1.1 进一步要求“SA 要把页面结构先固定住”。  

后续 GUI 开发不应再让 DA 按图片自由复刻，而应让 DA 在布局契约和 QML 槽位中完成实现。
