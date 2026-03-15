#src/core/deciders/impl/
import random
import logging
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
            # ===== 新增 DEBUG 日志 =====
            if state:
                state.log_event(
                    f"RecruitmentDecider: 派系 {faction.name} 国库 {faction.treasury} 空缺 {vacancies}，无法出价",
                    level=logging.DEBUG,
                    extra={"faction_id": faction.id, "treasury": faction.treasury, "vacancies": vacancies}
                )
            return {}

        # 排除被本派系抛弃的人物
        eligible = [fig for fig in available_figures
                    if getattr(fig, 'abandoned_by', None) != faction.id]

        # ===== 新增 DEBUG 日志 =====
        if state:
            state.log_event(
                f"RecruitmentDecider: 派系 {faction.name} 广场可用 {len(available_figures)} 人，排除后 {len(eligible)} 人，空缺 {vacancies}",
                level=logging.DEBUG,
                extra={"faction_id": faction.id, "available": len(available_figures), "eligible": len(eligible), "vacancies": vacancies}
            )

        if not eligible:
            return {}

        random.shuffle(eligible)
        selected = eligible[:vacancies]

        bids = {}
        for fig in selected:
            amount = random.randint(1, faction.treasury)
            bids[fig.id] = amount

        # ===== 新增 DEBUG 日志 =====
        if state:
            state.log_event(
                f"RecruitmentDecider: 派系 {faction.name} 决定出价 {len(bids)} 人，总预算 {sum(bids.values())}",
                level=logging.DEBUG,
                extra={"faction_id": faction.id, "bid_count": len(bids), "total_bid": sum(bids.values())}
            )

        return bids