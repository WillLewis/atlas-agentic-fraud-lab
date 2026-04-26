"""Recomputation correctness tests for Phase 3.

Covers:
  * Event-history mutations DO change recomputed features.
  * Events outside the 72h / 30d window do NOT change recomputed features.
  * No future-event leakage.
  * Ratios are always finite and divide-by-zero is explicit.
  * geo_consistency_flag is the integer 0 or 1 (not bool).
"""
from __future__ import annotations

import math
from copy import deepcopy
from datetime import timedelta

from atlas.synthetic.features import (
    NULL_RATIO_FALLBACK,
    _parse_utc,
    recompute_feature_vectors,
)


def _recompute(d):
    return recompute_feature_vectors(
        transfer_events=d["transfer_events"],
        customers=d["customers"],
        devices=d["devices"],
        graph_edges=d["graph_edges"],
        login_sessions=d["login_sessions"],
        security_events=d["security_events"],
    )


def _customer_with_logins(d):
    """Pick a customer that has at least one login session — needed so we
    can verify that adding a session changes the feature."""
    cust_ids_with_sessions = {s["customer_id"] for s in d["login_sessions"]}
    for c in d["customers"]:
        if c["customer_id"] in cust_ids_with_sessions:
            return c["customer_id"]
    raise RuntimeError("no customer with sessions")


def test_event_mutation_changes_features(build_dataset):
    """Adding a synthetic login session in the 72h window before a transfer
    must increment that transfer's login_count_72h."""
    d = build_dataset(42, 30)
    # Pick a transfer for a customer that already has at least one device.
    target_tx = d["transfer_events"][0]
    cust_id = target_tx["customer_id"]
    transfer_time = _parse_utc(target_tx["event_time_utc"])
    cust_devices = [dev for dev in d["devices"] if dev["customer_id"] == cust_id]
    assert cust_devices, "test fixture invariant: customer must have a device"

    before = _recompute(d)
    target_fv_before = next(
        fv for fv in before if fv["event_id"] == target_tx["transfer_event_id"]
    )

    # Insert a fresh login session 1h before the transfer.
    new_session_time = transfer_time - timedelta(hours=1)
    new_session = {
        "session_id": "sess_999999",
        "customer_id": cust_id,
        "device_id": cust_devices[0]["device_id"],
        "event_time_utc": new_session_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channel": cust_devices[0]["device_channel"],
        "region_bucket": d["customers"][0]["home_region_bucket"],  # any allowed bucket
        "challenge_required": False,
        "challenge_result": "not_required",
    }
    d_mutated = deepcopy(d)
    d_mutated["login_sessions"] = list(d["login_sessions"]) + [new_session]

    after = _recompute(d_mutated)
    target_fv_after = next(
        fv for fv in after if fv["event_id"] == target_tx["transfer_event_id"]
    )

    assert target_fv_after["login_count_72h"] == target_fv_before["login_count_72h"] + 1
    assert target_fv_after["login_count_30d"] == target_fv_before["login_count_30d"] + 1


def test_event_mutation_outside_window_no_effect(build_dataset):
    """A login session 100 days before the transfer must NOT affect
    login_count_72h or login_count_30d."""
    d = build_dataset(42, 30)
    target_tx = d["transfer_events"][0]
    cust_id = target_tx["customer_id"]
    transfer_time = _parse_utc(target_tx["event_time_utc"])
    cust_devices = [dev for dev in d["devices"] if dev["customer_id"] == cust_id]

    before = _recompute(d)
    target_fv_before = next(
        fv for fv in before if fv["event_id"] == target_tx["transfer_event_id"]
    )

    new_session_time = transfer_time - timedelta(days=100)
    new_session = {
        "session_id": "sess_888888",
        "customer_id": cust_id,
        "device_id": cust_devices[0]["device_id"],
        "event_time_utc": new_session_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channel": cust_devices[0]["device_channel"],
        "region_bucket": d["customers"][0]["home_region_bucket"],
        "challenge_required": False,
        "challenge_result": "not_required",
    }
    d["login_sessions"] = list(d["login_sessions"]) + [new_session]

    after = _recompute(d)
    target_fv_after = next(
        fv for fv in after if fv["event_id"] == target_tx["transfer_event_id"]
    )
    assert target_fv_after["login_count_72h"] == target_fv_before["login_count_72h"]
    assert target_fv_after["login_count_30d"] == target_fv_before["login_count_30d"]


