# src/core/deciders/impl/auto_festival_decider.py
import random
import logging
from typing import List, Dict
from src.core.deciders.festival_decider import FestivalDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class AutoFestivalDecider(FestivalDecider):
    def decide_festivals(self, faction: Faction, candidates: List[Figure], state: GameState) -> Dict[int, int]:
        min_age = state.config.get("political_rules.min_festival_age", 30)
        extra = {
            "function": "decide_festivals",
            "decider": self.__class__.__name__,
            "faction_id": faction.id,
            "faction_name": faction.name,
            "candidate_count": len(candidates),
            "min_age": min_age
        }
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_festivals: 派系 {faction.name} 候选人 {len(candidates)} 人，最低年龄 {min_age}",
            level=logging.DEBUG,
            extra=extra
        )

        decisions = {}
        for fig in candidates:
            if fig.is_dead:
                continue
            if fig.age < min_age:
                continue
            if fig.office is not None and not fig.office.startswith("ex-"):
                continue
            if fig.wealth <= 0:
                continue
            amount = random.randint(1, fig.wealth)
            decisions[fig.id] = amount

        extra["decisions_count"] = len(decisions)
        extra["total_spent"] = sum(decisions.values())
        extra["result"] = {str(k): v for k, v in decisions.items()}
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_festivals: 派系 {faction.name} 决定举办庆典 {len(decisions)} 人，总花费 {sum(decisions.values())}",
            level=logging.DEBUG,
            extra=extra
        )
        return decisions