#src/core/deciders/impl/
import random
import logging
from src.core.deciders.triumph_decider import TriumphDecider
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState


class AutoTriumphDecider(TriumphDecider):
    """自动凯旋审批决策器：根据配置的概率随机决定"""

    def decide_triumph(self, war: War, commander: Figure, state: GameState) -> bool:
        chance = state.config.get("combat_rules.triumph_approval_chance", 0.5)
        random_val = random.random()
        result = random_val < chance

        # ===== 新增 DEBUG 日志 =====
        if state:
            state.log_event(
                f"TriumphDecider: 战争 {war.name} 指挥官 {commander.name} 概率 {chance} 随机值 {random_val:.3f} 结果 {result}",
                level=logging.DEBUG,
                extra={"war_id": war.id, "commander_id": commander.id, "chance": chance, "random": random_val, "result": result}
            )

        return result