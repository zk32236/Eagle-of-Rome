import random
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
            return None

        # 分离贵族和骑士
        nobles = [f for f in living if f.class_tier == ClassTier.NOBILE]
        equites = [f for f in living if f.class_tier == ClassTier.EQUES]

        if not nobles or not equites:
            return None

        # 随机选择贵族（卖家）和骑士（买家）
        seller = random.choice(nobles)
        buyer = random.choice(equites)

        # 如果卖家无私地，尝试交换角色（贵族作为买家，骑士作为卖家）？
        # 根据设计，应该是贵族卖地给骑士。如果贵族无私地，则无法交易，返回 None。
        if seller.land_private <= 0:
            return None

        # 随机交易数量：1 到卖家土地之间
        amount = random.randint(1, seller.land_private)

        return seller.id, buyer.id, amount