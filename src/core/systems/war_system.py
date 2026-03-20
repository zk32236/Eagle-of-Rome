# src/core/systems/war_system.py
import json
import random
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any, TYPE_CHECKING
from src.core.entities.war import War, WarStatus, WarType
from src.core.localization import TerminologyService

if TYPE_CHECKING:
    from src.core.game_state import GameState


class WarSystem:
    """
    战争管理系统

    职责：
    1. 战争牌堆管理（加载、洗牌、抽取）
    2. 战争激活与推进
    3. 战争结算（胜利/失败判定）
    4. 战争与将领/军团关联
    """

    def __init__(self, state: 'GameState'):
        self.state = state
        self._wars: List[War] = []          # 所有战争（含牌堆、威胁、活跃等）
        # 原有 _war_deck, _war_discard, _active_wars 可以保留，但为了简化，我们统一用 _wars 并依靠状态区分
        # 建议逐步迁移到统一列表，但为了兼容，我们暂时保留原有结构，新增 _threats 列表
        self._war_deck: List[War] = []
        self._war_discard: List[War] = []
        self._active_wars: List[War] = []   # 已爆发的战争
        self._threats: List[War] = []        # 威胁中的战争（未爆发）
        self._legions_to_disband: List[int] = []  # 存储需要在人口阶段解散的军团编号
        self._truce_wars: List[War] = []  # 停战中的战争

    # ========== 以下函数为 MVP 0.7 的内容 ==========

    # -------------- MVP 0.7-6 国泰民安 -----------
    def get_threat_wars(self) -> List[War]:
        """返回所有威胁状态的战争列表（只读副本）"""
        return [war for war in self._threats if war.status == WarStatus.THREAT]

    # -------------- MVP 0.7-4 战争系统 -----------

    def create_rebellion_war(self, province) -> War:
        """为起义行省创建战争对象"""
        rebellion_strength = self.state.config.get("combat_rules.rebellion_strength", 5)
        war = War(
            id=f"rebellion_{province.province_id}_{self.state.turn.turn_number}",
            name=f"{province.name} 起义",
            war_type=WarType.PROVINCIAL,
            strength=rebellion_strength,
            naval_required=False,
            rebellion_province_id=province.province_id,
        )
        war.status = WarStatus.ACTIVE
        return war

    def get_wars_with_naval(self) -> List[War]:
        """返回所有需要海战的战争（当前版本空实现）"""
        return [w for w in self._active_wars if w.naval_required]

    def process_enemy_reinforcements(self) -> None:
        """处理敌军增援（预留）"""
        pass

    # -------------- MVP 0.7-1 停战议和 -----------

    def get_war_by_commander(self, commander_id: int) -> Optional[War]:
        """通过指挥官ID查找其指挥的战争（包括 ACTIVE 和 TRUCE 状态的）"""
        for war in self._active_wars + self._truce_wars:
            if war.commander_id == commander_id:
                return war
        return None

    def enter_truce(self, war: War, treaty: Dict) -> bool:
        """
        将战争置为停战状态，并设置草案。
        返回 True 表示成功，False 表示战争无法进入停战（可能已在其他列表）。
        """
        if self._move_to_truce(war):
            war.set_peace_treaty(treaty)
            # 记录原指挥官及上任回合，用于人口阶段转换
            if war.commander_id:
                war.set_original_commander(war.commander_id, war.commander_assigned_turn)
            return True
        return False

    def _move_to_truce(self, war: War) -> bool:
        """将战争从当前列表移至 _truce_wars"""
        # 从所有可能的位置移除
        if war in self._active_wars:
            self._active_wars.remove(war)
        elif war in self._threats:
            self._threats.remove(war)
        elif war in self._war_deck:
            self._war_deck.remove(war)
        elif war in self._war_discard:
            self._war_discard.remove(war)
        else:
            return False
        if war not in self._truce_wars:
            self._truce_wars.append(war)
        war.status = WarStatus.TRUCE
        return True

    def _move_to_active(self, war: War) -> bool:
        # 入口日志
        self.state.log_event(
            f"[DEBUG] _move_to_active 开始: war={war.id}",
            level=logging.DEBUG,
            extra={
                "function": "_move_to_active",
                "war_id": war.id,
                "phase": "enter",
                "active_before": [w.id for w in self._active_wars],
                "truce_before": [w.id for w in self._truce_wars],
            }
        )
        if war not in self._truce_wars:
            self.state.log_event(
                f"[DEBUG] _move_to_active 失败: war={war.id} 不在 truce_wars",
                level=logging.DEBUG,
                extra={
                    "function": "_move_to_active",
                    "war_id": war.id,
                    "phase": "exit",
                    "success": False,
                    "reason": "not_in_truce"
                }
            )
            return False
        self._truce_wars.remove(war)
        if war not in self._active_wars:
            self._active_wars.append(war)
        war.status = WarStatus.ACTIVE
        war.commander_id = None
        self.state.log_event(
            f"[DEBUG] _move_to_active 成功: war={war.id}",
            level=logging.DEBUG,
            extra={
                "function": "_move_to_active",
                "war_id": war.id,
                "phase": "exit",
                "success": True,
                "active_after": [w.id for w in self._active_wars],
                "truce_after": [w.id for w in self._truce_wars],
            }
        )
        if self.state.naval_system:
            self.state.naval_system.assign_available_fleets_to_war(war.id)
        return True

    def _move_to_threat(self, war: War, threat_level: int = 1) -> bool:
        # ----- 新增入口日志 -----

        self.state.log_event(
            f"[DEBUG] _move_to_threat 开始: war={war.id}, threat_level={threat_level}",
            level=logging.DEBUG,
            extra={
                "function": "_move_to_threat",
                "war_id": war.id,
                "threat_level": threat_level,
                "phase": "enter",
                "truce_before": [w.id for w in self._truce_wars],
            }
        )
        if war not in self._truce_wars:
            # ----- 新增失败日志 -----
            self.state.log_event(
                f"[DEBUG] _move_to_threat 失败: war={war.id} 不在 truce_wars",
                level=logging.DEBUG,
                extra={
                    "function": "_move_to_threat",
                    "war_id": war.id,
                    "phase": "exit",
                    "success": False,
                    "reason": "not_in_truce"
                }
            )
            return False
        self._truce_wars.remove(war)
        if war not in self._threats:
            self._threats.append(war)
        war.status = WarStatus.THREAT
        war._triggered_this_turn = True
        war.threat_level = threat_level
        war.commander_id = None
        # ----- 新增成功日志 -----
        self.state.log_event(
            f"[DEBUG] _move_to_threat 成功: war={war.id}, 新威胁等级={threat_level}",
            level=logging.DEBUG,
            extra={
                "function": "_move_to_threat",
                "war_id": war.id,
                "phase": "exit",
                "success": True,
                "truce_after": [w.id for w in self._truce_wars],
                "threats_after": [w.id for w in self._threats],
            }
        )
        return True

    # ===== 新增查询方法 =====
    def get_truce_wars(self) -> List[War]:
        """获取所有停战中的战争"""
        return self._truce_wars.copy()

    def get_truce_wars_with_pending_treaty(self) -> List[War]:
        """获取所有停战中且草案为 pending 的战争"""
        return [w for w in self._truce_wars
                if w.peace_treaty and w.peace_treaty.get('status') == 'pending']

    def get_truce_wars_with_approved_treaty(self) -> List[War]:
        """获取所有停战中且草案为 approved 的战争"""
        return [w for w in self._truce_wars
                if w.peace_treaty and w.peace_treaty.get('status') == 'approved']

    # ===== 军团待解散管理 =====
    def add_legions_to_disband(self, legion_numbers: List[int]) -> None:
        """添加需要解散的军团编号（用于和约批准后）"""
        self._legions_to_disband.extend(legion_numbers)

    def clear_legions_to_disband(self) -> List[int]:
        """清空并返回待解散军团编号列表"""
        result = self._legions_to_disband.copy()
        self._legions_to_disband.clear()
        return result

    # ========== 以下函数为 MVP 0.5 之前（含）的内容 ==========

    # ========== 日志操作 ==========

    def activate_war(self, war_id: str, consul_id: int, legions: int) -> bool:
        # 入口日志
        self.state.log_event(
            f"[DEBUG] activate_war 开始: war_id={war_id}, consul_id={consul_id}, legions={legions}",
            level=logging.DEBUG,
            extra={
                "function": "activate_war",
                "war_id": war_id,
                "consul_id": consul_id,
                "legions": legions,
                "phase": "enter"
            }
        )
        war = self.get_war_by_id(war_id)
        if not war or war.status != WarStatus.THREAT:
            print(f"      ⚠️ 激活战争失败：战争 {war_id} 不存在或不是威胁状态")
            self.state.log_event(
                f"[DEBUG] activate_war 失败: war={war_id} 不存在或状态错误",
                level=logging.DEBUG,
                extra={
                    "function": "activate_war",
                    "war_id": war_id,
                    "phase": "exit",
                    "success": False,
                    "reason": "invalid_war_or_status"
                }
            )
            return False
        war.status = WarStatus.ACTIVE
        war.declared_by = consul_id
        war.proposed_legions = legions
        war.activation_turn = self.state.turn.turn_number
        war.set_commander_assigned_turn(self.state.turn.turn_number)
        if war in self._threats:
            self._threats.remove(war)
        if war not in self._active_wars:
            self._active_wars.append(war)
        print(f"      ✅ 战争 {war.name} 已激活，批准军团数 {legions}")
        self.state.log_event(
            f"[DEBUG] activate_war 成功: war={war.name}, legions={legions}",
            level=logging.DEBUG,
            extra={
                "function": "activate_war",
                "war_id": war.id,
                "phase": "exit",
                "success": True,
                "legions": legions,
                "active_after": [w.id for w in self._active_wars],
                "threats_after": [w.id for w in self._threats],
            }
        )
        return True

    def deactivate_war_to_threat(self, war_id: str, threat_level: int = 1) -> bool:
        """将活跃战争降级为威胁状态"""
        war = self.get_war_by_id(war_id)
        if not war or war.status != WarStatus.ACTIVE:
            return False

        war.status = WarStatus.THREAT
        war.threat_level = threat_level
        war.commander_id = None
        war.legions_assigned = 0
        war.fleets_assigned = 0

        if war in self._active_wars:
            self._active_wars.remove(war)
        if war not in self._threats:
            self._threats.append(war)

        ms = self.state.get_military_system()
        if ms:
            ms.recall_from_war(war.id)
            if war.legion_numbers:
                self._legions_to_disband.extend(war.legion_numbers)
            war.clear_legion_numbers()

        if self.state.naval_system:
            self.state.naval_system.recall_fleets_from_war(war.id)

        self.state.log_event(
            f"战争降级为威胁：{war.name}，威胁等级 {threat_level}",
            extra={"war_id": war.id, "threat_level": threat_level}
        )
        return True

    def resolve_war(self, war_id: str, victory: bool) -> Dict[str, Any]:
        war = self.get_war_by_id(war_id)
        if not war:
            return {}

        terms = TerminologyService.get()

        result = {
            'war_name': war.name,
            'victory': victory,
            'duration': war.duration,
            'rewards': {},
            'penalties_applied': [],
        }

        if victory:
            war.status = WarStatus.RESOLVED

            # === 起义战争特殊处理 ===
            is_rebellion = False
            if war.rebellion_province_id is not None:
                is_rebellion = True
                province = self.state.get_province(war.rebellion_province_id)
                if province:
                    province.set_grievance(0)
                    province.clear_event_flag("rebellion_active")
                    if war.commander_id:
                        commander = self.state.get_member(war.commander_id)
                        if commander:
                            commander.family_prestige += 1
                            self.state.log_event(
                                f"指挥官 {commander.name} 因镇压起义获得声望+1",
                                extra={"figure_id": commander.id}
                            )
                    print(f"      ✅ 起义镇压成功，{province.name} 民怨归零。")
            # =========================

            # 皮洛士战争解锁舰队（无论是否起义，但起义战争不会是皮洛士战争）
            if war.id == "pyrrhic_war":
                self.state.pyrrhic_war_won = True
                self.state.log_event(
                    "皮洛士战争胜利！罗马解锁舰队建造能力。",
                    extra={"type": "tech_unlock", "feature": "naval"}
                )

            # 如果不是起义战争，执行正常战利品分配
            if not is_rebellion:
                # 保存凯旋指挥官ID
                if war.commander_id:
                    war.set_triumph_commander(war.commander_id)
                # 获取战利品奖励字典
                rewards = war.calculate_rewards()
                result['rewards'] = rewards

                # 从配置读取分配比例
                treasury_share = self.state.config.get("combat_rules.treasury_share", 0.5)
                faction_share = self.state.config.get("combat_rules.faction_share", 0.25)
                commander_share = self.state.config.get("combat_rules.commander_share", 0.15)
                soldier_share = self.state.config.get("combat_rules.soldier_share", 0.15)

                total_treasury = rewards.get('treasury', 0)

                # 计算各项份额（取整）
                treasury_part = int(total_treasury * treasury_share)
                faction_part = int(total_treasury * faction_share)
                commander_part = int(total_treasury * commander_share)
                soldier_part = total_treasury - treasury_part - faction_part - commander_part

                # 打印战利品分配
                print(f"\n      📦 战利品分配 ({war.name}):")
                print(f"        总额: {total_treasury} 塔兰特")
                print(f"        国库: +{treasury_part}")
                if war.commander_id:
                    commander = self.state.get_member(war.commander_id)
                    commander_name = commander.name if commander else "未知"
                    print(f"        指挥官 {commander_name} 私库: +{commander_part}")
                    if commander and commander.faction_id:
                        faction = self.state.get_faction(commander.faction_id)
                        if faction:
                            print(f"        派系 {faction.name} 金库: +{faction_part}")
                        else:
                            print(f"        派系金库: +{faction_part} (无派系)")
                    else:
                        print(f"        派系金库: +{faction_part} (指挥官无派系)")
                else:
                    print(f"        指挥官私库部分 (无指挥官) 归国库: +{commander_part + faction_part}")
                print(f"        士兵份额: {soldier_part} (将转换为老兵支持)")

                # 实际分配
                if not war.commander_id:
                    self.state.add_treasury(total_treasury)
                    self.state.log_event(f"战争 {war.name} 战利品: 国库 +{total_treasury}（无指挥官）")
                    war.set_soldier_share(0)
                else:
                    if treasury_part > 0:
                        self.state.add_treasury(treasury_part)
                        self.state.log_event(f"战争 {war.name} 战利品: 国库 +{treasury_part}")

                    if faction_part > 0:
                        commander = self.state.get_member(war.commander_id)
                        if commander and commander.faction_id:
                            faction = self.state.get_faction(commander.faction_id)
                            if faction:
                                faction.treasury += faction_part
                                self.state.log_event(f"战争 {war.name} 战利品: 派系 {faction.name} +{faction_part}")

                    if commander_part > 0:
                        commander = self.state.get_member(war.commander_id)
                        if commander:
                            commander.wealth += commander_part
                            self.state.log_event(f"战争 {war.name} 战利品: 指挥官 {commander.name} +{commander_part}")

                    if soldier_part > 0:
                        war.set_soldier_share(soldier_part)
                        self.state.log_event(f"战争 {war.name} 战利品: 士兵份额 {soldier_part} 待凯旋分配")

                # 土地奖励
                land_reward = rewards.get('land', 0)
                if land_reward > 0:
                    print(f"      [DEBUG] 增加前国家公地: {self.state.get_national_public_land()}")  # 添加
                    self.state.add_national_public_land(land_reward)
                    print(f"      [DEBUG] 增加后国家公地: {self.state.get_national_public_land()}")  # 添加
                    self.state.log_event(f"战争 {war.name} 土地: 国家公地 +{land_reward}")

                # 家族声望
                prestige_reward = rewards.get('family_prestige', 0)
                if prestige_reward > 0 and war.commander_id:
                    commander = self.state.get_member(war.commander_id)
                    if commander:
                        commander.family_prestige += prestige_reward
                        self.state.log_event(f"战争 {war.name} 家族声望: {commander.name} +{prestige_reward}")

                # 占领行省
                if war.unlocked_provinces:
                    self.state.conquer_provinces(war.id)

                print(f"   ✅ {war.name} resolved! Victory!")
                print(f"   🎁 Rewards: {result['rewards']}")
            else:
                # 起义战争胜利，不分配战利品，简单打印
                print(f"   ✅ {war.name} resolved! Victory (rebellion suppressed).")

            # === 通用处理：指挥官返回（所有胜利战争都需要） ===
            if war.commander_id:
                commander = self.state.get_member(war.commander_id)
                if commander and not commander.is_dead:
                    old_office = commander.office
                    assigned_turn = war.commander_assigned_turn or (self.state.turn.turn_number - 1)
                    if old_office in ('proconsul', 'propraetor', 'consul', 'praetor'):
                        commander.add_office_history(old_office, assigned_turn, self.state.turn.turn_number)
                        commander.office = None
                        commander.is_absent = False
                        commander.update_influence()
                        self.state.log_event(
                            f"指挥官 {commander.name} 从战争 {war.name} 返回罗马",
                            extra={'type': 'commander_return', 'war_id': war.id, 'figure_id': commander.id}
                        )
                        print(f"      🔄 指挥官 {commander.name} 返回罗马")

        else:  # 战败
            war.status = WarStatus.DEFEATED
            print(f"   ❌ {war.name} lost! Defeat!")
            self.state.log_event(
                f"战争失败：{war.name}",
                extra={"war_id": war.id, "victory": False}
            )

        # --- 清理战争数据（无论胜负）---
        ms = self.state.get_military_system()
        if ms:
            ms.recall_from_war(war.id)

        # ===== 新增：召回指派给该战争的所有舰队 =====
        if self.state.naval_system:
            self.state.naval_system.recall_fleets_from_war(war.id)

        if war in self._active_wars:
            self._active_wars.remove(war)

        self._war_discard.append(war)

        war.commander_id = None
        war.legions_assigned = 0
        war.fleets_assigned = 0

        return result

    def apply_turn_penalties(self) -> List[str]:
        """应用所有活跃战争的拖延惩罚"""
        events = []
        for war in self._active_wars:
            if war.status == WarStatus.ACTIVE:
                war_events = war.apply_penalties(self.state)
                events.extend(war_events)
                war.duration += 1
                # ===== 新增日志：记录战争拖延惩罚 =====
                if war_events:
                    self.state.log_event(
                        f"战争 {war.name} 拖延惩罚",
                        extra={"war_id": war.id, "duration": war.duration, "penalties": war_events}
                    )
        return events

    # ========== 数据加载 ==========

    def check_triggers(self, current_year: int):
        """检查是否有战争到达触发年份，将其从 INACTIVE 转为 THREAT"""
        if not self.state.config.get("enable_threats", True):
            return
        for war in self._war_deck[:]:
            if war.status == WarStatus.INACTIVE and current_year >= war.start_year:
                war.status = WarStatus.THREAT
                war.threat_level = 1  # 现在可以通过 setter 赋值
                war._triggered_this_turn = True  # 标记为刚触发
                self._threats.append(war)
                self._war_deck.remove(war)
                print(f"   ⚠️ 外交冲突：{war.name} 开始威胁罗马")

    def escalate_threats(self):
        events = []
        for war in self._threats[:]:
            if war._triggered_this_turn:
                war._triggered_this_turn = False
                continue
            if war.auto_escalate:
                old_level = war.threat_level
                war.threat_level += war.escalate_rate
                # ----- 记录升级 -----
                self.state.log_event(
                    f"[DEBUG] escalate_threats: 战争 {war.id} 威胁等级 {old_level} -> {war.threat_level}",
                    level=logging.DEBUG,
                    extra={
                        "function": "escalate_threats",
                        "war_id": war.id,
                        "old_level": old_level,
                        "new_level": war.threat_level,
                        "action": "escalate"
                    }
                )
                if war.threat_level >= 3:
                    war.status = WarStatus.ACTIVE
                    war.activation_turn = self.state.turn.turn_number
                    self._active_wars.append(war)
                    self._threats.remove(war)
                    war.commander_id = None
                    # ----- 记录激活 -----
                    self.state.log_event(
                        f"[DEBUG] escalate_threats: 战争 {war.id} 激活为活跃",
                        level=logging.DEBUG,
                        extra={
                            "function": "escalate_threats",
                            "war_id": war.id,
                            "action": "activate",
                            "active_after": [w.id for w in self._active_wars],
                        }
                    )
                    events.append(f"⚔️ 战争爆发：{war.name}！")
                else:
                    level_names = ["", "外交冲突", "大军压境"]
                    events.append(f"⚠️ {war.name} 升级至：{level_names[war.threat_level]}")
        return events

    def load_wars_from_json(self, filename: str = "wars.json") -> List[War]:
        """从JSON加载战争卡数据"""
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / filename

        wars = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for war_data in data.get('wars', []):
                war = self._parse_war_data(war_data)
                wars.append(war)

        except FileNotFoundError:
            print(f"   ⚠️  War data file not found: {file_path}")
            # 创建默认测试战争
            wars = self._create_default_wars()
        except json.JSONDecodeError as e:
            print(f"   ⚠️  JSON parse error: {e}")
            wars = self._create_default_wars()

        self._war_deck = wars
        return wars

    def _parse_war_data(self, data: Dict[str, Any]) -> War:
        war_type_str = data.get('type', 'foreign').upper()
        try:
            war_type = WarType[war_type_str]
        except KeyError:
            war_type = WarType.FOREIGN

        war = War(
            id=data.get('id', f"war_{random.randint(1000, 9999)}"),
            name=data.get('name', 'Unknown War'),
            description=data.get('description', ''),
            war_type=war_type,
            start_year=data.get('start_year', 0),
            threat_level=data.get('threat_level', 0),
            auto_escalate=data.get('auto_escalate', True),
            escalate_rate=data.get('escalate_rate', 1),
            strength=data.get('strength', 5),
            naval_support_required=data.get('naval_required', False),  # 注意：这里可能复用原有字段，但为了清晰，使用原有字段名
            naval_strength=data.get('naval_strength', 0),
            land_battle=data.get('land_battle', True),
            disaster_numbers=data.get('disaster_numbers', [2, 3, 4]),
            standoff_numbers=data.get('standoff_numbers', [5, 6, 7, 8, 9]),
            rewards=data.get('rewards', {}),
            penalties=data.get('penalties', {}),
            is_imminent=data.get('imminent', False),
            matched_war_id=data.get('matched_war'),
            unlocked_provinces=data.get('unlocked_provinces', []),
            # 新增字段
            naval_required=data.get('naval_required', False),
            enemy_naval_current=data.get('enemy_naval_current', 0),
            enemy_naval_max=data.get('enemy_naval_max', 0),
            enemy_land_current=data.get('enemy_land_current', 0),
            enemy_land_max=data.get('enemy_land_max', 0),
            enemy_budget_initial=data.get('enemy_budget', 0),  # 注意 JSON 中是 enemy_budget
            enemy_recovery_per_turn=data.get('enemy_recovery_per_turn', 0),
            enemy_maintenance_cost_per_unit=data.get('enemy_maintenance_cost_per_unit', 0),
            sea_zone_id=data.get('sea_zone'),
            mission_type=data.get('mission_type', 'JOINT_INVASION'),
            rebellion_province_id=None,  # 起义战争没有此项
        )
        return war

    def _create_default_wars(self) -> List[War]:
        """创建默认测试战争（当JSON加载失败时）"""
        terms = TerminologyService.get()

        return [
            War(
                id="test_war_1",
                name="Gallic Raiders",
                description="Barbarian incursion from the north",
                war_type=WarType.BARBARIAN,
                strength=4,
                naval_support_required=False,
                rewards={'treasury': 25, 'influence': 1},
                penalties={'unrest_per_turn': 1},
            ),
            War(
                id="test_war_2",
                name="Pirate Fleet",
                description="Mediterranean pirates threaten trade",
                war_type=WarType.FOREIGN,
                strength=6,
                naval_support_required=True,
                naval_strength=3,
                rewards={'treasury': 40, 'influence': 2},
                penalties={'treasury_cost': 5},
            ),
            War(
                id="test_war_3",
                name="Provincial Revolt",
                description="Unrest in the provinces",
                war_type=WarType.PROVINCIAL,
                strength=8,
                rewards={'treasury': 60, 'influence': 3, 'unrest_reduction': 3},
                penalties={'unrest_per_turn': 2},
            ),
        ]

    # ========== 牌堆管理 ==========

    def shuffle_deck(self):
        """洗牌"""
        random.shuffle(self._war_deck)
        print("   🔀 War deck shuffled")

    def draw_war(self) -> Optional[War]:
        """抽取战争卡"""
        if not self._war_deck:
            # 牌堆空时，弃牌堆重洗
            if self._war_discard:
                print("   ♻️  Reshuffling discard pile...")
                self._war_deck = self._war_discard
                self._war_discard = []
                self.shuffle_deck()
            else:
                return None

        war = self._war_deck.pop()
        return war

    def check_imminent_wars(self) -> List[War]:
        """检查即将爆发的战争（预警）"""
        return [w for w in self._war_deck if w.is_imminent]

    # ========== 战争查询 ==========

    def get_active_wars(self) -> List[War]:
        """获取所有活跃战争"""
        return [w for w in self._active_wars if w.status == WarStatus.ACTIVE]

    # 在 WarSystem 类中
    def get_war_by_id(self, war_id: str) -> Optional[War]:
        """通过ID查找战争（搜索所有战争列表，包括停战列表）"""
        all_wars = self._war_deck + self._war_discard + self._active_wars + self._threats + self._truce_wars
        for war in all_wars:
            if war.id == war_id:
                return war
        return None

    def get_active_wars_without_commander(self) -> List[War]:
        """获取活跃战争中无指挥官的列表"""
        return [w for w in self._active_wars if w.status == WarStatus.ACTIVE and w.commander_id is None]

    # ========== 战争操作 ==========

    def assign_commander(self, war_id: str, commander_id: int, legions: int = 0, fleets: int = 0) -> bool:
        war = self.get_war_by_id(war_id)
        if not war or war.status != WarStatus.ACTIVE:
            return False
        if war.commander_id is not None:
            print(f"   ⚠️  Replacing commander on {war.name}")
        war.commander_id = commander_id
        war.legions_assigned = legions
        war.fleets_assigned = fleets
        war.set_commander_assigned_turn(self.state.turn.turn_number)  # 使用 setter
        terms = TerminologyService.get()
        print(f"   🎖️  {terms.commander} assigned to {war.name}")
        print(f"      Forces: {legions} {terms.legion}, {fleets} {terms.fleet}")
        return True

    def recall_commander(self, war_id: str) -> bool:
        """召回将领"""
        war = self.get_war_by_id(war_id)
        if not war:
            return False

        war.commander_id = None
        war.legions_assigned = 0
        war.fleets_assigned = 0
        return True

    # ========== 战争结算 ==========

    def check_war_victory_condition(self, war: War) -> bool:
        """检查战争胜利条件（简化版）"""
        return war.status == WarStatus.RESOLVED

    # ========== 与GameState集成 ==========

    def sync_to_state(self):
        """同步战争状态到GameState（用于保存/加载）"""
        # 将战争数据存入state的临时存储（第5阶段完善持久化）
        self.state._war_system_data = {
            'deck': [w.id for w in self._war_deck],
            'discard': [w.id for w in self._war_discard],
            'active': [w.id for w in self._active_wars],
        }

    def load_from_state(self):
        """从GameState恢复战争状态"""
        # 第5阶段完善
        pass

    def get_wars_needing_reassignment(self) -> List[War]:
        """获取需要重新指派的战争（指挥官伤亡或0军团）"""
        ms = self.state.get_military_system()
        result = []

        for war in self.get_active_wars():
            # 检查指挥官状态
            if war.commander_status != "active":
                result.append(war)
                continue

            # 检查军团数量
            if ms:
                legions = ms.get_legions_for_battle(war.id)
                if not legions:
                    result.append(war)

        return result