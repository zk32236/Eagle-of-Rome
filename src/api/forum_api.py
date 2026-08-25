# src/api/forum_api.py
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from src.api import api_response
from src.core.game_state import GameState
from src.core.i18n import i18n
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import WarStatus
from src.core.service.land_trading_service import LandTradingService
from src.core.entities.figure import ClassTier, Figure
from src.core.systems.figure_generation_system import generate_figures as system_generate_figures, generate_market_figures


NEXT_PHASE_ID = "population"


def get_forum_view(state: GameState, viewer_player_id: str) -> dict:
    """Return the read-only GUI DTO for the forum stage."""
    try:
        viewer = state.get_player(viewer_player_id)
        if not viewer:
            return api_response(False, "Viewer player not found")

        current_player = state.get_current_player()
        current_phase_id = _current_phase_id(state)
        result = state.get_phase_result("forum")
        result_data = result.get("data", {}) if isinstance(result, dict) else {}
        pending = state.get_forum_pending()
        war_system = state.get_war_system()
        has_market_actions = any(
            pending.get(key)
            for key in ("market_opened", "recruitment_bids", "contract_bids", "land_purchases", "triumph_votes")
        )

        if state.is_phase_executed("forum") or result:
            current_step = "resolution"
        elif has_market_actions:
            current_step = "market"
        else:
            current_step = "retirement"

        data = {
            "phase_id": "forum",
            "current_phase_id": current_phase_id,
            "current_player_id": current_player.player_id if current_player else "",
            "viewer_player_id": viewer_player_id,
            "viewer_faction_id": viewer.faction_id,
            "current_step": current_step,
            "my_figures": _my_figure_rows(state, viewer.faction_id),
            "available_figures": _available_figure_rows(state),
            "pending_contracts": _pending_contract_rows(state),
            "land_sale_quota": int(getattr(state, "pending_land_sale_quota", 0) or 0),
            # WP-E F5（E-06）：历史事实载体 + 权威价格展示上下文 + viewer 作用域 pending + 结构化分配
            "land_sale_total": int(getattr(state, "turn_land_sale_total", 0) or 0),
            "land_price_per_unit": int(state.get_economic_rule("land_price_per_unit", 10)),
            "viewer_land_requests": [
                {"figure_id": fig_id, "requested_amount": amount}
                for fig_id, amount in pending.get("land_purchases", [])
                if state.get_member(fig_id) is not None
                and state.get_member(fig_id).faction_id == viewer.faction_id
            ],
            "viewer_contract_bids": _viewer_contract_bid_rows(
                pending.get("contract_bids", []), viewer.faction_id
            ),
            "land_allocation": result_data.get("land_allocation", [])
            if isinstance(result_data, dict)
            else [],
            "triumph_wars": _triumph_war_rows(state),
            "war_threats": _war_threat_rows(state),
            # WP-E F7（E-G7-14P/06P）：war_events 保留载体 + has_active_war（权威访问器）
            "war_events": state.get_forum_war_events(),
            "has_active_war": bool(war_system.get_active_wars()) if war_system else False,
            "pending_actions": {
                "retirements": len(pending.get("retirements", [])),
                "recruitment_bids": len(pending.get("recruitment_bids", [])),
                "contract_bids": len(pending.get("contract_bids", [])),
                "land_purchases": len(pending.get("land_purchases", [])),
                "triumph_votes": len(pending.get("triumph_votes", [])),
            },
            "can_execute": (
                current_phase_id == "forum"
                and state.is_current_player(viewer_player_id)
                and not state.is_phase_executed("forum")
            ),
            "can_advance": (
                current_phase_id == "forum"
                and state.is_current_player(viewer_player_id)
                and bool(result)
                and not state.is_phase_executed("forum")
            ),
            "step1_complete": current_step in {"market", "resolution"},
            "step2_complete": current_step == "resolution",
            "resolved": bool(result),
            "resolution_results": result_data.get("results", []) if isinstance(result_data, dict) else [],
            "next_phase_id": NEXT_PHASE_ID,
        }
        return api_response(True, "Forum view", data)
    except Exception as e:
        logging.exception("Forum view failed")
        return api_response(False, f"Forum view failed: {e}", errors=[str(e)])


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



