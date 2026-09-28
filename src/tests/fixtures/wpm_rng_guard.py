# src/tests/fixtures/wpm_rng_guard.py
"""WP-M slice test-isolation helper (cross-test global-RNG guard).

The WP-M slice (M-S1) adds ``test_api/test_wpm_s1_vacancy_resilience.py``,
whose scenarios repeatedly construct ``GameState`` objects through
``GameState.create_for_testing`` / ``make_base_state``.  ``GameState``
initialization consumes the **process-wide** ``random`` stream
(``_initialize_mortality_pool`` -> ``random.shuffle``), and several WP-M
scenarios also draw from that same stream.

That global stream is shared by every test in the run.  Without restoring it,
inserting the WP-M suites shifts the RNG stream seen by later, order-sensitive
offscreen GUI/QML regression tests (for example
``test_gui/test_senate_layout_regression.py``); the population-candidate pool
and the resulting consul election change, which flips the Senate submission
path and makes that test fail with a pre-existing, unrelated assertion.  The
same test is green when the suite runs without the WP-M suites, i.e. the
regression is induced purely by cross-test global-RNG leakage.

This fixture saves the global ``random`` state on entry and restores it on
exit, so the WP-M suites have a **net-zero** effect on the shared RNG stream
and the suite-wide RNG trajectory matches the pre-WP-M baseline.  It changes
no product semantics and does not weaken any assertion.

Mechanism mirrors ``src/tests/fixtures/wpo_rng_guard.py`` (WP-O O-AC-08).
"""
import random

import pytest


@pytest.fixture(autouse=True)
def _wpm_preserve_global_random_state():
    """Restore the process-wide ``random`` state after every WP-M test."""
    saved_state = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved_state)
