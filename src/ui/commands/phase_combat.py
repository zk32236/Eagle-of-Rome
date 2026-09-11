# src/ui/commands/phase_combat.py
"""
战斗阶段命令 - 处理所有活跃战争的战斗
优化打印格式，更清晰显示战斗过程
"""

import random
import logging
from typing import List, Optional, TYPE_CHECKING

from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.core.entities.war import WarStatus
from src.ui.utils import get_progress_bar
from src.core.deciders.peace_treaty_decider import PeaceTreatyDecider
from src.core.deciders.impl.auto_peace_treaty_decider import AutoPeaceTreatyDecider

if TYPE_CHECKING:
    from src.core.game_state import GameState
    from src.core.entities.war import War


# WP-G-R4（SA v1.7 §5.5/§3.4，S4 主 CLI nested 渲染）：两 stage 文本 helper（纯 display）。
# 消费同一 v2 envelope（naval/land 并列 executed）；数值逐项取自 stage（与 DATA 同 run 值
# 一致）；未执行 stage 无数值行（R4-05）；executed 字段缺失 → 「未记录」不制造零。
_STAGE_WORD = {
    "TRIUMPH": "大胜", "VICTORY": "胜利", "STALEMATE": "僵持",
    "DEFEAT": "战败", "DISASTER": "灾难",
    "triumph": "大胜", "victory": "胜利", "draw": "僵持",
    "defeat": "战败", "disaster": "灾难",
}


def _stage_value(stage, key, suffix=""):
    """executed stage 字段读取：缺失 → 「未记录」（暴露 DTO contract failure，不制造零）。"""
    if isinstance(stage, dict) and key in stage:
        return f"{stage[key]}{suffix}"
    return f"未记录{suffix}"


def _naval_stage_lines(naval):
    """Naval stage 文本行。NOT_READY → 「海军未就绪」（无 Land 数值行）；bypass 说明原因，
    不渲染作「海战胜利」；executed → 海战结果词 + 舰队损失 + 海权阶段结果（stage 快照）。"""
    if not isinstance(naval, dict):
        return []
    lines = []
    if naval.get("executed") is True:
        word = _STAGE_WORD.get(naval.get("result"), naval.get("result") or "未知")
        lines.append(f"⚓ 海战: {word}")
        lines.append(f"   舰队损失: {_stage_value(naval, 'roman_losses', ' 艘')}")
        if naval.get("sea_control_acquired") is True:
            lines.append("   海权: 已获取制海权")
        else:
            lines.append("   海权: 未获取制海权")
    elif naval.get("status") == "NOT_READY":
        lines.append("海军未就绪")
        if naval.get("reason") == "NO_READY_ASSIGNED_FLEET":
            lines.append("   未就绪：本战无已指派可用舰队")
    elif naval.get("reason") == "NOT_REQUIRED":
        lines.append("海战: 未执行 — 本战无需海军")
    elif naval.get("reason") == "SEA_CONTROL_ALREADY_ACQUIRED":
        lines.append("海战: 未执行 — 已获取制海权，本场跳过海战")
    else:
        lines.append("海战: 未执行")
    return lines


def _land_stage_lines(land):
    """Land stage 文本行。未执行（NAVAL_GATE_BLOCKED）→ 固定「陆战: 未执行 — 海战门未通过」；
    executed → 陆战结果词 + 骰子/攻击/防御/分数 + 真实损失/战利品（有才显示）。"""
    if not isinstance(land, dict):
        return []
    lines = []
    if land.get("executed") is True:
        word = _STAGE_WORD.get(land.get("result"), land.get("result") or "未知")
        lines.append(f"陆战: {word}")
        lines.append("   🎲 骰子: " + _stage_value(land, "dice", " / 12")
                     + " | 攻击总值: " + _stage_value(land, "total_attack")
                     + " vs 敌军防御: " + _stage_value(land, "enemy_defence")
                     + " = " + _stage_value(land, "total_score"))
        if "losses" in land and land.get("losses", 0) > 0:
            lines.append(f"   💀 军团损失: {land['losses']}")
        if "loot" in land and land.get("loot", 0) > 0:
            lines.append(f"   📦 战利品: {land['loot']} T")
    elif land.get("reason") == "NAVAL_GATE_BLOCKED":
        lines.append("陆战: 未执行 — 海战门未通过")
    elif land.get("reason") == "NAVAL_NOT_READY":
        lines.append("陆战: 未执行")
    else:
        lines.append("陆战: 未执行")
    return lines


