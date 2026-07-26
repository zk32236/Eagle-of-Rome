# MVP0.5-07 — 人物类型系统 Technical Mapping

## 1. 代码目录
```
src/core/entities/figure.py  # ClassTier 枚举 + Figure + RomanNameGenerator
src/api/figure_api.py        # get_figure_info()
```

## 2. 关键方法
- `create_nobile()`, `create_eques()`, `create_plebeian()` — 工厂方法
- `RomanNameGenerator.generate_nobile_name()` 等 — 名字生成
- `can_hold_office()` — class_tier 检查保民官资格

## 3. 人物生成调用链（Wave-01 更新）

### 3.1 广场阶段新人
```
CLI phase_forum._generate_new_figures()
  → forum_api.generate_figures(state)          # [NEW] API 层入口
    → figure_generation_system.generate_figures(state)  # [NEW] 纯业务层
      → Figure.create_nobile/eques/plebeian()   # 复用现有工厂方法
      → state.add_member(fig) + curia.add_figure(fig)
      → [可选] 历史英雄或随机猛男
```

### 3.2 `_generate_market_figures()` 调用链
```
forum_api.open_market(state)
  → _generate_market_figures(state)            # [UPDATED] 委托至专用系统
    → figure_generation_system.generate_market_figures(state)  # [NEW]
```

### 3.3 关键文件
| 文件 | 路径 | 角色 |
|:-----|:-----|:-----|
| `figure_generation_system.py` | `src/core/systems/` | 人物生成业务逻辑 |
| `forum_api.py` | `src/api/` | API 层入口 |
| `phase_forum.py` | `src/ui/commands/` | CLI shell（仅打印） |
| `figure.py` | `src/core/entities/` | Figure 实体 + 工厂方法（未修改） |

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-07-25 | 新增人物生成调用链说明 + figure_generation_system 引用 |
| v1.0 | 2026-07-12 | 初版 |
