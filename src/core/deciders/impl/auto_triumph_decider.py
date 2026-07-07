# src/core/deciders/impl/auto_triumph_decider.py
import random
import logging
from src.core.deciders.triumph_decider import TriumphDecider
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class AutoTriumphDecider(TriumphDecider):
    def decide_triumph(self, war: War, commander: Figure, state: GameState) -> bool:
        chance = state.config.get("combat_rules.triumph_approval_chance", 0.5)
        random_val = random.random()
        result = random_val < chance
        extra = {
            "function": "decide_triumph",
            "decider": self.__class__.__name__,
            "war_id": war.id,
            "war_name": war.name,
            "commander_id": commander.id,
            "commander_name": commander.name,
            "chance": chance,
            "random": random_val,
            "result": result
        }
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_triumph: 战争 {war.name} 指挥官 {commander.name} 概率 {chance} 随机值 {random_val:.3f} 结果 {result}",
            level=logging.DEBUG,
            extra=extra
        )
        return result