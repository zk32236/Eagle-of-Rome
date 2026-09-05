# MVP0.3-03 — 军团系统

> **功能简述：** 25 个军团池的全生命周期管理：征召、维护费、解散、老兵晋升、恢复机制。军团是罗马军事力量的基本单位，涉及征召、编成、战斗使用、解散和恢复全流程。

## 1. 功能目的

在罗马共和时期，军团是军事力量的核心。本系统实现了军团从创建到解散或毁灭的全流程管理：

- 罗马最多拥有 25 个军团编号（Legio I 至 Legio XXV），初始全部为未征召（UNRAISED）状态
- 玩家征召军团，征召后消耗国库资金（**国库不设征召门槛，G1-17**：国库可为负，由赤字机制兑底）
- 军团可指派给战争，在战斗阶段参与战斗
- 军团有维护费系统，国库不足时**先解散非老兵、未指派军团节省开支，剩余差额照扣（国库允许为负，由赤字破产机制兜底）**
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
4. 扣除国库资金（**国库不设门槛，G1-17**：国库 < 费用不阻止征召，扣款照扣、国库可为负，赤字由 Resolution/game-over 兜底），将军团状态设为 `ACTIVE`

**批量征召：**
```python
def recruit_multiple(self, count: int) -> List[Tuple[int, bool, str]]:
```
1. 获取所有可征召军团（UNRAISED + DISBANDED）
2. 按序逐一征召（无逐军团国库检查，G1-17）
3. 返回已征召结果汇总
4. 控制台输出征召汇总信息

> **Veteran 持久（G1-19 / R-13，WP-G GB）：** 征召（正常重募，UNRAISED/DISBANDED → ACTIVE）**不清理 `is_veteran`**——Veteran 唯一清除点 = `mark_destroyed`（战斗摧毁）。recall → AVAILABLE / 行政解散 → DISBANDED / 正常重募全程保留。

**续战增援 N 契约引用（G1-23 / G1-24，WP-G GA）：**

```
可征召池 = get_available_legions()（UNRAISED ∪ DISBANDED）
Reinforcement N（Takeover/Continue 的新增征召数）
  正常：1 ≤ N ≤ count(UNRAISED+DISBANDED)
  零池例外：count == 0 → N = 0 允许
  国库：不参与上限（G1-17/R-10）
详细契约见 MVP0.3-02 §3.3（GA 统一暴露 senate_api.reinforcement_range）
```

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
- 计算维护费（遍历 `_legions` 全集，按状态计费）
- 基础维护费从配置读取（`legion_maintenance_base`，默认 2）
- 老兵军团额外增加（`veteran_maintenance_bonus`，默认 1）
- **维护费同集（WP-G-R1 R1-G-02 修复，2026-09-05，取代下述 WP-F R2-02「ACTIVE-only」stale 表述）：** 维护集 = `ACTIVE` + released survivors（`AVAILABLE` via `recall()`，pending Population 行政退役）+ `RECALLING`（vestigial 枚举，全仓零写点）；排除 `UNRAISED`（征召池）/ `DISBANDED`（防重复维护，R1-08）/ `DESTROYED`。provenance 限定（P2-01）：生产唯一 `AVAILABLE` 生产者 = `Legion.recall()`（仅由 `recall_from_war` 触发，即 `resolve_war` 胜利与和约批准释放面）⟹ AVAILABLE 军团 = 已动员、等待行政退役的 released survivor（非「征召后待指派」后备军）；`get_available_legions()`（UNRAISED∪DISBANDED 征召池）语义不变。对齐舰队侧 G1-14（MVP0.5-04 §2.9）既有语义，非新规则
- **WP-F R2-02（2026-08-30，ACTIVE 段保持有效）：** STALEMATE→TRUCE 后附着军团的 status 仍为 ACTIVE（war_id 指向 TRUCE war，`enter_truce` 零 recall，war_system.py:103-133），故仍计入维护费；释放仅经 canonical 后续生命周期（`execute_passed_peace_treaty → recall_from_war`，political_system.py:566-577）

```python
def apply_maintenance(self, verbose: bool = True) -> Tuple[bool, str]:
```
- 在收入阶段扣除维护费（足额全扣；短款时先解散非老兵、未指派军团节省开支，剩余差额照扣，国库允许为负，由赤字破产机制兜底）
- 短款解散按军团**实际维护费**累计节省金额（非硬编码），解散后重算应扣额并**强制记录 `legion_maintenance` 日志事件**（含应扣/实扣/缺口/解散数/扣后国库）

### 2.7 战斗结果应用

