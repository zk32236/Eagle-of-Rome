# src/api/forum_api.py
import logging
import random
from typing import List, Optional, Tuple

from src.api import api_response
from src.core.game_state import GameState
from src.core.i18n import i18n
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.war import WarStatus
from src.core.service.land_trading_service import LandTradingService
from src.core.entities.figure import ClassTier


def _check_player_permission(state: GameState, player_id: str) -> Tuple[bool, dict]:
    """检查当前玩家权限，返回 (是否通过, 错误响应)"""
    if not state.config.get("testing.bypass_player_check", False):
        if not state.is_current_player(player_id):
            return False, api_response(False, i18n.get("error_not_your_turn"))
    player = state.get_player(player_id)
    if not player:
        return False, api_response(False, i18n.get("error_no_current_player"))
    return True, api_response(True)


def retire_figure(state: GameState, player_id: str, figure_id: int) -> dict:
    """
    淘汰人物：从派系中移除，加入广场。
    权限：当前玩家，且人物属于该玩家派系。
    校验：人物不能是派系领袖、不能有活跃合同。
    """
    ok, resp = _check_player_permission(state, player_id)
    if not ok:
        return resp

    player = state.get_player(player_id)
    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))

    if figure.faction_id != player.faction_id:
        return api_response(False, i18n.get("error_figure_not_in_your_faction"))

    if figure.is_faction_leader:
        return api_response(False, i18n.get("error_cannot_retire_leader"))

    if figure.has_active_contract:
        return api_response(False, i18n.get("error_figure_has_active_contract"))

    faction = state.get_faction(figure.faction_id)
    if faction:
        faction.remove_member(figure.id)

    state.curia.add_figure(figure)
    figure.faction_id = None
    figure.is_faction_leader = False

    state.add_forum_action("retirements", figure_id)

    message = i18n.get("info_figure_retired", name=figure.get_formal_name())
    state.log_event(f"人物被淘汰: {figure.get_formal_name()}", level=logging.INFO,
                    extra={"figure_id": figure.id})
    return api_response(True, message, data={"figure_id": figure_id})


def recruit_figure(state: GameState, player_id: str, figure_id: int, amount: int) -> dict:
    """
    招募出价：记录出价，等待公示结算。
    校验：金额>0，人物在广场中，派系有空位。
    """
    ok, resp = _check_player_permission(state, player_id)
    if not ok:
        return resp

    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    figure = next((f for f in state.curia.get_all_available() if f.id == figure_id), None)
    if not figure:
        return api_response(False, i18n.get("error_figure_not_in_curia"))

    player = state.get_player(player_id)
    faction = state.get_faction(player.faction_id)
    if not faction:
        return api_response(False, i18n.get("error_faction_not_found"))

    vacancies = faction.get_vacancies(state, state.get_economic_rule("faction_member_limit", 6))
    if vacancies <= 0:
        return api_response(False, i18n.get("error_faction_full"))

    state.add_forum_action("recruitment_bids", (player.faction_id, figure_id, amount))

    message = i18n.get("info_recruit_bid_recorded", name=figure.get_formal_name(), amount=amount)
    return api_response(True, message, data={"figure_id": figure_id, "amount": amount})


