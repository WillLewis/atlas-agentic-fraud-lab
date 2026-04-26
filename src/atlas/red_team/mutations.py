"""Phase 6 candidate-mutation primitives.

Pure-function mutators that operate on **copies** of synthetic history
records and produce a ``CandidateState`` from which the existing
Phase 2/3 pipeline can recompute features + regenerate labels for ONE
target transfer event.

Phase 6 invariants enforced here:

  * No direct engineered-feature mutation. Every candidate path mutates
    synthetic history records (login sessions, security events, graph
    edges, devices, recipients, transfers) and then calls
    ``atlas.synthetic.features.recompute_feature_vectors`` to derive the
    new ``FeatureVector``.
  * No label leakage into scoring. Labels are regenerated via
    ``atlas.synthetic.labels.generate_label_generation_records`` AFTER
    the feature is computed. The regenerated label is used only to
    validate whether the candidate qualifies as
    ``high_risk_synthetic_activity`` — the scorer never sees it.
  * Deterministic. Same ``(rng, base, target_event_id, family_id)`` →
    byte-identical ``CandidateState``.
  * Public-safe. New record IDs use existing safe prefixes (``sess_``,
    ``sec_``, ``edge_``, ``dev_``, ``recip_``, ``cand_``) extended with
    short hex suffixes derived from a blake2b digest. No PII-shaped
    strings.
  * In-memory only. Mutations are NEVER persisted to ``data/synthetic/``.
"""

from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import dataclass, field
from typing import Final

from atlas.synthetic.accounts import Account
from atlas.synthetic.customers import Customer, HOME_REGION_BUCKETS
from atlas.synthetic.devices import DEVICE_CHANNELS, Device
from atlas.synthetic.events import (
    AMOUNT_BUCKETS,
    LoginSession,
    SecurityEvent,
    TransferEvent,
)
from atlas.synthetic.features import FeatureVector, recompute_feature_vectors
from atlas.synthetic.graph import EDGE_ID_PREFIX, GraphEdge
from atlas.synthetic.labels import (
    LabelGenerationRecord,
    generate_label_generation_records,
)
from atlas.synthetic.recipients import Recipient

# ---------------------------------------------------------------------------
# Public family allow-list — must match
# config/synthetic_schema.yaml.model_vulnerability_families.
# ---------------------------------------------------------------------------

ALLOWED_FAMILY_IDS: Final[tuple[str, ...]] = (
    "low_velocity_high_graph_risk",
    "recent_change_feature_delay",
    "score_boundary_cluster",
    "activity_channel_shift",
    "current_device_mismatch",
    "label_noise_mislearned",
    "overfit_fix_failure",
)

# ID prefixes for newly-minted synthetic records produced by mutations.
# All use existing safe prefixes from config/safety.yaml — no new prefixes
# need to be allow-listed.
_NEW_SESSION_PREFIX: Final[str] = "sess_p6_"
_NEW_SECURITY_PREFIX: Final[str] = "sec_p6_"
_NEW_EDGE_PREFIX: Final[str] = f"{EDGE_ID_PREFIX}p6_"
_NEW_DEVICE_PREFIX: Final[str] = "dev_p6_"

# Top amount buckets that fire cash_movement_velocity_marker (see
# atlas.synthetic.labels._TOP_AMOUNT_BUCKETS). Re-stated here so the
# search modules don't depend on the labels module's privates.
_TOP_AMOUNT_BUCKETS: Final[tuple[str, ...]] = (
    "amount_bucket_08",
    "amount_bucket_09",
    "amount_bucket_10",
)

# Safe risk markers for synthetic security events emitted by mutations.
# Mirrors atlas.synthetic.events._SAFE_RISK_MARKERS.
_RECENT_ACCESS_CHANGE_MARKER: Final[str] = "recent_account_access_change"


