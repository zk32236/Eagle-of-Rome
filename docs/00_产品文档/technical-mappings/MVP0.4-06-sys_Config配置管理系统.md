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

## 4. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-22 | GUI-BETA-R1 WP-C-R1: 新增 economic_rules.senate_budget / senate_war_legions key（ODR-ED-01/02 权威值） |
| v1.0 | 2026-07-12 | 初版 |
