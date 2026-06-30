AS-P1-01 API Response 统一 — 边界审查报告（DSK-01）
审查人：DSK-01（任务架构师）
审查日期：2026-06-29
审查基线：9d126ea（debug-phase3-stderr-removal 分支）
审查范围：src/api/ 目录下全部9个Python文件

一、执行摘要
当前API层存在响应构造来源不统一的问题。虽然 src/api/__init__.py 已定义统一 api_response 工厂，但以下文件在本地重新定义了同名函数，导致实际调用可能相互覆盖或引入漂移：

文件	行为	风险等级
forum_api.py	本地定义了 api_response()	P0 阻断
senate_api.py	本地定义了 api_response() + _wrap_result()	P0 阻断
其他7个文件	从 src.api 导入 api_response，使用规范	✅ 合规
此外，存在一个架构边界问题：session_api.resolve_population_slice() 从 src.ui.processors.auto_player_processor 导入 AutoPlayerProcessor，形成了 API → UI 的反向依赖，与“UI不承载业务规则”的红线冲突。

二、详细发现
2.1 响应构造重复问题（P0）
文件：forum_api.py
python
def api_response(success: bool, message: str = "", data: Any = None, errors: List[str] = None) -> dict:
    """统一 API 返回格式"""
    return {
        "success": success,
        "message": message,
        "data": data or {},
        "errors": errors or []
    }
问题：完全重复了 __init__.py 中的定义，但行为略有不同（data or {} 强制转换，而 __init__.py 允许 data=None）。

后果：如果外部通过 from forum_api import api_response 导入，会绕过 __init__.py 的规范定义。

文件：senate_api.py
python
def api_response(success: bool, message: str = "", data: Any = None, errors: List[str] = None) -> dict:
    return {...}
def _wrap_result(result: dict) -> dict:
    return api_response(...)
问题：同样本地定义了 api_response，还多一个 _wrap_result 包装器。

后果：PoliticalSystem 返回的 {success, message, data, errors} 被二次包装，可能产生嵌套结构。

其他文件状态
文件	是否导入 api_response	来源
population_api.py	✅ 是	from src.api import api_response
figure_api.py	✅ 是	from src.api import api_response
province_api.py	✅ 是	from src.api import api_response
contract_api.py	✅ 是	from src.api import api_response
game_api.py	✅ 是	from src.api import api_response
player_api.py	✅ 是	from src.api import api_response
faction_api.py	✅ 是	from src.api import api_response
session_api.py	✅ 是	from src.api import api_response
2.2 架构边界问题（P1）
文件：session_api.py 第 155-163 行

python
def resolve_population_slice(state: GameState) -> dict:
    try:
        from src.ui.processors.auto_player_processor import AutoPlayerProcessor
        from src.core.deciders.impl.auto_retirement_decider import AutoRetirementDecider
        # ...
问题：API 层直接导入 UI 层的 AutoPlayerProcessor，形成 API → UI 的反向依赖。

影响：GUI 原型（gui_main.py）调用 session_api.resolve_population_slice() 时，间接依赖了 UI 处理器。这违反了 AGENTS.md 中“UI/GUI 不承载核心业务规则”的架构规则。

建议：本任务不扩大处理，但应登记为技术债（TD-AS-P1-01-001），待后续 P1 功能开发前评估是否将 AutoPlayerProcessor 下沉到 core.processors 或 core.systems 层。

2.3 兼容性风险评估
调用方	是否依赖特殊字段	风险
CLI 命令层（src/ui/commands/）	依赖 message 文本展示	低 — 只读 message 字段
GUI Session API（session_api.py）	依赖 data 结构化字段	低 — 使用 data 中的字段名
测试套件（src/tests/）	依赖 success 布尔值	低 — 仅检查 success
自动玩家决策器	依赖 data 返回结果	低 — 使用 data 中的键值
旧报告（ZP-01）中 734 passed	全量测试通过	✅ 基线已锁定
结论：所有调用方都基于 {success, message, data, errors} 这一标准结构，不存在历史特殊字段依赖。统一响应构造来源是安全的，不会破坏兼容性。

