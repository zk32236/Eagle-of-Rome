# MVP0.3-02 — 战争系统（战斗CRT + 战争走向）

> **功能简述：** 战争卡配置、牌堆机制、战斗CRT（2d6+战力 vs 敌军强度）、胜负条件和战争走向、战利品分配、指挥官伤亡、停战草案生成

## 1. 功能目的

战争系统是游戏的核心军事支柱。本功能实现：

- 战争牌堆管理：JSON 配置加载、触发、升级、激活的完整生命周期
- 战斗 CRT 判定：2d6 骰子 + 我方战力 vs 敌军强度 → 5 种结果
- 战斗结果处理：胜利（TRIUMPH/VICTORY）、僵持（STALEMATE）、失败（DEFEAT/DISASTER）
- 指挥官伤亡：战败时随机逃走/被俘/受伤/阵亡，灾难时阵亡
- 战利品分配：国库、派系、指挥官、士兵按配置比例分配
- 战争走向：激活、停战（仅 STALEMATE 生成条约）、三路径处置（Takeover/Continue/Peace）、胜利（RESOLVED）/ 和约批准（temporary TRUCE，G3C）
- 军团/舰队在战争解决时自动召回（`resolve_war` 胜利 / 和约批准时触发，停战期间不召回）
- 停战草案生成：**仅 STALEMATE 战斗结果（G1-08）**生成赔款和停战期

## 2. 玩家/系统行为

### 2.1 战争激活

系统流程：
1. 战争卡按年份触发威胁（`check_triggers`）
2. 威胁自动升级至等级 3 后爆发（`escalate_threats`）
3. 或由元老院主动批准激活威胁战争（`activate_threat_as_war`）

`activate_war(war_id, consul_id, legions) → bool`：
- 仅处理 THREAT 状态的战争
- 设置 `status → ACTIVE`
- 记录 activation_turn、declared_by、proposed_legions
- 从 _threats 移至 _active_wars

### 2.2 指派指挥官

`assign_commander(war_id, commander_id, legions, fleets) → bool`：
- 仅处理 ACTIVE 状态的战争
- 设置 commander_id、legions_assigned、fleets_assigned
- 记录指派回合（commander_assigned_turn）

### 2.3 战斗阶段

战斗阶段（`phase_combat.py`）按顺序处理：

1. 检查元老院阶段是否已完成
2. 获取活跃战争列表
3. 检查未指派指挥官的战争 → 继续战斗（无指挥官惩罚）
4. 对有指挥官的战争执行单场战斗：
   - 若有海战需求（`naval_required`）且**未获控**（`sea_control_acquired == false`），先执行海战（canonical 海军门，WP-G GC）：
     - 海战 TRIUMPH/VICTORY → 制海权获取（`sea_control_acquired = true`，持久至战争正式结束，G1-16）→ 本场陆战允许
     - 海战 **STALEMATE / DEFEAT / DISASTER → 陆战不执行（R-05）** → 军团保持 ACTIVE+assigned（G1-15 零陆战伤亡）→ 战争继续（duration+1）→ 本回合已处理，不阻塞战斗阶段推进
     - **已获控** → 跳过海战，直接陆战（R-06：同战未来战斗禁重复海战）
   - **获取参战集 = `MilitarySystem.get_legions_for_battle(war_id)`（live 实体附着，R-17）**
   - 计算总战力：`commander.martial + Σ legion.get_combat_strength()`（含老兵 +1）
   - 投 2d6 骰子
   - CRT 判定：战场等级 = dice + 总战力 - 敌军强度
   - 应用战斗结果
   - **仅 STALEMATE 结果尝试生成停战草案（G1-08：条约仅 STALEMATE）**

> **参与者/战力/伤亡权威 = live 实体（R-17 / §11.1，WP-G GB）：** 参战集、战力、伤亡源一律取自 live Legion 实体附着（`legion.war_id == war.id`）；`war.legions_assigned` / `war.legion_numbers` 镜像仅兼容 debug 字段，禁作战斗权威（N 件）。

### 2.4 CRT 判定规则

`_simplified_crt(dice_roll, combat_total, war) → str`：

