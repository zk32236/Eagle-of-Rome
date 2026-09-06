#src/core/deciders/impl/
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

        # R3-G-02（设计 §2.4 锚点，FROZEN）：多战退役窄修——对有 `_target_war_id` 且该
        # target 已 RESOLVED 的 released AVAILABLE survivor，在 Population 决策先返回退役；
        # 否则 A 舰会被仍 ACTIVE 的 B 战保留（既有全局「任何战争需海军即阻止退休」），
        # 既违反 next Population 退休又不允许跨战复用（R-12 单战专属），舰队将永久滞留
        # AVAILABLE 持续计费。不扩大到 missing target / 所有 TRUCE 的新处置。
        # （getattr 防御：autospec mock / legacy 舰队无 _target_war_id → None → 既有决策）
        target_war_id = getattr(fleet, "_target_war_id", None)
        if fleet.status == FleetStatus.AVAILABLE and target_war_id is not None:
            target_war = war_system.get_war_by_id(target_war_id)
            if target_war is not None and getattr(target_war, "status", None) == WarStatus.RESOLVED:
                return True

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