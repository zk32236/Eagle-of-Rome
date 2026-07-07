# src/core/deciders/impl/auto_recruitment_decider.py
import random
import logging
from typing import List, Dict
from src.core.deciders.recruitment_decider import RecruitmentDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class AutoRecruitmentDecider(RecruitmentDecider):
    def decide_bids(self, faction: Faction, available_figures: List[Figure],
                    vacancies: int, state: GameState) -> Dict[int, int]:
        extra = {
            "function": "decide_bids",
            "decider": self.__class__.__name__,
            "faction_id": faction.id,
            "faction_treasury": faction.treasury,
            "vacancies": vacancies,
            "available_count": len(available_figures)
        }

        if faction.treasury <= 0 or vacancies <= 0:
            extra["result"] = {}
            extra["reason"] = "insufficient_treasury_or_no_vacancy"
            if state:  # ← 添加保护
                state.log_event(
                    f"[DEBUG] {self.__class__.__name__}.decide_bids: 派系 {faction.name} 国库 {faction.treasury} 空缺 {vacancies}，无法出价",
                    level=logging.DEBUG,
                    extra=extra
                )
            return {}

        eligible = [fig for fig in available_figures
                    if getattr(fig, 'abandoned_by', None) != faction.id]
        extra["eligible_count"] = len(eligible)

        if not eligible:
            extra["result"] = {}
            extra["reason"] = "no_eligible"
            if state:  # ← 添加保护
                state.log_event(
                    f"[DEBUG] {self.__class__.__name__}.decide_bids: 派系 {faction.name} 无可招募人物",
                    level=logging.DEBUG,
                    extra=extra
                )
            return {}

        random.shuffle(eligible)
        selected = eligible[:vacancies]
        bids = {}
        for fig in selected:
            amount = random.randint(1, faction.treasury)
            bids[fig.id] = amount

        extra["result"] = {str(k): v for k, v in bids.items()}  # 转为字符串键便于日志
        extra["bid_count"] = len(bids)
        extra["total_bid"] = sum(bids.values())
        if state:  # ← 添加保护
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_bids: 派系 {faction.name} 决定出价 {len(bids)} 人，总预算 {sum(bids.values())}",
                level=logging.DEBUG,
                extra=extra
        )
        return bids