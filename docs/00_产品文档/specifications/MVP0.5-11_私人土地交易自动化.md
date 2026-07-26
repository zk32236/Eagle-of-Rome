# MVP0.5-11 — 私人土地交易自动化

> **功能简述：** AI 系统自动在贵族和骑士之间执行私人土地交易

## 1. 功能目的

私人土地交易是罗马共和国时期贵族（Nobile）出售土地给骑士（Eques）的重要经济行为。该功能实现 AI 自动化交易流程：在有财务官（Quaestor）在场时，系统自动在广场阶段的交易市场环节生成一笔土地交易，由 LandTradingService 执行实际结算。该机制使国家公地分配系统之外存在一条独立的私人土地流转渠道。

## 2. 玩家/系统行为

### 2.1 系统行为（自动模式）

1. 广场阶段 Step 4（交易市场环节）由 `ForumCommand._handle_step_4()` 处理
2. 当 `auto_mode = True` 且存在财务官时，调用 `self.land_trade_decider.decide_trade(self.state)`
3. 如果返回交易信息 `(seller_id, buyer_id, amount)`，直接调用 `LandTradingService.execute_trade()`
4. 交易成功后输出 "💱 Trade complete: ..."
5. 交易后更新相关派系的总土地（ faction.update_total_land() ）

### 2.2 系统行为（自动模式—AI 玩家）

1. 当 `auto_mode = False` 但为 AI 玩家时，调用 `self.auto_processor.process_land_trade(player_id, faction)`
2. 处理器内部调用 `self.land_trade_decider.decide_trade(self.state)`
3. 如有交易信息，调用 `forum_api.transact_land(self.state, player_id, seller_id, buyer_id, land, price)` 记录交易
4. 记录后放入 `_forum_pending["land_trades"]`

### 2.3 玩家行为（手动模式—财务官）

1. 在交易市场环节（UI_03-4），有财务官的玩家可输入：
   - `transact <卖家ID> <买家ID> <土地数量> <价格>` → 发起交易
   - `next` → 跳过
2. 调用 `forum_api.transact_land()` 校验：
   - 卖家和买家都必须属于当前玩家派系（非 bypass 模式）
   - 卖家必须存活且有足够土地
   - 卖家必须 `can_sell_land(amount)`
3. 校验通过后记录到 `_forum_pending["land_trades"]`

### 2.4 交易结算

1. 所有玩家的交易记录在步骤结束后通过 `forum_api.resolve_land_trades()` 统一结算
2. 结算时创建 `LandTradingService` 实例，对每条记录调用 `service.execute_trade()`
3. 交易成功后更新双方人物影响力、双方派系总土地
4. 输出交易结果

## 3. 核心规则

### 3.1 自动交易条件

| 条件 | 说明 |
|------|------|
| 有财务官 | 必须至少有一个存活人物担任 Quaestor |
| 有贵族与骑士 | 存活人物中必须同时有 NOBILE 和 EQUES 等级 |
| 卖方有土地 | 选中的贵族卖家的 `land_private > 0` |
| 功能开关 | 可通过 `forum_rules.enable_private_land_trade` 关闭（默认 False） |

### 3.2 交易选择逻辑

`AutoLandTradeDecider.decide_trade()`：

1. 获取所有存活人物
2. 筛选出 NOBILE 等级 = nobles，EQUES 等级 = equites
3. 如果两者都非空，`random.choice(nobles)` 选卖家，`random.choice(equites)` 选买家
4. 如果卖家 `land_private <= 0`，返回 None（不交易）
5. 交易数量 `amount = random.randint(1, seller.land_private)`
6. 返回 `(seller.id, buyer.id, amount)`

### 3.3 土地价格计算

`LandTradingService.calculate_land_price(seller, buyer)`：

- 基础价格：10 塔兰特/单位
- 价格修正因素：

| 条件 | 修正 |
|------|------|
| seller.popularity >= buyer.popularity | +0.20 |
| seller.influence >= buyer.influence | +0.10 |
| buyer.popularity >= 10 | -0.10 |
| 同一派系 | -0.20 |
| 敌对派系 | +0.30（MVP 简化版暂为 neutral） |

- 修正范围：0.5 ~ 2.0（`max(0.5, min(2.0, modifier))`）

### 3.4 交易执行

`LandTradingService.execute_trade(seller_id, buyer_id, amount, price_per_unit)`：

1. 校验卖家和买家存在且存活
2. 校验 seller.land_private >= amount
3. 校验 buyer.wealth >= total_cost
4. 执行：seller.sell_land(amount, price_per_unit)
5. 执行：buyer.buy_land(amount, price_per_unit)
6. 买方财富不足时回滚卖家
7. 更新双方影响力（`seller.update_influence()`, `buyer.update_influence()`）
8. 更新双方所属派系总土地
9. 记录交易历史到 seller.land_trade_history

