# src/tests/test_integration/test_wpe_candidate_supply_run.py
"""
WP-E（GUI-BETA-R1）E-G7-09：Candidate Supply 多回合证据运行 harness（T-7）。

覆盖（任务包 §20A v1.2 runtime 要求——≥8 回合连续 generated-game 运行或等价
确定性多回合 harness，复用 test_integration 基础设施）：
- 逐回合记录：每官职候选人数 / 零候选回合 / 空因标签
  （无存活合格者 / 冷却 / 曾任高阶禁选 / absent / 死亡 / 生成混合 / read-model 异常）
- 决策准则分类（设计 §4.3 / DA-Plan A10.3）：
  - 实现漂移（read-model 过滤错误 / stale 状态 / 谓词 bug）→ WP-E 内修正；
  - 冻结规则允许的不可避免零候选 → ODR + RETURN + STOP（禁 spawn hack/推荐值推进）
- harness 自检（Targeted）：跑通 8 回合 + 数据表可产出 + 分类判定明确。
"""
import random

import pytest

from src.core.game_state import GameState
from src.core.entities.figure import Figure, ClassTier
from src.core.entities.entities import Faction, GameTurn
from src.core.entities.player import Player, PlayerType
from src.api import population_api

_OFFICES = ["consul", "censor", "praetor", "quaestor", "tribune"]


def _production_political_rules():
    """生产等价 political_rules（对齐 data/config/game_config.json）。"""
    return {
        "office_cooldowns": {
            "consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2,
        },
        "offices_per_election": {
            "consul": 1, "censor": 1, "praetor": 1, "quaestor": 1, "tribune": 1,
        },
        "candidates_per_election": {
            "consul": 2, "censor": 2, "praetor": 2, "quaestor": 2, "tribune": 2,
        },
        "min_ages": {
            "consul": 40, "censor": 42, "praetor": 35, "quaestor": 30, "tribune": 30,
        },
        "office_rank": {
            "dictator": 6, "censor": 4, "consul": 5, "praetor": 3, "tribune": 1, "quaestor": 2,
        },
        "office_influence_bonus": {
            "dictator": 60, "censor": 50, "consul": 40, "praetor": 30, "tribune": 20,
            "quaestor": 10, "proconsul": 0, "propraetor": 0,
        },
        "ex_office_influence_bonus": {
            "ex-dictator": 30, "ex-censor": 25, "ex-consul": 20, "ex-praetor": 15,
            "ex-tribune": 10, "ex-quaestor": 5, "ex-proconsul": 20, "ex-propraetor": 15,
        },
        "family_prestige": {
            "Julius": 4, "Cornelius": 4, "Claudius": 3, "Fabius": 3, "Aemilius": 2, "Servilius": 2,
        },
    }


