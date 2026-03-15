from src.core.deciders.bid_decider import BidDecider
from src.core.entities.contract import Contract
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from typing import Optional, Tuple

class ManualBidDecider(BidDecider):
    """手动竞标决策器（骨架）"""
    def decide_tax_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float]]:
        print("手动包税竞标决策器被调用（当前为骨架）")
        return None

    def decide_works_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float, int, int]]:
        print("手动工程竞标决策器被调用（当前为骨架）")
        return None

    def decide_fleet_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float]]:
        print("手动舰队建造竞标决策器被调用（当前为骨架）")
        return None