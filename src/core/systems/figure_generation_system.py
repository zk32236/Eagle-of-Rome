"""
Figure Generation System — Figure creation workflow for forum initialization (C-09a).

Extracted from CLI phase_forum.py to provide a single source of truth for
figure generation, reusable by both CLI and future GUI.

Debug Logging Requirement (SA-Development-Workflow §A5):
  Every operation produces a DEBUG-level log_event() output.
"""

import logging
import random
from typing import List, Optional, Dict, Tuple, TYPE_CHECKING

from src.core.entities.figure import Figure, ClassTier, RomanNameGenerator

if TYPE_CHECKING:
    from src.core.game_state import GameState


# --- E-G7-09 (ODR-WP-E-01): veteran supply defaults (code-level; config optional) ---
# forum_rules.veteran_supply block; every key read via .get(key, default) so the
# mechanism stays active even when the config block is absent.
_DEFAULT_VETERAN_SUPPLY: Dict = {
    "enabled": True,
    "min_veteran_nobiles": 1,
    "max_veteran_nobiles": 2,
    "min_ex_consul_count": 1,
    "censor_anchor_years_ago": 1,
    "history_years_ago_min": 2,
    "history_years_ago_max": 8,
    "ex_consul_probability": 0.5,
    "age_min": 45,
    "age_max": 58,
}


def _read_veteran_supply_config(forum_rules: Dict) -> Dict:
    """Read the forum_rules.veteran_supply block with code-level defaults.

    All keys are read via .get(key, default) so a missing block (or missing key)
    falls back to the defaults and the mechanism stays effective.
    """
    vs = forum_rules.get("veteran_supply", {}) if isinstance(forum_rules, dict) else {}
    plan = {}
    for key, default in _DEFAULT_VETERAN_SUPPLY.items():
        raw = vs.get(key, default) if isinstance(vs, dict) else default
        if key == "enabled":
            plan[key] = bool(raw)
        elif key == "ex_consul_probability":
            plan[key] = float(raw)
        else:
            plan[key] = int(raw)
    return plan


def _build_cursus(fig: Figure, ct: int, offices: List[Tuple[str, int]]) -> None:
    """Attach a full office cursus to a figure (all terms in the past).

    Uses fig.add_office_history(office, start_turn): end_turn = start_turn + 1,
    is_active=False, office=None — structurally identical to the terms written by
    archive_office_holders (population_api). Each start_turn must be < ct (past).
    """
    for office_type, offset in offices:
        start_turn = ct + offset
        assert start_turn < ct, (
            f"veteran cursus term must be in the past: {office_type} @ {start_turn}"
        )
        fig.add_office_history(office_type, start_turn)


def _create_veteran_nobile(state: "GameState", slot: int, plan: Dict) -> Figure:
    """Create a veteran nobile (ex-consul / ex-praetor) with a full office cursus.

    slot 0 = censor-anchor: a fresh ex-consul (consul term within the cooldown
    window) that is deterministically censor-eligible and consul-cooldown-blocked
    this turn — guaranteeing >=1 censor candidate from turn 1.
    slots >= 1: ex-consul with probability ex_consul_probability, else ex-praetor;
    min_ex_consul_count-1 additional slots are forced ex-consul when configured.
    """
    ct = state.turn.turn_number
    min_ages = state.config.get("political_rules", {}).get("min_ages", {})
    min_age_consul = int(min_ages.get("consul", 40) or 40)
    min_age_censor = int(min_ages.get("censor", 42) or 42)
    age_min = int(plan["age_min"])
    age_max = int(plan["age_max"])

    if slot == 0:
        # Censor-anchor: consul @ ct - censor_anchor_years_ago (fresh, cooldown-blocked)
        anchor_ago = int(plan["censor_anchor_years_ago"])
        is_ex_consul = True
        age = random.randint(age_min, age_max)
        offices = [
            ("quaestor", -(anchor_ago + 4)),
            ("praetor", -(anchor_ago + 2)),
            ("consul", -anchor_ago),
        ]
    else:
        h = random.randint(
            int(plan["history_years_ago_min"]), int(plan["history_years_ago_max"])
        )
        forced_ex_consul = slot < max(0, int(plan["min_ex_consul_count"]))
        is_ex_consul = forced_ex_consul or random.random() < float(plan["ex_consul_probability"])
        if is_ex_consul:
            # Age: consul-year age >= min_ages.consul AND current age >= censor gate
            age = max(age_min, min_age_consul + h, min_age_censor) + random.randint(0, 3)
            offices = [
                ("quaestor", -(h + 4)),
                ("praetor", -(h + 2)),
                ("consul", -h),
            ]
        else:
            age = random.randint(age_min, age_max)
            offices = [
                ("quaestor", -(h + 2)),
                ("praetor", -h),
            ]

    fig = Figure.create_nobile(state.allocate_id(), None, age=age)
    _build_cursus(fig, ct, offices)
    if is_ex_consul:
        fig.charisma = max(fig.charisma, 7)
    else:
        fig.intelligence = max(fig.intelligence, 7)
    return fig