### 3.5 功能开关

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `forum_rules.enable_private_land_trade` | bool | `False` | 是否启用私地交易 |

## 4. 输入、输出与依赖

### 4.1 输入

| 数据 | 来源 | 说明 |
|------|------|------|
| 存活人物列表 | `GameState.get_living_members()` | 自动交易选择 |
| 贵族/骑士列表 | 按 ClassTier 过滤 | 自动交易选择 |
| 私地数量 | `Figure.land_private` | 判断是否可交易 |
| 买方财富 | `Figure.wealth` | 判断能否支付 |
| 交易记录 | `_forum_pending["land_trades"]` | 手动交易暂存 |
| 卖方/买方ID | 玩家输入 / AI 决策 | 指定交易参与者 |

### 4.2 输出

| 输出 | 目标 | 说明 |
|------|------|------|
| 交易结算信息 | 控制台 | 显示交易结果 |
| 派系总土地更新 | `Faction._total_land` | 交易后更新 |
| 人物影响力更新 | `Figure.influence` | 交易后重新计算 |
| 交易历史 | `seller.land_trade_history` | 卖家记录 |

### 4.3 依赖

| 依赖 | 说明 |
|------|------|
| `LandTradeDecider` (ABC) | 自动交易决策器抽象接口 |
| `AutoLandTradeDecider` | 自动交易决策器实现 |
| `LandTradingService` | 交易执行服务 |
| `Figure.sell_land()` | 卖家土地/财富变更 |
| `Figure.buy_land()` | 买家财富/土地变更 |
| `Figure.update_influence()` | 重新计算影响力 |
| `Faction.update_total_land()` | 更新派系总土地 |
| `forum_api.transact_land()` | 交易记录 API |
| `forum_api.resolve_land_trades()` | 交易结算 API |

## 5. 状态与边界

### 5.1 交易有效条件

- 卖家和买家都必须存活
- 卖家必须有足够私地（`land_private >= amount`）
- 买家必须有足够财富（`wealth >= amount * price`）
- `amount > 0`，`price > 0`
- （手动模式）卖家和买家都必须在当前玩家派系中
- （手动模式）功能开关 `enable_private_land_trade` 必须为 True

### 5.2 无效场景

| 场景 | 处理 |
|------|------|
| 无存活人物 | 返回 None，不交易 |
| 无贵族或无骑士 | 返回 None，不交易 |
| 卖家无私地 | 返回 None，不交易 |
| 土地数量 ≤ 0 | API 返回错误 |
| 卖方/买方已死亡 | API 返回错误，交易失败 |
| 同一人物 | 返回错误 "Cannot trade with yourself" |
| 自动模式无私地交易流程 | 功能开关关闭则跳过步骤4直接完成 |

### 5.3 回滚机制

如果 `buyer.buy_land()` 失败（财富不足），系统自动回滚卖家：
- 调用 `seller.buy_land(amount, price_per_unit)` 将土地还给卖家
- 调用时出现异常也记录日志但不对游戏状态造成持久损坏

### 5.4 交易与派系关系

- 当前实现中同一派系内交易享受 -0.20 价格折扣
- 派系关系 API（`_get_faction_relation`）目前始终返回 "neutral"
- 交易后双方所属派系的 `_total_land` 分别重新计算

## 6. 验收标准（编码已验证）

| # | 测试场景 | 期望结果 |
|---|----------|----------|
| 1 | 有贵族和骑士，卖家有地 | 选择卖家和买家，返回 (seller_id, buyer_id, amount) |
| 2 | 无私地交易功能开关关闭 | 跳过 Step 4 |
| 3 | 卖家无私地 | 返回 None |
| 4 | 无贵族或骑士 | 返回 None |
| 5 | 无存活人物 | 返回 None |
| 6 | 手动交易卖方土地不足 | API 返回错误 |
| 7 | 手动交易买方财富不足 | API 返回错误 |
| 8 | 成功交易后更新派系总土地 | faction.update_total_land() 被调用 |

## 7. 历史演化与证据

- 历史审计入口：HF-043（自动土地交易）
- 历史名称：私人土地交易自动化
- 首次实现版本：MVP 0.5
- 演化：从 `LandTradingService`（MVP 0.4.4）基础上扩展自动决策器。MVP 0.7 扩展了手动交易交互（UI_03-4 交易市场环节）和 `forum_api.transact_land()` 功能。

## 8. 技术架构映射

- [Technical Mapping](../technical-mappings/MVP0.5-11_私人土地交易自动化.md)

## 9. 版本日志

| 版本 | 日期 | 修改人 | 修改说明 |
|------|------|--------|---------|
| v1.0 | 2026-07-12 | Document Officer Sub-Agent E | 初版创建 |

> **维护规则：** 本文件为活文档，每次修改规格说明正文或技术映射时，必须在版本日志中追加新条目。版本号递增规则：大功能修改升主版本（v1→v2），小修小改升次版本（v1.0→v1.1）。