2.4 测试缺口（与本次任务相关）
forum_api.py 中的 transact_land、buy_land 等 API 缺乏 focused tests 覆盖失败路径（如权限不足、额度不足）。

senate_api.py 中的 propose、vote、veto 缺少对 api_response 格式的显式断言。

session_api.py 的 get_session_snapshot 返回 data 结构较大，但未见专门验证字段完整性的测试。

建议：技术任务书应要求补充 focused tests，覆盖：

统一响应格式的 success、message、data、errors 字段存在性。

错误路径（权限、非法输入）返回的 errors 列表非空。

三、迁移范围与策略
3.1 必须修改的文件
文件	修改内容
forum_api.py	删除本地 api_response 定义，改为 from src.api import api_response
senate_api.py	删除本地 api_response 和 _wrap_result 定义，改为 from src.api import api_response。_wrap_result 的包装逻辑直接内联到各函数中（或删除，因为 PoliticalSystem 已返回标准结构）
3.2 无需修改的文件（已合规）
population_api.py、figure_api.py、province_api.py、contract_api.py、game_api.py、player_api.py、faction_api.py、session_api.py 已从 src.api 导入，保持不变。

3.3 兼容层策略
无需保留兼容层。因为所有调用方都通过 from src.api import api_response 或 from src.api import 间接使用，从未直接依赖 forum_api.api_response 或 senate_api.api_response。

只需删除本地定义，确保所有调用点都使用 __init__.py 中的统一函数。

四、架构规则确认
规则	状态
API 返回保持 {success, message, data, errors}	✅ 已具备，本任务强化统一入口
UI/GUI 不承载核心业务规则	⚠️ 发现 resolve_population_slice 反向依赖 UI，已登记为技术债
不允许 UI 直接修改 Core/System/Entity 私有字段	✅ 未违反
不得破坏 GUI-P0-01 可玩切片	✅ 修改范围不涉及 GUI 页面
全量测试不退化	✅ 需开发后验证
五、技术债登记
编号	主题	优先级	建议处理时机
TD-AS-P1-01-001	session_api.resolve_population_slice 直接导入 AutoPlayerProcessor（API → UI 反向依赖）	P1	后续 session_api 或 GUI 深度优化时处理
TD-AS-P1-01-002	forum_api.py 中部分函数（如 resolve_forum）仍直接操作 state.contracts 内部列表，未完全通过 Service 层	P2	与后续 Forum/Contract 重构合并评估
TD-AS-P1-01-003	senate_api.py 中的 assign_fleets_to_active_wars 直接操作 naval_system 内部集合，未通过 Service 接口	P2	后续 NavalSystem 重构时处理
六、边界审查结论
API 响应统一的核心问题可控，范围明确：

P0 修复（本任务必做）：删除 forum_api.py 和 senate_api.py 中重复的 api_response 定义，统一使用 src.api 的导出。

测试补充（本任务建议）：至少补充 3-5 个 focused tests 锁定统一响应格式。

技术债登记（本任务不处理）：resolve_population_slice 的反向依赖已登记，后续评估。

本任务不扩大范围，不新增玩法，不改变公共 API 函数名，不破坏 GUI-P0-01 可玩切片。

七、技术任务书草稿（待定稿）
（基于以上边界审查，技术开发任务书的核心内容已可确定。待你确认边界审查结论后，我将输出正式技术任务书。）

任务书核心要点：

修改文件：forum_api.py、senate_api.py

修改内容：删除本地 api_response 定义，替换为 from src.api import api_response

测试要求：

运行全量 src/tests，确保仍为 734 passed（或差异有非本任务原因）

补充 test_api_response_unification.py，验证所有 API 返回包含 success、message、data、errors 四个键

验收标准：

所有 API 返回结构来源唯一（src.api）

无功能退化

全量测试通过