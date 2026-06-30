# AS-P1-01 API Response 统一 PM任务意图包

## 一、任务基本信息

| 项目 | 内容 |
| --- | --- |
| 任务编号 | AS-P1-01 |
| 任务名称 | API Response 统一 |
| 任务类型 | P1 前置架构清理 / API 一致性整改 |
| 优先级 | P1 |
| 目标阶段 | MVP 0.9 / MVP 1.0 P1 功能开发前置 |
| PM 判断 | 建议作为 GUI-P0-01 后第一个 P1 前置清理任务 |
| GUI 分级 | C 类：底层支撑任务，不要求新增 GUI 页面 |

## 二、任务目标

请 SA 先审查当前 `src/api` 层的返回结构与响应构造方式，明确统一边界、兼容要求和可修改范围，再据此定稿面向开发执行 Agent 的技术任务书。

本任务的目标不是新增玩法，而是统一 API 层响应格式来源，避免后续 P1 功能继续复制多套 `{success, message, data, errors}` 返回构造逻辑。

## 三、背景说明

当前项目已经完成：

- AS-P0-01 `PoliticalSystem` 重构。
- AS-P0-02 `EconomicService` 重构。
- AS-P0-03 私有字段访问收束第一批。
- AS-P0-04 广场阶段土地交易 API 化收尾。
- GUI-P0-01 MVP0.7 可玩 GUI 原型。
- 代码与文档统一仓库基线。

后续将进入 P1 功能增量开发，并采用“功能实现 + 最小可用 GUI 同步交付”模式。P1 功能将大量依赖 API 层给 CLI、GUI、自动玩家和测试提供稳定结构化结果，因此 API Response 统一应先于人物属性、经验值、忠诚度、腐败、审判、派系收买等 P1 功能展开。

## 四、当前协作与路径基线

| 类型 | 路径 |
| --- | --- |
| 唯一项目根 / Git 根 / 代码根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome` |
| 正式文档根 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs` |
| PM 任务书归档 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书` |
| SA/开发任务与验收归档 | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书` |
| Python 解释器 | `C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe` |
| 测试框架 | `pytest` |
| 当前正式基线提交 | `9d126ea Update unified repository collaboration baseline` |

`E:\Eagle of Rome` 仅作为旧文档工作区 / 历史来源，不再作为本任务正式归档路径。

## 五、依据文档

