# src/ui/processors/auto_player_processor.py
import logging
import random
from typing import Optional
from src.api import forum_api
from src.core.game_state import GameState
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.war import WarStatus
from src.core.deciders.retirement_decider import RetirementDecider
from src.core.deciders.recruitment_decider import RecruitmentDecider
from src.core.deciders.bid_decider import BidDecider
from src.core.deciders.triumph_decider import TriumphDecider
from src.core.deciders.festival_decider import FestivalDecider
from src.core.deciders.vote_decider import VoteDecider



class AutoPlayerProcessor:
    def __init__(self,
                 state: GameState,
                 retirement_decider: RetirementDecider,
                 recruitment_decider: RecruitmentDecider,
                 bid_decider: BidDecider,
                 triumph_decider: TriumphDecider,
                 festival_decider: Optional[FestivalDecider] = None,
                 vote_decider: Optional[VoteDecider] = None):
        self.state = state
        self.retirement_decider = retirement_decider
        self.recruitment_decider = recruitment_decider
        self.bid_decider = bid_decider
        self.triumph_decider = triumph_decider
        self.festival_decider = festival_decider
        self.vote_decider = vote_decider

    def process_festival(self, player_id: str, faction: Faction, bypass_permission: bool = False) -> None:
        """自动举办庆典：为派系内候选人随机举办庆典"""
        if not self.festival_decider:
            self.state.log_event(
                "[WARNING] AutoPlayerProcessor: festival_decider 未设置，跳过庆典",
                level=logging.WARNING
            )
            return

        try:
            from src.api.population_api import get_candidates
            cand_result = get_candidates(self.state)
            if not cand_result["success"]:
                return
            all_candidates = []
            for office, cands in cand_result["data"].items():
                all_candidates.extend([c["id"] for c in cands])

            # 转换为 Figure 对象
            candidates = []
            for cid in all_candidates:
                fig = self.state.get_member(cid)
                if fig and not fig.is_dead and fig.faction_id == faction.id:
                    candidates.append(fig)

            decisions = self.festival_decider.decide_festivals(faction, candidates, self.state)
            for fig_id, amount in decisions.items():
                if bypass_permission:
                    # 直接操作游戏状态
                    figure = self.state.get_member(fig_id)
                    if figure and not figure.is_dead and figure.wealth >= amount:
                        figure.wealth -= amount
                        figure.popularity += amount
                        figure.update_influence()
                        self.state._population_pending["campaigns"].append((player_id, fig_id, amount))
                        self.state.log_event(
                            f"AI 庆典 (直接): 派系 {faction.name} 为人物 {fig_id} 花费 {amount}",
                            extra={"player_id": player_id, "figure_id": fig_id, "amount": amount}
                        )
                    else:
                        self.state.log_event(
                            f"AI 庆典失败 (直接): 人物 {fig_id} 财富不足或已死亡",
                            level=logging.WARNING
                        )
                else:
                    # 调用API
                    from src.api import population_api
                    result = population_api.campaign(self.state, player_id, fig_id, amount)
                    if result["success"]:
                        self.state.log_event(
                            f"AI 庆典: 派系 {faction.name} 为人物 {fig_id} 花费 {amount}",
                            extra={"player_id": player_id, "figure_id": fig_id, "amount": amount}
                        )
                    else:
                        self.state.log_event(
                            f"AI 庆典失败: {result['message']}",
                            level=logging.WARNING
                        )
        except Exception as e:
            logging.exception(f"庆典环节 AI 决策异常: {e}")

    def process_vote(self, player_id: str, faction: Faction, bypass_permission: bool = False) -> None:
        """自动投票：为每个公职决定投票对象"""
        if not self.vote_decider:
            self.state.log_event(
                "[WARNING] AutoPlayerProcessor: vote_decider 未设置，跳过投票",
                level=logging.WARNING
            )
            return

        try:
            from src.api.population_api import get_candidates, vote
            cand_result = get_candidates(self.state)
            if not cand_result["success"]:
                return

            for office, cands in cand_result["data"].items():
                if not cands:
                    continue
                candidate_figures = []
                for c in cands:
                    fig = self.state.get_member(c["id"])
                    if fig:
                        candidate_figures.append(fig)
                chosen_id = self.vote_decider.decide_vote(office, candidate_figures, faction, self.state)
                if chosen_id is not None:
                    if bypass_permission:
                        # 直接记录投票
                        # 移除该玩家对该公职的旧投票（如有）
                        votes = self.state._population_pending["votes"]
                        new_votes = []
                        for v in votes:
                            if v[0] == player_id and v[1] == office:
                                continue
                            new_votes.append(v)
                        new_votes.append((player_id, office, chosen_id))
                        self.state._population_pending["votes"] = new_votes
                        self.state.log_event(
                            f"AI 投票 (直接): 派系 {faction.name} 为 {office} 投给 {chosen_id}",
                            extra={"player_id": player_id, "office": office, "figure_id": chosen_id}
                        )
                    else:
                        result = vote(self.state, player_id, office, chosen_id)
                        if result["success"]:
                            self.state.log_event(
                                f"AI 投票: 派系 {faction.name} 为 {office} 投给 {chosen_id}",
                                extra={"player_id": player_id, "office": office, "figure_id": chosen_id}
                            )
                        else:
                            self.state.log_event(
                                f"AI 投票失败: {result['message']}",
                                level=logging.WARNING
                            )
        except Exception as e:
            logging.exception(f"投票环节 AI 决策异常: {e}")

    def process_retirement(self, player_id: str, faction: Faction) -> bool:
        try:
            fig_id = self.retirement_decider.decide_whom_to_retire(faction)
            if fig_id is None:
                return False

            # 使用 forum_api.retire_figure 处理淘汰
            result = forum_api.retire_figure(self.state, player_id, fig_id)
            if result["success"]:
                # 如果成功，API 内部已记录操作，这里只需输出提示
                figure = self.state.get_member(fig_id)
                if figure:
                    print(f"   🤖 AI {faction.name} 淘汰了 {figure.get_formal_name()}", flush=True)
                return True
            else:
                self.state.log_event(
                    f"AI 淘汰失败: {result['message']}",
                    level=logging.WARNING,
                    extra={"player_id": player_id, "figure_id": fig_id}
                )
                return False
        except Exception as e:
            logging.exception(f"裁员环节 AI 决策异常: {e}")
            return False

    def process_market(self, player_id: str, faction: Faction) -> None:
        """执行市场环节决策（招募、竞标、凯旋投票）。"""
        try:
            # 1. 招募
            available_figures = self.state.curia.get_all_available()
            vacancies = faction.get_vacancies(
                self.state,
                self.state.get_economic_rule("faction_member_limit", 6)
            )
            bids = self.recruitment_decider.decide_bids(
                faction, available_figures, vacancies, self.state
            )
            for fig_id, amount in bids.items():
                forum_api.recruit_figure(self.state, player_id, fig_id, amount)

            # 2. 合同竞标
            budgeted_contracts = [
                c for c in self.state.contracts
                if c.status == ContractStatus.BUDGETED
            ]
            for contract in budgeted_contracts:
                knights = [
                    m for m in faction.get_members(self.state)
                    if m.class_tier == ClassTier.EQUES and not m.is_dead
                ]
                if not knights:
                    continue

                if contract.contract_type == ContractType.TAX_FARMING:
                    result = self.bid_decider.decide_tax_bid(contract, knights, self.state)
                    if result:
                        knight, amount, profit_rate = result
                        forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, profit_rate)

                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    if getattr(contract, '_is_fleet_construction', False):
                        result = self.bid_decider.decide_fleet_bid(contract, knights, self.state)
                        if result:
                            knight, amount, profit_rate = result
                            forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, profit_rate)
                    else:
                        result = self.bid_decider.decide_works_bid(contract, knights, self.state)
                        if result:
                            knight, amount, profit_rate, construction, warranty = result
                            # place_bid 会重新计算工期/质保期，但为了保持一致性，还是传入利润率
                            forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, profit_rate)

            # 3. 凯旋投票
            war_system = self.state.get_war_system()
            if war_system:
                for war in war_system._war_discard:
                    if (war.soldier_share > 0 and
                        war.status == WarStatus.RESOLVED and
                        war.triumph_commander_id is not None):
                        commander = self.state.get_member(war.triumph_commander_id)
                        if not commander or commander.is_dead:
                            continue
                        vote = self.triumph_decider.decide_triumph(war, commander, self.state)
                        forum_api.vote_triumph(self.state, player_id, war.id, vote)

            # 4. 公地认购（仅当有待售配额时）
            if self.state.pending_land_sale_quota > 0:
                try:
                    # 获取当前派系所有存活人物，筛选出影响力最高且财富足够的人
                    members = faction.get_members(self.state)
                    eligible = [m for m in members if m.wealth > 0 and not m.is_dead]
                    if eligible:
                        # 按影响力降序排序，选择影响力最高者
                        eligible.sort(key=lambda m: m.influence, reverse=True)
                        best = eligible[0]
                        # 认购数量：不超过剩余配额，不超过财富允许的最大值，可简单设为 min(配额, 财富/单价)
                        land_price = self.state.get_economic_rule("land_price_per_unit", 10)
                        max_by_wealth = best.wealth // land_price
                        if max_by_wealth > 0:
                            quota = self.state.pending_land_sale_quota
                            # 认购数量可随机 1 到 min(配额, max_by_wealth)
                            amount = random.randint(1, min(quota, max_by_wealth))
                            forum_api.buy_land(self.state, player_id, best.id, amount)
                            self.state.log_event(
                                f"AI {faction.name} 为人物 {best.get_formal_name()} 认购 {amount} C 公地",
                                level=logging.DEBUG
                            )
                except Exception as e:
                    logging.exception(f"公地认购 AI 决策异常: {e}")

        except Exception as e:
            logging.exception(f"市场环节 AI 决策异常: {e}")