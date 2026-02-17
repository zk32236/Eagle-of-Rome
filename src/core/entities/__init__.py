# src/core/entities/__init__.py

from core.entities.entities import Senator, Faction, GameTurn
from core.entities.war import War, WarStatus, WarType
from core.entities.legion import Legion, LegionStatus  # 新增
from .figure import Figure, ClassTier
from .curia import Curia
from .contract import Contract, ContractType, ContractStatus  # 新增

__all__ = ['Senator', 'Faction', 'GameTurn',
           'War', 'WarStatus', 'WarType',
           'Legion', 'LegionStatus']  # 新增