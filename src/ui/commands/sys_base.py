# src/ui/commands/sys_base.py
"""
命令抽象基类 - 所有命令必须继承并实现

设计原则:
- 类属性声明必选配置（元数据）
- 实例属性仅接收state（无状态化）
- execute方法接收原始参数列表（统一接口）
"""

from abc import ABC, abstractmethod
from typing import List, ClassVar, TYPE_CHECKING
from src.core.entities.player import PlayerType

if TYPE_CHECKING:
    from src.core.game_state import GameState


class Command(ABC):
    """
    命令抽象基类

    所有命令必须继承此类并实现:
    - name: 主命令名
    - aliases: 别名列表
    - description: 帮助文本
    - execute(): 命令执行逻辑
    """

    # === 必选类属性（元数据）===
    name: ClassVar[str]  # 主命令名，如 "help"
    aliases: ClassVar[List[str]]  # 别名列表，如 ["h"]
    description: ClassVar[str]  # 帮助文本，如 "Show this help message"

    def __init__(self, state: "GameState"):
        """
        初始化命令实例

        Args:
            state: 游戏状态实例（可能为None，由具体命令决定是否允许）
        """
        self.state = state

    @abstractmethod
    def execute(self, args: List[str]) -> bool:
        """
        执行命令

        Args:
            args: 命令参数字符串列表（已去除命令名本身）
                 如输入 "trade land 1 2 5" -> args=["1", "2", "5"]

        Returns:
            bool: True表示执行成功，False表示执行失败（业务逻辑失败）
                  异常应在方法内捕获，不向上抛出
        """
        pass

    # ==================== 新增：多玩家信息隔离相关方法 ====================

    def _is_auto_mode(self) -> bool:
        """判断是否处于自动模式（任何阶段的自动开关为 True）"""
        return (self.state.config.get("testing.auto_forum", False) or
                self.state.config.get("testing.auto_population", False) or
                self.state.config.get("testing.auto_senate", False))

    def _show_current_player_overview(self):
        # 优先使用子类自动模式标志（如果存在）
        if hasattr(self, '_auto_mode') and self._auto_mode:
            return

        player = self.state.get_current_player()
        if not player or player.player_type != PlayerType.HUMAN:
            return

        faction = self.state.get_faction(player.faction_id)
        if not faction:
            return

        from src.ui.utils import clear_screen
        clear_screen()

        # 显示玩家标识
        year_display = self.state.turn.get_year_display() if self.state.turn else "未知"
        print(f"===== 玩家 {player.player_id} ({faction.name}) 回合 =====")
        print(f"年份: {year_display}\n")

        # 显示派系金库
        print(f"💰 派系金库: {faction.treasury} 塔兰特")

        # 显示派系存活人物
        from src.api import figure_api
        result = figure_api.get_figure_info(self.state)
        if result["success"]:
            members = [f for f in result["data"]
                       if f["faction_id"] == faction.id and not f.get("is_dead", False)]
            if members:
                print("\n👥 派系人物：")
                for m in members:
                    status = "👑" if m.get("is_faction_leader") else "🟢"
                    tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(m["class_tier"], "❓")
                    print(f" {status}{tier_emoji} ID:{m['id']:<3} {m['name']:<25} "
                          f"影响力:{m['influence']} 财富:{m['wealth']} 人气:{m['popularity']}")

        # 显示阶段进度
        executed = len(self.state.executed_phases)
        total = len(("mortality", "revenue", "forum", "population", "senate", "combat", "resolution"))
        print(f"\n📋 阶段进度: {executed}/{total}")
        print("-" * 50)

    def _wait_for_pin(self):
        """等待玩家输入 PIN（可为空），仅手动模式且人类玩家时生效"""
        if hasattr(self, '_auto_mode') and self._auto_mode:
            return

        player = self.state.get_current_player()
        if not player or player.player_type != PlayerType.HUMAN:
            return

        print("\n🔐 请输入您的 PIN 码（直接回车跳过）: ", end="", flush=True)
        pin = input().strip()
        if pin:
            pass

    def _switch_to_next_player(self) -> bool:

        # 优先使用子类维护的玩家列表（如果有）
        if hasattr(self, '_players') and hasattr(self, '_current_player_index'):

            if not self._players:
                return False
            next_index = self._current_player_index + 1

            if next_index >= len(self._players):
                return False
            next_id = self._players[next_index]

            self._current_player_index = next_index
            player = self.state.get_player(next_id)
            if player:
                self.state.set_current_player(next_id)

            self._wait_for_pin()
            self._show_current_player_overview()
            return True
        else:
            # 回退到 state 的玩家顺序（用于未维护索引的阶段）

            current = self.state.get_current_player()
            next_id = self.state.next_player()
            if next_id and next_id != current.player_id:

                self._wait_for_pin()
                self._show_current_player_overview()
                return True
            return False