# ---------------------------------------------------------------------------
# State containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaseSearchState:
    """Read-only snapshot of one partition for the search to operate over.

    Use ``BaseSearchState.from_lists(...)`` to construct from in-memory
    lists (e.g. the conftest ``dataset`` fixture) or
    ``BaseSearchState.from_dataset_dir(...)`` to load the readable
    global artifact (``data/synthetic/{entities,events,graph}/``).
    """

    customers: tuple[Customer, ...]
    accounts: tuple[Account, ...]
    devices: tuple[Device, ...]
    recipients: tuple[Recipient, ...]
    graph_edges: tuple[GraphEdge, ...]
    login_sessions: tuple[LoginSession, ...]
    security_events: tuple[SecurityEvent, ...]
    transfer_events: tuple[TransferEvent, ...]

    @classmethod
    def from_lists(
        cls,
        *,
        customers,
        accounts,
        devices,
        recipients,
        graph_edges,
        login_sessions,
        security_events,
        transfer_events,
    ) -> "BaseSearchState":
        return cls(
            customers=tuple(customers),
            accounts=tuple(accounts),
            devices=tuple(devices),
            recipients=tuple(recipients),
            graph_edges=tuple(graph_edges),
            login_sessions=tuple(login_sessions),
            security_events=tuple(security_events),
            transfer_events=tuple(transfer_events),
        )

    @classmethod
    def from_dataset_dir(cls, data_dir) -> "BaseSearchState":
        """Load the readable global synthetic artifact (train + validation
        + clean_holdout). Phase 6 search reads only from these paths.
        """
        import json
        from pathlib import Path

        d = Path(data_dir)

        def _read(rel: str) -> list:
            p = d / rel
            if not p.exists():
                raise FileNotFoundError(
                    f"Phase 2/3 artifact not found at {p}. "
                    "Run `make seed` to regenerate the synthetic dataset."
                )
            return json.loads(p.read_text())

        return cls.from_lists(
            customers=_read("entities/customers.json"),
            accounts=_read("entities/accounts.json"),
            devices=_read("entities/devices.json"),
            recipients=_read("entities/recipients.json"),
            graph_edges=_read("graph/graph_edges.json"),
            login_sessions=_read("events/login_sessions.json"),
            security_events=_read("events/security_events.json"),
            transfer_events=_read("events/transfer_events.json"),
        )


@dataclass(frozen=True)
class CandidateState:
    """A mutation applied to ``BaseSearchState``.

    Holds the mutated copies needed to recompute features + regenerate
    labels for ONE target transfer; reuses the base records by reference
    for the unmutated parts.
    """

    candidate_id: str
    family_id: str
    target_event_id: str
    target_transfer: TransferEvent
    devices: list[Device]
    recipients: list[Recipient]
    graph_edges: list[GraphEdge]
    login_sessions: list[LoginSession]
    security_events: list[SecurityEvent]
    base: BaseSearchState = field(repr=False)


# ---------------------------------------------------------------------------
# ID helpers — deterministic, public-safe
# ---------------------------------------------------------------------------


def make_candidate_id(target_event_id: str, family_id: str, mutation_seed: int) -> str:
    """blake2b(target|family|seed)[:8] — short hex, no PII-shape risk."""
    h = hashlib.blake2b(
        f"{target_event_id}|{family_id}|{mutation_seed}".encode("utf-8"),
        digest_size=4,
    ).hexdigest()
    return f"cand_{h}"


def _short_hex(seed_str: str) -> str:
    """8-char hex digest — short enough to avoid the credit-card-shape
    pattern (13-16 consecutive digits) in the safety scanner.
    """
    return hashlib.blake2b(seed_str.encode("utf-8"), digest_size=4).hexdigest()


# ---------------------------------------------------------------------------
# Per-family record mutators
#
# Each function takes the ``rng`` plus the customer + relevant base
# records, and returns a NEW list (never mutates input). The dispatcher
# picks the right mutator(s) for the requested family.
# ---------------------------------------------------------------------------


