# src/core/phases/combat_phase.py

from typing import List, Optional, Dict, Any
from src.core.game_state import GameState
from src.core.localization import TerminologyService, GamePhase
from src.core.entities.legion import LegionStatus


class CombatPhase:
    """
    战斗阶段（Combat Phase）

    核心职责：
    1. 执行所有活跃战争的战斗
    2. CRT战斗结果表查询（第4阶段完善）
    3. 处理战斗结果（凯旋/阵亡/僵持等）
    4. 更新战争状态（胜利/失败/持续）
    """

    def __init__(self):
        self.phase_id = GamePhase.COMBAT

    def execute(self, state: GameState) -> bool:
        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_combat} Phase (Year {abs(state.turn.year)} BC) ---")

        # 获取战争系统
        war_system = state.get_war_system()
        if not war_system:
            print("   ☮️  No war system - phase skipped")
            state.turn.current_phase = "combat"
            return True  # 标记为完成

        # 获取活跃战争
        active_wars = war_system.get_active_wars()

        # 无战争时自动跳过
        if not active_wars:
            print("   ☮️  No active conflicts - phase skipped")
            state.turn.current_phase = "combat"
            return True  # 关键：返回True表示已完成

        # 检查是否有未指派指挥官的战争
        unassigned_wars = [w for w in active_wars if w.commander_id is None]
        if unassigned_wars:
            print(f"   ⚠️  {len(unassigned_wars)} war(s) without commanders!")
            for war in unassigned_wars:
                print(f"      • {war.name}")
            print(f"   💀 Wars continue without leadership...")

        # 只执行已指派指挥官的战争
        assigned_wars = [w for w in active_wars if w.commander_id is not None]
        if not assigned_wars:
            print("   ⏸️  No wars ready for combat")
            state.turn.current_phase = "combat"
            return True

        print(f"\n   ⚔️  Resolving {len(assigned_wars)} active conflict(s)...")

        # 执行每场战争的战斗
        for war in assigned_wars:
            self._resolve_battle(state, war_system, war, terms)

        state.turn.current_phase = "combat"
        return True

    def _resolve_battle(self, state: GameState, war_system, war, terms):
        """执行单场战斗"""
        print(f"\n   🎯 Battle: {war.name}")
        print(f"      Enemy Strength: {war.get_total_strength()}")

        # 检查指挥官
        if war.commander_id is None:
            print(f"      ⚠️  No {terms.commander} assigned!")
            return

        commander = state.get_member(war.commander_id)
        if not commander or commander.is_dead:
            print(f"      💀 {terms.commander} unavailable! War stalls...")
            war_system.recall_commander(war.id)
            return

        # 获取军事系统
        ms = state.get_military_system()

        # 计算军团战力
        legions = ms.get_legions_for_battle(war.id) if ms else []
        legion_count = len(legions)

        # 🆕 严格检查：必须至少1个军团
        if legion_count == 0:
            print(f"      ❌ No {terms.legion}s assigned!")
            war.duration += 1
            return

        # 计算军团战力
        legion_strength = sum(l.get_combat_strength() for l in legions)

        # 计算总战力
        military_bonus = commander.military
        total_force = military_bonus + legion_strength  # 🆕 确保这里定义了

        print(f"      🎖️  {terms.commander}: {commander.name} (Mil: {military_bonus})")
        print(f"      🛡️  Forces: {legion_count} {terms.legion}(s) (+{legion_strength})")

        # 显示军团详情
        for legion in legions:
            vet = "⭐" if legion.is_veteran else ""
            print(f"         • {legion.name}{vet} [Str:{legion.get_combat_strength()}]")

        # 海军加成
        if war.naval_support_required:
            if war.fleets_assigned < war.get_naval_strength_required():
                print(f"      ⚠️  Insufficient fleet!")
                total_force = total_force // 2  # 惩罚
            else:
                fleet_bonus = war.fleets_assigned
                total_force += fleet_bonus
                print(f"      ⚓ {terms.fleet}: {war.fleets_assigned} (+{fleet_bonus})")

        print(f"      ⚔️  Total Force: {total_force} vs Enemy {war.get_total_strength()}")

        # CRT战斗结果
        import random
        dice_roll = random.randint(2, 12)
        combat_total = dice_roll + total_force - war.get_total_strength()  # 使用 total_force

        print(f"\n      🎲 Dice roll: {dice_roll}")
        print(f"      📊 Combat Total: {dice_roll} + {total_force} - {war.get_total_strength()} = {combat_total}")

        # 判定结果
        result = self._simplified_crt(dice_roll, combat_total, war)

        # 应用结果（传递 ms 参数）
        self._apply_battle_result(state, war_system, war, commander, result, terms, ms)

    def _apply_battle_result(self, state: GameState, war_system, war, commander, result: str, terms, ms):
        """应用战斗结果（修复：先处理军团，再结束战争）"""
        result_emojis = {
            "TRIUMPH": "🏆",
            "VICTORY": "✅",
            "STALEMATE": "⏸️",
            "DEFEAT": "❌",
            "DISASTER": "💀",
        }

        emoji = result_emojis.get(result, "❓")
        print(f"\n      {emoji} RESULT: {result}")

        # 🆕 先获取军团列表（在战争结束前）
        legions_for_battle = ms.get_legions_for_battle(war.id) if ms else []

        if result == "TRIUMPH":
            print(f"      🎉 {terms.triumph}! {commander.name} returns in glory!")
            commander.influence += 10

            # 🆕 先处理军团（晋升+召回）
            for legion in legions_for_battle:
                legion.promote_to_veteran()
                legion.recall()
                print(f"      🏆 {legion.name} returns in triumph!")

            # 然后结束战争
            war_system.resolve_war(war.id, victory=True)

        elif result == "VICTORY":
            print(f"      ✓ Victory! {war.name} concluded successfully.")
            commander.influence += 5

            # 🆕 先处理军团
            for legion in legions_for_battle:
                legion.promote_to_veteran()
                legion.recall()
                print(f"      🏆 {legion.name} returns in triumph!")

            # 然后结束战争
            war_system.resolve_war(war.id, victory=True)

            # 然后召回军团
            if ms:
                for legion in ms.get_legions_for_battle(war.id):
                    legion.promote_to_veteran()
                    legion.recall()
                    print(f"      🏆 {legion.name} returns in triumph!")

        elif result == "STALEMATE":
            print(f"      ⏳ Stalemate. War continues...")
            # 僵持：军团留在战场，不召回
            war.duration += 1

        elif result == "DEFEAT":
            print(f"      💔 Defeat! Forces scattered.")

            # 失败：军团损失部分，将领可能伤亡
            if ms:
                legions = ms.get_legions_for_battle(war.id)
                losses = max(1, len(legions) // 2)  # 损失一半
                for i, legion in enumerate(legions):
                    if i < losses:
                        legion.status = LegionStatus.DISBANDED
                        legion.recall()
                        print(f"      💀 {legion.name} destroyed!")
                    else:
                        # 幸存者留在战场
                        print(f"      ⏳ {legion.name} remains")

            # 将领伤亡处理
            import random
            roll = random.random()
            if roll < 0.3:
                war.report_commander_casualty("fled", state.turn.turn_number)
                print(f"      🏃 {commander.name} fled!")
            elif roll < 0.5:
                war.report_commander_casualty("captured", state.turn.turn_number)
                print(f"      🔒 {commander.name} captured!")
            else:
                war.report_commander_casualty("wounded", state.turn.turn_number)
                print(f"      🚑 {commander.name} wounded")

            war.commander_id = None
            war.duration += 1

        elif result == "DISASTER":
            print(f"      🔥 DISASTER! Catastrophic defeat!")

            # 灾难：全军覆没
            if ms:
                for legion in ms.get_legions_for_battle(war.id):
                    legion.status = LegionStatus.DISBANDED
                    legion.recall()
                    print(f"      💀 {legion.name} destroyed!")

            # 将领阵亡
            commander.is_dead = True
            commander.is_leader = False
            if commander.id in state.turn.leader_ids:
                state.turn.leader_ids.remove(commander.id)

            war.report_commander_casualty("killed", state.turn.turn_number)
            war.commander_id = None
            war.legions_assigned = 0
            war.fleets_assigned = 0

            print(f"      ⚰️  {commander.name} falls in battle!")
            state.log_event(f"💀 Disaster at {war.name}: {commander.name} killed")

            war.duration += 1

    def _simplified_crt(self, dice_roll: int, combat_total: int, war) -> str:
        """简化版CRT判定（第4阶段替换）"""
        # 灾难判定
        if war.is_disaster_roll(dice_roll):
            return "DISASTER"
        # 大胜判定
        elif combat_total >= 12:
            return "TRIUMPH"
        # 胜利判定
        elif combat_total >= 6:
            return "VICTORY"
        # 僵持判定
        elif war.is_standoff_roll(dice_roll) or -3 <= combat_total < 6:
            return "STALEMATE"
        # 失败判定
        elif combat_total < -3:
            return "DEFEAT"
        else:
            return "STALEMATE"

