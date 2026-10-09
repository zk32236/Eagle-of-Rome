# src/tests/test_api/test_wpgr1_s4_takeover_required.py
"""WP-G-R1 S4（R1-G-05）→ WP-G-R5 卡投影改写（Plan §4.2 L2；SA §2.7 A-I14 / §4.10 C-M09）。

R5 supersede：`takeover_required` / `takeover_options` 只读态与 mandatory Takeover 门退役——
War lifecycle 事实统一经 `get_senate_view`.`war_cards`（§2.1 五事实 + defaults + 候选）；
commanderless 真实战照常投影为 `ongoing` 卡（不再强制任命，无软锁）。

保留反例/判据：commander 有效性（dead/absent proconsul）仍经 `is_war_commander_valid` 判定；
无 eligible consul 不引入无解软锁（resolve/advance 仍放行）。
Evidence Class=DATA。
"""
import unittest

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.core.entities.war import War, WarType, WarStatus
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.systems.political_system import PoliticalSystem
from src.api import senate_api


def _build_senate_state():
    """Senate 只读视图 fixture：玩家派系（optimates）持有 eligible consul + 备用元老。"""
    state = GameState.create_for_testing({})
    state.turn = GameTurn(turn_number=1, year=-264)
    state._war_system = WarSystem(state)
    state._military_system = MilitarySystem(state)
    state._naval_system = NavalSystem(state)

    faction = Faction(id="optimates", name="Optimates", treasury=50)
    state.add_faction(faction)
    consul = Figure(id=1, name="Consul Aemilius", faction_id="optimates", age=45)
    consul.office = "consul"
    consul.class_tier = ClassTier.NOBILE
    consul.influence = 80
    state.add_member(consul)
    faction.member_ids.append(1)

    player = Player(player_id="player_opt", faction_id="optimates", player_type=PlayerType.HUMAN)
    state.add_player(player)
    state.set_current_player("player_opt")
    return state, consul


def _make_active_war(state, war_id, commander_id=None, rebellion_province_id=None,
                     naval_required=False):
    war = War(id=war_id, name=f"War {war_id}", war_type=WarType.FOREIGN, strength=5,
              threat_level=3, naval_required=naval_required)
    war.status = WarStatus.ACTIVE
    war.commander_id = commander_id
    if rebellion_province_id is not None:
        war._rebellion_province_id = rebellion_province_id
    state._war_system._active_wars.append(war)
    return war


def _view(state, viewer="player_opt"):
    view = senate_api.get_senate_view(state, viewer)
    assert view["success"], view.get("message")
    return view["data"]


def _card(state, war_id, viewer="player_opt"):
    data = _view(state, viewer)
    for card in data["war_cards"]:
        if card["war_id"] == war_id:
            return card
    raise AssertionError(f"card missing for {war_id}: {[c['war_id'] for c in data['war_cards']]}")


