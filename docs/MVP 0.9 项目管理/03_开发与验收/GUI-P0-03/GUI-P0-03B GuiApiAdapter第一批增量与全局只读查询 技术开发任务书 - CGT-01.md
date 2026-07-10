# GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 技术开发任务书 - CGT-01

## 一、任务基本信息

| 项目 | 内容 |
| --- | --- |
| 任务编号 | GUI-P0-03B |
| 任务名称 | GuiApiAdapter第一批增量与全局只读查询 |
| 执行对象 | CGT-01 |
| 任务类型 | GUI 查询能力补齐 / API-Adapter 边界收束 / DTO 与权限过滤 |
| 优先级 | P0 |
| 所属阶段 | GUI-P0-03 OPC-01 GUI重设计实施拆分 |
| 代码基线 | `d0b615d Add GUI-P0-03B PM intent package` |
| 技术边界审查 | `docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 技术边界审查报告 - SA-01.md` |

## 二、任务目标

本轮目标是在 GUI-P0-03A/R1 已完成的底部查询栏和查询浮窗基础上，补齐第一批安全只读查询入口，并统一 `GuiApiAdapter` / `GuiSessionStore` 的查询 DTO 边界。

本轮不是复杂业务动作接入，不推进阶段，不改变 Core 规则。

必须优先完成四个查询：

1. 游戏状态
2. 派系信息
3. 战争列表
4. 军团状态

其余底部按钮本轮允许继续占位。

## 三、背景说明

GUI-P0-03A 已完成 OPC 五区主壳、底部查询栏和查询浮窗。当前查询数据仍有一部分在 `GuiSessionStore._build_global_query_result()` 中拼装，后续如果继续把查询规则放在 Store，会让 GUI 层逐步理解 Core/System 细节。

本轮应把查询能力收束到：

```text
QML -> GuiSessionStore -> GuiApiAdapter -> API -> Core/System/Service/Entity
```

其中 QML 只展示 DTO，Store 只负责保存查询结果和触发信号，Adapter 只负责调用 API 和响应格式适配，API 负责权限过滤和 DTO 构建。

## 四、依据文档

请优先参考：

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书\GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 PM任务意图包.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 技术边界审查报告 - SA-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03A OPC主壳骨架落地 技术开发任务书 - CGT-01.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\EOR_UI_API_Mapping.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\01_需求与版本规划\GUI需求\GUI_Code_Alignment_Audit.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\AGENTS.md`
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md`

## 五、允许修改范围

| 范围 | 说明 |
| --- | --- |
| `src/api/gui_query_api.py` | 推荐新增，只读 GUI 查询 API |
| `src/api/session_api.py` | 仅允许必要 DTO 辅助，不建议扩大 |
| `src/ui/gui/api_adapter.py` | 新增统一只读查询 wrapper |
| `src/ui/gui/session_store.py` | `doGlobalQuery()` 改为委托 Adapter/API，移除具体查询拼装 |
| `src/ui/gui/localization.py` | 新增查询文案 key |
| `src/ui/gui/qml/i18n/GuiText.qml` | 新增查询浮窗/按钮必要文案 key |
| `src/ui/gui/qml/shell/BottomQueryBar.qml` | 如需调整按钮状态或提示 |
| `src/ui/gui/qml/shell/QueryResultOverlay.qml` | 如需适配更完整 DTO |
| `src/tests/test_api/test_gui_query_api.py` | 新增 API 测试 |
| `src/tests/test_gui/test_adapter.py` | 更新 Adapter/Store 查询测试 |
| `src/tests/test_gui/test_qml_startup.py` | 更新 QML/边界/i18n 测试 |
| `docs\MVP 0.9 项目管理\03 开发任务书` | 开发验收报告 |

如确实不新增 `gui_query_api.py`，必须在开发报告中说明替代边界，并证明没有扩大 `game_api.py` 依赖。

## 六、禁止事项

1. 不得接入元老院提案、投票、否决、结算、战争接管、停战、预算、总督任命。
2. 不得接入广场招募、竞标、土地交易、凯旋投票、广场结算。
3. 不得接入战争执行、海战执行、战斗结算。
4. 不得接入收入结算、收入确认、决算推进、年度推进。
5. 不得让 GUI/QML/Store/Adapter 调用 CLI Command。
6. 不得调用 `game_api.execute_phase()` 或 `game_api.execute_turn()`。
7. 不得调用或导入 `CombatCommand`。
8. 不得在 QML 或 Store 直接读取 Core/System/Entity。
9. 不得读取或修改 Core 私有字段。
10. 不得裸显他派金库、人物私产、隐藏投票、隐藏竞标信息或未公开战争细节。
11. 不得新增行内 UI 文案硬编码。
12. 不得提交 Git。

## 七、实现要求

### 7.1 查询 API

推荐新增：

```text
src/api/gui_query_api.py
```

建议接口：

```python
def get_global_query_result(state: GameState, viewer_player_id: str, query_id: str) -> dict:
    ...
```

返回必须使用统一 API response：

