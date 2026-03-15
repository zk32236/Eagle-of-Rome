from src.core.deciders.land_trade_decider import LandTradeDecider
from src.core.game_state import GameState
from typing import Optional, Tuple

class ManualLandTradeDecider(LandTradeDecider):
    """手动土地交易决策器（骨架）"""
    def decide_trade(self, state: GameState) -> Optional[Tuple[int, int, int]]:
        print("手动土地交易决策器被调用（当前为骨架）")
        return None