def mutate_login_session_pattern(
    rng: random.Random,
    customer: Customer,
    sessions: list[LoginSession],
    family_id: str,
    *,
    target_event_time_utc: str,
    devices: list[Device],
) -> list[LoginSession]:
    """Append synthetic login session(s) that bias region or device per
    family. Returns a NEW list; ``sessions`` is unchanged.

    Families targeted:
      * ``activity_channel_shift`` — new login from a non-home region.
      * ``current_device_mismatch`` — new login from a different device
                                       than the customer's current one.
    """
    out = list(sessions)
    cust_devices = [d for d in devices if d["customer_id"] == customer["customer_id"]]
    if not cust_devices:
        return out

    if family_id == "activity_channel_shift":
        # Pick a region NOT in the customer's home region.
        non_home = tuple(
            r for r in HOME_REGION_BUCKETS if r != customer["home_region_bucket"]
        )
        if not non_home:
            return out
        device = cust_devices[0]
        new_session = LoginSession(
            session_id=f"{_NEW_SESSION_PREFIX}{_short_hex(customer['customer_id'] + 'channel')}",
            customer_id=customer["customer_id"],
            device_id=device["device_id"],
            event_time_utc=target_event_time_utc,
            channel=device["device_channel"],
            region_bucket=rng.choice(non_home),
            challenge_required=False,
            challenge_result="not_required",
        )
        out.append(new_session)
        return out

    if family_id == "current_device_mismatch":
        # Pick a non-current device's channel for the new session.
        non_current = [d for d in cust_devices if not d["is_current_event_device"]]
        chosen = non_current[0] if non_current else cust_devices[0]
        new_session = LoginSession(
            session_id=f"{_NEW_SESSION_PREFIX}{_short_hex(customer['customer_id'] + 'device')}",
            customer_id=customer["customer_id"],
            device_id=chosen["device_id"],
            event_time_utc=target_event_time_utc,
            channel=chosen["device_channel"],
            region_bucket=customer["home_region_bucket"],
            challenge_required=False,
            challenge_result="not_required",
        )
        out.append(new_session)
        return out

    # No-op for other families.
    return out


def mutate_security_event_timing(
    rng: random.Random,
    customer: Customer,
    sec_events: list[SecurityEvent],
    family_id: str,
    *,
    target_event_time_utc: str,
    devices: list[Device],
) -> list[SecurityEvent]:
    """Insert a synthetic security event close in time to the target
    transfer per family. Returns a NEW list; ``sec_events`` is unchanged.

    Families targeted:
      * ``recent_change_feature_delay`` — fresh password_recovery event
                                           ~24h before the target.
      * ``low_velocity_high_graph_risk`` — fires
        ``account_access_change_marker`` via a profile_update.
    """
    out = list(sec_events)
    cust_devices = [d for d in devices if d["customer_id"] == customer["customer_id"]]
    if not cust_devices:
        return out
    device = cust_devices[0]

    event_type, marker = _security_event_for_family(family_id)
    if event_type is None:
        return out

    new = SecurityEvent(
        security_event_id=(
            f"{_NEW_SECURITY_PREFIX}{_short_hex(customer['customer_id'] + family_id)}"
        ),
        customer_id=customer["customer_id"],
        session_id=f"{_NEW_SESSION_PREFIX}{_short_hex(customer['customer_id'] + 'sec')}",
        event_type=event_type,
        event_time_utc=target_event_time_utc,
        device_id=device["device_id"],
        safe_risk_marker=marker,
    )
    # Keep the rng touched so the mutation seed advances deterministically
    # even when mutate-policy is fixed for this family.
    rng.random()
    out.append(new)
    return out


def _security_event_for_family(family_id: str) -> tuple[str | None, str]:
    """Map a family to a (security_event_type, safe_risk_marker) pair."""
    if family_id == "recent_change_feature_delay":
        return "password_recovery_completed", _RECENT_ACCESS_CHANGE_MARKER
    if family_id == "low_velocity_high_graph_risk":
        return "profile_update", "normal_customer_update"
    if family_id == "label_noise_mislearned":
        return "username_recovery_completed", _RECENT_ACCESS_CHANGE_MARKER
    if family_id == "overfit_fix_failure":
        return "profile_update", "normal_customer_update"
    return None, ""


