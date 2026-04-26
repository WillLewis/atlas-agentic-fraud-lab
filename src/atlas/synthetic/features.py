"""Synthetic feature calculator (Phase 3).

Recomputes engineered ``FeatureVector`` records from raw entities, event
histories, and partition-local graph context. Emits one feature vector per
``transfer_event`` matching the public ``FeatureVector`` schema in
``project_atlas_openapi.yaml`` and the ``features[]`` shape in
``project_atlas_sample_data.json``.

Phase 3 emits 17 fields. The schema-config ``feature_families`` block in
``config/synthetic_schema.yaml`` lists a Bible §11.3 superset that includes
four future/internal names (``username_recovery_count_72h``,
``region_change_count_72h``, ``new_recipient_indicator``, ``account_age_days``);
those are intentionally NOT emitted here. The ``phase_3_emitted_features``
block in the schema config is the canonical list this module honors.

Phase 3 contracts (asserted by code, validated by tests in component 6):

  1. **Deterministic.** No ``random.*``, no ``datetime.now()``, no
     ``os.environ`` reads in the normal computation path. Same source
     data → byte-identical feature vectors.
  2. **One ``FeatureVector`` per ``transfer_event``.** Computed from
     entities, prior event histories, and partition-local graph context
     visible at ``transfer.event_time_utc``.
  3. **No label leakage.** This module does NOT import
     ``atlas.synthetic.labels``, does NOT read ``synthetic_truth_label``,
     and does NOT read ``label_generation`` records. Labels are
     downstream of features.
  4. **No future leakage.** For a feature vector keyed on ``tx_*``, only
     events with ``event_time_utc <= transfer.event_time_utc`` are
     visible to the formulas.
  5. **Safe ratios.** Every ratio uses an explicit
     ``denominator > 0`` guard; on zero-denominator the field returns
     ``NULL_RATIO_FALLBACK = 0.0``. Never ``NaN``, never ``inf``.
  6. **``geo_consistency_flag`` is ``0`` or ``1``** (int). Never bool,
     never str.
  7. **No direct engineered-feature mutation in the normal path.** A
     debug-only override (component 5) is gated by
     ``DEBUG_DIRECT_FEATURE_MUTATION=true``. The default
     recomputation path always derives features from raw histories.
  8. **Split-safe graph features.** ``shared_device_degree``,
     ``shared_recipient_degree``, and ``entity_graph_risk_score`` are
     computed from the partition's customer / device / recipient / edge
     view only — never from a global all-customers graph. Component 4
     calls ``recompute_feature_vectors`` once per partition.

Phase 3 stops here: NO model training, NO scorer, NO API, NO judge.
"""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Final, TypedDict

from atlas.synthetic.customers import Customer
from atlas.synthetic.devices import Device
from atlas.synthetic.events import LoginSession, SecurityEvent, TransferEvent
from atlas.synthetic.graph import GraphEdge

# ---------------------------------------------------------------------------
# Public record shape — matches OpenAPI FeatureVector (lines 661-699)
# ---------------------------------------------------------------------------


class FeatureVector(TypedDict):
    """Engineered feature vector emitted per transfer event.

    Field types mirror ``FeatureVector`` in ``project_atlas_openapi.yaml``:
    two strings, nine integers, six floats. ``geo_consistency_flag`` is
    an integer constrained to ``{0, 1}``.

    JSON-serializable as-is (no nested objects).
    """

    event_id: str
    customer_id: str
    login_count_72h: int
    login_count_30d: int
    login_velocity_ratio: float
    challenge_count_72h: int
    challenge_pass_ratio_30d: float
    password_recovery_count_72h: int
    device_count_72h: int
    current_device_tenure_days: int
    geo_consistency_flag: int
    transfer_count_72h: int
    recipient_tenure_days: int
    shared_device_degree: int
    shared_recipient_degree: int
    entity_graph_risk_score: float
    cash_movement_velocity_score: float


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Required key set used by ``_assert_feature_vector_shape``. Mirrors
# ``FeatureVector``'s TypedDict fields one-for-one. Any drift between this
# set and the TypedDict will fail the validator.
FEATURE_VECTOR_KEYS: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "customer_id",
        "login_count_72h",
        "login_count_30d",
        "login_velocity_ratio",
        "challenge_count_72h",
        "challenge_pass_ratio_30d",
        "password_recovery_count_72h",
        "device_count_72h",
        "current_device_tenure_days",
        "geo_consistency_flag",
        "transfer_count_72h",
        "recipient_tenure_days",
        "shared_device_degree",
        "shared_recipient_degree",
        "entity_graph_risk_score",
        "cash_movement_velocity_score",
    }
)

