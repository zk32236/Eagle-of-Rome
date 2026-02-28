import random
from src.core.deciders.triumph_decider import TriumphDecider
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class AutoTriumphDecider(TriumphDecider):
    """自动凯旋审批决策器：根据配置的概率随机决定"""

    def decide_triumph(self, war: War, commander: Figure, state: GameState) -> bool:
        chance = state.config.get("combat_rules.triumph_approval_chance", 0.5)
        return random.random() < chance