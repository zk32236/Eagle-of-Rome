# GUI-P0-02A-R1 UI反馈修正任务书 - SA-01

创建日期：2026-07-01
发布对象：CGT-01
发布角色：SA-01 / 系统架构师
任务类型：GUI 返修 / UI 验收反馈修正
优先级：P0

## 一、SA审查结论

Decision: RETURN_FOR_REWORK / R1_REQUIRED

CGT-01 的 GUI-P0-02A 主壳与阶段导航扩展在架构方向、测试覆盖和 i18n 预留方面总体符合任务书要求，但项目负责人提交的 UI 反馈指出两个玩家可见问题，当前不能直接作为 GUI-P0-02A 最终验收通过：

1. 左侧阶段导航显示顺序不符合项目负责人确认的 MVP0.7/P0 GUI 顺序。
2. 顶部状态栏 `142 T` 未明确标注为国库，玩家无法判断其资金归属。

本次 R1 是基于现有 GUI-P0-02A 未提交工作区的窄范围返修，不是重做主壳，不得回滚 CGT-01 已完成的主壳、阶段容器、i18n 预留和测试骨架。

## 二、依据材料

- 项目负责人 UI 反馈文档：`C:\Users\Kerl\Downloads\UI 反馈.docx`
- CGT-01 开发验收报告：`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02A GUI主壳与阶段导航扩展 开发验收报告 - CGT-01.md`
- GUI-P0-02A 技术开发任务书：`C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02A GUI主壳与阶段导航扩展 技术开发任务书 - CGT-01.md`
- 项目根：`C:\Users\Kerl\PycharmProjects\Eagle of Rome`

## 三、UI反馈原文摘要

项目负责人反馈：

1. `UI的7个阶段应该按“天命-收入-广场-人口-元老院-战争-决算”顺序从上向下排列。`
2. `界面上的142T是国库吗？请注明。`

SA 已检查反馈截图：当前 GUI 阶段导航仍显示为 `天命、人口、元老院、收入、广场、战争/海战、革命/决算`；顶部状态栏显示 `142 T` 与 `派系 10 T`，其中国库资金缺少文字标签。

## 四、允许修改范围

允许在 GUI-P0-02A 已修改范围内继续修正：

- `src/api/session_api.py`
- `src/ui/gui/session_store.py`
- `src/ui/gui/localization.py`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/ui/gui/qml/i18n/qmldir`
- `src/ui/gui/qml/shell/TopStatusBar.qml`
- `src/ui/gui/qml/shell/PhaseRail.qml`
- `src/ui/gui/qml/shell/GameShell.qml`
- `src/ui/gui/qml/shell/ContextPanel.qml`
- `src/ui/gui/qml/stages/LockedStagePlaceholder.qml`
- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_adapter.py`
- `src/tests/test_gui/test_qml_startup.py`
- 必要时新增或补充 GUI 测试文件
- 本次 R1 开发验收报告，归档到 `docs\MVP 0.9 项目管理\03 开发任务书\`

## 五、禁止事项

- 不得修改 `docs\MVP 0.9 项目管理\01_需求与版本规划\EOR MVP 1.0 目标版本规划 V1.1.xlsx`。
- 不得修改 `src/core/`、`src/ui/commands/`、`src/ui/processors/`、`src/api/game_api.py`。
- 不得改变 CLI 阶段流程、自动模式或真实 Core 阶段推进规则。
- 不得把未实现阶段伪装成已实现可操作阶段。
- 不得绕过 API、不得新增 GUI 对 Core 私有字段的直接访问。
- 不得移除 GUI-P0-02A 已建立的 i18n key / 文案集中边界。
- 不得自行提交 Git。

## 六、实现要求

### 1. 修正 GUI 阶段导航显示顺序

左侧阶段导航必须按以下顺序从上向下展示：

| 序号 | phase id | 显示名 |
| --- | --- | --- |
| 1 | `mortality` | `天命` |
| 2 | `revenue` | `收入` |
| 3 | `forum` | `广场` |
| 4 | `population` | `人口` |
| 5 | `senate` | `元老院` |
| 6 | `combat` | `战争` |
| 7 | `resolution` | `决算` |

要求：

- 修改 `session_api.get_session_snapshot()` / `_phase_definitions()` 的 GUI 导航 DTO 顺序，使 GUI Store 和 QML 均消费同一顺序。
- `combat` 的主显示名应为 `战争`；海战可保留在 subtitle 或 description 中。
- `resolution` 的主显示名应为 `决算`；革命可保留在 subtitle 或 description 中。
- 不要求也不得改变底层 CLI/Core 的阶段执行顺序；本次只修正 GUI 主壳导航展示顺序和 placeholder 信息。
- 人口阶段仍是当前唯一真实可操作切片，其他阶段仍为只读 placeholder。

### 2. 顶部状态栏补充国库标签

当前顶部状态栏类似 `142 T` 的显示必须明确标注为国库资金。

推荐显示：

```text
国库 142 T    派系金库 10 T
```

或：

```text
国库：142 T    派系金库：10 T
```

要求：

- `TopStatusBar.qml` 不应继续裸显示 `(sessionStore.treasury || 0) + " T"`。
- 国库、派系金库相关文字应进入 `GuiText.qml` 或既有 GUI 文案集中层，不要新增散落硬编码。
- 保持后续多语言扩展边界：本轮默认 zh-CN 即可，不要求实现运行时语言切换。
- 如果空间不足，优先保证“国库”二字可见，不得只用图标表达资金归属。

### 3. 更新测试

至少补强以下断言：

- Session snapshot 的 `phase_navigation` id 顺序为：
  `mortality, revenue, forum, population, senate, combat, resolution`
- Session snapshot 的阶段显示名顺序为：
  `天命, 收入, 广场, 人口, 元老院, 战争, 决算`
- QML startup 或 GUI adapter 测试能确认阶段导航数量仍为 7，且最后阶段显示为 `决算`。
- 如测试条件允许，补充 `GuiText` 或 `TopStatusBar` 的国库标签存在性检查；至少应通过截图/人工检查在报告中明确确认。

## 七、测试要求

请执行并在报告中记录结果：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_gui" -q
```

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_api\test_population_api.py" -q
```

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests\test_commands\test_phase_population.py" -q
```