| 条件 | 结果 | 说明 |
|------|------|------|
| 骰子在 disaster_numbers 内 | DISASTER | 灾难 |
| combat_total >= 12 | TRIUMPH | 大胜 |
| combat_total >= 6 | VICTORY | 小胜 |
| 骰子在 standoff_numbers 内或 -3 <= total < 6 | STALEMATE | 僵持 |
| combat_total < -3 | DEFEAT | 战败 |

### 2.5 战斗结果处理

**TRIUMPH（大胜）：**
- 指挥官影响力 +10
- **全部幸存参战军团晋级老兵（G1-22）** 并召回
- 战争胜利结算（`resolve_war(victory=True)` → RESOLVED，T9）
- 不生成停战草案（直接解决战争）

**VICTORY（小胜）：**
- 指挥官影响力 +5
- **全部幸存参战军团晋级老兵（G1-22）**
- 战争结束（→ RESOLVED，T10）→ 召回 → AVAILABLE（Veteran 保留）
- 不生成条约（G1-08）

**STALEMATE（僵持）：**
- 战争持续时间 +1
- 生成 pending 停战草案（战争进入 TRUCE）

**DEFEAT（战败）：**
- **随机无放回选择 ceil(N/2) 实际参战军团（live 实体）→ DESTROYED**（清 war_id/commander_id/is_veteran；G1-05/06/07）
- 幸存军团保持 ACTIVE + assigned（不召回）
- 指挥官随机结果：30% 逃走 / 20% 被俘 / 50% 受伤
- 清除 commander_id
- 战争持续时间 +1
- 战争保持 ACTIVE 继续（T11），不生成条约
- DESTROYED 军团进入恢复间隔（→ DISBANDED → 可再募）

**DISASTER（灾难）：**
- **全部实际参战军团（live 实体）→ DESTROYED**（清 war_id/commander_id/is_veteran；G1-07）
- 指挥官阵亡（`state.mark_member_dead`）
- 战争持续时间 +1
- 战争保持 ACTIVE 继续（T12），不生成条约

> **伤亡单一 owner（WP-G GB S2）：** DEFEAT/DISASTER 伤亡一律经 `MilitarySystem.apply_land_casualties(war_id, result)`（random.sample 无放回 → mark_destroyed），禁前缀序/「一半 DISBANDED」路径；VICTORY/TRIUMPH 晋升统一在 `WarSystem.resolve_war` victory 分支（先于召回，G1-22）。

> **条约仅 STALEMATE（G1-08 / R-07）：** TRIUMPH/VICTORY → 战争结束无条约；DEFEAT/DISASTER → 战争继续无条约；仅 STALEMATE 生成 pending treaty。

### 2.6 停战草案生成

`_maybe_generate_treaty(war_system, war, result, terms)`（CLI）/ `_generate_peace_treaty(war, battle_result, state)`（GUI）：
- **仅对 STALEMATE 结果触发（G1-08）**——VICTORY/DEFEAT/DISASTER/TRIUMPH 均不生成（fail-closed 守卫）
- 由 `PeaceTreatyDecider` 决策草案内容
- 调用 `war_system.enter_truce(war, treaty)` 将战争置为停战状态
- 赔款和停战期由决策器决定

**赔款计算公式（`AutoPeaceTreatyDecider.decide_treaty`）：**

```
赔款基数 = war.strength × indemnity_base_multiplier（默认 10）
持续时间加成 = war.duration × indemnity_duration_multiplier（默认 5）
原始赔款 = 赔款基数 + 持续时间加成

VICTORY → 赔款 = +原始赔款（敌方赔给我方，正数）※ 冻结模型下仅存档兼容，不再触发
DEFEAT   → 赔款 = -原始赔款（我方赔给敌方，负数）※ 冻结模型下仅存档兼容，不再触发
STALEMATE → 赔款 = 0（无赔款）※ 实际唯一生成入口

停战期：
  STALEMATE → duration = 3 回合
```

配置键：`combat_rules.peace_treaty.indemnity_base_multiplier`、`combat_rules.peace_treaty.indemnity_duration_multiplier`、`combat_rules.peace_treaty.duration_victory`、`combat_rules.peace_treaty.duration_stalemate`

### 2.7 战争胜利结算

`resolve_war(war_id, victory) → Dict[str, Any]`：

