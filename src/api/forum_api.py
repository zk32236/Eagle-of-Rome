# src/api/forum_api.py
from src.core.game_state import GameState
from src.api import api_response
from src.core.i18n import i18n
from src.core.entities.contract import ContractType, ContractStatus
import logging


def retire_figure(state: GameState, player_id: str, figure_id: int) -> dict:
    """
    淘汰人物：从派系中移除，加入广场。
    权限：当前玩家，且人物属于该玩家派系。
    """
    if not state.is_current_player(player_id):
        return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    figure = state.get_member(figure_id)
    if not figure or figure.is_dead:
        return api_response(False, i18n.get("figure_not_found", id=figure_id))

    if figure.faction_id != player.faction_id:
        return api_response(False, i18n.get("error_figure_not_in_your_faction"))

    # 不能淘汰派系领袖
    if figure.is_faction_leader:
        return api_response(False, i18n.get("error_cannot_retire_leader"))

    # 不能淘汰有活跃合同的人物
    if figure.has_active_contract:
        return api_response(False, i18n.get("error_figure_has_active_contract"))

    # 从派系中移除
    faction = state.get_faction(figure.faction_id)
    if faction:
        faction.remove_member(figure.id)

    # 将人物加入广场
    state.curia.add_figure(figure)
    figure.faction_id = None  # 清除派系归属
    figure.is_faction_leader = False

    # 记录淘汰操作（用于公示，但已立即生效）
    state.add_forum_action("retirements", figure_id)

    message = i18n.get("info_figure_retired", name=figure.get_formal_name())
    state.log_event(f"人物被淘汰: {figure.get_formal_name()}", level=logging.INFO,
                    extra={"figure_id": figure.id})
    return api_response(True, message, data={"figure_id": figure_id})


def recruit_figure(state: GameState, player_id: str, figure_id: int, amount: int) -> dict:
    """
    招募出价：记录出价，等待公示结算。
    """
    if not state.is_current_player(player_id):
        return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    # 检查人物是否在 Curia 中
    figure = next((f for f in state.curia.get_all_available() if f.id == figure_id), None)
    if not figure:
        return api_response(False, i18n.get("error_figure_not_in_curia"))

    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    # 记录出价
    state.add_forum_action("recruitment_bids", (player.faction_id, figure_id, amount))

    message = i18n.get("info_recruit_bid_recorded", name=figure.get_formal_name(), amount=amount)
    return api_response(True, message, data={"figure_id": figure_id, "amount": amount})


def place_bid(state: GameState, player_id: str, contract_id: int, amount: int) -> dict:
    """
    合同竞标：记录出价。
    """
    if not state.is_current_player(player_id):
        return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    contract = state.get_contract(contract_id)
    if not contract:
        return api_response(False, i18n.get("contract_not_found", id=contract_id))

    if contract.status != ContractStatus.BUDGETED:
        return api_response(False, i18n.get("error_contract_not_auctionable"))

    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    state.add_forum_action("contract_bids", (contract_id, player.faction_id, amount))

    message = i18n.get("info_bid_recorded", contract_name=contract.name, amount=amount)
    return api_response(True, message, data={"contract_id": contract_id, "amount": amount})


def buy_land(state: GameState, player_id: str, amount: int) -> dict:
    """
    认购公地：记录认购。
    """
    if not state.is_current_player(player_id):
        return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    if amount <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    # 检查国库是否有足够公地（暂不检查，公示时处理）
    state.add_forum_action("land_purchases", (player.faction_id, amount))

    message = i18n.get("info_land_purchase_recorded", amount=amount)
    return api_response(True, message, data={"amount": amount})


def vote_triumph(state: GameState, player_id: str, vote: bool) -> dict:
    """
    凯旋投票：记录投票（True=支持，False=反对）。
    """
    if not state.is_current_player(player_id):
        return api_response(False, i18n.get("error_not_your_turn"))

    player = state.get_player(player_id)
    if not player:
        return api_response(False, i18n.get("error_no_current_player"))

    state.add_forum_action("triumph_votes", (player.faction_id, vote))

    message = i18n.get("info_vote_recorded", vote="支持" if vote else "反对")
    return api_response(True, message, data={"vote": vote})


def transact_land(state: GameState, player_id: str, seller_id: int, buyer_id: int, land: int, price: int) -> dict:
    """
    土地交易：记录交易。
    """
    if not state.is_current_player(player_id):
        return api_response(False, i18n.get("error_not_your_turn"))

    # 检查买卖双方人物是否存在
    seller = state.get_member(seller_id)
    buyer = state.get_member(buyer_id)
    if not seller or not buyer:
        return api_response(False, i18n.get("figure_not_found"))

    if seller.is_dead or buyer.is_dead:
        return api_response(False, i18n.get("error_figure_dead"))

    if land <= 0 or price <= 0:
        return api_response(False, i18n.get("error_invalid_amount"))

    state.add_forum_action("land_trades", (seller_id, buyer_id, land, price))

    message = i18n.get("info_land_trade_recorded", seller=seller.get_formal_name(), buyer=buyer.get_formal_name())
    return api_response(True, message, data={"seller": seller_id, "buyer": buyer_id, "land": land, "price": price})