def initialize_forum_turn(state: GameState) -> dict:
    """Canonical forum turn initialization. Exactly-once per turn.

    Side effects: war trigger/escalate (015), fleet completion, figures(+hero, 009),
    contracts (014), province unrest. Shared by GUI / CLI / AI.
    """
    pending = state.get_forum_pending()
    if pending.get("forum_initialized"):
        return api_response(True, "Forum already initialized", data={})   # exactly-once guard

    # ODR-04 方案 B：入口校验 hero 标记回合归属（不匹配 → 丢弃，不消费）
    if state.hero_spawned_this_turn or state.hero_to_spawn is not None:
        _reconcile_stale_hero_markers(state)

    # ① war trigger + escalate（015）—— 尊重 enable_threats gate（war_system L736-737）
    war_events: List[str] = []
    ws = state.get_war_system()
    if ws:
        war_events = ws.check_triggers(state.turn.year, verbose=False) + ws.escalate_threats()

    # WP-E F7（E-G7-14P/06P）：war_events 写入保留载体（open_market 丢弃问题收敛——
    # 权威字符串直读，生命周期归 WP-G，零裁决零修改）
    state.set_forum_war_events(war_events)

    # ④ fleet construction completion（副产物）
    completed_fleets: List[int] = []
    if state.naval_system:
        completed_fleets = state.naval_system.process_fleet_construction(state.turn.turn_number)

    # ③ figures（含 hero，009）—— 走 forum_api.generate_figures wrapper（含 is_hero 标记行）
    figures_result = generate_figures(state)

    # ② contracts（014，含 fleet construction/replacement 合同）
    contracts_result = generate_contracts(state)

    # ⑤ 民变年度更新（副产物）
    unrest_result = check_province_unrest(state)

    # 防御性 hero 残留清理（009 跨回合陈旧触发兜底，ODR-04 后保留）
    state.hero_spawned_this_turn = False
    state.hero_to_spawn = None

    state.add_forum_action("forum_initialized", True)                     # 全部副作用成功后才置位
    return api_response(True, "Forum initialized", data={
        "war_events": war_events,
        "completed_fleets": completed_fleets,
        "figures": figures_result.get("data", {}).get("figures", []),
        "contracts": contracts_result.get("data", {}).get("contracts", []),
        "unrest": unrest_result.get("data", {}),
    })


def _reconcile_stale_hero_markers(state: GameState) -> None:
    """ODR-04 方案 B：hero_to_spawn 带 spawn_turn 戳且等于当前回合 → 保留消费；
    戳缺失（pre-fix 存档）或非当前回合 → 丢弃残留标记，不生成英雄。"""
    hero_info = state.hero_to_spawn
    if hero_info is not None:
        if hero_info.get("spawn_turn") == state.turn.turn_number:
            return                      # 本回合标记，正常消费路径（generate_figures 内）
        state.log_event(
            "initialize_forum_turn: stale hero marker discarded (turn mismatch)",
            level=logging.INFO,
            extra={"marker_turn": hero_info.get("spawn_turn"), "current_turn": state.turn.turn_number},
        )
    state.hero_to_spawn = None
    state.hero_spawned_this_turn = False


def open_market(state: GameState, player_id: str) -> dict:
    """Open the forum market and generate the turn's new figures once."""
    ok, resp = _check_player_permission(state, player_id)
    if not ok:
        return resp

    pending = state.get_forum_pending()
    if pending.get("market_opened"):
        return api_response(True, "Forum market already open", data={"generated_figures": []})

    init_result = initialize_forum_turn(state)                       # ← 切换 canonical init（AU-2，ODR-05）
    figure_ids = {fd["id"] for fd in init_result.get("data", {}).get("figures", [])}
    generated = [f for f in state.curia.get_all_available() if f.id in figure_ids]
    state.add_forum_action("market_opened", True)                    # L148 保留（market 步态标记）
    if generated:
        state.log_event(
            f"Forum market opened: generated {len(generated)} figures",
            level=logging.INFO,
            extra={"figure_ids": [fig.id for fig in generated]},
        )
    return api_response(
        True,
        "Forum market opened",
        data={"generated_figures": [_available_figure_row(fig) for fig in generated]},   # 行形不变
    )


