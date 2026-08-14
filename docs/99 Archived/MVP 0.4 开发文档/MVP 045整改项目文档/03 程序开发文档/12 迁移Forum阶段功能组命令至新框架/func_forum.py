# src/ui/commands/func_forum.py
"""
Forum 功能命令：说服 Curia 中的人物加入玩家派系
"""

from typing import List, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.entities.figure import Figure

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.entities import Faction


class PersuadeCommand(Command):
    """说服 Curia 中的指定人物加入你的派系"""

    name = "persuade"
    aliases = []
    description = "说服 Curia 中的指定人物加入你的派系，用法: persuade <人物ID>"

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
        执行 persuade 命令
        """
        # 参数检查
        if len(args) != 1:
            print("❌ 用法: persuade <人物ID>")
            return False

        # 转换 ID
        try:
            figure_id = int(args[0])
        except ValueError:
            print(f"❌ 无效的人物ID: {args[0]}，必须为整数")
            return False

        # 从 Curia 中移除人物
        figure = self.state.curia.remove_figure(figure_id)
        if figure is None:
            print(f"❌ 人物 {figure_id} 不在 Curia 中")
            return False

        # 获取玩家派系
        player_faction = self._get_player_faction()
        if not player_faction:
            print("❌ 没有玩家派系，无法招募")
            # 将人物放回 Curia
            self.state.curia.add_figure(figure)
            return False

        # 将人物加入玩家派系
        figure.faction_id = player_faction.id
        if figure.id not in player_faction.member_ids:
            player_faction.member_ids.append(figure.id)

        # 打印成功信息
        print(f"✅ {figure.get_formal_name()} 加入 {player_faction.name}！")
        return True