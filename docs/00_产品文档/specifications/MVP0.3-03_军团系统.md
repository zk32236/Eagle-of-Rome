# MVP0.3-03 — 军团系统

> **功能简述：** 10 个军团池的全生命周期管理：征召、维护费、解散、老兵晋升、恢复机制。军团是罗马军事力量的基本单位，涉及征召、编成、战斗使用、解散和恢复全流程。

## 1. 功能目的

在罗马共和时期，军团是军事力量的核心。本系统实现了军团从创建到解散或毁灭的全流程管理：

- 罗马最多拥有 25 个军团编号（Legio I 至 Legio XXV），初始全部为未征召（UNRAISED）状态
- 玩家在国库充裕时征召军团，征召后消耗国库资金
- 军团可指派给战争，在战斗阶段参与战斗
- 军团有维护费系统，国库不足时自动解散部分军团
- 军团可晋升为老兵，获得战力加成
- 军团被摧毁后进入恢复流程，按间隔回合数自动恢复为可重新征召状态
- 形成"国库→征召→指派→战斗→维护→恢复/解散"的完整军事管理链路

## 2. 玩家/系统行为

### 2.1 军团初始化

```python
def _initialize_legions(self):
    for i in range(1, self.MAX_LEGIONS + 1):  # MAX_LEGIONS = 25
        legion = Legion(number=i)
        self._legions.append(legion)
```

- **系统启动时：** `MilitarySystem.__init__()` 调用 `_initialize_legions()`
- 创建编号 1–25 的 25 个 Legion 实例，默认状态均为 `UNRAISED`（未征召）

### 2.2 征召操作

**单军团征召：**
```python
def recruit_legion(self, legion_number: int) -> Tuple[bool, str]:
```
1. 检查军团编号是否有效
2. 检查军团状态是否允许征召（必须为 `UNRAISED` 或 `DISBANDED`）
3. 从配置读取征召费用（`legion_recruit_cost`，默认 10）
4. 检查国库是否充足
5. 扣除国库资金，将军团状态设为 `ACTIVE`

**批量征召：**
```python
def recruit_multiple(self, count: int) -> List[Tuple[int, bool, str]]:
```
1. 获取所有可征召军团（UNRAISED + DISBANDED）
2. 按序逐一征召，每次检查国库是否足够
3. 国库不足时中断，返回已征召结果汇总
4. 控制台输出征召汇总信息

### 2.3 解散操作

**单军团解散：**
```python
def disband_legion(self, legion_number: int) -> Tuple[bool, str]:
```

**批量解散（用于战争结束）：**
```python
def disband_legions_for_war(self, legion_numbers: List[int]) -> Tuple[int, List[str]]:
```

前置约束：
- 军团不能指派给战争（`war_id` 必须为 None）
- 不能是 `DISBANDED` 或 `DESTROYED` 状态
- 军团必须为 `ACTIVE`、`AVAILABLE` 或 `RECALLING` 状态

### 2.4 指派到战争

```python
def assign_to_war(self, legion_numbers: List[int], war_id: str, commander_id: int) -> Tuple[int, str]:
```
1. 获取战争对象（从战争系统获取）
2. 遍历指定编号的军团
3. 检查军团状态是否为 `ACTIVE`、是否尚未指派给其他战争
4. 调用 `legion.assign_to_war()` 设置 war_id、commander_id，状态变为 `ACTIVE`
5. 将军团编号记录到战争对象（通过 `war.add_legion_number(num)`）

### 2.5 从战争召回

```python
def recall_from_war(self, war_id: str) -> int:
```
- 遍历所有军团，找到指派给指定战争的所有军团
- 调用 `legion.recall()` 将状态恢复为 `AVAILABLE`

### 2.6 维护费

```python
def calculate_maintenance(self) -> Tuple[int, Dict[str, int]]:
```
- 计算所有 `ACTIVE` 状态军团的维护费
- 基础维护费从配置读取（`legion_maintenance_base`，默认 2）
- 老兵军团额外增加（`veteran_maintenance_bonus`，默认 1）

