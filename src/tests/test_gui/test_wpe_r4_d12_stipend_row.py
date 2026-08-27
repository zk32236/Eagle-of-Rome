# src/tests/test_gui/test_wpe_r4_d12_stipend_row.py
"""WP-E-R4 D-12：国家支出「派系津贴(国库拨款)」行（DATA 四层对账）。

R4 修正 = RevenueStage 国家支出区块新增行 = Σ faction_rows[*].stipend（F6:317-318 扣国库）。
本测试锁定该行的权威 DTO 事实 + 四层对账恒等式：
closing == opening + Σincome − Σexpense（含 stipend 归国家支出）。
"""
from src.core.game_state import GameState
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.province import Province
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.war import War
from src.core.systems.war_system import WarSystem
from src.core.service.economic_service import EconomicService


_BETA_ECON_CONFIG = {
    "economic_rules": {
        "faction_stipend": 5,
        "land_price_per_unit": 10,
        "national_opex_rate": 0.0003,
        "initial_national_public_land": 0,
    }
}


def _make_state():
    """BETA-001 同款确定性状态：opening=142 + income=36（赔款）− opex=18 − stipend=15 → ending=145。"""
    s = GameState.create_for_testing(_BETA_ECON_CONFIG)
    s.turn = GameTurn(turn_number=5, year=-260)
    s.treasury = 142
    for fid, name in (("opt", "Optimates"), ("pop", "Populares"), ("equ", "Equites")):
        s.add_faction(Faction(id=fid, name=name))
    s._war_system = WarSystem(s)
    war = War(id="w1", name="赔款战争")
    war.set_indemnity_due(36)
    s.get_war_system()._active_wars.append(war)
    s.add_province(Province(1, "行省", total_land=6000, conquered=True))
    return s


def _settle(s):
    result = EconomicService(s).settle_revenue_phase()
    assert result["success"], f"Settlement failed: {result}"
    return result["data"]


def _stipend_total(data):
    return sum(row["stipend"] for row in data["faction_rows"].values())


def _income_total(data):
    total = 0
    for i in data.get("indemnities", []):
        if i.get("kind") == "income":
            total += i.get("amount", 0)
    pl = data.get("public_land_income") or {}
    total += pl.get("amount", 0)
    for r in data.get("contract_rows", []):
        if r.get("type") == "tax_farming":
            total += r.get("treasury_gain", 0)
    return total


def _expense_total(data):
    total = 0
    op = data.get("national_opex") or {}
    total += op.get("amount", 0)
    for r in data.get("contract_rows", []):
        if r.get("type") == "public_works":
            total += r.get("payment", 0)
    total += _stipend_total(data)  # R4：派系津贴归类国家支出（F6:317-318）
    for i in data.get("indemnities", []):
        if i.get("kind") == "expense":
            total += abs(i.get("amount", 0))
    m = data.get("maintenance") or {}
    total += (m.get("military") or {}).get("total", 0)
    total += (m.get("naval") or {}).get("total", 0)
    return total


class TestStipendRowValue:
    """国家支出新行值 = Σ faction_rows[*].stipend（权威 DTO）。"""

    def test_stipend_total_equals_sum_faction_stipend(self):
        data = _settle(_make_state())
        assert _stipend_total(data) == 15  # 3 × 5
        for fid in ("opt", "pop", "equ"):
            assert data["faction_rows"][fid]["stipend"] == 5

    def test_stipend_total_zero_when_no_faction(self):
        s = GameState.create_for_testing(_BETA_ECON_CONFIG)
        s.turn = GameTurn(turn_number=5, year=-260)
        s.treasury = 500
        data = _settle(s)
        assert _stipend_total(data) == 0


class TestFourLayerReconciliation:
    """四层对账恒等式：closing == opening + Σincome − Σexpense（含 stipend）。"""

    def test_identity_beta_001(self):
        data = _settle(_make_state())
        income = _income_total(data)
        expense = _expense_total(data)
        assert data["starting_treasury"] == 142
        assert income == 36
        assert expense == 33  # opex 18 + stipend 15
        assert data["treasury_delta"] == income - expense == 3
        assert data["ending_treasury"] == data["starting_treasury"] + income - expense
        assert data["ending_treasury"] == 145

    def test_identity_with_works_contract(self):
        """状态 B：活跃 works 合同 → 工程付款行计入支出，恒等式仍成立。"""
        s = _make_state()
        fig = Figure(101, "骑士甲", faction_id="opt", age=35)
        fig.wealth = 500
        s.add_member(fig)
        s.get_faction("opt").member_ids = [101]
        c = Contract(
            id=301, contract_type=ContractType.PUBLIC_WORKS, name="道路工程",
            base_cost=800, status=ContractStatus.ACTIVE, awarded_to=101,
            remaining_years=1, total_spent=534,
        )
        c._province_id = 1
        c._annual_income = 267
        c._annual_cost = 200
        s._contracts_dict[301] = c

        data = _settle(s)
        income = _income_total(data)
        expense = _expense_total(data)
        works_payment = sum(
            r.get("payment", 0)
            for r in data.get("contract_rows", [])
            if r.get("type") == "public_works"
        )
        assert works_payment > 0
        assert data["ending_treasury"] == data["starting_treasury"] + income - expense
        assert data["ending_treasury"] == data["starting_treasury"] + data["treasury_delta"]
