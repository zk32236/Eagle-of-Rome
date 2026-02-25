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


class SeatsCommand(Command):
    """显示席位占比分布"""

    name = "seats"
    aliases = []
    description = "显示席位占比分布（全国资产、个人席位、派系席位）"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        terms = TerminologyService.get()
        print(f"\n{'=' * 60}")
        print(f"   📊 Senate Seat Distribution (Total 300 seats)")
        print(f"{'=' * 60}")

        all_figures = [m for m in self.state.get_living_members() if not m.is_dead]
        total_land = sum(m.land_private for m in all_figures)
        total_veterans = sum(m.veterans for m in all_figures)
        total_assets = total_land + total_veterans

        if total_assets == 0:
            print("   No land or veterans to distribute seats")
            return True

        print(f"\n   📈 National Total: Land={total_land}, Veterans={total_veterans}")
        print(f"   🏛️  Seat Calculation: (Personal Assets / {total_assets}) × 300\n")

        # 按个人资产排序
        sorted_figures = sorted(all_figures, key=lambda m: m.get_seat_share(), reverse=True)[:15]

        print(f"   {'Rank':<4} {'Name':<22} {'Faction':<12} {'Assets':<6} {'Seats':<6} {'%':<5}")
        print(f"   {'-' * 60}")

        for idx, fig in enumerate(sorted_figures, 1):
            faction = self.state.get_faction(fig.faction_id)
            fname = faction.name[:10] if faction else "Unknown"
            assets = fig.get_seat_share()  # 直接使用 get_seat_share()
            seat_count = int((assets / total_assets) * 300) if total_assets > 0 else 0
            seat_pct = (assets / total_assets) * 100 if total_assets > 0 else 0
            tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(fig.class_tier.value, "❓")
            print(f"   {idx:<4} {tier_emoji} {fig.name[:18]:<20} {fname:<12} "
                  f"{assets:<6} {seat_count:<6} {seat_pct:4.1f}%")

        # 派系总计
        print(f"\n   🏛️  Faction Seat Distribution:")
        print(f"   {'Faction':<15} {'Land':<6} {'Vets':<6} {'Assets':<8} {'Seats':<8} {'%':<6}")
        print(f"   {'-' * 60}")

        total_faction_seats = 0
        for faction in self.state.factions.values():
            members = faction.get_members(self.state)
            fact_land = sum(m.land_private for m in members)
            fact_vets = sum(m.veterans for m in members)
            fact_assets = fact_land + fact_vets
            fact_seats = int((fact_assets / total_assets) * 300) if total_assets > 0 else 0
            total_faction_seats += fact_seats
            seat_pct = (fact_assets / total_assets) * 100 if total_assets > 0 else 0
            print(f"   {faction.name:<15} {fact_land:<6} {fact_vets:<6} "
                  f"{fact_assets:<8} {fact_seats:<8} {seat_pct:5.1f}%")

        print(f"\n   {'TOTAL':<15} {total_land:<6} {total_veterans:<6} "
              f"{total_assets:<8} {total_faction_seats:<8} 100.0%")
        print(f"{'=' * 60}")
        return True