# Default fallback for ratio features when the denominator is zero. Matches
# the divide-by-zero contract in the Phase 3 plan.
NULL_RATIO_FALLBACK: Final[float] = 0.0

# Time windows used by per-event temporal features. Constants here so
# component 2's formulas stay aligned with documentation.
WINDOW_72H_HOURS: Final[int] = 72
WINDOW_30D_DAYS: Final[int] = 30

# Allowed values for ``geo_consistency_flag``.
GEO_FLAG_VALUES: Final[tuple[int, ...]] = (0, 1)

# Coefficients for the ``entity_graph_risk_score`` aggregator. Module-level
# so component 3 + tests can reference the exact weights.
GRAPH_RISK_DEVICE_COEFF: Final[float] = 0.05
GRAPH_RISK_RECIPIENT_COEFF: Final[float] = 0.12

# Coefficients for ``cash_movement_velocity_score``. Document the source
# weights so red-team / blue-team agents in Phase 6+ can reason about them.
CASH_VELOCITY_AMOUNT_COEFF: Final[float] = 0.6
CASH_VELOCITY_FREQUENCY_COEFF: Final[float] = 0.4
CASH_VELOCITY_DENOMINATOR: Final[int] = 10

# Cross-reference ID prefixes that the validator expects. These mirror
# ``config/safety.yaml.synthetic_id_prefixes``.
EVENT_ID_PREFIX: Final[str] = "tx_"
CUSTOMER_ID_PREFIX: Final[str] = "cust_"


# ---------------------------------------------------------------------------
# Runtime shape validator
# ---------------------------------------------------------------------------


def _assert_feature_vector_shape(record: FeatureVector) -> None:
    """Runtime shape + domain check. Raises ``ValueError`` on any mismatch.

    Does NOT import any other ``atlas.synthetic`` module — keeps the label-
    leakage guard at compile time as well as runtime.
    """
    keys = set(record.keys())
    if keys != FEATURE_VECTOR_KEYS:
        missing = FEATURE_VECTOR_KEYS - keys
        extra = keys - FEATURE_VECTOR_KEYS
        raise ValueError(
            f"feature vector shape mismatch (missing={sorted(missing)}, "
            f"extra={sorted(extra)})"
        )

    if not record["event_id"].startswith(EVENT_ID_PREFIX):
        raise ValueError(
            f"event_id must reference a {EVENT_ID_PREFIX}* transfer: {record['event_id']!r}"
        )
    if not record["customer_id"].startswith(CUSTOMER_ID_PREFIX):
        raise ValueError(
            f"customer_id must use {CUSTOMER_ID_PREFIX}* prefix: {record['customer_id']!r}"
        )

    # Integer count fields must be non-negative.
    for count_field in (
        "login_count_72h",
        "login_count_30d",
        "challenge_count_72h",
        "password_recovery_count_72h",
        "device_count_72h",
        "current_device_tenure_days",
        "transfer_count_72h",
        "recipient_tenure_days",
        "shared_device_degree",
        "shared_recipient_degree",
    ):
        v = record[count_field]  # type: ignore[literal-required]
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError(f"{count_field} must be int, got {type(v).__name__}")
        if v < 0:
            raise ValueError(f"{count_field} must be >= 0, got {v}")

    # geo_consistency_flag is the int 0 or 1.
    geo = record["geo_consistency_flag"]
    if not isinstance(geo, int) or isinstance(geo, bool) or geo not in GEO_FLAG_VALUES:
        raise ValueError(f"geo_consistency_flag must be 0 or 1 (int), got {geo!r}")

    # Float fields must be finite and within their declared bounds.
    for ratio_field, lo, hi in (
        ("login_velocity_ratio", 0.0, float("inf")),
        ("challenge_pass_ratio_30d", 0.0, 1.0),
        ("entity_graph_risk_score", 0.0, 1.0),
        ("cash_movement_velocity_score", 0.0, 1.0),
    ):
        v = record[ratio_field]  # type: ignore[literal-required]
        if not isinstance(v, float):
            raise ValueError(f"{ratio_field} must be float, got {type(v).__name__}")
        # Reject NaN / +inf / -inf explicitly.
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError(f"{ratio_field} must be finite, got {v}")
        if not (lo <= v <= hi):
            raise ValueError(f"{ratio_field} out of bounds [{lo}, {hi}]: {v}")


