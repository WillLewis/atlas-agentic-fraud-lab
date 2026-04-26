"""Field-shape conformance tests for Phase 3 feature vectors.

Asserts that every emitted record has exactly the canonical 17-field
``FeatureVector`` shape from ``project_atlas_openapi.yaml`` and
``project_atlas_sample_data.json``, with the right types and ID prefixes.
"""
from __future__ import annotations

from atlas.synthetic.features import FEATURE_VECTOR_KEYS


def test_feature_vector_keys_complete(features_global):
    for i, fv in enumerate(features_global):
        actual = set(fv.keys())
        assert actual == FEATURE_VECTOR_KEYS, (
            f"feature_vector[{i}] field-set mismatch:\n"
            f"  missing: {sorted(FEATURE_VECTOR_KEYS - actual)}\n"
            f"  extra  : {sorted(actual - FEATURE_VECTOR_KEYS)}"
        )


def test_feature_vector_id_prefixes(features_global):
    for fv in features_global:
        assert fv["event_id"].startswith("tx_")
        assert fv["customer_id"].startswith("cust_")


def test_string_fields(features_global):
    for fv in features_global:
        assert isinstance(fv["event_id"], str)
        assert isinstance(fv["customer_id"], str)


def test_integer_count_fields(features_global):
    int_fields = (
        "login_count_72h",
        "login_count_30d",
        "challenge_count_72h",
        "password_recovery_count_72h",
        "device_count_72h",
        "current_device_tenure_days",
        "geo_consistency_flag",
        "transfer_count_72h",
        "recipient_tenure_days",
        "shared_device_degree",
        "shared_recipient_degree",
    )
    for fv in features_global:
        for k in int_fields:
            v = fv[k]
            assert isinstance(v, int) and not isinstance(v, bool), (
                f"{k} expected int, got {type(v).__name__}: {v!r}"
            )
            assert v >= 0, f"{k} must be >= 0: {v}"


def test_float_ratio_fields(features_global):
    float_fields = (
        "login_velocity_ratio",
        "challenge_pass_ratio_30d",
        "entity_graph_risk_score",
        "cash_movement_velocity_score",
    )
    for fv in features_global:
        for k in float_fields:
            v = fv[k]
            assert isinstance(v, float), (
                f"{k} expected float, got {type(v).__name__}: {v!r}"
            )


def test_features_match_transfer_events_1to1(features_global, dataset):
    assert len(features_global) == len(dataset["transfer_events"])


def test_feature_event_ids_match_transfer_event_ids(features_global, dataset):
    feature_event_ids = {fv["event_id"] for fv in features_global}
    transfer_event_ids = {t["transfer_event_id"] for t in dataset["transfer_events"]}
    assert feature_event_ids == transfer_event_ids


def test_feature_customer_ids_resolve(features_global, dataset):
    cust_ids = {c["customer_id"] for c in dataset["customers"]}
    for fv in features_global:
        assert fv["customer_id"] in cust_ids
