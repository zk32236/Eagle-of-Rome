# src/ui/commands/phase_combat.py
"""
战斗阶段命令 - 处理所有活跃战争的战斗
"""

import random
from typing import List, Optional, TYPE_CHECKING

from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.war import WarStatus
from src.core.entities.legion import LegionStatus
from src.ui.commands.func_status import get_progress_bar   # 新增

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.war import War



class CombatCommand(Command):
    """战斗阶段命令"""

    name = "combat"
    aliases = ["c"]
    description = "执行战斗阶段 (Combat Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        """
        执行战斗阶段
        """
        if not self.state.is_phase_executed("senate"):
            print("⚠️ 必须先执行元老院阶段 (senate)")
            return False

        # 检查阶段是否已执行
        if self.state.is_phase_executed("combat"):
            print("⚠️ 战斗阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_combat} Phase (Year {abs(self.state.turn.year)} BC) ---")

        # 获取战争系统
        war_system = self.state.get_war_system()
        if not war_system:
            print("   ☮️  No war system - phase skipped")
            self.state.mark_phase_executed("combat")
            return True

        # 获取活跃战争
        active_wars = war_system.get_active_wars()

        # 无战争时自动跳过
        if not active_wars:
            print("   ☮️  No active conflicts - phase skipped")
            self.state.mark_phase_executed("combat")
            return True

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
            self.state.mark_phase_executed("combat")
            return True

        print(f"\n   ⚔️  Resolving {len(assigned_wars)} active conflict(s)...")

        # 执行每场战争的战斗
        for war in assigned_wars:
            self._resolve_battle(war_system, war, terms)

        # 兼容旧逻辑：设置当前阶段
        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "combat"

        self.state.mark_phase_executed("combat")
        print(f"\n   Progress: {get_progress_bar(self.state)}")
        return True

    # ---------- 战斗解决私有方法 ----------

    def _resolve_battle(self, war_system, war: "War", terms):
        """执行单场战斗"""
        print(f"\n   🎯 Battle: {war.name}")
        print(f"      Enemy Strength: {war.get_total_strength()}")

        # 检查指挥官
        if war.commander_id is None:
            print(f"      ⚠️  No {terms.commander} assigned!")
            return

        commander = self.state.get_member(war.commander_id)
        if not commander or commander.is_dead:
            print(f"      💀 {terms.commander} unavailable! War stalls...")
            war_system.recall_commander(war.id)
            return

        # 获取军事系统
        ms = self.state.get_military_system()

        # 计算军团战力
        legions = ms.get_legions_for_battle(war.id) if ms else []
        legion_count = len(legions)

        if legion_count == 0:
            print(f"      ❌ No {terms.legion}s assigned!")
            war.duration += 1
            return

        # 计算军团战力
        legion_strength = sum(l.get_combat_strength() for l in legions)

        # 计算总战力
        military_bonus = commander.military if hasattr(commander, 'military') else 0
        total_force = military_bonus + legion_strength

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
        dice_roll = random.randint(2, 12)
        combat_total = dice_roll + total_force - war.get_total_strength()

        print(f"\n      🎲 Dice roll: {dice_roll}")
        print(f"      📊 Combat Total: {dice_roll} + {total_force} - {war.get_total_strength()} = {combat_total}")

        # 判定结果
        result = self._simplified_crt(dice_roll, combat_total, war)

        # 应用结果
        self._apply_battle_result(war_system, war, commander, result, terms, ms, legions)

    def _simplified_crt(self, dice_roll: int, combat_total: int, war) -> str:
        """简化版CRT判定"""
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

    def _apply_battle_result(self, war_system, war, commander, result: str, terms, ms, legions):
        """应用战斗结果"""
        result_emojis = {
            "TRIUMPH": "🏆",
            "VICTORY": "✅",
            "STALEMATE": "⏸️",
            "DEFEAT": "❌",
            "DISASTER": "💀",
        }
        emoji = result_emojis.get(result, "❓")
        print(f"\n      {emoji} RESULT: {result}")

        if result == "TRIUMPH":
            print(f"      🎉 {terms.triumph}! {commander.name} returns in glory!")
            commander.influence += 10

            for legion in legions:
                legion.promote_to_veteran()
                legion.recall()
                print(f"      🏆 {legion.name} returns in triumph!")
            war_system.resolve_war(war.id, victory=True)

        elif result == "VICTORY":
            print(f"      ✓ Victory! {war.name} concluded successfully.")
            commander.influence += 5

            for legion in legions:
                legion.promote_to_veteran()
                legion.recall()
                print(f"      🏆 {legion.name} returns in triumph!")
            war_system.resolve_war(war.id, victory=True)

        elif result == "STALEMATE":
            print(f"      ⏳ Stalemate. War continues...")
            war.duration += 1

        elif result == "DEFEAT":
            print(f"      💔 Defeat! Forces scattered.")

            # 失败：军团损失部分，将领可能伤亡
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
            roll = random.random()
            if roll < 0.3:
                war.report_commander_casualty("fled", self.state.turn.turn_number)
                print(f"      🏃 {commander.name} fled!")
            elif roll < 0.5:
                war.report_commander_casualty("captured", self.state.turn.turn_number)
                print(f"      🔒 {commander.name} captured!")
            else:
                war.report_commander_casualty("wounded", self.state.turn.turn_number)
                print(f"      🚑 {commander.name} wounded")

            war.commander_id = None
            war.duration += 1

        elif result == "DISASTER":
            print(f"      🔥 DISASTER! Catastrophic defeat!")

            # 灾难：全军覆没
            for legion in legions:
                legion.status = LegionStatus.DISBANDED
                legion.recall()
                print(f"      💀 {legion.name} destroyed!")

            # 将领阵亡
            commander.is_dead = True
            commander.is_faction_leader = False
            if commander.id in self.state.turn.leader_ids:
                self.state.turn.leader_ids.remove(commander.id)

            war.report_commander_casualty("killed", self.state.turn.turn_number)
            war.commander_id = None
            war.legions_assigned = 0
            war.fleets_assigned = 0

            print(f"      ⚰️  {commander.name} falls in battle!")
            self.state.log_event(f"💀 Disaster at {war.name}: {commander.name} killed")

            war.duration += 1