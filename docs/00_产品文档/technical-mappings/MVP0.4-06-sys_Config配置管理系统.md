# MVP0.4-06-sys — Config 配置管理系统 Technical Mapping

## 1. 代码目录
```
src/core/config.py              # Config 类 (核心)
src/ui/commands/sys_config.py   # ReloadCommand / TermsCommand
```

## 2. 关键类
- `Config` — get(), reload(), to_dict(), _deep_merge()

## 3. 核心算法
点号路径解析: "section.key.subkey" → 逐级访问
加载顺序: DEFAULTS → JSON 配置文件

### 3.1 新增 key（GUI-BETA-R1 WP-C-R1，ODR-ED-01/ED-02 CLOSED）
- `economic_rules.senate_budget`：`{public_works_min:1, public_works_max_ratio:1.5, tax_farming_min_ratio:0.75, tax_farming_max_ratio:2.0, step:1}`（`data/config/game_config.json`，ODR-ED-01 权威值）
- `economic_rules.senate_war_legions`：`{default:4, min:1, cap_mode:"available_pool"}`（ODR-ED-02 权威值；max 动态 = `get_available_legions()` 池大小）
- 消费方：`senate_api._budget_range_for_contract` / `_legion_options_for_war`（值域单一来源 §6.3）；`_populate_proposal` 权威谓词；`auto_submit_proposals`（P1-a）；`process_war_takeover` 执行期征召（D-2）

### 3.2 奖励份额 snapshot（EOR20261009-03 / OD-06，FC-11/FC-12/§5.4；append-only 注记）

> 权威：`SA-Development-Task.md` v3.0（G3 FROZEN）FC-11/FC-12/§5.4；对应规格 `specifications/MVP0.4-06-sys_Config配置管理系统.md` §3.6。

- **单一来源四键（raw）**：`combat_rules.treasury_share` / `faction_share` / `commander_share` / `soldier_share`（`data/config/game_config.json` + `src/core/config.py` `DEFAULTS.combat_rules`），默认 **50/25/15/10（sum=1.0）**。
- **`Config.get_reward_share_snapshot()`** → deep-copy `{source,raw,effective,valid,reason,config_version}`：
  - `raw` = raw JSON 层逐键类型编码（`missing` / `number` / `bool` / `str` / `NoneType`（`None`）/ nonfinite→`NaN`/`+Inf`/`-Inf`）；仅四 share 键，不含整配置/秘密。
  - `effective` = 四键 `{treasury,faction,commander,soldier}` 有限 float（与 receipt `shares_effective` 同值映射）。
  - `valid`/`reason`：reason 依序 `missing` / `invalid_type` / `nonfinite` / `out_of_range` / `sum_mismatch` / `load_failed`（valid 时 `null`）。
  - `config_version` = `reward-shares/v1:` + SHA256(canonical JSON `{source,raw,effective,valid,reason}`，`sort_keys`/紧凑分隔/`ensure_ascii`/`allow_nan=False`)。
- **缺键检测点 = raw JSON schema 层**（不取深合并后的 merged `get()`；DEFAULTS 必含 4 键故 merged 永不为缺）。
- **非法兜底（fail-safe）**：任一校验失败 → 整组冻结默认 + 结构化 WARNING（`WarSystem.get_reward_shares` 写 `reward_share_fallback`，含 `reason`/`raw`/`effective`）；不崩溃、不静默。
- **公开内存赋值**：`Config.__setattr__` / `_ConfigAttrProxy` 对 `combat_rules` 四键的赋值 → 同步 `source=memory` 的 raw + 重校验 + identity（改 `testing.*` 不影响 reward 版本）。
- **reload**：成功 → 整组 raw/effective/identity 同时替换；合法 JSON 但 shares 非法 → load 成功 + 默认 + WARNING；**reload 读/解析失败 → 原 `_config` + metadata（含 hash）全部保留**，返回 False。`Config.to_dict()` 公开 merged 语义保持；metadata 不新增全局持久化。
- **消费方**：`WarSystem.get_reward_shares()` 只消费 `snapshot.effective`（不重读 JSON）；`WarSystem.compute_reward_settlement`/`resolve_war` 捕获 `config_version` 进 receipt `identity_capture`。

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 新增 economic_rules.senate_budget / senate_war_legions key（ODR-ED-01/02 权威值） |
| v1.2 | 2026-10-11 | DA-Execute (EOR20261009-03 WRRI)：OD-06/FC-11/§5.4——`combat_rules` 默认增四份额键（50/25/15/10）；新增 §3.2 奖励份额 snapshot（raw/effective/identity 单源、raw 层缺键检测、fail-safe 默认 + 结构化 WARNING、公开内存赋值同步、reload 失败保留原 raw/effective/hash）。GAME_RULE_CHANGE=YES（Owner OD-06） |
| v1.0 | 2026-07-12 | 初版 |
