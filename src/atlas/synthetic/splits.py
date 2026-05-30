"""Customer-level partitioning + locked / drifted holdouts (Phase 2).

Splits customers strictly by ``customer_id`` into five partitions tuned for
the curated public demo::

    train                     0.25
    validation                0.10
    clean_holdout             0.25
    locked_adaptive_holdout   0.20  (locked: red-team / blue-team agents
                                     do not see this set during a round)
    drifted_holdout           0.20  (locked AND has synthetic drift applied
                                     to events; labels regenerated)

The customer set is shuffled once with the supplied RNG and sliced by the
schema fractions. No customer ID appears in two partitions; every customer
is in exactly one partition.

The ``found_adaptive_set`` referenced by ``round_config.yaml`` is NOT
created here — that's owned by the round engine in a later phase.

Drift process (modest, event-only)
----------------------------------
The drifted_holdout partition's events are perturbed before labels are
re-generated. Two safe shifts:

  * ``region_bucket`` of login sessions drifts to a non-home region at
    a higher rate (~22% vs the population's ~8%). Targets the
    ``activity_channel_shift`` and ``current_device_mismatch`` model-
    vulnerability families.
  * ``channel`` of transfer events biases toward ``web`` (~25% of
    transfers re-channeled). Surfaces channel-mix-shift patterns.

Customer-level fields (account_age_days, normal_login_frequency_30d,
etc.) and entity records (accounts, devices, external_accounts, recipients,
graph_edges) are NOT mutated. Drift is event-only by design — it preserves
the customer base intact so Phase 5 can compare baseline vs drifted
performance for the same population.

Persistence boundary
--------------------
This module returns a ``SplitsResult`` with each partition's filtered
records in memory. Component 7 (``scripts/generate_synthetic.py``) writes
each partition to disk:

  * Non-locked partitions (train/validation/clean_holdout) flow into the
    global ``data/synthetic/{entities,events,graph,labels}/*.json`` files.
  * The locked_adaptive_holdout partition lands ONLY under
    ``data/synthetic/holdouts/locked/`` — matching the
    ``.claude/settings.json:8`` read-deny.
  * The drifted_holdout partition lands under
    ``data/synthetic/holdouts/drifted/``; its labels go specifically to
    ``data/synthetic/holdouts/drifted/labels/`` matching
    ``.claude/settings.json:9``.

This module does not write any files itself.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Final

from atlas.synthetic.accounts import Account
from atlas.synthetic.customers import Customer, HOME_REGION_BUCKETS
from atlas.synthetic.devices import Device
from atlas.synthetic.events import (
    LoginSession,
    SecurityEvent,
    TransferEvent,
)
from atlas.synthetic.graph import GraphEdge
from atlas.synthetic.labels import (
    LabelGenerationRecord,
    generate_label_generation_records,
)
from atlas.synthetic.recipients import ExternalAccount, Recipient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PARTITION_NAMES: Final[tuple[str, ...]] = (
    "train",
    "validation",
    "clean_holdout",
    "locked_adaptive_holdout",
    "drifted_holdout",
)

LOCKED_PARTITIONS: Final[frozenset[str]] = frozenset(
    {"locked_adaptive_holdout", "drifted_holdout"}
)

# Drift-process constants. Tuned to be modest but visible at population
# scale — bumps the drift-marker fire rates without rewriting the customer
# distribution.
_DRIFTED_REGION_DRIFT_RATE: Final[float] = 0.22
_DRIFTED_CHANNEL_BIAS_TO_WEB_RATE: Final[float] = 0.25
_DRIFT_TARGET_CHANNEL: Final[str] = "web"

# Minimum customer count for a meaningful 5-way split. Below this, the
# fraction math collapses (a 10% partition of <10 customers rounds to 0).
_MIN_SUPPORTED_CUSTOMER_COUNT: Final[int] = 10

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SplitFractions:
    """Per-partition customer fractions. Must sum to 1.0."""

    train: float = 0.25
    validation: float = 0.10
    clean_holdout: float = 0.25
    locked_adaptive_holdout: float = 0.20
    drifted_holdout: float = 0.20

    def total(self) -> float:
        return (
            self.train
            + self.validation
            + self.clean_holdout
            + self.locked_adaptive_holdout
            + self.drifted_holdout
        )

    def validate(self) -> None:
        total = self.total()
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"split fractions must sum to 1.0, got {total}")
        for name in PARTITION_NAMES:
            v = getattr(self, name)
            if not (0.0 < v < 1.0):
                raise ValueError(f"partition {name!r} fraction must be in (0, 1), got {v}")


@dataclass
class PartitionData:
    """All records belonging to one customer-level partition."""

    name: str
    locked: bool
    customer_ids: list[str]
    customers: list[Customer]
    accounts: list[Account]
    devices: list[Device]
    external_accounts: list[ExternalAccount]
    graph_edges: list[GraphEdge]
    login_sessions: list[LoginSession]
    security_events: list[SecurityEvent]
    transfer_events: list[TransferEvent]
    label_records: list[LabelGenerationRecord]
    drift_applied: bool = False


@dataclass
class SplitsResult:
    """Result of partitioning + drift application."""

    partitions: dict[str, PartitionData]
    customer_split_membership: dict[str, str]
    fractions: SplitFractions = field(default_factory=SplitFractions)


# ---------------------------------------------------------------------------
# Partitioning
# ---------------------------------------------------------------------------


def partition_customers(
    rng: random.Random,
    customers: list[Customer],
    fractions: SplitFractions | None = None,
) -> dict[str, list[str]]:
    """Shuffle customers and partition by ``customer_id`` per ``fractions``.

    Uses floor-then-remainder math so every customer ends up in exactly one
    partition even when the fractions do not divide evenly. The drifted
    partition absorbs the remainder so it may end up slightly larger than
    its nominal fraction — train / validation / clean / locked are exact.

    Args:
        rng: Seeded ``random.Random``. Shuffle order is RNG-deterministic.
        customers: Customer list (unmodified).
        fractions: Override of the schema's default fractions. Must sum to 1.0.

    Returns:
        ``{partition_name: [customer_id, ...]}`` covering every customer
        exactly once.
    """
    if fractions is None:
        fractions = SplitFractions()
    fractions.validate()

    n = len(customers)
    if n < _MIN_SUPPORTED_CUSTOMER_COUNT:
        raise ValueError(
            f"need at least {_MIN_SUPPORTED_CUSTOMER_COUNT} customers for a 5-way split, "
            f"got {n}"
        )

    customer_ids = [c["customer_id"] for c in customers]
    shuffled = list(customer_ids)
    rng.shuffle(shuffled)

    train_n = int(n * fractions.train)
    val_n = int(n * fractions.validation)
    clean_n = int(n * fractions.clean_holdout)
    locked_n = int(n * fractions.locked_adaptive_holdout)
    # Drifted absorbs the remainder so totals always equal n.
    drifted_n = n - train_n - val_n - clean_n - locked_n
    if drifted_n < 1:
        raise ValueError(
            f"drifted_holdout would have {drifted_n} customers; check fractions and count"
        )

    boundaries = [
        0,
        train_n,
        train_n + val_n,
        train_n + val_n + clean_n,
        train_n + val_n + clean_n + locked_n,
        n,
    ]
    return {
        "train": shuffled[boundaries[0] : boundaries[1]],
        "validation": shuffled[boundaries[1] : boundaries[2]],
        "clean_holdout": shuffled[boundaries[2] : boundaries[3]],
        "locked_adaptive_holdout": shuffled[boundaries[3] : boundaries[4]],
        "drifted_holdout": shuffled[boundaries[4] : boundaries[5]],
    }


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def _filter_records_by_customers(
    customer_ids: set[str],
    accounts: list[Account],
    devices: list[Device],
    external_accounts: list[ExternalAccount],
    graph_edges: list[GraphEdge],
    login_sessions: list[LoginSession],
    security_events: list[SecurityEvent],
    transfer_events: list[TransferEvent],
    label_records: list[LabelGenerationRecord],
) -> dict[str, list]:
    """Filter every customer-bound record list to entries in ``customer_ids``."""
    p_accounts = [a for a in accounts if a["customer_id"] in customer_ids]
    p_devices = [d for d in devices if d["customer_id"] in customer_ids]
    p_external = [e for e in external_accounts if e["customer_id"] in customer_ids]
    # Graph edges where the source is one of these customers. Edges are
    # always source-customer-rooted in Phase 2 (uses_device, attempted_transfer_to).
    p_edges = [g for g in graph_edges if g["source_node_id"] in customer_ids]
    p_sessions = [s for s in login_sessions if s["customer_id"] in customer_ids]
    p_security = [s for s in security_events if s["customer_id"] in customer_ids]
    p_transfers = [t for t in transfer_events if t["customer_id"] in customer_ids]
    # Labels filtered by transfer event_id ∈ partition's transfers.
    p_tx_event_ids = {t["transfer_event_id"] for t in p_transfers}
    p_labels = [l for l in label_records if l["event_id"] in p_tx_event_ids]
    return {
        "accounts": p_accounts,
        "devices": p_devices,
        "external_accounts": p_external,
        "graph_edges": p_edges,
        "login_sessions": p_sessions,
        "security_events": p_security,
        "transfer_events": p_transfers,
        "label_records": p_labels,
    }


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def apply_drift_to_events(
    rng: random.Random,
    customers: list[Customer],
    login_sessions: list[LoginSession],
    transfer_events: list[TransferEvent],
) -> tuple[list[LoginSession], list[TransferEvent]]:
    """Apply modest synthetic drift to a partition's events.

    Returns NEW lists (shallow record copies) — callers receive the drifted
    view without mutating the originals.

    Drift dimensions:
      * region_bucket of login sessions drifts to a non-home region at
        ``_DRIFTED_REGION_DRIFT_RATE`` (~22%).
      * channel of transfer events biases to ``web`` at
        ``_DRIFTED_CHANNEL_BIAS_TO_WEB_RATE`` (~25%).
    """
    customer_by_id = {c["customer_id"]: c for c in customers}

    drifted_sessions: list[LoginSession] = []
    for session in login_sessions:
        new_session: LoginSession = dict(session)  # type: ignore[assignment]
        if rng.random() < _DRIFTED_REGION_DRIFT_RATE:
            customer = customer_by_id.get(session["customer_id"])
            if customer is not None:
                home = customer["home_region_bucket"]
                candidates = tuple(r for r in HOME_REGION_BUCKETS if r != home)
                new_session["region_bucket"] = rng.choice(candidates)
        drifted_sessions.append(new_session)

    drifted_transfers: list[TransferEvent] = []
    for tx in transfer_events:
        new_tx: TransferEvent = dict(tx)  # type: ignore[assignment]
        if rng.random() < _DRIFTED_CHANNEL_BIAS_TO_WEB_RATE:
            new_tx["channel"] = _DRIFT_TARGET_CHANNEL
        drifted_transfers.append(new_tx)

    return drifted_sessions, drifted_transfers


# ---------------------------------------------------------------------------
# Build (top-level)
# ---------------------------------------------------------------------------


def build_splits(
    rng: random.Random,
    customers: list[Customer],
    accounts: list[Account],
    devices: list[Device],
    recipients: list[Recipient],
    external_accounts: list[ExternalAccount],
    graph_edges: list[GraphEdge],
    login_sessions: list[LoginSession],
    security_events: list[SecurityEvent],
    transfer_events: list[TransferEvent],
    label_records: list[LabelGenerationRecord],
    fractions: SplitFractions | None = None,
) -> SplitsResult:
    """Top-level: partition + filter + (drift + relabel for drifted_holdout).

    Args:
        rng: Seeded ``random.Random``. Used for the customer shuffle, the
            drift application, and the drifted-partition label regeneration.
        customers...label_records: Full population data from earlier
            generators.
        fractions: Override partition fractions (default 60/10/10/10/10).

    Returns:
        ``SplitsResult`` with five named partitions and a customer→partition
        membership map.
    """
    if fractions is None:
        fractions = SplitFractions()

    # --- Partition customer IDs ---
    partition_to_ids = partition_customers(rng, customers, fractions)

    # Build customer→partition lookup for the manifest map.
    customer_split_membership: dict[str, str] = {}
    for pname, ids in partition_to_ids.items():
        for cid in ids:
            customer_split_membership[cid] = pname

    customer_by_id = {c["customer_id"]: c for c in customers}

    partitions: dict[str, PartitionData] = {}

    # --- Build each partition ---
    for pname in PARTITION_NAMES:
        ids_list = partition_to_ids[pname]
        ids_set = set(ids_list)
        p_customers = [customer_by_id[cid] for cid in ids_list]

        filtered = _filter_records_by_customers(
            customer_ids=ids_set,
            accounts=accounts,
            devices=devices,
            external_accounts=external_accounts,
            graph_edges=graph_edges,
            login_sessions=login_sessions,
            security_events=security_events,
            transfer_events=transfer_events,
            label_records=label_records,
        )

        drift_applied = False
        p_sessions = filtered["login_sessions"]
        p_transfers = filtered["transfer_events"]
        p_labels = filtered["label_records"]
        p_security = filtered["security_events"]

        if pname == "drifted_holdout":
            # Apply drift to event streams, then regenerate labels using
            # the drifted events. The label generator mutates p_transfers
            # in place to set the new synthetic_truth_label per record.
            p_sessions, p_transfers = apply_drift_to_events(
                rng, p_customers, p_sessions, p_transfers
            )
            # Deep copy p_security because labels.py reads from it but does
            # not mutate. Shallow-safe but copy keeps us from accidentally
            # cross-referencing the global list later.
            p_security_copy = [dict(s) for s in p_security]  # type: ignore[arg-type]
            p_labels = generate_label_generation_records(
                rng=rng,
                transfer_events=p_transfers,
                customers=p_customers,
                devices=filtered["devices"],
                recipients=recipients,
                security_events=p_security_copy,  # type: ignore[arg-type]
            )
            drift_applied = True

        partitions[pname] = PartitionData(
            name=pname,
            locked=(pname in LOCKED_PARTITIONS),
            customer_ids=list(ids_list),
            customers=p_customers,
            accounts=filtered["accounts"],
            devices=filtered["devices"],
            external_accounts=filtered["external_accounts"],
            graph_edges=filtered["graph_edges"],
            login_sessions=p_sessions,
            security_events=p_security,
            transfer_events=p_transfers,
            label_records=p_labels,
            drift_applied=drift_applied,
        )

    return SplitsResult(
        partitions=partitions,
        customer_split_membership=customer_split_membership,
        fractions=fractions,
    )


# ---------------------------------------------------------------------------
# Helpers for callers / tests
# ---------------------------------------------------------------------------


def assert_no_customer_leak(result: SplitsResult) -> None:
    """Raise if any customer_id appears in more than one partition."""
    seen: dict[str, str] = {}
    for pname, partition in result.partitions.items():
        for cid in partition.customer_ids:
            if cid in seen:
                raise ValueError(
                    f"customer leak: {cid!r} appears in both {seen[cid]!r} and {pname!r}"
                )
            seen[cid] = pname