def _generate_market_figures(state: GameState) -> List[Figure]:
    """
    Generate figures for the forum market.

    Delegates to figure_generation_system.generate_market_figures()
    to maintain a single source of truth for figure creation.
    """
    return generate_market_figures(state)


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

    # WP-E F7（E-G7-07）：恰一次防重——同 (contract_id, figure_id) 已出价 → 显式拒绝
    pending = state.get_forum_pending()
    for bid in pending.get("contract_bids", []):
        if len(bid) >= 2 and bid[0] == contract_id and bid[1] == figure_id:
            return api_response(False, "该人物已对本合同出价")

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

    # WP-E F5（E-09/R-08）：per-figure 防重——同人物本回合已提交 → 显式拒绝
    # （不采用静默替换，避免隐含语义；E-10 失败面显式反馈）
    pending = state.get_forum_pending()
    for fig_id, _ in pending.get("land_purchases", []):
        if fig_id == figure_id:
            return api_response(False, "该人物本回合已提交公地认购请求")

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
    execute_land_acts(state)          # ← 新增：canonical land-acts hook（幂等，resolution-time）
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

    # 3. 公地认购结算（WP-E F5：无条件配额处置 + 结构化 land_allocation）
    land_allocation: List[Dict[str, Any]] = []
    quota = state.pending_land_sale_quota
    if pending["land_purchases"]:
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
                    land_allocation.append({
                        "figure_id": fig_id,
                        "name": figure.get_formal_name() if figure else str(fig_id),
                        "requested_amount": amount,
                        "allocated_amount": 0,
                        "cost": 0,
                        "status": "skipped_dead",
                    })
            purchases_with_influence.sort(key=lambda x: x[2], reverse=True)

            land_price = state.get_economic_rule("land_price_per_unit", 10)
            remaining_quota = quota
            for figure, amount, _ in purchases_with_influence:
                if remaining_quota <= 0:
                    break
                max_buy_by_wealth = figure.wealth // land_price
                if max_buy_by_wealth <= 0:
                    results.append(f"⚠️ {figure.get_formal_name()} 资金不足，无法认购")
                    land_allocation.append({
                        "figure_id": figure.id,
                        "name": figure.get_formal_name(),
                        "requested_amount": amount,
                        "allocated_amount": 0,
                        "cost": 0,
                        "status": "insufficient_wealth",
                    })
                    continue

                actual_buy = min(amount, remaining_quota, max_buy_by_wealth)
                if actual_buy <= 0:
                    continue

                cost = actual_buy * land_price
                if not figure.buy_land(actual_buy, land_price):
                    results.append(f"⚠️ {figure.get_formal_name()} 资金不足，无法认购")
                    land_allocation.append({
                        "figure_id": figure.id,
                        "name": figure.get_formal_name(),
                        "requested_amount": amount,
                        "allocated_amount": 0,
                        "cost": 0,
                        "status": "insufficient_wealth",
                    })
                    continue
                figure.update_influence()
                state.add_treasury(cost)
                state.add_national_public_land(-actual_buy)

                remaining_quota -= actual_buy
                status = "allocated" if actual_buy >= amount else "partial"
                land_allocation.append({
                    "figure_id": figure.id,
                    "name": figure.get_formal_name(),
                    "requested_amount": amount,
                    "allocated_amount": actual_buy,
                    "cost": cost,
                    "status": status,
                })
                results.append(f"✅ {figure.get_formal_name()} 认购 {actual_buy} C 公地，花费 {cost} 塔兰特")

            if remaining_quota > 0:
                results.append(f"📭 剩余未售公地配额 {remaining_quota} C 作废")
            state.clear_pending_land_sale_quota()
    elif quota > 0:
        # WP-E F5/G-14 收敛：无认购但配额>0 → 无条件「未售作废」+ 清空（与 :645 既有语义一致，
        # 非新产品语义；消除跨年残留）
        results.append(f"📭 本回合公地未售，配额 {quota} C 作废")
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
    data = {"results": results, "land_allocation": land_allocation}
    state.record_phase_result("forum", {"success": True, "message": message, "data": data})
    return api_response(True, message, data=data)


def advance_forum_phase(state: GameState, viewer_player_id: str) -> dict:
    """Confirm forum resolution and advance to the population stage."""
    viewer = state.get_player(viewer_player_id)
    if not viewer:
        return api_response(False, "Viewer player not found")

    if state.is_phase_executed("forum"):
        return api_response(False, "Forum phase already executed")

    current_phase_id = _current_phase_id(state)
    if current_phase_id != "forum":
        return api_response(False, f"Current phase is {current_phase_id}, not forum")

    if not state.is_current_player(viewer_player_id):
        return api_response(False, "Current viewer is not the active player")

    result = state.get_phase_result("forum")
    if not result:
        return api_response(False, "Forum phase has not been resolved")

    state.mark_phase_executed("forum")
    return api_response(True, "Forum phase advanced", {
        "phase_executed": True,
        "next_phase_id": NEXT_PHASE_ID,
        "result": result,
    })


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


