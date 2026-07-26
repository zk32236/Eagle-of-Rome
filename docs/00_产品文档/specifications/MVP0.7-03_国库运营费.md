# MVP0.7-03 — 国库运营费

> **功能简述：** 每回合收入阶段自动从国库扣除国家运营费（按已征服行省土地面积和费率计算）

## 1. 功能目的

国库运营费（National Operational Expenditure, National Opex）模拟罗马共和国对已征服行省的行政管理成本。随着罗马版图扩张，征服的行省数量增加，总土地面积扩大，运营费用相应增长。该机制提供了一种自动化的财政消耗，与战争扩张形成资金面平衡——征服越多，持有成本越高。

## 2. 玩家/系统行为

### 2.1 系统行为

1. **触发时机**：收入阶段（Revenue Phase）经济结算时
2. **执行顺序**：战争赔款 → 运营费 → 公地收益 → 私地收益 → 合同收益
3. **计算过程**：
   - 遍历所有行省，筛选出 `conquered == True` 的已征服行省
   - 汇总所有已征服行省的 `total_land`
   - 公式：`opex = int(total_land × land_price × rate)`
4. **日志记录**：包含金额、扣除后余额、总土地面积等

### 2.2 核心规则

```
opex = int(total_conquered_land × land_price_per_unit × national_opex_rate)
```

| 变量 | 默认值 | 配置路径 |
|------|--------|----------|
| `land_price_per_unit` | `10` | `economic_rules.land_price_per_unit` |
| `national_opex_rate` | `0.003` | `economic_rules.national_opex_rate` |

### 2.3 边界条件

- 无已征服行省：opex=0，国库不变
- 国库不足：允许负值，由其他逻辑处理

## 3. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.7-03_国库运营费.md)

## 4. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent C | 初版创建 |
| v1.1 | 2026-07-12 | DA Sub-Agent (Phase2 Sync) | 新增 §10 收入阶段结算流程 |