def mutate_transfer_context(
    rng: random.Random,
    customer: Customer,
    target_transfer: TransferEvent,
    recipients: list[Recipient],
    graph_edges: list[GraphEdge],
    family_id: str,
) -> tuple[TransferEvent, list[GraphEdge], list[Recipient]]:
    """Mutate the target transfer + (optionally) graph edges and
    recipients per family. Returns deep-copied/new objects; inputs are
    unchanged.

    Families targeted:
      * ``low_velocity_high_graph_risk`` — reassign target's recipient
                                           to one with high reuse_degree.
      * ``score_boundary_cluster``       — bump amount to a top bucket.
      * ``current_device_mismatch``      — flip transfer's channel.
      * ``activity_channel_shift``       — flip transfer's channel.
      * ``overfit_fix_failure``          — combine graph + amount mutations.
    """
    new_transfer = copy.deepcopy(target_transfer)
    new_recipients = list(recipients)
    new_edges = list(graph_edges)

    if family_id in ("low_velocity_high_graph_risk", "overfit_fix_failure"):
        new_transfer["amount_bucket"] = rng.choice(_TOP_AMOUNT_BUCKETS)
        # Pick a high-reuse recipient if available.
        high_reuse = [r for r in recipients if r["recipient_reuse_degree"] >= 4]
        if high_reuse:
            chosen = high_reuse[rng.randrange(len(high_reuse))]
            new_transfer["recipient_id"] = chosen["recipient_id"]
            # Add an attempted_transfer_to edge so shared_recipient_degree
            # picks up the customer↔recipient link.
            new_edges.append(
                GraphEdge(
                    edge_id=(
                        f"{_NEW_EDGE_PREFIX}"
                        f"{_short_hex(customer['customer_id'] + chosen['recipient_id'])}"
                    ),
                    source_node_id=customer["customer_id"],
                    source_node_type="customer",
                    target_node_id=chosen["recipient_id"],
                    target_node_type="recipient",
                    relationship_type="attempted_transfer_to",
                    first_seen_days_ago=1,
                    event_count=2,
                )
            )
        return new_transfer, new_edges, new_recipients

    if family_id == "score_boundary_cluster":
        new_transfer["amount_bucket"] = rng.choice(_TOP_AMOUNT_BUCKETS)
        new_transfer["event_type"] = "large_transfer_attempt"
        return new_transfer, new_edges, new_recipients

    if family_id == "current_device_mismatch":
        # Flip channel to a less-common one for the customer.
        other = [c for c in DEVICE_CHANNELS if c != target_transfer["channel"]]
        new_transfer["channel"] = other[rng.randrange(len(other))]
        return new_transfer, new_edges, new_recipients

    if family_id == "activity_channel_shift":
        # Flip channel to a different one.
        other = [c for c in DEVICE_CHANNELS if c != target_transfer["channel"]]
        new_transfer["channel"] = other[rng.randrange(len(other))]
        new_transfer["amount_bucket"] = rng.choice(_TOP_AMOUNT_BUCKETS)
        return new_transfer, new_edges, new_recipients

    if family_id == "recent_change_feature_delay":
        # Bump amount to a top bucket so cash_movement_velocity_marker
        # fires alongside the security-event mutation.
        new_transfer["amount_bucket"] = rng.choice(_TOP_AMOUNT_BUCKETS)
        return new_transfer, new_edges, new_recipients

    if family_id == "label_noise_mislearned":
        # Light touch — small amount nudge so behaviour varies but the
        # marker count is intentionally low (some candidates flip, some
        # don't — that's the "noise" the family models).
        new_transfer["amount_bucket"] = rng.choice(AMOUNT_BUCKETS)
        return new_transfer, new_edges, new_recipients

    return new_transfer, new_edges, new_recipients


def mutate_devices_for_family(
    rng: random.Random,
    customer: Customer,
    devices: list[Device],
    family_id: str,
) -> list[Device]:
    """Insert / re-flag devices per family. Returns a NEW list.

    Families targeted:
      * ``current_device_mismatch`` — add a brand-new current device
                                       (first_seen_days_ago=2) and clear
                                       ``is_current_event_device`` on the
                                       previous current device.
      * ``recent_change_feature_delay`` — same: device-novelty fires.
    """
    if family_id not in ("current_device_mismatch", "recent_change_feature_delay"):
        return list(devices)

    out: list[Device] = []
    cust_id = customer["customer_id"]
    for d in devices:
        if d["customer_id"] == cust_id and d["is_current_event_device"]:
            new_d = dict(d)
            new_d["is_current_event_device"] = False
            out.append(new_d)  # type: ignore[arg-type]
        else:
            out.append(d)

    new_device = Device(
        device_id=f"{_NEW_DEVICE_PREFIX}{_short_hex(cust_id + family_id)}",
        customer_id=cust_id,
        device_channel=rng.choice(DEVICE_CHANNELS),
        first_seen_days_ago=2,
        login_count_30d=4,
        is_current_event_device=True,
    )
    out.append(new_device)
    return out


