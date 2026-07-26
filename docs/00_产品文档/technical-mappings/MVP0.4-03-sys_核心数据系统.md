# MVP0.4-03-sys — 核心数据系统 Technical Mapping

## 1. 代码目录
```
src/core/game_state.py           # GameState 容器 (1415行)
src/core/entities/
├── figure.py                    # Figure 人物实体 (660行)
├── entities.py                  # Faction / GameTurn
├── province.py                  # Province 行省 (392行)
├── city.py                      # City 城市
├── contract.py                  # Contract 合同
├── curia.py                     # Curia 广场人物池
├── player.py                    # Player 玩家
├── legion.py                    # Legion 军团
├── fleet.py                     # Fleet 舰队
└── war.py                       # War 战争
```

## 2. 关键方法
- GameState: to_dict()/load_from_dict(), reset(), add_member(), mark_member_dead()
- Figure: update_influence(), can_hold_office(), sell_land(), buy_land()

## 3. 版本日志
| v1.1 | 2026-07-17 | 审计修复 |
