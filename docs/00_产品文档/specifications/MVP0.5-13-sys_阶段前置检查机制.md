# MVP0.5-13-sys — 阶段前置检查机制

> **功能简述：** 通过 `is_phase_executed()` 方法确保每个阶段只能执行一次，防止重复执行和状态冲突

## 1. 功能目的

阶段前置检查机制是游戏引擎的核心守卫系统，确保每个阶段（回合制流程的各个子阶段）在本回合内只能执行一次。此机制确保：

1. **防止重复执行**：每个阶段执行后立即标记，后续调用会被拒绝
2. **状态一致性**：避免阶段间状态混乱（如人口阶段在收入阶段之后执行）
3. **流程正确性**：保证阶段按正确顺序执行（收入→广场→人口→元老院→战斗→决议）
4. **调试友好**：提供清晰的错误提示，便于发现逻辑错误

## 2. 玩家/系统行为

### 2.1 触发时机

所有阶段命令在执行前都会调用 `is_phase_executed()` 检查：

```python
if not self.state.is_phase_executed("revenue"):
    print("⚠️ 必须先执行收入阶段 (revenue)")
    return False

if self.state.is_phase_executed("forum"):
    print(i18n.get("error_phase_already_executed", phase="forum"), flush=True)
    return False
```

### 2.2 核心检查方法

**GameState.is_phase_executed(phase_name: str) → bool**

```python
def is_phase_executed(self, phase_name: str) -> bool:
    """检查阶段是否已执行"""
    return phase_name in self._executed_phases
```

- 输入：阶段名称字符串（如 "revenue", "forum", "population", "senate", "combat", "resolution"）
- 输出：`True`（已执行）/ `False`（未执行）

### 2.3 标记执行方法

**GameState.mark_phase_executed(phase_name: str) → None**

```python
def mark_phase_executed(self, phase_name: str):
    """标记阶段已执行"""
    self._executed_phases.add(phase_name)
```

- 执行阶段成功后调用，将阶段名称加入 `_executed_phases` 集合
- 在每个阶段命令的 `execute()` 方法末尾调用

### 2.4 阶段执行顺序

```
Revenue Phase (收入阶段)
  ↓
Forum Phase (广场阶段)
  ↓
Population Phase (人口阶段)
  ↓
Senate Phase (元老院阶段)
  ↓
Combat Phase (战斗阶段)
  ↓
Resolution Phase (决议阶段)
```

### 2.5 阶段依赖检查

某些阶段有前置依赖，必须在执行前检查：

| 阶段 | 必须先执行的前置阶段 | 检查代码位置 |
|------|---------------------|-------------|
| Forum | Revenue | `phase_forum.py:execute()` |
| Population | Forum | `phase_population.py:execute()` |
| Senate | Population | `phase_senate.py:execute()` |
| Combat | Senate | `phase_combat.py:execute()` |
| Resolution | Combat | `phase_resolution.py:execute()` |

## 3. 核心规则

### 3.1 阶段名称映射

| 阶段名称 | 英文 | 中文 | 对应命令文件 |
|----------|------|------|-------------|
| revenue | Revenue Phase | 收入阶段 | `phase_revenue.py` |
| forum | Forum Phase | 广场阶段 | `phase_forum.py` |
| population | Population Phase | 人口阶段 | `phase_population.py` |
| senate | Senate Phase | 元老院阶段 | `phase_senate.py` |
| combat | Combat Phase | 战斗阶段 | `phase_combat.py` |
| resolution | Resolution Phase | 决议阶段 | `phase_resolution.py` |

### 3.2 执行状态管理

```python
# GameState 初始化
self._executed_phases: Set[str] = set()

# 阶段执行前检查
if self.state.is_phase_executed("forum"):
    return False  # 阶段已执行，拒绝执行

# 阶段执行后标记
self.state.mark_phase_executed("forum")
```

### 3.3 状态重置