胜利时：
1. **起义战争特殊处理：** rebellion_province_id 不为空 → 行省民怨归零、指挥官声望 +1
2. **皮洛士战争解锁：** id == "pyrrhic_war" → `state.pyrrhic_war_won = True`
3. **战利品分配**（非起义战争）：
   - `war.calculate_rewards()` 获取奖励字典
   - 国库份额（默认 50%）
   - 派系金库份额（默认 25%，指挥官所属派系）
   - 指挥官私库份额（默认 15%）
   - 士兵份额（默认 15%，存入 war.soldier_share）
4. **土地奖励：** 增加国家公地
5. **家族声望：** 指挥官 family_prestige 增加
6. **行省占领：** 如果 war.unlocked_provinces 非空，占领对应行省
7. **指挥官返回：** 卸任前线官职、清除 is_absent、更新影响力
8. 从活跃列表移除，加入弃牌堆

战败时（DEFEAT/DISASTER，冻结模型 G1-08）：
- 战争保持 ACTIVE 继续（T11/T12），不 resolve、不 discard
- 不清算任何奖励
- `WarStatus.DEFEATED` 枚举退役：仅存档兼容，禁新写入（B 件 §1）

### 2.8 指挥官返回处理

- **和约批准（T5）**：`execute_passed_peace_treaty` 内联处理指挥官返回（卸任 proconsul/propraetor 官职、记录官职历史、清除 is_absent）——批准 = **TEMPORARY TRUCE**（G3C，2026-09-01 Owner Correction）：War 保持 TRUCE、Commander 返回罗马、Legion/Fleet 释放，truce_end_turn 写入，到期后恢复威胁/活跃生命周期
- `_process_commanders_returning`（旧路径，读「TRUCE+approved 容器」）：G3C 恢复 approved 战争驻留 TRUCE 容器后重新有效（双入口共享 canonical，幂等无重复）

### 2.9 战争拖延惩罚

`apply_turn_penalties() → List[str]`：
- 每回合仅对 **ACTIVE** 状态的战争应用惩罚（停战/威胁状态不触发）
- 战争持续时间 +1

### 2.10 战争状态转换

| 操作 | 前置状态 | 目标状态 |
|------|---------|---------|
| check_triggers | INACTIVE | THREAT |
| escalate_threats (level>=3) | THREAT | ACTIVE |
| activate_threat_as_war | THREAT | ACTIVE |
| enter_truce（仅 STALEMATE，G1-08） | ACTIVE | TRUCE + pending treaty |
| restore_rejected_peace_treaty（T6） | TRUCE | ACTIVE |
| resolve_war (victory) | ACTIVE | RESOLVED |
| 和约批准 execute_passed_peace_treaty（T5） | TRUCE | TRUCE（approved + truce_end_turn；到期 → THREAT → ACTIVE） |
| 和约到期（到期 → THREAT 降级）（G3C） | TRUCE（approved） | THREAT（threat_level=1，commander_id=None，Sea Control 保持） |
| Takeover（T7：P1 TRUCE+pending） | TRUCE | ACTIVE |
| Takeover（T15：P2 commanderless ACTIVE） | ACTIVE | ACTIVE |
| Continue Existing Command（T8） | TRUCE | ACTIVE |
| deactivate_war_to_threat | ACTIVE | THREAT |
| 陆战 DEFEAT/DISASTER（T11/T12） | ACTIVE | ACTIVE（继续） |

> **和约批准 = 临时停火（G3C，2026-09-01 Owner Correction）：** approved → War 保持 TRUCE（temporary truce，非战争结束）+ truce_end_turn + 到期 → THREAT（threat_level=1，禁直接 ACTIVE / 旧绑定恢复）→ 正常威胁自动升级（≥3 爆发）→ ACTIVE。Sea Control = same-War persistent（跨 approved TRUCE / 到期 / THREAT / ACTIVE 保持；仅 formal War termination 清理）。和约到期 → THREAT 降级为授权生命周期转换（G3C 恢复，非废弃）。`WarStatus.DEFEATED` 退役：战败/灾难 → ACTIVE 继续，禁新写入 DEFEATED（仅存档兼容，D-02-5）。

### 2.11 起义战争

