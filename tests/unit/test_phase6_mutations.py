"""Phase 6 candidate mutation tests.

Verify the mutation primitives are pure (don't mutate input lists),
deterministic, public-safe in the IDs they emit, and route every
candidate through ``recompute_feature_vectors`` (no direct feature edits)
+ ``score_features`` without label leakage.
"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from atlas.red_team.mutations import (
    ALLOWED_FAMILY_IDS,
    BaseSearchState,
    apply_candidate_mutation,
    make_candidate_id,
    recompute_for_candidate,
    regenerate_labels_for_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def base_state() -> BaseSearchState:
    return BaseSearchState.from_dataset_dir(REPO_ROOT / "data" / "synthetic")


@pytest.fixture(scope="module")
def first_target_event_id(base_state: BaseSearchState) -> str:
    return base_state.transfer_events[0]["transfer_event_id"]


# ---------------------------------------------------------------------------
# ALLOWED_FAMILY_IDS / make_candidate_id
# ---------------------------------------------------------------------------


def test_allowed_family_ids_match_canonical_seven():
    assert set(ALLOWED_FAMILY_IDS) == {
        "low_velocity_high_graph_risk",
        "recent_change_feature_delay",
        "score_boundary_cluster",
        "activity_channel_shift",
        "current_device_mismatch",
        "label_noise_mislearned",
        "overfit_fix_failure",
    }


def test_make_candidate_id_deterministic():
    a = make_candidate_id("tx_000001", "low_velocity_high_graph_risk", 7)
    b = make_candidate_id("tx_000001", "low_velocity_high_graph_risk", 7)
    assert a == b


def test_make_candidate_id_uses_safe_prefix():
    cid = make_candidate_id("tx_000001", "low_velocity_high_graph_risk", 1)
    assert cid.startswith("cand_")
    # 8 hex chars after prefix → safe against PII-shape patterns
    assert len(cid) == len("cand_") + 8


def test_different_seed_yields_different_id():
    a = make_candidate_id("tx_000001", "low_velocity_high_graph_risk", 1)
    b = make_candidate_id("tx_000001", "low_velocity_high_graph_risk", 2)
    assert a != b


# ---------------------------------------------------------------------------
# apply_candidate_mutation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("family", list(ALLOWED_FAMILY_IDS))
def test_apply_candidate_mutation_works_for_every_family(
    base_state: BaseSearchState, first_target_event_id: str, family: str
):
    state = apply_candidate_mutation(
        random.Random(42),
        base_state,
        first_target_event_id,
        family,
        mutation_seed=1,
    )
    assert state.candidate_id.startswith("cand_")
    assert state.family_id == family
    assert state.target_event_id == first_target_event_id


def test_apply_candidate_mutation_does_not_modify_base(
    base_state: BaseSearchState, first_target_event_id: str
):
    """Mutators return new lists; the base must be untouched."""
    n_devices_before = len(base_state.devices)
    n_sessions_before = len(base_state.login_sessions)
    n_security_before = len(base_state.security_events)
    n_edges_before = len(base_state.graph_edges)

    state = apply_candidate_mutation(
        random.Random(42),
        base_state,
        first_target_event_id,
        "low_velocity_high_graph_risk",
        mutation_seed=1,
    )
    # Mutation must produce DIFFERENT lists than the base
    assert state.devices is not base_state.devices
    assert state.graph_edges is not base_state.graph_edges
    # Base is unchanged
    assert len(base_state.devices) == n_devices_before
    assert len(base_state.login_sessions) == n_sessions_before
    assert len(base_state.security_events) == n_security_before
    assert len(base_state.graph_edges) == n_edges_before


def test_unknown_family_id_raises(base_state, first_target_event_id):
    with pytest.raises(ValueError, match="unknown family_id"):
        apply_candidate_mutation(
            random.Random(0),
            base_state,
            first_target_event_id,
            "no_such_family",
            mutation_seed=0,
        )


def test_unknown_target_event_id_raises(base_state):
    with pytest.raises(ValueError, match="not found"):
        apply_candidate_mutation(
            random.Random(0),
            base_state,
            "tx_does_not_exist",
            "low_velocity_high_graph_risk",
            mutation_seed=0,
        )


def test_apply_candidate_mutation_deterministic(
    base_state: BaseSearchState, first_target_event_id: str
):
    s1 = apply_candidate_mutation(
        random.Random(42), base_state, first_target_event_id,
        "low_velocity_high_graph_risk", mutation_seed=7,
    )
    s2 = apply_candidate_mutation(
        random.Random(42), base_state, first_target_event_id,
        "low_velocity_high_graph_risk", mutation_seed=7,
    )
    assert s1 == s2


# ---------------------------------------------------------------------------
# Recompute path: the search MUST go through recompute_feature_vectors
# (no direct feature mutation).
# ---------------------------------------------------------------------------


def test_recompute_for_candidate_calls_recompute_feature_vectors(
    base_state: BaseSearchState, first_target_event_id: str
):
    """Bible §6.1 + Phase 6 invariant: every candidate's feature vector
    is derived via recompute_feature_vectors, never hand-edited."""
    state = apply_candidate_mutation(
        random.Random(0), base_state, first_target_event_id,
        "low_velocity_high_graph_risk", mutation_seed=1,
    )
    # Patch the recompute function and assert it's called exactly once.
    import atlas.red_team.mutations as mut_mod
    with mock.patch.object(
        mut_mod, "recompute_feature_vectors", wraps=mut_mod.recompute_feature_vectors
    ) as wrapped:
        recompute_for_candidate(state)
        assert wrapped.call_count == 1


def test_recompute_for_candidate_returns_unique_feature_vector(
    base_state: BaseSearchState, first_target_event_id: str
):
    fv = recompute_for_candidate(
        apply_candidate_mutation(
            random.Random(0), base_state, first_target_event_id,
            "low_velocity_high_graph_risk", mutation_seed=1,
        )
    )
    # Must be a real FeatureVector dict with the 17 keys
    expected_keys = {
        "event_id", "customer_id",
        "login_count_72h", "login_count_30d", "login_velocity_ratio",
        "challenge_count_72h", "challenge_pass_ratio_30d",
        "password_recovery_count_72h",
        "device_count_72h", "current_device_tenure_days",
        "geo_consistency_flag", "transfer_count_72h",
        "recipient_tenure_days",
        "shared_device_degree", "shared_recipient_degree",
        "entity_graph_risk_score", "cash_movement_velocity_score",
    }
    assert set(fv) == expected_keys


# ---------------------------------------------------------------------------
# Label regeneration: used for validation only — never feeds the scorer.
# ---------------------------------------------------------------------------


def test_regenerate_labels_returns_valid_label(
    base_state: BaseSearchState, first_target_event_id: str
):
    state = apply_candidate_mutation(
        random.Random(0), base_state, first_target_event_id,
        "low_velocity_high_graph_risk", mutation_seed=1,
    )
    label = regenerate_labels_for_candidate(random.Random(0), state)
    assert label["synthetic_truth_label"] in {
        "normal_activity", "high_risk_synthetic_activity"
    }


# ---------------------------------------------------------------------------
# No-label-leakage: score_features payloads must NOT contain labels.
# ---------------------------------------------------------------------------


def test_score_features_payload_excludes_label(
    base_state: BaseSearchState, first_target_event_id: str, trained_baseline_dir
):
    """Phase 4 invariant carried into Phase 6: the scorer only sees the
    FeatureVector. No synthetic_truth_label, no binary_label."""
    from atlas.model.scorer import load_baseline_bundle
    from atlas.model.policy import load_decision_policy_config
    from atlas.red_team.random_search import random_search

    bundle = load_baseline_bundle(trained_baseline_dir)
    policy = load_decision_policy_config()

    seen_payloads: list[dict] = []
    import atlas.red_team.random_search as rs_mod

    real_fn = rs_mod.score_features

    def _wrap(fv, b):
        seen_payloads.append(dict(fv))
        return real_fn(fv, b)

    with mock.patch.object(rs_mod, "score_features", side_effect=_wrap):
        random_search(
            rng=random.Random(0), base_state=base_state,
            family_budgets={"low_velocity_high_graph_risk": 5},
            bundle=bundle, policy_config=policy,
        )

    assert seen_payloads, "score_features was never called"
    for payload in seen_payloads:
        assert "synthetic_truth_label" not in payload
        assert "binary_label" not in payload
