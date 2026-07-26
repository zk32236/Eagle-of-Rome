# MVP0.5-07 — 人物类型系统（ClassTier）

> **功能简述：** 人物身份等级系统（元老/骑士/平民），影响名字生成、初始属性、官职资格和数值配置

## 1. 功能目的

人物类型系统为游戏中的每个非玩家角色（NPC）和玩家可控人物赋予社会身份等级。在罗马共和国的社会等级体系中，人物分为贵族（Nobile）、骑士（Eques）和平民（Plebeian）三个等级。不同的等级决定了人物的名字生成风格、初始属性分布、可任官职范围以及家族声望的计算方式，是政治与经济系统的基础依赖。

## 2. 玩家/系统行为

### 2.1 系统行为（人物创建）

系统通过三个工厂方法创建人物：

1. **创建贵族（Nobile）：**
   - 调用 `Figure.create_nobile(id, faction_id, age)` 创建
   - 自动生成三要素罗马名（前名·族名·绰号），例如 `Gaius · Julius · Caesar`
   - 族名从 `ROMAN_NAMES["nomina"]` 列表中选择
   - 绰号从 `ROMAN_NAMES["cognomina"]` 列表中选择
   - 初始财富范围：10~20
   - 初始人气范围：2~5
   - 初始忠诚度：7（最高）
   - 初始家族声望：根据 `FAMILY_PRESTIGE` 表映射（若族名在表中）。例如 "Julius"=3、"Cornelius"=3、"Claudius"=2 等；未在表中的族名默认声望=1
   - 核心属性侧重：魅力（charisma）随机 5~9，智慧（intelligence）随机 3~7，军事（martial）随机 3~7，热忱（zeal）随机 2~6

2. **创建骑士（Eques）：**
   - 调用 `Figure.create_eques(id, faction_id, age)` 创建
   - 自动生成二要素或三要素罗马名（50%概率不含绰号）
   - 初始财富范围：15~30（最高）
   - 初始人气范围：1~3
   - 初始忠诚度：5
   - 无家族声望（`family=None, family_prestige=0`）
   - 核心属性侧重：智慧（intelligence）随机 5~9，经济经验 `economic_exp` 随机 1~5

3. **创建平民（Plebeian）：**
   - 调用 `Figure.create_plebeian(id, faction_id, age)` 创建
   - 70%概率生成单名（仅有名字），30%概率生成 `前名·简单族名` 格式
   - 初始财富范围：3~8（最低）
   - 初始人气范围：0~2
   - 初始忠诚度：3（最低）
   - 无家族声望（`family=None, family_prestige=0`）
   - 核心属性侧重：热忱（zeal）随机 5~9

### 2.2 系统行为（名字生成器）

`RomanNameGenerator` 静态类提供三种名字生成方式：

| 方法 | 输出格式 | 适用等级 |
|------|---------|---------|
| `generate_nobile_name()` | 前名 · 族名 · 绰号 | NOBILE |
| `generate_eques_name()` | 前名 · 族名（± 绰号，50%） | EQUES |
| `generate_plebeian_name()` | 单名（70%）或 前名 · 简单族名（30%） | PLEBEIAN |

平民的名字库包含特定的 `plebeian_names` 列表（如 "Quartus"、"Octavius" 等），以及英语化的简单族名列表（如 "Carpenter"、"Smith" 等）。

### 2.3 带有历史记录的变体创建

系统提供三个带历史记录的工厂方法变体：

- `create_nobile_with_history(id, faction_id, previous_office, age)`：创建贵族并附加既往官职历史
  - 曾担任执政官（consul）：确保 `charisma >= 7`
  - 曾担任大法官（praetor）：确保 `intelligence >= 7`
- `create_eques_with_history(id, faction_id, previous_office, age)`：类似，附带经济经验值
  - 曾担任大法官：确保 `intelligence >= 8`
  - 曾担任财务官（quaestor）：确保 `martial >= 7`
- `create_plebeian_with_history(id, faction_id, previous_office, age)`

这些变体用于游戏开局时创建已有政治履历的人物。

### 2.4 迭代创建（who_goes_first 等）

人物创建后，通过 `__post_init__` 自动调用 `update_influence()` 完成初始影响力计算。

## 3. 核心规则

### 3.1 等级定义及属性影响

| 等级 | 枚举值 | 名字风格 | 初始财富 | 初始人气 | 初始忠诚 | 家族声望 | 核心属性侧重 |
|------|--------|---------|---------|---------|---------|---------|------------|
| 贵族 | `ClassTier.NOBILE` | 三要素罗马名 | 10~20 | 2~5 | 7 | 有（1~3） | 魅力5~9 |
| 骑士 | `ClassTier.EQUES` | 二/三要素罗马名 | 15~30 | 1~3 | 5 | 无 | 智慧5~9 |
| 平民 | `ClassTier.PLEBEIAN` | 单名或简化名 | 3~8 | 0~2 | 3 | 无 | 热忱5~9 |

### 3.2 等级对官职资格的影响

`can_hold_office()` 方法中，等级作为保民官资格检查依据：

