# MVP0.5-01 — 国家公地系统 Technical Mapping

## 1. 代码目录
```
src/core/game_state.py          # _national_public_land + 同步方法 + _turn_land_sale_total
src/core/entities/province.py   # Province 实体
src/core/entities/figure.py     # Figure._land_private
src/api/game_api.py             # get_public_land_info()
src/api/forum_api.py            # resolve_forum() 公地认购结算
```

## 2. 关键方法
- `add_national_public_land()` — 增减公地 + 同步意大利
- `sync_italy_public_land()` — 意大利行省同步
- `_update_global_public_land()` — 全局公地缓存刷新
- `set_turn_land_sale_total()` / `turn_land_sale_total` — [WP-E] 本年度公地出售总额载体
  （`_turn_land_sale_total`，game_state.py；sale 法案在 political_system.py:510 并行写入）

## 3. WP-E 更新（2026-08-23）

### 3.1 三载体语义分离（GUI-BETA-011 / GUI-BETA-017）

| 载体 | 路径 | 语义 |
|:--|:--|:--|
| `_turn_land_sale_total` | game_state.py 新增 | **本年度出售总额**（sale 法案通过量，贯穿 resolve 稳定；清除点 = 次年 `_commit_settlement` A2 段） |
| `_pending_land_sale_quota` | game_state.py 既有 | **remaining_purchasable**（剩余可购额度；resolve 无条件配额处置后清） |
| `land_allocation` | forum_api.py resolve 结构化输出 | 每条认购请求的分配结果（allocated / partial / insufficient_wealth / skipped_dead） |

- **buy_land 防重**（forum_api.py:360-392）：pending 内已存在同 figure 的认购请求 →
  显式拒绝「该人物本回合已提交公地认购请求」（E-10 失败面，非静默替换）。
- **resolve_forum 无条件配额处置**（forum_api.py:604-646）：无认购且 quota > 0 →
  「📭 本回合公地未售，配额 X C 作废」+ clear（收敛 G-14 跨年残留；与既有「剩余未售
  公地配额 X C 作废」语义一致）。
- **经济价格权威值**：`land_price_per_unit` 经 `state.get_economic_rule` 读取（R-05，
  禁硬编码 Prototype 价格）。

### 3.2 相关引用

- 消费关系见 `MVP0.5-10_土地法案.md`（sale → quota + total 双写入）。
- GUI 展示见 `MVP0.5-07_战斗阶段` 无关；Forum DTO 新字段见 `EOR_UI_API_Mapping.md`。

## 4. 版本日志
| 版本 | 日期 | 修改人 | 修改说明 |
|:--|:--|:--|:--|
| v1.1 | 2026-08-23 | DA-Exec (WP-E Slice 11 PU-04) | 新增 §3：三载体语义分离（total / remaining / allocation）+ buy_land 防重 + resolve 无条件配额处置（GUI-BETA-011/017） |
| v1.0 | 2026-07-12 | Document Officer | 初版 |
