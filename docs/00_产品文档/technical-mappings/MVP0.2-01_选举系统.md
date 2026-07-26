# MVP0.2-01 — 选举系统（Technical Mapping）

> **功能简述：** 选举系统 — 罗马共和国年度公职选举的完整流程

## 1. 代码目录

```
src/
├── api/
│   └── population_api.py          # 选举核心 API（campaign, vote, get_candidates, resolve_election）
├── core/
│   ├── deciders/
│   │   ├── vote_decider.py          # 投票决策器接口
│   │   ├── festival_decider.py      # 庆典决策器接口
│   │   └── impl/
│   │       ├── auto_vote_decider.py     # 自动投票决策器实现
│   │       └── auto_festival_decider.py # 自动庆典决策器实现
│   ├── entities/
│   │   ├── figure.py                # 人物实体（影响力计算、任职资格检查、社会阶层）
│   │   └── entities.py              # Faction 实体（派系统计）GameTurn
│   ├── systems/
│   │   └── political_system.py      # 政治系统（元老院提案，不直接涉及选举）
│   └── game_state.py                # 游戏状态（选举临时数据管理）
├── ui/
│   ├── commands/
│   │   └── phase_population.py      # 人口阶段 UI 命令（4 步骤状态机）
│   └── processors/
│       └── auto_player_processor.py # AI 玩家庆典/投票自动化处理器
```

## 2. 关键模块

### 2.1 UI 层 — `phase_population.py` (670行)

方法: `execute()`, `_handle_step_0~3()`, `_remove_office_holders()`, `_convert_battlefield_commanders()`, `_campaign_all()`, `_vote_all()`

### 2.2 API 层 — `population_api.py` (320行)

方法: `campaign()`, `vote()`, `get_candidates()`, `resolve_election()`

### 2.3 实体层 — `figure.py`

方法: `can_hold_office()`, `get_qualification_attribute()`, `update_influence()`

## 3. 核心算法

### 3.1 候选人提名

选举顺序: consul → censor → praetor → quaestor → tribune，按资格属性降序取前 N 名。

### 3.2 选举计票

加权投票：各候选人得分 = Σ 支持者派系影响力总和，平局随机。

## 4. 数据结构

### 选举临时数据

```python
{
    "campaigns": List[Tuple[str, int, int]],  # [(player_id, figure_id, amount)]
    "votes":     List[Tuple[str, str, int]],  # [(player_id, office, figure_id)]
}
```

## 5. 配置项

| 配置路径 | 默认值 | 说明 |
|---------|--------|------|
| `candidates_per_election.consul` | 2 | 候选人数量 |
| `testing.auto_population` | false | 自动模式 |
| `political_rules.min_ages.*` | 30-42 | 各官职最低年龄 |
| `political_rules.office_cooldowns.*` | 2-10 | 各官职冷却年数 |

## 6. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.2 | 2026-07-17 | Audit Sub-Agent | 行数修正 |
| v1.0 | 2026-07-13 | 初版 | — |
