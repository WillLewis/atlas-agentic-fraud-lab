"""Synthetic event generators (Phase 2).

Emits three event tables matching the fixture envelope:

  * ``LoginSession``  — one record per synthetic login. Total per device
                        equals the device's ``login_count_30d``.
  * ``SecurityEvent`` — sparse account-access / profile / challenge events
                        anchored to existing login sessions.
  * ``TransferEvent`` — one record per synthetic transfer attempt. Recipient
                        is drawn from the customer's ``attempted_transfer_to``
                        graph edges; channel is drawn from the customer's
                        device pool.

Reference instant
-----------------
``REFERENCE_NOW = 2026-06-01T12:00:00Z`` is the synthetic "now" for all
event timestamps. Phase 2 events fall in the 30 days preceding this instant
(security events go back 60 days). Same seed → same RNG draws → same
``event_time_utc`` strings → byte-identical JSON.

``synthetic_truth_label`` placeholder
-------------------------------------
Per the user's component-4 instruction, transfer events carry
``synthetic_truth_label="normal_activity"`` as a placeholder. Component 5
(``labels.py``) re-evaluates each transfer using latent drivers and
overwrites the label where the driver mix indicates high-risk synthetic
activity. This keeps the schema's required-fields contract intact while
deferring real label logic to Phase 2's label component.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Final, TypedDict

from atlas.synthetic.accounts import Account
from atlas.synthetic.customers import Customer, HOME_REGION_BUCKETS
from atlas.synthetic.devices import Device
from atlas.synthetic.graph import GraphEdge

# ---------------------------------------------------------------------------
# Reference instant — fixed across every Phase 2 run
# ---------------------------------------------------------------------------

REFERENCE_NOW: Final[datetime] = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Record shapes
# ---------------------------------------------------------------------------


class LoginSession(TypedDict):
    session_id: str
    customer_id: str
    device_id: str
    event_time_utc: str
    channel: str
    region_bucket: str
    challenge_required: bool
    challenge_result: str


class SecurityEvent(TypedDict):
    security_event_id: str
    customer_id: str
    session_id: str
    event_type: str
    event_time_utc: str
    device_id: str
    safe_risk_marker: str


class TransferEvent(TypedDict):
    transfer_event_id: str
    customer_id: str
    account_id: str
    event_type: str
    event_time_utc: str
    amount_bucket: str
    recipient_id: str
    channel: str
    synthetic_truth_label: str


# ---------------------------------------------------------------------------
# Bucketed enums and ID prefixes
# ---------------------------------------------------------------------------

LOGIN_SESSION_ID_PREFIX: Final[str] = "sess_"
SECURITY_EVENT_ID_PREFIX: Final[str] = "sec_"
TRANSFER_EVENT_ID_PREFIX: Final[str] = "tx_"

# Allowed event types — mirrors config/synthetic_schema.yaml `events.allowed_types`.
ALLOWED_EVENT_TYPES: Final[tuple[str, ...]] = (
    "login_success",
    "login_challenge_required",
    "challenge_passed",
    "challenge_failed",
    "password_recovery_completed",
    "username_recovery_completed",
    "profile_update",
    "recipient_added",
    "external_account_link_attempt",
    "instant_transfer_attempt",
    "external_transfer_attempt",
    "large_transfer_attempt",
)

CHALLENGE_RESULTS: Final[tuple[str, ...]] = ("not_required", "passed", "failed")

# Sparse security-event types eligible for per-customer drawn events.
_SPARSE_SECURITY_EVENT_TYPES: Final[tuple[str, ...]] = (
    "password_recovery_completed",
    "username_recovery_completed",
    "profile_update",
    "recipient_added",
    "login_challenge_required",
    "challenge_passed",
    "challenge_failed",
)

# Per-customer extra-security-event count distribution.
_SECURITY_EVENT_COUNT_CHOICES: Final[tuple[int, ...]] = (0, 1, 2, 3)
_SECURITY_EVENT_COUNT_WEIGHTS: Final[tuple[float, ...]] = (0.60, 0.30, 0.08, 0.02)

# Mapping from security-event type → safe_risk_marker. Public-safe markers
# only — no operational descriptions.
_SAFE_RISK_MARKERS: Final[dict[str, str]] = {
    "password_recovery_completed": "recent_account_access_change",
    "username_recovery_completed": "recent_account_access_change",
    "profile_update": "normal_customer_update",
    "recipient_added": "new_recipient_added",
    "external_account_link_attempt": "external_account_pending_review",
    "login_challenge_required": "challenge_outcome_recorded",
    "challenge_passed": "challenge_outcome_recorded",
    "challenge_failed": "challenge_outcome_recorded",
}

ALLOWED_SAFE_RISK_MARKERS: Final[tuple[str, ...]] = tuple(
    sorted(set(_SAFE_RISK_MARKERS.values()))
)

# Transfer event-type weights.
_TRANSFER_EVENT_TYPES: Final[tuple[str, ...]] = (
    "instant_transfer_attempt",
    "external_transfer_attempt",
    "large_transfer_attempt",
)
_TRANSFER_EVENT_WEIGHTS: Final[tuple[float, ...]] = (0.65, 0.25, 0.10)

# Ten safe amount buckets. Matches fixture (`amount_bucket_02`, `amount_bucket_05`).
AMOUNT_BUCKETS: Final[tuple[str, ...]] = tuple(
    f"amount_bucket_{i:02d}" for i in range(1, 11)
)

# Login challenge frequency. Most logins do not require a challenge.
_CHALLENGE_REQUIRED_RATE: Final[float] = 0.05
_CHALLENGE_PASS_RATE: Final[float] = 0.85

# Region-drift rate on a session: most logins are in customer's home region.
_REGION_DRIFT_RATE: Final[float] = 0.08

# Time-window constants (days). Login sessions span the 30 days before
# REFERENCE_NOW; security events span 60 days; transfer events span 30 days.
_LOGIN_WINDOW_DAYS: Final[int] = 30
_TRANSFER_WINDOW_DAYS: Final[int] = 30
_SECURITY_WINDOW_DAYS: Final[int] = 60

# ---------------------------------------------------------------------------
# Required-key sets for runtime shape validation
# ---------------------------------------------------------------------------

_LOGIN_SESSION_KEYS: Final[frozenset[str]] = frozenset(
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

_SECURITY_EVENT_KEYS: Final[frozenset[str]] = frozenset(
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

_TRANSFER_EVENT_KEYS: Final[frozenset[str]] = frozenset(
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

# ---------------------------------------------------------------------------
# Public ID helpers
# ---------------------------------------------------------------------------


def make_login_session_id(index: int) -> str:
    if index < 1:
        raise ValueError("login session index must be >= 1")
    return f"{LOGIN_SESSION_ID_PREFIX}{index:06d}"


def make_security_event_id(index: int) -> str:
    if index < 1:
        raise ValueError("security event index must be >= 1")
    return f"{SECURITY_EVENT_ID_PREFIX}{index:06d}"


def make_transfer_event_id(index: int) -> str:
    if index < 1:
        raise ValueError("transfer event index must be >= 1")
    return f"{TRANSFER_EVENT_ID_PREFIX}{index:06d}"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _format_event_time_utc(instant: datetime) -> str:
    """Render a UTC ``datetime`` as ``YYYY-MM-DDTHH:MM:SSZ`` (fixture style)."""
    return instant.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _draw_event_time(rng: random.Random, window_days: int) -> str:
    """Draw a random instant in ``[REFERENCE_NOW - window_days, REFERENCE_NOW)``.

    Truncated to whole seconds so JSON output is byte-stable across runs.
    """
    days_ago = rng.uniform(0.0, float(window_days))
    delta = timedelta(days=days_ago)
    instant = REFERENCE_NOW - delta
    return _format_event_time_utc(instant)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _assert_login_session_shape(record: LoginSession) -> None:
    keys = set(record.keys())
    if keys != _LOGIN_SESSION_KEYS:
        missing = _LOGIN_SESSION_KEYS - keys
        extra = keys - _LOGIN_SESSION_KEYS
        raise ValueError(
            f"login session shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["session_id"].startswith(LOGIN_SESSION_ID_PREFIX):
        raise ValueError(f"session_id missing synthetic prefix: {record['session_id']!r}")
    if not record["customer_id"].startswith("cust_"):
        raise ValueError(f"customer_id missing synthetic prefix: {record['customer_id']!r}")
    if not record["device_id"].startswith("dev_"):
        raise ValueError(f"device_id missing synthetic prefix: {record['device_id']!r}")
    if record["region_bucket"] not in HOME_REGION_BUCKETS:
        raise ValueError(f"region_bucket not in allow-list: {record['region_bucket']!r}")
    if record["challenge_result"] not in CHALLENGE_RESULTS:
        raise ValueError(f"challenge_result not in allow-list: {record['challenge_result']!r}")
    if not isinstance(record["challenge_required"], bool):
        raise ValueError("challenge_required must be bool")


def _assert_security_event_shape(record: SecurityEvent) -> None:
    keys = set(record.keys())
    if keys != _SECURITY_EVENT_KEYS:
        missing = _SECURITY_EVENT_KEYS - keys
        extra = keys - _SECURITY_EVENT_KEYS
        raise ValueError(
            f"security event shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["security_event_id"].startswith(SECURITY_EVENT_ID_PREFIX):
        raise ValueError(
            f"security_event_id missing synthetic prefix: {record['security_event_id']!r}"
        )
    if not record["session_id"].startswith(LOGIN_SESSION_ID_PREFIX):
        raise ValueError(f"session_id missing synthetic prefix: {record['session_id']!r}")
    if record["event_type"] not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"event_type not in allow-list: {record['event_type']!r}")
    if record["safe_risk_marker"] not in ALLOWED_SAFE_RISK_MARKERS:
        raise ValueError(f"safe_risk_marker not in allow-list: {record['safe_risk_marker']!r}")


def _assert_transfer_event_shape(record: TransferEvent) -> None:
    keys = set(record.keys())
    if keys != _TRANSFER_EVENT_KEYS:
        missing = _TRANSFER_EVENT_KEYS - keys
        extra = keys - _TRANSFER_EVENT_KEYS
        raise ValueError(
            f"transfer event shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["transfer_event_id"].startswith(TRANSFER_EVENT_ID_PREFIX):
        raise ValueError(
            f"transfer_event_id missing synthetic prefix: {record['transfer_event_id']!r}"
        )
    if not record["customer_id"].startswith("cust_"):
        raise ValueError(f"customer_id missing synthetic prefix: {record['customer_id']!r}")
    if not record["account_id"].startswith("acct_"):
        raise ValueError(f"account_id missing synthetic prefix: {record['account_id']!r}")
    if not record["recipient_id"].startswith("recip_"):
        raise ValueError(f"recipient_id missing synthetic prefix: {record['recipient_id']!r}")
    if record["event_type"] not in _TRANSFER_EVENT_TYPES:
        raise ValueError(f"event_type not in transfer allow-list: {record['event_type']!r}")
    if record["amount_bucket"] not in AMOUNT_BUCKETS:
        raise ValueError(f"amount_bucket not in allow-list: {record['amount_bucket']!r}")
    if record["synthetic_truth_label"] not in {"normal_activity", "high_risk_synthetic_activity"}:
        raise ValueError(
            f"synthetic_truth_label not in allow-list: {record['synthetic_truth_label']!r}"
        )


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------


def _index_devices_by_customer(devices: list[Device]) -> dict[str, list[Device]]:
    by_cust: dict[str, list[Device]] = defaultdict(list)
    for d in devices:
        by_cust[d["customer_id"]].append(d)
    return dict(by_cust)


def _index_accounts_by_customer(accounts: list[Account]) -> dict[str, Account]:
    return {a["customer_id"]: a for a in accounts}


def _index_sessions_by_customer(
    sessions: list[LoginSession],
) -> dict[str, list[LoginSession]]:
    by_cust: dict[str, list[LoginSession]] = defaultdict(list)
    for s in sessions:
        by_cust[s["customer_id"]].append(s)
    return dict(by_cust)


def _index_transfer_edges_by_customer(
    graph_edges: list[GraphEdge],
) -> dict[str, list[GraphEdge]]:
    by_cust: dict[str, list[GraphEdge]] = defaultdict(list)
    for e in graph_edges:
        if e["relationship_type"] == "attempted_transfer_to":
            by_cust[e["source_node_id"]].append(e)
    return dict(by_cust)


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------


def _draw_session_region(rng: random.Random, customer: Customer) -> str:
    if rng.random() < _REGION_DRIFT_RATE:
        # Drift to a non-home region — supports the activity_channel_shift
        # and current_device_mismatch model-vulnerability families later.
        candidates = tuple(r for r in HOME_REGION_BUCKETS if r != customer["home_region_bucket"])
        return rng.choice(candidates)
    return customer["home_region_bucket"]


def _draw_challenge(rng: random.Random) -> tuple[bool, str]:
    if rng.random() < _CHALLENGE_REQUIRED_RATE:
        result = "passed" if rng.random() < _CHALLENGE_PASS_RATE else "failed"
        return True, result
    return False, "not_required"


# ---------------------------------------------------------------------------
# Public generators
# ---------------------------------------------------------------------------


def generate_login_sessions(
    rng: random.Random,
    customers: list[Customer],
    devices: list[Device],
) -> list[LoginSession]:
    """Generate one ``LoginSession`` per device-login over the 30-day window.

    Total per device equals the device's ``login_count_30d``. Total per
    customer therefore equals the customer's ``normal_login_frequency_30d``
    by construction (which is enforced upstream by ``devices.generate_devices``).
    """
    sessions: list[LoginSession] = []
    next_index = 0
    customer_by_id = {c["customer_id"]: c for c in customers}

    for device in devices:
        customer = customer_by_id.get(device["customer_id"])
        if customer is None:
            raise ValueError(
                f"device {device['device_id']!r} references unknown customer "
                f"{device['customer_id']!r}"
            )
        for _ in range(device["login_count_30d"]):
            next_index += 1
            challenge_required, challenge_result = _draw_challenge(rng)
            record: LoginSession = {
                "session_id": make_login_session_id(next_index),
                "customer_id": customer["customer_id"],
                "device_id": device["device_id"],
                "event_time_utc": _draw_event_time(rng, _LOGIN_WINDOW_DAYS),
                "channel": device["device_channel"],
                "region_bucket": _draw_session_region(rng, customer),
                "challenge_required": challenge_required,
                "challenge_result": challenge_result,
            }
            _assert_login_session_shape(record)
            sessions.append(record)
    return sessions


def generate_security_events(
    rng: random.Random,
    customers: list[Customer],
    login_sessions: list[LoginSession],
    external_account_pairs: list[tuple[str, str]] | None = None,
) -> list[SecurityEvent]:
    """Generate sparse account-access / profile / challenge events.

    Two passes:
      1. One ``external_account_link_attempt`` per external-account pair
         (passed in as ``(customer_id, anchor_session_event_time)``-style
         tuples — see component 7's wiring).
      2. Per-customer 0–3 extra security events drawn from the sparse type
         distribution. Each event anchors to a random login session of the
         same customer.

    External-account-link events are rendered via the second pass only when
    ``external_account_pairs`` is None — otherwise the first pass would
    duplicate them. For Phase 2 simplicity, the wiring CLI in component 7
    will pass ``None`` and rely on the sparse pass to surface a healthy
    distribution.

    Args:
        rng: Seeded ``random.Random``.
        customers: Customer list.
        login_sessions: All generated login sessions; needed to anchor each
            security event to a real session of the same customer.
        external_account_pairs: Reserved for future wiring; currently unused.
            The parameter is part of the signature so component 7 / 5 can
            extend behavior without changing the public API.

    Returns:
        Flat list of ``SecurityEvent`` TypedDicts.
    """
    _ = external_account_pairs  # reserved
    events: list[SecurityEvent] = []
    next_index = 0
    sessions_by_customer = _index_sessions_by_customer(login_sessions)

    for customer in customers:
        n_extra = rng.choices(
            _SECURITY_EVENT_COUNT_CHOICES, weights=_SECURITY_EVENT_COUNT_WEIGHTS, k=1
        )[0]
        if n_extra == 0:
            continue
        cust_sessions = sessions_by_customer.get(customer["customer_id"], [])
        if not cust_sessions:
            # No sessions to anchor to — skip even if RNG asked for events.
            continue
        for _ in range(n_extra):
            next_index += 1
            anchor = rng.choice(cust_sessions)
            event_type = rng.choice(_SPARSE_SECURITY_EVENT_TYPES)
            record: SecurityEvent = {
                "security_event_id": make_security_event_id(next_index),
                "customer_id": customer["customer_id"],
                "session_id": anchor["session_id"],
                "event_type": event_type,
                "event_time_utc": _draw_event_time(rng, _SECURITY_WINDOW_DAYS),
                "device_id": anchor["device_id"],
                "safe_risk_marker": _SAFE_RISK_MARKERS[event_type],
            }
            _assert_security_event_shape(record)
            events.append(record)
    return events


def generate_transfer_events(
    rng: random.Random,
    customers: list[Customer],
    accounts: list[Account],
    devices: list[Device],
    graph_edges: list[GraphEdge],
) -> list[TransferEvent]:
    """Generate transfer attempts at population scale.

    Each customer with ``normal_transfer_frequency_30d > 0`` and at least
    one ``attempted_transfer_to`` graph edge contributes that many transfer
    events. Recipient is drawn from the customer's edge list; channel is
    drawn from the customer's device list; account is the customer's 1:1
    account.

    All emitted records carry ``synthetic_truth_label="normal_activity"``
    as a placeholder. Component 5's ``labels.py`` re-evaluates each event
    with the latent-driver model and overwrites the label where appropriate.
    """
    events: list[TransferEvent] = []
    next_index = 0

    devices_by_customer = _index_devices_by_customer(devices)
    accounts_by_customer = _index_accounts_by_customer(accounts)
    edges_by_customer = _index_transfer_edges_by_customer(graph_edges)

    for customer in customers:
        target_count = customer["normal_transfer_frequency_30d"]
        if target_count <= 0:
            continue

        cust_edges = edges_by_customer.get(customer["customer_id"], [])
        if not cust_edges:
            # No graph link to any recipient — synthetic transfer count
            # is structurally zero for this customer.
            continue

        cust_devices = devices_by_customer.get(customer["customer_id"], [])
        cust_account = accounts_by_customer.get(customer["customer_id"])
        if not cust_devices or cust_account is None:
            # Defensive: every customer should have devices + account, but
            # if upstream invariants slip, skip rather than emit invalid
            # records.
            continue

        for _ in range(target_count):
            next_index += 1
            edge = rng.choice(cust_edges)
            device = rng.choice(cust_devices)
            event_type = rng.choices(
                _TRANSFER_EVENT_TYPES, weights=_TRANSFER_EVENT_WEIGHTS, k=1
            )[0]
            amount_bucket = rng.choice(AMOUNT_BUCKETS)
            record: TransferEvent = {
                "transfer_event_id": make_transfer_event_id(next_index),
                "customer_id": customer["customer_id"],
                "account_id": cust_account["account_id"],
                "event_type": event_type,
                "event_time_utc": _draw_event_time(rng, _TRANSFER_WINDOW_DAYS),
                "amount_bucket": amount_bucket,
                "recipient_id": edge["target_node_id"],
                "channel": device["device_channel"],
                # Placeholder; component 5 overrides where the latent-driver
                # model says high-risk.
                "synthetic_truth_label": "normal_activity",
            }
            _assert_transfer_event_shape(record)
            events.append(record)
    return events