def resolve_forum(state: GameState) -> dict:
    """
    公示结算：根据收集的操作执行实际游戏逻辑，返回汇总结果。
    """
    pending = state.get_forum_pending()
    results = []

    # 1. 招募结算
    if pending["recruitment_bids"]:
        # 按 figure_id 分组
        bids_by_figure = {}
        for faction_id, fig_id, amount in pending["recruitment_bids"]:
            bids_by_figure.setdefault(fig_id, []).append((faction_id, amount))

        for fig_id, bids in bids_by_figure.items():
            # 找出价最高者（若平局，随机选择）
            max_amount = max(b[1] for b in bids)
            top_bidders = [b[0] for b in bids if b[1] == max_amount]
            import random
            winner_faction_id = random.choice(top_bidders) if len(top_bidders) > 1 else top_bidders[0]

            # 从 Curia 中移除人物
            figure = next((f for f in state.curia.get_all_available() if f.id == fig_id), None)
            if figure:
                state.curia.remove_figure(fig_id)
                figure.faction_id = winner_faction_id
                # 加入派系成员列表
                faction = state.get_faction(winner_faction_id)
                if faction:
                    faction.member_ids.append(fig_id)
                # 扣款
                faction.treasury -= max_amount
                results.append(f"✅ {figure.get_formal_name()} 加入 {faction.name}，成交价 {max_amount}")
                state.log_event(f"招募成功: {figure.name} 加入 {faction.name}，价格 {max_amount}",
                                extra={"figure": fig_id, "faction": winner_faction_id, "amount": max_amount})
            else:
                results.append(f"⚠️ 人物 {fig_id} 不在广场中，招募失败")

    # 2. 合同竞标结算
    if pending["contract_bids"]:
        bids_by_contract = {}
        for contract_id, faction_id, amount in pending["contract_bids"]:
            bids_by_contract.setdefault(contract_id, []).append((faction_id, amount))

        for contract_id, bids in bids_by_contract.items():
            contract = state.get_contract(contract_id)
            if not contract:
                results.append(f"⚠️ 合同 {contract_id} 不存在")
                continue

            if contract.contract_type == ContractType.TAX_FARMING:
                # 包税合同：价高者得
                max_amount = max(b[1] for b in bids)
                top_bidders = [b[0] for b in bids if b[1] == max_amount]
                winner_faction = random.choice(top_bidders) if len(top_bidders) > 1 else top_bidders[0]
                # 中标处理
                contract.status = ContractStatus.ACTIVE  # 简化，实际需更多处理
                winner_faction_obj = state.get_faction(winner_faction)
                results.append(f"✅ 包税合同 {contract.name} 中标者: {winner_faction_obj.name}，出价 {max_amount}")
            else:
                # 工程合同：价低者得
                min_amount = min(b[1] for b in bids)
                top_bidders = [b[0] for b in bids if b[1] == min_amount]
                winner_faction = random.choice(top_bidders) if len(top_bidders) > 1 else top_bidders[0]
                contract.status = ContractStatus.ACTIVE
                winner_faction_obj = state.get_faction(winner_faction)
                results.append(f"✅ 工程合同 {contract.name} 中标者: {winner_faction_obj.name}，出价 {min_amount}")

    # 3. 公地认购结算
    if pending["land_purchases"]:
        # 按派系影响力排序（影响力大的优先）
        factions = list(state.factions.values())
        # 计算每个派系的影响力（使用派系总影响力）
        faction_influence = {f.id: sum(m.influence for m in f.get_members(state)) for f in factions}
        sorted_factions = sorted(factions, key=lambda f: faction_influence[f.id], reverse=True)

        land_price = state.get_economic_rule("land_price_per_unit", 10)
        total_purchased = 0
        for faction_id, amount in pending["land_purchases"]:
            # 查找派系对象
            faction = state.get_faction(faction_id)
            if not faction:
                continue
            # 检查国库是否有足够公地
            available_land = state.get_national_public_land()
            if available_land < total_purchased + amount:
                # 不足则分配剩余
                amount = available_land - total_purchased
            if amount > 0:
                cost = amount * land_price
                if faction.treasury >= cost:
                    faction.treasury -= cost
                    state.add_national_public_land(-amount)
                    total_purchased += amount
                    results.append(f"🏛️ {faction.name} 认购 {amount} C 公地，花费 {cost}")
                else:
                    results.append(f"⚠️ {faction.name} 资金不足，认购失败")
            else:
                results.append(f"⚠️ 公地不足，{faction.name} 认购失败")

    # 4. 凯旋投票结算
    if pending["triumph_votes"]:
        # 统计支持票和反对票（按派系影响力加权）
        votes_for = 0
        votes_against = 0
        total_influence = 0
        for faction_id, vote in pending["triumph_votes"]:
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
                results.append(f"✅ 凯旋仪式获得批准（支持率 {support_rate:.1%}）")
            else:
                results.append(f"❌ 凯旋仪式被否决（支持率 {support_rate:.1%}）")
        else:
            results.append("⚠️ 无有效投票")

    # 5. 土地交易结算
    if pending["land_trades"]:
        land_price = state.get_economic_rule("land_price_per_unit", 10)
        for seller_id, buyer_id, land, price in pending["land_trades"]:
            seller = state.get_member(seller_id)
            buyer = state.get_member(buyer_id)
            if not seller or not buyer:
                results.append(f"⚠️ 交易双方不存在")
                continue
            if seller.land_private < land:
                results.append(f"⚠️ {seller.get_formal_name()} 土地不足")
                continue
            if buyer.wealth < price:
                results.append(f"⚠️ {buyer.get_formal_name()} 财富不足")
                continue
            # 执行交易
            seller._land_private -= land
            buyer._land_private += land
            seller.wealth += price
            buyer.wealth -= price
            results.append(f"💱 {seller.get_formal_name()} 出售 {land} C 土地给 {buyer.get_formal_name()}，价格 {price}")

    # 清除临时数据
    state.clear_forum_pending()

    message = "\n".join(results) if results else i18n.get("info_no_forum_actions")
    return api_response(True, message, data={"results": results})