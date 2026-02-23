# src/core/scenario_loader.py - 修正版（元老分别拥有不同官职，骑士平民无官职）

import json
import random
from pathlib import Path
from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn


class ScenarioLoader:
    """场景加载器 - 支持配置化人物生成，派系数量可配置，元老各担一职，骑士平民无官职"""

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
        ScenarioLoader._initialize_faction_leaders(state)

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
        for f_data in factions_data:
            faction = Faction(
                id=f_data["id"],
                name=f_data["name"],
                treasury=f_data.get("treasury", 50),
                is_player=f_data.get("is_player", False)
            )
            state.add_faction(faction)

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

            nobles = []   # 元老
            equites = []  # 骑士
            plebs = []    # 平民

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

            # 为三个元老分配不同的官职历史
            if len(nobles) >= 3:
                # 随机打乱顺序，使官职分配随机
                random.shuffle(nobles)
                # 前执政官（需财务官→大法官→执政官链）
                nobles[0].add_office_history("quqaestor", -8)
                nobles[0].add_office_history("praetor", -5)
                nobles[0].add_office_history("consul", -2)
                nobles[0].charisma = max(nobles[0].charisma, 8)

                # 前大法官（需财务官→大法官链）
                nobles[1].add_office_history("quqaestor", -6)
                nobles[1].add_office_history("praetor", -3)
                nobles[1].management = max(nobles[1].management, 8)

                # 前财务官
                nobles[2].add_office_history("quqaestor", -4)
                nobles[2].strategy = max(nobles[2].strategy, 7)

            # 骑士和平民不添加任何官职历史

            # 合并所有人物并添加到游戏状态
            all_figures = nobles + equites + plebs
            for fig in all_figures:
                state.add_member(fig)
                if fig.id not in faction.member_ids:
                    faction.member_ids.append(fig.id)

    @staticmethod
    def _initialize_faction_leaders(state: GameState):
        for faction in state.factions.values():
            faction.update_faction_leader(state)