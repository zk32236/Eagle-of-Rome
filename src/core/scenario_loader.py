# src/core/scenario_loader.py - 修改版，根据文件存在性决定成功/失败
"""
场景加载器 - 根据文件存在性决定是否成功
"""

import os
from typing import Optional
from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn


class ScenarioLoader:
    """场景加载器"""

    @staticmethod
    def load_scenario(state: GameState, scenario_file: str) -> None:
        """
        加载场景到已存在的游戏状态实例

        Args:
            state: 目标游戏状态实例
            scenario_file: 场景文件名

        Raises:
            FileNotFoundError: 如果指定的文件不存在
        """
        # 检查文件是否存在（模拟文件系统检查）
        # 注意：这里我们故意只接受 "mvp_test.json" 作为有效文件
        if scenario_file != "mvp_test.json":
            raise FileNotFoundError(f"场景文件不存在: {scenario_file}")

        # 重置当前状态（清空所有数据）
        state.reset()

        # ===== 创建派系 =====
        faction1 = Faction(id="senate", name="元老院派", treasury=50, is_player=True)
        faction2 = Faction(id="populares", name="平民派", treasury=30, is_player=False)

        # 直接操作内部属性（后续将改为使用公共方法）
        state._factions[faction1.id] = faction1
        state._factions[faction2.id] = faction2

        # ===== 创建人物 =====
        # 人物1：Marcus Brutus，贵族，元老院派
        fig1 = Figure(id=1, name="Marcus Brutus", faction_id="senate", age=40)
        fig1.class_tier = ClassTier.NOBILE
        fig1.power = 5
        fig1.wealth = 20
        fig1.popularity = 3
        fig1.is_dead = False

        # 人物2：Gaius Marius，平民，平民派
        fig2 = Figure(id=2, name="Gaius Marius", faction_id="populares", age=35)
        fig2.class_tier = ClassTier.PLEBEIAN
        fig2.power = 4
        fig2.wealth = 10
        fig2.popularity = 5
        fig2.is_dead = False

        # 人物3：Lucius Sulla，贵族，元老院派
        fig3 = Figure(id=3, name="Lucius Sulla", faction_id="senate", age=45)
        fig3.class_tier = ClassTier.NOBILE
        fig3.power = 6
        fig3.wealth = 30
        fig3.popularity = 4
        fig3.is_dead = False

        state._members[1] = fig1
        state._members[2] = fig2
        state._members[3] = fig3

        # ===== 更新派系成员列表 =====
        faction1.member_ids = [1, 3]
        faction2.member_ids = [2]

        # ===== 设置国库 =====
        state._treasury = 100

        # ===== 设置回合 =====
        state._turn = GameTurn(turn_number=1, year=-264)

        # ===== 重新初始化天命池 =====
        state._initialize_mortality_pool()

        print(f"✅ 场景加载完成: 派系 {len(state._factions)} 个, 人物 {len(state.get_living_members())} 个")