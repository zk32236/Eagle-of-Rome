from abc import ABC, abstractmethod
from typing import Optional, Tuple

class LandTradeDecider(ABC):
    """土地交易决策器接口"""

    @abstractmethod
    def decide_trade(self, state) -> Optional[Tuple[int, int, int]]:
        """
        决定是否进行一笔土地交易。
        返回 (卖家ID, 买家ID, 交易数量) 或 None。
        """
        pass