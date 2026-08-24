# MVP0.3-01 — 7阶段回合制系统

> **功能简述：** 完整七阶段回合制（Mortality→Revenue→Forum→Population→Senate→Combat→Resolution），含阶段状态机、回合推进和阶段执行标记

## 1. 功能目的

罗马共和国的政治生活遵循严格的时间顺序。本功能将每个游戏年划分为7个阶段，按固定顺序依次执行：
- 确保各阶段间正确的数据依赖（如人口阶段需在元老院阶段前执行）
- 提供阶段性玩家交互和系统自动结算的切换
- 支持 `turn`（全自动）、`step`（逐阶段暂停）、阶段命令独立执行三种运行模式
- 每个阶段执行后标记，推进下一年时必须所有阶段已完成

## 2. 玩家/系统行为

### 2.1 阶段顺序

```python
PHASE_SEQUENCE = [
    "mortality",    # 1/7 死亡率阶段 — 人物天命判定
    "revenue",      # 2/7 收入阶段 — 税收、合同结算
    "forum",        # 3/7 广场阶段 — 竞标、招募
    "population",   # 4/7 人口阶段 — 选举、庆典
    "senate",       # 5/7 元老院阶段 — 提案、表决、否决
    "combat",       # 6/7 战斗阶段 — 战争结算
    "resolution"    # 7/7 决议阶段 — 总督交接、年度清算
]
```

### 2.2 阶段执行标记

```python
class GameState:
    def __init__(self):
        self._executed_phases: Set[str] = set()
        self._phase_results: Dict[str, Any] = {}

    def is_phase_executed(self, phase_name: str) -> bool:
        """检查阶段是否已执行"""
        return phase_name in self._executed_phases

    def mark_phase_executed(self, phase_name: str):
        """标记阶段已执行"""
        self._executed_phases.add(phase_name)

    def advance_year(self):
        """推进到下一年"""
        if self._turn:
            self._turn.advance_year()
        self._executed_phases.clear()    # 清空所有阶段标记
        self._phase_results.clear()      # 清空阶段结果
```

- 每回合开始阶段标记清空
- 每个阶段执行完毕后调用 `mark_phase_executed()` 记录
- `advance_year()` 时清空所有标记，准备新回合

### 2.3 回合推进命令

#### `next` 命令（func_turn_control.py）

```python
class NextCommand(Command):
    name = "next"
    aliases = ["n"]
```

功能：
1. 检查决议阶段（resolution）是否已执行，若未执行且非 force 模式则拒绝
2. 检查所有7个阶段是否已执行，若有缺失且非 force 模式则拒绝并列出缺失阶段
3. force 模式下可跳过未完成阶段（打印⚠️警告）
4. 清理广场中未被招募的人物（未招募人物从游戏消失）
5. 调用 `state.advance_year()` 推进年份
6. 显示回合进度摘要

#### `turn` 命令

```python
class TurnCommand(Command):
    name = "turn"
```

功能：
1. 检查是否所有阶段已执行，若是则提示使用 next
2. 按 `PHASE_SEQUENCE` 顺序依次执行所有未执行阶段
3. 每个阶段调用对应的 Command 类（如 `SenateCommand`、`RevenueCommand`）
4. 任一阶段失败则中断

#### `step` 命令

```python
class StepCommand(Command):
    name = "step"
```

功能：
1. 同 turn 命令，但在每个阶段执行后调用 `input()` 等待用户按 Enter
2. 支持 `KeyboardInterrupt` 中断

### 2.4 阶段命令类映射

```python
PHASE_COMMAND_CLASSES = {
    "mortality": MortalityCommand,
    "revenue": RevenueCommand,
    "forum": ForumCommand,
    "population": PopulationCommand,
    "senate": SenateCommand,
    "combat": CombatCommand,
    "resolution": ResolutionCommand,
}
```

每个阶段命令类必须实现 `execute(args)` 方法，并在执行成功后调用 `state.mark_phase_executed(phase_name)`。

### 2.5 回合进度摘要

```python
def _show_turn_summary(self):
    executed = self.state.executed_phases
    print(f"📅 Year {abs(self.state.turn.year)} BC:")
    print(f"   Completed: {len(executed)}/7 phases")
    for phase in PHASE_SEQUENCE:
        status = "✓" if phase in executed else "○"
        print(f"      {status} {phase_display_name}")
    if len(executed) == 7:
        print("   ✅ Ready for 'next'")
    else:
        print(f"   ⏳ {7 - len(executed)} remaining")
```

## 3. 核心规则

### 3.1 阶段依赖关系

- **硬依赖：** 人口阶段必须在元老院阶段前执行（`phase_senate.py` 入口检查）
- **软顺序：** 收入阶段 → 广场阶段（国库需先结算才能进行竞标）
- **强制顺序：** 决议阶段是每年的最后一个阶段（next 命令检查 resolution 是否执行）

### 3.2 阶段执行检查

