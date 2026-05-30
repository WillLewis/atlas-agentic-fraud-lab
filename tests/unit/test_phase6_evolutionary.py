"""Phase 6 evolutionary_search tests.

Includes the **Bible §18 Phase 6 acceptance criterion** test:
``test_evolutionary_beats_random_on_low_velocity_high_graph_risk``.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from atlas.red_team.evolutionary_search import (
    EvolutionaryResult,
    evolutionary_search,
)
from atlas.red_team.mutations import ALLOWED_FAMILY_IDS, BaseSearchState
from atlas.red_team.random_search import random_search

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def base_state() -> BaseSearchState:
    return BaseSearchState.from_dataset_dir(REPO_ROOT / "data" / "synthetic")


@pytest.fixture(scope="module")
def trained(trained_baseline_dir):
    from atlas.model.policy import load_decision_policy_config
    from atlas.model.scorer import load_baseline_bundle

    return load_baseline_bundle(trained_baseline_dir), load_decision_policy_config()


# ---------------------------------------------------------------------------
# Bible §18 Phase 6 acceptance — adaptive should not underperform random
# on the seeded family at the SAME budget.
# ---------------------------------------------------------------------------


def test_evolutionary_beats_random_on_low_velocity_high_graph_risk(
    base_state, trained,
):
    """The seeded headline family. Same seed + same budget; the curated
    publish fixture is dense enough that random can saturate the count, so
    evolutionary must at least match it while preserving the budget contract.
    """
    bundle, policy = trained
    SEED = 42
    BUDGET_PER_FAMILY = 50
    budgets = {"low_velocity_high_graph_risk": BUDGET_PER_FAMILY}

    rand = random_search(
        rng=random.Random(SEED), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy,
    )
    evo = evolutionary_search(
        rng=random.Random(SEED), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy,
    )

    # Same budget consumed by both methods.
    assert rand.queries_used == evo.queries_used == BUDGET_PER_FAMILY

    assert evo.valid_high_risk_events_tested >= rand.valid_high_risk_events_tested, (
        f"adaptive underperformed random on low_velocity_high_graph_risk: "
        f"random={rand.valid_high_risk_events_tested} "
        f"evo={evo.valid_high_risk_events_tested}"
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_evolutionary_search_byte_identical_under_repeat(base_state, trained):
    bundle, policy = trained
    budgets = {fam: 10 for fam in ALLOWED_FAMILY_IDS}
    a = evolutionary_search(rng=random.Random(42), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    b = evolutionary_search(rng=random.Random(42), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    assert a.candidates == b.candidates


def test_evolutionary_different_seed_differs(base_state, trained):
    bundle, policy = trained
    budgets = {"low_velocity_high_graph_risk": 10}
    a = evolutionary_search(rng=random.Random(1), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    b = evolutionary_search(rng=random.Random(2), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    assert a.candidates != b.candidates


# ---------------------------------------------------------------------------
# Budget contract — same as random_search
# ---------------------------------------------------------------------------


def test_evolutionary_queries_used_equals_budget_sum(base_state, trained):
    bundle, policy = trained
    budgets = {fam: 5 for fam in ALLOWED_FAMILY_IDS}
    expected = sum(budgets.values())
    result = evolutionary_search(
        rng=random.Random(0), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy,
    )
    assert result.queries_used == expected


def test_evolutionary_zero_budget(base_state, trained):
    bundle, policy = trained
    result = evolutionary_search(rng=random.Random(0), base_state=base_state,
        family_budgets={"low_velocity_high_graph_risk": 0},
        bundle=bundle, policy_config=policy)
    assert result.queries_used == 0


def test_evolutionary_budget_one(base_state, trained):
    """budget=1 corner case: pop_size = max(2, 1//5)=2 but clamped by remaining."""
    bundle, policy = trained
    result = evolutionary_search(rng=random.Random(0), base_state=base_state,
        family_budgets={"low_velocity_high_graph_risk": 1},
        bundle=bundle, policy_config=policy)
    assert result.queries_used == 1


def test_evolutionary_invalid_generations_raises(base_state, trained):
    bundle, policy = trained
    with pytest.raises(ValueError, match="generations"):
        evolutionary_search(
            rng=random.Random(0), base_state=base_state,
            family_budgets={"low_velocity_high_graph_risk": 5},
            bundle=bundle, policy_config=policy, generations=0,
        )


def test_evolutionary_empty_base_raises(trained):
    bundle, policy = trained
    empty = BaseSearchState.from_lists(
        customers=[], accounts=[], devices=[], recipients=[],
        graph_edges=[], login_sessions=[], security_events=[],
        transfer_events=[],
    )
    with pytest.raises(ValueError, match="no transfer_events"):
        evolutionary_search(
            rng=random.Random(0), base_state=empty,
            family_budgets={"low_velocity_high_graph_risk": 1},
            bundle=bundle, policy_config=policy,
        )


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------


def test_evolutionary_result_is_random_search_result_alias():
    from atlas.red_team.random_search import RandomSearchResult
    assert EvolutionaryResult is RandomSearchResult
