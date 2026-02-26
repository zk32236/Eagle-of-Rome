import random
from typing import List, Dict
from src.core.deciders.recruitment_decider import RecruitmentDecider
from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.game_state import GameState

class AutoRecruitmentDecider(RecruitmentDecider):
    """自动随机招募决策器：
        - 从广场中随机选择最多vacancies个人物（排除被本派系抛弃的）
        - 为每个人物生成随机出价金额，范围为1到派系私库当前金额之间
        - 若派系私库为0，则返回空字典
    """

    def decide_bids(self, faction: Faction, available_figures: List[Figure],
                    vacancies: int, state: GameState) -> Dict[int, int]:
        if faction.treasury <= 0 or vacancies <= 0:
            return {}

        # 排除被本派系抛弃的人物
        eligible = [fig for fig in available_figures
                    if getattr(fig, 'abandoned_by', None) != faction.id]

        if not eligible:
            return {}

        random.shuffle(eligible)
        selected = eligible[:vacancies]

        bids = {}
        for fig in selected:
            amount = random.randint(1, faction.treasury)
            bids[fig.id] = amount

        return bids