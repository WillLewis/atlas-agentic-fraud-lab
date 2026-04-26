"""Field-shape conformance tests for Phase 2.

Asserts that every generated record has exactly the fixture-canonical
field set. Mirrors ``project_atlas_sample_data.json`` and the
architecture doc §2.1 entity table (which were canonical inputs to the
component-1 schema realignment).
"""
from __future__ import annotations

EXPECTED_CUSTOMER_KEYS = frozenset(
    {
        "customer_id",
        "customer_segment",
        "home_region_bucket",
        "account_age_days",
        "normal_login_frequency_30d",
        "normal_transfer_frequency_30d",
        "synthetic_base_risk",
        "created_from_seed",
    }
)

EXPECTED_ACCOUNT_KEYS = frozenset(
    {
        "account_id",
        "customer_id",
        "account_type",
        "opened_days_ago",
        "available_balance_bucket",
        "account_status",
    }
)

EXPECTED_DEVICE_KEYS = frozenset(
    {
        "device_id",
        "customer_id",
        "device_channel",
        "first_seen_days_ago",
        "login_count_30d",
        "is_current_event_device",
    }
)

EXPECTED_RECIPIENT_KEYS = frozenset(
    {
        "recipient_id",
        "first_seen_days_ago",
        "recipient_reuse_degree",
        "recipient_risk_bucket",
    }
)

EXPECTED_EXTERNAL_ACCOUNT_KEYS = frozenset(
    {
        "external_account_id",
        "customer_id",
        "linked_days_ago",
        "verification_method",
        "external_account_risk_bucket",
    }
)

EXPECTED_GRAPH_EDGE_KEYS = frozenset(
    {
        "edge_id",
        "source_node_id",
        "source_node_type",
        "target_node_id",
        "target_node_type",
        "relationship_type",
        "first_seen_days_ago",
        "event_count",
    }
)

EXPECTED_LOGIN_SESSION_KEYS = frozenset(
    {
        "session_id",
        "customer_id",
        "device_id",
        "event_time_utc",
        "channel",
        "region_bucket",
        "challenge_required",
        "challenge_result",
    }
)

EXPECTED_SECURITY_EVENT_KEYS = frozenset(
    {
        "security_event_id",
        "customer_id",
        "session_id",
        "event_type",
        "event_time_utc",
        "device_id",
        "safe_risk_marker",
    }
)

EXPECTED_TRANSFER_EVENT_KEYS = frozenset(
    {
        "transfer_event_id",
        "customer_id",
        "account_id",
        "event_type",
        "event_time_utc",
        "amount_bucket",
        "recipient_id",
        "channel",
        "synthetic_truth_label",
    }
)

EXPECTED_LABEL_RECORD_KEYS = frozenset(
    {
        "event_id",
        "latent_drivers",
        "synthetic_risk_probability",
        "synthetic_truth_label",
    }
)

EXPECTED_LATENT_DRIVER_KEYS = frozenset(
    {
        "base_customer_risk",
        "account_access_change_marker",
        "device_novelty_marker",
        "security_recovery_marker",
        "cash_movement_velocity_marker",
        "entity_reuse_marker",
        "ring_membership_marker",
        "label_noise",
    }
)


def _check_keys(records, expected, label):
    for i, r in enumerate(records):
        actual = set(r.keys())
        assert actual == expected, (
            f"{label}[{i}] field-set mismatch:\n"
            f"  missing: {sorted(expected - actual)}\n"
            f"  extra  : {sorted(actual - expected)}"
        )


def test_customer_keys(dataset):
    _check_keys(dataset["customers"], EXPECTED_CUSTOMER_KEYS, "customer")


def test_account_keys(dataset):
    _check_keys(dataset["accounts"], EXPECTED_ACCOUNT_KEYS, "account")


def test_device_keys(dataset):
    _check_keys(dataset["devices"], EXPECTED_DEVICE_KEYS, "device")


def test_recipient_keys(dataset):
    _check_keys(dataset["recipients"], EXPECTED_RECIPIENT_KEYS, "recipient")


def test_external_account_keys(dataset):
    _check_keys(
        dataset["external_accounts"],
        EXPECTED_EXTERNAL_ACCOUNT_KEYS,
        "external_account",
    )


def test_graph_edge_keys(dataset):
    _check_keys(dataset["graph_edges"], EXPECTED_GRAPH_EDGE_KEYS, "graph_edge")


def test_login_session_keys(dataset):
    _check_keys(
        dataset["login_sessions"], EXPECTED_LOGIN_SESSION_KEYS, "login_session"
    )


def test_security_event_keys(dataset):
    _check_keys(
        dataset["security_events"], EXPECTED_SECURITY_EVENT_KEYS, "security_event"
    )


def test_transfer_event_keys(dataset):
    _check_keys(
        dataset["transfer_events"], EXPECTED_TRANSFER_EVENT_KEYS, "transfer_event"
    )


def test_label_record_keys(dataset):
    _check_keys(dataset["label_records"], EXPECTED_LABEL_RECORD_KEYS, "label_record")


def test_latent_driver_keys(dataset):
    for i, l in enumerate(dataset["label_records"]):
        actual = set(l["latent_drivers"].keys())
        assert actual == EXPECTED_LATENT_DRIVER_KEYS, (
            f"label_record[{i}].latent_drivers field-set mismatch:\n"
            f"  missing: {sorted(EXPECTED_LATENT_DRIVER_KEYS - actual)}\n"
            f"  extra  : {sorted(actual - EXPECTED_LATENT_DRIVER_KEYS)}"
        )


# ---------------------------------------------------------------------------
# Cross-record referential integrity
# ---------------------------------------------------------------------------


def test_account_customer_ids_resolve(dataset):
    cust_ids = {c["customer_id"] for c in dataset["customers"]}
    for a in dataset["accounts"]:
        assert a["customer_id"] in cust_ids


def test_device_customer_ids_resolve(dataset):
    cust_ids = {c["customer_id"] for c in dataset["customers"]}
    for d in dataset["devices"]:
        assert d["customer_id"] in cust_ids


def test_transfer_event_references_resolve(dataset):
    cust_ids = {c["customer_id"] for c in dataset["customers"]}
    acct_ids = {a["account_id"] for a in dataset["accounts"]}
    recip_ids = {r["recipient_id"] for r in dataset["recipients"]}
    for t in dataset["transfer_events"]:
        assert t["customer_id"] in cust_ids
        assert t["account_id"] in acct_ids
        assert t["recipient_id"] in recip_ids


def test_label_event_ids_match_transfer_event_ids(dataset):
    tx_ids = {t["transfer_event_id"] for t in dataset["transfer_events"]}
    label_event_ids = {l["event_id"] for l in dataset["label_records"]}
    assert label_event_ids == tx_ids


def test_security_event_session_ids_resolve(dataset):
    sess_ids = {s["session_id"] for s in dataset["login_sessions"]}
    for s in dataset["security_events"]:
        assert s["session_id"] in sess_ids
