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
from src.api import session_turn_service as turn_service


#: Range of narrow structured outcomes (S-C Overlay §1.1 / delta §3.3#6).
Outcome = turn_service.ExecutionOutcome



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

    def process_festival(self, player_id: str, faction: Faction, bypass_permission: bool = False,
                         *, caller_context=None) -> "Outcome":
        """自动举办庆典：为派系内候选人随机举办庆典"""
        if not self.festival_decider:
            self.state.log_event(
                "[WARNING] AutoPlayerProcessor: festival_decider 未设置，跳过庆典",
                level=logging.WARNING
            )
            return Outcome(turn_service.OUTCOME_FAILURE, detail="FESTIVAL_DECIDER_MISSING")

        try:
            from src.api import population_api
            from src.api.population_api import _get_candidates_impl
            # FC-D1-01: internal read inside the owning masked transaction -> the
            # service-private validated-read boundary (never the public boundary).
            cand_result = _get_candidates_impl(self.state)
            if not cand_result["success"]:
                return Outcome(turn_service.OUTCOME_FAILURE,
                               detail="FESTIVAL_CANDIDATES_UNAVAILABLE")
            all_candidates = []
            for office, cands in cand_result["data"].items():
                all_candidates.extend([c["id"] for c in cands])

            # 转换为 Figure 对象
            candidates = []
            for cid in all_candidates:
                fig = self.state.get_member(cid)
                if fig and not fig.is_dead and fig.faction_id == faction.id:
                    candidates.append(fig)
            if not candidates:
                return Outcome(turn_service.OUTCOME_STRUCTURAL_EMPTY,
                               detail="FESTIVAL_NO_OWN_CANDIDATES")

            decisions = self.festival_decider.decide_festivals(faction, candidates, self.state)
            failure = None
            for fig_id, amount in decisions.items():
                result = population_api.campaign(
                    self.state,
                    player_id,
                    fig_id,
                    amount,
                    bypass_permission=bypass_permission,
                    caller_context=caller_context,
                )
                if not result["success"]:
                    failure = result["message"]
                    self.state.log_event(
                        f"AI 庆典失败: {result['message']}",
                        level=logging.WARNING
                    )
            if failure is not None:
                return Outcome(turn_service.OUTCOME_FAILURE, detail=failure)
            if not decisions:
                return Outcome(turn_service.OUTCOME_NO_CHOICE, detail="NO_FESTIVAL_CHOICE")
            return Outcome(turn_service.OUTCOME_ACCEPTED, command_id="process_festival")
        except Exception as e:
            logging.exception(f"庆典环节 AI 决策异常: {e}")
            return Outcome(turn_service.OUTCOME_FAILURE, detail=f"FESTIVAL_EXCEPTION: {e}")

    def process_vote(self, player_id: str, faction: Faction, bypass_permission: bool = False,
                     *, caller_context=None) -> "Outcome":
        """自动投票：为每个公职决定投票对象"""
        if not self.vote_decider:
            self.state.log_event(
                "[WARNING] AutoPlayerProcessor: vote_decider 未设置，跳过投票",
                level=logging.WARNING
            )
            return Outcome(turn_service.OUTCOME_FAILURE, detail="VOTE_DECIDER_MISSING")

        try:
            from src.api.population_api import _get_candidates_impl, vote
            # FC-D1-01: internal read inside the owning masked transaction -> the
            # service-private validated-read boundary (never the public boundary).
            cand_result = _get_candidates_impl(self.state)
            if not cand_result["success"]:
                return Outcome(turn_service.OUTCOME_FAILURE,
                               detail="VOTE_CANDIDATES_UNAVAILABLE")

            failure = None
            voted = 0
            nonempty = 0
            for office, cands in cand_result["data"].items():
                if not cands:
                    continue
                nonempty += 1
                candidate_figures = []
                for c in cands:
                    fig = self.state.get_member(c["id"])
                    if fig:
                        candidate_figures.append(fig)
                chosen_id = self.vote_decider.decide_vote(office, candidate_figures, faction, self.state)
                if chosen_id is not None:
                    result = vote(
                        self.state,
                        player_id,
                        office,
                        chosen_id,
                        bypass_permission=bypass_permission,
                        caller_context=caller_context,
                    )
                    if not result["success"]:
                        failure = result["message"]
                        self.state.log_event(
                            f"AI 投票失败: {result['message']}",
                            level=logging.WARNING
                        )
                    else:
                        voted += 1
            if failure is not None:
                return Outcome(turn_service.OUTCOME_FAILURE, detail=failure)
            if nonempty == 0:
                return Outcome(turn_service.OUTCOME_STRUCTURAL_EMPTY,
                               detail="VOTE_ALL_OFFICES_EMPTY")
            if voted == 0:
                # deliberate eligible-decider no-choice on a mandatory vote.
                return Outcome(turn_service.OUTCOME_NO_CHOICE, detail="NO_VOTE_CHOICE")
            return Outcome(turn_service.OUTCOME_ACCEPTED, command_id="process_vote")
        except Exception as e:
            logging.exception(f"投票环节 AI 决策异常: {e}")
            return Outcome(turn_service.OUTCOME_FAILURE, detail=f"VOTE_EXCEPTION: {e}")

    def process_retirement(self, player_id: str, faction: Faction) -> "Outcome":
        try:
            fig_id = self.retirement_decider.decide_whom_to_retire(faction)
            if fig_id is None:
                return Outcome(turn_service.OUTCOME_NO_CHOICE, detail="NO_RETIREMENT_CHOICE")

            # 使用 forum_api.retire_figure 处理淘汰
            result = forum_api.retire_figure(self.state, player_id, fig_id)
            if result["success"]:
                # 如果成功，API 内部已记录操作，这里只需输出提示
                figure = self.state.get_member(fig_id)
                if figure:
                    print(f"   🤖 AI {faction.name} 淘汰了1位成员！", flush=True)
                return Outcome(turn_service.OUTCOME_ACCEPTED,
                               command_id="process_retirement")
            else:
                self.state.log_event(
                    f"AI 淘汰失败: {result['message']}",
                    level=logging.WARNING,
                    extra={"player_id": player_id, "figure_id": fig_id}
                )
                return Outcome(turn_service.OUTCOME_FAILURE, detail=result["message"])
        except Exception as e:
            logging.exception(f"裁员环节 AI 决策异常: {e}")
            return Outcome(turn_service.OUTCOME_FAILURE, detail=f"RETIREMENT_EXCEPTION: {e}")

    def process_market(self, player_id: str, faction: Faction, *,
                       caller_context=None, ai_capability=None) -> "Outcome":
        """执行市场环节决策（招募、竞标、凯旋投票、公地认购）。

        S-C F4: every authoritative child API outcome is CHECKED — a denied child
        (recruit/bid/triumph/land) is NOT swallowed into a false ACCEPTED; the
        aggregate returns FAILURE with the child reason so the caller never records
        a lawful finish on top of a failed business effect.
        """
        try:
            failure = None
            # Only checked successful child owner operations attest committed work.
            committed = []
            has_choices = False
            presented = {}
            if caller_context is not None:
                presented["caller_context"] = caller_context
            if ai_capability is not None:
                presented["ai_capability"] = ai_capability
            # 1. 招募
            available_figures = self.state.curia.get_all_available()
            # WP-I S3（DESIGN FROZEN 2026-09-26）：Auto 路 vacancies 来源收敛单权威 resolver——
            # 传“权威剩余招募槽位”（physical_vacancies − pending distinct）；不再读 config
            # faction_member_limit / 固定 6（R-I02/R-I08）。decider 策略零改（vacancy-bounded）。
            vacancies = self.state.get_remaining_recruitment_slots(faction.id)
            has_choices = bool(available_figures) and vacancies > 0
            bids = self.recruitment_decider.decide_bids(
                faction, available_figures, vacancies, self.state
            )
            for fig_id, amount in bids.items():
                result = forum_api.recruit_figure(self.state, player_id, fig_id, amount, **presented)
                if not result.get("success"):
                    failure = result.get("message") or "RECRUIT_FIGURE_FAILED"
                else:
                    committed.append("recruit_figure")

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

                if contract.contract_type in (ContractType.TAX_FARMING, ContractType.PUBLIC_WORKS):
                    has_choices = True
                if contract.contract_type == ContractType.TAX_FARMING:
                    result = self.bid_decider.decide_tax_bid(contract, knights, self.state)
                    if result:
                        knight, amount, profit_rate = result
                        bid = forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, profit_rate, **presented)
                        if not bid.get("success"):
                            failure = bid.get("message") or "PLACE_BID_FAILED"
                        else:
                            committed.append("place_bid")

                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    if getattr(contract, '_is_fleet_construction', False):
                        result = self.bid_decider.decide_fleet_bid(contract, knights, self.state)
                        if result:
                            knight, amount, profit_rate = result
                            bid = forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, profit_rate, **presented)
                            if not bid.get("success"):
                                failure = bid.get("message") or "PLACE_BID_FAILED"
                            else:
                                committed.append("place_bid")
                    else:
                        result = self.bid_decider.decide_works_bid(contract, knights, self.state)
                        if result:
                            knight, amount, profit_rate, construction, warranty = result
                            # place_bid 会重新计算工期/质保期，但为了保持一致性，还是传入利润率
                            bid = forum_api.place_bid(self.state, player_id, knight.id, contract.id, amount, profit_rate, **presented)
                            if not bid.get("success"):
                                failure = bid.get("message") or "PLACE_BID_FAILED"
                            else:
                                committed.append("place_bid")

            # 3. 凯旋投票
            war_system = self.state.get_war_system()
            if war_system:
                for war in war_system.get_resolved_wars():
                    if (war.soldier_share > 0 and
                        war.status == WarStatus.RESOLVED and
                        war.triumph_commander_id is not None):
                        commander = self.state.get_member(war.triumph_commander_id)
                        if not commander or commander.is_dead:
                            continue
                        has_choices = True
                        vote = self.triumph_decider.decide_triumph(war, commander, self.state)
                        tv = forum_api.vote_triumph(self.state, player_id, war.id, vote, **presented)
                        if not tv.get("success"):
                            failure = tv.get("message") or "VOTE_TRIUMPH_FAILED"
                        else:
                            committed.append("vote_triumph")

            # 4. 公地认购（仅当有待售配额时）
            if self.state.pending_land_sale_quota > 0:
                try:
                    # 获取当前派系所有存活人物，筛选出影响力最高且财富足够的人
                    members = faction.get_members(self.state)
                    eligible = [m for m in members if m.wealth > 0 and not m.is_dead]
                    if eligible:
                        has_choices = True
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
                            land = forum_api.buy_land(self.state, player_id, best.id, amount, **presented)
                            if not land.get("success"):
                                failure = land.get("message") or "BUY_LAND_FAILED"
                            else:
                                committed.append("buy_land")
                                self.state.log_event(
                                    f"AI {faction.name} 为人物 {best.get_formal_name()} 认购 {amount} C 公地",
                                    level=logging.DEBUG
                                )
                except Exception as e:
                    # F4: a swallowed land exception is NOT a lawful completion.
                    logging.exception(f"公地认购 AI 决策异常: {e}")
                    failure = f"BUY_LAND_EXCEPTION: {e}"

            if failure is not None:
                # A denied/exception child is NOT a false ACCEPTED — the caller must
                # not record a lawful finish (F4).
                return Outcome(turn_service.OUTCOME_FAILURE, detail=failure,
                               receipts=tuple(committed))
            if committed:
                return Outcome(turn_service.OUTCOME_ACCEPTED, command_id="process_market",
                               receipts=tuple(committed))
            if has_choices:
                return Outcome(turn_service.OUTCOME_NO_CHOICE, detail="NO_MARKET_CHOICE")
            return Outcome(turn_service.OUTCOME_STRUCTURAL_EMPTY,
                           detail="MARKET_NO_AVAILABLE_OPERATIONS")
        except Exception as e:
            logging.exception(f"市场环节 AI 决策异常: {e}")
            return Outcome(turn_service.OUTCOME_FAILURE, detail=f"MARKET_EXCEPTION: {e}")

    def process_senate(self, player_id: str, faction: Faction, bypass_permission: bool = False) -> dict:
        """自动执行元老院阶段提案生成（AI 执政官专用）。

        当人类玩家不是执政官时，由 AutoPlayerProcessor 检测并调用此方法，
        确保 AI 执政官自动提交提案。

        Args:
            player_id: 当前人类玩家 ID（用于日志上下文）
            faction: 当前人类玩家派系
            bypass_permission: 保留参数，接口一致性

        Returns:
            senate_api.auto_submit_proposals() 的 api_response dict
        """
        try:
            from src.api import senate_api
            result = senate_api.auto_submit_proposals(self.state)
            if result["success"]:
                count = len(result["data"].get("proposals", []))
                self.state.log_event(
                    f"AI 自动提案完成: {faction.name} 提交了 {count} 项法案",
                    level=logging.INFO,
                )
            else:
                self.state.log_event(
                    f"AI 自动提案失败: {result['message']}",
                    level=logging.WARNING,
                )
            return result
        except Exception as e:
            self.state.log_event(
                f"元老院阶段 AI 决策异常: {e}",
                level=logging.ERROR,
            )
            return {"success": False, "message": str(e), "data": {}, "errors": [str(e)]}