**GameState.reset()** 方法在初始化时清空执行状态：

```python
def reset(self):
    """重置状态 - 实例方法，仅影响当前实例"""
    self._executed_phases.clear()
    self._phase_results.clear()
    # ... 其他重置逻辑
```

确保每个新游戏实例从干净状态开始。

### 3.4 阶段结果记录

除了标记执行状态，还记录阶段结算结果：

```python
def record_phase_result(self, phase_id: str, result: Any) -> None:
    """记录阶段结算结果，供 GUI/API 在阶段推进前后读取。"""
    self._phase_results[phase_id] = copy.deepcopy(result)

def get_phase_result(self, phase_id: str) -> Any:
    """读取阶段结算结果。"""
    return copy.deepcopy(self._phase_results.get(phase_id))
```

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 阶段名称 | 命令调用者 | "revenue", "forum", "population", "senate", "combat", "resolution" |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 执行状态 | `is_phase_executed()` 返回值 | `True`（已执行）/ `False`（未执行） |
| 错误消息 | 控制台输出 | "⚠️ 必须先执行XXX阶段" 或 "⚠️ XXX阶段在本回合已执行过" |
| 执行标记 | `mark_phase_executed()` | 将阶段名称加入 `_executed_phases` 集合 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `GameState._executed_phases` | 阶段执行状态集合 |
| `GameState._phase_results` | 阶段结果存储字典 |
| `GameState.reset()` | 游戏初始化时清空状态 |
| `GameState.advance_year()` | 回合推进时重置执行状态 |

## 5. 状态与边界

### 5.1 正常流程

```
1. 游戏初始化 → _executed_phases = set()
2. 执行收入阶段 → is_phase_executed("revenue") = False
3. mark_phase_executed("revenue") → _executed_phases = {"revenue"}
4. 执行广场阶段 → is_phase_executed("forum") = False
5. mark_phase_executed("forum") → _executed_phases = {"revenue", "forum"}
6. ... 以此类推
7. 执行决议阶段 → mark_phase_executed("resolution")
8. 回合结束 → advance_year() → _executed_phases.clear()
9. 下一回合 → 从步骤2重新开始
```

### 5.2 边界情况

| 场景 | 处理 |
|------|------|
| 重复执行同一阶段 | 返回 `False`，打印错误消息 "⚠️ XXX阶段在本回合已执行过" |
| 跳过前置阶段 | 返回 `False`，打印错误消息 "⚠️ 必须先执行XXX阶段" |
| 无效阶段名称 | 返回 `False`（不在集合中） |
| 多实例独立状态 | 每个 GameState 实例有独立的 `_executed_phases` 集合 |

### 5.3 多阶段并发

- 所有阶段命令使用同一 `GameState` 实例，状态由 `_executed_phases` 集合保护
- 阶段间通过前置依赖检查确保顺序正确
- 不存在并发执行问题（单线程游戏引擎）

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 第一次执行阶段 | `is_phase_executed()` 返回 `False`，执行成功，`mark_phase_executed()` 被调用 |
| 2 | 重复执行同一阶段 | `is_phase_executed()` 返回 `True`，返回 `False`，打印错误消息 |
| 3 | 执行前置未满足的阶段 | `is_phase_executed()` 返回 `False`，返回 `False`，打印依赖错误 |
| 4 | 回合推进后重置状态 | `advance_year()` 清空 `_executed_phases`，所有阶段可重新执行 |
| 5 | 多实例独立状态 | 不同 GameState 实例有独立的执行状态，互不影响 |

## 7. 历史演化与证据

- 首次实现版本：MVP 0.5
- 相关演化：随着游戏阶段增加，阶段前置检查机制成为必需的流程守卫
- 代码入口：`src/core/game_state.py`（`is_phase_executed` / `mark_phase_executed` 方法）

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-13-sys_阶段前置检查机制.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-13 | Document Officer (DA) | 初版创建 |
