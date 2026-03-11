import logging
from src.core.deciders.fleet_disband_decider import FleetDisbandDecider
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.game_state import GameState
from src.core.entities.war import WarStatus


class AutoFleetDisbandDecider(FleetDisbandDecider):
    """自动舰队解散决策器：当没有任何需要海战的战争时，解散所有可用或闲置舰队"""

    def should_disband_fleet(self, fleet: Fleet, state: GameState) -> bool:
        # 只考虑 AVAILABLE 或 ON_MISSION 的舰队（不包括建造中的）
        if fleet.status not in (FleetStatus.AVAILABLE, FleetStatus.ON_MISSION) or fleet.is_building:
            return False

        # 检查是否有需要海战的活跃战争或威胁战争
        war_system = state.get_war_system()
        if not war_system:
            return False

        has_naval_war = False
        for war in war_system.get_active_wars():
            if war.naval_required:
                has_naval_war = True
                break
        if not has_naval_war:
            for war in war_system._threats:
                if war.naval_required:
                    has_naval_war = True
                    break

        # 如果没有任何需要海战的战争，则解散舰队
        return not has_naval_war