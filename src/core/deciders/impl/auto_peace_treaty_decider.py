#src/core/deciders/impl/
import math
from typing import Optional, Dict
from src.core.deciders.peace_treaty_decider import PeaceTreatyDecider
from src.core.entities.war import War
from src.core.game_state import GameState

class AutoPeaceTreatyDecider(PeaceTreatyDecider):
    """自动停战草案生成决策器，根据配置和战争属性计算赔款额"""

    def decide_treaty(self, war: War, battle_result: str, state: GameState) -> Optional[Dict]:
        # 只有 VICTORY, DEFEAT, STALEMATE 才会生成草案
        if battle_result not in ('VICTORY', 'DEFEAT', 'STALEMATE'):
            return None

        # 读取配置
        config = state.config.get("combat_rules.peace_treaty", {})
        base_multiplier = config.get("indemnity_base_multiplier", 10)
        duration_multiplier = config.get("indemnity_duration_multiplier", 5)
        duration_victory = config.get("duration_victory", 5)
        duration_stalemate = config.get("duration_stalemate", 3)

        # 基础赔款额 = 战争基础强度 × 乘数 + 战争持续时间 × 乘数
        base = war.strength * base_multiplier
        duration_part = war.duration * duration_multiplier
        raw_indemnity = base + duration_part

        # 根据结果调整正负号
        if battle_result == 'VICTORY':
            indemnity = raw_indemnity          # 敌方赔给我方（正）
            duration = duration_victory
        elif battle_result == 'DEFEAT':
            indemnity = -raw_indemnity         # 我方赔给敌方（负）
            duration = duration_victory
        else:  # STALEMATE
            indemnity = 0                      # 无赔款
            duration = duration_stalemate

        return {
            'indemnity': indemnity,
            'duration': duration,
            'generated_turn': state.turn.turn_number
        }