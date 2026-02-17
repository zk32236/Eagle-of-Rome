# src/ui/debug_cli.py

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.game_state import GameState
from core.scenario_loader import ScenarioLoader
from core.phases.revenue_phase import RevenuePhase
from core.phases.mortality_phase import MortalityPhase
from core.phases.senate_phase import SenatePhase
from core.phases.forum_phase import ForumPhase
from core.phases.population_phase import PopulationPhase
from core.phases.combat_phase import CombatPhase
from core.phases.resolution_phase import ResolutionPhase
from core.localization import TerminologyService, GamePhase


class DebugCLI:
    """调试命令行界面 - MVP 0.4.3 合同系统版"""

    def __init__(self):
        self.state: GameState = GameState()
        self.running = True

        # 定义阶段顺序（MVP 0.3完整7阶段）
        self.phase_sequence = [
            ("mortality", "m", "💀"),
            ("revenue", "r", "💰"),
            ("forum", "f", "📜"),
            ("population", "p", "👥"),
            ("senate", "s", "🏛️"),
            ("combat", "c", "⚔️"),
            ("resolution", "x", "🔚"),
        ]
        self.phase_map = {name: (abbr, emoji) for name, abbr, emoji in self.phase_sequence}

    def run(self):
        terms = TerminologyService.get()

        print(f"🏛️  Eagle of Rome - MVP 0.4.3 Contract System")
        print(f"   Active terms: {terms.assembly}/{terms.nobles}/{terms.currency}")
        print(f"   Phase order: {' → '.join([name for name, _, _ in self.phase_sequence])}")
        print("Type 'help' for commands, 'exit' to quit")

        while self.running:
            try:
                cmd = input("\n> ").strip().lower()
                self._handle_command(cmd)
            except KeyboardInterrupt:
                print("\nUse 'exit' to quit")
            except Exception as e:
                # 添加完整错误打印
                import traceback
                print(f"\n{'=' * 60}")
                print("❌ ERROR OCCURRED - Full Traceback:")
                print(f"{'=' * 60}")
                traceback.print_exc()
                print(f"{'=' * 60}")
                print(f"Error type: {type(e).__name__}")
                print(f"Error message: {e}")
                print(f"{'=' * 60}")

    def _handle_command(self, cmd: str):
        """命令分发"""
        if cmd == "exit":
            self.running = False

        elif cmd == "help":
            self._show_help()

        elif cmd == "load":
            self._load_scenario()

        elif cmd == "status":
            self._show_status()

        # 阶段命令（按顺序）
        elif cmd in ("mortality", "m"):
            self._do_phase("mortality")

        elif cmd in ("revenue", "r"):
            self._do_phase("revenue")

        elif cmd in ("forum", "f"):
            self._do_phase("forum")

        elif cmd in ("population", "p"):
            self._do_phase("population")

        elif cmd in ("senate", "s"):
            self._do_phase("senate")

        elif cmd in ("combat", "c"):
            self._do_phase("combat")

        elif cmd in ("resolution", "x"):
            self._do_phase("resolution")

        # 回合控制
        elif cmd in ("next", "n"):
            self._next_turn(force=False)

        elif cmd.startswith("next "):
            self._next_turn(force="force" in cmd)

        elif cmd == "turn":
            self._do_full_turn(auto=True)

        elif cmd == "step":
            self._do_full_turn(auto=False)

        # 战争阶段命令
        elif cmd == "wars":
            self._show_wars()

        elif cmd == "assign":
            self._assign_commander_interactive()

        elif cmd == "legions":
            self._show_legions()

        elif cmd == "recruit":
            self._recruit_legion_interactive()

        elif cmd == "disband":
            self._disband_legion_interactive()

        # 广场阶段指令
        elif cmd.startswith("persuade "):
            self._persuade_figure(cmd[9:])

        # 人口阶段指令
        elif cmd.startswith("festival "):
            self._hold_festival(cmd[9:])

        # 合同阶段指令 - MVP 0.4.3
        elif cmd == "contracts":
            self._show_contracts()

        elif cmd.startswith("vote contract "):
            parts = cmd.split()
            if len(parts) >= 3:
                try:
                    contract_id = int(parts[2])
                    self._vote_contract_interactive(contract_id)
                except ValueError:
                    print("   ❌ Invalid contract ID")
            else:
                print("   ❌ Usage: vote contract <id>")

        elif cmd.startswith("assign works "):
            parts = cmd.split()
            if len(parts) >= 4:
                try:
                    contract_id = int(parts[2])
                    figure_id = int(parts[3])
                    self._assign_works(contract_id, figure_id)
                except ValueError:
                    print("   ❌ Invalid ID")
            else:
                print("   ❌ Usage: assign works <contract_id> <figure_id>")

        # 土地交易指令 - MVP 0.4.4
        elif cmd.startswith("trade land "):
            parts = cmd.split()
            if len(parts) >= 5:
                try:
                    seller_id = int(parts[2])
                    buyer_id = int(parts[3])
                    amount = int(parts[4])
                    self._trade_land(seller_id, buyer_id, amount)
                except ValueError:
                    print("   ❌ Invalid arguments")
            else:
                print("   ❌ Usage: trade land <seller_id> <buyer_id> <amount>")

        elif cmd.startswith("land price "):
            parts = cmd.split()
            if len(parts) >= 4:
                try:
                    seller_id = int(parts[2])
                    buyer_id = int(parts[3])
                    self._preview_land_price(seller_id, buyer_id)
                except ValueError:
                    print("   ❌ Invalid IDs")
            else:
                print("   ❌ Usage: land price <seller_id> <buyer_id>")

        elif cmd == "seats":
            self._show_seat_standings()

        # 术语切换
        elif cmd.startswith("terms "):
            self._switch_terms(cmd[6:])

        elif cmd == "reload":
            self._reload_config()

        else:
            print(f"Unknown command: {cmd}")

    def _show_help(self):
        terms = TerminologyService.get()

        print(f"""
🏛️  Eagle of Rome - Commands (MVP 0.4.3)
═══════════════════════════════════════════════════
  load                    Load scenario
  status                  Show game state

  Phase Commands (in order):
    m, mortality          {terms.phase_mortality} Phase
    r, revenue            {terms.phase_revenue} Phase  
    f, forum              {terms.phase_forum} Phase
    p, population         {terms.phase_population} Phase
    s, senate             {terms.phase_senate} Phase
    c, combat             {terms.phase_combat} Phase
    x, resolution         {terms.phase_resolution} Phase

  Turn Control:
    turn                  Auto full turn (all 7 phases)
    step                  Step-by-step turn
    n, next               Next turn (requires all 7 phases)
    n force, next force   Force next turn (skip check)

  War Commands:
    wars                    Show war status (deck/active/discard)
    assign                  Interactive commander assignment


  Military Commands:
    legions                 Show legion status
    recruit                 Recruit legions
    disband                 Disband legions

  Forum Commands (MVP 0.4):
    persuade <id>           Persuade figure to join faction
    festival <id> <amount>  Hold festival (personal funds → popularity)

  Contract Commands (MVP 0.4.3):
    contracts               Show all contracts (pending/active/completed)
    vote contract <id>      Vote to award tax farming contract
    assign works <cid> <fid> Assign public works to figure (Consul only)
    
  Land Trading Commands (MVP 0.4.4):
    seats                   Show seat share standings
    trade land <s> <b> <n>  Trade n land from seller to buyer
    land price <s> <b>      Preview land price between figures

  Terminology:
    terms [preset]        Switch: original/historical_roman/generic_latin/chinese_historical

  Other:
    reload                Reload config
    exit                  Quit 
        """)

    def _switch_terms(self, preset: str):
        """切换术语集"""
        if TerminologyService.set_preset(preset):
            terms = TerminologyService.get()
            print(f"   ✅ Switched to: {preset}")
            print(f"   Now using: {terms.assembly}/{terms.nobles}/{terms.currency}")
        else:
            print(f"   ❌ Unknown preset: {preset}")
            print(f"   Available: original, historical_roman, generic_latin, chinese_historical")

    def _load_scenario(self):
        self.state = ScenarioLoader.load_scenario("mvp_test.json")
        print("\n✅ Game loaded!")
        self._show_status()

    def _show_status(self):
        if not self._check_loaded():
            return
        print(self.state.get_status_summary())

        # 显示阶段进度
        self._show_progress()

    def _do_phase(self, phase_name: str):
        """通用阶段执行（强制军事准备检查）"""
        if not self._check_loaded():
            return

        terms = TerminologyService.get()

        # 🆕 Combat阶段前强制检查军事准备
        if phase_name == "combat":
            is_ready, unassigned, no_legions = self.state.get_military_preparation_status()

            if not is_ready:
                print(f"\n{'!' * 55}")
                print(f"⛔ CANNOT EXECUTE {terms.phase_combat.upper()}")
                print(f"{'!' * 55}")

                if unassigned:
                    print(f"\n   ⚠️  {len(unassigned)} war(s) need COMMANDERS:")
                    for war in unassigned:
                        print(f"      • {war.name} (Str: {war.get_total_strength()})")

                if no_legions:
                    print(f"\n   ⚠️  {len(no_legions)} war(s) need LEGIONS:")
                    for war in no_legions:
                        cmd = self.state.get_member(war.commander_id)
                        cmd_name = cmd.name if cmd else "Unknown"
                        print(f"      • {war.name} (Commander: {cmd_name})")

                print(f"\n   🛡️  REQUIRED ACTIONS (execute in order):")
                print(f"      1. recruit  - Recruit legions")
                print(f"      2. assign   - Assign commanders and legions")
                print(f"\n   After preparation, retry: {phase_name}")
                print(f"{'!' * 55}")
                return  # 阻止执行

        # 检查阶段是否已执行
        if self.state.is_phase_executed(phase_name):
            display_name = getattr(terms, f"phase_{phase_name}", phase_name)
            print(f"⚠️  {display_name} Phase already executed!")
            self._show_missing_phases()
            return

        # 获取阶段类
        phase_class = self._get_phase_class(phase_name)
        if not phase_class:
            print(f"❌ Phase {phase_name} not implemented")
            return

        # 执行阶段
        phase = phase_class()
        success = phase.execute(self.state)

        if success:
            self.state.mark_phase_executed(phase_name)
            self._show_progress()

            # 🆕 检查是否完成军事准备，提示用户
            if phase_name in ("recruit", "assign"):
                is_ready, _, _ = self.state.get_military_preparation_status()
                if is_ready and self._has_active_wars():
                    print(f"\n   ✅ Military preparation complete!")
                    print(f"   Ready for: {terms.phase_combat}")

    def _has_active_wars(self) -> bool:
        """检查是否有活跃战争"""
        ws = self.state.get_war_system()
        if not ws:
            return False
        return len(ws.get_active_wars()) > 0

    def _get_phase_class(self, phase_name: str):
        """根据名称获取阶段类"""
        phase_classes = {
            "mortality": MortalityPhase,
            "revenue": RevenuePhase,
            "forum": ForumPhase,
            "population": PopulationPhase,
            "senate": SenatePhase,
            "combat": CombatPhase,
            "resolution": ResolutionPhase,
        }
        return phase_classes.get(phase_name)

    def _next_turn(self, force: bool = False):
        """推进到下一年（修复：无战争时自动完成Combat）"""
        if not self._check_loaded():
            return

        # 🆕 检查是否可以自动完成Combat
        self._auto_complete_combat_if_no_wars()

        executed = set(self.state.executed_phases)
        required = set(name for name, _, _ in self.phase_sequence)
        missing = required - executed

        if missing and not force:
            terms = TerminologyService.get()
            missing_display = [getattr(terms, f"phase_{m}", m) for m in sorted(missing)]
            print(f"\n⛔ CANNOT ADVANCE")
            print(f"   Missing phases: {', '.join(missing_display)}")
            print(f"\n   Options:")
            print(f"      1. Execute missing phases")
            print(f"      2. 'next force' to skip")
            print(f"      3. 'turn' to auto-complete")
            return

        if missing and force:
            missing_names = ', '.join(sorted(missing))
            print(f"\n⚠️  FORCE ADVANCE - Skipping: {missing_names}")

        self.state.advance_year()
        print(f"Advanced to Year {abs(self.state.turn.year)} BC")
        self._show_turn_summary()

    def _auto_complete_combat_if_no_wars(self):
        """如果没有战争，自动标记Combat为完成"""
        ws = self.state.get_war_system()
        if not ws:
            return

        # 检查是否有活跃战争
        active = ws.get_active_wars()

        # 如果没有战争且Combat未执行，自动标记
        if not active and "combat" not in self.state.executed_phases:
            terms = TerminologyService.get()
            print(f"\n   ☮️  No wars - auto-completing {terms.phase_combat}")
            self.state.mark_phase_executed("combat")

    def _do_full_turn(self, auto: bool = True):
        """执行完整回合（修复：强制军事准备）"""
        if not self._check_loaded():
            return

        executed = set(self.state.executed_phases)
        if executed == set(name for name, _, _ in self.phase_sequence):
            print("⚠️  All phases executed! Use 'next' to advance.")
            return

        terms = TerminologyService.get()
        print(f"\n{'#' * 60}")
        print(f" TURN {self.state.turn.turn_number} ({abs(self.state.turn.year)} BC)")
        print(f" Terms: {terms.assembly}/{terms.nobles}/{terms.currency}")
        print(f"{'#' * 60}")

        # 按顺序执行阶段
        for name, abbr, emoji in self.phase_sequence:
            if name in executed:
                continue

            display_name = getattr(terms, f"phase_{name}", name)
            print(f"\n[{len(executed) + 1}/7] {emoji} {display_name}...")

            # 🆕 Senate阶段后检查是否有未准备的战争
            if name == "combat":
                ws = self.state.get_war_system()
                if ws:
                    active = ws.get_active_wars()
                    unassigned = [w for w in active if w.commander_id is None]

                    if active and unassigned:
                        print(f"\n   ⚠️  {len(unassigned)} war(s) need commanders!")
                        print(f"   🛡️  Military preparation required before combat")

                        # 强制进入准备模式
                        self._forced_military_preparation(unassigned)

                        # 重新检查
                        unassigned = [w for w in ws.get_active_wars() if w.commander_id is None]
                        if unassigned:
                            print(f"   ❌ Still {len(unassigned)} war(s) unprepared - combat skipped")
                            self.state.mark_phase_executed("combat")
                            continue

            # 执行阶段
            self._do_phase(name)

            if not auto and name not in self.state.executed_phases:
                input("   Press Enter...")

        print(f"\n{'#' * 60}")
        print(f" ✅ TURN COMPLETE - All 7 phases executed")
        print(f"{'#' * 60}")

    def _forced_military_preparation(self, unassigned_wars):
        """强制军事准备流程"""
        terms = TerminologyService.get()
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()

        print(f"\n{'=' * 50}")
        print(f"   🛡️  FORCED MILITARY PREPARATION")
        print(f"{'=' * 50}")

        # 步骤1：检查并征召军团
        available_legions = ms.get_unassigned_legions() if ms else []
        if not available_legions:
            print(f"\n   📢 No {terms.legion}s available!")
            print(f"   Options: [r]ecruit / [s]kip")
            choice = input("   > ").strip().lower()

            if choice == 'r':
                self._recruit_legion_interactive()
                # 重新获取
                available_legions = ms.get_unassigned_legions() if ms else []

        # 步骤2：为每个未指派战争指派
        for war in unassigned_wars:
            # 跳过已指派的（可能在上一步中被指派）
            if war.commander_id is not None:
                continue

            print(f"\n   📋 Prepare: {war.name}")
            print(f"   Options: [a]ssign / [s]kip")
            choice = input("   > ").strip().lower()

            if choice == 'a':
                self._quick_assign(war)

        print(f"{'=' * 50}")

    def _quick_assign(self, war):
        """快速指派（简化版）"""
        terms = TerminologyService.get()
        ms = self.state.get_military_system()
        ws = self.state.get_war_system()

        # 快速选择将领（影响力最高的可用将领）
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.is_present:
                    candidates.append(member)

        if not candidates:
            print("   ❌ No available commanders")
            return

        # 显示前5个
        print(f"\n   Select {terms.commander}:")
        for idx, cmd in enumerate(candidates[:5], 1):
            print(f"      {idx}. {cmd.name} (Mil:{cmd.military})")

        try:
            choice = int(input(f"   # (1-{len(candidates[:5])}): ")) - 1
            if not (0 <= choice < len(candidates[:5])):
                return
            selected_cmd = candidates[choice]
        except ValueError:
            return

        # 快速选择军团（全部可用）
        available = ms.get_unassigned_legions() if ms else []
        if not available:
            print("   ❌ No legions available")
            return

        print(f"\n   Assign {terms.legion}s (max {len(available)}):")
        try:
            count = int(input(f"   Count (0-{len(available)}): "))
            count = max(0, min(len(available), count))
        except ValueError:
            count = 0

        # 执行指派
        if count > 0:
            selected = available[:count]
            legion_numbers = [l.number for l in selected]

            ws.assign_commander(war.id, selected_cmd.id, count, 0)
            assigned, msg = ms.assign_to_war(legion_numbers, war.id, selected_cmd.id)
            print(f"   ✅ {msg}")

    def _show_missing_phases(self):
        """显示剩余阶段"""
        executed = set(self.state.executed_phases)
        required = set(name for name, _, _ in self.phase_sequence)
        missing = required - executed

        if missing:
            terms = TerminologyService.get()
            missing_display = [getattr(terms, f"phase_{m}", m) for m in sorted(missing)]
            print(f"   ⏳ Still need: {', '.join(missing_display)}")

    def _show_progress(self):
        """显示阶段进度条"""
        executed = self.state.executed_phases
        total_phases = len(self.phase_sequence)
        completed = len(executed)

        bar = "█" * completed + "░" * (total_phases - completed)
        print(f"\n   Progress: [{bar}] {completed}/{total_phases}")

    def _show_turn_summary(self):
        """显示回合总结"""
        terms = TerminologyService.get()
        executed = self.state.executed_phases
        year = abs(self.state.turn.year)

        print(f"\n📅 Year {year} BC:")
        print(f"   Completed: {len(executed)}/7 phases")

        for name, abbr, emoji in self.phase_sequence:
            display_name = getattr(terms, f"phase_{name}", name)
            status = "✓" if name in executed else "○"
            print(f"      {status} {emoji} {display_name}")

        if len(executed) == 7:
            print(f"   ✅ Ready for 'next'")
        else:
            print(f"   ⏳ {7 - len(executed)} remaining")

    def _reload_config(self):
        """重新加载配置"""
        if not self._check_loaded():
            return
        try:
            old_cooldown = self.state.get_cooldown_years()
            self.state.config = self.state._load_config()
            new_cooldown = self.state.get_cooldown_years()
            print(f"🔄 Config: {old_cooldown} → {new_cooldown} years")
        except Exception as e:
            print(f"❌ Failed: {e}")

    def _check_loaded(self) -> bool:
        """检查游戏是否已加载"""
        if not self.state or not self.state.factions:
            print("No game loaded. Use 'load' first.")
            return False
        return True

    def _show_wars(self):
        """显示战争状态（含伤亡状态）"""
        if not self._check_loaded():
            return

        ws = self.state.get_war_system()
        if not ws:
            print("War system not available")
            return

        terms = TerminologyService.get()

        print(f"\n{'=' * 55}")
        print(f"   ⚔️  {terms.phase_combat} Status")
        print(f"{'=' * 55}")

        # 牌堆
        deck_count = len(ws._war_deck)
        print(f"\n   📚 Deck: {deck_count} war(s) waiting")

        # 预警
        imminent = ws.check_imminent_wars()
        if imminent:
            print(f"\n   🔮 Imminent:")
            for war in imminent:
                print(f"      ⚠️  {war.name}")

        # 活跃战争
        active = ws.get_active_wars()
        if active:
            is_ready, unassigned, no_legions = self.state.get_military_preparation_status()

            # 准备状态摘要
            if is_ready:
                print(f"\n   ✅ READY FOR COMBAT")
            else:
                print(f"\n   ❌ NOT READY")

            # 🆕 修改部分：显示每个战争的详细状态
            for war in active:
                print(f"\n   📋 {war.name}")
                print(f"      Strength: {war.get_total_strength()} | Duration: {war.duration}y")

                # 显示指挥官状态（修改部分）
                if war.commander_id:
                    commander = self.state.get_member(war.commander_id)
                    if commander and not commander.is_dead:
                        # 指挥官存活且健康
                        print(f"      🎖️  Commander: {commander.name}")
                    else:
                        # 🆕 指挥官伤亡，显示状态
                        status_info = {
                            "killed": ("⚰️", "KILLED"),
                            "fled": ("🏃", "FLED"),
                            "captured": ("🔒", "CAPTURED"),
                        }.get(war.commander_status, ("❓", "UNKNOWN"))
                        emoji, text = status_info
                        print(f"      {emoji} Commander {text} - NEED REASSIGNMENT")
                else:
                    # 无指挥官
                    print(f"      ❌ NO COMMANDER - NEED ASSIGNMENT")

                # 显示军团状态（修改部分）
                ms = self.state.get_military_system()
                if ms:
                    legions = ms.get_legions_for_battle(war.id)
                    if legions:
                        vet_count = sum(1 for l in legions if l.is_veteran)
                        vet_text = f" ({vet_count}⭐)" if vet_count else ""
                        print(f"      🛡️  {len(legions)} legion(s){vet_text}")
                    else:
                        # 🆕 无军团
                        print(f"      💀 NO LEGIONS - NEED REINFORCEMENT")

                # 显示惩罚
                if war.penalties:
                    penalty_text = []
                    if 'unrest_per_turn' in war.penalties:
                        penalty_text.append(f"{terms.unrest}+{war.penalties['unrest_per_turn']}/turn")
                    if 'treasury_cost' in war.penalties:
                        penalty_text.append(f"{war.penalties['treasury_cost']}{terms.currency}/turn")
                    if penalty_text:
                        print(f"      💸 {', '.join(penalty_text)}")

        else:
            print(f"\n   ☮️  No active wars")

        # 弃牌
        discard_count = len(ws._war_discard)
        if discard_count:
            print(f"\n   ♻️  Resolved: {discard_count} war(s)")

        print(f"{'=' * 55}")

    def _assign_commander_interactive(self):
        """交互式指派将领（修复：显示所有战争，允许增援）"""
        if not self._check_loaded():
            return

        ws = self.state.get_war_system()
        ms = self.state.get_military_system()
        if not ws or not ms:
            print("War/Military system not available")
            return

        terms = TerminologyService.get()

        # 🆕 修改1：显示所有活跃战争（不只是未指派的）
        active = ws.get_active_wars()

        if not active:
            print("No active wars to assign commanders")
            return

        # 🆕 修改2：显示所有战争，标注状态
        print(f"\nSelect {terms.phase_combat}:")
        for idx, war in enumerate(active, 1):
            if war.commander_id:
                cmd = self.state.get_member(war.commander_id)
                if cmd and not cmd.is_dead:
                    cmd_text = f" [Cmd: {cmd.name}]"
                    status = "✅"
                else:
                    # 🆕 显示伤亡状态
                    status_emoji = {
                        "killed": "⚰️",
                        "fled": "🏃",
                        "captured": "🔒",
                    }.get(war.commander_status, "❓")
                    cmd_text = f" [{status_emoji} {war.commander_status.upper()}]"
                    status = "💀"
            else:
                cmd_text = " [NO COMMANDER]"
                status = "❌"

            naval_need = f" (⚓{war.get_naval_strength_required()})" if war.naval_support_required else ""
            print(f"  {idx}. {status} {war.name}{cmd_text} (Str: {war.get_total_strength()}){naval_need}")

        try:
            choice = int(input(f"\nWar # (1-{len(active)}): ")) - 1
            if not (0 <= choice < len(active)):
                print("Invalid selection")
                return
            selected_war = active[choice]
        except ValueError:
            print("Invalid input")
            return

        # 🆕 修改3：如果已有指挥官，提供增援选项
        if selected_war.commander_id is not None:
            commander = self.state.get_member(selected_war.commander_id)
            print(f"\n   ℹ️  {selected_war.name} already assigned to {commander.name}")
            print(f"   Options: [a]dd legions / [r]eplace commander / [c]ancel")
            option = input("   > ").strip().lower()

            if option == 'c':
                return
            elif option == 'a':
                # 只添加军团
                self._add_legions_to_war(selected_war, ms, terms)
                return
            # 'r' 继续下面的重新指派流程

        # 选择指挥官（原有逻辑）
        print(f"\nSelect {terms.commander}:")
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.is_present:
                    candidates.append(member)
                    leader_mark = f" [{terms.leader_title}]" if member.is_leader else ""
                    print(f"  {len(candidates)}. {member.name}{leader_mark} (Mil:{member.military})")

        try:
            choice = int(input(f"\nCommander # (1-{len(candidates)}): ")) - 1
            if not (0 <= choice < len(candidates)):
                print("Invalid selection")
                return
            selected_cmd = candidates[choice]
        except ValueError:
            print("Invalid input")
            return

        # 选择军团（原有逻辑）
        available_legions = ms.get_unassigned_legions()
        max_legions = len(available_legions)

        if max_legions == 0:
            print(f"\n❌ No available {terms.legion}s!")
            proceed = input("Assign commander without legions? (y/n): ").lower()
            if proceed != 'y':
                return
            selected_legions = []
        else:
            print(f"\nSelect {terms.legion}s:")
            for idx, legion in enumerate(available_legions, 1):
                vet = "⭐" if legion.is_veteran else ""
                print(f"  {idx}. {legion.name}{vet}")

            try:
                input_str = input(f"\nEnter numbers (e.g., 1,2,3) or 'all': ")
                if input_str.lower() == 'all':
                    selected_legions = available_legions
                else:
                    indices = [int(x.strip()) - 1 for x in input_str.split(',')]
                    selected_legions = []
                    for idx in indices:
                        if 0 <= idx < len(available_legions):
                            selected_legions.append(available_legions[idx])

                if not selected_legions:
                    print("No legions selected")
                    return

            except ValueError:
                print("Invalid input")
                return

        # 海军（如需要）
        fleets = 0
        if selected_war.naval_support_required:
            try:
                fleets = int(input(f"{terms.fleet}s to assign (0-5): "))
                fleets = max(0, min(5, fleets))
            except ValueError:
                fleets = 0

        # 执行指派
        success = ws.assign_commander(
            selected_war.id,
            selected_cmd.id,
            len(selected_legions),
            fleets
        )

        if success:
            print(f"\n✅ {selected_cmd.name} assigned to {selected_war.name}")

            if selected_legions:
                legion_numbers = [l.number for l in selected_legions]
                assigned_count, msg = ms.assign_to_war(
                    legion_numbers,
                    selected_war.id,
                    selected_cmd.id
                )
                print(f"   {msg}")

                # 检查准备状态
                is_ready, _, _ = self.state.get_military_preparation_status()
                if is_ready:
                    print(f"\n   ✅ All wars prepared! Ready for {terms.phase_combat}")
            else:
                print(f"   ⚠️  Warning: No {terms.legion}s assigned!")

    def _add_legions_to_war(self, war, ms, terms):
        """只添加军团到已有指挥官的战争"""
        available = ms.get_unassigned_legions()

        if not available:
            print(f"   ❌ No available {terms.legion}s to add")
            return

        print(f"\n   Available {terms.legion}s to add:")
        for idx, legion in enumerate(available, 1):
            vet = "⭐" if legion.is_veteran else ""
            print(f"      {idx}. {legion.name}{vet}")

        try:
            input_str = input(f"\n   Enter numbers to add: ")
            indices = [int(x.strip()) - 1 for x in input_str.split(',')]

            selected = []
            for idx in indices:
                if 0 <= idx < len(available):
                    selected.append(available[idx])

            if selected:
                legion_numbers = [l.number for l in selected]
                assigned, msg = ms.assign_to_war(legion_numbers, war.id, war.commander_id)
                print(f"   ✅ Added {assigned} {terms.legion}(s)")

                # 检查准备状态
                is_ready, _, _ = self.state.get_military_preparation_status()
                if is_ready:
                    print(f"\n   ✅ All wars prepared! Ready for {terms.phase_combat}")
            else:
                print("   No legions added")

        except ValueError:
            print("   Invalid input")

    def _show_legions(self):
        """显示军团状态"""
        if not self._check_loaded():
            return

        ms = self.state.get_military_system()
        if not ms:
            print("Military system not available")
            return

        print(ms.get_military_summary())
        ms.display_legion_status()

    def _recruit_legion_interactive(self):
        """征召军团（支持批量）"""
        if not self._check_loaded():
            return

        ms = self.state.get_military_system()
        if not ms:
            return

        terms = TerminologyService.get()
        available = ms.get_available_legions()

        if not available:
            print(f"No {terms.legion}s available for recruitment")
            return

        print(f"\n📊 Treasury: {self.state.treasury} {terms.currency}")
        print(f"Available {terms.legion}s: {len(available)}")
        print(f"Recruit cost: 10 {terms.currency} each")

        # 选择模式
        print(f"\nMode: [1] Single  [2] Multiple")
        mode = input("Choice (1-2): ").strip()

        if mode == "2":
            # 批量模式
            try:
                count = int(input(f"How many (1-{len(available)})? "))
                count = max(1, min(len(available), count))

                total_cost = count * 10
                if self.state.treasury < total_cost:
                    print(f"❌ Need {total_cost} {terms.currency}, have {self.state.treasury}")
                    return

                results = ms.recruit_multiple(count)
                success = sum(1 for _, s, _ in results if s)
                print(f"\n✅ Recruited {success}/{count} {terms.legion}(s)")

                # 🆕 检查准备状态
                self._check_prep_after_action()

            except ValueError:
                print("Invalid input")
        else:
            # 单军团模式（原有逻辑）
            print(f"\nSelect {terms.legion}:")
            for legion in available:
                print(f"  {legion.number}. {legion.name}")

            try:
                choice = int(input(f"\nRecruit # (1-10): "))
                success, msg = ms.recruit_legion(choice)
                status = "✅" if success else "❌"
                print(f"   {status} {msg}")
            except ValueError:
                print("Invalid input")

            if success:
                # 🆕 检查准备状态
                self._check_prep_after_action()

    def _check_prep_after_action(self):
        """行动后检查准备状态"""
        terms = TerminologyService.get()
        is_ready, _, _ = self.state.get_military_preparation_status()

        if is_ready and self._has_active_wars():
            print(f"\n   ✅ All wars prepared! Ready for {terms.phase_combat}")
        elif self._has_active_wars():
            print(f"\n   ⏳ Still need: assign commanders/legions")

    def _disband_legion_interactive(self):
        """交互式解散军团（支持批量）"""
        if not self._check_loaded():
            return

        ms = self.state.get_military_system()
        if not ms:
            print("Military system not available")
            return

        terms = TerminologyService.get()
        active = [l for l in ms.get_active_legions() if l.war_id is None]

        if not active:
            print(f"No unassigned {terms.legion}s available for disbandment")
            return

        print(f"\nUnassigned {terms.legion}s:")
        for idx, legion in enumerate(active, 1):
            vet = "⭐" if legion.is_veteran else ""
            print(f"  {idx}. {legion.name}{vet}")

        # 🆕 支持批量输入
        input_str = input(f"\nDisband # (1-{len(active)}, comma-separated, or 'all'): ").strip()

        if input_str.lower() == 'all':
            to_disband = active
        else:
            try:
                indices = [int(x.strip()) - 1 for x in input_str.split(',')]
                to_disband = []
                for idx in indices:
                    if 0 <= idx < len(active):
                        to_disband.append(active[idx])
                    else:
                        print(f"   ⚠️  Invalid selection: {idx + 1}")
            except ValueError:
                print("Invalid input")
                return

        # 执行解散
        success_count = 0
        for legion in to_disband:
            success, msg = ms.disband_legion(legion.number)
            if success:
                success_count += 1
                print(f"   ✅ {msg}")
            else:
                print(f"   ❌ {msg}")

        print(f"\nDisbanded {success_count}/{len(to_disband)} {terms.legion}(s)")

    def _check_military_preparation(self) -> bool:
        """检查并强制军事准备（修复：包含伤亡检查）"""
        terms = TerminologyService.get()
        ws = self.state.get_war_system()
        ms = self.state.get_military_system()

        if not ws or not ms:
            return True

        active = ws.get_active_wars()
        if not active:
            return True

        # 🆕 检查需要重新指派的战争
        needs_reassign = ws.get_wars_needing_reassignment()
        unassigned = [w for w in active if w.commander_id is None]

        # 合并列表（去重）
        check_wars = list(set(needs_reassign + unassigned))

        if not check_wars:
            return True

        print(f"\n{'!' * 55}")
        print(f"⛔ CANNOT EXECUTE {terms.phase_combat.upper()}")
        print(f"{'!' * 55}")

        for war in check_wars:
            if war.commander_status == "killed":
                cmd_name = "Previous commander KIA"
            elif war.commander_status == "fled":
                cmd_name = "Previous commander fled"
            elif war.commander_status == "captured":
                cmd_name = "Previous commander captured"
            elif war.commander_id is None:
                cmd_name = "NO COMMANDER"
            else:
                cmd_name = "Needs reinforcement"

            print(f"\n   ⚠️  {war.name}: {cmd_name}")

            # 检查军团
            legions = ms.get_legions_for_battle(war.id)
            if not legions:
                print(f"      💀 No legions assigned!")

        print(f"\n   🛡️  REQUIRED: Use 'assign' to appoint new commander/legions")
        print(f"{'!' * 55}")

        return False

    def _persuade_figure(self, figure_id_str: str):
        """说服人物加入派系"""
        if not self._check_loaded():
            return

        terms = TerminologyService.get()

        try:
            figure_id = int(figure_id_str)
        except ValueError:
            print(f"   ❌ Invalid figure ID: {figure_id_str}")
            return

        # 获取人物
        figure = self.state.curia.remove_figure(figure_id)
        if not figure:
            print(f"   ❌ Figure {figure_id} not found in Curia")
            return

        # 获取玩家派系
        player_faction = None
        for f in self.state.factions.values():
            if f.is_player:
                player_faction = f
                break

        if not player_faction:
            print(f"   ❌ No player faction found")
            # 放回 Curia
            self.state.curia.add_figure(figure)
            return

        # MVP简化：直接加入，未来添加说服难度和成本
        figure.faction_id = player_faction.id
        player_faction.member_ids.append(figure.id)

        print(f"   ✅ {figure.get_formal_name()} joins {player_faction.name}!")
        print(f"      {figure}")

    def _hold_festival(self, args: str):
        """举办庆典，指定人物出资获得人气"""
        if not self._check_loaded():
            return

        # 解析参数
        parts = args.split()
        if len(parts) != 2:
            print(f"   ❌ Usage: festival <figure_id> <amount>")
            print(f"   Example: festival 1 10")
            return

        try:
            figure_id = int(parts[0])
            amount = int(parts[1])
        except ValueError:
            print(f"   ❌ Invalid arguments: {args}")
            return

        if amount <= 0:
            print(f"   ❌ Amount must be positive")
            return

        # 获取人物
        figure = self.state.get_member(figure_id)
        if not figure:
            print(f"   ❌ Figure {figure_id} not found")
            return

        # 检查是否属于玩家派系
        player_faction = self._get_player_faction()
        if not player_faction or figure.faction_id != player_faction.id:
            print(f"   ❌ Figure {figure_id} is not in your faction")
            return

        # 检查个人资金
        if figure.wealth < amount:
            print(f"   ❌ {figure.get_formal_name()} has insufficient funds: {figure.wealth} < {amount}")
            return

        # 执行庆典
        figure.wealth -= amount

        # 计算人气收益（MVP简化：1:1比例）
        popularity_gain = amount  # 全额转化

        figure.add_popularity(popularity_gain)

        print(f"   🎉 {figure.get_formal_name()} holds a festival!")
        print(f"      Spent {amount} personal funds")
        print(f"      Gained {popularity_gain} popularity")
        print(f"      Current: {figure.popularity} popularity, {figure.wealth} wealth")

    # ==================== MVP 0.4.3 合同命令 ====================

    def _show_contracts(self):
        """显示所有合同状态 - MVP 0.4.3"""
        if not self._check_loaded():
            return

        terms = TerminologyService.get()

        print(f"\n{'=' * 60}")
        print(f"   📜 {terms.assembly} Contracts")
        print(f"{'=' * 60}")

        if not self.state.contracts:
            print(f"\n   📭 No contracts")
            return

        # 按状态分组
        pending = [c for c in self.state.contracts if c.status.value == "pending"]
        active = [c for c in self.state.contracts if c.status.value == "active"]
        completed = [c for c in self.state.contracts if c.status.value == "completed"]
        expired = [c for c in self.state.contracts if c.status.value == "expired"]

        # 待决合同
        if pending:
            print(f"\n   ⏳ PENDING (Awaiting Senate Action):")
            for c in pending:
                type_name = "📊 Tax" if c.contract_type.value == "tax_farming" else "🏗️ Works"
                print(f"      ID:{c.id} {type_name}: {c.name}")
                print(f"         Cost: {c.base_cost} | Profit: {c.expected_profit}")
                if c.contract_type.value == "tax_farming":
                    print(f"         💡 Use: vote contract {c.id}")
                else:
                    print(f"         💡 Senate Phase: Consul assigns")

        # 执行中合同
        if active:
            print(f"\n   ▶️  ACTIVE:")
            for c in active:
                type_name = "📊 Tax" if c.contract_type.value == "tax_farming" else "🏗️ Works"
                figure = self.state.get_member(c.awarded_to)
                fname = figure.name if figure else "Unknown"
                faction = self.state.get_faction(c.awarded_faction)
                fact_name = faction.name if faction else "Unknown"

                print(f"      ID:{c.id} {type_name}: {c.name}")
                print(f"         Contractor: {fname} ({fact_name})")
                print(f"         Remaining: {c.remaining_years} years")
                print(f"         Progress: {c.total_collected + c.total_spent}/{c.expected_profit}")

        # 已完成
        if completed:
            print(f"\n   ✅ COMPLETED:")
            for c in completed:
                type_name = "📊" if c.contract_type.value == "tax_farming" else "🏗️"
                print(f"      {type_name} {c.name} - Total: {c.total_collected + c.total_spent}")

        # 已过期
        if expired:
            print(f"\n   ❌ EXPIRED:")
            for c in expired:
                print(f"      {c.name}")

        print(f"{'=' * 60}")

    def _vote_contract_interactive(self, contract_id: int):
        """交互式投票授予包税合同 - MVP 0.4.3"""
        if not self._check_loaded():
            return

        from core.entities.contract import ContractType, ContractStatus
        terms = TerminologyService.get()

        # 查找合同
        contract = None
        for c in self.state.contracts:
            if c.id == contract_id:
                contract = c
                break

        if not contract:
            print(f"   ❌ Contract {contract_id} not found")
            return

        if contract.status != ContractStatus.PENDING:
            print(f"   ⚠️  Contract already processed ({contract.status.value})")
            return

        if contract.contract_type != ContractType.TAX_FARMING:
            print(f"   ❌ This is not a tax farming contract")
            return

        # 获取候选人（骑士）
        candidates = []
        for faction in self.state.factions.values():
            for member in faction.get_members(self.state):
                if not member.is_dead and member.class_tier.value == "eques":
                    candidates.append((member, faction))

        if not candidates:
            print(f"   ❌ No eligible {terms.cavalry_class} candidates")
            return

        print(f"\n   📊 Voting: {contract.name}")
        print(f"      Prepayment: {contract.base_cost} {terms.currency}")
        print(f"      Expected Profit: {contract.expected_profit} {terms.currency}")
        print(f"      Duration: {contract.duration_years} years")

        print(f"\n   Candidates ({terms.cavalry_class}):")
        for idx, (member, faction) in enumerate(candidates, 1):
            can_afford = "✅" if member.wealth >= contract.base_cost else "❌"
            print(f"      {idx}. {member.name} ({faction.name})")
            print(f"         Wealth: {member.wealth} {can_afford}")

        try:
            choice = int(input(f"\n   Select candidate (1-{len(candidates)}): ")) - 1
            if not (0 <= choice < len(candidates)):
                print("   ❌ Invalid selection")
                return
        except ValueError:
            print("   ❌ Invalid input")
            return

        winner, winner_faction = candidates[choice]

        # 检查资金
        if winner.wealth < contract.base_cost:
            print(f"   ❌ {winner.name} cannot afford {contract.base_cost} {terms.currency}")
            return

        # 执行授予
        if contract.award(winner.id, winner_faction.id, self.state.turn.turn_number):
            winner.wealth -= contract.base_cost
            self.state.treasury += contract.base_cost
            print(f"\n   ✅ Contract awarded to {winner.name}!")
            print(f"      {winner.name} paid {contract.base_cost} {terms.currency}")
            print(f"      Treasury: +{contract.base_cost} {terms.currency}")
        else:
            print(f"   ❌ Failed to award contract")

    def _assign_works(self, contract_id: int, figure_id: int):
        """执政官指派工程合同 - MVP 0.4.3"""
        if not self._check_loaded():
            return

        from core.entities.contract import ContractType, ContractStatus
        terms = TerminologyService.get()

        # 查找合同
        contract = None
        for c in self.state.contracts:
            if c.id == contract_id:
                contract = c
                break

        if not contract:
            print(f"   ❌ Contract {contract_id} not found")
            return

        if contract.status != ContractStatus.PENDING:
            print(f"   ⚠️  Contract already processed ({contract.status.value})")
            return

        if contract.contract_type != ContractType.PUBLIC_WORKS:
            print(f"   ❌ This is not a public works contract")
            return

        # 查找人物
        figure = self.state.get_member(figure_id)
        if not figure:
            print(f"   ❌ Figure {figure_id} not found")
            return

        if figure.is_dead:
            print(f"   ❌ {figure.name} is deceased")
            return

        if figure.class_tier.value != "eques":
            print(f"   ⚠️  Warning: {figure.name} is not {terms.cavalry_class}")

        # 检查执政官权限
        player_faction = self._get_player_faction()
        if not player_faction:
            print(f"   ❌ No player faction")
            return

        # 检查是否有执政官
        has_consul = any(cid in player_faction.member_ids for cid in self.state.turn.leader_ids)
        if not has_consul:
            print(f"   ⛔ Your faction has no {terms.leader_title} to assign contracts")
            return

        # 执行授予
        if contract.award(figure.id, figure.faction_id, self.state.turn.turn_number):
            print(f"\n   ✅ Works contract assigned!")
            print(f"      Project: {contract.name}")
            print(f"      Contractor: {figure.name}")
            print(f"      Budget: {contract.base_cost} {terms.currency}")
            print(f"      Expected Profit: {contract.expected_profit} {terms.currency}")
        else:
            print(f"   ❌ Failed to assign contract")

    def _get_player_faction(self):
        """获取玩家控制的派系"""
        for faction in self.state.factions.values():
            if faction.is_player:
                return faction
        return None

    def _trade_land(self, seller_id: int, buyer_id: int, amount: int):
        """执行土地交易 - MVP 0.4.4"""
        if not self._check_loaded():
            return

        from core.service.land_trading_service import LandTradingService

        service = LandTradingService(self.state)
        success, msg = service.execute_trade(seller_id, buyer_id, amount)

        if success:
            print(f"\n   ✅ {msg}")
        else:
            print(f"\n   ❌ Trade failed: {msg}")

    def _preview_land_price(self, seller_id: int, buyer_id: int):
        """预览土地交易价格 - MVP 0.4.4"""
        if not self._check_loaded():
            return

        from core.service.land_trading_service import LandTradingService

        service = LandTradingService(self.state)
        preview = service.get_trade_preview(seller_id, buyer_id, 1)  # 预览1单位价格

        if not preview:
            print("   ❌ Figure not found")
            return

        print(f"\n   💰 Land Trade Preview:")
        print(f"      Seller: {preview['seller_name']} (Land: {preview['seller_land_after'] + 1})")
        print(f"      Buyer:  {preview['buyer_name']} (Land: {preview['buyer_land_after'] - 1})")
        print(f"      Price:  {preview['price_per_unit']} Talents/unit")
        print(f"      Example: 5 units = {preview['price_per_unit'] * 5} Talents")

    def _show_seat_standings(self):
        """显示席位占比排名 - MVP 0.4.4（修复比例计算）"""
        if not self._check_loaded():
            return

        terms = TerminologyService.get()

        print(f"\n{'=' * 60}")
        print(f"   📊 Senate Seat Distribution (Total 300 seats)")
        print(f"{'=' * 60}")

        # 计算全国总土地和总私兵
        all_figures = [m for m in self.state.get_living_members() if not m.is_dead]
        total_land = sum(m.land for m in all_figures)
        total_veterans = sum(m.veterans for m in all_figures)
        total_assets = total_land + total_veterans

        if total_assets == 0:
            print("   No land or veterans to distribute seats")
            return

        print(f"\n   📈 National Total: Land={total_land}, Veterans={total_veterans}")
        print(f"   🏛️  Seat Calculation: (Personal Assets / {total_assets}) × 300\n")

        # 按个人资产排序
        sorted_figures = sorted(all_figures, key=lambda m: m.get_seat_share(), reverse=True)[:15]

        print(f"   {'Rank':<4} {'Name':<22} {'Faction':<12} {'Assets':<6} {'Seats':<6} {'%':<5}")
        print(f"   {'-' * 60}")

        for idx, fig in enumerate(sorted_figures, 1):
            faction = self.state.get_faction(fig.faction_id)
            fname = faction.name[:10] if faction else "Unknown"
            assets = fig.get_seat_share()

            # ===== 修复：按比例计算席位 =====
            seat_count = int((assets / total_assets) * 300)
            seat_pct = (assets / total_assets) * 100

            tier_emoji = {"nobile": "🏛️", "eques": "💰", "plebeian": "👤"}.get(fig.class_tier.value, "❓")

            print(f"   {idx:<4} {tier_emoji} {fig.name[:18]:<20} {fname:<12} "
                  f"{assets:<6} {seat_count:<6} {seat_pct:4.1f}%")

        # 派系总计（修复比例）
        print(f"\n   🏛️  Faction Seat Distribution:")
        print(f"   {'Faction':<15} {'Land':<6} {'Vets':<6} {'Assets':<8} {'Seats':<8} {'%':<6}")
        print(f"   {'-' * 60}")

        total_faction_seats = 0

        for faction in self.state.factions.values():
            members = faction.get_members(self.state)
            fact_land = sum(m.land for m in members)
            fact_vets = sum(m.veterans for m in members)
            fact_assets = fact_land + fact_vets

            # ===== 修复：按比例计算派系席位 =====
            fact_seats = int((fact_assets / total_assets) * 300) if total_assets > 0 else 0
            total_faction_seats += fact_seats

            seat_pct = (fact_assets / total_assets) * 100 if total_assets > 0 else 0

            print(f"   {faction.name:<15} {fact_land:<6} {fact_vets:<6} "
                  f"{fact_assets:<8} {fact_seats:<8} {seat_pct:5.1f}%")

        # 验证总计
        print(f"\n   {'TOTAL':<15} {total_land:<6} {total_veterans:<6} "
              f"{total_assets:<8} {total_faction_seats:<8} 100.0%")

        print(f"\n   💡 Formula: Seats = (Land + Veterans) / {total_assets} × 300")
        print(f"      Land = Estate holdings")
        print(f"      Veterans = Loyal veteran soldiers (from victories)")
        print(f"{'=' * 60}")

    def _get_player_faction(self):
        """获取玩家控制的派系"""
        for faction in self.state.factions.values():
            if faction.is_player:
                return faction
        return None

if __name__ == "__main__":
    cli = DebugCLI()
    cli.run()