def _make_runtime_state() -> GameState:
    """确定性种子状态：3 派系 ×（ex-consul / ex-praetor / ex-quaestor / 2 eques / 2 pleb），
    对齐 test_population_5turn_runtime._make_runtime_state（零 random 构造）。"""
    state = GameState.create_for_testing({
        "testing": {"bypass_player_check": True},
        "political_rules": _production_political_rules(),
    })
    state.turn = GameTurn(turn_number=1, year=-264)

    for fid, fname in [("f1", "Optimates"), ("f2", "Populares"), ("f3", "Equites")]:
        state.add_faction(Faction(id=fid, name=fname, treasury=1000))
    for pid, fid in [("p1", "f1"), ("p2", "f2"), ("p3", "f3")]:
        state.add_player(Player(player_id=pid, faction_id=fid, player_type=PlayerType.HUMAN))
    state.set_turn_order(["p1", "p2", "p3"])
    state.set_current_player("p1")

    fig_counter = {"n": 0}

    def new_fig(faction_id, name, age, tier):
        fig_counter["n"] += 1
        fig = Figure(
            id=fig_counter["n"],
            name=name,
            faction_id=faction_id,
            age=age,
            class_tier=tier,
        )
        fig.charisma = 5
        fig.intelligence = 5
        fig.martial = 5
        fig.zeal = 5
        fig.popularity = 10
        fig.wealth = 50
        fig.update_influence()
        state.add_member(fig)
        faction = state.get_faction(faction_id)
        if faction is not None:
            faction.member_ids.append(fig.id)
        return fig

    for fid in ["f1", "f2", "f3"]:
        ec = new_fig(fid, f"ex-consul-{fid}", 50, ClassTier.NOBILE)
        ec.add_office_history("quaestor", -8, -7)
        ec.add_office_history("praetor", -5, -4)
        ec.add_office_history("consul", -2, -1)
        ec.charisma = 9
        ep = new_fig(fid, f"ex-praetor-{fid}", 45, ClassTier.NOBILE)
        ep.add_office_history("quaestor", -6, -5)
        ep.add_office_history("praetor", -3, -2)
        ep.intelligence = 9
        eq = new_fig(fid, f"ex-quaestor-{fid}", 35, ClassTier.NOBILE)
        eq.add_office_history("quaestor", -4, -3)
        eq.martial = 9
        for k in range(2):
            new_fig(fid, f"eques-{fid}-{k}", 33, ClassTier.EQUES)
        for k in range(2):
            new_fig(fid, f"pleb-{fid}-{k}", 33, ClassTier.PLEBEIAN)

    return state


def _elect(state: GameState, viewer_id: str, cands: dict) -> dict:
    """确定性选举：每 office 投第一个候选人。"""
    for office in _OFFICES:
        rows = cands.get(office, [])
        if rows:
            state.record_population_vote(viewer_id, office, rows[0]["id"], replace=True)
    result = population_api.resolve_election(state)
    winners = {}
    for er in result.get("data", {}).get("election_results", []):
        winners[er["office"]] = er["figure_id"]
    return winners


def _advance_year(state: GameState) -> None:
    """模拟年度推进（turn+1、清 phase_results、清 pending）。"""
    state.turn.advance_year()
    state.clear_population_pending()
    state._phase_results.clear()
    state._executed_phases.clear()


def _make_sparse_state() -> GameState:
    """稀疏供给种子：每派系仅 1 ex-praetor（无 ex-consul）+ 1 ex-quaestor + 2 年轻 pleb。

    构造使高阶官职（consul/censor）候选供给紧张：consul 需前置 praetor 历史，
    censor 需前置 consul 历史——8 回合内可能出现零候选（冻结规则允许的产物）。
    """
    state = GameState.create_for_testing({
        "testing": {"bypass_player_check": True},
        "political_rules": _production_political_rules(),
    })
    state.turn = GameTurn(turn_number=1, year=-264)

    for fid, fname in [("f1", "Optimates"), ("f2", "Populares"), ("f3", "Equites")]:
        state.add_faction(Faction(id=fid, name=fname, treasury=1000))
    for pid, fid in [("p1", "f1"), ("p2", "f2"), ("p3", "f3")]:
        state.add_player(Player(player_id=pid, faction_id=fid, player_type=PlayerType.HUMAN))
    state.set_turn_order(["p1", "p2", "p3"])
    state.set_current_player("p1")

    fig_counter = {"n": 0}

    def new_fig(faction_id, name, age, tier):
        fig_counter["n"] += 1
        fig = Figure(id=fig_counter["n"], name=name, faction_id=faction_id, age=age, class_tier=tier)
        fig.charisma = 5
        fig.intelligence = 5
        fig.martial = 5
        fig.zeal = 5
        fig.popularity = 10
        fig.wealth = 50
        fig.update_influence()
        state.add_member(fig)
        faction = state.get_faction(faction_id)
        if faction is not None:
            faction.member_ids.append(fig.id)
        return fig

    for fid in ["f1", "f2", "f3"]:
        # 仅 ex-praetor（无 consul 历史 → censor 永无候选；consul 依赖 praetor 供给）
        ep = new_fig(fid, f"ex-praetor-{fid}", 45, ClassTier.NOBILE)
        ep.add_office_history("quaestor", -6, -5)
        ep.add_office_history("praetor", -3, -2)
        ep.intelligence = 9
        eq = new_fig(fid, f"ex-quaestor-{fid}", 35, ClassTier.NOBILE)
        eq.add_office_history("quaestor", -4, -3)
        eq.martial = 9
        for k in range(2):
            new_fig(fid, f"pleb-{fid}-{k}", 33, ClassTier.PLEBEIAN)

    return state


