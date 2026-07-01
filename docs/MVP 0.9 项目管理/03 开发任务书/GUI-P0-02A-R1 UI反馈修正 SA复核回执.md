# GUI-P0-02A-R1 UI反馈修正 SA复核回执

日期：2026-07-01
复核对象：CGT-01
复核角色：SA-01 / 系统架构师

## Decision

CONDITIONAL_PASS / READY_FOR_MANUAL_VISUAL_CHECK

## 结论

CGT-01 对 GUI-P0-02A-R1 的代码与自动化测试交付通过 SA 技术复核。阶段导航顺序、阶段主标题和顶部国库标签均已按项目负责人 UI 反馈修正，并保留 GUI-P0-02A 的主壳、阶段容器、i18n 预留和人口阶段真实切片边界。

根据 2026-07-01 项目负责人新决策，CGT-01 后续不再被强制要求提交 GUI 截图；本轮最终视觉验收改由项目负责人或 SA 在真实 Windows GUI 窗口中人工确认。因此本回执不以 CGT-01 截图为最终视觉依据。

## 复核要点

- 左侧阶段导航 DTO 顺序已修正为：`mortality, revenue, forum, population, senate, combat, resolution`。
- 玩家可见阶段顺序应为：`天命-收入-广场-人口-元老院-战争-决算`。
- `combat` 主标题为 `战争`，海战保留在 subtitle / description。
- `resolution` 主标题为 `决算`，革命检查保留在 subtitle / description。
- 顶部状态栏国库资金不再裸显，改为通过 `GuiText.treasuryPrefix` 显示 `国库 ` 标签。
- 派系资金标签集中到 `GuiText.factionTreasuryPrefix`，显示为 `派系金库 `。
- 未发现本轮改动触碰 `src/core/`、`src/ui/commands/`、`src/ui/processors/`、`src/api/game_api.py`。
- 既有无关 XLSX 修改仍未纳入本任务复核范围。

## Files reviewed

- `src/api/session_api.py`
- `src/ui/gui/qml/i18n/GuiText.qml`
- `src/ui/gui/qml/shell/TopStatusBar.qml`
- `src/tests/test_gui/test_session_api.py`
- `src/tests/test_gui/test_qml_startup.py`
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A-R1 UI反馈修正 开发验收报告 - CGT-01.md`

## 开发规范同步

已按项目负责人要求更新 GUI 开发规范：

- `docs/MVP 0.9 项目管理/P1功能最小可用GUI开发与验收标准.md`
  - 版本更新为 `V1.1`。
  - 新增 `GUI 人工视觉验收规则`。
  - 明确 CGT-01 不再被强制要求提交 GUI 截图。
- `docs/MVP 0.9 项目管理/AI开发任务模板.md`
  - 新增 `GUI截图与人工视觉验收规则`。
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A GUI主壳与阶段导航扩展 技术开发任务书 - CGT-01.md`
  - 追加 2026-07-01 截图交付规则修订附录。
- `docs/MVP 0.9 项目管理/03 开发任务书/GUI-P0-02A-R1 UI反馈修正任务书 - SA-01.md`
  - 追加 2026-07-01 截图要求修订附录。

## Test status

SA 已复跑：

```text
src/tests/test_gui: 20 passed in 1.54s
src/tests/test_api/test_population_api.py + src/tests/test_commands/test_phase_population.py: 50 passed in 0.42s
full src/tests: 745 passed in 9.35s
git diff --check: passed，仅 CRLF 工作区换行提示，无空白错误
```

## Manual visual verification required

请项目负责人或 SA 在真实 Windows GUI 窗口中人工确认：

1. 左侧导航从上到下显示 `天命-收入-广场-人口-元老院-战争-决算`。
2. 顶部资金栏显示 `国库 142 T` 或等价清晰标签。
3. `派系金库` 标签清晰可读。
4. 中文显示正常，无方块字。
5. 主壳布局无明显重叠、遮挡或关键控件不可达。
6. 人口阶段真实切片仍可打开并继续操作。

人工视觉确认通过后，本任务可进入 Git 归档授权节点。

## Architecture risks

- GUI-P0-02A 仍只扩展主壳与阶段导航，不执行未迁移阶段业务，符合任务边界。
- `session_api.resolve_population_slice()` 中既有 API -> UI processor 历史依赖未在本轮扩大处理，仍建议登记为后续 GUI/API 边界技术债。
- 截图自动化仍可保留为辅助工具，但不再作为 CGT-01 必交付物或视觉验收依据。