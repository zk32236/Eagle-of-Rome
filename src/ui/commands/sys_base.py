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