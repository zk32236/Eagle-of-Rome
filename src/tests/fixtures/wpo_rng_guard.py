# src/tests/fixtures/wpo_rng_guard.py
"""WP-O slice test-isolation helper.

The WP-O slices (O-S1/O-S2/O-S3) construct many ``GameState`` objects through
``GameState.create_for_testing``.  ``GameState`` initialization consumes the
**process-wide** ``random`` stream (``_initialize_mortality_pool`` ->
``random.shuffle``) and several WP-O scenarios also exercise producers that
draw from it.

That global stream is shared by every test in the run.  Without restoring it,
inserting the WP-O suites shifts the RNG stream seen by later, order-sensitive
offscreen GUI/QML regression tests (for example
``test_gui/test_senate_layout_regression.py``); the population-candidate pool
and the resulting consul election change, which flips the Senate submission
path and makes that test fail with a pre-existing, unrelated assertion.  The
same test is green when the suite runs without the WP-O suites, i.e. the
regression is induced purely by cross-test global-RNG leakage.

This fixture saves the global ``random`` state on entry and restores it on
exit, so the WP-O suites have a **net-zero** effect on the shared RNG stream
and the suite-wide RNG trajectory matches the pre-WP-O baseline.  It changes
no product semantics and does not weaken any assertion.
"""
import random

import pytest


@pytest.fixture(autouse=True)
def _wpo_preserve_global_random_state():
    """Restore the process-wide ``random`` state after every WP-O test."""
    saved_state = random.getstate()
    try:
        yield
    finally:
        random.setstate(saved_state)
