"""
GameState 手动/边界测试（补充）
涵盖 T1-3 指令中建议的边界场景
"""

import pytest
from src.core.game_state import GameState
from src.core.entities.entities import Province
from src.core.entities.contract import ContractType


class TestGameStateManual:
    """GameState 边界测试"""

    def setup_method(self):
        """每个测试前创建新的 GameState 实例"""
        self.state = GameState.create_for_testing({})

    # ---------- 行省管理边界 ----------
    def test_add_duplicate_province(self):
        """测试添加重复行省（后添加的应覆盖前者）"""
        province1 = Province(1, "西西里", 1000)
        province2 = Province(1, "撒丁尼亚", 500)  # 相同ID

        self.state.add_province(province1)
        self.state.add_province(province2)

        retrieved = self.state.get_province(1)
        assert retrieved is province2  # 后添加的覆盖前者
        assert retrieved.name == "撒丁尼亚"

    def test_get_nonexistent_province(self):
        """获取不存在的行省返回 None"""
        assert self.state.get_province(999) is None

    def test_get_nonexistent_contract(self):
        """获取不存在的合同返回 None"""
        assert self.state.get_contract(999) is None

    # ---------- 合同创建边界 ----------
    def test_create_contract_with_invalid_province_id(self):
        """创建合同时传入不存在的 province_id（无校验，合同仍可创建）"""
        contract = self.state.create_contract(
            contract_type=ContractType.TAX_FARMING,
            province_id=999,   # 不存在的 ID
            base_cost=100,
            current_turn=5
        )
        assert contract.id == 1
        assert contract.province_id == 999  # 允许创建

    # ---------- get_province_contract 边界 ----------
    def test_get_province_contract_invalid_type(self):
        """传入无效的 ContractType 应返回 None"""
        province = Province(1, "西西里", 1000)
        self.state.add_province(province)

        # 传入 None 或非法类型（这里用字符串模拟，但类型系统会阻止）
        # 实际上 get_province_contract 参数类型为 ContractType，传入非法枚举会引发 TypeError
        # 但我们可以测试传入未绑定的类型
        assert self.state.get_province_contract(1, ContractType.TAX_FARMING) is None
        # 即使类型正确，未绑定时也返回 None

    # ---------- 返回列表的副本机制 ----------
    def test_get_all_provinces_returns_copy(self):
        """修改返回的列表不应影响内部字典"""
        province1 = Province(1, "西西里", 1000)
        province2 = Province(2, "撒丁尼亚", 500)
        self.state.add_province(province1)
        self.state.add_province(province2)

        provinces_copy = self.state.get_all_provinces()
        provinces_copy.clear()
        assert len(self.state.get_all_provinces()) == 2  # 内部不变

    def test_get_all_contracts_returns_copy(self):
        """修改返回的列表不应影响内部字典"""
        self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)
        self.state.create_contract(ContractType.PUBLIC_WORKS, 2, 200, 5)

        contracts_copy = self.state.get_all_contracts()
        contracts_copy.clear()
        assert len(self.state.get_all_contracts()) == 2

    # ---------- reset 行为 ----------
    def test_reset_twice(self):
        """连续调用两次 reset，状态保持一致"""
        province = Province(1, "西西里", 1000)
        self.state.add_province(province)
        self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)

        self.state.reset()
        first_state = (self.state._provinces.copy(), self.state._contracts_dict.copy(),
                       self.state._public_land_total, self.state._contract_id_counter)

        self.state.reset()
        second_state = (self.state._provinces.copy(), self.state._contracts_dict.copy(),
                        self.state._public_land_total, self.state._contract_id_counter)

        assert first_state == second_state

    # ---------- 全局公地更新 ----------
    def test_public_land_updates_correctly(self):
        """添加/移除行省时全局公地总数自动更新"""
        province1 = Province(1, "西西里", 1000)  # 公地 600
        province2 = Province(2, "撒丁尼亚", 500)  # 公地 300

        self.state.add_province(province1)
        assert self.state._public_land_total == 600

        self.state.add_province(province2)
        assert self.state._public_land_total == 900

        # 移除行省（直接操作内部字典模拟，因为 GameState 没有提供 remove 方法）
        # 但 reset 会清空
        self.state.reset()
        assert self.state._public_land_total == 0

    # ---------- 合同 ID 自增 ----------
    def test_contract_id_auto_increment(self):
        """验证合同 ID 连续自增"""
        c1 = self.state.create_contract(ContractType.TAX_FARMING, 1, 90, 5)
        c2 = self.state.create_contract(ContractType.PUBLIC_WORKS, 2, 200, 5)
        c3 = self.state.create_contract(ContractType.TAX_FARMING, 3, 80, 5)

        assert c1.id == 1
        assert c2.id == 2
        assert c3.id == 3