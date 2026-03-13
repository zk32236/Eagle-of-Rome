# src/core/entities/player.py
"""
玩家实体，关联派系，用于多人轮流操作。
"""
from typing import Optional, Dict, Any
from enum import Enum


class PlayerType(Enum):
    HUMAN = "human"
    AI = "ai"
    OBSERVER = "observer"


class Player:
    """玩家实体"""

    def __init__(
        self,
        player_id: str,
        faction_id: Optional[str] = None,
        player_type: PlayerType = PlayerType.HUMAN,
        is_online: bool = False,
        connection_id: Optional[str] = None
    ):
        self._player_id = player_id
        self._faction_id = faction_id
        self._player_type = player_type
        self._is_online = is_online
        self._connection_id = connection_id

    # --- 属性访问器 ---
    @property
    def player_id(self) -> str:
        return self._player_id

    @property
    def faction_id(self) -> Optional[str]:
        return self._faction_id

    @property
    def player_type(self) -> PlayerType:
        return self._player_type

    @property
    def is_online(self) -> bool:
        return self._is_online

    @is_online.setter
    def is_online(self, value: bool):
        self._is_online = value

    @property
    def connection_id(self) -> Optional[str]:
        return self._connection_id

    @connection_id.setter
    def connection_id(self, value: Optional[str]):
        self._connection_id = value

    # --- 序列化 ---
    def to_dict(self) -> Dict[str, Any]:
        return {
            "player_id": self._player_id,
            "faction_id": self._faction_id,
            "player_type": self._player_type.value,
            "is_online": self._is_online,
            "connection_id": self._connection_id,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Player":
        return Player(
            player_id=data["player_id"],
            faction_id=data.get("faction_id"),
            player_type=PlayerType(data.get("player_type", "human")),
            is_online=data.get("is_online", False),
            connection_id=data.get("connection_id"),
        )

    def __repr__(self) -> str:
        return f"Player({self._player_id}, faction={self._faction_id}, type={self._player_type.value})"