# ---------------------------------------------------------------------------
# Public entry point — implementation lands in components 2 + 3
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _parse_utc(timestamp: str) -> datetime:
    """Parse a fixture-format ``YYYY-MM-DDTHH:MM:SSZ`` string to UTC.

    Mirrors ``atlas.synthetic.events._format_event_time_utc`` exactly, so
    every event we emit is round-trippable.
    """
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


# Half-open window: events with ``event_time_utc`` in
# ``[anchor - window, anchor)`` are considered "prior". The strict-less-
# than upper bound prevents a transfer from including itself in its own
# transfer_count_72h, and avoids the chicken-and-egg case where two events
# at exactly the same timestamp would each count the other.


def _in_prior_window(
    event_time: datetime, anchor: datetime, window: timedelta
) -> bool:
    return (anchor - window) <= event_time < anchor


# ---------------------------------------------------------------------------
# Index helpers — pre-compute per-customer views to avoid O(n*m) scans.
# ---------------------------------------------------------------------------


def _index_sessions_by_customer(
    sessions: list[LoginSession],
) -> dict[str, list[tuple[datetime, LoginSession]]]:
    """Customer-id → list of (parsed_time, session) tuples, time-sorted.

    Sorting once lets ``geo_consistency_flag`` walk the list in reverse
    to find the most-recent prior login in O(k) rather than O(n).
    """
    by_cust: dict[str, list[tuple[datetime, LoginSession]]] = defaultdict(list)
    for s in sessions:
        by_cust[s["customer_id"]].append((_parse_utc(s["event_time_utc"]), s))
    for cid in by_cust:
        by_cust[cid].sort(key=lambda pair: pair[0])
    return dict(by_cust)


def _index_security_by_customer(
    security_events: list[SecurityEvent],
) -> dict[str, list[tuple[datetime, SecurityEvent]]]:
    by_cust: dict[str, list[tuple[datetime, SecurityEvent]]] = defaultdict(list)
    for e in security_events:
        by_cust[e["customer_id"]].append((_parse_utc(e["event_time_utc"]), e))
    return dict(by_cust)


def _index_transfers_by_customer(
    transfer_events: list[TransferEvent],
) -> dict[str, list[tuple[datetime, TransferEvent]]]:
    by_cust: dict[str, list[tuple[datetime, TransferEvent]]] = defaultdict(list)
    for t in transfer_events:
        by_cust[t["customer_id"]].append((_parse_utc(t["event_time_utc"]), t))
    return dict(by_cust)


def _index_devices_by_customer(
    devices: list[Device],
) -> dict[str, list[Device]]:
    by_cust: dict[str, list[Device]] = defaultdict(list)
    for d in devices:
        by_cust[d["customer_id"]].append(d)
    return dict(by_cust)


def _index_transfer_edges(
    graph_edges: list[GraphEdge],
) -> dict[tuple[str, str], GraphEdge]:
    """``(customer_id, recipient_id)`` → ``attempted_transfer_to`` edge."""
    out: dict[tuple[str, str], GraphEdge] = {}
    for g in graph_edges:
        if g["relationship_type"] == "attempted_transfer_to":
            out[(g["source_node_id"], g["target_node_id"])] = g
    return out


# ---------------------------------------------------------------------------
# Per-feature helpers (component 2 — non-graph fields)
# ---------------------------------------------------------------------------


def _count_in_window(
    events: list[tuple[datetime, object]],
    anchor: datetime,
    window: timedelta,
) -> int:
    return sum(1 for ts, _ in events if _in_prior_window(ts, anchor, window))


def _safe_ratio(numerator: float, denominator: float) -> float:
    """Ratio with deterministic divide-by-zero. Always finite, in [0, ...]."""
    if denominator <= 0:
        return NULL_RATIO_FALLBACK
    return numerator / denominator


def _login_features(
    customer_sessions: list[tuple[datetime, LoginSession]],
    transfer_time: datetime,
) -> tuple[int, int, float]:
    """Returns (login_count_72h, login_count_30d, login_velocity_ratio)."""
    win72 = timedelta(hours=WINDOW_72H_HOURS)
    win30 = timedelta(days=WINDOW_30D_DAYS)
    n72 = _count_in_window(customer_sessions, transfer_time, win72)
    n30 = _count_in_window(customer_sessions, transfer_time, win30)
    ratio = round(_safe_ratio(n72, n30), 4)
    return n72, n30, ratio


