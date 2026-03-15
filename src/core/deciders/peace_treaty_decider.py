#src/core/deciders/
from abc import ABC, abstractmethod
from typing import Optional, Dict
from src.core.entities.war import War
from src.core.game_state import GameState

class PeaceTreatyDecider(ABC):
    """停战草案生成决策器接口"""

    @abstractmethod
    def decide_treaty(self, war: War, battle_result: str, state: GameState) -> Optional[Dict]:
        """
        根据战斗结果返回草案字典，或 None（表示不生成草案）。

        草案字典必须包含：
        - indemnity: int  赔款额（正数表示敌方付给我方，负数表示我方付给敌方）
        - duration: int   和约有效期（回合数）
        - generated_turn: int  生成时的回合数

        Args:
            war: 当前战争实体
            battle_result: 战斗结果字符串，可能取值：
                'VICTORY', 'DEFEAT', 'STALEMATE', 'TRIUMPH', 'DISASTER'
            state: 游戏状态，用于读取配置

        Returns:
            Optional[Dict] 草案字典，如果不生成则返回 None
        """
        pass