import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock
from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.province import Province
from src.ui.commands.phase_mortality import MortalityCommand
from src.ui.commands.phase_revenue import RevenueCommand


class TestDisasterEvent(unittest.TestCase):

    def setUp(self):
        self.test_config = {
            "mortality_rules": {
                "event_deck": [{"name": "无妄天灾", "effect": "disaster", "weight": 1}],
                "event_draw_count": 1,
                "disaster_base_loss": 0.5,
                "disaster_mitigation_factor": 0.1
            },
            "economic_rules": {
                "land_price_per_unit": 10,
                "public_land_income_rate": 0.01,
                "national_public_land_tax_rate": 0.1,
                "private_land_income_rate": 0.05,
                "faction_tax_rate": 0.1,
                "national_opex_rate": 0
            }
        }
        self.state = GameState.create_for_testing(self.test_config)
        self.state.turn = GameTurn(turn_number=1, year=-264)

        # 添加已征服行省
        self.italy = Province(0, "意大利", 6000, conquered=True)
        self.italy._infrastructure["roads"] = 2
        self.state.add_province(self.italy)

        self.sicily = Province(1, "西西里", 1000, conquered=True)
        self.sicily._infrastructure["roads"] = 1
        self.state.add_province(self.sicily)

        self.unconquered = Province(2, "未征服", 500, conquered=False)
        self.state.add_province(self.unconquered)

        # 添加人物
        from src.core.entities.figure import Figure, ClassTier
        from src.core.entities.entities import Faction
        faction = Faction("test", "测试派")
        self.state.add_faction(faction)
        self.fig = Figure(101, "测试人物", faction_id="test", age=30)
        self.fig._land_private = 100
        self.fig.class_tier = ClassTier.NOBILE
        self.state.add_member(self.fig)
        faction.member_ids = [101]

        # 设置国家公地
        self.state._national_public_land = 1000

    @patch.object(MortalityCommand, '_load_disasters')
    @patch("random.choice")
    def test_disaster_affects_italy(self, mock_random_choice, mock_load_disasters):
        """测试受灾行省为意大利时，私地收入和国家公地收益减少"""
        disaster_data = {
            "id": "test",
            "name": "Test Disaster",
            "base_loss": 0.5,
            "mitigation_infra": "roads",
            "mitigation_factor": 0.1
        }
        mock_load_disasters.return_value = [disaster_data]
        mock_random_choice.side_effect = [self.italy, disaster_data]

        cmd_m = MortalityCommand(self.state)
        cmd_m.execute([])

        self.assertIn("disaster", self.state._active_events)  # 直接检查私有字段
        disaster_info = self.state._active_events["disaster"]
        self.assertEqual(disaster_info["province_id"], 0)
        self.assertAlmostEqual(disaster_info["loss_ratio"], 0.4, places=2)

        self.state._executed_phases.add("mortality")
        cmd_r = RevenueCommand(self.state)
        f = io.StringIO()
        with redirect_stdout(f):
            cmd_r.execute([])

        # 国家公地收益：原10，损失40%后为6，国库从0变为6
        self.assertEqual(self.state.treasury, 6)
        # 私地收入：原50，损失40%后30，抽成10%得27
        self.assertEqual(self.fig.wealth, 27)

    @patch.object(MortalityCommand, '_load_disasters')
    @patch("random.choice")
    def test_disaster_affects_sicily(self, mock_random_choice, mock_load_disasters):
        """测试受灾行省为西西里时，包税合同利润减少"""
        disaster_data = {
            "id": "test",
            "name": "Test Disaster",
            "base_loss": 0.5,
            "mitigation_infra": "roads",
            "mitigation_factor": 0.1
        }
        mock_load_disasters.return_value = [disaster_data]
        mock_random_choice.side_effect = [self.sicily, disaster_data]

        # 将人物私地设为0，仅测试合同利润
        self.fig._land_private = 0

        # 创建包税合同，直接设置为ACTIVE并设置必要字段
        from src.core.entities.contract import Contract, ContractType, ContractStatus
        contract = self.state.create_contract(
            ContractType.TAX_FARMING,
            province_id=1,
            base_cost=100,
            current_turn=self.state.turn.turn_number - 1
        )
        contract.status = ContractStatus.ACTIVE
        contract.awarded_to = 101
        contract._winning_bid = {"bidder_id": 101, "amount": 100}
        contract._contract_price = 100  # 合同价
        contract._profit_rate = 0.5  # 利润率 50%
        contract.remaining_years = 5
        self.fig.add_contract(contract.id)
        self.sicily.bind_tax_contract(contract.id)

        cmd_m = MortalityCommand(self.state)
        cmd_m.execute([])

        self.assertIn("disaster", self.state._active_events)
        disaster_info = self.state._active_events["disaster"]
        self.assertEqual(disaster_info["province_id"], 1)
        self.assertAlmostEqual(disaster_info["loss_ratio"], 0.45, places=2)

        self.state._executed_phases.add("mortality")
        initial_treasury = self.state.treasury
        initial_wealth = self.fig.wealth

        cmd_r = RevenueCommand(self.state)
        cmd_r.execute([])

        # 国库变化：国家公地收益10 + 合同价100 = 110
        expected_treasury_change = 10 + 100
        self.assertEqual(self.state.treasury - initial_treasury, expected_treasury_change)

        # 骑士财富变化：利润 = contract_price * profit_rate = 100 * 0.5 = 50，扣除派系抽成10%得45
        expected_wealth_gain = int(100 * 0.5 * (1 - 0.1))  # 45
        self.assertEqual(self.fig.wealth - initial_wealth, expected_wealth_gain)