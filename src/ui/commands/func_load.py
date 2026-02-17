# src/ui/commands/func_load.py
"""
Load命令 - 加载游戏场景
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.scenario_loader import ScenarioLoader

if TYPE_CHECKING:
    from core.game_state import GameState


class LoadCommand(Command):
    """加载游戏场景命令"""

    name = "load"
    aliases = ["l"]
    description = "加载场景 (默认: mvp_test.json)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """
        执行load命令

        Args:
            args: 命令参数，可指定场景文件名，默认为 "mvp_test.json"

        Returns:
            bool: 加载成功返回 True，失败返回 False
        """
        # 解析场景文件名（支持参数）
        scenario_file = args[0] if args else "mvp_test.json"

        try:
            # 调用 ScenarioLoader，传入当前游戏状态和场景文件名
            ScenarioLoader.load_scenario(self.state, scenario_file)

            # 获取加载后的人物数量
            living_count = len(self.state.get_living_members())

            print(f"\n✅ 场景加载成功: {scenario_file}")
            print(f"   国库: {self.state.treasury} 塔兰特")
            print(f"   存活人物: {living_count}")

            return True

        except FileNotFoundError as e:
            print(f"\n❌ 场景文件不存在: {scenario_file}")
            print(f"   错误信息: {e}")
            return False

        except Exception as e:
            print(f"\n❌ 场景加载失败: {e}")
            import traceback
            traceback.print_exc()
            return False