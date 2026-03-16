# src/core/deciders/impl/auto_vote_decider.py
import random
import logging
from typing import List, Optional
from src.core.deciders.vote_decider import VoteDecider
from src.core.entities.figure import Figure
from src.core.entities.entities import Faction
from src.core.game_state import GameState


class AutoVoteDecider(VoteDecider):
    """自动投票决策器：随机选择本派系候选人，若无则从所有候选人中随机选一人"""

    def decide_vote(self, office: str, candidates: List[Figure], faction: Faction, state: GameState) -> Optional[int]:
        if not candidates:
            # 无候选人，弃权
            return None

        # 过滤出本派系的候选人
        own_candidates = [c for c in candidates if c.faction_id == faction.id]

        if own_candidates:
            # 有本派系候选人，随机选择一个
            chosen = random.choice(own_candidates)
            chosen_id = chosen.id
            reason = "本派系候选人"
        else:
            # 无本派系候选人，从所有候选人中随机选一个（可调整策略，如弃权）
            # 简单起见，我们仍随机选一个（模拟“随意投票”）
            chosen = random.choice(candidates)
            chosen_id = chosen.id
            reason = "随机候选人"

        # 记录调试日志
        state.log_event(
            f"AutoVoteDecider: 派系 {faction.name} 为 {office} 投票给 {chosen.name} (ID:{chosen_id})，原因：{reason}",
            level=logging.DEBUG,
            extra={
                "faction_id": faction.id,
                "office": office,
                "chosen_id": chosen_id,
                "reason": reason
            }
        )

        return chosen_id