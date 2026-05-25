"""Synthetic latent-label generator (Phase 2).

Emits one ``LabelGenerationRecord`` per ``TransferEvent`` and overwrites
each transfer's placeholder ``synthetic_truth_label`` with the value
implied by the latent-driver model.

Latent-driver model
-------------------
Each label record carries the same eight drivers as the fixture:

  * ``base_customer_risk``                — direct from ``customer.synthetic_base_risk``
  * ``account_access_change_marker``      — recent recovery / profile-update events
  * ``device_novelty_marker``             — current device is not long-tenured
  * ``security_recovery_marker``          — recent password / username recovery
  * ``cash_movement_velocity_marker``     — large transfer or top amount bucket
  * ``entity_reuse_marker``               — recipient reuse-degree >= 4
  * ``ring_membership_marker``            — deterministic ~4% of customers
  * ``label_noise``                       — uniform jitter in [0, 0.04]

Probability formula
-------------------
The public demo labels emphasize observable synthetic feature interactions.
That keeps the walkthrough about fixable model behavior, not hidden latent
customer risk:

    sum_markers = sum(six binary markers)
    if sum_markers > 0:
        prob = 0.45 * base_customer_risk
             + 0.08 * sum_markers
             + interaction_bonus
             + label_noise
    else:
        prob = base_customer_risk / 6.0 + label_noise
    prob = clamp(round(prob, 4), 0.0, 1.0)

The 1/6 "no-markers" dampener is the value that makes the fixture's
``tx_000001`` row come out at 0.04 (base=0.18, noise=0.01 → 0.18/6 + 0.01
= 0.04). Without that dampener, "clean" customers carry too much of their
base risk into the synthetic label, which over-saturates the
high-risk-synthetic-activity class.

Threshold at 0.5 → ``high_risk_synthetic_activity``; otherwise
``normal_activity``.

Phase-3 boundary
----------------
Markers are derived only from raw event context and entity fields. No
windowed aggregations, no velocity ratios, no graph-risk scores. The
"recent" event context is an existence check across the customer's
security-event list — not a windowed count.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Final, TypedDict

from atlas.synthetic.customers import Customer
from atlas.synthetic.devices import Device
from atlas.synthetic.events import SecurityEvent, TransferEvent
from atlas.synthetic.recipients import Recipient

# ---------------------------------------------------------------------------
# Record shapes
# ---------------------------------------------------------------------------


class LatentDrivers(TypedDict):
    base_customer_risk: float
    account_access_change_marker: int
    device_novelty_marker: int
    security_recovery_marker: int
    cash_movement_velocity_marker: int
    entity_reuse_marker: int
    ring_membership_marker: int
    label_noise: float


class LabelGenerationRecord(TypedDict):
    """1:1 with each transfer event. Keyed by the transfer's ``event_id``."""

    event_id: str
    latent_drivers: LatentDrivers
    synthetic_risk_probability: float
    synthetic_truth_label: str


# ---------------------------------------------------------------------------
# Allow-lists and constants
# ---------------------------------------------------------------------------

ALLOWED_LABEL_VALUES: Final[tuple[str, ...]] = (
    "normal_activity",
    "high_risk_synthetic_activity",
)

# Marker thresholds and weights. Tuned for a demo population where risk
# labels depend on observable synthetic signals instead of base-risk alone.
_HIGH_RISK_THRESHOLD: Final[float] = 0.5
_BASE_RISK_WEIGHT_WITH_MARKERS: Final[float] = 0.45
_PER_MARKER_WEIGHT: Final[float] = 0.08
_CASH_DEVICE_INTERACTION_WEIGHT: Final[float] = 0.22
_CASH_ENTITY_INTERACTION_WEIGHT: Final[float] = 0.14
_RECENT_ACCESS_DEVICE_INTERACTION_WEIGHT: Final[float] = 0.12
# Dampener applied to base_customer_risk when no markers fire. 1/6 is the
# value that reproduces the fixture's tx_000001 row exactly (0.18/6 + 0.01
# = 0.04). See the module docstring for the formula.
_BASE_DAMPENER_NO_MARKERS: Final[float] = 1.0 / 6.0

_DEVICE_NOVELTY_DAYS: Final[int] = 150
_ENTITY_REUSE_DEGREE_THRESHOLD: Final[int] = 4
_TOP_AMOUNT_BUCKETS: Final[frozenset[str]] = frozenset(
    {"amount_bucket_08", "amount_bucket_09", "amount_bucket_10"}
)
_LABEL_NOISE_MAX: Final[float] = 0.04

# Ring membership: customer_id index modulo 23 → ~4.3% of customers are
# ring members. Deterministic across seeds (depends only on customer_id),
# which gives Phase 6+ red-team a stable hidden-cluster pattern to search
# against.
_RING_MEMBERSHIP_MODULUS: Final[int] = 23