def _current_phase_id(state: GameState) -> str:
    for phase_id in ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]:
        if not state.is_phase_executed(phase_id):
            return phase_id
    return "resolution"


def _tier_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _tier_label(value: Any) -> str:
    labels = {
        "nobile": "贵族",
        "eques": "骑士",
        "plebeian": "平民",
    }
    return labels.get(_tier_value(value), _tier_value(value))


def _figure_name(figure: Any) -> str:
    if hasattr(figure, "get_formal_name"):
        return figure.get_formal_name()
    return getattr(figure, "name", f"Figure {getattr(figure, 'id', '')}")


def _my_figure_rows(state: GameState, faction_id: Optional[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not faction_id:
        return rows
    for figure in state.get_living_members():
        if figure.faction_id != faction_id:
            continue
        rows.append({
            "id": figure.id,
            "name": _figure_name(figure),
            "faction_id": figure.faction_id,
            "influence": figure.influence,
            "martial": getattr(figure, "martial", 0),
            "intellect": getattr(figure, "intellect", 0),
            "charisma": getattr(figure, "charisma", 0),
            "zeal": getattr(figure, "zeal", 0),
            "wealth": getattr(figure, "wealth", 0),
            "class_tier": _tier_value(figure.class_tier),
            "class_label": _tier_label(figure.class_tier),
            "is_leader": bool(getattr(figure, "is_faction_leader", False)),
            "has_active_contract": bool(getattr(figure, "has_active_contract", False)),
            "can_retire": (
                not getattr(figure, "is_faction_leader", False)
                and not getattr(figure, "has_active_contract", False)
            ),
            "can_bid": _tier_value(figure.class_tier) == "eques",
            "can_buy_land": getattr(figure, "wealth", 0) > 0,
        })
    return rows


def _available_figure_row(figure: Figure) -> Dict[str, Any]:
    return {
        "id": figure.id,
        "name": _figure_name(figure),
        "martial": getattr(figure, "martial", 0),
        "intellect": getattr(figure, "intellect", 0),
        "charisma": getattr(figure, "charisma", 0),
        "zeal": getattr(figure, "zeal", 0),
        "influence": getattr(figure, "influence", 0),
        "wealth": getattr(figure, "wealth", 0),
        "class_tier": _tier_value(figure.class_tier),
        "class_label": _tier_label(figure.class_tier),
        "cost": max(10, getattr(figure, "influence", 0)),
    }


def _available_figure_rows(state: GameState) -> List[Dict[str, Any]]:
    return [_available_figure_row(figure) for figure in state.curia.get_all_available()]


def _viewer_contract_bid_rows(bids: List[Any], faction_id: Optional[str]) -> List[Dict[str, Any]]:
    """Normalize legacy 4/5/7 tuple bids into a viewer-scoped read model."""
    rows: List[Dict[str, Any]] = []
    for bid in bids:
        if not isinstance(bid, (list, tuple)) or len(bid) not in {4, 5, 7}:
            continue
        contract_id, figure_id, bid_faction_id, amount = bid[:4]
        if bid_faction_id != faction_id:
            continue
        profit_rate = bid[4] if len(bid) >= 5 else None
        rows.append({
            "contract_id": contract_id,
            "figure_id": figure_id,
            "amount": amount,
            "profit_rate": profit_rate,
            "status": "pending",
        })
    return rows


def _pending_contract_rows(state: GameState) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for contract in state.get_all_contracts():
        if contract.status not in {ContractStatus.PENDING, ContractStatus.BUDGETED}:
            continue
        is_budgeted = contract.status == ContractStatus.BUDGETED
        rows.append({
            "id": contract.id,
            "name": contract.name,
            "type": contract.contract_type.value if hasattr(contract.contract_type, "value") else str(contract.contract_type),
            "type_label": "包税" if contract.contract_type == ContractType.TAX_FARMING else "工程",
            "base_cost": contract.base_cost,
            "expected_profit": getattr(contract, "expected_profit", 0),
            "province_id": str(getattr(contract, "province_id", "")),
            "status": contract.status.value if hasattr(contract.status, "value") else str(contract.status),
            "status_label": "待广场竞标" if is_budgeted else "待元老院预算表决",
            "can_bid": is_budgeted,
        })
    return rows


def _war_threat_rows(state: GameState) -> List[Dict[str, Any]]:
    """016: read-only war-threat rows for the forum DTO.

    Shares war identity with the Senate view (war_system.get_threat_wars(),
    war.id) and mirrors political_system.build_initial_info's minimal field set
    {war_id/name/threat_level/naval_required}. Enhancement fields are read
    directly from the War entity (no threat computation/rule duplication).
    """
    ws = state.get_war_system()
    if not ws:
        return []
    return [
        {
            "war_id": str(war.id),
            "name": war.name,
            "threat_level": war.threat_level,
            "naval_required": bool(war.naval_required),
            "start_year": getattr(war, "start_year", None),
            "escalate_rate": getattr(war, "escalate_rate", None),
            "auto_escalate": bool(getattr(war, "auto_escalate", False)),
        }
        for war in ws.get_threat_wars()
    ]


def _triumph_war_rows(state: GameState) -> List[Dict[str, Any]]:
    war_system = state.get_war_system()
    if not war_system:
        return []
    rows: List[Dict[str, Any]] = []
    for war in war_system.get_resolved_wars():
        if war.status != WarStatus.RESOLVED or war.soldier_share <= 0 or war.triumph_commander_id is None:
            continue
        commander = state.get_member(war.triumph_commander_id)
        rows.append({
            "war_id": str(war.id),
            "name": war.name,
            "commander_id": war.triumph_commander_id,
            "commander_name": _figure_name(commander) if commander else "未知指挥官",
            "soldier_share": war.soldier_share,
        })
    return rows


# =====================================================================
# Wave-01 Forum Init: New Public API — Figure + Contract Generation
# =====================================================================


def generate_figures(state: GameState) -> dict:
    """
    Public API: generate all new figures for the forum initialization phase.

    Delegates to: figure_generation_system.generate_figures(state)

    Input:
        state: GameState — current game state

    Output:
        dict — api_response(True, ..., data={
            "figures": [figure_data...]
        })
    """
    try:
        figures = system_generate_figures(state)
        figure_list = []
        for fig in figures:
            figure_data = {
                "id": fig.id,
                "name": fig.get_formal_name(),
                "class_tier": fig.class_tier.value if hasattr(fig.class_tier, "value") else str(fig.class_tier),
                "martial": getattr(fig, "martial", 0),
                "intelligence": getattr(fig, "intelligence", 0),
                "charisma": getattr(fig, "charisma", 0),
                "zeal": getattr(fig, "zeal", 0),
                "age": getattr(fig, "age", 0),
                "is_hero": False,
                "hero_type": None,
            }
            figure_list.append(figure_data)

        # Detect hero: figure count exceeds configured new_figures_count
        # or hero_spawned_this_turn was True before generation
        forum_rules = state.config.get("forum_rules", {})
        normal_count = int(forum_rules.get("new_figures_count", 3) or 3)
        if len(figure_list) > normal_count:
            # Mark the extra figures (heroes) that exceed the normal count
            for i in range(normal_count, len(figure_list)):
                figure_list[i]["is_hero"] = True
                figure_list[i]["hero_type"] = (
                    "historical"
                    if len(state.spawned_hero_ids) > 0
                    else "random"
                )

        hero_count = sum(1 for fd in figure_list if fd["is_hero"])
        state.log_event(
            "forum_api.generate_figures: completed",
            level=logging.DEBUG,
            extra={"total_figures": len(figures), "hero_count": hero_count},
        )
        return api_response(True, "Figures generated", data={"figures": figure_list})
    except Exception as e:
        state.log_event(
            f"forum_api.generate_figures failed: {e}",
            level=logging.ERROR,
            extra={"error": str(e)},
        )
        return api_response(False, f"Figure generation failed: {e}")


def generate_contracts(state: GameState) -> dict:
    """
    Public API: generate all new/renewal contracts for the forum initialization phase.

    Logic (lifted verbatim from CLI phase_forum._generate_contracts()):
        1. Renew tax contracts (remaining_years == 1, province conquered)
        2. Renew works contracts (warranty_remaining == 1, province conquered)
        3. New tax contracts (conquered non-Italy provinces, no existing active/pending/budgeted)
        4. New works contracts (all conquered provinces including Italy, no existing non-expired/completed)
        5. Delegate fleet construction to naval_system.generate_construction_contracts()
        6. Delegate fleet replacement to naval_system.generate_replacement_contracts()

    Input:
        state: GameState — current game state

    Output:
        dict — api_response(True, ..., data={"contracts": [contract_data...]})
    """
    contracts = []
    config = state.config
    land_price = config.get("economic_rules.land_price_per_unit", 10)
    private_income_rate = config.get("economic_rules.private_land_income_rate", 0.05)
    province_tax_rate = config.get("economic_rules.province_tax_rate", 0.1)
    auction_ratio = config.get("economic_rules.tax_auction_ratio", 0.8)
    infra_rate = config.get("economic_rules.infrastructure_cost_rate", 0.001)
    budget_margin = config.get("economic_rules.project_budget_margin", 0.2)
    tax_duration = config.get("economic_rules.tax_contract_duration", 5)
    works_duration = config.get("economic_rules.works_contract_duration", 3)

    try:
        # ---------- 1. Renewal contracts (conquered provinces only) ----------
        for contract in list(state.contracts):
            # Tax contract renewal (remaining_years == 1)
            if contract.contract_type == ContractType.TAX_FARMING and contract.status == ContractStatus.ACTIVE:
                if contract.remaining_years == 1:
                    province = state.get_province(contract.province_id)
                    if not province or not province.conquered:
                        continue
                    existing = any(
                        c for c in state.contracts
                        if c.province_id == contract.province_id
                        and c.contract_type == ContractType.TAX_FARMING
                        and c.status == ContractStatus.PENDING
                    )
                    if not existing and province.land_public > 0:
                        land_value = province.land_public * land_price
                        base_income = int(land_value * private_income_rate)
                        base_tax = int(base_income * province_tax_rate)
                        base_cost = int(base_tax * auction_ratio)

                        new_contract = state.create_contract(
                            ContractType.TAX_FARMING,
                            province.province_id,
                            base_cost,
                            state.turn.turn_number,
                        )
                        year = state.turn.year
                        year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                        new_contract.name = f"{province.name}包税权 ({year_display})"
                        new_contract.expected_profit = base_tax - base_cost
                        new_contract.duration_years = tax_duration
                        contracts.append(new_contract)
                        state.log_event(
                            f"forum_api: tax contract renewal: {province.name}, contract_id={new_contract.id}",
                            level=logging.DEBUG,
                            extra={
                                "contract_id": new_contract.id,
                                "province_id": province.province_id,
                                "base_cost": base_cost,
                            },
                        )

            # Works contract renewal (warranty_remaining == 1)
            elif contract.contract_type == ContractType.PUBLIC_WORKS and contract.status == ContractStatus.COMPLETED:
                if contract.warranty_remaining == 1:
                    province = state.get_province(contract.province_id)
                    if not province or not province.conquered:
                        continue
                    existing = any(
                        c for c in state.contracts
                        if c.province_id == contract.province_id
                        and c.contract_type == ContractType.PUBLIC_WORKS
                        and c.status == ContractStatus.PENDING
                    )
                    if not existing and province.land_public > 0:
                        land_value = province.land_public * land_price
                        infra_cost = int(land_value * infra_rate)
                        budget = int(infra_cost * (1 + budget_margin))

                        year = state.turn.year
                        year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                        new_contract = state.create_contract(
                            ContractType.PUBLIC_WORKS,
                            province.province_id,
                            budget,
                            state.turn.turn_number,
                        )
                        new_contract.name = f"{province.name}工程 ({year_display})"
                        new_contract._original_budget = budget
                        new_contract.duration_years = works_duration
                        contracts.append(new_contract)
                        state.log_event(
                            f"forum_api: works contract renewal: {province.name}, contract_id={new_contract.id}",
                            level=logging.DEBUG,
                            extra={
                                "contract_id": new_contract.id,
                                "province_id": province.province_id,
                                "budget": budget,
                            },
                        )

        # ---------- 2. New contracts ----------
        for province in state.get_all_provinces():
            # Tax contract: conquered non-Italy provinces only
            if province.province_id != 0 and province.conquered and province.land_public > 0:
                has_tax_active = any(
                    c for c in state.contracts
                    if c.province_id == province.province_id
                    and c.contract_type == ContractType.TAX_FARMING
                    and c.status in (ContractStatus.ACTIVE, ContractStatus.PENDING, ContractStatus.BUDGETED)
                )
                if not has_tax_active:
                    land_value = province.land_public * land_price
                    base_income = int(land_value * private_income_rate)
                    base_tax = int(base_income * province_tax_rate)
                    base_cost = int(base_tax * auction_ratio)

                    contract = state.create_contract(
                        ContractType.TAX_FARMING,
                        province.province_id,
                        base_cost,
                        state.turn.turn_number,
                    )
                    year = state.turn.year
                    year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                    contract.name = f"{province.name}包税权 ({year_display})"
                    contract.expected_profit = base_tax - base_cost
                    contract.duration_years = tax_duration
                    contracts.append(contract)
                    state.log_event(
                        f"forum_api: new tax contract: {province.name}, contract_id={contract.id}",
                        level=logging.DEBUG,
                        extra={
                            "contract_id": contract.id,
                            "province_id": province.province_id,
                            "base_cost": base_cost,
                        },
                    )

            # Works contract: conquered provinces or Italy
            if (province.conquered or province.province_id == 0) and province.land_public > 0:
                has_works = any(
                    c for c in state.contracts
                    if c.province_id == province.province_id
                    and c.contract_type == ContractType.PUBLIC_WORKS
                    and c.status not in (ContractStatus.EXPIRED, ContractStatus.COMPLETED)
                )
                if not has_works:
                    land_value = province.land_public * land_price
                    infra_cost = int(land_value * infra_rate)
                    budget = int(infra_cost * (1 + budget_margin))

                    year = state.turn.year
                    year_display = f"{abs(year)} BC" if year < 0 else f"{year} AD"
                    contract = state.create_contract(
                        ContractType.PUBLIC_WORKS,
                        province.province_id,
                        budget,
                        state.turn.turn_number,
                    )
                    contract.name = f"{province.name}工程 ({year_display})"
                    contract._original_budget = budget
                    contract.duration_years = works_duration
                    contracts.append(contract)
                    state.log_event(
                        f"forum_api: new works contract: {province.name}, contract_id={contract.id}",
                        level=logging.DEBUG,
                        extra={
                            "contract_id": contract.id,
                            "province_id": province.province_id,
                            "budget": budget,
                        },
                    )

        # ---------- 3. Fleet construction contracts (via naval_system) ----------
        fleet_construction_count = 0
        fleet_replacement_count = 0
        if state.naval_system:
            try:
                construction_contracts = state.naval_system.generate_construction_contracts(
                    state.turn.turn_number
                )
                fleet_construction_count = len(construction_contracts)
                contracts.extend(construction_contracts)
            except Exception as e:
                state.log_event(
                    f"forum_api: fleet construction delegation failed: {e}",
                    level=logging.WARNING,
                    extra={"error": str(e)},
                )

            try:
                replacement_contracts = state.naval_system.generate_replacement_contracts(
                    state.turn.turn_number
                )
                fleet_replacement_count = len(replacement_contracts)
                contracts.extend(replacement_contracts)
            except Exception as e:
                state.log_event(
                    f"forum_api: fleet replacement delegation failed: {e}",
                    level=logging.WARNING,
                    extra={"error": str(e)},
                )

            state.log_event(
                "forum_api: delegated fleet construction to naval_system",
                level=logging.DEBUG,
                extra={
                    "naval_system": True,
                    "construction_count": fleet_construction_count,
                    "replacement_count": fleet_replacement_count,
                },
            )

        state.log_event(
            f"forum_api.generate_contracts: completed",
            level=logging.DEBUG,
            extra={"total_contracts": len(contracts)},
        )

        # Build response data
        contract_data_list = []
        for c in contracts:
            contract_data_list.append({
                "id": c.id,
                "name": getattr(c, "name", ""),
                "contract_type": c.contract_type.value if hasattr(c.contract_type, "value") else str(c.contract_type),
                "contract_type_label": "包税" if c.contract_type == ContractType.TAX_FARMING else "工程",
                "province_id": getattr(c, "_province_id", 0),
                "base_cost": getattr(c, "base_cost", 0),
                "expected_profit": getattr(c, "expected_profit", 0),
                "duration_years": getattr(c, "duration_years", 0),
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "is_renewal": False,  # Tracked separately if needed
                "is_fleet": getattr(c, "_is_fleet_construction", False),
            })

        return api_response(True, "Contracts generated", data={"contracts": contract_data_list})

    except Exception as e:
        state.log_event(
            f"forum_api.generate_contracts failed: {e}",
            level=logging.ERROR,
            extra={"error": str(e)},
        )
        return api_response(False, f"Contract generation failed: {e}")


# =====================================================================
# Wave-02 Province & Land CLI 下沉: C-09c / C-09d
# =====================================================================


def check_province_unrest(state: GameState) -> dict:
    """
    Public API: check all provinces for civil unrest and trigger rebellions.

    Delegates to: ProvinceUnrestSystem.check_and_trigger_unrest()

    Input:
        state: GameState — current game state

    Output:
        dict — api_response(True, ..., data={
            "rebellions": [rebellion_data...],
            "province_updates": [{province_id, name, old_grievance, new_grievance, reason}]
        })
    """
    try:
        from src.core.systems.province_unrest_system import ProvinceUnrestSystem

        system = ProvinceUnrestSystem(state)
        result = system.check_and_trigger_unrest()

        rebellions = result.get("rebellions", [])
        province_updates = result.get("province_updates", [])

        rebellion_list = []
        for r in rebellions:
            province = state.get_province(r.rebellion_province_id)
            province_name = province.name if province else "未知"
            rebellion_list.append({
                "id": r.id,
                "name": r.name,
                "province_id": r.rebellion_province_id,
                "province_name": province_name,
            })

        state.log_event(
            f"check_province_unrest: {len(state.get_all_provinces())} provinces checked, "
            f"{len(rebellions)} rebellions triggered",
            level=logging.DEBUG,
            extra={
                "province_count": len(state.get_all_provinces()),
                "rebellion_count": len(rebellions),
            },
        )

        return api_response(True, "Unrest check completed", data={
            "rebellions": rebellion_list,
            "province_updates": province_updates,
        })
    except Exception as e:
        state.log_event(
            f"forum_api.check_province_unrest failed: {e}",
            level=logging.ERROR,
            extra={"error": str(e)},
        )
        return api_response(False, f"Unrest check failed: {e}")


def execute_land_acts(state: GameState) -> dict:
    """
    Public API: execute all pending land distribution acts.

    Logic (lifted verbatim from CLI phase_forum._execute_pending_land_acts()
    and _execute_land_distribution()):
        1. Retrieve pending_land_acts from game state
        2. For each 'distribution' act: calculate amount, deduct from
           national public land, add to Italy private land, reset grievance
        3. Clear pending land acts

    Input:
        state: GameState — current game state

    Output:
        dict — api_response(True, ..., data={
            "executed_acts": [{act_type, percent, amount, message}...]
        })
    """
    try:
        acts = state.get_pending_land_acts()
        if not acts:
            return api_response(True, "No pending land acts", data={"executed_acts": []})

        land_price = state.get_economic_rule("land_price_per_unit", 10)
        executed = []

        for act in acts:
            try:
                if act.get("type") == "distribution":
                    result = _execute_land_distribution(state, act, land_price)
                    executed.append(result)
                elif act.get("type") == "sale":
                    # Sale acts set quota in resolve_senate; already handled
                    executed.append({
                        "act_type": "sale",
                        "percent": act.get("percent", 0),
                        "amount": act.get("amount", 0),
                        "message": f"Sale quota set: {act.get('amount', 0)} C",
                    })
            except Exception as e:
                state.log_event(
                    f"execute_land_acts: act failed: {e}",
                    level=logging.WARNING,
                    extra={"act": act, "error": str(e)},
                )

        state.clear_pending_land_acts()

        state.log_event(
            f"execute_land_acts: completed",
            level=logging.DEBUG,
            extra={"executed_count": len(executed)},
        )

        return api_response(True, "Land acts executed", data={
            "executed_acts": executed,
        })
    except Exception as e:
        state.log_event(
            f"forum_api.execute_land_acts failed: {e}",
            level=logging.ERROR,
            extra={"error": str(e)},
        )
        return api_response(False, f"Land acts execution failed: {e}")


def _execute_land_distribution(state: GameState, act: dict, land_price: int) -> dict:
    """Internal: execute a single land distribution act."""
    national_land = state.get_national_public_land()
    percent = act.get("percent", 0)
    amount = int(national_land * percent)
    if amount <= 0:
        return {
            "act_type": "distribution",
            "percent": percent,
            "amount": 0,
            "message": "Insufficient national public land",
        }

    state.add_national_public_land(-amount)
    italy = state.get_province(0)
    if italy:
        italy.update_land_type(0, amount)
        italy.reset_turns_since_last_distribution()
        italy.set_grievance(0)

    state.log_event(
        f"Land act distribution: assigned {amount} to province 0 (Italy)",
        level=logging.DEBUG,
        extra={"act_type": "distribution", "amount": amount, "province_id": 0},
    )

    return {
        "act_type": "distribution",
        "percent": percent,
        "amount": amount,
        "message": f"Assigned {amount} C land to Italy private land",
    }
