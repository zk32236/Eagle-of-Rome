import random
from typing import List, Dict, Optional
from core.entities import Senator, Faction
from core.game_state import GameState


class SimpleAI:
    """
    简单规则AI
    基于贪婪算法和随机性的基础AI
    """

    def select_candidate(self, senators: List[Senator], office: str) -> Senator:
        """
        选择候选人
        策略：优先选择影响力最高且军事/演说能力符合职位的元老
        """
        if office == "consul":
            # 执政官需要高影响力+高军事或高演说
            scored = []
            for s in senators:
                score = s.influence * 2 + s.military + s.oratory
                scored.append((score, s))
            scored.sort(reverse=True)
            return scored[0][1] if scored else senators[0]

        # 默认返回影响力最高的
        return max(senators, key=lambda s: s.influence)

    def decide_senate_vote(self, faction: Faction,
                           nominations: Dict[str, Senator],
                           state: GameState) -> Dict:
        """
        决定元老院投票策略
        返回: {"target_id": senator_id, "reason": str}
        """
        # 策略1：如果有本派系候选人，优先投给自己人
        if faction.id in nominations:
            own_candidate = nominations[faction.id]
            return {
                "target_id": own_candidate.id,
                "reason": "support_own_faction"
            }

        # 策略2：否则投给影响力最高的候选人（攀附强者）
        best_candidate = max(nominations.values(), key=lambda s: s.influence)

        # 策略3：小概率随机投票（模拟政治波动）
        if random.random() < 0.2:
            random_candidate = random.choice(list(nominations.values()))
            return {
                "target_id": random_candidate.id,
                "reason": "random_politics"
            }

        return {
            "target_id": best_candidate.id,
            "reason": "support_strongest"
        }

    def should_support_measure(self, faction: Faction, measure_type: str) -> bool:
        """
        决定是否支持某项提案
        """
        # 基础随机策略，后续可根据派系立场细化
        return random.random() > 0.3  # 70%概率支持