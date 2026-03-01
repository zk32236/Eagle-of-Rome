import pytest
from unittest.mock import MagicMock, patch
from src.core.entities.figure import Figure, ClassTier
from src.core.deciders.impl.auto_land_trade_decider import AutoLandTradeDecider
from src.core.game_state import GameState


class TestAutoLandTradeDecider:
    """测试自动土地交易决策器"""

    def test_decide_trade_success(self):
        """测试成功返回交易信息"""
        state = MagicMock(spec=GameState)
        noble = Figure(id=1, name="Noble", class_tier=ClassTier.NOBILE)
        noble._land_private = 5
        eques = Figure(id=2, name="Eques", class_tier=ClassTier.EQUES)
        state.get_living_members.return_value = [noble, eques]

        decider = AutoLandTradeDecider()
        with patch('random.choice', side_effect=[noble, eques]), \
             patch('random.randint', return_value=3):
            result = decider.decide_trade(state)

        assert result == (1, 2, 3)

    def test_decide_trade_no_nobles(self):
        """测试没有贵族时返回 None"""
        state = MagicMock(spec=GameState)
        eques = Figure(id=2, name="Eques", class_tier=ClassTier.EQUES)
        state.get_living_members.return_value = [eques]

        decider = AutoLandTradeDecider()
        result = decider.decide_trade(state)
        assert result is None

    def test_decide_trade_no_equites(self):
        """测试没有骑士时返回 None"""
        state = MagicMock(spec=GameState)
        noble = Figure(id=1, name="Noble", class_tier=ClassTier.NOBILE)
        state.get_living_members.return_value = [noble]

        decider = AutoLandTradeDecider()
        result = decider.decide_trade(state)
        assert result is None

    def test_decide_trade_noble_no_land(self):
        """测试贵族无私地时返回 None"""
        state = MagicMock(spec=GameState)
        noble = Figure(id=1, name="Noble", class_tier=ClassTier.NOBILE)
        noble._land_private = 0
        eques = Figure(id=2, name="Eques", class_tier=ClassTier.EQUES)
        state.get_living_members.return_value = [noble, eques]

        decider = AutoLandTradeDecider()
        with patch('random.choice', return_value=noble):
            result = decider.decide_trade(state)
        assert result is None

    def test_decide_trade_land_amount_random(self):
        """测试随机交易数量在合理范围内"""
        state = MagicMock(spec=GameState)
        noble = Figure(id=1, name="Noble", class_tier=ClassTier.NOBILE)
        noble._land_private = 10
        eques = Figure(id=2, name="Eques", class_tier=ClassTier.EQUES)
        state.get_living_members.return_value = [noble, eques]

        decider = AutoLandTradeDecider()
        with patch('random.choice', side_effect=[noble, eques]), \
             patch('random.randint', return_value=7) as mock_randint:
            result = decider.decide_trade(state)
            mock_randint.assert_called_once_with(1, 10)
            assert result == (1, 2, 7)