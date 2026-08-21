# MVP0.7-07 — 天降猛男（技术映射）

## 1. 代码目录
```
src/core/service/mortality_service.py  # _handle_mighty_man_event()
src/core/systems/figure_generation_system.py  # [NEW] _create_historical_hero() / _create_random_mighty_man()
src/api/forum_api.py                  # [NEW] generate_figures() API
src/ui/commands/phase_forum.py         # _generate_new_figures() shell
data/cards/heroes.json                 # 历史英雄数据
```

## 2. 核心逻辑
筛选可用英雄 → 标记 hero_to_spawn → `figure_generation_system` 创建人物

## 3. 英雄生成调用链（Wave-01 更新）

### 3.1 历史英雄
```
天命阶段 mortality_service._handle_mighty_man_event()
  → 设置 state.hero_spawned_this_turn = True
  → 设置 state.hero_to_spawn = {"type": "historical", "data": {...}, "spawn_turn": <当前回合>}  # WP-C: 新增 spawn_turn 戳（ODR-04）
  ↓
广场阶段 canonical init forum_api.initialize_forum_turn()     # WP-C: GUI/CLI/AI 共用入口
  → 入口 ODR-04 归属校验 _reconcile_stale_hero_markers()（戳==当前回合才消费，否则丢弃）
  → forum_api.generate_figures(state)           # [NEW] API 层入口
    → figure_generation_system.generate_figures(state)  # [NEW] 业务层
      → _create_historical_hero(state, data)     # [NEW] 从 CLI 下沉
        → Figure(id, name, martial, intel, charisma, zeal, family_prestige)
        → state.add_spawned_hero_id(data["id"])
        → state.add_member(hero) + curia.add_figure(hero)
      → 清除 state.hero_spawned_this_turn / hero_to_spawn
```

### 3.2 随机猛男
```
→ state.hero_to_spawn = {"type": "random", "spawn_turn": <当前回合>}   # WP-C: 新增 spawn_turn 戳（ODR-04）
  ↓
→ canonical init forum_api.initialize_forum_turn() → generate_figures()（入口 ODR-04 归属校验）
→ figure_generation_system._create_random_mighty_man(state)
  ↓
→ 使用 RomanNameGenerator + 当前存活着 max-stat 创建
```

### 3.3 关键文件
| 文件 | 路径 | 角色 |
|:-----|:-----|:-----|
| `figure_generation_system.py` | `src/core/systems/` | 英雄创建业务逻辑（从 CLI 下沉） |
| `forum_api.py` | `src/api/` | API 层入口 |
| `phase_forum.py` | `src/ui/commands/` | CLI shell（仅打印 + 委托） |
| `figure.py` | `src/core/entities/` | Figure 实体（未修改） |
| `heroes.json` | `data/cards/` | 历史英雄数据 |

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.2 | 2026-08-21 | GUI-BETA-R1 WP-C: hero_to_spawn 标记新增 spawn_turn 戳（mortality L294/L310）；广场阶段消费入口改为 canonical init（initialize_forum_turn，含 ODR-04 回合归属校验） |
| v1.1 | 2026-07-25 | 新增英雄生成调用链 + figure_generation_system + forum_api 引用 |
| v1.0 | 2026-07-12 | 初版 |