```python
def apply_maintenance(self, verbose: bool = True) -> Tuple[bool, str]:
```
- 在收入阶段扣除维护费
- 国库不足时自动解散部分非老兵、未指派军团以节省开支

### 2.7 战斗结果应用

```python
def apply_battle_results(self, war_id: str, victory: bool, disaster: bool = False):
```
由战斗阶段（`CombatCommand._apply_battle_result`）调用：

| 结果 | 军团影响 | 指挥官影响 |
|------|---------|-----------|
| **TRIUMPH（凯旋）** | 全部晋升老兵 + 召回 + 战争结束 | influence +10 |
| **VICTORY（胜利）** | 全部晋升老兵 | influence +5 |
| **STALEMATE（僵持）** | 无变化，`war.duration += 1` | 无变化 |
| **DEFEAT（失败）** | 前一半军团 DISBANDED + 召回 | 30%逃跑 / 20%被俘 / else 受伤 |
| **DISASTER（灾难）** | 全部 `mark_destroyed()` | 阵亡（`state.mark_member_dead()`） |

### 2.8 军团恢复机制

```python
def _process_legion_recovery(self, current_turn: int) -> List[int]:
```
- 从配置读取恢复间隔（`combat_rules.legion_recovery_interval`，默认 5 回合）
- 遍历所有 `DESTROYED` 状态军团（按摧毁回合升序）
- 若 `current_turn - destroyed_turn >= interval`，恢复最老的一个
- 恢复后状态变为 `DISBANDED`，`destroyed_turn` 重置为 0
- `interval <= 0` 时禁用恢复功能

## 3. 核心规则

### 3.1 军团实体状态机

```
UNRAISED ──[征召]──→ ACTIVE ──[指派]──→ ACTIVE(w/ war_id)
                          │                  │
                          ├──[解散]──→ DISBANDED
                          │                  │
                          ├──[召回]──→ AVAILABLE
                          │
                     [战斗-DISASTER]──→ DESTROYED ──[恢复间隔期满]──→ DISBANDED
                     [战斗-DEFEAT]  ──→ DISBANDED(部分)
                     [战斗-TRIUMPH] ──→ AVAILABLE + 老兵晋升
```

### 3.2 LEGION 状态有效转换

| 当前状态 | 可转换到 | 触发操作 |
|---------|---------|---------|
| UNRAISED | ACTIVE | `recruit()` |
| DISBANDED | ACTIVE | `recruit()` |
| ACTIVE | AVAILABLE | 无 war_id 且 `recall()` |
| ACTIVE | ACTIVE(w/war_id) | `assign_to_war()` |
| ACTIVE(w/war_id) | AVAILABLE | `recall()` 或战斗结束 |
| ACTIVE/AVAILABLE | DISBANDED | `disband()` |
| AVAILABLE/ACTIVE/RECALLING | DESTROYED | `mark_destroyed()`（战斗灾难） |
| DESTROYED | DISBANDED | `recover()`（恢复间隔期满） |

### 3.3 军团禁用操作

- 指派给战争的军团不可解散（`war_id` 不为 None）
- 已解散或已摧毁的军团不可再次解散
- 未征召或已解散的军团不可直接指派战争
- `DESTROYED` 状态的军团不可直接征召（必须先恢复）

### 3.4 老兵晋升规则

```
基础战力 = 2
老兵加成 = +1（is_veteran = True）
触发晋升条件：战斗结果 VICTORY 或 TRIUMPH
```

### 3.5 军团类型机制

军团支持三种历史类型：
- **波利比乌斯（polybian）**：共和国早期（默认）
- **马略（marius）**：共和国晚期
- **奥古斯都（augustan）**：帝国早期

通过 `set_legion_type()` 设置，当前版本为类型预留而未实现差异化战力/成本。

### 3.6 恢复间隔配置

```json
{
  "combat_rules": {
    "legion_recovery_interval": 5
  }
}
```