```python
{
    "success": bool,
    "message": str,
    "data": {
        "id": str,
        "title": str,
        "title_key": str,
        "status": "connected" | "readonly" | "placeholder",
        "message": str,
        "message_key": str,
        "message_params": dict,
        "items": [
            {
                "label": str,
                "label_key": str,
                "value": str,
                "meta": dict
            }
        ],
        "summary": dict
    },
    "errors": list
}
```

### 7.2 Adapter / Store

- `GuiApiAdapter` 新增统一方法，例如 `get_global_query_result(viewer_id, query_id)`。
- `GuiSessionStore.doGlobalQuery(query_id)` 必须调用 Adapter，不再自己拼装游戏状态、派系、战争、军团的明细。
- `GuiSessionStore` 可以保留 `_placeholder_query()`，但推荐由 API 统一返回 placeholder DTO。
- `QueryResultOverlay.qml` 应继续只消费 `sessionStore.globalQueryResult`。

### 7.3 四个首批查询

#### 游戏状态

必须包含安全摘要，例如：

- 年份
- 回合
- 当前权威阶段
- 当前玩家
- 国库
- 在世人物数
- 派系数

不得通过 `game_api.execute_phase()` 或 CLI command 获取。

#### 派系信息

必须按 viewer 过滤：

- viewer 所属派系：可显示派系金库、成员数、总影响力等。
- 其他派系：只显示公开概览，例如名称、成员数、影响力；不得显示 treasury。

必须有测试覆盖“不会暴露其他派系 treasury”。

#### 战争列表

必须通过 `WarSystem` 公共查询方法或既有公开 API/DTO 获取，不得读取 `_active_wars`、`_threats`、`_truce_wars` 等私有字段。

允许展示：

- 战争 id/name
- status
- threat_level
- naval_required
- commander public summary

不得执行战斗，不得调用 `CombatCommand`。

#### 军团状态

必须通过 `MilitarySystem` 公共查询方法获取，不得读取 `_legions` 私有字段。

允许展示：

- 总数
- active / available / assigned / destroyed 等计数
- 军团编号、状态、是否分配战争的公开摘要

不得征召、解散、分配或召回军团。

### 7.4 其余按钮

其余按钮本轮允许继续占位，但占位 DTO 必须统一：

- `status = "placeholder"`
- 文案集中化
- 明确 handoff task 或后续任务

### 7.5 i18n

新增 UI 文案必须通过 `GuiText.get("key")` 或等价集中调用。

允许：

- `GuiText.qml` 集中属性/函数
- `localization.py` key
- 可迁移到后续 JSON 语言包的 key

禁止新增 QML 行内中文/英文 UI 文案。

## 八、调试日志要求

- 查询失败时应通过 Adapter 返回结构化 `errors`，并在 GUI feedback 中可见。
- API 可以记录轻量 debug log，但不得打印到 stdout。
- 不得让查询失败污染 Core 状态。

## 九、测试要求

CGT-01 至少执行并报告：

```powershell
cd "C:\Users\Kerl\PycharmProjects\Eagle of Rome"
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api\test_gui_query_api.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\test_adapter.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui\test_qml_startup.py" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_gui" -q
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
git diff --check
```

必须执行并报告边界扫描：

```text
game_api.execute_phase
game_api.execute_turn
CombatCommand
phase_senate
phase_forum
phase_revenue
phase_combat
_active_wars
_threats
_truce_wars
_legions
```

必须执行 i18n 硬编码扫描，确认新增/修改 QML 中没有新增行内 UI 文案硬编码。

## 十、验收标准

| 类别 | 验收标准 |
| --- | --- |
| 查询能力 | 游戏状态、派系信息、战争列表、军团状态可通过底部查询浮窗查看 |
| DTO 边界 | QML/Store 不直接拼装 Core/System 细节 |
| Adapter 边界 | 查询经 `GuiSessionStore -> GuiApiAdapter -> API` |
| 信息隔离 | 不显示他派 treasury、人物私产、隐藏投票/竞标/战争细节 |
| 动作边界 | 不新增任何状态改变型业务动作 |
| i18n | 新增 UI 文案集中管理 |
| 测试 | API/GUI/全量测试和扫描通过 |
| 交付 | 开发验收报告完整，未提交 Git |

## 十一、CGT-01 交付格式

请将开发验收报告归档到：

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书\GUI-P0-03B GuiApiAdapter第一批增量与全局只读查询 开发验收报告 - CGT-01.md
```

报告必须包含：

```text
Decision by CGT-01: READY_FOR_SA_REVIEW / BLOCKED / RETURN_FOR_SCOPE_CONFIRMATION

代码基线:

修改文件:

实现摘要:

查询按钮接入状态表:
- 游戏状态:
- 派系信息:
- 战争列表:
- 军团状态:
- 其余按钮:

API/DTO 边界说明:

信息隔离说明:

未接入内容说明:

测试结果:
- test_gui_query_api:
- test_adapter:
- test_qml_startup:
- test_gui:
- full src/tests:
- git diff --check:
- 边界扫描:
- i18n 硬编码扫描:

已知风险:

需要 SA/项目负责人确认的问题:
```

CGT-01 不得提交 Git。Git 归档由 SA 在项目负责人确认后执行。
