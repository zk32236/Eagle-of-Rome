# src/core/deciders/impl/auto_land_trade_decider.py
import random
import logging
from typing import Optional, Tuple
from src.core.deciders.land_trade_decider import LandTradeDecider
from src.core.entities.figure import ClassTier
from src.core.game_state import GameState

class AutoLandTradeDecider(LandTradeDecider):
    def decide_trade(self, state: GameState) -> Optional[Tuple[int, int, int]]:
        extra = {
            "function": "decide_trade",
            "decider": self.__class__.__name__
        }
        living = state.get_living_members()
        extra["living_count"] = len(living)
        if not living:
            extra["result"] = None
            extra["reason"] = "no_living"
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_trade: 无存活人物",
                level=logging.DEBUG,
                extra=extra
            )
            return None

        nobles = [f for f in living if f.class_tier == ClassTier.NOBILE]
        equites = [f for f in living if f.class_tier == ClassTier.EQUES]
        extra["noble_count"] = len(nobles)
        extra["equite_count"] = len(equites)

        if not nobles or not equites:
            extra["result"] = None
            extra["reason"] = "insufficient_classes"
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_trade: 贵族 {len(nobles)} 骑士 {len(equites)} 不足",
                level=logging.DEBUG,
                extra=extra
            )
            return None

        seller = random.choice(nobles)
        buyer = random.choice(equites)
        extra["seller_id"] = seller.id
        extra["buyer_id"] = buyer.id

        if seller.land_private <= 0:
            extra["result"] = None
            extra["reason"] = "seller_no_land"
            state.log_event(
                f"[DEBUG] {self.__class__.__name__}.decide_trade: 卖家 {seller.name} 无私地",
                level=logging.DEBUG,
                extra=extra
            )
            return None

        amount = random.randint(1, seller.land_private)
        extra["amount"] = amount
        extra["result"] = (seller.id, buyer.id, amount)
        state.log_event(
            f"[DEBUG] {self.__class__.__name__}.decide_trade: 选择交易 卖家 {seller.name}(ID:{seller.id}) 买家 {buyer.name}(ID:{buyer.id}) 数量 {amount}",
            level=logging.DEBUG,
            extra=extra
        )
        return seller.id, buyer.id, amount