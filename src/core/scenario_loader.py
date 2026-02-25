# src/core/scenario_loader.py - 配置化版（支持动态派系，按权力分配历史官职，并根据官职设置初始私地）

import json
import random
from pathlib import Path
from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn,Province


class ScenarioLoader:
    """场景加载器 - 支持配置化人物生成，派系数量可配置，人物生成规则统一，按权力分配历史官职，并根据官职设置初始私地"""

    @staticmethod
    def load_scenario(state: GameState, scenario_file: str = "mvp_test.json") -> None:
        state.reset()
        base_path = Path(__file__).parent.parent.parent
        file_path = base_path / "data" / "scenarios" / scenario_file
        config = None
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ 配置文件加载失败: {e}，使用默认配置")
                config = None
        else:
            print(f"⚠️ 配置文件不存在: {file_path}，使用默认配置")
        if config is None:
            config = ScenarioLoader._get_default_config()
        start_year = config.get("start_year", -264)
        state.turn = GameTurn(turn_number=1, year=start_year)
        ScenarioLoader._load_factions(state, config)
        ScenarioLoader._load_figures(state, config)
        state.treasury = config.get("initial_state", {}).get("treasury", 100)
        print("DEBUG: economic_rules =", config.get("economic_rules"))
        state._national_public_land = state.config.get("economic_rules.initial_national_public_land", 1000)
        ScenarioLoader._initialize_faction_leaders(state)

        # 意大利（国家公地） - ID 0
        italy = Province(0, "意大利", 0)  # total_land 设为0，后续手动设置公地
        italy._land_public = state.get_national_public_land()  # 从 state 获取当前国家公地
        italy._land_private = 0
        state.add_province(italy)

        provinces_data = [
            {"id": 1, "name": "西西里", "total_land": 1000},
            {"id": 2, "name": "撒丁尼亚", "total_land": 800},
            {"id": 3, "name": "科西嘉", "total_land": 600},
        ]
        for p in provinces_data:
            province = Province(p["id"], p["name"], p["total_land"])
            state.add_province(province)

    @staticmethod
    def _get_default_config() -> dict:
        return {
            "scenario_name": "Default Scenario",
            "start_year": -264,
            "initial_state": {
                "treasury": 100,
                "factions": [
                    {"id": "optimates", "name": "Optimates", "treasury": 50, "is_player": True},
                    {"id": "populares", "name": "Populares", "treasury": 50, "is_player": False},
                    {"id": "equites", "name": "Equites", "treasury": 50, "is_player": False}
                ],
                "figure_generation": {
                    "per_faction": {
                        "nobile": {"count": 3, "age_range": [35, 50]},
                        "eques": {"count": 2, "age_range": [25, 40]},
                        "plebeian": {"count": 1, "age_range": [25, 35]}
                    }
                }
            }
        }

    @staticmethod
    def _load_factions(state: GameState, config: dict):
        factions_data = config["initial_state"]["factions"]
        # 获取配置中的初始资金，默认10
        initial_treasury = state.get_economic_rule("faction_initial_treasury", 10)
        for f_data in factions_data:
            faction = Faction(
                id=f_data["id"],
                name=f_data["name"],
                treasury=initial_treasury,  # 使用配置值
                is_player=f_data.get("is_player", False)
            )
            state.add_faction(faction)

    @staticmethod
    def _set_land_by_office(figure: Figure):
        """根据人物的最高官职设置私地数量"""
        if figure.class_tier == ClassTier.NOBILE:
            # 找出最高官职（按执政官 > 大法官 > 财务官）
            highest = None
            for term in figure.office_history:
                if term.office_type == "consul":
                    highest = "consul"
                    break
                elif term.office_type == "praetor" and highest != "consul":
                    highest = "praetor"
                elif term.office_type == "quaestor" and highest not in ("consul", "praetor"):
                    highest = "quaestor"
            if highest == "consul":
                figure._land_private = 3
            elif highest == "praetor":
                figure._land_private = 2
            elif highest == "quaestor":
                figure._land_private = 1
            else:
                # 无历史，随机1-3
                figure._land_private = random.randint(1, 3)
        else:
            # 骑士和平民无私地
            figure._land_private = 0

    @staticmethod
    def _load_figures(state: GameState, config: dict):
        figure_generation = config["initial_state"].get("figure_generation", {})
        per_faction = figure_generation.get("per_faction", {})

        target_nobile = per_faction.get("nobile", {}).get("count", 3)
        target_eques = per_faction.get("eques", {}).get("count", 2)
        target_pleb = per_faction.get("plebeian", {}).get("count", 1)

        age_nobile = per_faction.get("nobile", {}).get("age_range", [35, 50])
        age_eques = per_faction.get("eques", {}).get("age_range", [25, 40])
        age_pleb = per_faction.get("plebeian", {}).get("age_range", [25, 35])

        figure_id = 1
        factions_data = config["initial_state"]["factions"]

        for f_data in factions_data:
            faction_id = f_data["id"]
            faction = state.get_faction(faction_id)
            if not faction:
                continue

            nobles = []
            equites = []
            plebs = []

            # 生成贵族
            for _ in range(target_nobile):
                age = random.randint(age_nobile[0], age_nobile[1])
                fig = Figure.create_nobile(figure_id, faction_id, age)
                nobles.append(fig)
                figure_id += 1

            # 生成骑士
            for _ in range(target_eques):
                age = random.randint(age_eques[0], age_eques[1])
                fig = Figure.create_eques(figure_id, faction_id, age)
                equites.append(fig)
                figure_id += 1

            # 生成平民
            for _ in range(target_pleb):
                age = random.randint(age_pleb[0], age_pleb[1])
                fig = Figure.create_plebeian(figure_id, faction_id, age)
                plebs.append(fig)
                figure_id += 1

            # 为贵族中权力最高者添加执政官历史（确保有历史人物）
            if nobles:
                nobles_sorted = sorted(nobles, key=lambda f: f.influence, reverse=True)
                # 前执政官（权力最高）
                ex_consul = nobles_sorted[0]
                ex_consul.add_office_history("quqaestor", -8)
                ex_consul.add_office_history("praetor", -5)
                ex_consul.add_office_history("consul", -2)
                ex_consul.charisma = max(ex_consul.charisma, 8)

                # 前大法官（权力次高）
                if len(nobles_sorted) >= 2:
                    ex_praetor = nobles_sorted[1]
                    ex_praetor.add_office_history("quqaestor", -6)
                    ex_praetor.add_office_history("praetor", -3)
                    ex_praetor.intelligence = max(ex_praetor.intelligence, 8)  # 原 management

                # 前财务官（权力第三高）
                if len(nobles_sorted) >= 3:
                    ex_quaestor = nobles_sorted[2]
                    ex_quaestor.add_office_history("quqaestor", -4)
                    ex_quaestor.martial = max(ex_quaestor.martial, 7)  # 原 strategy

            # 设置私地：根据官职或随机
            all_figures = nobles + equites + plebs
            for fig in all_figures:
                ScenarioLoader._set_land_by_office(fig)

            # 初始化影响力
            for fig in all_figures:
                fig.update_influence()

            # 添加到游戏状态
            for fig in all_figures:
                state.add_member(fig)
                if fig.id not in faction.member_ids:
                    faction.member_ids.append(fig.id)

    @staticmethod
    def _initialize_faction_leaders(state: GameState):
        for faction in state.factions.values():
            faction.update_faction_leader(state)