# src/ui/processors/auto_player_processor.py
import logging
from typing import Optional

from src.core.game_state import GameState
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.contract import ContractType, ContractStatus
from src.core.entities.war import WarStatus
from src.core.deciders.retirement_decider import RetirementDecider
from src.core.deciders.recruitment_decider import RecruitmentDecider
from src.core.deciders.bid_decider import BidDecider
from src.core.deciders.triumph_decider import TriumphDecider


class AutoPlayerProcessor:
    def __init__(self,
                 state: GameState,
                 retirement_decider: RetirementDecider,
                 recruitment_decider: RecruitmentDecider,
                 bid_decider: BidDecider,
                 triumph_decider: TriumphDecider):
        self.state = state
        self.retirement_decider = retirement_decider
        self.recruitment_decider = recruitment_decider
        self.bid_decider = bid_decider
        self.triumph_decider = triumph_decider

    def process_retirement(self, player_id: str, faction: Faction) -> bool:
        """执行裁员决策。返回 True 表示执行了淘汰，否则 False。"""
        try:
            fig_id = self.retirement_decider.decide_whom_to_retire(faction)
            if fig_id is None:
                return False

            figure = self.state.get_member(fig_id)
            if not figure or figure.faction_id != faction.id:
                self.state.log_event(
                    f"[WARNING] 裁员决策返回的人物 {fig_id} 不属于派系 {faction.id}，已忽略",
                    level=logging.WARNING,
                    extra={"function": "process_retirement", "player_id": player_id}
                )
                return False

            # 从派系移除
            faction.remove_member(fig_id)
            # 加入广场
            self.state.curia.add_figure(figure)
            figure.faction_id = None
            figure.is_faction_leader = False
            # 记录操作（用于公示）
            self.state.add_forum_action("retirements", fig_id)
            # 记录日志
            self.state.log_event(
                f"人物被淘汰: {figure.get_formal_name()}",
                level=logging.INFO,
                extra={"figure_id": figure.id}
            )
            # 用户可见提示
            print(f"   🤖 AI {faction.name} 淘汰了 {figure.get_formal_name()}", flush=True)
            return True

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
                self.state.add_forum_action("recruitment_bids", (faction.id, fig_id, amount))

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
                        knight, amount, tax_rate = result
                        self.state.add_forum_action(
                            "contract_bids",
                            (contract.id, knight.id, faction.id, amount)
                        )
                elif contract.contract_type == ContractType.PUBLIC_WORKS:
                    if getattr(contract, '_is_fleet_construction', False):
                        result = self.bid_decider.decide_fleet_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r = result
                            self.state.add_forum_action(
                                "contract_bids",
                                (contract.id, knight.id, faction.id, amount)
                            )
                    else:
                        result = self.bid_decider.decide_works_bid(contract, knights, self.state)
                        if result:
                            knight, amount, r, construction, warranty = result
                            self.state.add_forum_action(
                                "contract_bids",
                                (contract.id, knight.id, faction.id, amount)
                            )

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
                        self.state.add_forum_action(
                            "triumph_votes",
                            (war.id, faction.id, vote)
                        )

        except Exception as e:
            logging.exception(f"市场环节 AI 决策异常: {e}")