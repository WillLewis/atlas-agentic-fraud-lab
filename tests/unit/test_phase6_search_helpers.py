"""Phase 6 allocator + graph_probe tests."""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from atlas.red_team.graph_probe import (
    GRAPH_RELEVANT_FAMILIES,
    _customer_degree,
    graph_probe,
)
from atlas.red_team.mutations import ALLOWED_FAMILY_IDS, BaseSearchState
from atlas.red_team.scoring_query_allocator import (
    SEARCH_METHODS,
    allocate_queries,
    per_method_budgets,
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
# allocate_queries — sum-equals-budget contract + edge cases
# ---------------------------------------------------------------------------


def test_allocator_sum_equals_budget_clean_split():
    alloc = allocate_queries(
        search_methods=list(SEARCH_METHODS),
        family_ids=list(ALLOWED_FAMILY_IDS),
        max_score_queries=210,  # 3 * 7 = 21 pairs, exact 10 each
    )
    assert sum(alloc.values()) == 210
    assert all(v == 10 for v in alloc.values())


def test_allocator_sum_equals_budget_with_remainder():
    """Distributes the remainder in deterministic round-robin."""
    alloc = allocate_queries(
        search_methods=list(SEARCH_METHODS),
        family_ids=list(ALLOWED_FAMILY_IDS),
        max_score_queries=215,  # remainder=5
    )
    assert sum(alloc.values()) == 215


def test_allocator_sum_equals_budget_tiny_budget_lt_n_pairs():
    alloc = allocate_queries(
        search_methods=["random", "evolutionary"],
        family_ids=["a", "b", "c"],
        max_score_queries=4,
    )
    assert sum(alloc.values()) == 4
    # Some pairs get 1, some get 0
    assert all(v in (0, 1) for v in alloc.values())


def test_allocator_per_pair_non_negative():
    alloc = allocate_queries(
        search_methods=list(SEARCH_METHODS),
        family_ids=list(ALLOWED_FAMILY_IDS),
        max_score_queries=215,
    )
    assert all(v >= 0 for v in alloc.values())


def test_allocator_zero_budget():
    alloc = allocate_queries(
        search_methods=["random"], family_ids=["a", "b"], max_score_queries=0,
    )
    assert sum(alloc.values()) == 0


def test_allocator_deterministic():
    a = allocate_queries(
        search_methods=list(SEARCH_METHODS),
        family_ids=list(ALLOWED_FAMILY_IDS),
        max_score_queries=215,
    )
    b = allocate_queries(
        search_methods=list(SEARCH_METHODS),
        family_ids=list(ALLOWED_FAMILY_IDS),
        max_score_queries=215,
    )
    assert a == b


def test_allocator_sorted_input_independence():
    """Reversed input order produces identical output."""
    a = allocate_queries(
        search_methods=list(SEARCH_METHODS),
        family_ids=list(ALLOWED_FAMILY_IDS),
        max_score_queries=215,
    )
    b = allocate_queries(
        search_methods=list(reversed(SEARCH_METHODS)),
        family_ids=list(reversed(ALLOWED_FAMILY_IDS)),
        max_score_queries=215,
    )
    assert a == b


# ---------------------------------------------------------------------------
# Allocator error paths
# ---------------------------------------------------------------------------


def test_allocator_rejects_negative_budget():
    with pytest.raises(ValueError, match=">= 0"):
        allocate_queries(
            search_methods=["random"], family_ids=["a"], max_score_queries=-1,
        )


def test_allocator_rejects_empty_methods():
    with pytest.raises(ValueError, match="at least one search_method"):
        allocate_queries(search_methods=[], family_ids=["a"], max_score_queries=10)


def test_allocator_rejects_empty_families():
    with pytest.raises(ValueError, match="at least one family_id"):
        allocate_queries(search_methods=["random"], family_ids=[], max_score_queries=10)


def test_allocator_rejects_unknown_method():
    with pytest.raises(ValueError, match="unknown search_method"):
        allocate_queries(
            search_methods=["unknown"], family_ids=["a"], max_score_queries=10,
        )


# ---------------------------------------------------------------------------
# per_method_budgets pivot
# ---------------------------------------------------------------------------


def test_per_method_budgets_pivot():
    alloc = {
        ("random", "a"): 5, ("random", "b"): 6,
        ("evolutionary", "a"): 7, ("evolutionary", "b"): 8,
    }
    pivot = per_method_budgets(alloc)
    assert pivot == {
        "random": {"a": 5, "b": 6},
        "evolutionary": {"a": 7, "b": 8},
    }


# ---------------------------------------------------------------------------
# graph_probe — graph-relevant family restriction
# ---------------------------------------------------------------------------


def test_graph_probe_silently_skips_non_graph_relevant_families(base_state, trained):
    bundle, policy = trained
    result = graph_probe(
        rng=random.Random(0), base_state=base_state,
        family_budgets={"activity_channel_shift": 10, "current_device_mismatch": 10},
        bundle=bundle, policy_config=policy,
    )
    assert result.queries_used == 0
    assert result.candidates == ()


def test_graph_probe_consumes_only_graph_relevant_families(base_state, trained):
    bundle, policy = trained
    result = graph_probe(
        rng=random.Random(0), base_state=base_state,
        family_budgets={fam: 10 for fam in ALLOWED_FAMILY_IDS},
        bundle=bundle, policy_config=policy,
    )
    # Two graph-relevant families, 10 each
    assert result.queries_used == 10 * len(GRAPH_RELEVANT_FAMILIES)


def test_graph_probe_candidates_are_graph_relevant_only(base_state, trained):
    bundle, policy = trained
    result = graph_probe(
        rng=random.Random(0), base_state=base_state,
        family_budgets={fam: 5 for fam in ALLOWED_FAMILY_IDS},
        bundle=bundle, policy_config=policy,
    )
    families_in_candidates = {c.family_id for c in result.candidates}
    assert families_in_candidates.issubset(GRAPH_RELEVANT_FAMILIES)


def test_graph_probe_byte_identical_under_repeat(base_state, trained):
    bundle, policy = trained
    budgets = {fam: 10 for fam in ALLOWED_FAMILY_IDS}
    a = graph_probe(rng=random.Random(0), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    b = graph_probe(rng=random.Random(0), base_state=base_state,
        family_budgets=budgets, bundle=bundle, policy_config=policy)
    assert a.candidates == b.candidates


def test_graph_probe_empty_base_raises(trained):
    bundle, policy = trained
    empty = BaseSearchState.from_lists(
        customers=[], accounts=[], devices=[], recipients=[],
        graph_edges=[], login_sessions=[], security_events=[],
        transfer_events=[],
    )
    with pytest.raises(ValueError, match="no transfer_events"):
        graph_probe(
            rng=random.Random(0), base_state=empty,
            family_budgets={"low_velocity_high_graph_risk": 1},
            bundle=bundle, policy_config=policy,
        )


def test_customer_degree_counts_both_directions(base_state):
    """Edges where the customer is on either source or target side count."""
    deg = _customer_degree(base_state.graph_edges)
    # Every customer that appears in graph_edges has positive degree
    for edge in base_state.graph_edges:
        if edge["source_node_type"] == "customer":
            assert deg[edge["source_node_id"]] >= 1
        if edge["target_node_type"] == "customer":
            assert deg[edge["target_node_id"]] >= 1
