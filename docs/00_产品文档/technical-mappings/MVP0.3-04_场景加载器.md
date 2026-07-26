# MVP0.3-04 — 场景加载器 Technical Mapping

## 1. 代码目录
```
src/core/scenario_loader.py     # 场景加载器 (280行)
src/core/game_state.py          # 游戏状态容器
src/core/entities/figure.py     # 人物实体（工厂方法）
src/ui/commands/func_load.py    # CLI 加载命令
data/scenarios/mvp_test.json    # 默认场景配置
data/cards/provinces.json       # 行省数据
```

## 2. 关键模块
- `scenario_loader.py` — load_scenario(): 重置→配置→回合→派系→人物→国库→行省→总督→玩家
- `func_load.py` — LoadCommand CLI 封装

## 3. 版本日志
| v1.0 | 2026-07-12 | 初版 |
