"""
EOR20260729-01 Legacy Cleanup — test_screenshot_revenue.py 副作用剥离迁移

归属：test_core/（原文件位于 test_gui/，但纯 DTO 断言测试属于核心层）

说明：
- 本文件由 test_gui/test_screenshot_revenue.py 剥离副作用后迁移而来。
- 移除了：写 JSON 证据文件、QML 离屏渲染、Qt 事件循环、os.makedirs 等副作用。
- 保留了：settle_revenue_phase DTO 完整性断言、treasury_delta 数学关系、
  派系展示名映射验证，并强化了断言使其独立成立。
- Owner 应手工删除遗留文件（见 Implementation Report 建议删除清单）。
"""
import pytest

from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.entities.province import Province
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.game_state import GameState
from src.core.service.economic_service import EconomicService
from src.api import faction_api


def _make_full_revenue_state():
    """
    创建完整收入结算状态（剥离自原 _full_revenue_state，无副作用）。
    """
    state = GameState.create_for_testing({
        "faction_style_map": {
            "opt": {"color": "#8B0000", "name": "Optimates", "name_i18n": "贵族派", "id_display": "Opt", "order": 1},
            "pop": {"color": "#006400", "name": "Populares", "name_i18n": "平民派", "id_display": "Pop", "order": 2},
            "equ": {"color": "#00008B", "name": "Equites", "name_i18n": "骑士派", "id_display": "Equ", "order": 3},
        },
        "faction_style_fallback": {"color": "#3A3530", "name": "未知派系", "id_display": "?"},
        "economic_rules": {
            "base_tax": 100,
            "faction_stipend": 10,
            "national_opex_rate": 0.0003,
            "private_land_income_rate": 0.05,
            "faction_tax_rate": 0.1,
            "initial_national_public_land": 1000,
        },
    })
    state.treasury = 500

    # 派系
    opt = Faction(id="opt", name="Optimates")
    pop = Faction(id="pop", name="Populares")
    equ = Faction(id="equ", name="Equites")
    for f in [opt, pop, equ]:
        state.add_faction(f)

    # 行省 — 使国家运营费和公地收益有数据
    prov1 = Province(1, "Italia", total_land=2000, conquered=True)
    prov2 = Province(2, "Sicilia", total_land=1500, conquered=True)
    prov3 = Province(3, "Africa", total_land=3000, conquered=True)
    for p in [prov1, prov2, prov3]:
        state.add_province(p)

    # 人物（含私地）
    figures = [
        Figure(101, "Gaius·Marius·Arpinas", faction_id="pop", age=55),
        Figure(102, "Lucius·Cornelius·Sulla·Felix", faction_id="opt", age=50),
        Figure(103, "Marcus·Licinius·Crassus·Dives", faction_id="equ", age=45),
        Figure(104, "Gnaeus·Pompeius·Magnus·Pius", faction_id="pop", age=48),
    ]
    for i, f in enumerate(figures):
        f._land_private = 20 + i * 5
        f._wealth = 100 + i * 50
        state.add_member(f)

    opt.member_ids = [102]
    pop.member_ids = [101, 104]
    equ.member_ids = [103]

    # 活跃合同（使合同收入有数据）
    contract1 = Contract(
        id=501, contract_type=ContractType.TAX_FARMING, name="西西里包税",
        base_cost=100, status=ContractStatus.ACTIVE, awarded_to=101,
        awarded_faction="pop", remaining_years=3, total_spent=0,
    )
    contract1._province_id = 2
    contract1._annual_income = 50
    contract1._annual_cost = 30
    state._contracts_dict[501] = contract1

    contract2 = Contract(
        id=502, contract_type=ContractType.PUBLIC_WORKS, name="罗马大道工程",
        base_cost=800, status=ContractStatus.ACTIVE, awarded_to=103,
        awarded_faction="equ", remaining_years=2, total_spent=200,
    )
    contract2._province_id = 1
    contract2._annual_income = 267
    contract2._annual_cost = 200
    state._contracts_dict[502] = contract2

    return state