`create_rebellion_war(province) → War`：
- 为起义行省创建战争对象
- 从配置读取起义强度 `combat_rules.rebellion_strength`
- 类型为 PROVINCIAL，naval_required=False
- `register_rebellion_war(war) → bool`：防止重复
- 胜利时镇压起义，不清算战利品

## 3. 核心规则

### 3.1 CRT 结果

| 结果 | 触发条件 | 军团影响 | 指挥官影响 | 战争影响 |
|------|---------|---------|-----------|---------|
| DISASTER | 骰子在 disaster_numbers | **全部实际参战 DESTROYED** | 阵亡 | 持续（ACTIVE，无条约） |
| TRIUMPH | total >= 12 | **全部幸存参战者晋级老兵 + 召回** | 影响力+10 | 胜利解决（RESOLVED） |
| VICTORY | total >= 6 | **全部幸存参战者晋级老兵** | 影响力+5 | 结束（→RESOLVED，不生成条约） |
| STALEMATE | 骰子在 standoff_numbers 或 -3<=total<6 | 无损 | 无损 | 持续，**生成 pending treaty（G1-08）** |
| DEFEAT | total < -3 | **随机 ceil(N/2) 实际参战 DESTROYED**（G1-05/06/07） | 随机逃走/被俘/受伤 | 持续（ACTIVE，无条约） |

### 3.2 Takeover / Continue / Peace 三路径（G1-01 / G1-21 / ODR-G-01）

面对 TRUCE + pending treaty 的战争，新执政官三选一（互斥，F 件 §2）：

| 路径 | 条约 | 战争 | 指挥官 | 军团 | 征召 |
|------|------|------|--------|------|------|
| **Peace Proposal** | 提交 → 表决 → approved/rejected | approved=TRUCE 保持 + truce_end_turn / rejected=ACTIVE | 返回罗马释放 / 保留 | 召回 / 保留 assigned | 无（经 takeover） |
| **Takeover（T7）** | 终止（cleared/non-submitted） | TRUCE→ACTIVE | **新 Consul** | 保留幸存 + 全量 rebind 新 Commander | **Reinforcement N** |
| **Continue（T8）** | 终止（cleared/non-submitted） | TRUCE→ACTIVE | **现有 Commander 保留** | 保留幸存（绑定不变） | **Reinforcement N** |

**Takeover 双前置（统一 Takeover mutation，F 件 §2.1 / ODR-G-01）：**

```
P1 — TRUCE + pending treaty（T7）：terminate treaty → TRUCE→ACTIVE → Shared Core
P2 — ACTIVE + no valid commander（T15）：无状态转换、无条约 mutation → Shared Core
异常态（ACTIVE+pending / TRUCE+无 pending / ACTIVE+valid commander）→ fail closed（禁任意接管）
```

**Shared Core（十步）：** 校验 Consul → 读实际幸存 attached Legion/Fleet 实体 → 保留全部幸存（禁裁员 G1-04/R-08）→ Legion 全量 rebind → Fleet 全量 rebind → 设 War.commander_id → 显式 Reinforcement N → 新军团 bind 新 Commander → 持久一致结果（反 split-brain R-14）。

**Continue 前置（F 件 §2.2）：** TRUCE + pending + 现有 commander 有效；清条约 → TRUCE→ACTIVE → 保留 commander（禁静默替换）→ 保留幸存 → 征召 N → 新军团 bind 现有 commander。

> **无 orphan TRUCE（R-16）：** pending treaty 必须经 T5（peace approved）/ T6（rejected）/ T7（Takeover）/ T8（Continue）之一处置，不得无期限滞留。approved TRUCE（temporary truce）持有 truce_end_turn，到期自动进入 THREAT/ACTIVE 生命周期（G3C），无需人工处置。

### 3.3 Reinforcement N 契约（G1-23 / G1-24 / G1-17）

```
Reinforcement N（新征召军团数）= 新 Consul 唯一决策量（取代 Target-N / 多退少补）

正常规则：   1 ≤ N ≤ count(UNRAISED + DISBANDED)          （G1-23）
零池例外：   count(UNRAISED + DISBANDED) == 0 → N = 0 允许（G1-24）
国库：       不参与上限（G1-17 / R-10）——征召可致国库为负，赤字由 Resolution 兑底

可征召池 = MilitarySystem.get_available_legions()（UNRAISED ∪ DISBANDED）
值域 API = senate_api.reinforcement_range(state, war)（GA 统一暴露，GB/GC/GD 消费）
```

