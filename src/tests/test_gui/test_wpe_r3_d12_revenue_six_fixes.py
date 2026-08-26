# src/tests/test_gui/test_wpe_r3_d12_revenue_six_fixes.py
"""
WP-E（GUI-BETA-R1）D-12：Revenue 六项行级 read-model DATA 证据（R3-E-04）。

冻结设计 §E.2：六项全部纯 QML read-model（producer 零改动）——本测试锁定驱动
六行渲染的 DTO 事实（EconomicService.settle_revenue_phase 生产路径）：
#1 包税空行消除（可见性 = 存在 tax_farming 行）/ #2 工程付款行（payment）
#3 insufficient notice（kind=insufficient）/ #4 basis 标签（stipend/tax 分列）
#5 赔款单次（逐行，无合计依赖）/ #6 新余额（ending_treasury）
"""
from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.province import Province
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import War
from src.core.systems.war_system import WarSystem
from src.core.service.economic_service import EconomicService


def _base_state(treasury=500):
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=5, year=-260)
    state.treasury = treasury
    state.add_faction(Faction(id="opt", name="Optimates"))
    state.add_province(Province(1, "Italia", total_land=2000, conquered=True))
    state.add_province(Province(2, "Sicilia", total_land=1500, conquered=True))
    fig = Figure(101, "Marcus", faction_id="opt", age=40)
    fig._land_private = 50
    fig._wealth = 200
    state.add_member(fig)
    state.get_faction("opt").member_ids = [101]
    state._war_system = WarSystem(state)
    return state


def _add_contract(state, cid, ctype, base_cost=100):
    c = Contract(cid, ctype, f"C{cid}", base_cost=base_cost,
                 status=ContractStatus.ACTIVE, awarded_to=101,
                 awarded_faction="opt", remaining_years=3)
    if ctype == ContractType.TAX_FARMING:
        c._province_id = 2
        c._annual_income = 50
        c._annual_cost = 30
        c._winning_bid = {"bidder_id": 101}  # 生产路径（place_bid）写入的赢标结构
        c._contract_price = base_cost
        c._profit_rate = 0.2
    else:
        c._is_fleet_construction = False
        c._annual_income = 60
        c._annual_cost = 30
    state._contracts_dict[cid] = c
    return c


def _add_war_with_indemnity(state, war_id, amount):
    war = War(id=war_id, name=f"War {war_id}", start_year=-270, threat_level=5, strength=5)
    war.set_indemnity_due(amount)
    state._war_system._active_wars.append(war)
    return war


def _settle(state):
    result = EconomicService(state).settle_revenue_phase()
    assert result["success"], f"Settlement failed: {result}"
    return result["data"]


def test_works_payment_row_data_exists():
    """#2：工程合同付款事实在 DTO（contract_rows[type=public_works].payment > 0）——驱动支出区新增行。"""
    state = _base_state()
    _add_contract(state, 11, ContractType.PUBLIC_WORKS)
    data = _settle(state)
    works = [r for r in data["contract_rows"] if r["type"] == "public_works"]
    assert works, "public_works row missing"
    assert works[0]["payment"] > 0


def test_no_tax_farming_hides_empty_income_row():
    """#1：仅 works 合同时 contract_rows 无 tax_farming 行 → QML 包税行隐藏（禁空「+0」）。"""
    state = _base_state()
    _add_contract(state, 11, ContractType.PUBLIC_WORKS)
    data = _settle(state)
    assert [r for r in data["contract_rows"] if r["type"] == "tax_farming"] == []


def test_tax_farming_row_has_treasury_gain():
    """#1 正向：tax_farming 行存在且 treasury_gain 非 0（驱动收入行显示）。"""
    state = _base_state()
    _add_contract(state, 12, ContractType.TAX_FARMING)
    data = _settle(state)
    tax_rows = [r for r in data["contract_rows"] if r["type"] == "tax_farming"]
    assert tax_rows
    assert tax_rows[0]["treasury_gain"] > 0


def test_indemnity_income_once_and_insufficient_kind():
    """#3/#5：income 逐行单次（无合计依赖）；国库不足 → kind=insufficient 入 notice 面。"""
    state = _base_state(treasury=1000)
    _add_war_with_indemnity(state, "w1", 50)
    data = _settle(state)
    income = [r for r in data["indemnities"] if r["kind"] == "income"]
    assert len(income) == 1
    assert income[0]["amount"] == 50

    state2 = _base_state(treasury=30)
    _add_war_with_indemnity(state2, "w2", -50)
    data2 = _settle(state2)
    insufficient = [r for r in data2["indemnities"] if r["kind"] == "insufficient"]
    assert len(insufficient) == 1
    assert insufficient[0]["amount"] == -50


def test_faction_basis_fields_present():
    """#4：faction_rows 含 stipend/tax 分列（驱动「拨款（国库支出）/会员税（派系金库）」标签）。"""
    state = _base_state()
    _add_contract(state, 12, ContractType.TAX_FARMING)
    data = _settle(state)
    row = data["faction_rows"]["opt"]
    assert "stipend" in row and "tax" in row
    assert row["stipend"] >= 0 and row["tax"] >= 0


def test_ending_treasury_consistent():
    """#6：ending_treasury 字段在位且 = starting + delta（新余额绑定数据源，不混快照）。"""
    state = _base_state()
    _add_contract(state, 12, ContractType.TAX_FARMING)
    data = _settle(state)
    assert data["ending_treasury"] == data["starting_treasury"] + data["treasury_delta"]