def place_bid(state: GameState, player_id: str, figure_id: int, contract_id: int,
              amount: int, profit_rate: float = None) -> dict:
    """
    竞标出价：记录出价，等待公示结算。
    校验：合同状态 BUDGETED，金额>0，利润率在(0,1)，骑士身份正确。
    金额范围：包税合同金额 ≥ base_cost，工程合同金额 ≤ base_cost。
    """
    ok, resp = _check_player_permission(state, player_id)
    if not ok:
        return resp

    # 合同校验
    contract = state.get_contract(contract_id)
    if not contract:
        return api_response(False, i18n.get("contract_not_found", id=contract_id))
    if contract.status != ContractStatus.BUDGETED:
        return api_response(False, i18n.get("error_contract_not_auctionable"))
    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    # 利润率处理
    if profit_rate is None:
        profit_rate = state.get_economic_rule("default_bid_profit_rate", 0.2)
    if profit_rate <= 0 or profit_rate >= 1:
        return api_response(False, i18n.get("error_invalid_profit_rate"))

    # 骑士校验
    player = state.get_player(player_id)
    faction = state.get_faction(player.faction_id)
    if not faction:
        return api_response(False, i18n.get("error_faction_not_found"))

    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))
    if figure.faction_id != faction.id:
        return api_response(False, i18n.get("error_figure_not_in_your_faction"))
    if figure.class_tier != ClassTier.EQUES:
        return api_response(False, i18n.get("error_not_knight"))

    # 金额范围校验（不再强制等式）
    if contract.contract_type == ContractType.TAX_FARMING:
        if amount < contract.base_cost:
            return api_response(False, i18n.get("error_bid_too_low", min=contract.base_cost))
    elif contract.contract_type == ContractType.PUBLIC_WORKS:
        if amount > contract.base_cost:
            return api_response(False, i18n.get("error_bid_too_high", max=contract.base_cost))
    else:
        return api_response(False, "未知的合同类型")

    # 计算工期和质保期
    actual_construction = 0
    actual_warranty = 0

    if contract.contract_type == ContractType.TAX_FARMING:
        # 包税合同：无工期/质保期
        pass
    elif contract.contract_type == ContractType.PUBLIC_WORKS:
        is_fleet = getattr(contract, '_is_fleet_construction', False)
        if is_fleet:
            actual_construction = 1
            actual_warranty = 0
        else:
            original_budget = getattr(contract, '_original_budget', contract.base_cost)
            # 实际成本 = 金额 * (1 - 利润率)
            actual_cost = int(amount * (1 - profit_rate))
            if actual_cost <= 0:
                actual_cost = 1  # 避免除零
            cost_ratio = actual_cost / original_budget if original_budget > 0 else 1.0

            theoretical_construction = state.get_economic_rule("project_theoretical_construction", 3)
            theoretical_warranty = state.get_economic_rule("project_theoretical_warranty", 10)

            # 施工周期 = 理论周期 * (原始预算 / 实际成本)
            actual_construction = int(theoretical_construction * original_budget / actual_cost)
            actual_construction = max(1, actual_construction)

            # 质保期 = 理论质保期 * 成本比例
            actual_warranty = int(theoretical_warranty * cost_ratio)
            actual_warranty = max(0, actual_warranty)

    # 存储出价（7元组）
    state.add_forum_action(
        "contract_bids",
        (contract_id, figure_id, faction.id, amount, profit_rate, actual_construction, actual_warranty)
    )

    message = i18n.get("info_bid_recorded", contract_name=contract.name, amount=amount)
    return api_response(True, message, data={"contract_id": contract_id, "amount": amount, "profit_rate": profit_rate})

def buy_land(state: GameState, player_id: str, figure_id: int, amount: int) -> dict:
    ok, resp = _check_player_permission(state, player_id)
    if not ok:
        return resp

    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))

    player = state.get_player(player_id)
    if figure.faction_id != player.faction_id:
        return api_response(False, i18n.get("error_figure_not_in_your_faction"))

    # 新增：检查待售公地配额
    quota = state.pending_land_sale_quota
    if quota <= 0:
        return api_response(False, i18n.get("error_no_land_sale_quota"))

    # 新增：检查财富是否足够
    land_price = state.get_economic_rule("land_price_per_unit", 10)
    total_cost = amount * land_price
    if figure.wealth < total_cost:
        return api_response(False, i18n.get("error_insufficient_wealth"))

    # 记录操作，最终结算时会扣除财富和配额
    state.add_forum_action("land_purchases", (figure_id, amount))

    message = i18n.get("info_land_purchase_recorded", amount=amount)
    return api_response(True, message, data={"figure_id": figure_id, "amount": amount})


