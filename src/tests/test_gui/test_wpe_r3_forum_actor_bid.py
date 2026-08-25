"""WP-E-R3 Forum explicit actor and durable bid presentation checks."""

from pathlib import Path

from src.api import forum_api
from src.core.entities.contract import Contract, ContractStatus, ContractType
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.game_state import GameState


QML_PATH = Path(__file__).parents[2] / "ui" / "gui" / "qml" / "stages" / "ForumStage.qml"


def _forum_state():
    state = GameState.create_for_testing({"testing": {"bypass_player_check": True}})
    state.turn = GameTurn(turn_number=5, year=-260)
    state._players["human"] = Player(player_id="human", faction_id="f1", player_type=PlayerType.HUMAN)
    state._factions["f1"] = Faction(id="f1", name="F1")
    eques = Figure.create_eques(11, "f1", 30)
    eques.name = "Second Actor"
    eques.wealth = 5000
    state.add_member(eques)
    state._factions["f1"].member_ids = [11]
    contract = Contract(
        id=91,
        contract_type=ContractType.TAX_FARMING,
        name="R3 Tax",
        base_cost=100,
        status=ContractStatus.BUDGETED,
    )
    state._contracts_dict[91] = contract
    state.set_pending_land_sale_quota(100)
    return state, eques, contract


def test_explicit_actor_drives_land_and_bid_exactly_once():
    state, actor, contract = _forum_state()

    assert forum_api.buy_land(state, "human", actor.id, 5)["success"] is True
    assert forum_api.place_bid(state, "human", actor.id, contract.id, 120)["success"] is True
    assert forum_api.buy_land(state, "human", actor.id, 6)["success"] is False
    assert forum_api.place_bid(state, "human", actor.id, contract.id, 130)["success"] is False

    pending = state.get_forum_pending()
    assert pending["land_purchases"] == [(actor.id, 5)]
    assert len(pending["contract_bids"]) == 1
    assert len(pending["contract_bids"][0]) == 7

    view = forum_api.get_forum_view(state, "human")["data"]
    assert view["viewer_land_requests"] == [{"figure_id": actor.id, "requested_amount": 5}]
    assert view["viewer_contract_bids"] == [{
        "contract_id": contract.id,
        "figure_id": actor.id,
        "amount": 120,
        "profit_rate": 0.2,
        "status": "pending",
    }]
    assert forum_api.get_forum_view(state, "human")["data"]["viewer_contract_bids"] == view["viewer_contract_bids"]


def test_forum_qml_has_explicit_actor_and_inline_feedback_contract():
    source = QML_PATH.read_text(encoding="utf-8-sig")

    assert "property int selectedMarketActorId: 0" in source
    assert "property int selectedRetirementFigureId" in source
    assert "selectedOwnFigureId" not in source
    assert "forumViewerContractBids" in source
    assert 'objectName: "marketActorPrompt"' in source
    assert 'objectName: "forumInlineNotice"' in source
    assert "请先选择竞标人物" in source
    assert "（待结算）" in source
    assert "root.openLandDialog(actor.id, actor.name)" in source
    assert "sessionStore.doPlaceBid(actor.id, contractId, amount)" in source
