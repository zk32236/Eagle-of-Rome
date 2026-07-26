"""
Figure Generation System — Figure creation workflow for forum initialization (C-09a).

Extracted from CLI phase_forum.py to provide a single source of truth for
figure generation, reusable by both CLI and future GUI.

Debug Logging Requirement (SA-Development-Workflow §A5):
  Every operation produces a DEBUG-level log_event() output.
"""

import logging
import random
from typing import List, Optional, Dict, TYPE_CHECKING

from src.core.entities.figure import Figure, ClassTier, RomanNameGenerator

if TYPE_CHECKING:
    from src.core.game_state import GameState


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

    # --- 2. Generate normal figures ---
    for _ in range(max(0, count)):
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

    for _ in range(max(0, count)):
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
