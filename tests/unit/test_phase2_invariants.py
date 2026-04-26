"""Safety / leakage / id-prefix invariants for Phase 2.

These tests close the gap left by ``config/safety.yaml`` ignoring
``data/synthetic/**``: the safety scanner doesn't lint generated
records, so unit tests assert the same invariants directly.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Allowed synthetic ID prefixes (mirrors config/safety.yaml synthetic_id_prefixes
# subset that Phase 2 actually generates)
# ---------------------------------------------------------------------------

ALLOWED_RECORD_PREFIXES = {
    "customer_id": "cust_",
    "account_id": "acct_",
    "device_id": "dev_",
    "recipient_id": "recip_",
    "external_account_id": "extacct_",
    "edge_id": "edge_",
    "session_id": "sess_",
    "security_event_id": "sec_",
    "transfer_event_id": "tx_",
}

# Cross-reference fields (id of another entity referenced inside a record)
ALLOWED_REFERENCE_PREFIXES = {
    "customer_id": "cust_",
    "device_id": "dev_",
    "account_id": "acct_",
    "recipient_id": "recip_",
    "session_id": "sess_",
    "source_node_id": ("cust_",),  # Phase 2 graph edges always source = customer
    "target_node_id": ("dev_", "recip_"),
}

# Real institution / payment processor names (mirrors safety.yaml
# real_institution_names rule). If any of these appear in any string field,
# the test fails.
REAL_INSTITUTION_RE = re.compile(
    r"\b(jpmorgan|jp morgan|chase|citibank|citigroup|wells fargo|bank of america|"
    r"bofa|hsbc|barclays|santander|deutsche bank|goldman sachs|morgan stanley|"
    r"capital one|td bank|us bank|pnc|usaa|ally bank|truist|fifth third|"
    r"key bank|m&t bank|visa|mastercard|american express|amex|discover|"
    r"paypal|venmo|zelle|cash app|stripe|square)\b",
    re.IGNORECASE,
)

# PII shape regexes (mirrors safety.yaml pii_shaped_strings rule).
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CC_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
PHONE_RE = re.compile(
    r"\+\d{1,3}[-. ]?\(?\d{2,4}\)?[-. ]?\d{3,4}[-. ]?\d{3,4}\b"
)


# ---------------------------------------------------------------------------
# ID-prefix invariants
# ---------------------------------------------------------------------------


def _check_record_prefix(record: dict, key: str, prefix: str | tuple[str, ...]) -> None:
    if key not in record:
        return
    value = record[key]
    if isinstance(prefix, tuple):
        assert any(value.startswith(p) for p in prefix), (
            f"{key}={value!r} does not start with any of {prefix}"
        )
    else:
        assert value.startswith(prefix), f"{key}={value!r} does not start with {prefix!r}"


def test_all_primary_ids_use_synthetic_prefixes(dataset):
    """Every record's primary ID uses the configured synthetic prefix."""
    for c in dataset["customers"]:
        _check_record_prefix(c, "customer_id", "cust_")
    for a in dataset["accounts"]:
        _check_record_prefix(a, "account_id", "acct_")
    for d in dataset["devices"]:
        _check_record_prefix(d, "device_id", "dev_")
    for r in dataset["recipients"]:
        _check_record_prefix(r, "recipient_id", "recip_")
    for e in dataset["external_accounts"]:
        _check_record_prefix(e, "external_account_id", "extacct_")
    for g in dataset["graph_edges"]:
        _check_record_prefix(g, "edge_id", "edge_")
    for s in dataset["login_sessions"]:
        _check_record_prefix(s, "session_id", "sess_")
    for s in dataset["security_events"]:
        _check_record_prefix(s, "security_event_id", "sec_")
    for t in dataset["transfer_events"]:
        _check_record_prefix(t, "transfer_event_id", "tx_")


def test_all_cross_references_use_synthetic_prefixes(dataset):
    """Records' cross-reference fields point at synthetic IDs."""
    for a in dataset["accounts"]:
        _check_record_prefix(a, "customer_id", "cust_")
    for d in dataset["devices"]:
        _check_record_prefix(d, "customer_id", "cust_")
    for e in dataset["external_accounts"]:
        _check_record_prefix(e, "customer_id", "cust_")
    for g in dataset["graph_edges"]:
        _check_record_prefix(g, "source_node_id", "cust_")
        _check_record_prefix(g, "target_node_id", ("dev_", "recip_"))
    for s in dataset["login_sessions"]:
        _check_record_prefix(s, "customer_id", "cust_")
        _check_record_prefix(s, "device_id", "dev_")
    for s in dataset["security_events"]:
        _check_record_prefix(s, "customer_id", "cust_")
        _check_record_prefix(s, "session_id", "sess_")
        _check_record_prefix(s, "device_id", "dev_")
    for t in dataset["transfer_events"]:
        _check_record_prefix(t, "customer_id", "cust_")
        _check_record_prefix(t, "account_id", "acct_")
        _check_record_prefix(t, "recipient_id", "recip_")
    for l in dataset["label_records"]:
        _check_record_prefix(l, "event_id", "tx_")