请 SA 优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\后续任务池.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\MVP0.7模块开发优先级表.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\P1功能最小可用GUI开发与验收标准.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\文档-代码一致性审计清单.md`

## 六、PM 级任务意图

本任务希望解决的问题：

1. API 层返回结构来源不完全统一，后续 P1 功能容易复制旧模式。
2. GUI Session/API 已经开始依赖结构化结果，返回格式漂移会增加 GUI 增量开发成本。
3. P1 功能涉及政治、经济、人物、派系、审判等多个 API 入口，需要提前统一成功、失败、错误和数据载荷的表达方式。
4. 本任务可作为 P1 阶段第一个低风险技术校准任务，帮助 SA/开发执行 Agent 在统一仓库基线上恢复协作节奏。

PM 期望结果：

- SA 明确当前 `src/api` 层是否已有统一 `api_response` 或等价入口。
- SA 明确哪些 API 文件需要迁移，哪些历史返回差异必须保留兼容。
- 开发执行后，API 层对外函数名、调用方式和既有测试语义不退化。
- CLI、GUI、自动玩家和多玩家权限隔离不受影响。

## 七、建议 SA 审查重点

请 SA 在定稿技术任务书前重点审查：

1. `src/api/__init__.py` 是否应作为统一响应构造入口。
2. `forum_api.py`、`senate_api.py`、`population_api.py`、`game_api.py`、`session_api.py` 等文件是否存在重复响应构造。
3. 现有 API 返回结构是否全部满足 `{success, message, data, errors}`。
4. 是否存在 GUI 或 CLI 依赖的历史特殊字段，不能在本任务中破坏。
5. 是否需要新增或调整 focused tests 来锁定失败返回、权限失败、非法操作和 GUI Session 调用。
6. 是否需要同步函数索引或架构文档。

## 八、允许修改范围建议

最终范围由 SA 定稿。PM 建议允许范围如下：

| 范围 | 说明 |
| --- | --- |
| `src/api/` | 统一 API 响应构造入口与各 API 模块调用方式 |
| `src/tests/test_api/` | 补齐或调整 API 返回结构测试 |
| `src/tests/test_gui/` | 如涉及 GUI Session API，补充不退化测试 |
| `src/tests/test_commands/` | 如 CLI 命令层依赖响应结构，补充回归测试 |
| `docs/MVP 0.9 项目管理/03 开发任务书` | SA 技术任务书、验收回执和开发验收报告归档 |

## 九、禁止事项

本任务不得扩大为玩法开发或 API 重设计。

明确禁止：

- 不得新增 P1 玩法。
- 不得改变现有公共 API 函数名，除非 SA 明确批准并要求兼容层。
- 不得让 UI/GUI 直接绕过 API 调用 Core/System/Service。
- 不得把业务规则下沉或上移到错误层级。
- 不得改变 CLI 玩家可见流程。
- 不得破坏 GUI-P0-01 人口阶段可玩切片。
- 不得破坏自动玩家流程。
- 不得破坏多玩家权限与信息隔离。
- 不得做无关格式化、大范围重命名或目录重组。

## 十、实现要求建议

开发任务书由 SA 定稿时，建议至少包含：

1. 明确统一响应构造函数或工厂的所在模块。
2. 所有迁移后的 API 响应仍保持 `{success, message, data, errors}` 基本结构。
3. 对历史调用方保持兼容，尤其是 CLI 命令层、GUI Session API 和现有测试。
4. 错误列表、消息文本和数据载荷的兼容策略由 SA 明确，不交给开发执行 Agent 自行判断。
5. 若发现响应格式以外的 API 职责问题，应登记为后续技术债，不在本任务中扩大处理。

## 十一、调试日志要求

本任务默认不要求新增运行期日志。

如 SA 发现某些 API 错误路径缺少可观测性，可要求开发执行 Agent 补充轻量 DEBUG 或测试断言，但不得为了日志而改变业务行为。

## 十二、测试要求建议

SA 定稿时应要求至少覆盖：

| 测试类型 | 要求 |
| --- | --- |
| API focused tests | 覆盖成功响应、失败响应、权限失败、非法输入 |
| GUI regression | 保证 GUI-P0-01 Session/API 相关测试不退化 |
| CLI regression | 保证命令层读取 API 返回结构不退化 |
| Full regression | 全量 `src/tests` 应通过 |

建议基础测试命令：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
```

当前基线参考：`734 passed`。

## 十三、验收标准

| 类别 | 标准 |
| --- | --- |
| 架构 | API 响应构造来源统一，未新增 UI/API/Core 反向依赖 |
| 兼容 | 现有 API 函数名、CLI 流程、GUI Session 调用和自动玩家行为不退化 |
| 数据结构 | API 返回保持 `{success, message, data, errors}` 基本结构 |
| 测试 | SA 指定测试与全量测试通过，或失败项有明确非本任务原因 |
| 文档 | 如公共接口或响应约定发生变化，SA 明确是否需要同步文档/函数索引 |

## 十四、交付物

本 PM 任务意图包暂不直接发送给 SA。

待项目负责人确认后，PM 可将本任务意图包发送给 SA。SA 后续应输出：

- `AS-P1-01 API Response 统一 边界审查报告 - SA-01.md`
- `AS-P1-01 API Response 统一 技术开发任务书.md`
- 开发完成后的 SA 验收回执

开发执行 Agent 后续应输出：

- 修改文件清单。
- 实现摘要。
- 测试命令与结果。
- 风险与遗留问题。
- 是否建议提交 Git。

## 十五、PM 当前结论

`AS-P1-01 API Response 统一` 建议作为 GUI-P0-01 后的第一个 P1 前置技术任务。它不直接增加玩家玩法，但能降低后续 P1 功能与最小 GUI 同步交付时的 API 漂移风险。