# Security-event types that flip the per-customer markers.
_ACCESS_CHANGE_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"password_recovery_completed", "username_recovery_completed", "profile_update"}
)
_SECURITY_RECOVERY_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"password_recovery_completed", "username_recovery_completed"}
)

_LATENT_DRIVER_KEYS: Final[frozenset[str]] = frozenset(
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

_LABEL_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "latent_drivers",
        "synthetic_risk_probability",
        "synthetic_truth_label",
    }
)


# ---------------------------------------------------------------------------
# Driver derivation helpers
# ---------------------------------------------------------------------------


def _is_ring_member(customer_id: str) -> bool:
    """Deterministic ring-membership check based on the customer index."""
    suffix = customer_id.removeprefix("cust_")
    return int(suffix) % _RING_MEMBERSHIP_MODULUS == 0


def _has_access_change_event(events: list[SecurityEvent]) -> bool:
    return any(e["event_type"] in _ACCESS_CHANGE_EVENT_TYPES for e in events)


def _has_security_recovery_event(events: list[SecurityEvent]) -> bool:
    return any(e["event_type"] in _SECURITY_RECOVERY_EVENT_TYPES for e in events)


def _has_novel_current_device(devices: list[Device]) -> bool:
    for d in devices:
        if d["is_current_event_device"] and d["first_seen_days_ago"] <= _DEVICE_NOVELTY_DAYS:
            return True
    return False


def _is_high_velocity_transfer(transfer: TransferEvent) -> bool:
    if transfer["event_type"] == "large_transfer_attempt":
        return True
    return transfer["amount_bucket"] in _TOP_AMOUNT_BUCKETS


def _is_high_reuse_recipient(recipient: Recipient) -> bool:
    return recipient["recipient_reuse_degree"] >= _ENTITY_REUSE_DEGREE_THRESHOLD


# ---------------------------------------------------------------------------
# Probability formula
# ---------------------------------------------------------------------------


def _compute_risk_probability(
    base_customer_risk: float,
    marker_sum: int,
    label_noise: float,
    *,
    account_access_change_marker: int,
    device_novelty_marker: int,
    security_recovery_marker: int,
    cash_movement_velocity_marker: int,
    entity_reuse_marker: int,
) -> float:
    """Latent drivers → synthetic risk probability."""
    if marker_sum > 0:
        interaction_bonus = 0.0
        if cash_movement_velocity_marker and device_novelty_marker:
            interaction_bonus += _CASH_DEVICE_INTERACTION_WEIGHT
        if cash_movement_velocity_marker and entity_reuse_marker:
            interaction_bonus += _CASH_ENTITY_INTERACTION_WEIGHT
        if (
            device_novelty_marker
            and (account_access_change_marker or security_recovery_marker)
        ):
            interaction_bonus += _RECENT_ACCESS_DEVICE_INTERACTION_WEIGHT
        raw = (
            (_BASE_RISK_WEIGHT_WITH_MARKERS * base_customer_risk)
            + (_PER_MARKER_WEIGHT * marker_sum)
            + interaction_bonus
            + label_noise
        )
    else:
        raw = _BASE_DAMPENER_NO_MARKERS * base_customer_risk + label_noise
    clamped = max(0.0, min(1.0, raw))
    return round(clamped, 4)


