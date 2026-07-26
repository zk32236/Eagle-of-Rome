# MVP0.5-15-sys — 游戏输出与日志规范

> **功能简述：** API层统一输出格式（success/message/data/errors）、日志轮转和备份规范、i18n 国际化输出

## 1. 功能目的

游戏输出与日志规范系统为整个 Eagle of Rome 项目提供统一的输出与日志框架。此机制确保：

1. **统一 API 响应格式**：所有 API 调用返回 `{success, message, data, errors}` 标准化结构
2. **多语言支持**：通过 i18n 系统，所有面向用户的文本支持中英文切换
3. **日志规范**：文件日志使用 RotatingFileHandler 轮转，内存日志实时记录所有事件
4. **调试输出**：Tee 输出机制同时写入终端和日志文件，便于调试复现
5. **进度展示**：阶段执行进度条和状态摘要，提升可读性

## 2. 玩家/系统行为

### 2.1 API 统一响应格式

**文件：** `src/api/__init__.py`

```python
def api_response(success: bool, message: str = "",
                 data: Any = None, errors: Optional[List[str]] = None) -> Dict:
    """
    统一的API返回值格式
    """
    return {
        "success": success,      # 操作是否成功
        "message": message,      # 人类可读的消息
        "data": data,            # 结构化数据（可选）
        "errors": errors or []   # 错误列表（可选）
    }
```

**使用示例：**

```python
# 成功
api_response(True, "收入阶段执行成功", data={"treasury": 1000, ...})
# → {"success": True, "message": "收入阶段执行成功", "data": {...}, "errors": []}

# 失败
api_response(False, "你没有权限执行此操作", errors=["not_your_turn"])
# → {"success": False, "message": "你没有权限执行此操作", "data": None, "errors": ["not_your_turn"]}
```

**使用范围：** 所有 `src/api/*.py` 模块均使用此统一格式。

### 2.2 国际化输出

**文件：** `src/core/i18n.py`

```python
class I18n:
    """单例模式国际化类"""

    def load(self, language: str = "zh-CN", force: bool = False):
        """
        加载指定语言的字符串表。
        - 文件路径: data/i18n/{language}.json
        - 支持 UTF-8 BOM
        - 回退策略：指定语言不存在时回退到 zh-CN
        """

    def get(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        """
        获取本地化字符串。
        - key 不存在时返回 default 或 key 本身
        - 支持 kwargs 格式化: i18n.get("greeting", name="Claudius")
        """

# 全局实例
i18n = I18n()
i18n.load("zh-CN")  # 默认加载中文
```

**使用示例：**

```python
# 模板: "国库: {treasury} Talents"
i18n.get("status_summary",
         turn_num=1,
         year_display="264 BC",
         treasury=500,
         living_count=30,
         faction_count=3)

# 出错时回退
i18n.get("unknown_key", default="默认文本")

# kwargs 格式化
i18n.get("figure_not_found", id=42)
# → "❌ 人物 ID 42 不存在或已死亡"
```

### 2.3 日志系统

**文件：** `src/core/game_state.py`

```python
# 日志初始化（_setup_logging 方法）
def _setup_logging(self):
    """根据配置初始化文件日志（实例独立，共用同一文件）。"""
    log_config = self._config.get("logging", {})
    if not log_config.get("enabled", False):
        return

    # 生成带时间戳的文件名: game_20260713_174600.log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = log_config.get("file_path", "logs/game.log")
    dir_name = os.path.dirname(base_name)
    base_file = os.path.basename(base_name)
    name, ext = os.path.splitext(base_file)
    new_name = f"{name}_{timestamp}{ext}"
    GameState._log_filename = os.path.join(dir_name, new_name)

    # RotatingFileHandler: 10MB 轮转，保留 3 个备份
    max_bytes = log_config.get("max_bytes", 10485760)   # 10MB
    backup_count = log_config.get("backup_count", 3)     # 3个备份
    level_str = log_config.get("log_level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)

    # 确保日志目录存在
    log_dir = os.path.dirname(GameState._log_filename)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 创建独立 Logger（不共享根 Logger）
    self._logger = logging.Logger(name=f"EOR-{id(self)}", level=level)
    handler = logging.handlers.RotatingFileHandler(
        GameState._log_filename, maxBytes=max_bytes, backupCount=backup_count,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    self._logger.addHandler(handler)
    self._logger.propagate = False  # 不传播到根 Logger
```