# ---------------------------------------------------------------------------
# Orchestrator — apply per-family mutation, build CandidateState
# ---------------------------------------------------------------------------


def apply_candidate_mutation(
    rng: random.Random,
    base: BaseSearchState,
    target_event_id: str,
    family_id: str,
    *,
    mutation_seed: int,
) -> CandidateState:
    """Produce a deterministic ``CandidateState`` for the target transfer
    under the requested family mutation.

    The returned state references the base for unmutated record types
    (customers, accounts) and carries new lists for the types this
    family touches (devices, recipients, graph_edges, login_sessions,
    security_events, plus the target transfer).
    """
    if family_id not in ALLOWED_FAMILY_IDS:
        raise ValueError(
            f"unknown family_id {family_id!r}; expected one of {list(ALLOWED_FAMILY_IDS)}"
        )

    target = next(
        (t for t in base.transfer_events if t["transfer_event_id"] == target_event_id),
        None,
    )
    if target is None:
        raise ValueError(
            f"target_event_id {target_event_id!r} not found in BaseSearchState "
            f"transfer_events ({len(base.transfer_events)} events)."
        )
    customer = next(
        (c for c in base.customers if c["customer_id"] == target["customer_id"]),
        None,
    )
    if customer is None:
        raise ValueError(
            f"customer {target['customer_id']!r} for target {target_event_id!r} "
            "not in BaseSearchState customers."
        )

    devices = mutate_devices_for_family(rng, customer, list(base.devices), family_id)
    sessions = mutate_login_session_pattern(
        rng,
        customer,
        list(base.login_sessions),
        family_id,
        target_event_time_utc=target["event_time_utc"],
        devices=devices,
    )
    security = mutate_security_event_timing(
        rng,
        customer,
        list(base.security_events),
        family_id,
        target_event_time_utc=target["event_time_utc"],
        devices=devices,
    )
    new_target, edges, recipients = mutate_transfer_context(
        rng,
        customer,
        target,
        list(base.recipients),
        list(base.graph_edges),
        family_id,
    )

    return CandidateState(
        candidate_id=make_candidate_id(target_event_id, family_id, mutation_seed),
        family_id=family_id,
        target_event_id=target_event_id,
        target_transfer=new_target,
        devices=devices,
        recipients=recipients,
        graph_edges=edges,
        login_sessions=sessions,
        security_events=security,
        base=base,
    )


# ---------------------------------------------------------------------------
# Recompute features + regenerate label for a candidate
# ---------------------------------------------------------------------------


def recompute_for_candidate(state: CandidateState) -> FeatureVector:
    """Run the Phase 3 feature pipeline on the candidate's mutated state.

    Returns the single ``FeatureVector`` for ``state.target_transfer``.
    Reuses the base partition's customers + accounts (those record types
    aren't mutated by Phase 6 mutations).
    """
    feats = recompute_feature_vectors(
        transfer_events=[state.target_transfer],
        customers=list(state.base.customers),
        devices=state.devices,
        graph_edges=state.graph_edges,
        login_sessions=state.login_sessions,
        security_events=state.security_events,
    )
    if len(feats) != 1:
        raise RuntimeError(
            f"recompute_feature_vectors returned {len(feats)} vectors; "
            f"expected exactly 1 for candidate {state.candidate_id!r}."
        )
    return feats[0]


def regenerate_labels_for_candidate(
    rng: random.Random, state: CandidateState
) -> LabelGenerationRecord:
    """Run the Phase 2 label generator over a deep copy of the candidate's
    target transfer.

    Used to determine whether the candidate qualifies as
    ``high_risk_synthetic_activity``. The label NEVER feeds into
    scoring — it is consumed by red-team search only to count
    ``valid_high_risk_events_tested``.
    """
    transfers_copy = [copy.deepcopy(state.target_transfer)]
    labels = generate_label_generation_records(
        rng=rng,
        transfer_events=transfers_copy,
        customers=list(state.base.customers),
        devices=state.devices,
        recipients=state.recipients,
        security_events=state.security_events,
    )
    if len(labels) != 1:
        raise RuntimeError(
            f"generate_label_generation_records returned {len(labels)} labels; "
            f"expected exactly 1 for candidate {state.candidate_id!r}."
        )
    return labels[0]
