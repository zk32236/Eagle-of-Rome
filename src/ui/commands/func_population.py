# src/ui/commands/func_population.py
"""
Population 功能命令：举办庆典，消耗个人财富增加人气
"""

from typing import List, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.entities.figure import Figure

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.entities import Faction


class FestivalCommand(Command):
    """举办庆典，消耗个人财富增加人气"""

    name = "festival"
    aliases = []
    description = "举办庆典，消耗个人财富增加人气，用法: festival <人物ID> <金额>"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _get_player_faction(self) -> Optional["Faction"]:
        """获取玩家派系"""
        for faction in self.state.factions.values():
            if faction.is_player:
                return faction
        return None

    def execute(self, args: List[str]) -> bool:
        """
        执行 festival 命令
        """
        # 参数个数检查
        if len(args) != 2:
            print("❌ 用法: festival <人物ID> <金额>")
            return False

        # 转换参数
        try:
            figure_id = int(args[0])
            amount = int(args[1])
        except ValueError:
            print(f"❌ 无效的参数，人物ID和金额必须为整数")
            return False

        if amount <= 0:
            print("❌ 金额必须为正数")
            return False

        # 获取人物
        figure = self.state.get_member(figure_id)
        if not figure or figure.is_dead:
            print(f"❌ 人物 {figure_id} 不存在或已死亡")
            return False

        # 获取玩家派系
        player_faction = self._get_player_faction()
        if not player_faction:
            print("❌ 没有玩家派系")
            return False

        # 检查人物是否属于玩家派系
        if figure.faction_id != player_faction.id:
            print(f"❌ {figure.get_formal_name()} 不属于你的派系")
            return False

        # 检查财富是否足够
        if figure.wealth < amount:
            print(f"❌ {figure.get_formal_name()} 财富不足，当前 {figure.wealth} < {amount}")
            return False

        # 执行庆典：扣除财富，增加人气
        figure.wealth -= amount
        figure.add_popularity(amount)  # 人气增加量与花费相同

        # 打印成功信息
        print(f"🎉 {figure.get_formal_name()} 举办了一场庆典！")
        print(f"   花费 {amount} 个人资金")
        print(f"   获得 {amount} 人气")
        print(f"   当前: 人气 {figure.popularity}, 财富 {figure.wealth}")

        return True