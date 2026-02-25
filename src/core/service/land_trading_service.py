# src/core/service/land_trading_service.py

from typing import Optional, Tuple
from src.core.game_state import GameState
from src.core.entities.figure import Figure
from src.core.localization import TerminologyService


class LandTradingService:
    """
    土地交易服务 - MVP 0.4.4

    职责：
    1. 计算土地价格（基于人气、权力、派系关系）
    2. 执行人物间土地买卖
    3. 更新席位占比
    """

    BASE_LAND_PRICE = 10  # 基础土地价格（塔兰特/单位）

    def __init__(self, state: GameState):
        self.state = state

    def calculate_land_price(self, seller: Figure, buyer: Figure) -> int:
        """
        计算土地交易价格 - 基于双方属性浮动

        价格公式：基础价格 × (1 + 卖方溢价 - 买方折扣)
        """
        terms = TerminologyService.get()

        base = self.BASE_LAND_PRICE
        modifier = 1.0

        # 卖方溢价因素
        if seller.popularity >= buyer.popularity:
            modifier += 0.20
        if seller.influence >= buyer.influence:
            modifier += 0.10

        # 买方折扣因素
        if buyer.popularity >= 10:
            modifier -= 0.10
        if seller.faction_id == buyer.faction_id:
            modifier -= 0.20
        elif seller.faction_id and buyer.faction_id:
            relation = self._get_faction_relation(seller.faction_id, buyer.faction_id)
            if relation == "hostile":
                modifier += 0.30

        modifier = max(0.5, min(2.0, modifier))

        final_price = int(base * modifier)
        return final_price

    def _get_faction_relation(self, faction_id1: str, faction_id2: str) -> str:
        """获取派系关系（预留接口，MVP简化）"""
        return "neutral"

    def execute_trade(self, seller_id: int, buyer_id: int, amount: int) -> Tuple[bool, str]:
        terms = TerminologyService.get()

        seller = self.state.get_member(seller_id)
        buyer = self.state.get_member(buyer_id)

        if not seller or not buyer:
            return False, "Figure not found"

        if seller.is_dead or buyer.is_dead:
            return False, "Deceased figure cannot trade"

        if seller_id == buyer_id:
            return False, "Cannot trade with yourself"

        if amount <= 0:
            return False, "Invalid amount"

        # 检查卖方土地是否足够
        if seller.land_private < amount:
            return False, f"{seller.name} has insufficient land ({seller.land_private} < {amount})"

        # 计算价格
        price_per_unit = self.calculate_land_price(seller, buyer)
        total_cost = amount * price_per_unit

        if buyer.wealth < total_cost:
            return False, f"{buyer.name} cannot afford {total_cost} {terms.currency} (has {buyer.wealth})"

        # 记录交易前状态（用于显示）
        seller_land_before = seller.land_private
        buyer_land_before = buyer.land_private

        # 执行交易
        earnings = seller.sell_land(amount, price_per_unit)  # 卖家土地减少，财富增加
        if earnings == 0:
            return False, "Seller failed to sell land"
        success = buyer.buy_land(amount, price_per_unit)  # 买家财富减少，土地增加
        if not success:
            # 回滚卖家
            seller.buy_land(amount, price_per_unit)  # 重新买回
            return False, "Buyer failed to buy land"

        # 记录交易历史
        self._record_trade(seller, buyer, amount, price_per_unit)

        # 生成消息
        msg = (f"Trade complete: {amount} land @ {price_per_unit}/unit = {total_cost} {terms.currency}\n"
               f"   {seller.name}: land {seller_land_before}→{seller.land_private}, "
               f"seats {self._calculate_seats(seller_land_before, seller.veterans)}→{self._calculate_seats(seller.land_private, seller.veterans)} (of 300)\n"
               f"   {buyer.name}: land {buyer_land_before}→{buyer.land_private}, "
               f"seats {self._calculate_seats(buyer_land_before, buyer.veterans)}→{self._calculate_seats(buyer.land_private, buyer.veterans)} (of 300)")

        return True, msg

    def _calculate_seats(self, land: int, veterans: int, total_assets: int = None) -> int:
        """根据土地和私兵计算席位（需全国总资产）"""
        if total_assets is None:
            all_figures = [m for m in self.state.get_living_members() if not m.is_dead]
            total_land = sum(m.land_private for m in all_figures)
            total_veterans = sum(m.veterans for m in all_figures)
            total_assets = total_land + total_veterans
        if total_assets == 0:
            return 0
        assets = land + veterans
        return int((assets / total_assets) * 300)

    def _record_trade(self, seller: Figure, buyer: Figure, amount: int, price: int):
        """记录交易历史"""
        trade_record = {
            "turn": self.state.turn.turn_number,
            "seller_id": seller.id,
            "buyer_id": buyer.id,
            "amount": amount,
            "price_per_unit": price,
            "total_value": amount * price
        }
        if not hasattr(seller, 'land_trade_history'):
            seller.land_trade_history = []
        seller.land_trade_history.append(trade_record)

    def get_trade_preview(self, seller_id: int, buyer_id: int, amount: int) -> Optional[dict]:
        seller = self.state.get_member(seller_id)
        buyer = self.state.get_member(buyer_id)

        if not seller or not buyer:
            return None

        price_per_unit = self.calculate_land_price(seller, buyer)
        total_cost = amount * price_per_unit

        return {
            "seller_name": seller.name,
            "buyer_name": buyer.name,
            "amount": amount,
            "price_per_unit": price_per_unit,
            "total_cost": total_cost,
            "seller_land_after": seller.land_private - amount,
            "buyer_land_after": buyer.land_private + amount,
            "can_execute": seller.land_private >= amount and buyer.wealth >= total_cost
        }

    def get_faction_land_summary(self, faction_id: str) -> dict:
        """获取派系土地摘要"""
        faction = self.state.get_faction(faction_id)
        if not faction:
            return {}

        members = faction.get_members(self.state)
        total_land = sum(m.land_private for m in members)
        total_seats = sum(m.get_seat_share() for m in members)

        return {
            "faction_name": faction.name,
            "member_count": len(members),
            "total_land": total_land,
            "total_seats": total_seats,
            "avg_land_per_member": total_land // len(members) if members else 0
        }