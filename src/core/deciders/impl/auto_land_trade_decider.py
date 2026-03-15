#src/core/deciders/impl/
import random
import logging
from typing import Optional, Tuple, List
from src.core.deciders.land_trade_decider import LandTradeDecider
from src.core.entities.figure import ClassTier
from src.core.game_state import GameState


class AutoLandTradeDecider(LandTradeDecider):
    """自动土地交易决策器：随机选择一对贵族和骑士进行土地交易"""

    def decide_trade(self, state: GameState) -> Optional[Tuple[int, int, int]]:
        # 获取所有存活人物
        living = state.get_living_members()
        if not living:
            # ===== 新增 DEBUG 日志 =====
            if state:
                state.log_event(
                    "LandTradeDecider: 无存活人物",
                    level=logging.DEBUG,
                    extra={}
                )
            return None

        # 分离贵族和骑士
        nobles = [f for f in living if f.class_tier == ClassTier.NOBILE]
        equites = [f for f in living if f.class_tier == ClassTier.EQUES]

        if not nobles or not equites:
            # ===== 新增 DEBUG 日志 =====
            if state:
                state.log_event(
                    f"LandTradeDecider: 贵族 {len(nobles)} 人，骑士 {len(equites)} 人，不足",
                    level=logging.DEBUG,
                    extra={"noble_count": len(nobles), "equite_count": len(equites)}
                )
                return None

        # 随机选择贵族（卖家）和骑士（买家）
        seller = random.choice(nobles)
        buyer = random.choice(equites)

        # 如果卖家无私地，无法交易
        if seller.land_private <= 0:
            # ===== 新增 DEBUG 日志 =====
            if state:
                state.log_event(
                    f"LandTradeDecider: 卖家 {seller.name} 无私地",
                    level=logging.DEBUG,
                    extra={"seller_id": seller.id}
                )
            return None

        # 随机交易数量：1 到卖家土地之间
        amount = random.randint(1, seller.land_private)

        # ===== 新增 DEBUG 日志 =====
        if state:
            state.log_event(
                f"LandTradeDecider: 选择交易 卖家 {seller.name}(ID:{seller.id}) 买家 {buyer.name}(ID:{buyer.id}) 数量 {amount}",
                level=logging.DEBUG,
                extra={"seller_id": seller.id, "buyer_id": buyer.id, "amount": amount}
            )

        return seller.id, buyer.id, amount