def vote_triumph(state: GameState, player_id: str, war_id: str, vote: bool) -> dict:
    ok, resp = _check_player_permission(state, player_id)
    if not ok:
        return resp

    war_system = state.get_war_system()
    if not war_system:
        return api_response(False, "战争系统不可用")

    war = war_system.get_war_by_id(war_id)
    if not war:
        return api_response(False, i18n.get("war_not_found", id=war_id))
    if war.status != WarStatus.RESOLVED or war.soldier_share <= 0 or war.triumph_commander_id is None:
        return api_response(False, i18n.get("error_not_triumph_war"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # 获取指挥官名称，用于生成友好消息
    commander = state.get_member(war.triumph_commander_id)
    commander_name = commander.get_formal_name() if commander else "未知指挥官"

    state.add_forum_action("triumph_votes", (war_id, player.faction_id, vote))

    vote_text = "支持" if vote else "反对"
    message = f"✅ 已记录对 {commander_name} 凯旋的 {vote_text} 投票"

    return api_response(True, message, data={"vote": vote})


def transact_land(state: GameState, player_id: str, seller_id: int, buyer_id: int,
                  land: int, price: int, bypass_permission: bool = False) -> dict:
    player = None
    if not bypass_permission:
        ok, resp = _check_player_permission(state, player_id)
        if not ok:
            return resp
        player = state.get_player(player_id)

    seller = state.get_member(seller_id)
    buyer = state.get_member(buyer_id)
    if not seller or not buyer:
        return api_response(False, i18n.get("figure_not_found"))
    if seller.is_dead or buyer.is_dead:
        return api_response(False, i18n.get("error_figure_dead"))
    if land <= 0 or price <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))
    if not bypass_permission and player:
        if seller.faction_id != player.faction_id or buyer.faction_id != player.faction_id:
            return api_response(False, i18n.get("error_figure_not_in_your_faction"))
    if not seller.can_sell_land(land):
        return api_response(False, i18n.get("error_insufficient_land"))

    state.add_forum_action("land_trades", (seller_id, buyer_id, land, price))

    message = i18n.get("info_land_trade_recorded", seller=seller.get_formal_name(), buyer=buyer.get_formal_name())
    return api_response(True, message, data={"seller": seller_id, "buyer": buyer_id, "land": land, "price": price})


