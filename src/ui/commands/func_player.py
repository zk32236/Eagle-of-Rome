# src/ui/commands/func_player.py
"""
玩家管理命令：显示玩家列表、结束当前玩家回合
"""
from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.api import player_api
from src.core.i18n import i18n

if TYPE_CHECKING:
    from src.core.game_state import GameState


class PlayersCommand(Command):
    """显示所有玩家及当前玩家"""

    name = "players"
    aliases = ["pl"]
    description = "显示所有玩家及当前玩家"

    def execute(self, args: List[str]) -> bool:
        result = player_api.get_players(self.state)
        print(result["message"])
        return result["success"]


class EndTurnCommand(Command):
    """结束当前玩家回合，切换到下一个玩家"""

    name = "end_turn"
    aliases = ["et"]
    description = "结束当前玩家回合，切换到下一个玩家"

    def execute(self, args: List[str]) -> bool:
        player = self.state.get_current_player()
        if not player:
            print(i18n.get("error_no_current_player"))
            return False
        result = player_api.next_player(self.state, player.player_id)
        print(result["message"])
        return result["success"]