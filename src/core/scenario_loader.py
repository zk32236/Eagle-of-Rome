# src/core/scenario_loader.py - MVP 0.4.5 配置化版

import json
import random
from pathlib import Path
from core.game_state import GameState
from core.entities import Figure, GameTurn, Faction


class ScenarioLoader:
    """场景加载器 - 支持配置化人物生成"""

    # 默认人物生成配置
    DEFAULT_FIGURE_CONFIG = {
        "per_faction": {
            "nobile": {
                "count": 3,
                "age_range": [35, 50]
            },
            "eques": {
                "count": 2,
                "age_range": [25, 40]
            },
            "plebeian": {
                "count": 1,
                "age_range": [25, 35]
            }
        }
    }

    @staticmethod
    def load_scenario(scenario_file: str) -> GameState:
        """
        加载场景配置文件

        Args:
            scenario_file: 场景文件名（如 "mvp_test.json"）

        Returns:
            GameState: 初始化完成的游戏状态
        """
        base_path = Path(__file__).parent.parent.parent
        file_path = base_path / "data" / "scenarios" / scenario_file

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"❌ Scenario file not found: {file_path}")
            raise
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in scenario file: {e}")
            raise

        # 初始化游戏状态
        state = GameState()
        state.reset()

        # 设置起始年份
        start_year = data.get("start_year", -264)
        state.turn = GameTurn(turn_number=1, year=start_year)

        # 加载派系
        ScenarioLoader._load_factions(state, data)

        # 加载人物（配置化生成）
        ScenarioLoader._load_figures(state, data)

        # 设置国库
        state.treasury = data["initial_state"].get("treasury", 100)

        # 初始化派系领袖
        ScenarioLoader._initialize_faction_leaders(state)

        # 打印加载信息
        ScenarioLoader._print_load_info(state, data)

        return state

    @staticmethod
    def _load_factions(state: GameState, data: dict):
        """加载派系"""
        for faction_data in data["initial_state"]["factions"]:
            faction = Faction(
                id=faction_data["id"],
                name=faction_data["name"],
                treasury=faction_data.get("treasury", 50),
                is_player=faction_data.get("is_player", False)
            )
            state.add_faction(faction)

    @staticmethod
    def _load_figures(state: GameState, data: dict):
        """加载人物（配置化生成，含初始公职历史）"""

        # 获取人物生成配置
        figure_config = data["initial_state"].get("figure_generation", {})
        per_faction_config = figure_config.get("per_faction", {})

        # 合并配置
        generation_rules = {
            "nobile": {**ScenarioLoader.DEFAULT_FIGURE_CONFIG["per_faction"]["nobile"],
                       **per_faction_config.get("nobile", {})},
            "eques": {**ScenarioLoader.DEFAULT_FIGURE_CONFIG["per_faction"]["eques"],
                      **per_faction_config.get("eques", {})},
            "plebeian": {**ScenarioLoader.DEFAULT_FIGURE_CONFIG["per_faction"]["plebeian"],
                         **per_faction_config.get("plebeian", {})}
        }

        figure_id = 1

        for faction_data in data["initial_state"]["factions"]:
            faction_id = faction_data["id"]
            faction = state.get_faction(faction_id)

            if not faction:
                continue

            figures = []

            # ===== 先生成3名有公职历史的人物（确保第一回合有候选人）=====

            # 1. 前执政官（贵族，曾任执政官，需要曾任大法官）
            # 先创建曾任大法官的历史，再添加执政官历史
            ex_consul = Figure.create_nobile(figure_id, faction_id, age=45)
            ex_consul.add_office_history("quqaestor", -8)  # 先当财务官
            ex_consul.add_office_history("praetor", -5)  # 再当大法官
            ex_consul.add_office_history("consul", -2)  # 最后执政官（刚卸任）
            ex_consul.charisma = max(ex_consul.charisma, 8)  # 高魅力
            figures.append(ex_consul)
            figure_id += 1

            # 2. 前大法官（骑士或贵族，曾任大法官，需要曾任财务官）
            ex_praetor = Figure.create_eques(figure_id, faction_id, age=38)
            ex_praetor.add_office_history("quqaestor", -6)  # 先当财务官
            ex_praetor.add_office_history("praetor", -3)  # 再大法官（刚卸任）
            ex_praetor.management = max(ex_praetor.management, 8)  # 高智略
            figures.append(ex_praetor)
            figure_id += 1

            # 3. 前财务官（平民或骑士，曾任财务官）
            if random.random() > 0.5:
                ex_quaestor = Figure.create_eques(figure_id, faction_id, age=33)
            else:
                ex_quaestor = Figure.create_plebeian(figure_id, faction_id, age=33)
            ex_quaestor.add_office_history("quqaestor", -4)  # 财务官（刚卸任）
            ex_quaestor.strategy = max(ex_quaestor.strategy, 7)  # 高军略
            figures.append(ex_quaestor)
            figure_id += 1

            # ===== 再按配置生成剩余人物 =====

            # 计算还需生成的人数（总配置数 - 3名历史人物）
            total_nobile = generation_rules["nobile"]["count"]
            total_eques = generation_rules["eques"]["count"]
            total_pleb = generation_rules["plebeian"]["count"]

            # 已生成：1贵族(执政官) + 1骑士(大法官) + 1平民/骑士(财务官)
            remaining_nobile = max(0, total_nobile - 1)  # 已生成1贵族
            remaining_eques = max(0, total_eques - 1)  # 已生成1骑士（大法官）
            remaining_pleb = max(0, total_pleb - 1)  # 可能已生成1平民

            # 如果财务官也是骑士，骑士数再减1
            if ex_quaestor.class_tier.value == "eques":
                remaining_eques = max(0, remaining_eques - 1)
            else:
                remaining_pleb = max(0, remaining_pleb - 1)

            # 生成剩余贵族
            nobile_rule = generation_rules["nobile"]
            for i in range(remaining_nobile):
                age_range = nobile_rule.get("age_range", [35, 50])
                age = random.randint(age_range[0], age_range[1])
                figure = Figure.create_nobile(figure_id, faction_id, age)
                figures.append(figure)
                figure_id += 1

            # 生成剩余骑士
            eques_rule = generation_rules["eques"]
            for i in range(remaining_eques):
                age_range = eques_rule.get("age_range", [25, 40])
                age = random.randint(age_range[0], age_range[1])
                figure = Figure.create_eques(figure_id, faction_id, age)
                figures.append(figure)
                figure_id += 1

            # 生成剩余平民
            pleb_rule = generation_rules["plebeian"]
            for i in range(remaining_pleb):
                age_range = pleb_rule.get("age_range", [25, 35])
                age = random.randint(age_range[0], age_range[1])
                figure = Figure.create_plebeian(figure_id, faction_id, age)
                figures.append(figure)
                figure_id += 1

            # 添加到游戏状态
            for figure in figures:
                state.add_member(figure)
                if figure.id not in faction.member_ids:
                    faction.member_ids.append(figure.id)

            # 输出该派系初始公职配置
            print(f"   {faction.name}: Ex-Consul({ex_consul.name}), "
                  f"Ex-Praetor({ex_praetor.name}), "
                  f"Ex-Quaestor({ex_quaestor.name})")

    @staticmethod
    def _initialize_faction_leaders(state: GameState):
        """初始化派系领袖（权力最高者）"""
        for faction in state.factions.values():
            leader = faction.update_faction_leader(state)
            if leader:
                print(f"   👑 {faction.name} leader: {leader.name} (Power: {leader.power})")

    @staticmethod
    def _print_load_info(state: GameState, data: dict):
        """打印加载信息"""
        print(f"\n✅ Scenario loaded: {data.get('scenario_name', 'Unknown')}")
        print(f"   Year: {abs(data.get('start_year', -264))} BC")
        print(f"   Active figures: {len(state.get_living_members())}/300")

        # 显示配置的人物生成规则
        figure_config = data["initial_state"].get("figure_generation", {})
        per_faction = figure_config.get("per_faction", {})

        nobles = per_faction.get("nobile", {}).get("count", 3)
        equites = per_faction.get("eques", {}).get("count", 2)
        plebs = per_faction.get("plebeian", {}).get("count", 1)
        total = nobles + equites + plebs

        print(f"   Generation config: {nobles}🏛️ {equites}💰 {plebs}👤 = {total}/faction")

        # 显示各派系详情
        print(f"\n   Faction Details:")
        for faction in state.factions.values():
            members = faction.get_members(state)

            # 统计各阶层
            f_nobles = sum(1 for m in members if m.class_tier.value == "nobile")
            f_equites = sum(1 for m in members if m.class_tier.value == "eques")
            f_plebs = sum(1 for m in members if m.class_tier.value == "plebeian")

            # 统计权力
            total_power = sum(m.power for m in members)

            # 获取领袖
            leader = faction.get_leader(state)
            leader_name = leader.name if leader else "None"
            leader_office = ""
            if leader and leader.office:
                office_emoji = {"consul": "🏛️", "praetor": "⚖️", "quqaestor": "💰"}.get(leader.office, "")
                leader_office = f" {office_emoji}{leader.office}"

            # 玩家标记
            player_mark = "[PLAYER]" if faction.is_player else ""

            print(f"      {faction.name} {player_mark}")
            print(f"         Members: {f_nobles}🏛️ {f_equites}💰 {f_plebs}👤 | "
                  f"Power: {total_power} | Leader: {leader_name}{leader_office}")

        print()  # 空行分隔


# 便捷加载函数
def load_scenario(scenario_file: str = "mvp_test.json") -> GameState:
    """便捷加载场景"""
    return ScenarioLoader.load_scenario(scenario_file)