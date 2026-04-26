"""Phase 4 decision-policy + reason-code tests."""
from __future__ import annotations

import pytest

from atlas.model.policy import (
    DECISION_ACTIONS,
    apply_decision_policy,
    load_decision_policy_config,
)


def _base_fv(**overrides):
    fv = {
        "event_id": "tx_000001", "customer_id": "cust_000001",
        "login_count_72h": 0, "login_count_30d": 0, "login_velocity_ratio": 0.0,
        "challenge_count_72h": 0, "challenge_pass_ratio_30d": 0.0,
        "password_recovery_count_72h": 0,
        "device_count_72h": 1, "current_device_tenure_days": 500,
        "geo_consistency_flag": 1, "transfer_count_72h": 0,
        "recipient_tenure_days": 500,
        "shared_device_degree": 0, "shared_recipient_degree": 0,
        "entity_graph_risk_score": 0.0, "cash_movement_velocity_score": 0.0,
    }
    fv.update(overrides)
    return fv


@pytest.fixture(scope="module")
def config():
    return load_decision_policy_config()


@pytest.mark.parametrize(
    "score,action",
    [
        (0.0, "accept"),
        (0.5, "accept"),
        (0.73999, "accept"),
        (0.74, "challenge"),
        (0.85999, "challenge"),
        (0.86, "alert"),
        (0.91999, "alert"),
        (0.92, "decline"),
        (1.0, "decline"),
    ],
)
def test_action_threshold_mapping(config, score, action):
    r = apply_decision_policy(score, _base_fv(), config)
    assert r.decision_action == action


@pytest.mark.parametrize("action", DECISION_ACTIONS)
def test_decision_band_matches_config(config, action):
    score = {"accept": 0.1, "challenge": 0.75, "alert": 0.87, "decline": 0.95}[action]
    r = apply_decision_policy(score, _base_fv(), config)
    assert r.decision_band == config.decision_bands[action]


def test_no_review_action(config):
    """Phase 4 has 4 actions only — no `review`."""
    for score in (0.0, 0.5, 0.85, 0.95, 1.0):
        r = apply_decision_policy(score, _base_fv(), config)
        assert r.decision_action != "review"
        assert r.decision_action in DECISION_ACTIONS


def test_reason_codes_subset_of_allowlist(config):
    """No reason code outside the configured allow-list."""
    fv = _base_fv(
        device_count_72h=3, entity_graph_risk_score=0.9, current_device_tenure_days=2,
        password_recovery_count_72h=1, cash_movement_velocity_score=0.85,
        recipient_tenure_days=1, geo_consistency_flag=0,
        shared_device_degree=10, shared_recipient_degree=10,
    )
    r = apply_decision_policy(0.74, fv, config)
    assert set(r.reason_codes).issubset(set(config.allowed_reason_codes))


def test_reason_codes_in_config_order(config):
    fv = _base_fv(
        device_count_72h=3, entity_graph_risk_score=0.9, current_device_tenure_days=2,
        password_recovery_count_72h=1, geo_consistency_flag=0,
    )
    r = apply_decision_policy(0.5, fv, config)
    indices = [config.allowed_reason_codes.index(rc) for rc in r.reason_codes]
    assert indices == sorted(indices)


def test_reason_codes_empty_on_baseline(config):
    """Clean low-risk vector with no triggers fires no reason codes."""
    r = apply_decision_policy(0.10, _base_fv(), config)
    assert r.reason_codes == ()


def test_individual_reason_code_triggers(config):
    cases = [
        ("recent_activity_change", {"device_count_72h": 2}),
        ("entity_graph_risk", {"entity_graph_risk_score": 0.7}),
        ("device_novelty", {"current_device_tenure_days": 7}),
        ("security_recovery_recent", {"password_recovery_count_72h": 1}),
        ("cash_movement_velocity_high", {"cash_movement_velocity_score": 0.7}),
        ("new_recipient_low_tenure", {"recipient_tenure_days": 7}),
        ("region_change_recent", {"geo_consistency_flag": 0}),
        ("shared_device_high_degree", {"shared_device_degree": 5}),
        ("shared_recipient_high_degree", {"shared_recipient_degree": 5}),
    ]
    for code, override in cases:
        r = apply_decision_policy(0.10, _base_fv(**override), config)
        assert code in r.reason_codes, f"override {override} should trigger {code}"


def test_score_validation(config):
    for bad in (-0.001, 1.001, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            apply_decision_policy(bad, _base_fv(), config)


def test_threshold_version_from_config(config):
    r = apply_decision_policy(0.5, _base_fv(), config)
    assert r.threshold_version == "thresholds_v1"


def test_determinism(config):
    fv = _base_fv(entity_graph_risk_score=0.8)
    r1 = apply_decision_policy(0.85, fv, config)
    r2 = apply_decision_policy(0.85, fv, config)
    assert r1 == r2
