AS-P1-01 API Response 统一 技术开发任务书（修订版 V2）
任务编号：AS-P1-01
任务名称：API Response 统一
任务类型：P1 前置架构清理 / API 一致性整改
目标阶段：MVP 0.9 / MVP 1.0 P1 功能开发前置
SA 负责人：DSK-01
执行 Agent：待定（建议 CGT-01 或具备 API 层修改经验的 Agent）
SA 裁决结论：CONDITIONAL PASS（边界审查通过，任务书经修订后定稿）
修订版本：V2（2026-06-29，基于项目负责人复审意见修正）

一、任务目标
统一 src/api 层响应构造来源，消除各 API 模块中重复定义的 api_response，确保所有 API 返回结构统一来自 src.api.__init__ 中的唯一工厂函数。

明确不涉及：

新增玩法或业务逻辑。

修改公共 API 函数名或调用签名（除非必要且需保持兼容）。

UI/GUI 绕过 API 直接调用 Core/System/Service。

二、当前架构基线
API 目录构成：src/api/ 下共 10 个功能模块 + __init__.py：

模块	状态
__init__.py	✅ 定义统一 api_response
forum_api.py	❌ 本地重复定义了 api_response（第 14 行）
senate_api.py	❌ 本地重复定义了 api_response 及 _wrap_result（第 17 行）
population_api.py	✅ 从 src.api 导入
figure_api.py	✅ 从 src.api 导入
province_api.py	✅ 从 src.api 导入
contract_api.py	✅ 从 src.api 导入
game_api.py	✅ 从 src.api 导入
player_api.py	✅ 从 src.api 导入
faction_api.py	✅ 从 src.api 导入
session_api.py	✅ 从 src.api 导入
三、修改范围（明确限定）
3.1 生产代码修改范围（仅限以下文件）
文件	修改内容
forum_api.py	删除本地 api_response 定义，改为从 src.api 导入
senate_api.py	删除本地 api_response 和 _wrap_result 定义，改为从 src.api 导入，并显式解包 PoliticalSystem 返回结果
本任务生产代码不得修改任何其他 src/api/*.py 文件。

3.2 测试代码允许范围（允许新增/修改）
路径	允许操作
src/tests/test_api/test_api_response_unification.py	新增文件，验证统一响应格式
src/tests/test_api/ 下其他现有测试文件	仅允许微调断言以适配 data=None 语义，不得大规模重构
四、具体修改要求
4.1 forum_api.py 修改项
删除：第 14-21 行的本地 api_response 定义。

新增：在文件顶部导入区域添加 from src.api import api_response。

验证：确保文件中所有 api_response(...) 调用均指向统一入口。

4.2 senate_api.py 修改项
删除：第 17-26 行的本地 api_response 和 _wrap_result 定义。

新增：在文件顶部导入区域添加 from src.api import api_response。

调整：原有通过 _wrap_result(result) 包装的调用点（如 get_senate_initial_info、propose、vote、veto、resolve_senate 等），需直接调用 api_response 构造返回值。

示例（替换模式）：

python
# 原代码
return _wrap_result(_political_system(state).some_method(...))

# 替换为
result = _political_system(state).some_method(...)
return api_response(
    success=result.get("success", False),
    message=result.get("message", ""),
    data=result.get("data", {}),
    errors=result.get("errors", [])
)
注意：_wrap_result 在当前代码中表现为“重新标准化包装”，不构成嵌套结构缺陷。删除时确保显式解包不丢失 PoliticalSystem 返回的任何字段。

4.3 兼容性强制要求（针对 data 默认值）
关键差异：src.api.api_response 中 data 默认值为 None；而 forum_api.py / senate_api.py 本地版本将空 data 转为 {}（如 data or {}）。

统一后影响：原先返回 {} 的 API 调用方将收到 None。

强制要求：

不得修改 src.api.__init__.py 中的 data=None 默认值。

本任务优先通过 focused tests 验证兼容性（见第五章）。若执行 Agent 在测试过程中发现 CLI/GUI 调用方确实因 data=None 崩溃，必须立即停止并报告 SA，不得擅自扩大修改调用方代码。SA 将评估是否需额外兼容层或作为独立任务处理。

4.4 关于 errors 字段的约束
本任务不改变错误语义。

所有 API 返回必须包含 errors 键，但不强制要求非空。当前很多失败路径返回 errors=[] 是合法行为。

执行 Agent 不得为了“让错误路径看起来更完整”而凭空添加错误信息。

五、测试要求
5.1 新增 Focused Tests（必须）
在 src/tests/test_api/test_api_response_unification.py 中新增测试，至少覆盖：

格式完整性：验证 forum_api 和 senate_api 中的所有公开函数返回的字典包含 success、message、data、errors 四个键。

data 为 None 兼容性：选择现有 API 的无数据响应路径（如 faction_api.get_factions_status 在无派系时，或 contract_api.get_contracts_status 在无合同时），验证 data=None 不导致 CLI 界面或直接调用崩溃。

错误路径不退化：对 forum_api.retire_figure、senate_api.propose 等函数，在非法输入下返回 success=False 且 errors 为列表（可为空）。

5.2 回归测试（必须通过）
测试命令（沿用交接报告）：

powershell
cd "C:\Users\Kerl\PycharmProjects\Eagle of Rome"
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
验收标准：

全量测试通过。

测试数量不得少于当前基线（因新增 focused tests，总数会增加）。

若出现失败或数量异常变化，执行 Agent 必须在报告中逐项说明原因。

六、明确排除项（历史技术债，不纳入本任务）
以下两项为既有架构边界问题，本任务不得扩大处理：

编号	描述	位置
TD-AS-P1-01-001	session_api.resolve_population_slice() 直接导入 src.ui.processors.auto_player_processor，形成 API → UI 反向依赖	session_api.py:254
TD-AS-P1-01-002	game_api.py 直接导入各 CLI 命令类（MortalityCommand 等），形成 API → UI 反向依赖	game_api.py:11-18
约束：执行 Agent 在修改 forum_api.py 和 senate_api.py 时，不得以“顺便重构”为由触及上述两个文件的结构性改动。如有重构建议，需在开发报告中单独提出，待后续评估。

七、交付物与提交流程
7.1 交付物清单
交付物	负责方	归档路径
修改文件清单（含 diff 摘要）	执行 Agent	开发报告内嵌
代码实现摘要	执行 Agent	开发报告内嵌
测试命令与结果日志	执行 Agent	开发报告内嵌
开发验收报告（含风险与遗留问题）	执行 Agent	docs/MVP 0.9 项目管理/03 开发任务书
SA 验收回执	DSK-01	docs/MVP 0.9 项目管理/03 开发任务书
7.2 提交与合并流程（强制）
执行 Agent 不得自行提交 Git。

开发完成后，执行 Agent 将修改文件、测试结果和验收报告打包交付给 DSK-01（SA）。

SA 进行本地验证（代码审查、pytest、GUI 回归）。

SA 验收通过后，由 SA 或项目负责人提交至当前协作分支 debug-phase3-stderr-removal。

提交信息格式建议：AS-P1-01: unify api_response source, remove local duplicates。

八、验收标准（Final Checklist）
类别	标准
架构	src/api/ 中所有 API 响应构造唯一来自 __init__.py；无本地重复定义
兼容性	forum_api 和 senate_api 的公共函数名、调用方式和既有测试不退化
数据结构	所有 API 返回包含 {success, message, data, errors}；data 可为 None；errors 为列表（可为空）
测试	新增 focused tests 通过 + 全量测试通过，数量不少于基线
排除项	game_api 和 session_api 的 CLI/UI 反向依赖未被意外改动
提交流程	执行 Agent 未自行提交；由 SA/项目负责人统一提交归档
九、开发执行前检查清单
执行 Agent 在动手前应确认：

当前工作区在 debug-phase3-stderr-removal 分支，基线为 9d126ea。

已运行一次全量测试，记录当前通过数量和失败项（如有）。

已阅读本任务书全部章节，尤其是“修改范围”、“排除项”和“提交流程”。

任务书签发：DSK-01（SA）
签发日期：2026-06-29
修订版本：V2（已纳入项目负责人复审意见）
状态：✅ 已定稿，可派发至执行 Agent