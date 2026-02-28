import random
from src.core.deciders.war_takeover_decider import WarTakeoverDecider
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class AutoWarTakeoverDecider(WarTakeoverDecider):
    """自动战争接管决策器：根据配置的概率随机决定"""

    def decide_takeover(self, war: War, new_consul: Figure, old_commander: Figure, state: GameState) -> bool:
        chance = state.config.get("combat_rules.war_takeover_chance", 1.0)
        return random.random() < chance