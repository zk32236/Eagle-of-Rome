#src/core/deciders/impl/
from src.core.deciders.bid_decider import BidDecider
from src.core.entities.contract import Contract
from src.core.entities.figure import Figure
from src.core.game_state import GameState
from typing import Optional, Tuple


class AutoBidDecider(BidDecider):
    """自动竞标决策器（基础版本）"""

    def decide_tax_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float]]:
        """包税合同竞标，基础版本返回 None（不出价）"""
        return None

    def decide_works_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float, int, int]]:
        """工程合同竞标，基础版本返回 None（不出价）"""
        return None

    def decide_fleet_bid(
        self,
        contract: Contract,
        knights: list[Figure],
        state: GameState
    ) -> Optional[Tuple[Figure, int, float]]:
        """舰队建造合同竞标，基础版本返回 None（不出价）"""
        return None