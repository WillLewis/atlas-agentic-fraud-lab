"""Phase 6 random_search tests.

Determinism, score-query budget honored exactly, edge cases.
"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from atlas.red_team.mutations import ALLOWED_FAMILY_IDS, BaseSearchState
from atlas.red_team.random_search import (
    CandidateResult,
    RandomSearchResult,
    random_search,
)

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
# Budget contract
# ---------------------------------------------------------------------------


def test_random_search_queries_used_equals_budget_sum(base_state, trained):
    bundle, policy = trained
    budgets = {fam: 5 for fam in ALLOWED_FAMILY_IDS}
    expected = sum(budgets.values())
    result = random_search(
        rng=random.Random(0), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy,
    )
    assert result.queries_used == expected
    assert len(result.candidates) == expected


def test_random_search_zero_budget(base_state, trained):
    bundle, policy = trained
    result = random_search(
        rng=random.Random(0), base_state=base_state,
        family_budgets={"low_velocity_high_graph_risk": 0},
        bundle=bundle, policy_config=policy,
    )
    assert result.queries_used == 0
    assert result.candidates == ()


def test_random_search_empty_budgets(base_state, trained):
    bundle, policy = trained
    result = random_search(
        rng=random.Random(0), base_state=base_state,
        family_budgets={}, bundle=bundle, policy_config=policy,
    )
    assert result.queries_used == 0


def test_random_search_empty_base_raises(trained):
    bundle, policy = trained
    empty = BaseSearchState.from_lists(
        customers=[], accounts=[], devices=[], recipients=[],
        graph_edges=[], login_sessions=[], security_events=[],
        transfer_events=[],
    )
    with pytest.raises(ValueError, match="no transfer_events"):
        random_search(
            rng=random.Random(0), base_state=empty,
            family_budgets={"low_velocity_high_graph_risk": 1},
            bundle=bundle, policy_config=policy,
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_random_search_byte_identical_under_repeat(base_state, trained):
    bundle, policy = trained
    budgets = {fam: 5 for fam in ALLOWED_FAMILY_IDS}
    a = random_search(rng=random.Random(42), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    b = random_search(rng=random.Random(42), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    assert a.candidates == b.candidates
    assert a.queries_used == b.queries_used


def test_random_search_different_seed_differs(base_state, trained):
    bundle, policy = trained
    budgets = {fam: 5 for fam in ALLOWED_FAMILY_IDS}
    a = random_search(rng=random.Random(1), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    b = random_search(rng=random.Random(2), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    assert a.candidates != b.candidates


def test_family_iteration_is_sorted(base_state, trained):
    """Different input dict orderings must produce identical output —
    walks families in sorted order for byte-stability."""
    bundle, policy = trained
    fams_a = list(ALLOWED_FAMILY_IDS)
    fams_b = list(reversed(ALLOWED_FAMILY_IDS))
    a = random_search(rng=random.Random(0), base_state=base_state,
        family_budgets={f: 3 for f in fams_a}, bundle=bundle, policy_config=policy)
    b = random_search(rng=random.Random(0), base_state=base_state,
        family_budgets={f: 3 for f in fams_b}, bundle=bundle, policy_config=policy)
    assert a.candidates == b.candidates


# ---------------------------------------------------------------------------
# CandidateResult shape
# ---------------------------------------------------------------------------


def test_candidate_result_fields(base_state, trained):
    bundle, policy = trained
    result = random_search(rng=random.Random(0), base_state=base_state,
        family_budgets={"low_velocity_high_graph_risk": 1},
        bundle=bundle, policy_config=policy)
    c = result.candidates[0]
    assert isinstance(c, CandidateResult)
    assert c.candidate_id.startswith("cand_")
    assert c.target_event_id.startswith("tx_")
    assert 0.0 <= c.score <= 1.0
    assert c.decision_action in {"accept", "challenge", "alert", "decline"}
    assert c.synthetic_truth_label in {"normal_activity", "high_risk_synthetic_activity"}
    assert c.amount_bucket.startswith("amount_bucket_")


# ---------------------------------------------------------------------------
# Aggregate properties
# ---------------------------------------------------------------------------


def test_model_miss_rate_is_complement_of_recall(base_state, trained):
    """Per-family invariant: accepted_high_risk / valid_high_risk."""
    bundle, policy = trained
    result = random_search(rng=random.Random(0), base_state=base_state,
        family_budgets={"low_velocity_high_graph_risk": 30},
        bundle=bundle, policy_config=policy)
    valid = result.valid_high_risk_events_tested
    accepted = result.accepted_high_risk_events
    if valid > 0:
        assert result.model_miss_rate == accepted / valid
    else:
        assert result.model_miss_rate == 0.0


def test_per_family_counts_dict_shape(base_state, trained):
    bundle, policy = trained
    result = random_search(rng=random.Random(0), base_state=base_state,
        family_budgets={"low_velocity_high_graph_risk": 5, "score_boundary_cluster": 5},
        bundle=bundle, policy_config=policy)
    counts = result.per_family_counts()
    assert set(counts) == {"low_velocity_high_graph_risk", "score_boundary_cluster"}
    for fam, c in counts.items():
        assert set(c) == {"valid_high_risk", "accepted_high_risk"}
