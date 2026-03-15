from src.core.deciders.triumph_decider import TriumphDecider
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class ManualTriumphDecider(TriumphDecider):
    """手动凯旋投票决策器（骨架）"""
    def decide_triumph(self, war: War, commander: Figure, state: GameState) -> bool:
        print("手动凯旋投票决策器被调用（当前为骨架）")
        return False