class CombatCommand(Command):
    """战斗阶段命令"""

    name = "combat"
    aliases = ["c"]
    description = "执行战斗阶段 (Combat Phase)"

    def __init__(self, state: "GameState",
                 peace_treaty_decider: Optional[PeaceTreatyDecider] = None):
        super().__init__(state)
        self.peace_treaty_decider = peace_treaty_decider or AutoPeaceTreatyDecider()

    def execute(self, args: List[str]) -> bool:
        if not self.state.is_phase_executed("senate"):
            print("⚠️ 必须先执行元老院阶段 (senate)")
            return False

        if self.state.is_phase_executed("combat"):
            print("⚠️ 战斗阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_combat} Phase (Year {abs(self.state.turn.year)} BC) ---")

        war_system = self.state.get_war_system()
        if not war_system:
            print("   ☮️  No war system - phase skipped")
            self.state.mark_phase_executed("combat")
            return True

        # ─── S1: 委托给 combat_api.auto_resolve_combat 共享用例 ───
        from src.api import combat_api

        # 获取当前玩家 ID
        current_player = self.state.get_current_player()
        player_id = current_player.player_id if current_player else ""

        result = combat_api.auto_resolve_combat(self.state, player_id)

        if not result.get("success"):
            print(f"   ❌ 战斗结算失败: {result.get('message', '')}")
            return False

        data = result.get("data", {})
        battles = data.get("battles", [])
        treaties = data.get("treaties", [])
        commanders_returned = data.get("commanders_returned", [])
        active_war_count = data.get("active_war_count", 0)
        skipped_no_commander = data.get("skipped_no_commander", 0)

        if active_war_count == 0:
            print("   ☮️  No active conflicts - phase skipped")
        else:
            # 无指挥官战争报告
            if skipped_no_commander > 0:
                print(f"   ⚠️  {skipped_no_commander} war(s) without commanders!")
                print(f"   💀 Wars continue without leadership...")

            # 战斗结果（WP-G-R4 S4：nested 两 stage 文本渲染，consume 同一 v2 envelope）
            if battles:
                print(f"\n   ⚔️  Resolving {len(battles)} active conflict(s)...")
                for b in battles:
                    print(f"\n   ⚔️  {b.get('war_name', 'Unknown')}:")
                    if isinstance(b, dict) and b.get("schema_version") == 2 \
                            and isinstance(b.get("land"), dict) and isinstance(b.get("naval"), dict):
                        for line in _naval_stage_lines(b.get("naval")):
                            print(f"      {line}")
                        for line in _land_stage_lines(b.get("land")):
                            print(f"      {line}")
                        outcome = b.get("war_outcome") or {}
                        if outcome.get("terminal_success"):
                            print(f"      🎉 {b.get('war_name', '')} resolved!")
                    else:
                        # legacy flat 回退（旧消费者/旧 DTO）
                        result_emojis = {
                            "triumph": "🏆", "victory": "✅",
                            "draw": "⏸️", "defeat": "❌", "disaster": "💀",
                        }
                        emoji = result_emojis.get(b.get("result", ""), "❓")
                        print(f"      🎲 Dice: {b.get('dice', '?')} | "
                              f"{emoji} Result: {b.get('result_label', b.get('result', '?'))}")
                        if b.get("losses", 0) > 0:
                            print(f"      💀 Legion losses: {b['losses']}")
                        if b.get("loot", 0) > 0:
                            print(f"      🏆 Loot: {b['loot']} "
                                  f"(Treasury: {b.get('treasury_share', 0)}"
                                  f", Commander: {b.get('commander_share', 0)})")
                        if b.get("triumph"):
                            print(f"      🎉 {b.get('war_name', '')} ends in triumph!")

            # WP-G-R4（SA v1.7 §3.4）：no-ready 战争独立 unavailable 提示（非 battles）
            unavailable = data.get("unavailable_wars", []) or []
            for u in unavailable:
                w = war_system.get_war_by_id(u.get("war_id")) if war_system else None
                name = w.name if w is not None else u.get("war_id", "Unknown")
                code = u.get("code", "")
                if code == "NAVAL_NOT_READY":
                    print(f"      ⚓ {name} 海军未就绪（NAVAL_NOT_READY）："
                          f"本战无已指派可用舰队，跳过海战与登陆")
                elif code == "NAVAL_SYSTEM_UNAVAILABLE":
                    print(f"      ⚓ {name} 海军系统不可用（技术失败，阻断攻击）")
                else:
                    print(f"      ⚓ {name} 不可用（{code}）")

            if not battles and not unavailable:
                print("   ⏸️  No wars ready for combat")

            # 停战条约（防范 Mock 值）
            for t in treaties:
                indemnity = t.get('indemnity', 0)
                duration = t.get('duration', 0)
                if isinstance(indemnity, (int, float)) and isinstance(duration, (int, float)):
                    print(f"      📜 War treaty: indemnity {indemnity}, "
                          f"duration {duration} turns")

        # 指挥官返回
        for cr in commanders_returned:
            print(f"      🔄 Commander {cr.get('commander_name', '')} returns to Rome, "
                  f"relinquishing {cr.get('former_office', '')}")

        completed = data.get("completed", False)
        next_phase = data.get("next_phase", "resolution")
        if completed:
            print(f"\n   ✅ Combat phase complete. Advancing to {next_phase}.")
        else:
            print(f"\n   ⏳ Combat phase pending.")

        if hasattr(self.state.turn, 'current_phase'):
            self.state.turn.current_phase = "combat"

        return True

    # ================================= MVP 0.7 ===========================================

    # ======== MVP 0.7.1 停战议和 =======

    def _process_commanders_returning(self, war_system):
        """处理元老院已批准停战的指挥官返回罗马"""
        current_turn = self.state.turn.turn_number
        # 获取所有 TRUCE 且草案为 approved 的战争
        approved_wars = war_system.get_truce_wars_with_approved_treaty()
        for war in approved_wars:
            commander_id = war.original_commander_id or war.commander_id
            if not commander_id:
                continue
            commander = self.state.get_member(commander_id)
            if not commander or commander.is_dead:
                continue

            # 卸任前线官职
            old_office = commander.office
            if old_office in ('proconsul', 'propraetor'):
                # 获取上任回合（从战争记录中获取）
                assigned_turn = war.commander_assigned_turn or (current_turn - 1)
                commander.add_office_history(old_office, assigned_turn, current_turn - 1)
                commander.office = None
                commander.is_absent = False
                commander.update_influence()
                print(f"      🔄 指挥官 {commander.name} 返回罗马，卸任 {old_office}")
                self.state.log_event(
                    f"指挥官 {commander.name} 返回罗马",
                    extra={'type': 'commander_return', 'figure_id': commander.id, 'war_id': war.id}
                )

    def _resolve_battle(self, war_system, war: "War", terms):
        """执行单场战斗（包含强制结果开关）"""
        if war.commander_id is None:
            print(f"      ⚠️  No {terms.commander} assigned!")
            return

        commander = self.state.get_member(war.commander_id)
        if not commander or commander.is_dead:
            print(f"      💀 {terms.commander} unavailable! War stalls...")
            war_system.recall_commander(war.id)
            return

        ms = self.state.get_military_system()

        # WP-G-R4（SA v1.7 §3.1/§3.3 legacy 窄 parity）：共享 NavalSystem readiness 门 +
        # 已获控 skip；NOT_READY 独立返回（零副作用，不加 duration、不打陆战）。
        if war.naval_required and not war.sea_control_acquired:
            from src.api.combat_api import _naval_attack_readiness
            _code, _reason = _naval_attack_readiness(self.state, war)
            if _code is not None:
                print(f"      ⚓ 海军未就绪（{_code}）：本战无已指派可用舰队，跳过海战与登陆")
                return
        if war.naval_required and self.state.naval_system and not war.sea_control_acquired:
            print(f"\n      ⚓ 进行海战...")
            # ----- 海战前日志 -----
            fleet_ids = war.assigned_fleet_ids
            fleets = [self.state.naval_system.get_fleet(fid) for fid in fleet_ids]
            fleet_statuses = [f.status.value if f else "missing" for f in fleets]
            self.state.log_event(
                f"[DEBUG] 海战开始: war={war.id}, 指派舰队={fleet_ids}, 舰队状态={fleet_statuses}",
                level=logging.DEBUG,
                extra={
                    "function": "_resolve_battle",
                    "war_id": war.id,
                    "phase": "naval_battle_start",
                    "assigned_fleet_ids": fleet_ids,
                    "fleet_statuses": fleet_statuses
                }
            )
            naval_result, losses = self.state.naval_system.resolve_naval_battle(war)
            print(f"      海战结果: {naval_result}, 罗马损失 {losses.get('roman_losses', 0)} 艘战舰")
            # ----- 海战后日志 -----
            self.state.log_event(
                f"[DEBUG] 海战结束: war={war.id}, 结果={naval_result}, 损失={losses}",
                level=logging.DEBUG,
                extra={
                    "function": "_resolve_battle",
                    "war_id": war.id,
                    "phase": "naval_battle_end",
                    "result": naval_result,
                    "losses": losses
                }
            )
            # R-05（G1-09，WP-G GC）：STALEMATE 亦阻断陆战（legacy 对齐 canonical 门）；
            # resolve_naval_battle 已含 sea_control mutation（TRIUMPH/VICTORY → 获控，与 canonical 同源）
            if naval_result in ("STALEMATE", "DEFEAT", "DISASTER"):
                print(f"      海战失败，无法登陆，战争持续")
                war.duration += 1
                return

        legions = ms.get_legions_for_battle(war.id) if ms else []
        legion_count = len(legions)


        if legion_count == 0:
            print(f"      ❌ No {terms.legion}s assigned!")
            war.duration += 1
            return


        # 打印战斗标题
        print(f"\n   ⚔️  Resolving {war.name}:")

        # 指挥官信息（使用 martial 属性）
        print(f"      🎖️  Roma Commander: {commander.name} (Mil: {commander.martial})")

        # 军团力量
        legion_strength = sum(l.get_combat_strength() for l in legions)
        print(f"      🛡️  Roma Forces: {legion_count} Legion(s) (+{legion_strength})")


        # 计算总战力（使用 martial）
        military_bonus = commander.martial if hasattr(commander, 'martial') else 0
        total_force = military_bonus + legion_strength
        enemy_strength = war.get_total_strength()

        print(f"\n      ⚔️  Total Force: {total_force} vs Enemy {enemy_strength}")

        # 强制结果开关
        force_result = self.state.config.get("testing.force_battle_result")
        if force_result:
            print(f"      ⚙️ 强制战斗结果: {force_result}")
            self._apply_battle_result(war_system, war, commander, force_result, terms, ms, legions, legion_strength)
            # 强制结果后也尝试生成草案（如果需要）
            self._maybe_generate_treaty(war_system, war, force_result, terms)
            return

        dice_roll = random.randint(2, 12)
        combat_total = dice_roll + total_force - enemy_strength

        print(f"\n      🎲 Dice roll: {dice_roll}")
        print(f"      📊 Combat Total: {dice_roll} + {total_force} - {enemy_strength} = {combat_total}")

        result = self._simplified_crt(dice_roll, combat_total, war)
        self._apply_battle_result(war_system, war, commander, result, terms, ms, legions, legion_strength)

        # ===== 新增：草案生成 =====
        self._maybe_generate_treaty(war_system, war, result, terms)

    # ================================= MVP 0.1-0.5 =======================================

    def _maybe_generate_treaty(self, war_system, war: "War", result: str, terms):
        """根据战斗结果尝试生成停战草案（C1，G1-08：仅 STALEMATE 生成 pending treaty）。

        TRIUMPH/VICTORY → 战争结束（RESOLVED，GB）；DEFEAT/DISASTER → ACTIVE 继续（无条约）。
        """
        if result != 'STALEMATE':
            return

        treaty = self.peace_treaty_decider.decide_treaty(war, result, self.state)

        required = {'indemnity', 'duration', 'generated_turn'}
        missing = required - treaty.keys()
        if missing:
            print(f"ERROR: treaty missing keys: {missing}")
            return

        try:
            if war_system.enter_truce(war, treaty):
                print(f"      📜 战争 {war.name} 达成停战草案，等待元老院审批。")
                self.state.log_event(
                    f"战争 {war.name} 生成停战草案，赔款 {treaty['indemnity']}，有效期 {treaty['duration']} 回合",
                    extra={
                        'type': 'peace_treaty_generated',
                        'war_id': war.id,
                        'result': result,
                        'indemnity': treaty['indemnity'],
                        'duration': treaty['duration'],
                        'generated_turn': treaty['generated_turn']
                    }
                )
            else:
                print(f"      ⚠️ 战争 {war.name} 无法进入停战状态，草案无效。")
                self.state.log_event(
                    f"战争 {war.name} 草案生成失败：无法进入停战",
                    extra={'type': 'peace_treaty_failed', 'war_id': war.id},
                    level=logging.WARNING
                )
        except Exception as e:
            print(f"ERROR in enter_truce: {e}")
            import traceback
            traceback.print_exc()

    def _simplified_crt(self, dice_roll: int, combat_total: int, war) -> str:
        """简化版CRT判定"""
        if war.is_disaster_roll(dice_roll):
            return "DISASTER"
        elif combat_total >= 12:
            return "TRIUMPH"
        elif combat_total >= 6:
            return "VICTORY"
        elif war.is_standoff_roll(dice_roll) or -3 <= combat_total < 6:
            return "STALEMATE"
        elif combat_total < -3:
            return "DEFEAT"
        else:
            return "STALEMATE"

    def _apply_battle_result(self, war_system, war, commander, result: str, terms, ms, legions, legion_strength):
        """应用战斗结果，并打印结果摘要"""
        legion_count = len(legions)
        result_emojis = {
            "TRIUMPH": "🏆",
            "VICTORY": "✅",
            "STALEMATE": "⏸️",
            "DEFEAT": "❌",
            "DISASTER": "💀",
        }
        emoji = result_emojis.get(result, "❓")

        if result == "TRIUMPH":
            print(f"\n      {emoji} RESULT: TRIUMPH (0 losses)")
            print(f"      🎉 {terms.triumph}! {commander.name} returns in glory!")
            commander.influence += 10

            for legion in legions:
                legion.promote_to_veteran()
                legion.recall()
            # WP-G-R4（§4.2/§4.3）：legacy helper 成功分支显式传 CRT 词（identity）
            war_system.resolve_war(war.id, victory=True, combat_result="triumph")


        elif result == "VICTORY":
            print(f"\n      {emoji} RESULT: VICTORY (0 losses)")
            print(f"      ✓ Victory! {war.name} concluded, but enemy not destroyed.")
            commander.influence += 5

            # S5（G1-22 / §11.4，WP-G GB）：VICTORY = 战争结束——晋升统一在
            # resolve_war victory 分支（先于召回）→ RESOLVED → recall→AVAILABLE（Veteran 保留）；
            # 不生成条约（GA G1-08 门收敛后天然不触发）。晋升不再在本分支重复执行（防
            # battles_won 双计，单一晋升 owner = resolve_war）。
            war_system.resolve_war(war.id, victory=True, combat_result="victory")

        elif result == "STALEMATE":
            print(f"\n      {emoji} RESULT: STALEMATE (0 losses)")
            print(f"      ⏳ Stalemate. War continues...")
            war.duration += 1

        elif result == "DEFEAT":
            # S5（G1-05/06/07，WP-G GB）：委托 S2 原语——random.sample 无放回 ceil(N/2)
            # → DESTROYED（清 war_id/commander_id/is_veteran）；幸存保持 ACTIVE+assigned。
            # 移除旧「前一半 DISBANDED + recall」前缀序路径（§11.2/§21 偏差实证），
            # 单一陆战结果权威 = combat_api + apply_land_casualties。
            losses = len(legions) - len(legions) // 2  # = ceil(N/2)（G1-06）
            print(f"\n      {emoji} RESULT: DEFEAT, {losses} Legion(s) destroyed")
            print(f"      💔 Defeat! Forces scattered.")
            ms.apply_land_casualties(war.id, "DEFEAT")

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

            print(f"\n      {emoji} RESULT: DISASTER, {legion_count} Legion(s) destroyed")
            print(f"      🔥 DISASTER! Catastrophic defeat!")

            for legion in legions:
                legion.mark_destroyed(self.state.turn.turn_number)
            # 将领阵亡 - 统一通过 GameState 处理
            self.state.mark_member_dead(commander.id, transfer_land=True, transfer_wealth=True)
            war.report_commander_casualty("killed", self.state.turn.turn_number)
            war.commander_id = None
            war.legions_assigned = 0
            war.fleets_assigned = 0

            print(f"      ⚰️  {commander.name} falls in battle!")
            self.state.log_event(f"💀 Disaster at {war.name}: {commander.name} killed")

            war.duration += 1