- 默认 5 回合
- 设为 0 时禁用恢复
- 每 interval 回合恢复一个最老的被摧毁军团
- 恢复到 `DISBANDED` 状态（可重新征召）

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 征召命令 | `RecruitCommand` / `MilitarySystem.recruit_legion()` | 玩家输入军团编号 |
| 解散命令 | `DisbandCommand` / `MilitarySystem.disband_legion()` | 玩家输入军团编号或 all |
| 指派命令 | `AssignCommand` / `MilitarySystem.assign_to_war()` | 玩家选择战争、指挥官、军团 |
| 国库资金 | `state.treasury` | 整数，征召时扣除 |
| 回合编号 | `state.turn.turn_number` | 用于恢复间隔判断 |
| 战斗结果 | `CombatCommand._simplified_crt()` | TRIUMPH/VICTORY/STALEMATE/DEFEAT/DISASTER |
| 恢复配置 | `state.config["combat_rules.legion_recovery_interval"]` | 默认 5 回合 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 军团状态变化 | `Legion.status` | 状态机转换 |
| 国库扣除 | `state.treasury` | 征召费用和维护费 |
| 战斗摘要 | 控制台打印 | 战斗结果、损失、晋升信息 |
| 恢复通知 | 控制台打印 | 回收复的军团编号 |
| 军团显示 | 控制台打印 / `to_display_dict()` | 军团状态概览（模拟 + emoji） |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `GameState` | 全局状态：国库、回合、战争系统、军事系统 |
| `WarSystem` | 获取战争对象，管理战争生命周期 |
| `War` | 战争实体：`add_legion_number()` 记录军团编号 |
| `Figure` | 指挥官实体：`martial` 属性参与战力计算 |
| `GameTurn` | 回合信息：`turn_number` 用于恢复判断 |
| `EconomicService` | 维护费结算（通过 state 交互） |
| `TerminologyService` | 术语隔离（`legion` / `commander` / `currency`） |
| `PeaceTreatyDecider` | 战斗后的停战草案生成（MVP 0.7） |
| `Config` | 经济规则和战斗规则配置 |

## 5. 状态与边界

### 5.1 军团池边界

- `MAX_LEGIONS = 25`：最多 25 个军团编号
- 初始化时全部为 `UNRAISED` 状态
- 所有军团编号 1–25，超出无效

### 5.2 国库不足

- 征召时国库 < `legion_recruit_cost`（默认 10）→ 征召失败
- 维护费时国库 < 总维护费 → 自动解散非老兵、未指派军团
- 自动解散按优先级：非老兵 > 未指派，直到节省金额覆盖缺口

### 5.3 战斗边界

- 无军团指派到战争时，战斗跳过（`war.duration += 1`）
- 无指挥官指派到战争时，战斗跳过（打印提示）
- 指挥官已死亡时，战斗跳过（调用 `recall_commander()`）

### 5.4 恢复边界

- `interval <= 0`：禁用恢复，被摧毁军团永久消失
- 恢复队列为空时，处理无效果
- 每次只恢复一个最老的满足条件的军团
- 恢复后的军团可重新征召

### 5.5 显示边界

