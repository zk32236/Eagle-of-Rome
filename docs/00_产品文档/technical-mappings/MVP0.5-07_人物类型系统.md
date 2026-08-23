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

### 3.2 市场生成实况调用链（2026-08-23 修正）

> ⚠️ 原 §3.2「open_market → _generate_market_figures」已过时：
> `_generate_market_figures`（forum_api.py:249-256）无生产调用方（仅测试）。
> 每回合市场生成的实况入口为 `generate_figures`（GUI 与 CLI 均如此）：

```
GUI: api_adapter.py → forum_api.open_market(:196)
CLI: phase_forum.py → forum_api.initialize_forum_turn(:138)
  → forum_api.generate_figures(:981) → system_generate_figures
    → figure_generation_system.generate_figures(state)
      → Figure.create_nobile/eques/plebeian()（或 veteran nobile，见 §3.4）
      → state.add_member(fig) + curia.add_figure(fig)
      → [可选] 历史英雄或随机猛男（hero 零注入）
```

`generate_market_figures`（figure_generation_system.py）保留为与 `generate_figures`
共享同一核心循环的无 hero 变体（供测试与 `_generate_market_figures` 委托使用）。

### 3.3 关键文件
| 文件 | 路径 | 角色 |
|:-----|:-----|:-----|
| `figure_generation_system.py` | `src/core/systems/` | 人物生成业务逻辑（含 veteran supply 注入） |
| `forum_api.py` | `src/api/` | API 层入口 |
| `phase_forum.py` | `src/ui/commands/` | CLI shell（仅打印） |
| `figure.py` | `src/core/entities/` | Figure 实体 + 工厂方法（未修改） |

## 4. 市场资深贵族供给（veteran supply）— E-G7-09（2026-08-23 新增）

### 4.1 机制概述（ODR-WP-E-01 Owner 裁决落地）

市场生成新人时，通过**确定性槽位预留**保证每回合至少 1-2 名资深贵族（nobile）为
前执政官（ex-consul）/ 前大法官（ex-praetor），携带完整 office cursus：

- **槽 1 = censor-anchor（ex-consul，冷却期新鲜注入）**：完整 cursus
  `[quaestor @ ct-5, praetor @ ct-3, consul @ ct-1]`（ct = 当前回合号）。
  consul 任期距今 1 回合 < cooldown(2) → 本回合 consul 复选被冷却阻断，但 censor
  资格链通过 → **该人物只进 censor 池、永不被 consul 槽占用** → 从 T1 起每回合
  censor ≥1 候选（确定性保证）。
- **槽 2..k（若 k≥2）**：按 `ex_consul_probability`（默认 0.5）掷为 ex-consul 或
  ex-praetor（任期距今 h ∈ [2,8] 回合，同职复选不被冷却阻断）。
- **总量不变**：市场每回合总人数仍 = `new_figures_count`（默认 3）；hero 检测逻辑
  `len(figure_list) > new_figures_count` 不受影响。
- **非 spawn hack 合规**：注入发生在市场生成链（正常生命周期：市场新人 → 竞价招募
  → 选举结算），非选举时点补丁；office_history 为完整 `OfficeTerm` 记录
  （office_type/start_turn/end_turn/is_active），与 `archive_office_holders` 写入的
  历史同构。

### 4.2 年龄一致性

- 注入者现年龄 ∈ [45,58]（`age_min`/`age_max`），且**任职当年年龄** ≥ 该官职
  `min_ages` 门槛（consul ≥40 / censor ≥42 / praetor ≥35 / quaestor ≥30）——
  无「25 岁前执政官」类矛盾；`add_office_history` 年龄地板（consul→42 / praetor→37 /
  quaestor→32）为纵深防御。
- 统计强化：ex-consul → `charisma = max(charisma, 7)`；ex-praetor →
  `intelligence = max(intelligence, 7)`。不 bump zeal（censor 排名属性，供给保证 =
  存在性，排序正交，v1 不强化）。

### 4.3 参数化（`forum_rules.veteran_supply`，代码默认 + 产品配置同步）

| 键 | 默认 | 语义 |
|:---|:---|:---|
| `enabled` | `true` | 总开关；false → 完全恢复现状（零注入） |
| `min_veteran_nobiles` | `1` | 每回合保证的资深贵族下限 |
| `max_veteran_nobiles` | `2` | 每回合资深贵族上限 |
| `min_ex_consul_count` | `1` | 其中至少 1 名为 ex-consul（censor 供给锚） |
| `censor_anchor_years_ago` | `1` | 锚 ex-consul 任期距今回合数（< cooldown 2） |
| `history_years_ago_min` | `2` | 其余资深贵族最近任期距今下限（≥ cooldown） |
| `history_years_ago_max` | `8` | 距今上限 |
| `ex_consul_probability` | `0.5` | 非锚槽位掷为 ex-consul 的概率 |
| `age_min` | `45` | 注入年龄下界（≥ censor 门槛 42） |
| `age_max` | `58` | 注入年龄上界 |

参数约束：`0 < min ≤ max ≤ count`（clamp）、`1 ≤ min_ex_consul_count ≤ max`、
`1 ≤ censor_anchor_years_ago < cooldown`、`history_years_ago_min ≥ cooldown`。

### 4.4 代码落点

全部变更限 `src/core/systems/figure_generation_system.py`：

- `_read_veteran_supply_config(forum_rules)` — 读取参数块（全 `.get(key, default)`）
- `_build_cursus(fig, ct, offices)` — 按 `(office_type, offset)` 调 `add_office_history`
- `_create_veteran_nobile(state, slot, plan)` — 槽位构造（含年龄公式 + 统计强化）
- `_resolve_veteran_slot_count(count, plan)` — k = randint(min, min(max, count))
- `_generate_normal_figures(state, count, nobile_prob, eques_prob, plan)` — **共享核心
  循环**（`generate_figures` 与 `generate_market_figures` 均经此；原逐行相同循环体
  收敛为单点）

**零改动（边界声明）：** `figure.py`（can_hold_office / add_office_history / OfficeTerm /
create_* 工厂 / 序列化）、`population_api.py`（get_candidates / resolve_election /
archive_office_holders）、`forum_api.py`（open_market / initialize_forum_turn /
recruit_figure / resolve_forum）、hero 生成、GUI/QML/Store/DTO、WP-G 生命周期。

## 5. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.2 | 2026-08-23 | 新增 §4 市场资深贵族供给（veteran supply，E-G7-09）；§3.2 调用链修正（open_market → initialize_forum_turn → forum_api.generate_figures → figure_generation_system.generate_figures；`_generate_market_figures` 无生产调用方） |
| v1.1 | 2026-07-25 | 新增人物生成调用链说明 + figure_generation_system 引用 |
| v1.0 | 2026-07-12 | 初版 |
