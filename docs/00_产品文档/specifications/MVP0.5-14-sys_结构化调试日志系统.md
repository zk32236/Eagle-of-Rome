# MVP0.5-14-sys — 结构化调试日志系统

> **功能简述：** 基于 Config 配置的结构化文件日志系统，支持内存日志 + RotatingFileHandler 文件日志，含异常跟踪和结构化字段

## 1. 功能目的

为游戏引擎提供可配置、持久化、多实例安全的日志基础设施。通过 `_setup_logging()` 初始化独立的实例 Logger，支持文件轮转和存储空间管理；通过 `log_event()` 向内存和外存同步写入；通过 `log_exception()` 捕获异常上下文用于调试诊断。

本系统是系统能力（System Capability），不直接面向玩家，而是为开发者提供一个结构化、可审计的游戏运行时日志方案。

## 2. 玩家/系统行为

### 2.1 系统行为

1. **日志初始化 `_setup_logging()`：**
   - 在 `GameState.__init__()` 和 `create_for_testing()` 中自动调用
   - 从 `config["logging"]` 读取配置
   - 如果 `enabled = True`，则：
     - 使用类级缓存 `GameState._log_filename` 确保同一进程中使用同一个日志文件
     - 生成带时间戳的文件名：`<base_name>_<YYYYMMDD_HHMMSS>.log`
     - 确保目录存在（`os.makedirs`）
     - 创建独立的 `logging.Logger` 实例（`name=f"EOR-{id(self)}"`）
     - 添加 `RotatingFileHandler`，支持文件大小限制和备份数
     - 设置日志级别（默认 INFO）
     - 禁止日志传播（`propagate = False`）

2. **日志记录 `log_event(message, level, extra)：`**
   - 总是将消息追加到内存 `_event_log` 列表
   - 如果文件日志已启用，将格式化的消息写入文件
   - 如果提供了 `extra` 字典，输出格式为：`<key>=<value> ... - <message>`

3. **异常日志 `log_exception()`：**
   - 自动获取调用位置回溯（`traceback.format_exc()`）
   - 记录异常类型、消息、追踪信息和自定义上下文

4. **日志关闭 `close_logging()`：**
   - 遍历并关闭所有文件 handler 并移除
   - 主要用于测试环境，避免文件句柄泄漏

### 2.2 开发者行为

开发者可调用：
```python
state.log_event("事件消息")
state.log_event("调试消息", level=logging.DEBUG, extra={"war_id": "w1", "amount": 100})
state.log_exception(e, context="交易异常", extra={"seller_id": 1})
state.close_logging()  # 测试后清理
```

## 3. 核心规则

### 3.1 日志配置

配置从 `GameState._config` 读取，键路径为 `logging.*`：

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `logging.enabled` | `bool` | `False` | 是否启用文件日志 |
| `logging.file_path` | `str` | `"logs/game.log"` | 基础日志文件路径（自动插入时间戳） |
| `logging.max_bytes` | `int` | `10485760` (10MB) | 单个日志文件最大字节数 |
| `logging.backup_count` | `int` | `3` | 轮转保留备份文件数 |
| `logging.log_level` | `str` | `"INFO"` | 日志级别（DEBUG/INFO/WARNING/ERROR） |

### 3.2 文件名生成规则

```python
base_name = "logs/game.log"
# → logs/game_20260712_162600.log
```

同一进程内所有 `GameState` 实例共享同一个日志文件（通过类静态字段 `_log_filename` 实现）。

### 3.3 内存日志格式

追加到 `_event_log` 列表，内容为 message 字符串本身。不支持持久化存储（重启丢失）。

### 3.4 文件日志格式

```
2026-07-12 16:26:00,123 - EOR-<hex_id> - INFO - extra_k1=v1 extra_k2=v2 - 消息正文
```

### 3.5 实例隔离

每个 GameState 实例创建独立的 `Logger` 实例：
```python
self._logger = logging.Logger(name=f"EOR-{id(self)}", level=level)
```

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 日志配置 | `state.config.get("logging")` | 初始化时读取 |
| 日志消息 | 调用者提供 | `message` 字符串 |
| 日志级别 | 调用者提供 | `logging.DEBUG/INFO/WARNING/ERROR` |
| 结构化字段 | 调用者提供 | `extra` 字典 |
| 异常对象 | `except` 块 | `log_exception()` 的 Exception 参数 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 内存日志 | `GameState._event_log` (List[str]) | 所有消息追加到此列表 |
| 文件日志 | 指定路径 | 含时间戳、实例名、级别、额外字段 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `Config.get("logging.*")` | 读取日志配置 |
| `logging.Logger` | Python 标准日志库 |
| `logging.handlers.RotatingFileHandler` | 文件轮转 handler |
| `os.makedirs` | 确保日志目录存在 |
| `datetime.datetime.now()` | 生成时间戳文件名 |
| `traceback.format_exc()` | 异常日志时获取回溯 |

## 5. 状态与边界

### 5.1 配置未启用

如果 `logging.enabled = False`，文件日志不初始化（`self._logger` 保持为 `None`）。`log_event()` 仅写入内存列表，不写文件。

### 5.2 测试工厂方法

`GameState.create_for_testing()` 也会调用 `_setup_logging()`，测试实例同样具备日志能力。

### 5.3 文件轮转行为

当文件大小超过 `max_bytes`（默认 10MB）时，`RotatingFileHandler` 自动执行轮转：`game.log` → `game.log.1` → ... → `game.log.3`，旧文件依次推移，最多保留 `backup_count` 个备份。

### 5.4 关闭与清理

`close_logging()` 关闭所有 handler 并将其从 logger 移除，释放文件句柄。测试框架中应在每个测试用例后调用，避免跨测试文件泄漏。

### 5.5 类级共享文件名

```python
GameState._log_filename = os.path.join(dir_name, new_name)
```

所有实例共享同一文件。不同进程（或不同 Python 解释器运行）会生成带不同时间戳的文件。

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 启用文件日志后创建实例 | 生成带时间戳的 `.log` 文件 |
| 2 | `log_event("Test message 1")` | 日志文件包含该消息 |
| 3 | `log_event("Test message 2", logging.WARNING)` | 日志文件包含该消息及 WARNING 级别 |
| 4 | 提供 extra 字典 | 日志行格式化为 `<key>=<value> ... - <message>` |
| 5 | `close_logging()` 后文件可安全读取 | 文件 handler 已关闭，读取无冲突 |

## 7. 历史演化与证据

- Feature Registry 分类：系统能力（-sys），所属系统：系统/日志
- 首次实现版本：MVP 0.5
- 核心代码：`game_state.py` 中 `_setup_logging()`、`log_event()`、`log_exception()`、`close_logging()` 方法
- 测试：`test_game_state.py` 中 `test_logging_enabled_creates_file` 用例
- 代码注释标记：`# ---------- 新增：日志记录器 ----------`

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-14-sys_结构化调试日志系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent F | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