```python
# phase_senate.py 入口检查
if not self.state.is_phase_executed("population"):
    print("⚠️ 必须先执行人口阶段 (population)")
    return False

if self.state.is_phase_executed("senate"):
    print("⚠️ 元老院阶段在本回合已执行过")
    return False
```

### 3.3 防重复执行

每个阶段命令在入口处检查 `is_phase_executed()`，防止同一阶段重复执行。

### 3.4 强制推进

`next force` 命令可跳过未完成的阶段，用于调试和测试环境。

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 阶段命令 | 游戏内命令（`turn`/`step`/`next`） | 用户输入 |
| 阶段配置 | `func_turn_control.py::PHASE_SEQUENCE` | 7阶段固定顺序 |
| 阶段命令映射 | `func_turn_control.py::PHASE_COMMAND_CLASSES` | 阶段名称→命令类 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 阶段执行标记 | `GameState._executed_phases` | Set[str]，记录已执行阶段 |
| 阶段结算结果 | `GameState._phase_results` | Dict[str, Any]，存储阶段结果 |
| 回合进度摘要 | 控制台输出 | 显示已执行/未执行阶段 |
| 年份推进 | `GameState._turn.advance_year()` | 推进到下一年的年份 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `GameState._executed_phases` | 阶段执行标记集合 |
| `GameState._turn` | GameTurn 对象，`advance_year()` 推进年份 |
| `game_state.py` | `is_phase_executed` / `mark_phase_executed` / `advance_year` |
| `func_turn_control.py` | 回合控制命令（NextCommand / TurnCommand / StepCommand） |
| `TerminologyService` | 阶段名称的本地化显示 |
| `Curia` | 广场对象，年尾清理未招募人物 |

## 5. 状态与边界

### 5.1 阶段状态

| 状态 | 说明 |
|------|------|
| 未执行 | `phase_name not in _executed_phases` |
| 已执行 | `phase_name in _executed_phases` |

### 5.2 回合状态

| 状态 | 条件 |
|------|------|
| 进行中 | 至少一个阶段未执行 |
| 可推进 | 全部7阶段已执行 |
| 强制推进 | `next force` 跳过未完成阶段 |

### 5.3 边界条件

- 所有阶段已执行后再调用 `turn` → 提示"所有阶段已执行！使用 next 推进回合"
- 重复执行同一阶段 → 拒绝，打印"已执行过"
- 在人口阶段之前执行元老院阶段 → 拒绝
- 决议阶段未执行时调用 `next` → 拒绝

### 5.4 阶段结果存储

- `record_phase_result(phase_id, result)` 存储阶段执行结果
- `get_phase_result(phase_id)` 读取阶段结果
- 结果使用 `copy.deepcopy()` 进行深拷贝，防止外部修改
- 跨年时 `_phase_results.clear()`

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|---------|
| 1 | 依次执行所有7个阶段 | 每个阶段执行后 `is_phase_executed()` 返回 True |
| 2 | 重复执行同一阶段 | 返回 False，打印"已执行过" |
| 3 | 违反阶段依赖 | 拒绝执行，打印提示 |
| 4 | 所有阶段完成后调用 next | 推进到下一年，所有阶段标记清空 |
| 5 | 非全部阶段调用 next | 拒绝，列出缺失阶段 |
| 6 | next force 跳过缺失阶段 | 推进年份，打印警告 |
| 7 | turn 命令全自动执行 | 按顺序执行所有未执行阶段 |
| 8 | step 命令逐阶段暂停 | 阶段执行后等待 Enter |
| 9 | 年尾清理广场未被招募人物 | 未招募人物从 `_members` 中删除 |
| 10 | 跨年阶段结果清空 | 新年第一回合 `get_phase_result()` 返回 None |

## 7. 历史演化与证据

- **首次实现版本：** MVP 0.3
- **代码入口：** `game_state.py`（阶段标记 + 年份推进） + `func_turn_control.py`（回合控制命令）
- **主要实现者：** 原始 CLI 版本（`debug_cli.py`），后迁移至独立的回合控制命令系统
- **主要修订：** MVP 0.5 增加 `_phase_results` 字典，为 GUI 提供阶段结算结果读取

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.3-01_7阶段回合制系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-08-24 | DA-Exec (WP-E-G7R) | REVIEWED-NO-CHANGE（主体无 GUI 阶段推进描述）；v1.1 注中「两段式年度推进」已由 GUI 侧单命令修订（见 tech mapping §6.1，GUI-BETA-005 E-05）——本文档 CLI 状态机语义不受影响 |
| v1.1 | 2026-08-23 | DA-Exec (WP-E Slice 11 PU-04) | 新增 §7 注：Resolution 阶段 read-model + 两段式年度推进（GUI）；市场生成段 veteran supply 注入（E-G7-09，同 tech 映射 §6） |
| v1.0 | 2026-07-12 | Document Officer Worker L | 初版创建 |
