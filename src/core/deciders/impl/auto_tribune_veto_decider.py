import random
import logging
from typing import Any
from src.core.deciders.tribune_veto_decider import TribuneVetoDecider
from src.core.game_state import GameState


class AutoTribuneVetoDecider(TribuneVetoDecider):
    """自动随机否决决策器：根据配置的概率随机决定"""

    def decide_veto(self, issue: Any, tribune_id: int, state: GameState) -> bool:

        print(f"DEBUG: 保民官决策器收到议题: {issue}, 类型: {type(issue)}")
        if isinstance(issue, dict):
            print(f"      议题内容: type={issue.get('type')}, war_id={issue.get('war_id')}")

        chance = state.config.get("political_rules.tribune_veto_chance", 0.2)
        random_val = random.random()
        result = random_val < chance

        if state:
            state.log_event(
                f"保民官否决决策: 议题 {type(issue).__name__} ID {getattr(issue, 'id', '?')} 概率 {chance} 随机值 {random_val:.3f} 结果 {result}",
                level=logging.DEBUG,
                extra={
                    "issue_type": type(issue).__name__,
                    "tribune_id": tribune_id,
                    "chance": chance,
                    "random": random_val,
                    "result": result
                }
            )
        return result