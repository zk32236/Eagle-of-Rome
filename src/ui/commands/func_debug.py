# src/ui/commands/func_debug.py
import logging
from typing import List, Optional

from src.ui.commands.sys_base import Command
from src.core.entities.fleet import Fleet, FleetStatus
from src.core.localization import TerminologyService

class DebugFleetCommand(Command):
    name = "debug_fleet"
    aliases = ["df"]
    description = "显示舰队内部状态: debug_fleet <fleet_id>"

    def execute(self, args: List[str]) -> bool:
        if not args:
            print("❌ 请指定舰队编号")
            return False
        try:
            fleet_id = int(args[0])
        except ValueError:
            print("❌ 舰队编号必须为整数")
            return False

        ns = self.state.naval_system
        if not ns:
            print("❌ 海军系统未就绪")
            return False
        fleet = ns.get_fleet(fleet_id)
        if not fleet:
            print(f"❌ 舰队 {fleet_id} 不存在")
            return False

        print(f"\n🔍 舰队 {fleet.name} (编号:{fleet.number}) 内部状态：")
        print(f"  类型: {fleet.fleet_type}")
        print(f"  状态: {fleet.status.value}")
        print(f"  指挥官ID: {fleet.commander_id}")
        print(f"  经验: {fleet.experience}")
        print(f"  基础战力: {fleet._strength_base}")
        print(f"  是否老兵: {fleet.is_veteran}")
        print(f"  指派战争ID: {fleet.assigned_war_id}")
        print(f"  指派任务类型: {fleet._assigned_mission_type}")
        print(f"  目标战争ID(建造时): {fleet._target_war_id}")
        print(f"  建造开始回合: {fleet.build_start_turn}")
        print(f"  建造结束回合: {fleet.build_end_turn}")
        print(f"  关联合同ID: {fleet.contract_id}")
        print(f"  被摧毁回合: {fleet.destroyed_turn}")
        return True

class DebugWarCommand(Command):
    name = "debug_war"
    aliases = ["dw"]
    description = "显示战争内部状态: debug_war <war_id>"

    def execute(self, args: List[str]) -> bool:
        if not args:
            print("❌ 请指定战争ID")
            return False
        war_id = args[0]
        ws = self.state.get_war_system()
        if not ws:
            print("❌ 战争系统未就绪")
            return False
        war = ws.get_war_by_id(war_id)
        if not war:
            print(f"❌ 战争 {war_id} 不存在")
            return False

        print(f"\n🔍 战争 {war.name} (ID:{war.id}) 内部状态：")
        print(f"  状态: {war.status.value}")
        print(f"  类型: {war.war_type.value}")
        print(f"  指挥官ID: {war.commander_id}")
        print(f"  指派军团数: {war.legions_assigned}")
        print(f"  指派舰队ID: {war.assigned_fleet_ids}")
        print(f"  在 active_wars: {war in ws._active_wars}")
        print(f"  在 truce_wars: {war in ws._truce_wars}")
        print(f"  在 threats: {war in ws._threats}")
        print(f"  和约: {war.peace_treaty}")
        print(f"  停战结束回合: {war.truce_end_turn}")
        print(f"  威胁等级: {war.threat_level}")
        print(f"  需要海战: {war.naval_required}")
        print(f"  敌方海军当前: {war.enemy_naval_current}")
        print(f"  原指挥官ID: {war.original_commander_id}")
        print(f"  指挥官指派回合: {war.commander_assigned_turn}")
        return True

class BuildFleetCommand(Command):
    """调试命令：直接建造舰队"""
    name = "build_fleet"
    aliases = ["bf"]
    description = "调试：建造一艘舰队 build_fleet [fleet_type] [commander_id]"

    def execute(self, args: List[str]) -> bool:
        if not self.state.naval_system:
            print("❌ 海军系统未就绪")
            return False

        # ===== 新增：检查技术解锁 =====
        if not self.state.pyrrhic_war_won:
            print("❌ 舰队技术尚未解锁（需要皮洛士战争胜利）")
            return False
        # =============================

        fleet_type = "trireme"
        commander_id = None
        if len(args) >= 1:
            fleet_type = args[0].lower()
            if fleet_type not in ("trireme", "quadrireme", "quinquereme"):
                print("❌ 无效舰队类型，可选：trireme, quadrireme, quinquereme")
                return False
        if len(args) >= 2:
            try:
                commander_id = int(args[1])
                if not self.state.get_living_member(commander_id):
                    print(f"❌ 指挥官 {commander_id} 不存在或已死亡")
                    return False
            except ValueError:
                print("❌ 指挥官ID必须为整数")
                return False

        # 获取配置
        fleet_configs = self.state.config.get("economic_rules.fleet_types", {})
        if fleet_type not in fleet_configs:
            print(f"❌ 配置中未定义舰队类型 {fleet_type}")
            return False
        config = fleet_configs[fleet_type]
        build_cost = config.get("build_cost", 40)

        # 检查国库
        if self.state.treasury < build_cost:
            print(f"❌ 国库资金不足，需要 {build_cost}，现有 {self.state.treasury}")
            return False

        # 扣款并创建舰队（立即可用）
        self.state.treasury -= build_cost
        ns = self.state.naval_system
        fleet = Fleet(
            number=ns._next_fleet_number,
            fleet_type=fleet_type,
            name=f"Fleet {ns._next_fleet_number} ({fleet_type})"
        )
        fleet.set_strength_from_config(config)
        if commander_id:
            fleet._commander_id = commander_id
        fleet._status = FleetStatus.AVAILABLE  # 直接可用，无建造期
        ns._fleets[ns._next_fleet_number] = fleet
        ns._next_fleet_number += 1

        print(f"✅ 舰队 {fleet.name} 建造完成，花费 {build_cost}，现已可用")
        self.state.log_event(
            f"调试: 建造舰队 {fleet.name}",
            extra={"fleet_number": fleet.number, "fleet_type": fleet_type}
        )
        return True