def _challenge_features(
    customer_sessions: list[tuple[datetime, LoginSession]],
    transfer_time: datetime,
) -> tuple[int, float]:
    """Returns (challenge_count_72h, challenge_pass_ratio_30d)."""
    win72 = timedelta(hours=WINDOW_72H_HOURS)
    win30 = timedelta(days=WINDOW_30D_DAYS)
    n_required_72h = 0
    n_required_30d = 0
    n_passed_30d = 0
    for ts, s in customer_sessions:
        if not s["challenge_required"]:
            continue
        if _in_prior_window(ts, transfer_time, win72):
            n_required_72h += 1
        if _in_prior_window(ts, transfer_time, win30):
            n_required_30d += 1
            if s["challenge_result"] == "passed":
                n_passed_30d += 1
    pass_ratio = round(_safe_ratio(n_passed_30d, n_required_30d), 4)
    return n_required_72h, pass_ratio


def _password_recovery_count_72h(
    customer_security: list[tuple[datetime, SecurityEvent]],
    transfer_time: datetime,
) -> int:
    win72 = timedelta(hours=WINDOW_72H_HOURS)
    return sum(
        1
        for ts, e in customer_security
        if e["event_type"] == "password_recovery_completed"
        and _in_prior_window(ts, transfer_time, win72)
    )


def _device_count_72h(
    customer_sessions: list[tuple[datetime, LoginSession]],
    transfer_time: datetime,
) -> int:
    win72 = timedelta(hours=WINDOW_72H_HOURS)
    seen: set[str] = set()
    for ts, s in customer_sessions:
        if _in_prior_window(ts, transfer_time, win72):
            seen.add(s["device_id"])
    return len(seen)


def _current_device_tenure_days(customer_devices: list[Device]) -> int:
    for d in customer_devices:
        if d["is_current_event_device"]:
            return d["first_seen_days_ago"]
    return 0


def _geo_consistency_flag(
    customer_sessions: list[tuple[datetime, LoginSession]],
    customer: Customer,
    transfer_time: datetime,
) -> int:
    """1 iff the customer's most-recent session at-or-before the transfer
    is in the customer's home region. ``0`` when no prior session exists.
    """
    most_recent: LoginSession | None = None
    most_recent_ts: datetime | None = None
    for ts, s in customer_sessions:
        if ts <= transfer_time and (most_recent_ts is None or ts > most_recent_ts):
            most_recent_ts = ts
            most_recent = s
    if most_recent is None:
        return 0
    return 1 if most_recent["region_bucket"] == customer["home_region_bucket"] else 0


def _transfer_count_72h(
    customer_transfers: list[tuple[datetime, TransferEvent]],
    transfer_time: datetime,
) -> int:
    win72 = timedelta(hours=WINDOW_72H_HOURS)
    return _count_in_window(customer_transfers, transfer_time, win72)


def _recipient_tenure_days(
    edges_by_pair: dict[tuple[str, str], GraphEdge],
    customer_id: str,
    recipient_id: str,
) -> int:
    edge = edges_by_pair.get((customer_id, recipient_id))
    if edge is None:
        return 0
    return edge["first_seen_days_ago"]


def _amount_bucket_index(amount_bucket: str) -> int:
    """Extract the 1..10 index from ``amount_bucket_NN``."""
    try:
        idx = int(amount_bucket.rsplit("_", 1)[-1])
    except ValueError as exc:
        raise ValueError(f"unrecognized amount_bucket: {amount_bucket!r}") from exc
    if not (1 <= idx <= 10):
        raise ValueError(f"amount_bucket index out of range [1,10]: {idx}")
    return idx


def _cash_movement_velocity_score(
    amount_bucket: str, transfer_count_72h: int
) -> float:
    amount_index = _amount_bucket_index(amount_bucket)
    raw = (
        CASH_VELOCITY_AMOUNT_COEFF * (amount_index / CASH_VELOCITY_DENOMINATOR)
        + CASH_VELOCITY_FREQUENCY_COEFF
        * (transfer_count_72h / CASH_VELOCITY_DENOMINATOR)
    )
    return round(max(0.0, min(1.0, raw)), 4)