def resolve_forum(state: GameState) -> dict:
    """
    公示结算：根据收集的操作执行实际游戏逻辑，返回汇总结果。
    此函数已在原有基础上添加统一返回格式。
    """
    pending = state.get_forum_pending()
    results = []

    # 1. 招募结算
    if pending["recruitment_bids"]:
        bids_by_figure = {}
        for faction_id, fig_id, amount in pending["recruitment_bids"]:
            bids_by_figure.setdefault(fig_id, []).append((faction_id, amount))

        for fig_id, bids in bids_by_figure.items():
            max_amount = max(b[1] for b in bids)
            top_bidders = [b[0] for b in bids if b[1] == max_amount]
            winner_faction_id = random.choice(top_bidders) if len(top_bidders) > 1 else top_bidders[0]

            figure = next((f for f in state.curia.get_all_available() if f.id == fig_id), None)
            if figure:
                state.curia.remove_figure(fig_id)
                figure.faction_id = winner_faction_id
                faction = state.get_faction(winner_faction_id)
                if faction:
                    faction.member_ids.append(fig_id)
                faction.treasury -= max_amount
                results.append(f"✅ {figure.get_formal_name()} 加入 {faction.name}，成交价 {max_amount}")
                state.log_event(f"招募成功: {figure.name} 加入 {faction.name}，价格 {max_amount}",
                                extra={"figure": fig_id, "faction": winner_faction_id, "amount": max_amount})
            else:
                results.append(f"⚠️ 人物 {fig_id} 不在广场中，招募失败")

    # 2. 合同竞标结算
    if pending["contract_bids"]:
        bids_by_contract = {}
        for bid in pending["contract_bids"]:
            if len(bid) == 4:
                contract_id, figure_id, faction_id, amount = bid
                profit_rate = None
                construction_years = 0
                warranty_years = 0
            elif len(bid) == 5:
                contract_id, figure_id, faction_id, amount, profit_rate = bid
                construction_years = 0
                warranty_years = 0
            elif len(bid) == 7:
                contract_id, figure_id, faction_id, amount, profit_rate, construction_years, warranty_years = bid
            else:
                continue
            bids_by_contract.setdefault(contract_id, []).append(
                (figure_id, faction_id, amount, profit_rate, construction_years, warranty_years)
            )

        for contract_id, bids in bids_by_contract.items():
            contract = state.get_contract(contract_id)
            if not contract:
                results.append(f"⚠️ 合同 {contract_id} 不存在")
                continue

            if contract.contract_type == ContractType.TAX_FARMING:
                # 包税：价高者得
                max_amount = max(b[2] for b in bids)
                top_bidders = [b for b in bids if b[2] == max_amount]
                winner = random.choice(top_bidders)
                winner_figure, winner_faction, amount, profit_rate, _, _ = winner

                if profit_rate is None:
                    profit_rate = state.get_economic_rule("default_bid_profit_rate", 0.2)

                contract._profit_rate = profit_rate
                contract._contract_price = amount
                contract._winning_bid = {
                    "bidder_id": winner_figure,
                    "amount": amount,
                    "tax_rate": profit_rate
                }

                base_tax_rate = state.get_economic_rule("province_tax_rate", 0.1)
                actual_tax_rate = base_tax_rate * (1 + profit_rate)
                contract._tax_rate = actual_tax_rate

                contract.mark_winner(winner_figure, state.turn.turn_number, 0)

                province = state.get_province(contract.province_id)
                if province:
                    province.bind_tax_contract(contract.id)
                figure = state.get_member(winner_figure)
                if figure:
                    figure.add_contract(contract.id)

                winner_faction_name = state.get_faction(winner_faction).name if winner_faction else "未知"
                results.append(
                    f"✅ 包税合同 {contract.name} 中标者: {figure.name} ({winner_faction_name})，出价 {amount}，税率 {actual_tax_rate * 100:.1f}% (利润率 {profit_rate * 100:.1f}%)"
                )

            else:
                # 工程：价低者得
                min_amount = min(b[2] for b in bids)
                top_bidders = [b for b in bids if b[2] == min_amount]
                winner = random.choice(top_bidders)
                winner_figure, winner_faction, amount, profit_rate, construction_years, warranty_years = winner

                contract.mark_winner(winner_figure, state.turn.turn_number, 0)
                contract.awarded_faction = winner_faction

                r = profit_rate
                original_budget = getattr(contract, '_original_budget', contract.base_cost)
                actual_cost = int(amount * (1 - r))
                cost_ratio = actual_cost / original_budget if original_budget > 0 else 1.0

                state.log_event(
                    f"工程合同中标: {contract.name}, 中标金额={amount}, 利润率={r:.4f}, 实际成本={actual_cost}, 原始预算={original_budget}, 成本比例={cost_ratio:.4f}",
                    level=logging.INFO,
                    extra={
                        "contract_id": contract.id,
                        "actual_cost": actual_cost,
                        "original_budget": original_budget,
                        "cost_ratio": cost_ratio
                    }
                )

                # 工期使用出价时计算的，质保期重新计算确保一致
                warranty_years = int(state.get_economic_rule("project_theoretical_warranty", 10) * cost_ratio)
                warranty_years = max(0, warranty_years)

                annual_income = amount // construction_years if construction_years else amount
                annual_cost = actual_cost // construction_years if construction_years else actual_cost

                contract._annual_income = annual_income
                contract._annual_cost = annual_cost
                contract.remaining_years = construction_years
                contract._construction_years = construction_years
                contract._warranty_years = warranty_years
                contract._warranty_remaining = warranty_years
                contract.base_cost = amount

                if getattr(contract, '_is_fleet_construction', False):
                    contract._actual_cost = actual_cost
                    contract._original_budget = original_budget
                    state.naval_system.on_contract_awarded(contract, winner_figure)

                figure = state.get_member(winner_figure)
                winner_faction_name = state.get_faction(winner_faction).name if winner_faction else "未知"
                results.append(
                    f"✅ 工程合同 {contract.name} 中标者: {figure.name} ({winner_faction_name})，出价 {amount}"
                )

    # 3. 公地认购结算
    if pending["land_purchases"]:
        quota = state.pending_land_sale_quota
        if quota <= 0:
            results.append("📭 本回合无可售公地配额")
        else:
            purchases = pending["land_purchases"]
            purchases_with_influence = []
            for fig_id, amount in purchases:
                figure = state.get_member(fig_id)
                if figure and not figure.is_dead:
                    purchases_with_influence.append((figure, amount, figure.influence))
                else:
                    results.append(f"⚠️ 人物 {fig_id} 不存在或已死亡，认购请求无效")
            purchases_with_influence.sort(key=lambda x: x[2], reverse=True)

            land_price = state.get_economic_rule("land_price_per_unit", 10)
            remaining_quota = quota
            for figure, amount, _ in purchases_with_influence:
                if remaining_quota <= 0:
                    break
                max_buy_by_wealth = figure.wealth // land_price
                if max_buy_by_wealth <= 0:
                    results.append(f"⚠️ {figure.get_formal_name()} 资金不足，无法认购")
                    continue

                actual_buy = min(amount, remaining_quota, max_buy_by_wealth)
                if actual_buy <= 0:
                    continue

                cost = actual_buy * land_price
                if not figure.buy_land(actual_buy, land_price):
                    results.append(f"⚠️ {figure.get_formal_name()} 资金不足，无法认购")
                    continue
                figure.update_influence()
                state.add_treasury(cost)
                state.add_national_public_land(-actual_buy)

                remaining_quota -= actual_buy
                results.append(f"✅ {figure.get_formal_name()} 认购 {actual_buy} C 公地，花费 {cost} 塔兰特")

            if remaining_quota > 0:
                results.append(f"📭 剩余未售公地配额 {remaining_quota} C 作废")
            state.clear_pending_land_sale_quota()

    # 4. 凯旋投票结算
    war_system = state.get_war_system()
    votes_by_war = {}
    if pending["triumph_votes"]:
        for war_id, faction_id, vote in pending["triumph_votes"]:
            votes_by_war.setdefault(war_id, []).append((faction_id, vote))

    if war_system:
        for war in war_system.get_resolved_wars():
            if war.soldier_share <= 0 or war.status != WarStatus.RESOLVED or war.triumph_commander_id is None:
                continue

            commander = state.get_member(war.triumph_commander_id)
            if not commander or commander.is_dead:
                war.set_soldier_share(0)
                results.append(f"⚠️ 战争 {war.name} 指挥官已死，凯旋失效")
                continue

            votes = votes_by_war.get(war.id, [])
            if not votes:
                war.set_soldier_share(0)
                results.append(f"⚠️ 战争 {war.name} 无有效投票")
                continue

            votes_for = 0
            votes_against = 0
            total_influence = 0
            for faction_id, vote in votes:
                faction = state.get_faction(faction_id)
                if faction:
                    influence = sum(m.influence for m in faction.get_members(state))
                    total_influence += influence
                    if vote:
                        votes_for += influence
                    else:
                        votes_against += influence
            if total_influence > 0:
                support_rate = votes_for / total_influence
                if support_rate > 0.5:
                    duration = state.config.get("combat_rules.triumph_veteran_duration", 5)
                    per_turn = war.soldier_share // duration
                    if per_turn > 0:
                        commander.add_temp_influence_task(per_turn, duration)
                    war.set_triumph_approved(True)
                    results.append(f"✅ 战争 {war.name} 的凯旋仪式获得批准（支持率 {support_rate:.1%}）")
                else:
                    results.append(f"❌ 战争 {war.name} 的凯旋仪式被否决（支持率 {support_rate:.1%}）")
            else:
                results.append(f"⚠️ 战争 {war.name} 无有效投票")

            war.set_soldier_share(0)

    state.clear_forum_pending()

    message = "\n".join(results) if results else i18n.get("info_no_forum_actions")
    return api_response(True, message, data={"results": results})


def resolve_land_trades(state: GameState) -> dict:
    """
    结算土地交易（仅在交易市场环节调用），返回交易结果。
    """
    pending = state.get_forum_pending()
    results = []

    if pending["land_trades"]:
        service = LandTradingService(state)
        for seller_id, buyer_id, land, price in pending["land_trades"]:
            if land > 0:
                price_per_unit = price // land
                success, msg = service.execute_trade(seller_id, buyer_id, land, price_per_unit)
                if success:
                    results.append(f"💱 {msg}")
                else:
                    results.append(f"⚠️ 土地交易失败：{msg}")
            else:
                results.append(f"⚠️ 土地数量无效")

    state.clear_forum_action("land_trades")

    message = "\n".join(results) if results else ""
    return api_response(True, message, data={"results": results})
