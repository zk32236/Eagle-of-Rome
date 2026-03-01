import random
from typing import Optional, Tuple
from src.core.deciders.land_proposal_decider import LandProposalDecider
from src.core.game_state import GameState

class AutoLandProposalDecider(LandProposalDecider):
    """自动土地法案提案决策器"""

    def __init__(self, target_faction: str, proposal_type: str):
        """
        :param target_faction: 对应的派系ID，如 'populares' 或 'optimates'
        :param proposal_type: 法案类型，'distribution' 或 'sale'
        """
        self.target_faction = target_faction
        self.proposal_type = proposal_type

    def decide_proposal(self, faction_id: str, state: GameState) -> Optional[Tuple[str, float]]:
        if faction_id != self.target_faction:
            return None

        config = state.config.get("political_rules.land_proposal", {})
        chance = config.get(f"{self.proposal_type}_chance", 0.3)
        if random.random() >= chance:
            return None

        min_pct = config.get("land_percent_min", 0.05)
        max_pct = config.get("land_percent_max", 0.10)
        percent = random.uniform(min_pct, max_pct)
        return (self.proposal_type, percent)