class TestRevenueSettlementDTO:
    """收入结算后 DTO 完整性验证（原 screenshot 证据测试的纯断言版本）"""

    def test_settle_revenue_phase_dto_completeness(self):
        """
        settle_revenue_phase 返回的 data 必须包含完整结算字段，
        且 treasury_delta 数学关系严格成立。
        """
        state = _make_full_revenue_state()
        service = EconomicService(state)
        result = service.settle_revenue_phase()

        assert isinstance(result, dict)
        assert result.get("success") is True, f"Settlement failed: {result.get('message', '')}"

        data = result["data"]
        assert data is not None

        # 核心字段必须存在
        required_keys = [
            "starting_treasury",
            "ending_treasury",
            "treasury_delta",
            "faction_rows",
            "private_land_rows",
            "contract_rows",
            "indemnities",
            "national_opex",
            "public_land_income",
            "warranty_rows",
            "maintenance",
            "debug_events",
            "accounting_window",
        ]
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

        # treasury_delta 数学关系
        assert data["ending_treasury"] == data["starting_treasury"] + data["treasury_delta"]
        window = data["accounting_window"]
        assert window["basis"] == "republic_treasury_cash"
        assert window["reconciled"] is True
        assert sum(row["signed_amount"] for row in window["treasury_ledger_rows"]) == data["treasury_delta"]
        assert window["displayed_net_total"] == data["treasury_delta"]
        # 有数据时 delta 不应为 0（行省/合同/私地均存在）
        assert data["treasury_delta"] != 0, "Expected non-zero delta with populated state"

    def test_faction_rows_structure_and_values(self):
        """
        faction_rows 使用 faction_id 作为 key，且包含数值型 stipend/tax/total。
        """
        state = _make_full_revenue_state()
        result = EconomicService(state).settle_revenue_phase()
        data = result["data"]
        faction_rows = data["faction_rows"]

        assert isinstance(faction_rows, dict)
        assert len(faction_rows) >= 3, f"Expected at least 3 faction rows, got {len(faction_rows)}"

        for fid, row in faction_rows.items():
            assert "stipend" in row, f"Missing stipend for {fid}"
            assert "tax" in row, f"Missing tax for {fid}"
            assert "total" in row, f"Missing total for {fid}"
            assert isinstance(row["stipend"], (int, float)), f"stipend not numeric for {fid}: {row}"
            assert isinstance(row["tax"], (int, float)), f"tax not numeric for {fid}: {row}"
            assert isinstance(row["total"], (int, float)), f"total not numeric for {fid}: {row}"
            # total = stipend + tax（四舍五入后）
            assert row["total"] == row["stipend"] + row["tax"], (
                f"total mismatch for {fid}: {row['total']} != {row['stipend']} + {row['tax']}"
            )
            assert fid in ("opt", "pop", "equ"), f"Unexpected faction_id: {fid}"

    def test_private_land_rows_fields(self):
        """
        private_land_rows 每项必须包含 name 和 income。
        """
        state = _make_full_revenue_state()
        result = EconomicService(state).settle_revenue_phase()
        land_rows = result["data"]["private_land_rows"]

        assert isinstance(land_rows, list)
        assert len(land_rows) > 0, "Expected at least one private_land_row with figures having land"

        for lr in land_rows:
            assert "name" in lr, f"Missing name in private_land_row: {lr}"
            assert "income" in lr, f"Missing income in private_land_row: {lr}"
            assert isinstance(lr["income"], (int, float)), f"income not numeric: {lr}"

    def test_faction_display_name_mapping(self):
        """
        派系区块使用 faction_id → faction_style_map 展示名映射。
        验证 faction_rows 的 key 均可通过 faction_api.get_faction_style_map 正确映射为展示名。
        """
        state = _make_full_revenue_state()

        # 先验证 style_map 配置完整性
        style_result = faction_api.get_faction_style_map(state)
        assert style_result["success"] is True, "faction_style_map API failed"
        style_data = style_result["data"]
        assert "map" in style_data
        assert "fallback" in style_data
        assert len(style_data["map"]) >= 3

        # 执行结算
        result = EconomicService(state).settle_revenue_phase()
        assert result["success"] is True
        data = result["data"]
        faction_rows = data["faction_rows"]

        # 每个 faction_id 均可映射到展示名，且展示名 ≠ raw id
        for fid in faction_rows:
            entry = style_data["map"].get(fid)
            assert entry is not None, f"Faction {fid} not found in style map"
            display_name = entry["name"]
            assert display_name != fid, (
                f"Display name should differ from raw id for {fid}, got: {display_name}"
            )
            assert display_name, f"Empty display name for {fid}"

    def test_faction_style_map_unknown_faction_fallback(self):
        """
        未知 faction_id 不在 style_map 中时，应使用 fallback 配置。
        """
        state = _make_full_revenue_state()
        # 添加一个不在 faction_style_map 中的派系
        unknown = Faction(id="xyz", name="Rebels")
        state.add_faction(unknown)

        result = faction_api.get_faction_style_map(state)
        data = result["data"]

        assert "xyz" in data["map"], "Unknown faction should appear in map with fallback"
        assert data["map"]["xyz"]["color"] == "#3A3530", "Fallback color mismatch"
        assert data["map"]["xyz"]["name"] == "Rebels", "Should preserve faction.name for unknown"

    def test_contract_rows_structure(self):
        """
        有活跃合同时 contract_rows 应包含 payment/type 等字段。
        """
        state = _make_full_revenue_state()
        result = EconomicService(state).settle_revenue_phase()
        contract_rows = result["data"]["contract_rows"]

        assert isinstance(contract_rows, list)
        assert len(contract_rows) > 0, "Expected contract rows with active contracts"

        for row in contract_rows:
            assert "contract_id" in row, f"Missing contract_id: {row}"
            assert "type" in row, f"Missing type: {row}"
            assert "payment" in row, f"Missing payment: {row}"
            assert isinstance(row["payment"], (int, float)), f"payment not numeric: {row}"