```python
def apply_battle_results(self, war_id: str, victory: bool, disaster: bool = False) -> List[int]:
```
由战斗阶段（`CombatCommand._apply_battle_result`）调用（legacy/测试面；生产 canonical 入口 = `combat_api.auto_resolve_combat`）：

| 结果 | 军团影响 | 指挥官影响 |
|------|---------|-----------|
| **TRIUMPH（凯旋）** | **全部幸存参战者晋级老兵 + 召回 → AVAILABLE + 战争结束（RESOLVED，G1-22）** | influence +10 |
| **VICTORY（胜利）** | **全部幸存参战者晋级老兵 + 战争结束（RESOLVED）→ 召回 → AVAILABLE（G1-22）** | influence +5 |
| **STALEMATE（僵持）** | 无变化，`war.duration += 1` | 无变化 |
| **DEFEAT（失败）** | **随机无放回 ceil(N/2) 实际参战 → DESTROYED**（清 war_id/commander_id/is_veteran，G1-05/06/07）；幸存保持 ACTIVE+assigned | 30%逃跑 / 20%被俘 / else 受伤 |
| **DISASTER（灾难）** | **全部实际参战 `mark_destroyed()`**（G1-07） | 阵亡（`state.mark_member_dead()`） |

> **伤亡/晋升单一 owner（WP-G GB S2/S3）：** DEFEAT/DISASTER 伤亡一律经 `MilitarySystem.apply_land_casualties(war_id, result)`（random.sample 无放回 → mark_destroyed；禁前缀序/「一半 DISBANDED」路径）；VICTORY/TRIUMPH 晋升统一在 `WarSystem.resolve_war` victory 分支（先于召回，recall 保留 Veteran）。

### 2.8 军团恢复机制

```python
def _process_legion_recovery(self, current_turn: int) -> List[int]:
```
- 从配置读取恢复间隔（`combat_rules.legion_recovery_interval`，默认 5 回合）
- 遍历所有 `DESTROYED` 状态军团（按摧毁回合升序）
- 若 `current_turn - destroyed_turn >= interval`，恢复最老的一个
- 恢复后状态变为 `DISBANDED`，`destroyed_turn` 重置为 0
- `interval <= 0` 时禁用恢复功能
- **恢复后 `is_veteran` 保持 False（摧毁已清，G1-19）**；恢复后可正常再募
- **Resolution 顺序（G1-25，权威 = `resolution_api.execute_resolution`）：** `check_victory_conditions`（含 all-25-legions-DESTROYED 败北）**先于** `process_legion_recovery`——即使某军团本 Resolution 恢复间隔已满，全 25 灭仍判共和覆灭

## 3. 核心规则

### 3.1 军团实体状态机

```
UNRAISED / DISBANDED ──[征召]──→ ACTIVE ──[指派]──→ ACTIVE(w/ war_id)
                                        │                │
                                        ├──[解散]──→ DISBANDED（Veteran 保留）
                                        │                │
                                        ├──[召回]──→ AVAILABLE（Veteran 保留）
                                        │
                   [战斗-DISASTER]──→ DESTROYED ──[恢复间隔期满]──→ DISBANDED → 可再募（Veteran False）
                   [战斗-DEFEAT]   ──→ DESTROYED（随机 ceil(N/2)，G1-05/06/07）
                   [战斗-TRIUMPH/VICTORY] ──→ AVAILABLE + 老兵晋升（幸存全晋升，G1-22）
```

### 3.2 LEGION 状态有效转换

| 当前状态 | 可转换到 | 触发操作 |
|---------|---------|---------|
| UNRAISED | ACTIVE | `recruit()`（保留 is_veteran，G1-19） |
| DISBANDED | ACTIVE | `recruit()`（保留 is_veteran，G1-19） |
| ACTIVE | AVAILABLE | 无 war_id 且 `recall()` |
| ACTIVE | ACTIVE(w/war_id) | `assign_to_war()` |
| ACTIVE(w/war_id) | AVAILABLE | `recall()` 或战斗胜利（G1-22） |
| ACTIVE/AVAILABLE | DISBANDED | `disband()`（行政解散，Veteran 保留） |
| ACTIVE(w/war_id) | DESTROYED | `mark_destroyed()`（战斗 DEFEAT 随机 ceil(N/2) / DISASTER 全灭，G1-05/06/07） |
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
触发晋升条件：TRIUMPH / VICTORY → 全部幸存参战军团晋升（G1-22）
晋升后生命周期：War RESOLVED → recall → AVAILABLE → Revenue 维护 → Population DISBANDED → Veteran 保留
```

**Veteran 持久契约（G1-19 / R-13，WP-G GB）：**

```
保留点：recall → AVAILABLE；行政解散 → DISBANDED；正常重募（UNRAISED/DISBANDED → recruit）
唯一清除点：mark_destroyed()（战斗摧毁 → DESTROYED）
代码：recruit_legion 不再置 is_veteran=False（S4）；recall/disband 不清 is_veteran（已对齐）
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
- `get_available_legions()` = UNRAISED ∪ DISBANDED = **Reinforcement N 可征召池**（G1-23/G1-24；N 上限引用见 MVP0.3-02 §3.3）

