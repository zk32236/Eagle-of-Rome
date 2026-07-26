# EOR 产品文档体系

## 1. 文档体系目的

本目录是 EOR（Era of Rome）产品的**统一产品文档中心**，旨在建立从产品需求到技术实现的可追溯体系。

核心目标：
- **统一追溯**：将零散的历史功能文档收敛为结构化、可双向追溯的产品文档
- **降低认知门槛**：新成员或外部审计可快速理解 EOR 的功能全景
- **维护纪律**：通过 Feature Registry + 规格 + 技术映射的三层体系，控制功能膨胀与代码熵增

## 2. 三层映射关系

```
Feature_Registry.md  ←→  specifications/<Feature ID>.md  ←→  technical-mappings/<Feature ID>.md
     │                         │                                  │
功能注册表                   功能规格说明                       技术架构映射
（全景索引）                 （玩家/系统行为描述）              （代码实现线索）
```

### 2.1 第一层：Feature Registry（功能注册表）
- **位置**：`Feature_Registry.md`
- **功能**：EOR 所有功能的完整索引
- **内容**：功能编码、名称、所属系统、状态、首次实现版本

### 2.2 第二层：Specifications（功能规格说明）
- **位置**：`specifications/<Feature ID>.md`
- **功能**：功能的目的、行为、规则、验收标准等详细说明
- **受众**：产品经理、QA、开发者

### 2.3 第三层：Technical Mappings（技术架构映射）
- **位置**：`technical-mappings/<Feature ID>.md`
- **功能**：功能的代码实现线索（代码目录、关键模块、类、函数、测试映射）
- **受众**：开发者

### 2.4 回溯
- Feature Registry 和 Specifications 之间**双向链接**
- Specifications 和 Technical Mappings 之间**双向链接**

## 3. 编码与命名规则

### 3.1 功能编码格式
```
MVP<major>.<minor>-<sequence>
```

例如：`MVP0.2-01`、`MVP0.5-08`、`MVP0.7-24`

### 3.2 -sys 定义规则

> **-sys** 编码表示可独立维护的系统基础能力（System Capability），用于支撑多个 MVP 功能。它们属于产品文档体系，但不属于玩家可直接体验的游戏功能。

例如：
- `MVP0.4-03-sys` — 核心数据系统
- `MVP0.4-04-sys` — Command命令体系架构

### 3.3 文件命名规则
- **规格文件**：`specifications/<Feature ID>.md`
- **技术映射文件**：`technical-mappings/<Feature ID>.md`

## 4. 当前覆盖版本

| 版本 | 覆盖范围 | 状态 |
|------|---------|------|
| MVP 0.2 | 基础功能（选举系统、术语隔离） | ✅ 已覆盖 |
| MVP 0.3 | 核心游戏循环（回合制、战争、军团、场景加载） | ✅ 已覆盖 |
| MVP 0.4 | 经济系统（土地交易、包税权合同） | ✅ 已覆盖 |
| MVP 0.4.x | 系统基础能力（数据、Command、GameState、Config） | ✅ 已覆盖（-sys）|
| MVP 0.5 | 行省、人物、政治系统 | ✅ 已覆盖 |
| MVP 0.5.x | 系统支撑能力 | ✅ 已覆盖（-sys）|
| MVP 0.7 | 已完成游戏功能、系统能力 | ✅ 已覆盖 |
| MVP 0.9 | 规划功能 | 🕐 PLANNED |

## 5. 使用规则

1. **新增功能**：任何新增游戏功能必须先向 Feature Registry 申请编码
2. **编码冻结**：已有编码一经注册即冻结，不得修改、重排或删除
3. **规格撰写**：功能实现前必须完成规格说明文档
4. **技术映射**：功能实现后应更新技术映射文档
5. **状态变更**：功能状态变更（COMPLETE → PLANNED 等）需在 Feature Registry 中标注并说明原因
6. **-sys 编码**：系统能力编码以 `-sys` 结尾，不进入 Feature Registry 主体

## 6. 维护规则

1. **定期审计**：每季度审计一次 Feature Registry 与实际实现的一致性
2. **废弃处理**：已废弃功能移入 Superseded 区段，保留编码不删除
3. **版本对齐**：Feature Registry 中的"首次实现版本"字段在功能重构后无需更新
4. **链接维护**：移动文件后需同步更新所有交叉引用链接
5. **引用文件**：`references/` 目录存放历史引用文档副本，不修改源文件

## 7. 目录结构

```
Product Documentation/
├── README.md                         ← 本文档
├── Feature_Registry.md               ← 功能注册表
├── specifications/                   ← 功能规格说明
│   ├── MVP0.2-01.md
│   ├── MVP0.2-02.md
│   └── ...
├── technical-mappings/               ← 技术架构映射
│   ├── MVP0.2-01.md
│   ├── MVP0.2-02.md
│   └── ...
└── references/                       ← 引用文件
    ├── Historical_Feature_ID_Mapping.md
    └── Feature_ID_Review_Items.md
```

## 8. 相关文档

- [EOR 产品文档入口](../../../EOR_Document_Index.md)（如有）
- [Feature Registry](Feature_Registry.md)
- [已有正式功能编码注册表](../../Existing_Feature_ID_Register.md)
