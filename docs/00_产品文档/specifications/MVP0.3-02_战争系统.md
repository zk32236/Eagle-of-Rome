# MVP0.3-02 — 战争系统（战斗CRT + 战争走向）

> **功能简述：** 战争卡配置、牌堆机制、战斗CRT（2d6+战力 vs 敌军强度）、胜负条件和战争走向、战利品分配、指挥官伤亡、停战草案生成

## 1. 功能目的

战争系统是游戏的核心军事支柱。本功能实现：

- 战争牌堆管理：JSON 配置加载、触发、升级、激活的完整生命周期
- 战斗 CRT 判定：2d6 骰子 + 我方战力 vs 敌军强度 → 5 种结果
- 战斗结果处理：胜利（TRIUMPH/VICTORY）、僵持（STALEMATE）、失败（DEFEAT/DISASTER）
- 指挥官伤亡：战败时随机逃走/被俘/受伤/阵亡，灾难时阵亡
- 战利品分配：国库、派系、指挥官、士兵按配置比例分配
- 战争走向：激活、停战、降级、重激活
- 军团/舰队在战争解决时自动召回（仅 `resolve_war` 胜利或战败时触发，停战期间不召回）
- 停战草案生成：依据战斗结果生成赔款和停战期

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
   - 若有海战需求，先执行海战
   - 获取军团列表
   - 计算总战力：`commander.martial + 军团战力总和`
   - 投 2d6 骰子
   - CRT 判定：战场等级 = dice + 总战力 - 敌军强度
   - 应用战斗结果
   - 非 TRIUMPH/DISASTER 的结果尝试生成停战草案

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
- 所有军团晋级老兵并召回
- 战争胜利结算（`resolve_war(victory=True)`）
- 不生成停战草案（直接解决战争）

**VICTORY（小胜）：**
- 指挥官影响力 +5
- 所有军团晋级老兵
- 战争不结束（尝试生成停战草案）

**STALEMATE（僵持）：**
- 战争持续时间 +1
- 尝试生成停战草案

**DEFEAT（战败）：**
- 损失一半军团（状态 → DISBANDED）
- 指挥官随机结果：30% 逃走 / 20% 被俘 / 50% 受伤
- 清除 commander_id
- 战争持续时间 +1

**DISASTER（灾难）：**
- 全部军团摧毁
- 指挥官阵亡（`state.mark_member_dead`）
- 战争持续时间 +1
- 不生成停战草案

### 2.6 停战草案生成

`_maybe_generate_treaty(war_system, war, result, terms)`：
- 仅对 VICTORY / STALEMATE / DEFEAT 结果触发
- 由 `PeaceTreatyDecider` 决策草案内容
- 调用 `war_system.enter_truce(war, treaty)` 将战争置为停战状态
- 赔款和停战期由决策器决定

**赔款计算公式（`AutoPeaceTreatyDecider.decide_treaty`）：**

```
赔款基数 = war.strength × indemnity_base_multiplier（默认 10）
持续时间加成 = war.duration × indemnity_duration_multiplier（默认 5）
原始赔款 = 赔款基数 + 持续时间加成

VICTORY → 赔款 = +原始赔款（敌方赔给我方，正数）
DEFEAT   → 赔款 = -原始赔款（我方赔给敌方，负数）
STALEMATE → 赔款 = 0（无赔款）

停战期：
  VICTORY/DEFEAT → duration = 5 回合
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

战败时：
- 设置 status → DEFEATED
- 不清算任何奖励

### 2.8 指挥官返回处理

`_process_commanders_returning(war_system)`：
- 每回合战斗阶段结束时处理
- 检查停战草案已批准的战争
- 从停战战争中返回的指挥官：
  - 卸任 proconsul/propraetor 官职
  - 记录官职历史
  - 清除 is_absent

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
| enter_truce | ACTIVE/THREAT | TRUCE |
| restore_rejected_peace_treaty | TRUCE | ACTIVE |
| resolve_war (victory) | ACTIVE | RESOLVED |
| resolve_war (defeat) | ACTIVE | DEFEATED |
| deactivate_war_to_threat | ACTIVE | THREAT |
| _move_to_active (truce到期) | TRUCE | ACTIVE |
| _move_to_threat (truce到期) | TRUCE | THREAT |

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
| DISASTER | 骰子在 disaster_numbers | 全部摧毁 | 阵亡 | 持续 |
| TRIUMPH | total >= 12 | 晋级老兵+召回 | 影响力+10 | 胜利解决 |
| VICTORY | total >= 6 | 晋级老兵 | 影响力+5 | 可停战 |
| STALEMATE | 骰子在 standoff_numbers 或 -3<=total<6 | 无损 | 无损 | 持续，可停战 |
| DEFEAT | total < -3 | 一半摧毁 | 随机逃走/被俘/受伤 | 持续，可停战 |

### 3.2 战利品分配比例（可配置）

| 接收方 | 默认比例 | 配置键 |
|--------|---------|--------|
| 国库 | 50% | `combat_rules.treasury_share` |
| 指挥官派系金库 | 25% | `combat_rules.faction_share` |
| 指挥官私库 | 15% | `combat_rules.commander_share` |
| 士兵份额 | 15% | `combat_rules.soldier_share` |

### 3.3 军团战力构成

```
军团战力 = legion.get_combat_strength()
总战力 = commander.martial + sum(legion_strengths)
战场等级 = 2d6 + 总战力 - war.get_total_strength()
```

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
                         │ trigger
                    ┌────▼─────┐
                    │  THREAT   │ ◄── deactivate
                    └────┬─────┘
                         │ escalate / activate
                    ┌────▼────┐
             ┌──────│ ACTIVE  │──────┐
             │      └─────────┘      │
         enter_truce             resolve_war
             │                    (victory/defeat)
        ┌────▼─────┐         ┌──────▼────────┐
        │  TRUCE    │         │ RESOLVED/DEFEATED│
        └────┬─────┘         └───────────────┘
             │ _move_to_active / _move_to_threat
             └── ACTIVE / THREAT
```

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
| 3 | 战斗阶段成功执行 | 小胜结果，生成停战草案 | `test_phase_combat.py::test_execute_success` |
| 4 | 战斗阶段无战争 | 显示无冲突，跳过 | `test_phase_combat.py` |
| 5 | VICTORY 生成停战草案 | 生成草案并调用 enter_truce | `test_phase_combat_peace.py::test_victory_generates_treaty` |
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