# ---------------------------------------------------------------------------
# Graph-derived feature helpers (component 3 — split-safe)
#
# Split-safety contract: the caller passes PARTITION-LOCAL lists into
# ``recompute_feature_vectors``. These helpers compute relationship counts
# from only the data they see — there is no global state, no on-disk read,
# no cross-partition lookup. Component 4 will codify the per-partition
# calling pattern in ``scripts/generate_synthetic.py``.
#
# Definitions for Phase 3:
#
#   * ``shared_device_degree``    — for customer ``C`` in partition ``P``:
#       number of OTHER customers in ``P`` whose current-event device's
#       ``device_channel`` matches ``C``'s current-event device's channel.
#       Returns ``0`` when ``C`` has no current-event device.
#
#   * ``shared_recipient_degree`` — for transfer ``C → R`` in partition ``P``:
#       number of OTHER customers in ``P`` who also have an
#       ``attempted_transfer_to`` edge to recipient ``R``.
#       Returns ``0`` when no edge exists for ``C → R``.
#
#   * ``entity_graph_risk_score`` —
#       ``clamp(GRAPH_RISK_DEVICE_COEFF * shared_device_degree
#              + GRAPH_RISK_RECIPIENT_COEFF * shared_recipient_degree,
#              0, 1)`` rounded to 4dp.
# ---------------------------------------------------------------------------


def _index_current_device_channel_by_customer(
    devices: list[Device],
) -> dict[str, str]:
    """Customer → ``device_channel`` of their current-event device.

    Customers without a current-event device do not appear in the result.
    Phase 2's ``devices.generate_devices`` guarantees exactly one current
    device per customer, so ties are not expected; if multiple devices are
    flagged current the first wins (insertion order).
    """
    out: dict[str, str] = {}
    for d in devices:
        if d["is_current_event_device"] and d["customer_id"] not in out:
            out[d["customer_id"]] = d["device_channel"]
    return out


def _index_customers_by_current_channel(
    channel_by_customer: dict[str, str],
) -> dict[str, set[str]]:
    """Inverted index: ``device_channel`` → set of customers using it as
    their current-event device's channel."""
    out: dict[str, set[str]] = defaultdict(set)
    for cid, channel in channel_by_customer.items():
        out[channel].add(cid)
    return dict(out)


def _index_customers_by_recipient(
    graph_edges: list[GraphEdge],
) -> dict[str, set[str]]:
    """Recipient → set of customer_ids with an ``attempted_transfer_to``
    edge to that recipient. Partition-local when ``graph_edges`` is the
    partition's edge list.
    """
    out: dict[str, set[str]] = defaultdict(set)
    for g in graph_edges:
        if g["relationship_type"] != "attempted_transfer_to":
            continue
        out[g["target_node_id"]].add(g["source_node_id"])
    return dict(out)


def _shared_device_degree(
    customer_id: str,
    channel_by_customer: dict[str, str],
    customers_by_channel: dict[str, set[str]],
) -> int:
    channel = channel_by_customer.get(customer_id)
    if channel is None:
        return 0
    cohort = customers_by_channel.get(channel, set())
    # Subtract self if present (always present by construction, but defensive).
    return max(0, len(cohort) - (1 if customer_id in cohort else 0))


def _shared_recipient_degree(
    customer_id: str,
    recipient_id: str,
    customers_by_recipient: dict[str, set[str]],
) -> int:
    cohort = customers_by_recipient.get(recipient_id, set())
    return max(0, len(cohort) - (1 if customer_id in cohort else 0))


def _entity_graph_risk_score(
    shared_device_degree: int, shared_recipient_degree: int
) -> float:
    raw = (
        GRAPH_RISK_DEVICE_COEFF * shared_device_degree
        + GRAPH_RISK_RECIPIENT_COEFF * shared_recipient_degree
    )
    return round(max(0.0, min(1.0, raw)), 4)


# ---------------------------------------------------------------------------
# Public entry point — component 2 fills 14 of 17 fields. The three
# graph-derived fields (``shared_device_degree``, ``shared_recipient_degree``,
# ``entity_graph_risk_score``) are zero placeholders here and are replaced
# in component 3.
# ---------------------------------------------------------------------------


