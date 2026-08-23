# src/tests/test_api/test_wpe_tax_farming_determinism.py
"""
WP-E（GUI-BETA-R1）E-G7-12：tax-farming 收入确定性证明测试（T-6）。

G1 实证：出现/消失机制完全由合同状态迁移驱动
（BUDGETED→ACTIVE 出现；ACTIVE→EXPIRED / remaining_years 归零 / 中标者死亡 → 消失；
economic_service.py:247-270 仅 ACTIVE 合同）。UI 显隐 = contract_rows.length > 0
（同一权威 state + 同一刷新点 → 确定性一致）。

三态确定性（零产品代码变更，A7.3）：
- no-contract：无 ACTIVE 合同 → collect_contract_revenues 空 rows
- active：ACTIVE 合同 → 有 rows
- expiry-removal：合同过期后（ACTIVE→EXPIRED）→ 空 rows
- 同 state 重入 → 同 rows（确定性）
"""
import pytest

from src.core.game_state import GameState
from src.core.entities.entities import GameTurn
from src.core.entities.contract import ContractType, ContractStatus
from src.core.service.economic_service import EconomicService


def _make_state(turn_number=5):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=turn_number, year=-260)
    return state


def _make_active_contract(state, contract_type=ContractType.TAX_FARMING):
    contract = state.create_contract(contract_type, 1, 100, 1)
    contract.status = ContractStatus.ACTIVE
    contract._contract_price = 90
    contract._profit_rate = 0.2
    contract._tax_rate = 0.12
    contract.remaining_years = 3
    contract.awarded_to = 1
    # _settle_tax_farming_contract 需要 winning_bid.bidder_id + 存活 figure
    contract._winning_bid = {"bidder_id": 1, "amount": 90, "tax_rate": 0.12}
    if state.get_member(1) is None:
        from src.core.entities.figure import Figure
        state.add_member(Figure(id=1, name="Bidder", wealth=1000))
    return contract


def test_no_contract_empty_rows():
    """no-contract 态：无 ACTIVE 合同 → rows 空（不出现）。"""
    state = _make_state()
    service = EconomicService(state)
    rows = service.collect_contract_revenues(faction_tax_collected={}, tax_rate=0.1)
    assert rows == []


def test_active_contract_produces_rows():
    """active 态：ACTIVE 合同 → rows 非空（出现）。"""
    state = _make_state()
    _make_active_contract(state)
    service = EconomicService(state)
    rows = service.collect_contract_revenues(faction_tax_collected={}, tax_rate=0.1)
    assert len(rows) >= 1


def test_expiry_removal_empties_rows():
    """expiry-removal 态：ACTIVE→EXPIRED → rows 空（消失）。"""
    state = _make_state()
    contract = _make_active_contract(state)
    service = EconomicService(state)
    assert len(service.collect_contract_revenues(faction_tax_collected={}, tax_rate=0.1)) >= 1

    contract.terminate()  # ACTIVE → EXPIRED（terminate 是 ACTIVE 合同的有效过期路径）
    rows = service.collect_contract_revenues(faction_tax_collected={}, tax_rate=0.1)
    assert rows == []


def test_same_state_reentry_same_rows():
    """同 state 重入 → 同 rows（确定性：同输入同输出，无随机/时序依赖）。"""
    state = _make_state()
    _make_active_contract(state)
    service = EconomicService(state)
    rows1 = service.collect_contract_revenues(faction_tax_collected={}, tax_rate=0.1)
    rows2 = service.collect_contract_revenues(faction_tax_collected={}, tax_rate=0.1)
    assert rows1 == rows2


def test_only_active_contracts_considered():
    """仅 ACTIVE 合同进入 collect_contract_revenues（:247-270 语义）。"""
    state = _make_state()
    pending_c = state.create_contract(ContractType.TAX_FARMING, 1, 100, 1)  # PENDING
    active_c = _make_active_contract(state)
    expired_c = state.create_contract(ContractType.TAX_FARMING, 1, 100, 1)
    expired_c.status = ContractStatus.EXPIRED

    service = EconomicService(state)
    rows = service.collect_contract_revenues(faction_tax_collected={}, tax_rate=0.1)
    # 只有 active_c 产生 rows；PENDING/EXPIRED 不出现
    assert len(rows) == 1
    assert rows[0]["contract_id"] == active_c.id