### 3.4 战利品分配比例（可配置）

| 接收方 | 默认比例 | 配置键 |
|--------|---------|--------|
| 国库 | 50% | `combat_rules.treasury_share` |
| 指挥官派系金库 | 25% | `combat_rules.faction_share` |
| 指挥官私库 | 15% | `combat_rules.commander_share` |
| 士兵份额 | 15% | `combat_rules.soldier_share` |

### 3.5 军团战力构成

```
参战集（参与者权威，R-17 / §11.1，WP-G GB）= MilitarySystem.get_legions_for_battle(war_id)  # live 实体附着
N            = len(参战集)
军团战力     = legion.get_combat_strength()（基础 2，老兵 +1）
总战力       = commander.martial + Σ legion.get_combat_strength()
战场等级     = 2d6 + 总战力 - war.get_total_strength()
伤亡源       = 参战集（DEFEAT 随机无放回 ceil(N/2)，G1-05/06/07）
```

> **镜像字段退役（N 件 / R-17）：** `war.legions_assigned` / `war.legion_numbers` 仅兼容 debug 读取，不再作参与者/战力/伤亡权威（GUI canonical 路径已收敛至 live 实体，WP-G GB S1/S2）。

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 战争配置 | `data/cards/wars.json` | 所有战争的参数 |
| 军团战力 | `legion.get_combat_strength()` | 各军团的基础战力 |
| 指挥官 martial | `Figure.martial` | 军事能力加成 |
| 骰子 | `random.randint(2, 12)` | 随机数 |
| 敌军强度 | `war.get_total_strength()` | 敌军总战力 |
| 强制结果开关 | `config["testing.force_battle_result"]` | 调试用 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 战斗结果 | 控制台 / state.log_event | CRT 结果和摘要 |
| 战利品分配 | 国库/派系/指挥官/士兵 | 按比例分配 |
| 停战草案 | war.peace_treaty | 包含赔款和停战期 |
| 指挥官状态 | war.commander_status | 战斗后状态变化 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `War` / `WarStatus` / `WarType` | 战争实体和枚举 |
| `WarSystem` | 核心战争管理系统 |
| `MilitarySystem` | 军团管理 |
| `NavalSystem` | 海军管理（海战集成） |
| `CombatCommand` | 战斗阶段命令 |
| `PeaceTreatyDecider` | 停战草案决策器接口，定义 `decide_treaty(war, battle_result, state) → Dict` |
| `AutoPeaceTreatyDecider` | 自动停战草案生成实现，根据战争强度和持续时间计算赔款额（赔款 = 强度×基数 + 持续回合×加成，正负号取决于战斗结果） |
| `Legion` | 军团实体 |
| `Figure` | 人物实体（指挥官 martial） |
| `TerminologyService` | 术语服务 |

## 5. 状态与边界

### 5.1 战争状态合法转换

```
                    ┌──────────┐
                    │ INACTIVE │
                    └────┬─────┘
                         │ trigger (T1)
                    ┌────▼─────┐
                    │  THREAT   │ ◄── deactivate
                    └────┬─────┘
                         │ escalate (T2) / activate (T3)
                    ┌────▼────┐
             ┌──────│ ACTIVE  │──────┐
             │      └─────────┘      │
         T4 陆战 STALEMATE     T9/T10 胜利
             │                    (→RESOLVED)
        ┌────▼─────┐
        │  TRUCE    │
        │ +pending  │
        └────┬─────┘
             │ T5 和约批准 → TRUCE 保持（temporary truce，G3C）
             │ T6 拒绝 → ACTIVE（保留 commander）
             │ T7 Takeover → ACTIVE（新 Commander）
             │ T8 Continue → ACTIVE（现有 Commander）
             │ T5' 到期（truce_end_turn 到）→ THREAT（threat_level=1）
             └── escalate_threats（≥3 爆发）──▶ ACTIVE（正常威胁升级）

ACTIVE ──T11/T12（陆战 DEFEAT/DISASTER）──▶ ACTIVE（继续）
ACTIVE（no valid commander）──T15（Takeover P2）──▶ ACTIVE（新 Commander）
```