class AssignFleetCommand(Command):
    """调试命令：指派舰队到战争"""
    name = "assign_fleet"
    aliases = ["af"]
    description = "调试：指派舰队到战争 assign_fleet <fleet_id> <war_id> [commander_id]"

    def execute(self, args: List[str]) -> bool:
        if len(args) < 2:
            print("❌ 用法: assign_fleet <fleet_id> <war_id> [commander_id]")
            return False

        try:
            fleet_id = int(args[0])
        except ValueError:
            print("❌ 舰队ID必须为整数")
            return False
        war_id = args[1]
        commander_id = None
        if len(args) >= 3:
            try:
                commander_id = int(args[2])
            except ValueError:
                print("❌ 指挥官ID必须为整数")
                return False

        ns = self.state.naval_system
        if not ns:
            print("❌ 海军系统未就绪")
            return False

        fleet = ns.get_fleet(fleet_id)
        if not fleet:
            print(f"❌ 舰队 {fleet_id} 不存在")
            return False
        if fleet.status != FleetStatus.AVAILABLE:
            print(f"❌ 舰队当前状态 {fleet.status.value}，无法指派")
            return False

        ws = self.state.get_war_system()
        if not ws:
            print("❌ 战争系统未就绪")
            return False
        war = ws.get_war_by_id(war_id)
        if not war:
            print(f"❌ 战争 {war_id} 不存在")
            return False
        if not war.naval_required:
            print(f"❌ 战争 {war.name} 不需要海战")
            return False

        if ns.assign_fleet_to_war(fleet_id, war_id, "naval", commander_id):
            print(f"✅ 舰队 {fleet.name} 指派至战争 {war.name}")
            return True
        else:
            print("❌ 指派失败")
            return False


class ShowFleetsCommand(Command):
    """调试命令：显示所有舰队状态"""
    name = "show_fleets"
    aliases = ["fl"]  # 从 "sf" 改为 "fl"
    description = "调试：显示所有舰队状态"

    def execute(self, args: List[str]) -> bool:
        ns = self.state.naval_system
        if not ns:
            print("❌ 海军系统未就绪")
            return False

        fleets = ns.get_all_fleets()
        if not fleets:
            print("📭 没有舰队")
            return True

        print("\n   ⚓ 舰队状态：")
        print("   ID  名称               类型      状态        指挥官  战力")
        print("   " + "-" * 50)
        for fleet in fleets:
            status_emoji = {
                FleetStatus.BUILDING: "🏗️",
                FleetStatus.AVAILABLE: "🟢",
                FleetStatus.ON_MISSION: "⚓",
                FleetStatus.IN_COMBAT: "⚔️",
                FleetStatus.DESTROYED: "💀"
            }.get(fleet.status, "❓")
            status_str = fleet.status.value
            commander_name = ""
            if fleet.commander_id:
                fig = self.state.get_member(fleet.commander_id)
                commander_name = fig.name if fig else "?"
            print(f"   {fleet.number:<3} {fleet.name:<18} {fleet.fleet_type:<8} {status_emoji}{status_str:<8} {commander_name:<8} {fleet.get_combat_strength(self.state)}")
        print()
        return True


class ProcessFleetConstructionCommand(Command):
    """调试命令：手动触发舰队建造完成检查"""
    name = "process_fleet_construction"
    aliases = ["pfc"]
    description = "调试：手动触发舰队建造完成检查"

    def execute(self, args: List[str]) -> bool:
        ns = self.state.naval_system
        if not ns:
            print("❌ 海军系统未就绪")
            return False

        completed = ns.process_fleet_construction(self.state.turn.turn_number)
        if completed:
            print(f"✅ 舰队 {completed} 建造完成")
        else:
            print("ℹ️ 没有舰队在本回合完工")
        return True