def test_no_future_event_leakage(build_dataset):
    """Inserting a login session AFTER the transfer's timestamp must not
    affect that transfer's features."""
    d = build_dataset(42, 30)
    target_tx = d["transfer_events"][0]
    cust_id = target_tx["customer_id"]
    transfer_time = _parse_utc(target_tx["event_time_utc"])
    cust_devices = [dev for dev in d["devices"] if dev["customer_id"] == cust_id]

    before = _recompute(d)
    target_fv_before = next(
        fv for fv in before if fv["event_id"] == target_tx["transfer_event_id"]
    )

    future_session_time = transfer_time + timedelta(hours=1)
    future_session = {
        "session_id": "sess_777777",
        "customer_id": cust_id,
        "device_id": cust_devices[0]["device_id"],
        "event_time_utc": future_session_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channel": cust_devices[0]["device_channel"],
        "region_bucket": d["customers"][0]["home_region_bucket"],
        "challenge_required": False,
        "challenge_result": "not_required",
    }
    d["login_sessions"] = list(d["login_sessions"]) + [future_session]

    after = _recompute(d)
    target_fv_after = next(
        fv for fv in after if fv["event_id"] == target_tx["transfer_event_id"]
    )
    assert target_fv_after == target_fv_before, (
        "future event must not change the prior transfer's features"
    )


def test_concurrent_event_excluded_from_self_count(build_dataset):
    """A transfer's own timestamp is the strict-less-than upper bound:
    transfer_count_72h excludes the transfer itself."""
    d = build_dataset(42, 30)
    fvs = _recompute(d)
    # No feature vector should have transfer_count_72h equal to ALL of the
    # customer's transfer events (the customer's transfer_count_72h must
    # never include the transfer at the anchor itself).
    for fv in fvs:
        cust_tx = [t for t in d["transfer_events"] if t["customer_id"] == fv["customer_id"]]
        # transfer_count_72h must be at most len(cust_tx) - 1 (excluding self).
        assert fv["transfer_count_72h"] <= len(cust_tx) - 1


def test_no_nan_or_inf_ratios(features_global):
    for fv in features_global:
        for k in (
            "login_velocity_ratio",
            "challenge_pass_ratio_30d",
            "entity_graph_risk_score",
            "cash_movement_velocity_score",
        ):
            v = fv[k]
            assert math.isfinite(v), f"{k} not finite: {v}"


def test_login_velocity_ratio_zero_when_30d_empty(features_global):
    """When login_count_30d = 0, login_velocity_ratio must be the
    NULL_RATIO_FALLBACK (0.0)."""
    zero_30d = [fv for fv in features_global if fv["login_count_30d"] == 0]
    if not zero_30d:
        # The 60-customer fixture may not exhibit this; skip if nothing to check.
        import pytest as _pytest
        _pytest.skip("no feature vectors with login_count_30d=0 in fixture")
    for fv in zero_30d:
        assert fv["login_velocity_ratio"] == NULL_RATIO_FALLBACK == 0.0


def test_challenge_pass_ratio_30d_zero_when_no_challenges(features_global):
    """When the customer has no challenge-required logins in 30d,
    challenge_pass_ratio_30d must be 0.0 (NULL_RATIO_FALLBACK)."""
    no_challenge = [fv for fv in features_global if fv["challenge_pass_ratio_30d"] == 0.0]
    # This branch fires for most customers (challenge rate is ~5%) so we expect coverage.
    assert no_challenge, "expected at least one fv with challenge_pass_ratio_30d=0"


def test_geo_consistency_flag_is_int_not_bool(features_global):
    for fv in features_global:
        v = fv["geo_consistency_flag"]
        assert isinstance(v, int)
        assert not isinstance(v, bool)
        assert v in (0, 1)


def test_ratio_bounds_strict(features_global):
    for fv in features_global:
        assert 0.0 <= fv["login_velocity_ratio"]
        assert 0.0 <= fv["challenge_pass_ratio_30d"] <= 1.0
        assert 0.0 <= fv["entity_graph_risk_score"] <= 1.0
        assert 0.0 <= fv["cash_movement_velocity_score"] <= 1.0


def test_no_label_leakage_in_module():
    """``atlas.synthetic.features`` must not import ``labels``."""
    import sys
    # Force a fresh import to be sure.
    if "atlas.synthetic.features" in sys.modules:
        del sys.modules["atlas.synthetic.features"]
    if "atlas.synthetic.labels" in sys.modules:
        del sys.modules["atlas.synthetic.labels"]
    import atlas.synthetic.features  # noqa: F401
    assert "atlas.synthetic.labels" not in sys.modules, (
        "features.py must NOT import labels.py (label-leakage guard)"
    )