def _resolve_veteran_slot_count(count: int, veteran_plan: Dict) -> int:
    """Resolve k = number of reserved veteran-nobile slots this turn.

    enabled=False -> 0 (fully restores prior behavior). count<=0 -> 0.
    k = randint(min_veteran_nobiles, min(max_veteran_nobiles, count)).
    """
    if not veteran_plan.get("enabled", True):
        return 0
    if count <= 0:
        return 0
    min_v = max(0, int(veteran_plan.get("min_veteran_nobiles", 1)))
    max_v = max(min_v, int(veteran_plan.get("max_veteran_nobiles", 2)))
    return random.randint(min_v, min(max_v, count))


def _generate_normal_figures(
    state: "GameState",
    count: int,
    nobile_prob: float,
    eques_prob: float,
    veteran_plan: Dict,
) -> List[Figure]:
    """Shared core loop for normal (non-hero) figure generation.

    Reserved slots [0, k) become veteran nobiles (E-G7-09 injection); the rest use
    the existing class-probability roll (nobile / eques / plebeian). Total count
    unchanged; registration side effects preserved (add_member + curia.add_figure).
    """
    new_figures: List[Figure] = []
    count = max(0, int(count))
    k = _resolve_veteran_slot_count(count, veteran_plan)
    for i in range(count):
        if i < k:
            fig = _create_veteran_nobile(state, i, veteran_plan)
        else:
            tier_roll = random.random()
            if tier_roll < nobile_prob:
                fig = Figure.create_nobile(state.allocate_id(), None, age=random.randint(30, 50))
            elif tier_roll < nobile_prob + eques_prob:
                fig = Figure.create_eques(state.allocate_id(), None, age=random.randint(25, 40))
            else:
                fig = Figure.create_plebeian(state.allocate_id(), None, age=random.randint(20, 35))
        state.add_member(fig)
        state.curia.add_figure(fig)
        new_figures.append(fig)
    return new_figures


def _veteran_supply_log_extra(new_figures: List[Figure], veteran_plan: Dict) -> Dict:
    """Log extra describing the veteran-supply injection for this turn."""
    return {
        "enabled": bool(veteran_plan.get("enabled", True)),
        "veteran_count": sum(1 for f in new_figures if f.office_history),
        "ex_consul_count": sum(
            1 for f in new_figures if any(t.office_type == "consul" for t in f.office_history)
        ),
        "config": {
            "min_veteran_nobiles": veteran_plan.get("min_veteran_nobiles"),
            "max_veteran_nobiles": veteran_plan.get("max_veteran_nobiles"),
            "min_ex_consul_count": veteran_plan.get("min_ex_consul_count"),
            "censor_anchor_years_ago": veteran_plan.get("censor_anchor_years_ago"),
        },
    }

