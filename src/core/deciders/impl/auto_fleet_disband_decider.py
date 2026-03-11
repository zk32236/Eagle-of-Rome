import logging
from src.core.deciders.fleet_disband_decider import FleetDisbandDecider
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.game_state import GameState
from src.core.entities.war import WarStatus

class AutoFleetDisbandDecider(FleetDisbandDecider):
    """自动舰队解散决策器：仅当没有任何需要海战的战争（包括停战草案未批准的战争）时，解散所有可用或闲置舰队"""

    def should_disband_fleet(self, fleet: Fleet, state: GameState) -> bool:
        # 只考虑 AVAILABLE 或 ON_MISSION 的舰队（不包括建造中的）
        if fleet.status not in (FleetStatus.AVAILABLE, FleetStatus.ON_MISSION) or fleet.is_building:
            return False

        war_system = state.get_war_system()
        if not war_system:
            return False

        # 定义判断战争是否需要海战的内部函数
        def war_needs_naval(war):
            if not war.naval_required:
                return False
            if war.status == WarStatus.ACTIVE:
                return True
            if war.status == WarStatus.THREAT:
                return True
            if war.status == WarStatus.TRUCE:
                # 停战战争中，仅当草案已批准时才不需要保留舰队，否则未来可能恢复
                treaty = war.peace_treaty
                if treaty and treaty.get('status') == 'approved':
                    return False
                else:
                    return True
            return False

        # 检查所有可能影响舰队需求的战争（使用公开方法）
        for war in war_system.get_active_wars():
            if war_needs_naval(war):
                return False
        for war in war_system.get_threat_wars():
            if war_needs_naval(war):
                return False
        for war in war_system.get_truce_wars():
            if war_needs_naval(war):
                return False

        # 没有需要海战的战争，可以解散
        return True