def recompute_feature_vectors(
    transfer_events: list[TransferEvent],
    customers: list[Customer],
    devices: list[Device],
    graph_edges: list[GraphEdge],
    login_sessions: list[LoginSession],
    security_events: list[SecurityEvent],
) -> list[FeatureVector]:
    """Recompute one ``FeatureVector`` per transfer event.

    Inputs are typically partition-local — call once per
    train / validation / clean_holdout / locked_adaptive_holdout /
    drifted_holdout partition. Component 4 will codify that calling
    pattern in ``scripts/generate_synthetic.py``.

    Determinism: walks data structures in their input order, no RNG, no
    time-of-day reads. Same inputs → identical output list.

    Args:
        transfer_events: Transfer events to compute features for. Order
            preserved in output.
        customers, devices, graph_edges, login_sessions, security_events:
            Read-only context. Recipients are not needed at this layer
            because the recipient_tenure_days lookup goes through
            graph_edges; component 3 will pass partition-local edges to
            compute shared_recipient_degree split-safely.

    Returns:
        Length-equal list of ``FeatureVector`` records, validated against
        ``FEATURE_VECTOR_KEYS`` and the type/range constraints in
        ``_assert_feature_vector_shape``.
    """
    customer_by_id: dict[str, Customer] = {c["customer_id"]: c for c in customers}
    sessions_by_cust = _index_sessions_by_customer(login_sessions)
    security_by_cust = _index_security_by_customer(security_events)
    transfers_by_cust = _index_transfers_by_customer(transfer_events)
    devices_by_cust = _index_devices_by_customer(devices)
    edges_by_pair = _index_transfer_edges(graph_edges)

    # Graph-derived (component 3, split-safe). All built from the supplied
    # PARTITION-LOCAL lists — no global lookups.
    channel_by_customer = _index_current_device_channel_by_customer(devices)
    customers_by_channel = _index_customers_by_current_channel(channel_by_customer)
    customers_by_recipient = _index_customers_by_recipient(graph_edges)

    out: list[FeatureVector] = []
    for transfer in transfer_events:
        cid = transfer["customer_id"]
        customer = customer_by_id.get(cid)
        if customer is None:
            raise ValueError(
                f"transfer {transfer['transfer_event_id']!r} references unknown "
                f"customer {cid!r}"
            )

        transfer_time = _parse_utc(transfer["event_time_utc"])
        cust_sessions = sessions_by_cust.get(cid, [])
        cust_security = security_by_cust.get(cid, [])
        cust_transfers = transfers_by_cust.get(cid, [])
        cust_devices = devices_by_cust.get(cid, [])

        login_72h, login_30d, login_ratio = _login_features(
            cust_sessions, transfer_time
        )
        challenge_72h, challenge_pass_30d = _challenge_features(
            cust_sessions, transfer_time
        )
        pwd_recovery_72h = _password_recovery_count_72h(cust_security, transfer_time)
        device_72h = _device_count_72h(cust_sessions, transfer_time)
        current_dev_tenure = _current_device_tenure_days(cust_devices)
        geo_flag = _geo_consistency_flag(cust_sessions, customer, transfer_time)
        transfer_72h = _transfer_count_72h(cust_transfers, transfer_time)
        recip_tenure = _recipient_tenure_days(
            edges_by_pair, cid, transfer["recipient_id"]
        )
        cash_velocity = _cash_movement_velocity_score(
            transfer["amount_bucket"], transfer_72h
        )

        # Component 3 — split-safe graph features.
        sdd = _shared_device_degree(
            cid, channel_by_customer, customers_by_channel
        )
        srd = _shared_recipient_degree(
            cid, transfer["recipient_id"], customers_by_recipient
        )
        graph_risk = _entity_graph_risk_score(sdd, srd)

        record: FeatureVector = {
            "event_id": transfer["transfer_event_id"],
            "customer_id": cid,
            "login_count_72h": login_72h,
            "login_count_30d": login_30d,
            "login_velocity_ratio": login_ratio,
            "challenge_count_72h": challenge_72h,
            "challenge_pass_ratio_30d": challenge_pass_30d,
            "password_recovery_count_72h": pwd_recovery_72h,
            "device_count_72h": device_72h,
            "current_device_tenure_days": current_dev_tenure,
            "geo_consistency_flag": geo_flag,
            "transfer_count_72h": transfer_72h,
            "recipient_tenure_days": recip_tenure,
            "shared_device_degree": sdd,
            "shared_recipient_degree": srd,
            "entity_graph_risk_score": graph_risk,
            "cash_movement_velocity_score": cash_velocity,
        }
        _assert_feature_vector_shape(record)
        out.append(record)

    return out