def generate_figures(state: "GameState") -> List[Figure]:
    """
    Generate new figures and optionally a hero for the forum initialization phase.

    Input:
        state: GameState — current game state

    Output:
        List[Figure] — flat list of all generated Figure entities

    Side effects (preserved from CLI):
        - Calls state.allocate_id() for each new Figure
        - Calls state.add_member(figure) for each
        - Calls state.curia.add_figure(figure) for each
        - For historical heroes: calls state.add_spawned_hero_id(hero_id)
        - Clears state.hero_spawned_this_turn and state.hero_to_spawn after hero generation
    """
    new_figures: List[Figure] = []

    # --- 1. Class probability configuration ---
    forum_rules = state.config.get("forum_rules", {})
    count = int(forum_rules.get("new_figures_count", 3) or 3)
    probs = forum_rules.get("class_probabilities", {})
    nobile_prob = float(probs.get("nobile", 0.1) or 0.1)
    eques_prob = float(probs.get("eques", 0.25) or 0.25)
    pleb_prob = 1.0 - nobile_prob - eques_prob
    if pleb_prob < 0:
        pleb_prob = 0.65

    # --- 2. Generate normal figures (shared core loop w/ veteran supply) ---
    veteran_plan = _read_veteran_supply_config(forum_rules)
    new_figures = _generate_normal_figures(state, count, nobile_prob, eques_prob, veteran_plan)

    # --- 3. Debug log: figure generation ---
    class_counts = {"nobile": 0, "eques": 0, "plebeian": 0}
    for fig in new_figures:
        tier_key = fig.class_tier.value if hasattr(fig.class_tier, "value") else str(fig.class_tier)
        class_counts[tier_key] = class_counts.get(tier_key, 0) + 1
    state.log_event(
        f"figure_generation_system: generated {len(new_figures)} new figures",
        level=logging.DEBUG,
        extra={
            "figure_ids": [fig.id for fig in new_figures],
            "classes": class_counts,
            "veteran_supply": _veteran_supply_log_extra(new_figures, veteran_plan),
        },
    )

    # --- 4. Hero generation (extra figure) ---
    if _should_spawn_hero(state):
        hero = _generate_hero(state)
        if hero:
            state.add_member(hero)
            state.curia.add_figure(hero)
            new_figures.append(hero)

            # Determine hero type for logging
            hero_type = "historical" if state.hero_to_spawn and state.hero_to_spawn.get("type") == "historical" else "random"
            state.log_event(
                f"figure_generation_system: hero spawned: {hero.get_formal_name()}",
                level=logging.DEBUG,
                extra={
                    "type": hero_type,
                    "figure_id": hero.id,
                    "hero_id": _get_hero_data_id(state),
                },
            )

            # Clear spawn markers
            state.hero_spawned_this_turn = False
            state.hero_to_spawn = None

    return new_figures


def _should_spawn_hero(state: "GameState") -> bool:
    """Check whether a hero should be spawned this turn."""
    return bool(state.hero_spawned_this_turn and state.hero_to_spawn)


def _generate_hero(state: "GameState") -> Optional[Figure]:
    """
    Generate a hero figure based on hero_to_spawn configuration.

    Returns:
        Figure if hero was created, None otherwise.
    """
    hero_info = state.hero_to_spawn
    if not hero_info:
        return None

    try:
        if hero_info.get("type") == "historical":
            return _create_historical_hero(state, hero_info.get("data", {}))
        else:
            return _create_random_mighty_man(state)
    except Exception as e:
        state.log_event(
            f"figure_generation_system: hero creation failed: {e}",
            level=logging.ERROR,
            extra={"error": str(e)},
        )
        return None


def _create_historical_hero(state: "GameState", data: dict) -> Figure:
    """
    Create a Figure from historical hero data.
    Logic lifted verbatim from phase_forum._create_historical_hero().
    """
    birth_year = data["birth_year"]
    current_year = state.turn.year
    age = abs(current_year - birth_year)
    figure_id = state.allocate_id()
    hero = Figure(
        id=figure_id,
        name=data["name"],
        age=age,
        martial=data["martial"],
        intelligence=data["intelligence"],
        charisma=data["charisma"],
        zeal=data["zeal"],
        family_prestige=data.get("family_prestige", 0),
    )
    hero.class_tier = ClassTier.NOBILE
    state.add_spawned_hero_id(data["id"])
    return hero


