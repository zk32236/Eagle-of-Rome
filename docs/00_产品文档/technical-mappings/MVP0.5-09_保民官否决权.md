# MVP0.5-09 — 保民官否决权 Technical Mapping

> **版本：** v1.1
> **日期：** 2026-08-23（v1.0 初版 2026-07-12）
> **v1.1 依据：** Grill-Lite v1.1 **D-10**（Tribune Veto Authority）+ **ODR-WP-D-01**（CLOSED——方案 B + 防线 1/2）
> 所有 file:line 锚以最终 commit `4d09b17` 工作树实证为准。

## 1. 代码目录
```
src/core/systems/political_system.py   # _is_eligible_tribune 单一谓词 + record_veto + _set_absent（防线 2）
src/api/senate_api.py                  # _current_tribune / _viewer_has_tribune / DTO can_veto·can_auto_veto
src/core/deciders/impl/auto_tribune_veto_decider.py  # AI 否决决策器（仅 AI 路径）
src/core/systems/war_system.py         # 防线 2 内联 guard（起义指挥官置位）
src/core/scenario_loader.py            # 防线 2 内联 guard（初始总督置位）
src/ui/gui/qml/stages/SenateStage.qml  # 否决交互控件（enabled 绑定 DTO authority）
```

## 2. D-10 authority 语义（非纯概率）

否决权由**当前合法 Tribune office authority** 决定，不由「当前玩家回合」「页面可操作」或 QML 本地状态替代：

- 人类派系持有 eligible Tribune → 人类拥有否决决策权（控件可交互；AI 否决决策器不得覆盖/抢占）
- 人类派系未持有 eligible Tribune → 控件锁定；否决路由到 eligible AI Tribune / AI authority 路径
- 无 eligible Tribune 的直接/手动否决 mutation → **fail-closed 拒绝**（political_system.py:230-233 record_veto「只有保民官可以行使否决权」）
- 概率（`tribune_veto_chance`）仅存在于 **AI 路径**的决策器内部（auto_tribune_veto_decider.py:9-24，chance = config `political_rules.tribune_veto_chance`，默认 0.2）——**否决权归属判定与概率无关**；v1.0「否决概率 20%」表述仅适用于 AI 代行场景，不再描述 authority 语义

## 3. eligible Tribune 定义（ODR-WP-D-01 方案 B）

```text
eligible Tribune = office == "tribune" + 未死亡
is_absent 不参与判定
```

- **法律语义（Owner 2026-08-23 裁决）：** 保民官在职期间不能离开罗马城——法律上保民官不存在缺席；absent 对在职 tribune 不是合法状态
- **实现：** `political_system.py:749-758` `_is_eligible_tribune(member)`（方案 B：删除了原方案 A 的 `not member.is_absent` 条件）
- **⚠️ Consul 侧未动：** `_is_eligible_consul`（political_system.py:741-747）保持「在职 + 未死亡 + 未 absent」原实现（不在 ODR-WP-D-01 裁决范围）

## 4. 单谓词三消费方收敛

`_is_eligible_tribune` 为否决权链唯一资格事实源（三处消费，一改全改）：

| 消费方 | 落点 | 语义 |
|:--|:--|:--|
| `record_veto` | political_system.py:218-233（谓词搜索 :223-228） | 人类手动否决——faction 内 eligible tribune 检查，无 → fail-closed |
| `_current_tribune` | senate_api.py:284-294 | 全局首个 eligible Tribune（AI 语义；迭代范围=全局 living members，P2-05 已文档化） |
| `_viewer_has_tribune` | senate_api.py:298-302 | viewer 派系是否持有 eligible Tribune → DTO `can_veto` / `can_auto_veto`（senate_api.py:528-529） |

## 5. 防线 1 — 派遣/总督路径排除在职 Tribune（fail-closed）

全部 absent 置位路径对在职 tribune **天然 fail-closed**（office 资格结构保证）+ 测试双重锁定：

| 置位路径 | 落点 | 排除机制 |
|:--|:--|:--|
| 出征指挥官选择（AI takeover） | political_system.py:606-609 | `available_commanders` 仅收 `office in ("consul","praetor")` |
| 出征指挥官（玩家直接接管） | senate_api.py:625 | `takeover_war` 前置 `office=="consul" + 未 absent + 未死亡` |
| 宣战执行 | political_system.py:509 | consul 来自 `_find_consul_for_faction`（`_is_eligible_consul`，:778-795） |
| 总督任命（提案执行） | political_system.py:708-718 | `get_eligible_governor_candidates` 要求 office None/ex-\* |
| 总督任命（自动分配） | senate_api.py:1504 | `_tribune_absent_guard` 内联 guard（纯防御） |
| 总督出征（起义） | war_system.py:1125 | 内联条件 guard（纯防御；指挥官=行省总督） |
| 初始总督（场景加载） | scenario_loader.py:124 | 内联条件 guard（纯防御；候选 office=None） |

## 6. 防线 2 — 在职 Tribune 置位 absent 拒绝（fail-closed）

- **政治系统内统一管理点：** `political_system.py:760-774` `_set_absent(figure)` —— `office=="tribune" 且未死亡` → 拒绝置位（保持原状态 + WARNING 日志 + 返回 False；不抛异常）。政治系统内 5 处置位全部改经此方法：总督任命 :443 / 宣战执行 :509 / process_war_takeover 两分支 :643/:680 / execute_war_takeover_direct :980 —— 未来新增路径走同一方法即自动受 guard 保护
- **模块级共享 guard：** `political_system.py:18-25` `_tribune_absent_guard(figure)`（True=允许置位；False=拒绝）——senate_api.py:1504 消费；war_system.py:1125 / scenario_loader.py:124 用等价内联条件（避免跨模块 import 耦合）
- **不选 Figure property setter 的原因：** `is_absent` 为 dataclass 普通字段（figure.py:186），改 property 会波及 from_dict/to_dict 与全仓序列化面——超出「窄修正 + 最小侵入」边界（ODR-WP-D-01 落地记录）

## 7. AI 否决路由边界

- **DTO：** `get_senate_view`（senate_api.py:528-529）—— `can_veto = actionable && step==tribune_veto && viewer_has_tribune`（人类控制）；`can_auto_veto = actionable && step==tribune_veto && !viewer_has_tribune`（AI 路由）
- **AI 决策器：** `auto_tribune_veto_decider.py:9-24` —— 仅当否决权路由到 AI 时生效（chance 概率内部化，不参与 authority 判定）
- **GUI：** 否决 CheckBox enabled 绑定 DTO（canManuallySelectSenateVeto，session_store.py:373）；人类持 Tribune → 「确认否决 → 公示结果」；无 → 「AI 判定否决 → 公示结果」（SenateStage.qml tribuneActionText）
- **负向：** 未授权直接否决 mutation → fail-closed（record_veto，political_system.py:230-233）

## 8. 版本日志
| 版本 | 日期 | 摘要 |
|:-----|:-----|:------|
| v1.1 | 2026-08-23 | GUI-BETA-R1 WP-D + ODR-WP-D-01: D-10 authority 语义（非纯概率）/ 方案 B（在职+未死亡，is_absent 不参与）/ 防线 1（派遣路径 fail-closed）/ 防线 2（_set_absent + _tribune_absent_guard）/ 单谓词三消费方 / AI 否决路由边界——Trial Audit P1-PC-02/P1-PC-03 文档闭合 |
| v1.0 | 2026-07-12 | 初版 |