class TestTr108TakeoverRequiredCore(unittest.TestCase):
    """T-R1-08 → R5：commanderless ACTIVE 卡投影（defaults/候选），无 mandatory 门。"""

    def test_commanderless_active_exposes_required_rows(self):
        """单场 commanderless ACTIVE → 卡存在；current_commander None；默认目标 = eligible Consul。"""
        state, consul = _build_senate_state()
        _make_active_war(state, "war_commanderless", commander_id=None)
        card = _card(state, "war_commanderless")

        self.assertTrue(card["is_real_war"])
        self.assertEqual(card["classification"], "ongoing")
        self.assertIsNone(card["current_commander_id"])
        self.assertEqual(card["defaults"]["target_commander_id"], consul.id)
        candidate_ids = [c["figure_id"] for c in card["commander_candidates"]]
        self.assertIn(consul.id, candidate_ids)

    def test_multi_war_per_war_rows(self):
        """多场 commanderless ACTIVE → 每场一卡（per-war 完整表达）。"""
        state, consul = _build_senate_state()
        _make_active_war(state, "war_b", commander_id=None)
        _make_active_war(state, "war_a", commander_id=None)
        _make_active_war(state, "war_c", commander_id=None)
        data = _view(state)
        ids = [c["war_id"] for c in data["war_cards"]]
        for wid in ("war_a", "war_b", "war_c"):
            self.assertIn(wid, ids)
        for wid in ("war_a", "war_b", "war_c"):
            card = _card(state, wid)
            self.assertIsNone(card["current_commander_id"])
            self.assertEqual(card["defaults"]["target_commander_id"], consul.id)

    def test_valid_commander_rows_empty(self):
        """ACTIVE + valid commander → 卡默认保留现任 Commander（禁任意接管）。"""
        state, _consul = _build_senate_state()
        _make_active_war(state, "war_commanded", commander_id=1)
        card = _card(state, "war_commanded")
        self.assertEqual(card["current_commander_id"], 1)
        self.assertEqual(card["defaults"]["target_commander_id"], 1)

    def test_mixed_valid_and_commanderless_counts_only_commanderless(self):
        """混合：valid-commander 与 commanderless 并存 → 两卡各自表达。"""
        state, consul = _build_senate_state()
        _make_active_war(state, "war_cmd", commander_id=1)
        _make_active_war(state, "war_free", commander_id=None)
        self.assertEqual(_card(state, "war_cmd")["current_commander_id"], 1)
        self.assertEqual(_card(state, "war_cmd")["defaults"]["target_commander_id"], 1)
        self.assertIsNone(_card(state, "war_free")["current_commander_id"])
        self.assertEqual(_card(state, "war_free")["defaults"]["target_commander_id"], consul.id)

    def test_rebellion_war_excluded(self):
        """R5（Plan §4.2 L2；SA §2.7 A-I14 / C-M09）：mandatory takeover 退役——起义战争
        无强制接管门；`takeover_required` 键不再存在。

        WP-G-R12 A1-venue Test Amendment（ODR-R12-01，2026-10-09）：原断言「起义战照常投影
        为卡（`assertIn("war_rebellion", ids)`）」被 A1-venue supersede——起义卡（无合法 route）
        **移出**元老院提案列表（`build_war_card_views` 空 `authority_by_mode` ⇒ `continue`）；
        可见性改由战斗阶段（CombatStage）/ 广场（Forum 起义警示）承担（FC-R12-A1-06）。
        原意图注释保留；mandatory-takeover 退役断言（`assertNotIn("takeover_required")`）保留。
        """
        state, _consul = _build_senate_state()
        _make_active_war(state, "war_rebellion", commander_id=None, rebellion_province_id=7)
        data = _view(state)
        self.assertNotIn("takeover_required", data)
        ids = [c["war_id"] for c in data["war_cards"]]
        # A1-venue：起义卡移出元老院提案面（原 `assertIn` 已由 ODR-R12-01 取代）
        self.assertNotIn("war_rebellion", ids)

    def test_truce_pending_not_counted(self):
        """P1（TRUCE + pending treaty）→ pending_peace 卡（可选 peace 模式），非强制接管。"""
        state, _consul = _build_senate_state()
        war = War(id="war_p1", name="Truce War", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 50, "duration": 3, "generated_turn": 1})  # status 默认 pending
        war.commander_id = 1
        state._war_system._truce_wars.append(war)
        data = _view(state)
        self.assertNotIn("takeover_required", data)
        card = _card(state, "war_p1")
        self.assertEqual(card["classification"], "pending_peace")
        self.assertIs(card["peace_capability"], True)
        self.assertEqual(card["allowed_modes"], ["command", "peace"])

    def test_no_eligible_consul_required_false_no_deadlock(self):
        """无 eligible consul → 卡默认目标 None；不引入无解软锁（resolve/advance 仍放行）。"""
        state, consul = _build_senate_state()
        consul.is_absent = True  # 被派去战场 → 不再 eligible
        _make_active_war(state, "war_free", commander_id=None)
        card = _card(state, "war_free")
        self.assertIsNone(card["current_commander_id"])
        self.assertIsNone(card["defaults"]["target_commander_id"])

        # 无 mandatory 门 → 结算/推进不被阻挡
        state.senate_proposal_decision_complete = True
        resolved = senate_api.resolve_senate(state)
        self.assertTrue(resolved["success"], resolved.get("message"))
        adv = senate_api.advance_senate_phase(state, "player_opt")
        self.assertTrue(adv["success"], adv.get("message"))

    def test_dead_commander_reason_and_rows(self):
        """commander 阵亡（commander_id 指向 dead figure）→ is_war_commander_valid False；
        WP-O O-S2（FC-07/R05/R06）：卡现任身份经 live 谓词解析 → 死者不呈现为现任
        （current_commander_id None），且不静默替换（无复活指派）。"""
        state, _consul = _build_senate_state()
        dead = Figure(id=50, name="Dead General", faction_id="optimates", age=55)
        dead.is_dead = True
        state.add_member(dead)
        state.get_faction("optimates").member_ids.append(50)
        war = _make_active_war(state, "war_dead_cmd", commander_id=50)
        self.assertFalse(PoliticalSystem(state).is_war_commander_valid(war))
        card = _card(state, "war_dead_cmd")
        # WP-O O-S2 supersession（SA-Design R05 live-current predicate / FC-07）：原断言
        # `== 50` 即 dead-identity 泄漏面，已由 O-S2 读侧闭合取代；卡不呈现死者为现任，
        # 亦不静默替换（无复活指派）。
        self.assertIsNone(card["current_commander_id"])
        self.assertNotIn(50, [c["figure_id"] for c in card["commander_candidates"]])

    def test_absent_commander_not_valid_war_commander(self):
        """absent proconsul/propraetor commander → is_war_commander_valid False（需重新任命）。"""
        state, _consul = _build_senate_state()
        absent_cmd = Figure(id=60, name="Absent Proconsul", faction_id="optimates", age=50)
        absent_cmd.office = "proconsul"
        absent_cmd.is_absent = True
        state.add_member(absent_cmd)
        state.get_faction("optimates").member_ids.append(60)
        war = _make_active_war(state, "war_absent_cmd", commander_id=60)
        self.assertFalse(PoliticalSystem(state).is_war_commander_valid(war))


if __name__ == "__main__":
    unittest.main()