def _create_random_mighty_man(state: "GameState") -> Figure:
    """
    Generate a random mighty man (hero).
    Logic lifted verbatim from phase_forum._create_random_mighty_man().
    """
    living = state.get_living_members()
    if living:
        max_martial = max(f.martial for f in living)
        max_intel = max(f.intelligence for f in living)
        max_charisma = max(f.charisma for f in living)
        max_zeal = max(f.zeal for f in living)
    else:
        max_martial = max_intel = max_charisma = max_zeal = 5

    # Generate Roman name
    praenomen, nomen, cognomen, full_name = RomanNameGenerator.generate_nobile_name()
    figure_id = state.allocate_id()
    hero = Figure(
        id=figure_id,
        name=full_name,
        age=random.randint(30, 45),
        martial=max_martial,
        intelligence=max_intel,
        charisma=max_charisma,
        zeal=max_zeal,
        family_prestige=random.randint(1, 3),
    )
    hero.class_tier = ClassTier.NOBILE
    hero.praenomen = praenomen
    hero.nomen = nomen
    hero.cognomen = cognomen
    return hero


def _get_hero_data_id(state: "GameState") -> Optional[str]:
    """Extract the hero data ID for logging purposes."""
    hero_info = state.hero_to_spawn
    if not hero_info:
        return None
    data = hero_info.get("data", {})
    return str(data.get("id", ""))

def generate_market_figures(state: "GameState") -> List[Figure]:
    """
    Generate figures for the forum market (opens the market once per turn).

    This is a variant of generate_figures() that produces only normal figures
    (no hero), matching the existing _generate_market_figures() logic.
    It delegates to the core generation loop without hero spawn.

    Returns:
        List[Figure] — newly generated figures placed in curia.
    """
    new_figures: List[Figure] = []

    forum_rules = state.config.get("forum_rules", {})
    count = int(forum_rules.get("new_figures_count", 3) or 3)
    probs = forum_rules.get("class_probabilities", {})
    nobile_prob = float(probs.get("nobile", 0.1) or 0.1)
    eques_prob = float(probs.get("eques", 0.25) or 0.25)

    # 共享核心循环（E-G7-09 veteran supply 注入；无 hero）
    veteran_plan = _read_veteran_supply_config(forum_rules)
    new_figures = _generate_normal_figures(state, count, nobile_prob, eques_prob, veteran_plan)

    class_counts = {"nobile": 0, "eques": 0, "plebeian": 0}
    for fig in new_figures:
        tier_key = fig.class_tier.value if hasattr(fig.class_tier, "value") else str(fig.class_tier)
        class_counts[tier_key] = class_counts.get(tier_key, 0) + 1
    state.log_event(
        f"figure_generation_system: generated {len(new_figures)} market figures",
        level=logging.DEBUG,
        extra={
            "figure_ids": [fig.id for fig in new_figures],
            "classes": class_counts,
            "veteran_supply": _veteran_supply_log_extra(new_figures, veteran_plan),
        },
    )

    return new_figures

def _determine_figure_class(state: "GameState") -> str:
    """
    Roll a class tier based on configured probabilities.

    Returns:
        "nobile", "eques", or "plebeian"
    """
    forum_rules = state.config.get("forum_rules", {})
    probs = forum_rules.get("class_probabilities", {})
    nobile_prob = float(probs.get("nobile", 0.1) or 0.1)
    eques_prob = float(probs.get("eques", 0.25) or 0.25)
    pleb_prob = 1.0 - nobile_prob - eques_prob
    if pleb_prob < 0:
        pleb_prob = 0.65

    tier_roll = random.random()
    if tier_roll < nobile_prob:
        return "nobile"
    elif tier_roll < nobile_prob + eques_prob:
        return "eques"
    else:
        return "plebeian"