如无环境阻塞，请继续执行全量回归：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "src\tests" -q
```

并执行：

```powershell
git diff --check
```

截图要求：

- 运行 `gui_screenshot.py` 生成 1440 和 1280 截图。
- 若截图文件是已跟踪文件，不要默认纳入提交范围；可复制到临时验收目录并在报告中写明路径。
- 报告中必须明确截图/真实窗口检查结果：左侧顺序是否为 `天命-收入-广场-人口-元老院-战争-决算`，顶部是否显示 `国库 142 T` 或等价标签。

## 八、验收标准

SA 后续验收至少检查：

- GUI 左侧 7 阶段顺序完全符合项目负责人反馈。
- `战争/海战` 不再作为阶段主标题，主标题应为 `战争`。
- `革命/决算` 不再作为阶段主标题，主标题应为 `决算`。
- 顶部国库资金不再裸显，必须有 `国库` 标签。
- 已有 GUI-P0-02A 架构边界不退化。
- `src/tests/test_gui`、人口 API、人口命令回归通过；全量测试如未执行，必须说明原因。
- 不触碰预先存在的 XLSX 修改。

## 九、交付物

请 CGT-01 交付：

1. 修改文件清单。
2. 实现摘要。
3. 阶段顺序修正说明。
4. 国库标签修正说明。
5. i18n 边界保持说明。
6. 测试命令与结果。
7. 截图路径与视觉确认结果。
8. 风险与遗留问题。
9. 开发验收报告，归档为：
   `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-02A-R1 UI反馈修正 开发验收报告 - CGT-01.md`

完成后请在 CGT-01 线程回执：`READY_FOR_SA_REVIEW`。不要自行提交 Git。
## 附录：2026-07-01 截图要求修订

根据项目负责人最新决策，本 R1 及后续 GUI 任务不再要求 CGT-01 提交 GUI 截图作为必交付物。上文涉及 `gui_screenshot.py`、截图路径或截图材料的条目统一改为可选辅助材料。

CGT-01 必须保留并报告自动化测试、QML 启动验证、DTO/API 断言和手工验证步骤；最终 GUI 视觉判断由项目负责人或 SA 在真实 Windows GUI 窗口中人工完成。本次 R1 的最终验收重点为：左侧阶段顺序、顶部国库标签、中文正常显示、布局无明显重叠和人口阶段切片可继续操作。