**日志格式（文件日志）：**
```
2026-07-13 17:46:00,123 - EOR-140734567876544 - INFO - 税收阶段完成: 国库 1500
2026-07-13 17:46:00,456 - EOR-140734567876544 - DEBUG - function=decide_bids faction_id=populares faction_treasury=500 vacancies=3 - 派系 平民派 决定出价 3 人
```

**事件日志方法：**

```python
def log_event(self, message: str, level: int = logging.INFO, extra: dict = None):
    """
    记录事件到内存日志，并写入文件日志（如果启用）。
    - message: 事件描述
    - level: 日志级别（DEBUG/INFO/WARNING/ERROR）
    - extra: 结构化字段，如 {"war_id": "war1", "amount": 100}
    """
    self._event_log.append(message)        # 内存日志
    if self._logger:
        log_msg = message
        if extra:
            extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
            log_msg = f"{extra_str} - {message}"
        self._logger.log(level, log_msg)    # 文件日志
```

### 2.4 CLI 输出

**文件：** `src/ui/debug_cli.py`

**Tee 输出：** 同时写入终端和日志文件

```python
class Tee:
    """将输出同时写入文件和原始 stdout"""
    def __init__(self, filename, mode='a', encoding='utf-8'):
        self.file = open(filename, mode, encoding=encoding)
        self.stdout = sys.stdout

    def write(self, message):
        self.stdout.write(message)
        self.stdout.flush()
        self.file.write(message)
        self.file.flush()
```

**进度条：**

**文件：** `src/ui/utils.py`

```python
def get_progress_bar(state, width=7):
    """
    生成进度条字符串
    格式: [▓▓▓░░░░] 3/7
    """
    executed = len(state.executed_phases)
    total = 7
    filled = "▓" * executed
    empty = "░" * (total - executed)
    return f"[{filled}{empty}] {executed}/{total}"
```

### 2.5 阶段预览输出

每个阶段在 CLI 通过 i18n 输出预览文本：

```python
preview_key = f"phase_{phase_name}_preview"
preview = i18n.get(preview_key, default="")
# 例如: phase_mortality_preview
#      phase_revenue_preview
#      phase_forum_preview
#      phase_population_preview
#      phase_senate_preview
#      phase_combat_preview
#      phase_resolution_preview
```

## 3. 核心规则

### 3.1 API 响应规范

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `success` | `bool` | 是 | True=成功, False=失败 |
| `message` | `str` | 推荐 | 人类可读的描述，通常通过 i18n 获取 |
| `data` | `Any` | 否 | 结构化数据载荷 |
| `errors` | `List[str]` | 否 | 错误代码或描述列表 |

### 3.2 日志轮转配置

| 配置键 | `game_config.json` | 说明 |
|--------|-------------------|------|
| `logging.enabled` | `true` | 是否启用文件日志 |
| `logging.file_path` | `"logs/game.log"` | 日志文件路径（自动插入时间戳） |
| `logging.max_bytes` | `10485760` | 单个日志文件最大字节数（10MB） |
| `logging.backup_count` | `3` | 保留的旧日志文件数 |
| `logging.log_level` | `"INFO"` | 日志级别（DEBUG/INFO/WARNING/ERROR） |

### 3.3 i18n 规则

- 单例模式：整个进程共享一个 I18n 实例
- 文件路径：`data/i18n/{language}.json`
- 回退策略：语言文件不存在时回退到 zh-CN
- 格式化：支持 Python `str.format(**kwargs)`
- 默认语言：zh-CN（在模块加载时自动加载）

### 3.4 CLI 输出规则