> **和约批准 = 临时停火（G3C，2026-09-01 Owner Correction）：** approved → War 保持 TRUCE
> （temporary truce，非战争结束）+ truce_end_turn；到期 → THREAT（threat_level=1，
> commander_id=None，不恢复旧绑定，Sea Control 保持）→ 正常威胁自动升级（≥3 爆发）→ ACTIVE。
> TRIUMPH/VICTORY → RESOLVED 为独立生命周期（resolve_war）。`DEFEATED` 枚举仅存档兼容，禁新写入（B 件 §1）。

### 5.2 无效操作

- 不可激活非 THREAT 状态的战争
- 不可指派指挥官给非 ACTIVE 状态的战争
- 不可重复激活同一战争（`activate_war` 通过 status 检查）

### 5.3 无指挥官

- 活跃战争无指挥官 → 战斗阶段提示 `"wars without commanders"`
- 战斗继续进行（无指挥官 martial 加成）

### 5.4 强制结果

- 调试配置 `testing.force_battle_result` 可跳过随机判定
- 用于测试特定战斗结果

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 | 测试文件 |
|---|----------|---------|---------|
| 1 | 战争触发年份边界 | 年份到达时触发，未到达时不触发 | `test_war_system.py::TestWarThreatMechanism` |
| 2 | 威胁自动升级 | 1→2→3，3 级时爆发 | `test_war_system.py::test_auto_escalation` |
| 3 | 战斗阶段成功执行 | 僵持（STALEMATE）结果生成停战草案 | `test_phase_combat.py::test_execute_success` |
| 4 | 战斗阶段无战争 | 显示无冲突，跳过 | `test_phase_combat.py` |
| 5 | VICTORY 不生成草案（G1-08） | 不调用 enter_truce（仅 STALEMATE 生成） | `test_phase_combat_peace.py::test_victory_generates_no_treaty` |
| 6 | TRIUMPH 不生成草案 | 不调用 enter_truce | `test_phase_combat_peace.py::test_triumph_no_treaty` |
| 7 | STALEMATE 生成草案 | 生成草案 | `test_phase_combat_peace.py::test_stalemate_generates_treaty` |
| 8 | 胜利奖励按比例分配 | 国库/派系/指挥官/士兵正确分配 | `test_war_rewards.py::test_victory_rewards_distribution` |
| 9 | 胜利无指挥官 | 全部战利品归国库 | `test_war_rewards.py::test_victory_no_commander` |
| 10 | 战败无奖励 | 国库/派系/指挥官不变 | `test_war_rewards.py::test_defeat_no_rewards` |
| 11 | 土地奖励 | 国家公地增加 | `test_war_rewards.py::test_rewards_with_land` |
| 12 | 家族声望奖励 | 指挥官声望增加 | `test_war_rewards.py::test_family_prestige_increase` |
| 13 | 停战战争状态切换 | ACTIVE→TRUCE→THREAT 正确切换 | `test_war_ext.py::test_war_system_truce_lists` |
| 14 | 起义战争创建 | rebellion_province_id 正确 | `war_system.py create_rebellion_war` |
| 15 | War 序列化完整 | to_dict/from_dict 正确恢复 | `test_war.py::test_war_to_dict_and_from_dict` |

## 7. 历史演化与证据

