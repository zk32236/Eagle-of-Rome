#src/core/deciders/impl/
import random
import logging
from typing import List, Dict
from src.core.deciders.festival_decider import FestivalDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState


class AutoFestivalDecider(FestivalDecider):
    """自动庆典决策器：为候选人中符合条件的人物随机花费1到其私库之间的金额"""

    def decide_festivals(self, faction: Faction, candidates: List[Figure], state: GameState) -> Dict[int, int]:
        # 从配置读取最低庆典年龄
        min_age = state.config.get("political_rules.min_festival_age", 30)

        # ===== 新增 DEBUG 日志 =====
        if state:
            state.log_event(
                f"FestivalDecider: 派系 {faction.name} 候选人 {len(candidates)} 人，最低年龄 {min_age}",
                level=logging.DEBUG,
                extra={"faction_id": faction.id, "candidate_count": len(candidates), "min_age": min_age}
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

        # ===== 新增 DEBUG 日志 =====
        if state:
            state.log_event(
                f"FestivalDecider: 派系 {faction.name} 决定举办庆典 {len(decisions)} 人，总花费 {sum(decisions.values())}",
                level=logging.DEBUG,
                extra={"faction_id": faction.id, "decisions_count": len(decisions), "total_spent": sum(decisions.values())}
            )
        return decisions