- 阶段标题：`### 回合 N (YYYY BC) - 阶段名 [M/7]`
- 预览文本：从 i18n 获取 `phase_{name}_preview`
- 进度条：`[▓▓▓░░░░] 3/7`
- Tee 输出：所有 print 内容同时写入 CLI 日志文件
- 日志文件名：`logs/cli_{timestamp}.log`

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 语言配置 | `Config.get("language")` | 当前语言（zh-CN / en-US） |
| 日志配置 | `Config.get("logging")` | 日志级别、轮转参数 |
| 阶段预览 | `data/i18n/{lang}.json` | 各阶段预览文本 |
| API 调用参数 | 各 api 函数参数 | 执行结果、错误信息 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| API 响应 | 调用方（CLI/GUI/测试） | `{success, message, data, errors}` |
| 文件日志 | `logs/game_{timestamp}.log` | RotatingFileHandler 轮转日志 |
| 内存日志 | `GameState._event_log` | 字符串列表，用于存档和调试 |
| CLI 日志 | `logs/cli_{timestamp}.log` | CLI 完整输出的副本 |
| 终端输出 | stdout | 阶段结果、状态摘要、错误信息 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `Config` | 提供 logging 和 language 配置 |
| `RotatingFileHandler` | 标准库日志轮转处理器 |
| `json` | i18n 语言文件解析 |
| `os`, `datetime` | 日志文件名生成、目录创建 |
| `io.StringIO` | API 层输出捕获（TeeStdout） |
| `contextlib.redirect_stdout` | API 层阶段输出重定向 |

## 5. 状态与边界

### 5.1 正常流程

**API 调用：**
1. 调用方调用 `game_api.execute_phase()`
2. 内部创建 TeeStdout 捕获输出
3. 执行阶段命令
4. 恢复 stdout
5. 返回 `api_response(success, output, data)`

**日志记录：**
1. 游戏初始化时调用 `_setup_logging()`
2. 生成 `game_{timestamp}.log`
3. 各模块调用 `state.log_event()`
4. 日志同时写入文件 + 内存

**i18n 加载：**
1. `I18n()` 单例在模块加载时创建
2. `load("zh-CN")` 自动调用
3. `i18n.get(key)` 按需获取文本

### 5.2 边界情况

| 场景 | 处理 |
|------|------|
| 日志目录不存在 | `os.makedirs()` 自动创建 |
| 日志文件达到 10MB | RotatingFileHandler 自动轮转 |
| i18n key 不存在 | 返回 `default` 或 key 本身 |
| 语言文件不存在 | 回退到 zh-CN |
| 语言文件编码 | 支持 UTF-8 BOM |
| CLI 输出流异常 | Tee 尝试同时写入文件和终端，单个失败不影响另一个 |

### 5.3 格式规范

**API 响应格式（所有 api 模块统一）：**
```json
{
    "success": true,
    "message": "操作成功",
    "data": {
        "treasury": 1000,
        "living_count": 30
    },
    "errors": []
}
```

**文件日志格式（标准 logging 格式）：**
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

**i18n JSON 格式：**
```json
{
    "status_summary": "\n... 回合: 第 {turn_num} 年 ({year_display}) ...",
    "figure_not_found": "❌ 人物 ID {id} 不存在或已死亡"
}
```

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | API 返回统一格式 | `api_response()` 返回 `{success, message, data, errors}` |
| 2 | 日志文件创建 | 游戏启动后 `logs/game_*.log` 文件存在 |
| 3 | 日志内容写入 | 阶段执行后日志文件包含对应事件 |
| 4 | 日志轮转 | 超过 max_bytes 后创建备份文件 |
| 5 | i18n 中文加载 | 中文语言文件正确加载 |
| 6 | i18n key 不存在回退 | 返回 key 本身或 default |
| 7 | i18n 格式化 | kwargs 正确替换到模板字符串 |
| 8 | CPU 阶段输出包含进度条 | `[▓▓▓░░░░] 3/7` 格式正确 |
| 9 | CLI Tee 输出 | 终端和日志文件内容一致 |
| 10 | 异常日志 | 未捕获异常通过 `log_exception()` 记录 |

## 7. 历史演化与证据

- 首次实现版本：MVP 0.5
- 相关子系统：结构化调试日志系统（MVP0.5-14-sys）、调试命令框架（MVP0.5-16-sys）
- 代码入口：`src/core/i18n.py`, `src/api/__init__.py`, `src/ui/utils.py`, `src/ui/debug_cli.py`

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-15-sys_游戏输出与日志规范.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-13 | Document Officer (DA) | 初版创建 |
| v1.1 | 2026-07-13 | Audit Subagent (DS) | 审计通过，无代码不一致问题 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
