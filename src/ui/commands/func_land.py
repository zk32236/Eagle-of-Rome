# src/ui/commands/func_land.py
"""
土地交易功能命令：土地交易、价格预览、席位显示
"""

from typing import List, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.service.land_trading_service import LandTradingService
from src.core.localization import TerminologyService

if TYPE_CHECKING:
    from src.core.game_state import GameState


class TradeCommand(Command):
    """执行土地交易，子命令: land"""

    name = "trade"
    aliases = []
    description = "执行交易，用法: trade land <卖家ID> <买家ID> <数量>"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _parse_int(self, s: str, desc: str) -> Optional[int]:
        try:
            return int(s)
        except ValueError:
            print(f"❌ {desc} 必须为整数: {s}")
            return None

    def execute(self, args: List[str]) -> bool:
        if len(args) != 4 or args[0].lower() != "land":
            print("❌ 用法: trade land <卖家ID> <买家ID> <数量>")
            return False

        seller_id = self._parse_int(args[1], "卖家ID")
        if seller_id is None:
            return False
        buyer_id = self._parse_int(args[2], "买家ID")
        if buyer_id is None:
            return False
        amount = self._parse_int(args[3], "数量")
        if amount is None:
            return False
        if amount <= 0:
            print("❌ 数量必须为正数")
            return False

        service = LandTradingService(self.state)
        success, msg = service.execute_trade(seller_id, buyer_id, amount)
        print(msg)
        return success


class LandCommand(Command):
    """土地相关命令，子命令: price"""

    name = "land"
    aliases = []
    description = "土地相关命令，用法: land price <卖家ID> <买家ID>"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _parse_int(self, s: str, desc: str) -> Optional[int]:
        try:
            return int(s)
        except ValueError:
            print(f"❌ {desc} 必须为整数: {s}")
            return None

    def execute(self, args: List[str]) -> bool:
        if len(args) != 3 or args[0].lower() != "price":
            print("❌ 用法: land price <卖家ID> <买家ID>")
            return False

        seller_id = self._parse_int(args[1], "卖家ID")
        if seller_id is None:
            return False
        buyer_id = self._parse_int(args[2], "买家ID")
        if buyer_id is None:
            return False

        service = LandTradingService(self.state)
        preview = service.get_trade_preview(seller_id, buyer_id, 1)  # 预览1单位价格
        if not preview:
            print("❌ 无法获取预览信息，请检查人物ID")
            return False

        terms = TerminologyService.get()
        print(f"\n   💰 Land Trade Preview:")
        print(f"      Seller: {preview['seller_name']} (Land: {preview['seller_land_after'] + 1})")
        print(f"      Buyer:  {preview['buyer_name']} (Land: {preview['buyer_land_after'] - 1})")
        print(f"      Price:  {preview['price_per_unit']} Talents/unit")
        print(f"      Example: 5 units = {preview['price_per_unit'] * 5} Talents")
        return True

