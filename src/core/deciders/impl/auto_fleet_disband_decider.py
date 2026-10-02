#src/core/deciders/impl/
import logging
from src.core.deciders.fleet_disband_decider import FleetDisbandDecider
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.game_state import GameState
from src.core.entities.war import WarStatus

class AutoFleetDisbandDecider(FleetDisbandDecider):
    """自动舰队解散决策器（WP-L L2 / FC-L2-05/06/07/08，FROZEN）。

    L2 收窄（ODR-L-08）：仅移除「无相关海战战争（战争未爆发）」这一 terminal 自动解散；
    **保留** approved-TRUCE（战争未 RESOLVED）退役（现状行为）与 resolved-target（战争结束）
    退役；战争结束召回 + 战斗 DESTROYED 语义不变。

    决策顺序（D2.5，冻结）：
      (i)   resolved-target（AVAILABLE + 该舰队 target 战 RESOLVED）→ 退役；
      (ii)  任一 naval_required 战争处于 ACTIVE/THREAT 或 TRUCE-未批准 → 保留；
      (iii) 任一 naval_required approved-TRUCE 战争 → 退役；
      (iv)  否则（无相关海战战争 / 战争未爆发）→ 保留（L2-T2 移除自动解散）。
    """

    def should_disband_fleet(self, fleet: Fleet, state: GameState) -> bool:
        # 只考虑 AVAILABLE 或 ON_MISSION 的舰队（不包括建造中的）
        if fleet.status not in (FleetStatus.AVAILABLE, FleetStatus.ON_MISSION) or fleet.is_building:
            return False

        war_system = state.get_war_system()
        if not war_system:
            return False

        # (i) R3-G-02 多战退役窄修（FROZEN，保留）：对有 `_target_war_id` 且该 target 已
        # RESOLVED 的 released AVAILABLE survivor，在 Population 决策先返回退役；否则 A 舰会被
        # 仍 ACTIVE 的 B 战保留（既有全局「任何战争需海军即阻止退休」），违反 next Population 退休
        # 且不允许跨战复用（R-12 单战专属），舰队将永久滞留 AVAILABLE 持续计费。
        # （getattr 防御：autospec mock / legacy 舰队无 _target_war_id → None → 既有决策）
        target_war_id = getattr(fleet, "_target_war_id", None)
        if fleet.status == FleetStatus.AVAILABLE and target_war_id is not None:
            target_war = war_system.get_war_by_id(target_war_id)
            if target_war is not None and getattr(target_war, "status", None) == WarStatus.RESOLVED:
                return True

        # (ii)/(iii) 扫描所有相关战争（ACTIVE / THREAT / TRUCE 容器互斥，去重）
        has_approved_truce = False
        relevant_wars = (
            list(war_system.get_active_wars())
            + list(war_system.get_threat_wars())
            + list(war_system.get_truce_wars())
        )
        for war in relevant_wars:
            if not getattr(war, "naval_required", False):
                continue
            status = getattr(war, "status", None)
            if status in (WarStatus.ACTIVE, WarStatus.THREAT):
                # (ii) 有需要海战的活跃/威胁战争 → 保留
                return False
            if status == WarStatus.TRUCE:
                treaty = war.peace_treaty
                if treaty and treaty.get('status') == 'approved':
                    # (iii) approved-TRUCE（战争未 RESOLVED）→ 退役（保留现状行为，ODR-L-08）
                    has_approved_truce = True
                else:
                    # 未批准/待表决停战 → 保留（未来可能恢复）
                    return False

        if has_approved_truce:
            return True

        # (iv) 无相关海战战争（战争未爆发）→ 保留（L2-T2 移除 terminal 自动解散；
        # 舰队保持 maintenance-bearing，FC-L2-01/05）
        return False