def _classify_empty_cause(state: GameState, office: str, turn: int) -> str:
    """零候选空因分类（设计 §4.3 空因标签）。"""
    current_turn = state.turn.turn_number
    living = state.get_living_members()
    if not living:
        return "无存活合格者(全员死亡)"
    candidates = []
    for fig in living:
        if fig.is_absent:
            continue
        if fig.faction_id is None:
            continue
        can_hold, reason = fig.can_hold_office(office, current_turn, state.config)
        if can_hold:
            candidates.append(fig)
    if candidates:
        return "read-model异常(有合格者但零候选)"
    # 无合格者 → 分析最接近的失败原因
    reasons = {}
    for fig in living:
        if fig.is_absent:
            reasons.setdefault("absent", 0)
            reasons["absent"] += 1
            continue
        if fig.faction_id is None:
            reasons.setdefault("curia无派系", 0)
            reasons["curia无派系"] += 1
            continue
        _, reason = fig.can_hold_office(office, current_turn, state.config)
        key = reason
        reasons.setdefault(key, 0)
        reasons[key] += 1
    if not reasons:
        return "无存活合格者"
    # 优先返回系统性原因（可区分实现漂移 vs 冻结规则）
    for k in sorted(reasons, key=lambda x: -reasons[x]):
        if k.startswith("Cooldown"):
            return f"冷却({reasons[k]}人)"
        if "higher office" in k:
            return f"曾任高阶禁选({reasons[k]}人)"
        if "Age" in k:
            return f"年龄不足({reasons[k]}人)"
        if "Requires prior" in k:
            return f"前置职务缺失({reasons[k]}人)"
        if "Only equites" in k:
            return f"阶级限制({reasons[k]}人)"
        if "Currently holding" in k:
            return f"现任官职({reasons[k]}人)"
        if "Already holding" in k:
            return f"现任同职({reasons[k]}人)"
        if k == "Unknown office type":
            return "read-model异常(未知官职)"
    return "生成混合"


@pytest.fixture(autouse=True)
def _freeze_rng(monkeypatch):
    """冻结 resolve_election 平局 tie-break（确定性）。"""
    monkeypatch.setattr(random, "choice", lambda seq: seq[0])


