# src/core/deciders/impl/auto_vote_decider.py
import random
import logging
from typing import List, Optional
from src.core.deciders.vote_decider import VoteDecider
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction
from src.core.game_state import GameState

class AutoVoteDecider(VoteDecider):
    def decide_vote(self, office: str, candidates: List[Figure], faction: Faction, state: GameState) -> Optional[int]:
        extra = {
            "function": "decide_vote",
            "decider": self.__class__.__name__,
            "office": office,
            "faction_id": faction.id,
            "faction_name": faction.name,
            "candidates_count": len(candidates)
        }
        if not candidates:
            extra["result"] = None
            extra["reason"] = "no_candidates"
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_vote: 派系 {faction.name} 为 {office} 投票：无候选人",
                level=logging.DEBUG,
                extra=extra
            )
            return None

        own_candidates = [c for c in candidates if c.faction_id == faction.id]
        extra["own_candidates_count"] = len(own_candidates)

        if own_candidates:
            chosen = max(own_candidates, key=lambda c: c.influence)
            reason = f"本派系候选人中影响力最高({chosen.influence})"
        else:
            chosen = random.choice(candidates)
            reason = "随机候选人"

        extra.update({
            "chosen_id": chosen.id,
            "chosen_name": chosen.name,
            "reason": reason,
            "result": chosen.id
        })
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_vote: 派系 {faction.name} 为 {office} 投票给 {chosen.name} (ID:{chosen.id})，原因：{reason}",
            level=logging.DEBUG,
            extra=extra
        )
        return chosen.id