# ---------------------------------------------------------------------------
# PII shape invariants
# ---------------------------------------------------------------------------


def _walk_strings(node: Any, path: str = ""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")


def test_no_pii_shaped_strings(dataset):
    for table_name in (
        "customers",
        "accounts",
        "devices",
        "recipients",
        "external_accounts",
        "graph_edges",
        "login_sessions",
        "security_events",
        "transfer_events",
        "label_records",
    ):
        records = dataset[table_name]
        for i, rec in enumerate(records):
            for path, value in _walk_strings(rec, f"{table_name}[{i}]"):
                # Skip the timestamp field — its dash-separated date can
                # match overly permissive regexes; events.py rendering is
                # already pinned via _format_event_time_utc.
                if path.endswith(".event_time_utc"):
                    continue
                assert not SSN_RE.search(value), f"SSN-shape at {path}: {value!r}"
                assert not CC_RE.search(value), f"CC-shape at {path}: {value!r}"
                assert not PHONE_RE.search(value), f"phone-shape at {path}: {value!r}"


def test_no_real_institution_names_in_records(dataset):
    for table_name in (
        "customers",
        "accounts",
        "devices",
        "recipients",
        "external_accounts",
        "graph_edges",
        "login_sessions",
        "security_events",
        "transfer_events",
        "label_records",
    ):
        for i, rec in enumerate(dataset[table_name]):
            for path, value in _walk_strings(rec, f"{table_name}[{i}]"):
                m = REAL_INSTITUTION_RE.search(value)
                assert m is None, (
                    f"real institution name {m.group(0)!r} at {path}: {value!r}"
                )


# ---------------------------------------------------------------------------
# Customer-level split / leakage invariants
# ---------------------------------------------------------------------------


def test_no_customer_leak_across_partitions(dataset):
    splits = dataset["splits"]
    seen: dict[str, str] = {}
    for pname, partition in splits.partitions.items():
        for cid in partition.customer_ids:
            assert cid not in seen, (
                f"customer {cid!r} appears in both {seen[cid]!r} and {pname!r}"
            )
            seen[cid] = pname
    # Every customer must appear in exactly one partition
    assert len(seen) == dataset["customer_count"]


def test_all_customers_in_one_partition(dataset):
    splits = dataset["splits"]
    partition_ids = set()
    for partition in splits.partitions.values():
        partition_ids.update(partition.customer_ids)
    all_ids = {c["customer_id"] for c in dataset["customers"]}
    assert partition_ids == all_ids


def test_locked_holdout_records_isolated_from_other_partitions(dataset):
    splits = dataset["splits"]
    locked = splits.partitions["locked_adaptive_holdout"]
    locked_cust_ids = set(locked.customer_ids)

    for pname in ("train", "validation", "clean_holdout", "drifted_holdout"):
        other = splits.partitions[pname]
        other_cust_ids = set(other.customer_ids)
        assert not (locked_cust_ids & other_cust_ids), (
            f"locked customer leaked into {pname}"
        )


def test_drifted_holdout_records_isolated_from_other_partitions(dataset):
    splits = dataset["splits"]
    drifted = splits.partitions["drifted_holdout"]
    drifted_cust_ids = set(drifted.customer_ids)

    for pname in ("train", "validation", "clean_holdout", "locked_adaptive_holdout"):
        other = splits.partitions[pname]
        other_cust_ids = set(other.customer_ids)
        assert not (drifted_cust_ids & other_cust_ids), (
            f"drifted customer leaked into {pname}"
        )


# ---------------------------------------------------------------------------
# Drift application invariants
# ---------------------------------------------------------------------------


def test_drifted_partition_has_drift_applied_flag(dataset):
    splits = dataset["splits"]
    assert splits.partitions["drifted_holdout"].drift_applied is True
    for pname in ("train", "validation", "clean_holdout", "locked_adaptive_holdout"):
        assert splits.partitions[pname].drift_applied is False


def test_drifted_labels_match_drifted_transfers(dataset):
    """Each drifted label record references a drifted transfer event 1:1."""
    splits = dataset["splits"]
    drifted = splits.partitions["drifted_holdout"]
    tx_ids = {t["transfer_event_id"] for t in drifted.transfer_events}
    label_ids = {l["event_id"] for l in drifted.label_records}
    assert tx_ids == label_ids


# ---------------------------------------------------------------------------
# Label-class invariants
# ---------------------------------------------------------------------------


def test_all_synthetic_truth_labels_in_allow_list(dataset):
    allowed = {"normal_activity", "high_risk_synthetic_activity"}
    for t in dataset["transfer_events"]:
        assert t["synthetic_truth_label"] in allowed
    for l in dataset["label_records"]:
        assert l["synthetic_truth_label"] in allowed
