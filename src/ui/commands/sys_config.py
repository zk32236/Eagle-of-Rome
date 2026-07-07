# src/ui/commands/sys_config.py
"""
系统配置命令 - 术语切换和配置重载
"""

from typing import List, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService

if TYPE_CHECKING:
    from src.core.game_state import GameState


class TermsCommand(Command):
    """切换术语预设命令"""

    name = "terms"
    aliases = []  # 原基线无别名，保持
    description = "切换术语预设，用法: terms [preset] (预设: original/historical_roman/generic_latin/chinese_historical)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def _get_current_preset_name(self) -> str:
        """
        获取当前术语预设的名称
        通过比较 _current 对象与 PRESETS 中的实例来确定
        """
        current = TerminologyService._current
        for name, preset in TerminologyService.PRESETS.items():
            if current is preset:  # 同一实例
                return name
        return "custom"  # 自定义或未知

    def execute(self, args: List[str]) -> bool:
        """
        执行 terms 命令
        - 无参数：显示当前预设和可用列表
        - 有参数：尝试切换预设
        """
        if not args:
            # 显示当前预设和可用列表
            current_name = self._get_current_preset_name()
            current = TerminologyService.get()
            print(f"📝 当前术语预设: {current_name}")
            print(f"   例如: {current.assembly}/{current.nobles}/{current.currency}")
            print("\n可用预设:")
            for preset_name in TerminologyService.PRESETS.keys():
                print(f"  - {preset_name}")
            return True

        preset = args[0].lower()
        success = TerminologyService.set_preset(preset)
        if success:
            new_terms = TerminologyService.get()
            print(f"✅ 已切换至: {preset}")
            print(f"   现在使用: {new_terms.assembly}/{new_terms.nobles}/{new_terms.currency}")
        else:
            print(f"❌ 未知预设: {preset}")
            print("可用预设: " + ", ".join(TerminologyService.PRESETS.keys()))
        return success


class ReloadCommand(Command):
    """重新加载配置文件命令"""

    name = "reload"
    aliases = []
    description = "重新加载配置文件 (data/config/game_config.json)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """
        执行 reload 命令
        调用 state.config.reload() 并打印结果
        """
        if not self.state or not hasattr(self.state, 'config') or self.state.config is None:
            print("❌ 游戏状态未初始化或配置不可用")
            return False

        success = self.state.config.reload()
        if success:
            print("✅ 配置重载成功")
            # 可选显示部分更新后的配置项，原基线仅打印成功信息
        else:
            print("⚠️ 配置重载失败，保持原配置")
        return success