# ---------------------------------------------------------------------------
# DEBUG-ONLY: direct feature mutation
#
# Bible §6.1 rule 9 and §18 Phase 3 acceptance criterion: synthetic search
# must mutate event histories and then recompute features. Direct engineered-
# feature mutation is permitted ONLY behind an explicit debug flag and MUST
# NOT power the public demo.
#
# This module exposes a single narrow override entry point. It is gated by
# the ``DEBUG_DIRECT_FEATURE_MUTATION`` environment variable, evaluated on
# every call (not at module-import time) so tests can toggle the flag via
# ``monkeypatch.setenv`` without reimporting.
#
# Phase 6+ red-team workers MUST NOT call this function in normal operation;
# their canonical path is "mutate event histories → call
# ``recompute_feature_vectors``". The override exists only for diagnostic
# experiments where re-running the full pipeline is expensive and a single
# field needs to be perturbed in isolation.
# ---------------------------------------------------------------------------

DEBUG_MUTATION_ENV_VAR: Final[str] = "DEBUG_DIRECT_FEATURE_MUTATION"
DEBUG_MUTATION_ENABLED_VALUE: Final[str] = "true"


class DirectFeatureMutationDisabledError(RuntimeError):
    """Raised when ``apply_direct_feature_mutation`` is called without the
    ``DEBUG_DIRECT_FEATURE_MUTATION=true`` environment variable.

    The error message is intentionally explicit so a stray red-team or
    blue-team caller in the public demo path surfaces the violation
    immediately rather than silently no-opping.
    """


def is_direct_feature_mutation_enabled() -> bool:
    """``True`` iff the debug environment variable is set to the literal
    string ``"true"``.

    The strict equality check (rather than a truthy / case-insensitive
    test) is deliberate: it prevents accidental enabling via
    ``DEBUG_DIRECT_FEATURE_MUTATION=1`` or ``=True``, which would otherwise
    paper over the safety contract.
    """
    return os.environ.get(DEBUG_MUTATION_ENV_VAR) == DEBUG_MUTATION_ENABLED_VALUE


def apply_direct_feature_mutation(
    feature_vector: FeatureVector,
    overrides: Mapping[str, Any],
) -> FeatureVector:
    """DEBUG-ONLY direct override of ``FeatureVector`` fields.

    Returns a NEW ``FeatureVector`` (does not mutate ``feature_vector``).
    The result is validated with ``_assert_feature_vector_shape`` so any
    type / range / prefix violation surfaces at the call site.

    Args:
        feature_vector: A canonical ``FeatureVector`` (typically produced
            by ``recompute_feature_vectors``).
        overrides: Sparse map of feature-name → new value. Keys must be
            members of ``FEATURE_VECTOR_KEYS``.

    Returns:
        A new ``FeatureVector`` with overrides applied.

    Raises:
        DirectFeatureMutationDisabledError: when the debug environment
            variable is not set to ``"true"``. This is the default state
            in the public demo path.
        ValueError: when ``overrides`` contains keys not in
            ``FEATURE_VECTOR_KEYS``, or when the resulting record fails
            the shape validator (e.g., a negative count, an out-of-range
            ratio, or a non-``0``/``1`` ``geo_consistency_flag``).
    """
    if not is_direct_feature_mutation_enabled():
        raise DirectFeatureMutationDisabledError(
            "Direct engineered-feature mutation is disabled in the public "
            "demo path. Set the environment variable "
            f"{DEBUG_MUTATION_ENV_VAR}={DEBUG_MUTATION_ENABLED_VALUE!r} "
            "to enable this debug-only override "
            "(PROJECT_ATLAS_BIBLE.md §6.1 rule 9, §18 Phase 3)."
        )

    extra_keys = set(overrides.keys()) - FEATURE_VECTOR_KEYS
    if extra_keys:
        raise ValueError(
            f"apply_direct_feature_mutation: unknown FeatureVector keys "
            f"in overrides: {sorted(extra_keys)}"
        )

    mutated: dict[str, Any] = dict(feature_vector)
    mutated.update(overrides)
    # Validator catches negative counts, out-of-range ratios, NaN/inf,
    # bad ID prefixes, non-0/1 geo flag, etc.
    _assert_feature_vector_shape(mutated)  # type: ignore[arg-type]
    return mutated  # type: ignore[return-value]
