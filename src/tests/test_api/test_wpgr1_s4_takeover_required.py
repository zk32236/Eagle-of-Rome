# src/tests/test_api/test_wpgr1_s4_takeover_required.py
"""WP-G-R1 S4（R1-G-05）— Commanderless ACTIVE Mandatory Takeover Core Contract。

冻结设计：SA-Design-WP-G-R1 v1.6 §2.5 + §3 T-R1-08（per-war required rows，P2-03）。

覆盖（SC-05，Evidence Class=DATA）：
- commanderless ACTIVE（≥1 场，非起义）→ get_senate_view DTO `takeover_required`：
  required==True + rows 长度==场数 + 每行 eligible_consul==True + target_commander_id
  存在（复用 `_is_eligible_consul` 权威，political_system:906）
- ACTIVE + valid commander → 不产生 required row（禁任意接管，F 件 §5.1）
- TRUCE + pending（P1 可选接管）不计入 takeover_required
- 起义战争排除（总督接管路径）
- 无 eligible consul → required=False（无解软锁规避）；reason = 冻结 machine token
  三态（commander_dead/commander_absent/commander_missing，v1.6 §2.5.1 值域）与
  `_commander_unavailable_token` 同源（中文展示文案由 legacy takeover_options 展示层
  映射，不在此 DTO）
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


def _takeover_required_dto(state, viewer="player_opt"):
    view = senate_api.get_senate_view(state, viewer)
    assert view["success"], view.get("message")
    return view["data"]["takeover_required"]


class TestTr108TakeoverRequiredCore(unittest.TestCase):
    """T-R1-08：commanderless ACTIVE → takeover_required 权威态（per-war rows）。"""

    def test_commanderless_active_exposes_required_rows(self):
        """单场 commanderless ACTIVE → required True；rows==1；eligible_consul True + target 存在。"""
        state, consul = _build_senate_state()
        war = _make_active_war(state, "war_commanderless", commander_id=None)
        tr = _takeover_required_dto(state)

        self.assertTrue(tr["required"])
        self.assertEqual(len(tr["rows"]), 1)
        row = tr["rows"][0]
        self.assertEqual(row["war_id"], "war_commanderless")
        self.assertEqual(row["war_name"], war.name)
        self.assertTrue(row["eligible_consul"])
        self.assertEqual(row["target_commander_id"], consul.id)
        self.assertEqual(row["reason"], "commander_missing")  # commander_id None → missing 同源

    def test_multi_war_per_war_rows(self):
        """多场 commanderless ACTIVE → rows 长度==场数（per-war 完整表达，非单对象）。"""
        state, _consul = _build_senate_state()
        _make_active_war(state, "war_b", commander_id=None)
        _make_active_war(state, "war_a", commander_id=None)
        _make_active_war(state, "war_c", commander_id=None)
        tr = _takeover_required_dto(state)

        self.assertTrue(tr["required"])
        self.assertEqual(len(tr["rows"]), 3)
        # 确定性顺序：war_id 字典序
        self.assertEqual([r["war_id"] for r in tr["rows"]], ["war_a", "war_b", "war_c"])
        for row in tr["rows"]:
            self.assertTrue(row["eligible_consul"])
            self.assertIsNotNone(row["target_commander_id"])

    def test_valid_commander_rows_empty(self):
        """ACTIVE + valid commander → 不产生 required row（禁任意接管）。"""
        state, _consul = _build_senate_state()
        _make_active_war(state, "war_commanded", commander_id=1)
        tr = _takeover_required_dto(state)
        self.assertFalse(tr["required"])
        self.assertEqual(tr["rows"], [])

    def test_mixed_valid_and_commanderless_counts_only_commanderless(self):
        """混合：valid-commander 与 commanderless 并存 → rows 只含 commanderless。"""
        state, _consul = _build_senate_state()
        _make_active_war(state, "war_cmd", commander_id=1)
        _make_active_war(state, "war_free", commander_id=None)
        tr = _takeover_required_dto(state)
        self.assertTrue(tr["required"])
        self.assertEqual([r["war_id"] for r in tr["rows"]], ["war_free"])

    def test_rebellion_war_excluded(self):
        """起义战争排除（总督接管，非执政官强制接管）。"""
        state, _consul = _build_senate_state()
        _make_active_war(state, "war_rebellion", commander_id=None, rebellion_province_id=7)
        tr = _takeover_required_dto(state)
        self.assertFalse(tr["required"])
        self.assertEqual(tr["rows"], [])

    def test_truce_pending_not_counted(self):
        """P1（TRUCE + pending treaty）不计入 takeover_required（可选替换指挥官，非强制）。"""
        state, _consul = _build_senate_state()
        war = War(id="war_p1", name="Truce War", war_type=WarType.FOREIGN, strength=5)
        war.status = WarStatus.TRUCE
        war.set_peace_treaty({"indemnity": 50, "duration": 3, "generated_turn": 1})  # status 默认 pending
        war.commander_id = 1
        state._war_system._truce_wars.append(war)
        tr = _takeover_required_dto(state)
        self.assertFalse(tr["required"])
        self.assertEqual(tr["rows"], [])
        # P1 仍以可选 takeover_options 暴露（既有语义不变）
        view = senate_api.get_senate_view(state, "player_opt")
        self.assertTrue(any(o["war_id"] == "war_p1" for o in view["data"]["takeover_options"]))

    def test_no_eligible_consul_required_false_no_deadlock(self):
        """无 eligible consul → required False（rows eligible_consul False；不引入无解软锁）。"""
        state, consul = _build_senate_state()
        # consul 被派去战场（absent）→ 不再 eligible
        consul.is_absent = True
        _make_active_war(state, "war_free", commander_id=None)
        tr = _takeover_required_dto(state)
        self.assertFalse(tr["required"])
        self.assertEqual(len(tr["rows"]), 1)
        self.assertFalse(tr["rows"][0]["eligible_consul"])
        self.assertIsNone(tr["rows"][0]["target_commander_id"])

    def test_dead_commander_reason_and_rows(self):
        """commander 阵亡（commander_id 指向 dead figure）→ reason=commander_dead + required row。"""
        state, _consul = _build_senate_state()
        dead = Figure(id=50, name="Dead General", faction_id="optimates", age=55)
        dead.is_dead = True
        state.add_member(dead)
        state.get_faction("optimates").member_ids.append(50)
        _make_active_war(state, "war_dead_cmd", commander_id=50)
        tr = _takeover_required_dto(state)
        self.assertTrue(tr["required"])
        self.assertEqual(tr["rows"][0]["reason"], "commander_dead")

    def test_absent_commander_not_valid_war_commander(self):
        """absent proconsul/propraetor commander → is_war_commander_valid False → required row。"""
        state, _consul = _build_senate_state()
        absent_cmd = Figure(id=60, name="Absent Proconsul", faction_id="optimates", age=50)
        absent_cmd.office = "proconsul"
        absent_cmd.is_absent = True
        state.add_member(absent_cmd)
        state.get_faction("optimates").member_ids.append(60)
        _make_active_war(state, "war_absent_cmd", commander_id=60)
        tr = _takeover_required_dto(state)
        self.assertTrue(tr["required"])
        self.assertEqual(tr["rows"][0]["reason"], "commander_absent")


if __name__ == "__main__":
    unittest.main()
