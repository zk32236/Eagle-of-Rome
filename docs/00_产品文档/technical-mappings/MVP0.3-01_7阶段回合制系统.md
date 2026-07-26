# MVP0.3-01 — 7阶段回合制系统（技术映射）

## 1. 代码目录

```
src/
├── core/
│   ├── game_state.py                 # GameState：阶段标记、年份推进、阶段结果存储
│   └── localization.py               # TerminologyService：阶段名称本地化
├── ui/
│   └── commands/
│       ├── func_turn_control.py      # 回合控制命令：NextCommand / TurnCommand / StepCommand
│       ├── phase_mortality.py        # 1/7 死亡率阶段
│       ├── phase_revenue.py          # 2/7 收入阶段
│       ├── phase_forum.py            # 3/7 广场阶段
│       ├── phase_population.py       # 4/7 人口阶段
│       ├── phase_senate.py           # 5/7 元老院阶段
│       ├── phase_combat.py           # 6/7 战斗阶段
│       ├── phase_resolution.py       # 7/7 决议阶段
│       └── sys_base.py               # Command 基类
```

## 2. 关键模块

| 文件 | 行数 | 功能角色 |
|------|------|---------|
| `game_state.py` | 1415 | **核心状态** — 阶段标记、推进、结果 |
| `func_turn_control.py` | 231 | **控制命令** — Next/Turn/Step 命令 |

## 3. 核心类

### 3.1 GameState 阶段方法

```python
is_phase_executed(phase_name) → bool
mark_phase_executed(phase_name)
record_phase_result(phase_id, result)
get_phase_result(phase_id) → Any
advance_year()
```

### 3.2 阶段顺序

```python
PHASE_SEQUENCE = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]
```

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Worker L | 初版创建 |