- **保民官（Tribune）**：仅限骑士（EQUES）和平民（PLEBEIAN）担任
- **贵族（NOBILE）**：不可担任保民官，返回 `"Only equites and plebeians can be tribune"`
- 其他官职不受等级限制

### 3.3 家族声望体系

- 只有贵族（NOBILE）拥有族名（nomen）和家族声望
- 预设族名声望表 `FAMILY_PRESTIGE`：

| 族名 | 声望值 |
|------|--------|
| Julius, Cornelius | 3 |
| Claudius, Fabius | 2 |
| Aemilius, Servilius, Valerius | 1 |

- 未在表中的族名默认声望 = 1
- 家族声望直接影响人物影响力计算（声望 × 10）

### 3.4 可配置性

通过 `Figure.load_config(config)` 可以从配置系统覆盖 `FAMILY_PRESTIGE` 表，实现场景间差异化配置。

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 人物等级 | `Figure.class_tier` 字段 | 创建时由工厂方法设定 |
| 族名声望值 | `Figure.FAMILY_PRESTIGE` 类字段 | 预设或通过 config 加载 |
| 名字库 | `Figure.ROMAN_NAMES` 类字段 | 静态字典，包含前名/族名/绰号/平民名 |
| 配置覆盖 | `Figure.load_config(config)` | 从游戏 config 加载覆盖值 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| `Figure.class_tier` | Figure 实体 | 人物等级的 Enum 值 |
| `Figure.get_formal_name()` | 展示层 | 格式化的完整罗马名 |
| `Figure.__repr__()` | 调试/日志 | 包含等级表情符号的人物摘要 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `ClassTier` 枚举 | 定义三个等级常量 |
| `RomanNameGenerator` | 静态名字生成器，根据等级调用不同方法 |
| `Figure` 工厂方法 | `create_nobile/eques/plebeian` 创建不同等级人物 |
| `can_hold_office()` | 使用 `class_tier` 检查保民官资格 |

## 5. 状态与边界

### 5.1 正常状态

- 人物创建后 `class_tier` 字段不可为空（`PLEBEIAN` 为默认值）
- `family_prestige` 对贵族非零，对骑士/平民为 0
- `family` 对贵族为族名（nomen），对骑士/平民为 `None`

### 5.2 边界情况

- 角色死亡（`is_dead=True`）不影响 `class_tier` 字段值，仅影响能否行使否决权等
- `Family.PRESTIGE.get(nomen, 1)` 保证未注册族名至少获得声望 1
- 等级在人物生命周期内不可改变（当前设计，无等级晋升机制——见 MVP0.9-13 骑士进阶元老规划）
- 如果通过 dataclass 直接构造（不经过工厂方法），`class_tier` 默认值为 `PLEBEIAN`

### 5.3 代码特殊点

- 类中 `add_member()` 方法（第 155 行）引用了 `self._used_ids` 和 `self._members`，但 `Figure` 类中没有这两个字段。该方法可能属于容器类（如 Faction 或 GameState），在 Figure 中出现可能是复制粘贴错误，当前假定该方法的实际调用方会自动绕过或用正确对象调用。

## 6. 验收标准

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 调用 `create_nobile()` 创建人物 | `class_tier == ClassTier.NOBILE`，家族声望正确，名字为三要素格式 |
| 2 | 调用 `create_eques()` 创建人物 | `class_tier == ClassTier.EQUES`，家族声望为 0，名字为二或三要素 |
| 3 | 调用 `create_plebeian()` 创建人物 | `class_tier == ClassTier.PLEBEIAN`，家族声望为 0，名字简化为单名或双名 |
| 4 | 检查贵族初始属性分布 | 魅力 5~9，智慧 3~7，军事 3~7，热忱 2~6，忠诚度 7 |
| 5 | 检查骑士初始属性分布 | 智慧 5~9，经济经验 1~5，忠诚度 5 |
| 6 | 检查平民初始属性分布 | 热忱 5~9，忠诚度 3 |
| 7 | `can_hold_office("tribune")` 对贵族调用 | 返回 `False`，理由含 "Only equites and plebeians" |
| 8 | 未注册族名（如 "Antonius"）的贵族创建 | `family_prestige` 默认 = 1 |
| 9 | 通过 config 覆盖 `FAMILY_PRESTIGE` | 创建后使用新配置值 |
| 10 | 直接 `Figure(id, name, ...)` 构造 | `class_tier` 默认为 `PLEBEIAN` |

## 7. 历史演化与证据

- 历史审计入口：HF-017（从人物体系分离）
- 历史名称：人物类型系统
- 首次实现版本：MVP 0.5 (2026-02-25)
- 演化：从 MVP 0.4 时代简化的 `figure_type` 字符串字段演变为 `ClassTier` 枚举体系。名字生成器和工厂方法在 MVP 0.5 时统一结构化。`create_xxx_with_history` 变体为后续选举系统提供历史官职初始化支持。等级晋升（骑士→元老）规划于 MVP 0.9-13。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-07_人物类型系统.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent B | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