- **首次实现版本：** MVP 0.3（基础战争卡 + 简单 CRT）
- **MVP 0.5 扩展：** 战利品分配（按比例分割国库/派系/指挥官/士兵）、战争加载/序列化完善、指挥官返回处理
- **MVP 0.7 扩展：** 停战草案（含决策器）、指挥官死亡/返回、海战集成、战争状态 TRUCE/THREAT 切换
- **代码入口：** `war_system.py`（核心逻辑）+ `war.py`（实体）+ `phase_combat.py`（战斗阶段）
- **测试文件：** `test_war_system.py`、`test_war_rewards.py`、`test_phase_combat.py`、`test_phase_combat_peace.py`、`test_war.py`、`test_war_ext.py`

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.3-02_战争系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Worker K | 初版创建 |
| v1.1 | 2026-07-12 | DA Sub-Agent (GLM Audit Fix) | 修复：停战草案赔款公式、召回条件、惩罚范围 |
| v1.2 | 2026-07-28 | PM (Augustus) | 新增技术债务附录：战斗三动作残桩（scout/defence/attack） |
| v1.3 | 2026-08-31 | DA Sub-Agent (WP-G GA) | 冻结语义同步（G1-08/G1-14/G1-21/G1-23/G1-24/G1-17/ODR-G-01）：条约仅 STALEMATE；Takeover 双前置 P1/P2 + Continue/Peace 三路径；Reinforcement N 契约（零池例外、国库无关）；DEFEATED 枚举退役禁新写入。⚠️ 其中「approved=战争正式结束（RESOLVED，truce 到期恢复退役）」条款 = DESIGN DRIFT，已被 v1.6（G3C）撤销 |
| v1.4 | 2026-08-31 | DA Sub-Agent (WP-G GB) | 陆战权威收敛（G1-05/06/07/19/22/25）：DEFEAT=随机无放回 ceil(N/2)→DESTROYED（禁「一半 DISBANDED」/前缀序）；DISASTER=全部参战 DESTROYED；TRIUMPH/VICTORY=全部幸存参战者晋升 Veteran→RESOLVED→召回→AVAILABLE；参战集/战力/伤亡源=live 实体（镜像退役，R-17）；伤亡单一 owner=apply_land_casualties |
| v1.5 | 2026-08-31 | DA Sub-Agent (WP-G GC) | 海军门语义同步（G1-09/16/R-05/R-06）：§2.3 海战前置句补完整状态机——STALEMATE/DEFEAT/DISASTER 阻断陆战（legacy CLI 同步）、TRIUMPH/VICTORY 获控后同场陆战、已获控跳过海战；制海权持久至战争正式结束（sea_control_acquired 权威字段，替代 _sea_control_ratio；GameState 存档接线 = GD） |
| v1.6 | 2026-09-01 | DA Sub-Agent (WP-G G3C) | Treaty Lifecycle 修正（Owner Correction 2026-09-01 / DC-TREATY-LIFECYCLE-CORRECTION-01）：**approved = TEMPORARY TRUCE（撤销 v1.3 的 approved=RESOLVED）**——War 保持 TRUCE + truce_end_turn + Commander 返回 + Legion/Fleet 释放 + Revenue 最后维护 + Population DISBANDED；到期 → THREAT（threat_level=1，禁直接 ACTIVE / 旧绑定恢复，Sea Control 保持）→ 自动升级 → ACTIVE；TRIUMPH/VICTORY = RESOLVED 独立；ODR-CAND-01 修复 = enqueue-then-clear（_legions_to_disband 双入残留消除） |

---

## 附录 A — 已知技术债务

### A.1 战斗三动作残桩（scout / defence / attack）

**引入时间：** Phase 6 Combat full flow (`8b8e26d`)，`S1 重构 (f0126e7)` 保留

**现状：** `combat_api.py` 和 `CombatStage.qml` 包含三种动作骨架：

| 动作 | 状态 | 说明 |
|:-----|:----:|:------|
| `attack`（进攻） | ✅ 完整 | 标准战斗执行，`do_combat_action()` → `_compute_combat_result()` → `resolve_war()`，写入 GameState。Product Spec 定义的标准路径 |
| `scout`（侦查） | ✅ 预览模式 | `do_combat_action(action="scout")` 固定 dice=7 计算并返回预览结果，不写入 GameState。设计正确但未在产品文档中定义 |
| `defence`（防御） | ⚠️ 残桩 | `do_combat_action(action="defence")` → +2 bias 偏置生效，但 `resolve_war(war_id, victory)` 不接收 action 参数，defence 与 attack 的损失/战利品完全相同。本质上是一个+2 attack，无语义差异 |

**当前 GUI（2026-07-28 Owner 决策）：** 砍回只剩 `attack` 按钮。`scout` 和 `defence` 按钮移除。

**以后正式启用三动作前需完成：**
- [ ] 产品文档定义三动作的独立语义与平衡规则
- [ ] `resolve_war()` 新增 action 感知（防御减损失、侦查获情报）
- [ ] CLI 命令同时暴露三动作
- [ ] bias 值改为 config 配置（当前硬编码 defence:+2, scout:-1）
- [ ] 三动作的测试覆盖