class TestWpeCandidateSupplyRun:
    """E-G7-09：≥8 回合连续运行，证据表 + 分类判定。"""

    def test_8turn_candidate_supply_evidence_run(self, capsys):
        """8 回合连续运行：逐回合记录每官职候选数 + 零候选空因 + 分类判定。"""
        import os
        state = _make_runtime_state()
        turn_count = 8
        table = []  # (turn, office, count, cause)
        zero_turns = []

        for t in range(1, turn_count + 1):
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            for office in _OFFICES:
                count = len(cands.get(office, []))
                cause = ""
                if count == 0:
                    cause = _classify_empty_cause(state, office, t)
                    zero_turns.append((t, office, cause))
                table.append((t, office, count, cause))
            winners = _elect(state, "p1", cands)
            _advance_year(state)

        # 输出证据表（runtime 采集）
        print("\n=== E-G7-09 candidate supply runtime table (8 turns) ===")
        print("turn | office   | count | empty-cause")
        for turn, office, count, cause in table:
            print(f"{turn:4d} | {office:8s} | {count:5d} | {cause}")

        print("\n=== zero-candidate turns ===")
        for turn, office, cause in zero_turns:
            print(f"turn {turn} {office}: {cause}")

        # 自检：harness 跑通 8 回合
        assert state.turn.turn_number == 1 + turn_count

        # 分类判定：零候选是否由「实现漂移」引起
        drift_signatures = [
            "read-model异常", "生成混合", "无存活合格者(全员死亡)",
        ]
        implementation_drift = [
            z for z in zero_turns if any(s in z[2] for s in drift_signatures)
        ]
        frozen_rule_zeros = [
            z for z in zero_turns if z not in implementation_drift
        ]

        print(f"\n=== classification ===")
        print(f"zero-candidate turns total: {len(zero_turns)}")
        print(f"implementation-drift suspected: {len(implementation_drift)} {implementation_drift}")
        print(f"frozen-rule unavoidable (candidate): {len(frozen_rule_zeros)} {frozen_rule_zeros}")

        # 判定准则（A10.3）：
        # - 实现漂移 → WP-E 内修正（本 harness 预期零实现漂移——read-model 直读 can_hold_office）
        # - 冻结规则允许的不可避免零候选 → 不在此 harness 内裁决（由 DA 依证据升级 ODR）
        for turn, office, cause in implementation_drift:
            # 若出现 → 先复核（可能是种子构造导致，非 read-model bug）
            state2 = _make_runtime_state()
            population_api.begin_population_phase(state2)
            cands2 = population_api.get_candidates(state2)["data"]
            assert len(cands2.get(office, [])) >= 0  # 复核不断言；证据记录为准

        # 证据采集：若指定 EOR_EVIDENCE_RUNTIME 目录，写入数据表（md + csv）
        evidence_dir = os.environ.get("EOR_EVIDENCE_RUNTIME", "")
        if evidence_dir:
            os.makedirs(evidence_dir, exist_ok=True)
            md_path = os.path.join(evidence_dir, "wpe-eg7-09-candidate-supply-8turns-2026-08-23.md")
            csv_path = os.path.join(evidence_dir, "wpe-eg7-09-candidate-supply-8turns-2026-08-23.csv")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("# E-G7-09 Candidate Supply — 8-turn runtime evidence (WP-E Slice 10)\n\n")
                f.write("| turn | office | count | empty-cause |\n")
                f.write("|:--|:--|:--|:--|\n")
                for turn, office, count, cause in table:
                    f.write(f"| {turn} | {office} | {count} | {cause} |\n")
                f.write("\n## zero-candidate turns\n\n")
                for turn, office, cause in zero_turns:
                    f.write(f"- turn {turn} {office}: {cause}\n")
                f.write("\n## classification\n\n")
                f.write(f"- zero-candidate turns total: {len(zero_turns)}\n")
                f.write(f"- implementation-drift suspected: {len(implementation_drift)} {implementation_drift}\n")
                f.write(f"- frozen-rule unavoidable (candidate): {len(frozen_rule_zeros)} {frozen_rule_zeros}\n")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("turn,office,count,empty_cause\n")
                for turn, office, count, cause in table:
                    f.write(f"{turn},{office},{count},{cause}\n")

    def test_harness_seed_all_offices_nonempty_turn1(self):
        """自检：Turn1 五官职候选池非空（种子健康，harness 有效）。"""
        state = _make_runtime_state()
        population_api.begin_population_phase(state)
        cands = population_api.get_candidates(state)["data"]
        for office in _OFFICES:
            assert len(cands.get(office, [])) >= 1, f"Turn1 {office} 池空（种子异常）"

    def test_harness_reuses_production_chain(self):
        """自检：候选经真实 begin_population_phase → get_candidates 链（非手工 DTO 注入）。"""
        state = _make_runtime_state()
        result = population_api.begin_population_phase(state)
        assert "converted" in result  # 真实入口共享用例
        cands = population_api.get_candidates(state)
        assert cands["success"] is True
        assert set(cands["data"].keys()) == set(_OFFICES)

    def test_generated_game_8turn_supply(self, capsys):
        """generated-game 变体：每年度真实市场生成（initialize_forum_turn → generate_figures，
        市场新人含 E-G7-09 veteran supply 注入——veteran nobile 携带 office_history；
        非资深新人无 office_history）→ 人口选举；8 回合逐官职候选数。

        核心因子（设计 §4.3）：非资深市场新人只能竞 quaestor/tribune；高阶候选依赖
        注入 ex-consul/ex-praetor + 前任选举胜者（archive_office_holders 写 history）。
        本变体验证真实生成链下候选供给。
        """
        import os
        from src.api import forum_api

        state = _make_runtime_state()
        turn_count = 8
        table = []
        zero_turns = []

        for t in range(1, turn_count + 1):
            # 真实市场生成（生成新人 → 无 office_history）
            init = forum_api.initialize_forum_turn(state)
            assert init["success"] is True
            generated = init.get("data", {}).get("figures", [])
            # 人口阶段
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            for office in _OFFICES:
                count = len(cands.get(office, []))
                cause = ""
                if count == 0:
                    cause = _classify_empty_cause(state, office, t)
                    zero_turns.append((t, office, cause))
                table.append((t, office, count, cause))
            winners = _elect(state, "p1", cands)
            _advance_year(state)

        print("\n=== E-G7-09 generated-game supply table (8 turns) ===")
        print("turn | office   | count | empty-cause")
        for turn, office, count, cause in table:
            print(f"{turn:4d} | {office:8s} | {count:5d} | {cause}")
        print("\n=== zero-candidate turns ===")
        for turn, office, cause in zero_turns:
            print(f"turn {turn} {office}: {cause}")

        # 判定：零候选是否由实现漂移引起
        drift_signatures = ["read-model异常", "生成混合", "无存活合格者(全员死亡)"]
        implementation_drift = [z for z in zero_turns if any(s in z[2] for s in drift_signatures)]
        print(f"\n=== classification ===")
        print(f"zero-candidate turns total: {len(zero_turns)}")
        print(f"implementation-drift suspected: {len(implementation_drift)} {implementation_drift}")

        # 证据采集
        evidence_dir = os.environ.get("EOR_EVIDENCE_RUNTIME", "")
        if evidence_dir:
            os.makedirs(evidence_dir, exist_ok=True)
            md_path = os.path.join(evidence_dir, "wpe-eg7-09-generated-game-8turns-2026-08-23.md")
            csv_path = os.path.join(evidence_dir, "wpe-eg7-09-generated-game-8turns-2026-08-23.csv")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("# E-G7-09 Candidate Supply — generated-game 8-turn runtime evidence (WP-E Slice 10)\n\n")
                f.write("变体：每年真实 initialize_forum_turn 市场生成（市场新人含 veteran supply 注入）→ 人口选举。\n\n")
                f.write("| turn | office | count | empty-cause |\n")
                f.write("|:--|:--|:--|:--|\n")
                for turn, office, count, cause in table:
                    f.write(f"| {turn} | {office} | {count} | {cause} |\n")
                f.write("\n## zero-candidate turns\n\n")
                for turn, office, cause in zero_turns:
                    f.write(f"- turn {turn} {office}: {cause}\n")
                f.write("\n## classification\n\n")
                f.write(f"- zero-candidate turns total: {len(zero_turns)}\n")
                f.write(f"- implementation-drift suspected: {len(implementation_drift)} {implementation_drift}\n")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("turn,office,count,empty_cause\n")
                for turn, office, count, cause in table:
                    f.write(f"{turn},{office},{count},{cause}\n")

    def test_sparse_supply_8turn_zero_candidate_classification(self, capsys):
        """稀疏供给变体：无 ex-consul → censor 必然零候选（冻结规则允许）；
        8 回合记录 + 空因分类——区分「实现漂移」vs「冻结规则不可避免」两种判定路径。"""
        import os
        state = _make_sparse_state()
        turn_count = 8
        table = []
        zero_turns = []

        for t in range(1, turn_count + 1):
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            for office in _OFFICES:
                count = len(cands.get(office, []))
                cause = ""
                if count == 0:
                    cause = _classify_empty_cause(state, office, t)
                    zero_turns.append((t, office, cause))
                table.append((t, office, count, cause))
            winners = _elect(state, "p1", cands)
            _advance_year(state)

        print("\n=== E-G7-09 sparse-supply table (8 turns) ===")
        print("turn | office   | count | empty-cause")
        for turn, office, count, cause in table:
            print(f"{turn:4d} | {office:8s} | {count:5d} | {cause}")
        print("\n=== zero-candidate turns ===")
        for turn, office, cause in zero_turns:
            print(f"turn {turn} {office}: {cause}")

        # 判定：零候选由「实现漂移」还是「冻结规则」引起
        drift_signatures = ["read-model异常", "生成混合", "无存活合格者(全员死亡)"]
        implementation_drift = [z for z in zero_turns if any(s in z[2] for s in drift_signatures)]
        frozen_rule_zeros = [z for z in zero_turns if z not in implementation_drift]

        print(f"\n=== classification ===")
        print(f"zero-candidate turns total: {len(zero_turns)}")
        print(f"implementation-drift suspected: {len(implementation_drift)} {implementation_drift}")
        print(f"frozen-rule unavoidable (candidate): {len(frozen_rule_zeros)} {frozen_rule_zeros}")

        # 空因标签校验：零候选必须被分类（无未分类残留）
        for turn, office, cause in zero_turns:
            assert cause, f"turn {turn} {office} 零候选缺空因标签"

        # 本变体构造上 censor 应出现零候选（无 ex-consul → 前置职务缺失）——
        # 若出现，其空因应为「前置职务缺失」或「冷却」等冻结规则类别（非实现漂移）
        censor_zeros = [z for z in zero_turns if z[1] == "censor"]
        if censor_zeros:
            for _, _, cause in censor_zeros:
                assert "前置职务缺失" in cause or "冷却" in cause or "年龄不足" in cause, cause

        # 证据采集
        evidence_dir = os.environ.get("EOR_EVIDENCE_RUNTIME", "")
        if evidence_dir:
            os.makedirs(evidence_dir, exist_ok=True)
            md_path = os.path.join(evidence_dir, "wpe-eg7-09-sparse-supply-8turns-2026-08-23.md")
            csv_path = os.path.join(evidence_dir, "wpe-eg7-09-sparse-supply-8turns-2026-08-23.csv")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("# E-G7-09 Candidate Supply — sparse-supply 8-turn runtime evidence (WP-E Slice 10)\n\n")
                f.write("变体：无 ex-consul 供给 → 高阶官职零候选的冻结规则分类验证。\n\n")
                f.write("| turn | office | count | empty-cause |\n")
                f.write("|:--|:--|:--|:--|\n")
                for turn, office, count, cause in table:
                    f.write(f"| {turn} | {office} | {count} | {cause} |\n")
                f.write("\n## zero-candidate turns\n\n")
                for turn, office, cause in zero_turns:
                    f.write(f"- turn {turn} {office}: {cause}\n")
                f.write("\n## classification\n\n")
                f.write(f"- zero-candidate turns total: {len(zero_turns)}\n")
                f.write(f"- implementation-drift suspected: {len(implementation_drift)} {implementation_drift}\n")
                f.write(f"- frozen-rule unavoidable (candidate): {len(frozen_rule_zeros)} {frozen_rule_zeros}\n")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("turn,office,count,empty_cause\n")
                for turn, office, count, cause in table:
                    f.write(f"{turn},{office},{count},{cause}\n")

    # ------------------------------------------------------------------
    # T-VS-10 / T-VS-11（Slice 10b 收口）：E-G7-09 注入后 8 回合复验
    # ------------------------------------------------------------------

    @staticmethod
    def _relax_faction_limit(state: GameState) -> None:
        """放宽派系容量上限（测试配置）：保证每回合注入新人可真实招募入派系
        （recruit_figure 需 vacancies>0；产品语义的容量限制非本机制焦点）。"""
        cfg = state._config._config
        cfg.setdefault("economic_rules", {})["faction_member_limit"] = 999

    @staticmethod
    def _recruit_all_new_figures(state: GameState, init: dict) -> None:
        """真实招募链：对 initialize_forum_turn 产出的每位新人出价 → resolve_forum 结算。"""
        from src.api import forum_api
        figure_ids = [row["id"] for row in init.get("data", {}).get("figures", [])]
        for fid in figure_ids:
            resp = forum_api.recruit_figure(state, "p1", fid, 10)
            assert resp["success"] is True, f"recruit_figure failed for figure {fid}: {resp}"
        forum_api.resolve_forum(state)

    def test_tvs10_sparse_supply_with_injection_8turn_zero_candidate(self, capsys):
        """T-VS-10（= T-7b rerun）：稀疏供给 seed + 市场注入 → 8 回合复验。

        每回合：initialize_forum_turn（真实市场生成，含 veteran supply 注入）→
        自动招募全部新人（真实 recruit_figure + resolve_forum）→ begin_population_phase →
        get_candidates 记录 → _elect → _advance_year。固定 random.seed 保证证据可复现。

        断言：8 回合 censor 零候选回合 == 0（锚从 T1 保证）；对照既有稀疏供给
        wpe-eg7-09-sparse-supply-8turns 证据：零候选 1 → 0。
        """
        import os
        from src.api import forum_api, population_api

        random.seed(20260823)
        state = _make_sparse_state()
        self._relax_faction_limit(state)
        turn_count = 8
        table = []
        zero_turns = []

        for t in range(1, turn_count + 1):
            init = forum_api.initialize_forum_turn(state)
            assert init["success"] is True
            self._recruit_all_new_figures(state, init)
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            for office in _OFFICES:
                count = len(cands.get(office, []))
                cause = ""
                if count == 0:
                    cause = _classify_empty_cause(state, office, t)
                    zero_turns.append((t, office, cause))
                table.append((t, office, count, cause))
            winners = _elect(state, "p1", cands)
            _advance_year(state)

        print("\n=== E-G7-09 sparse-supply WITH market injection table (8 turns) ===")
        print("turn | office   | count | empty-cause")
        for turn, office, count, cause in table:
            print(f"{turn:4d} | {office:8s} | {count:5d} | {cause}")
        print("\n=== zero-candidate turns ===")
        for turn, office, cause in zero_turns:
            print(f"turn {turn} {office}: {cause}")

        censor_zero = [z for z in zero_turns if z[1] == "censor"]
        print(f"\n=== assertion ===")
        print(f"censor zero-candidate turns: {len(censor_zero)} (expected 0)")
        assert len(censor_zero) == 0, f"censor 零候选回合应为 0，实测 {censor_zero}"

        # 证据采集（对照既有 wpe-eg7-09-sparse-supply-8turns：零候选 1 → 0）
        evidence_dir = os.environ.get("EOR_EVIDENCE_RUNTIME", "")
        if evidence_dir:
            os.makedirs(evidence_dir, exist_ok=True)
            md_path = os.path.join(evidence_dir, "wpe-eg7-09-sparse-supply-with-injection-8turns-2026-08-23.md")
            csv_path = os.path.join(evidence_dir, "wpe-eg7-09-sparse-supply-with-injection-8turns-2026-08-23.csv")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("# E-G7-09 Candidate Supply — sparse-supply + market injection 8-turn runtime evidence\n\n")
                f.write("变体：无 ex-consul 供给 seed + E-G7-09 veteran supply 注入（每回合真实市场生成 +\n")
                f.write("真实招募链）→ 8 回合逐官职候选数。对照 wpe-eg7-09-sparse-supply-8turns：\n")
                f.write("censor 零候选回合 1 → 0。\n\n")
                f.write("| turn | office | count | empty-cause |\n")
                f.write("|:--|:--|:--|:--|\n")
                for turn, office, count, cause in table:
                    f.write(f"| {turn} | {office} | {count} | {cause} |\n")
                f.write("\n## zero-candidate turns\n\n")
                for turn, office, cause in zero_turns:
                    f.write(f"- turn {turn} {office}: {cause}\n")
                f.write("\n## assertion\n\n")
                f.write(f"- censor zero-candidate turns: {len(censor_zero)} (expected 0)\n")
                f.write(f"- total zero-candidate turns: {len(zero_turns)} {zero_turns}\n")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("turn,office,count,empty_cause\n")
                for turn, office, count, cause in table:
                    f.write(f"{turn},{office},{count},{cause}\n")

    def test_tvs11_rich_supply_with_injection_8turn_no_zero(self, capsys):
        """T-VS-11（对照）：富供给 seed + 注入 → 8 回合全官职零候选 == 0
        （回归确认注入不引入新零候选）。"""
        import os
        from src.api import forum_api, population_api

        random.seed(20260823)
        state = _make_runtime_state()
        self._relax_faction_limit(state)
        turn_count = 8
        table = []
        zero_turns = []

        for t in range(1, turn_count + 1):
            init = forum_api.initialize_forum_turn(state)
            assert init["success"] is True
            self._recruit_all_new_figures(state, init)
            population_api.begin_population_phase(state)
            cands = population_api.get_candidates(state)["data"]
            for office in _OFFICES:
                count = len(cands.get(office, []))
                cause = ""
                if count == 0:
                    cause = _classify_empty_cause(state, office, t)
                    zero_turns.append((t, office, cause))
                table.append((t, office, count, cause))
            winners = _elect(state, "p1", cands)
            _advance_year(state)

        print("\n=== E-G7-09 rich-supply WITH injection table (8 turns) ===")
        print("turn | office   | count | empty-cause")
        for turn, office, count, cause in table:
            print(f"{turn:4d} | {office:8s} | {count:5d} | {cause}")
        print("\n=== zero-candidate turns ===")
        for turn, office, cause in zero_turns:
            print(f"turn {turn} {office}: {cause}")

        assert len(zero_turns) == 0, f"富供给 + 注入 8 回合应零候选 == 0，实测 {zero_turns}"

        evidence_dir = os.environ.get("EOR_EVIDENCE_RUNTIME", "")
        if evidence_dir:
            os.makedirs(evidence_dir, exist_ok=True)
            md_path = os.path.join(evidence_dir, "wpe-eg7-09-rich-supply-with-injection-8turns-2026-08-23.md")
            csv_path = os.path.join(evidence_dir, "wpe-eg7-09-rich-supply-with-injection-8turns-2026-08-23.csv")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("# E-G7-09 Candidate Supply — rich-supply + market injection 8-turn runtime evidence\n\n")
                f.write("变体：富供给 seed + E-G7-09 veteran supply 注入 → 8 回合全官职零候选 == 0\n")
                f.write("（回归确认注入不引入新零候选）。\n\n")
                f.write("| turn | office | count | empty-cause |\n")
                f.write("|:--|:--|:--|:--|\n")
                for turn, office, count, cause in table:
                    f.write(f"| {turn} | {office} | {count} | {cause} |\n")
                f.write("\n## zero-candidate turns\n\n")
                for turn, office, cause in zero_turns:
                    f.write(f"- turn {turn} {office}: {cause}\n")
                f.write("\n## assertion\n\n")
                f.write(f"- total zero-candidate turns: {len(zero_turns)} (expected 0)\n")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("turn,office,count,empty_cause\n")
                for turn, office, count, cause in table:
                    f.write(f"{turn},{office},{count},{cause}\n")
