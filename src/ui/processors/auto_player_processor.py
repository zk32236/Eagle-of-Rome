# src/ui/processors/auto_player_processor.py
import logging
from typing import Optional

from src.core.game_state import GameState
from src.core.entities.entities import Faction
from src.core.deciders.retirement_decider import RetirementDecider


class AutoPlayerProcessor:
    def __init__(self, state: GameState, retirement_decider: RetirementDecider):
        self.state = state
        self.retirement_decider = retirement_decider

    def process_retirement(self, player_id: str, faction: Faction) -> bool:
        """
        执行裁员决策。返回 True 表示执行了淘汰，否则 False。
        内部已捕获异常并记录日志，不会向上抛出。
        """
        try:
            fig_id = self.retirement_decider.decide_whom_to_retire(faction)
            if fig_id is None:
                return False

            figure = self.state.get_member(fig_id)
            if not figure or figure.faction_id != faction.id:
                self.state.log_event(
                    f"[WARNING] 裁员决策返回的人物 {fig_id} 不属于派系 {faction.id}，已忽略",
                    level=logging.WARNING,
                    extra={"function": "process_retirement", "player_id": player_id}
                )
                return False

            # 从派系移除
            faction.remove_member(fig_id)
            # 加入广场
            self.state.curia.add_figure(figure)
            figure.faction_id = None
            figure.is_faction_leader = False
            # 记录操作（用于公示）
            self.state.add_forum_action("retirements", fig_id)
            # 记录日志
            self.state.log_event(
                f"人物被淘汰: {figure.get_formal_name()}",
                level=logging.INFO,
                extra={"figure_id": figure.id}
            )
            # 用户可见提示
            print(f"   🤖 AI {faction.name} 淘汰了 {figure.get_formal_name()}", flush=True)
            return True

        except Exception as e:
            logging.exception(f"裁员环节 AI 决策异常: {e}")
            return False