def _label_from_probability(prob: float) -> str:
    return (
        "high_risk_synthetic_activity"
        if prob >= _HIGH_RISK_THRESHOLD
        else "normal_activity"
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _assert_latent_drivers_shape(drivers: LatentDrivers) -> None:
    keys = set(drivers.keys())
    if keys != _LATENT_DRIVER_KEYS:
        missing = _LATENT_DRIVER_KEYS - keys
        extra = keys - _LATENT_DRIVER_KEYS
        raise ValueError(
            f"latent drivers shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    base = drivers["base_customer_risk"]
    if not (0.0 <= base <= 1.0):
        raise ValueError(f"base_customer_risk out of [0,1]: {base}")
    noise = drivers["label_noise"]
    if not (0.0 <= noise <= _LABEL_NOISE_MAX):
        raise ValueError(f"label_noise out of [0,{_LABEL_NOISE_MAX}]: {noise}")
    for marker_name in (
        "account_access_change_marker",
        "device_novelty_marker",
        "security_recovery_marker",
        "cash_movement_velocity_marker",
        "entity_reuse_marker",
        "ring_membership_marker",
    ):
        if drivers[marker_name] not in (0, 1):
            raise ValueError(f"{marker_name} must be 0 or 1, got {drivers[marker_name]!r}")


def _assert_label_record_shape(record: LabelGenerationRecord) -> None:
    keys = set(record.keys())
    if keys != _LABEL_RECORD_KEYS:
        missing = _LABEL_RECORD_KEYS - keys
        extra = keys - _LABEL_RECORD_KEYS
        raise ValueError(
            f"label record shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["event_id"].startswith("tx_"):
        raise ValueError(f"event_id must reference a tx_* transfer: {record['event_id']!r}")
    prob = record["synthetic_risk_probability"]
    if not (0.0 <= prob <= 1.0):
        raise ValueError(f"synthetic_risk_probability out of [0,1]: {prob}")
    if record["synthetic_truth_label"] not in ALLOWED_LABEL_VALUES:
        raise ValueError(
            f"synthetic_truth_label not in allow-list: {record['synthetic_truth_label']!r}"
        )
    _assert_latent_drivers_shape(record["latent_drivers"])


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------


def generate_label_generation_records(
    rng: random.Random,
    transfer_events: list[TransferEvent],
    customers: list[Customer],
    devices: list[Device],
    recipients: list[Recipient],
    security_events: list[SecurityEvent],
) -> list[LabelGenerationRecord]:
    """Generate one label record per transfer event.

    SIDE EFFECT: ``transfer_events`` is mutated. Each transfer's
    ``synthetic_truth_label`` is overwritten with the latent-driver-implied
    value (``"normal_activity"`` or ``"high_risk_synthetic_activity"``). The
    caller (component 7's ``scripts/generate_synthetic.py``) owns the
    transfer list and must persist it AFTER calling this function.

    Args:
        rng: Seeded ``random.Random``. Used only for ``label_noise`` jitter
            so each label's noise is RNG-deterministic.
        transfer_events: Transfer events from ``events.generate_transfer_events``.
            Mutated in place.
        customers, devices, recipients, security_events: Read-only context
            for marker derivation.

    Returns:
        List of ``LabelGenerationRecord`` TypedDicts, one per transfer
        event, in the same order as ``transfer_events``.
    """
    customer_by_id = {c["customer_id"]: c for c in customers}
    recipient_by_id = {r["recipient_id"]: r for r in recipients}

    devices_by_customer: dict[str, list[Device]] = defaultdict(list)
    for d in devices:
        devices_by_customer[d["customer_id"]].append(d)

    security_by_customer: dict[str, list[SecurityEvent]] = defaultdict(list)
    for s in security_events:
        security_by_customer[s["customer_id"]].append(s)

    records: list[LabelGenerationRecord] = []

    for transfer in transfer_events:
        customer = customer_by_id.get(transfer["customer_id"])
        if customer is None:
            raise ValueError(
                f"transfer {transfer['transfer_event_id']!r} references unknown customer "
                f"{transfer['customer_id']!r}"
            )
        recipient = recipient_by_id.get(transfer["recipient_id"])
        if recipient is None:
            raise ValueError(
                f"transfer {transfer['transfer_event_id']!r} references unknown recipient "
                f"{transfer['recipient_id']!r}"
            )

        cust_devices = devices_by_customer.get(transfer["customer_id"], [])
        cust_security_events = security_by_customer.get(transfer["customer_id"], [])

        # Six binary markers (booleans coerced to 0/1).
        access_change = int(_has_access_change_event(cust_security_events))
        device_novelty = int(_has_novel_current_device(cust_devices))
        security_recovery = int(_has_security_recovery_event(cust_security_events))
        cash_velocity = int(_is_high_velocity_transfer(transfer))
        entity_reuse = int(_is_high_reuse_recipient(recipient))
        ring_member = int(_is_ring_member(customer["customer_id"]))

        marker_sum = (
            access_change
            + device_novelty
            + security_recovery
            + cash_velocity
            + entity_reuse
            + ring_member
        )

        # Per-record noise jitter — RNG-deterministic.
        label_noise = round(rng.uniform(0.0, _LABEL_NOISE_MAX), 4)

        prob = _compute_risk_probability(
            base_customer_risk=customer["synthetic_base_risk"],
            marker_sum=marker_sum,
            label_noise=label_noise,
            account_access_change_marker=access_change,
            device_novelty_marker=device_novelty,
            security_recovery_marker=security_recovery,
            cash_movement_velocity_marker=cash_velocity,
            entity_reuse_marker=entity_reuse,
        )
        label = _label_from_probability(prob)

        drivers: LatentDrivers = {
            "base_customer_risk": customer["synthetic_base_risk"],
            "account_access_change_marker": access_change,
            "device_novelty_marker": device_novelty,
            "security_recovery_marker": security_recovery,
            "cash_movement_velocity_marker": cash_velocity,
            "entity_reuse_marker": entity_reuse,
            "ring_membership_marker": ring_member,
            "label_noise": label_noise,
        }
        record: LabelGenerationRecord = {
            "event_id": transfer["transfer_event_id"],
            "latent_drivers": drivers,
            "synthetic_risk_probability": prob,
            "synthetic_truth_label": label,
        }
        _assert_label_record_shape(record)

        # Side effect: rewrite the transfer's placeholder label.
        transfer["synthetic_truth_label"] = label

        records.append(record)

    return records