- `display_legion_status()` 显示所有 25 个军团的状态
- 使用 emoji 标识状态：⚪ UNRAISED, 🟢 AVAILABLE, ⚔️ ACTIVE, 🔙 RECALLING, 💀 DISBANDED/DESTROYED
- 已摧毁的军团额外显示 `(摧毁于 N 回合)`

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 | 测试文件 |
|---|----------|---------|---------|
| 1 | 初始状态：所有军团 UNRAISED | 25 个军团，全部 UNRAISED | `test_legion_recovery.py::test_initial_state` |
| 2 | 标记军团被摧毁 | status → DESTROYED, destroyed_turn → current_turn, war_id/commander_id → None, veteran → False | `test_legion_recovery.py::test_mark_destroyed` |
| 3 | 被摧毁军团按摧毁回合排序 | `get_destroyed_legions()` 返回升序列表 | `test_legion_recovery.py::test_get_destroyed_legions_order` |
| 4 | 恢复条件未满足时不应恢复 | `current_turn - destroyed_turn < interval` → 恢复列表为空 | `test_legion_recovery.py::test_recovery_not_yet` |
| 5 | 刚好满足恢复条件时恢复最老的一个 | 每次恢复一个最老的满足条件的军团 | `test_legion_recovery.py::test_recovery_just_meet` |
| 6 | 从配置读取恢复间隔 | 修改配置后间隔生效 | `test_legion_recovery.py::test_recovery_interval_config` |
| 7 | 恢复间隔为 0 时禁用恢复 | `interval = 0` → 永不恢复 | `test_legion_recovery.py::test_recovery_with_zero_interval` |
| 8 | 战斗灾难导致军团全部摧毁 | DISASTER → 全部 `mark_destroyed(current_turn)` | `test_legion_recovery.py::test_apply_battle_results_disaster` |
| 9 | 完整恢复周期测试 | 摧毁 → 等待 N 回合 → 恢复 → 可重新征召 | `test_legion_recovery_manual.py::test_legion_recovery` |
| 10 | 解散指派给战争的军团失败 | 有 war_id 的军团解散失败 | `test_military_system_disband.py::test_disband_with_war_id` |
| 11 | 早已解散的军团再次解散失败 | 二次解散返回 0 | `test_military_system_disband.py::test_disband_already_disbanded` |
| 12 | 批量解散混合结果 | 部分成功 + 部分报错 | `test_military_system_disband.py::test_disband_existing_legions` |
| 13 | 战斗大胜 → 全部晋升老兵 + 召回 + 战争结束 | TRIUMPH → promote + recall + resolve_war | `test_phase_combat.py::test_battle_outcomes_triumph` |
| 14 | 战斗中胜 → 全部晋升老兵 + 生成停战草案 | VICTORY → promote + enter_truce | `test_phase_combat.py::test_battle_outcomes_victory` |
| 15 | 战斗僵持 → 持续 + 生成停战草案 | STALEMATE → duration+1 + enter_truce | `test_phase_combat.py::test_battle_outcomes_stalemate` |
| 16 | 战斗失败 → 部分解散 + 指挥官伤亡 | DEFEAT → 一半 DISBANDED + 逃跑/被俘/受伤 | `test_phase_combat.py::test_battle_outcomes_defeat_fled` |
| 17 | 战斗灾难 → 全部摧毁 + 指挥官阵亡 | DISASTER → mark_destroyed + mark_member_dead | `test_phase_combat.py::test_battle_outcomes_disaster` |
| 18 | 无军团指派到战争 → 跳过战斗 | legions=[] → 无战斗 | `test_phase_combat.py::test_no_legions_assigned` |
| 19 | 无活跃战争 → 跳过阶段 | active_wars=[] → phase complete | `test_phase_combat.py::test_no_active_wars` |
| 20 | 战斗阶段已执行 → 拒绝再次执行 | 已标记 combat → 返回 False | `test_phase_combat.py::test_already_executed` |

## 7. 历史演化与证据

- **首次实现版本：** MVP 0.3（2026-02-xx）
- **初始实现：** Legion 实体 + MilitarySystem 基础征召/解散/指派 → 10 个军团
- **MVP 0.7 扩展：** 军团数量扩展至 25、军团恢复机制、LegionStatus 增加 RECALLING/DESTROYED、
  军团类型系统（polybian/marius/augustan）、战斗结果应用重构、停战草案生成
- **代码入口：** `legion.py` (实体) + `military_system.py` (系统) + `phase_combat.py` (战斗阶段触发)
- **关键变更：** 军团数量从 10 增至 25、`mark_destroyed()` 和 `recover()` 方法新增、`legion_recovery_interval` 配置项

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.3-03_军团系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent J | 初版创建（代码审计完成，含恢复机制/战斗结果/停战草案） |
