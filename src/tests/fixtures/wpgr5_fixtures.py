# src/tests/fixtures/wpgr5_fixtures.py
"""WP-G-R5 (SA-Design §2.1/§2.2/§2.4/§2.5/§3) — DA-B1 builders.

复用 wpgr4_fixtures 的 bootstrap（GameState.create_for_testing + task-local 内存 config），
在其上叠加 R5 War Card / Commander Claim / Submit 场景所需实体：
- War lifecycle origin（active_declaration / passive_declaration / legacy_unknown）
- 真实 War 的 Commander 占用
- pending-peace War（TRUCE + pending treaty）
- THREAT active-declaration candidate
- Province governor 占用（候选排除）

纪律：真实实体（War/Figure/Province），不代跑业务；force 键保持 committed 默认。
"""

from typing import Any, Dict, List, Optional

from src.core.entities.figure import Figure, ClassTier
from src.core.entities.province import Province
from src.core.entities.war import War, WarType, WarStatus

from src.tests.fixtures.wpgr4_fixtures import (  # noqa: F401  (re-export 供测试使用)
    make_base_state,
    add_faction,
    add_player,
    add_consul,
    make_war,
    attach_active,
    attach_truce,
    recruit_legions_for_war,
    _base_config,
)

FIXED = {
    "player": "player1",
    "faction": "optimates",
    "consul": 1,
    "cmd_a": 2,
    "cmd_b": 3,
    "cmd_gov": 4,
    "war_ongoing": "pyrrhic_war",
    "war_peace": "first_punic_war",
    "war_threat": "threat_war",
    "war_passive": "passive_war",
    "province": 10,
}


def add_figure(state, faction, figure_id: int, name: str, office: str = "ex-consul",
               martial: int = 4, absent: bool = False, history=None) -> Figure:
    fig = Figure(id=figure_id, name=name, faction_id=faction.id, age=45)
    fig.office = office
    fig.martial = martial
    fig.is_absent = absent
    fig.class_tier = ClassTier.NOBILE
    fig.influence = 30
    if history:
        for term in history:
            fig.add_office_history(term["office_type"], term["start_turn"], term.get("end_turn"))
    state.add_member(fig)
    faction.member_ids.append(figure_id)
    return fig


def add_province(state, province_id: int, name: str, governor_id: Optional[int] = None,
                 governor_designate_id: Optional[int] = None,
                 governor_type: str = "proconsul") -> Province:
    province = Province(
        province_id=province_id, name=name, total_land=100,
        governor_id=governor_id, governor_designate_id=governor_designate_id,
        governor_type=governor_type, conquered=True,
    )
    state.add_province(province)
    return province


def make_passive_war(war_id: str, name: str, activation_turn: int,
                     commander_id: Optional[int] = None) -> War:
    war = make_war(war_id, name, status=WarStatus.ACTIVE, commander_id=commander_id)
    war.activation_turn = activation_turn
    war.set_activation_origin("passive_declaration")
    return war


def build_r5_base(turn_number: int = 1, with_governor: bool = False,
                  with_passive: bool = True) -> Dict[str, Any]:
    """R5 主样本：Consul C1 留城；ongoing War(commander=cmd_a) + pending-peace War(commander=cmd_b)
    + THREAT candidate + 可选 passive War + 可选 Province governor 占用。"""
    state = make_base_state(turn_number=turn_number, year=-264)
    faction = add_faction(state, treasury=500)
    add_player(state)
    consul = add_consul(state, faction, figure_id=FIXED["consul"], name="Consul Aemilius")
    cmd_a = add_figure(state, faction, FIXED["cmd_a"], "Commander A", office="ex-consul")
    cmd_b = add_figure(state, faction, FIXED["cmd_b"], "Commander B", office="ex-praetor")
    cmd_gov = add_figure(state, faction, FIXED["cmd_gov"], "Governor G", office="ex-consul",
                         history=[{"office_type": "consul", "start_turn": -3, "end_turn": -2}])

    war_ongoing = make_war(FIXED["war_ongoing"], "Pyrrhic War", status=WarStatus.ACTIVE,
                           commander_id=cmd_a.id)
    war_ongoing.activation_turn = turn_number
    war_ongoing.set_activation_origin("active_declaration")
    attach_active(state, war_ongoing)

    war_peace = make_war(FIXED["war_peace"], "First Punic War", status=WarStatus.TRUCE,
                         commander_id=cmd_b.id,
                         treaty={"indemnity": 80, "duration": 3, "status": "pending",
                                 "generated_turn": turn_number})
    attach_truce(state, war_peace)

    war_threat = make_war(FIXED["war_threat"], "Threat War", status=WarStatus.THREAT,
                          threat_level=2)
    state._war_system._threats.append(war_threat)

    war_passive = None
    if with_passive:
        war_passive = make_passive_war(FIXED["war_passive"], "Passive War",
                                       activation_turn=turn_number)
        attach_active(state, war_passive)

    province = None
    if with_governor:
        province = add_province(state, FIXED["province"], "Sicilia", governor_id=cmd_gov.id)

    return {
        "state": state,
        "faction": faction,
        "player_id": FIXED["player"],
        "consul": consul,
        "consul_id": consul.id,
        "cmd_a": cmd_a,
        "cmd_b": cmd_b,
        "cmd_gov": cmd_gov,
        "war_ongoing": war_ongoing,
        "war_peace": war_peace,
        "war_threat": war_threat,
        "war_passive": war_passive,
        "province": province,
        "manifest": {"fixture": "R5-BASE", "fixed_ids": FIXED, "turn": turn_number},
    }


def card_by_war(cards: List[Dict[str, Any]], war_id: str) -> Optional[Dict[str, Any]]:
    for card in cards:
        if card.get("war_id") == war_id:
            return card
    return None


def submit_request(war_drafts=None, proposals=None, session="S1", request_id="req-1") -> Dict[str, Any]:
    return {
        "senate_session_id": session,
        "submit_request_id": request_id,
        "war_drafts": war_drafts or [],
        "proposals": proposals or [],
    }


def command_draft(war_id: str, target_commander_id, reinforcement_n=0, checked=True) -> Dict[str, Any]:
    return {"war_id": war_id, "checked": checked, "mode": "command",
            "target_commander_id": target_commander_id, "reinforcement_n": reinforcement_n}


def peace_draft(war_id: str, checked=True) -> Dict[str, Any]:
    return {"war_id": war_id, "checked": checked, "mode": "peace",
            "target_commander_id": None, "reinforcement_n": 0}


def error_codes(result: Dict[str, Any]) -> List[str]:
    return [e.get("code") for e in (result.get("errors") or [])]
