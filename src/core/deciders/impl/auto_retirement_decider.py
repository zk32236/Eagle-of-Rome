# src/core/deciders/impl/auto_retirement_decider.py
import random
import logging
from typing import Optional
from src.core.deciders.retirement_decider import RetirementDecider
from src.core.entities.entities import Faction
from src.core.game_state import GameState

class AutoRetirementDecider(RetirementDecider):
    def __init__(self, state: GameState):
        self.state = state

    def decide_whom_to_retire(self, faction: Faction) -> Optional[int]:
        chance = self.state.config.get("political_rules.retirement_chance", 0.3)
        random_val = random.random()
        extra = {
            "function": "decide_whom_to_retire",
            "decider": self.__class__.__name__,
            "faction_id": faction.id,
            "chance": chance,
            "random": random_val,
        }

        if random_val >= chance:
            extra["result"] = None
            extra["reason"] = "chance_not_hit"
            self.state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_whom_to_retire: 派系 {faction.name} 概率未命中，不淘汰",
                level=logging.DEBUG,
                extra=extra
            )
            return None

        members = faction.get_members(self.state)
        extra["member_count"] = len(members)

        eligible = [
            m for m in members
            if not m.is_faction_leader
               and not (m.office and not m.office.startswith("ex-"))
               and not m.has_active_contract
        ]
        extra["eligible_count"] = len(eligible)

        if not eligible:
            extra["result"] = None
            extra["reason"] = "no_eligible"
            self.state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_whom_to_retire: 派系 {faction.name} 无符合条件人物",
                level=logging.DEBUG,
                extra=extra
            )
            return None

        chosen = random.choice(eligible)
        extra["chosen_id"] = chosen.id
        extra["result"] = chosen.id
        extra["reason"] = "eligible_available"
        self.state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_whom_to_retire: 派系 {faction.name} 淘汰 {chosen.name} (ID:{chosen.id})",
            level=logging.DEBUG,
            extra=extra
        )
        return chosen.id