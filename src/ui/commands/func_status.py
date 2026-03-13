# src/ui/commands/func_status.py (改造后)
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.figure import ClassTier
from src.core.entities.contract import ContractType
from typing import List, Optional, TYPE_CHECKING
import src.api.game_api as game_api
import src.api.figure_api as figure_api
import src.api.faction_api as faction_api
import src.api.province_api as province_api

if TYPE_CHECKING:
    from src.core.game_state import GameState

# ===== StatusCommand =====
class StatusCommand(Command):
    name = "status"
    aliases = ["sts"]
    description = "显示当前游戏状态摘要（国库、人物数等）"

    def execute(self, args: List[str]) -> bool:
        result = game_api.get_status_summary(self.state)
        if result["success"]:
            print(result["message"])
        else:
            print(f"❌ {result['message']}")
            if result["errors"]:
                for err in result["errors"]:
                    print(f"   {err}")
        return result["success"]

# ===== StatusPublicLandCommand =====
class StatusPublicLandCommand(Command):
    name = "status_public_land"
    aliases = ["spl"]
    description = "显示国家公地信息"

    def execute(self, args: List[str]) -> bool:
        result = game_api.get_public_land_info(self.state)
        print(result["message"])
        return result["success"]

# ===== StatusPrivateLandCommand =====
class StatusPrivateLandCommand(Command):
    name = "status_private_land"
    aliases = ["spr"]
    description = "显示所有存活人物的私地信息"

    def execute(self, args: List[str]) -> bool:
        result = figure_api.get_private_land_info(self.state)
        print(result["message"])
        return result["success"]

# ===== StatusFigureCommand =====
class StatusFigureCommand(Command):
    name = "status_figure"
    aliases = ["sf"]
    description = "显示人物详细信息，用法: status_figure [人物ID]（不指定ID则显示所有存活人物）"

    def execute(self, args: List[str]) -> bool:
        if args:
            try:
                figure_id = int(args[0])
                result = figure_api.get_figure_info(self.state, figure_id)
            except ValueError:
                print("❌ 人物ID必须为整数")
                return False
        else:
            result = figure_api.get_figure_info(self.state)
        print(result["message"])
        return result["success"]

# ===== FactionStatusCommand =====
class FactionStatusCommand(Command):
    name = "factions"
    aliases = ["fs"]
    description = "显示所有派系状态（金库、成员数、总影响力）"

    def execute(self, args: List[str]) -> bool:
        result = faction_api.get_factions_status(self.state)
        print(result["message"])
        return result["success"]

# ===== ProvinceCommand =====
class ProvinceCommand(Command):
    name = "province"
    aliases = ["prov"]
    description = "显示行省状态，用法: province [行省ID] (不指定ID则显示所有行省概要)"

    def execute(self, args: List[str]) -> bool:
        if args:
            try:
                pid = int(args[0])
                result = province_api.get_province_info(self.state, pid)
            except ValueError:
                print(f"❌ 无效的行省ID: {args[0]}，必须为整数")
                return False
        else:
            result = province_api.get_province_info(self.state)
        print(result["message"])
        return result["success"]

# 进度条函数保留（如果有其他地方用到）
def get_progress_bar(state, width=7):
    executed = len(state.executed_phases)
    total = 7
    filled = "▓" * executed
    empty = "░" * (total - executed)
    return f"[{filled}{empty}] {executed}/{total}"