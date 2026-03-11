import random
import logging
from src.core.deciders.war_takeover_decider import WarTakeoverDecider
from src.core.entities.war import War
from src.core.entities.figure import Figure
from src.core.game_state import GameState


class AutoWarTakeoverDecider(WarTakeoverDecider):
    """自动战争接管决策器：根据配置的概率随机决定"""

    def decide_takeover(self, war: War, new_consul: Figure, old_commander: Figure, state: GameState) -> bool:
        # 新增：记录输入（已有日志但可调整前缀）
        if war.rebellion_province_id is not None:
            if state:
                state.log_event(
                    f"[DEBUG] WarTakeoverDecider: 战争 {war.name} 是起义战争，执政官不接管",
                    level=logging.DEBUG,
                    extra={"war_id": war.id, "result": False}
                )
            return False

        if old_commander and new_consul.id == old_commander.id:
            return False

        chance = state.config.get("combat_rules.war_takeover_chance", 1.0)
        random_val = random.random()
        result = random_val < chance

        if state:
            war_name = getattr(war, 'name', '未知战争') if war else '无'
            new_consul_name = getattr(new_consul, 'name', '未知执政官') if new_consul else '无'
            old_commander_name = getattr(old_commander, 'name', '无') if old_commander else '无'

            state.log_event(
                f"[DEBUG] WarTakeoverDecider: 战争 {war_name} 新执政官 {new_consul_name} 旧指挥官 {old_commander_name} 概率 {chance} 随机值 {random_val:.3f} 接管 {result}",
                level=logging.DEBUG,
                extra={
                    "war_id": getattr(war, 'id', None) if war else None,
                    "new_consul_id": getattr(new_consul, 'id', None) if new_consul else None,
                    "old_commander_id": getattr(old_commander, 'id', None) if old_commander else None,
                    "chance": chance,
                    "random": random_val,
                    "result": result
                }
            )
        return result