### 5.2 国库不足

- **征召不设国库门槛（G1-17/R-10）**：征召时国库 < 征召费不阻止征召——扣款照扣、国库可为负，赤字由 Resolution/game-over 兜底
- 维护费时国库 < 总维护费 → 先解散非老兵、未指派军团节省开支（按实际维护费累计）
- 解散后剩余差额照扣（国库允许为负），由赤字破产机制兜底；每回合维护费结算强制记录日志（`legion_maintenance`）

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
| 14 | 战斗中胜 → 全部幸存参战者晋升老兵 + 战争结束 | VICTORY → promote（resolve_war victory 分支）→ RESOLVED（G1-22，不再 enter_truce） | `test_phase_combat.py::test_battle_outcomes_victory` |
| 15 | 战斗僵持 → 持续 + 生成停战草案 | STALEMATE → duration+1 + enter_truce | `test_phase_combat.py::test_battle_outcomes_stalemate` |
| 16 | 战斗失败 → 随机 ceil(N/2) DESTROYED + 指挥官伤亡 | DEFEAT → random.sample ceil(N/2) DESTROYED（G1-05/06/07）+ 逃跑/被俘/受伤 | `test_phase_combat.py::test_battle_outcomes_defeat_fled` |
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
| v1.6 | 2026-09-05 | DA Sub-Agent (WP-G-R1 B1) | R1-G-02 文档同步（§2.6）：维护集由「get_active_legions()（ACTIVE-only）」改为「ACTIVE + released survivors（AVAILABLE via recall，pending Population retirement）+ RECALLING（vestigial 零写点）；排除 UNRAISED/DISBANDED/DESTROYED」——精确表达 released-survivor provenance（P2-01），不泛化为「所有 AVAILABLE+RECALLING 一概收费」；WP-F R2-02 ACTIVE 段标注保持有效 |
| v1.5 | 2026-08-31 | DA Sub-Agent (WP-G GD) | DI-3：§2.3 补「战后解散时序 + 共享入口」（G1-14：战争结束 → recall → 下个 Revenue → 下个 Population canonical 解散，GUI/CLI 共享，Veteran 保留，禁立即解散）；§2.5 补「AVAILABLE 为退役前中间态，非立即解散」；版本日志 |
| v1.0 | 2026-07-12 | Document Officer Sub-Agent J | 初版创建（代码审计完成，含恢复机制/战斗结果/停战草案） |
| v1.1 | 2026-08-27 | DA Sub-Agent (WP-E-R5) | 维护费短款行为修订 |
| v1.2 | 2026-08-30 | DA Sub-Agent (WP-F-R2) | 权威已动员计数（`mobilized_legion_count = len(get_active_legions())`）：TRUCE 附着 ACTIVE 军团计入「已动员军团」概览与维护费同集；STALEMATE 非释放点（释放仅经 canonical 后续生命周期）；GUI 概览改读权威 DTO/Store 字段（combat_api.get_combat_view + `combatMobilizedLegions` + CombatStage.qml），禁 QML 生命周期推断 |
| v1.3 | 2026-08-31 | DA Sub-Agent (WP-G GA) | 冻结语义同步（G1-17/G1-23/G1-24）：征召移除国库门槛（扣款照扣、国库可负、赤字 Resolution 兑底）；`get_available_legions()` = UNRAISED∪DISBANDED 明确定义为 Reinforcement N 可征召池（续战增援契约引用 MVP0.3-02 §3.3） |
| v1.4 | 2026-08-31 | DA Sub-Agent (WP-G GB) | 陆战权威收敛（G1-05/06/07/19/22/25）：DEFEAT=随机 ceil(N/2) DESTROYED（禁「前一半 DISBANDED」）；DISASTER=全部实际参战 DESTROYED；VICTORY/TRIUMPH=全部幸存参战者晋升 Veteran→RESOLVED→召回；Veteran 持久契约（recall/解散/重募保留，唯一清除点=mark_destroyed）；恢复生命周期显式化（Veteran False + Resolution 先判胜负后恢复）；伤亡单一 owner=apply_land_casualties |
