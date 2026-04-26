"""Synthetic relationship-graph generator (Phase 2).

Emits raw ``GraphEdge`` records for two relationship types:

  * ``uses_device``           — customer → device, exactly one per device.
                                ``event_count`` mirrors the device's
                                ``login_count_30d``; ``first_seen_days_ago``
                                mirrors the device's first-seen.
  * ``attempted_transfer_to`` — customer → recipient. The recipient's
                                ``recipient_reuse_degree`` is honored as a
                                hard target: the recipient is wired to
                                exactly ``min(reuse_degree, customer_count)``
                                distinct customers, sampled uniformly via
                                ``rng.sample``.

Phase-3-derived "shared" edge kinds (``shared_device``, ``shared_recipient``,
``shared_external_account``, ``shared_region``) are NOT emitted here. They
are computed graph features owned by the Phase 3 feature calculator.

Determinism: ``generate_graph_edges`` consumes only from the supplied RNG.
"""

from __future__ import annotations

import random
from typing import Final, TypedDict

from atlas.synthetic.customers import Customer
from atlas.synthetic.devices import Device
from atlas.synthetic.recipients import Recipient

# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------


class GraphEdge(TypedDict):
    """Edge between two synthetic nodes in the relationship graph."""

    edge_id: str
    source_node_id: str
    source_node_type: str
    target_node_id: str
    target_node_type: str
    relationship_type: str
    first_seen_days_ago: int
    event_count: int


# ---------------------------------------------------------------------------
# Bucketed enums
# ---------------------------------------------------------------------------

EDGE_ID_PREFIX: Final[str] = "edge_"

# Phase 2 raw edge kinds. Bible §11 / schema-config also lists derived
# (Phase 3) kinds — those are not emitted here.
RAW_EDGE_RELATIONSHIPS: Final[tuple[str, ...]] = (
    "uses_device",
    "attempted_transfer_to",
)

NODE_TYPES: Final[tuple[str, ...]] = ("customer", "device", "recipient")

_GRAPH_EDGE_KEYS: Final[frozenset[str]] = frozenset(
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

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def make_edge_id(index: int) -> str:
    if index < 1:
        raise ValueError("edge index must be >= 1")
    return f"{EDGE_ID_PREFIX}{index:06d}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _assert_graph_edge_shape(record: GraphEdge) -> None:
    keys = set(record.keys())
    if keys != _GRAPH_EDGE_KEYS:
        missing = _GRAPH_EDGE_KEYS - keys
        extra = keys - _GRAPH_EDGE_KEYS
        raise ValueError(
            f"graph edge shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["edge_id"].startswith(EDGE_ID_PREFIX):
        raise ValueError(f"edge_id missing synthetic prefix: {record['edge_id']!r}")
    if record["source_node_type"] not in NODE_TYPES:
        raise ValueError(f"source_node_type not in allow-list: {record['source_node_type']!r}")
    if record["target_node_type"] not in NODE_TYPES:
        raise ValueError(f"target_node_type not in allow-list: {record['target_node_type']!r}")
    if record["relationship_type"] not in RAW_EDGE_RELATIONSHIPS:
        raise ValueError(
            f"relationship_type not in Phase 2 raw allow-list: {record['relationship_type']!r}"
        )
    if record["first_seen_days_ago"] < 0:
        raise ValueError(f"first_seen_days_ago must be >= 0: {record['first_seen_days_ago']}")
    if record["event_count"] < 0:
        raise ValueError(f"event_count must be >= 0: {record['event_count']}")


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------


def generate_graph_edges(
    rng: random.Random,
    customers: list[Customer],
    devices: list[Device],
    recipients: list[Recipient],
) -> list[GraphEdge]:
    """Generate raw graph edges from the entity population.

    Two passes:
      1. ``uses_device`` — one edge per device, mirroring device metadata.
      2. ``attempted_transfer_to`` — for each recipient, sample
         ``min(reuse_degree, len(customers))`` distinct customers
         uniformly via ``rng.sample`` and emit one edge per pair.

    Args:
        rng: Seeded ``random.Random``. Caller owns seeding.
        customers: Customer list (unmodified). Used as the sample population
            for recipient links.
        devices: Device list (unmodified).
        recipients: Recipient pool. Each recipient's ``recipient_reuse_degree``
            controls how many customer links it receives.

    Returns:
        List of ``GraphEdge`` TypedDicts with global 1-based ``edge_id``s.
    """
    edges: list[GraphEdge] = []
    next_index = 0

    # --- Pass 1: customer → device (uses_device) ---
    for device in devices:
        next_index += 1
        edge: GraphEdge = {
            "edge_id": make_edge_id(next_index),
            "source_node_id": device["customer_id"],
            "source_node_type": "customer",
            "target_node_id": device["device_id"],
            "target_node_type": "device",
            "relationship_type": "uses_device",
            "first_seen_days_ago": device["first_seen_days_ago"],
            "event_count": device["login_count_30d"],
        }
        _assert_graph_edge_shape(edge)
        edges.append(edge)

    # --- Pass 2: customer → recipient (attempted_transfer_to) ---
    customer_count = len(customers)
    if customer_count == 0:
        return edges

    for recipient in recipients:
        target_links = min(recipient["recipient_reuse_degree"], customer_count)
        # Uniform-without-replacement: every recipient is wired to exactly
        # `target_links` distinct customers. Phase 6+ red-team can refine
        # this to weight by customer transfer frequency if needed.
        chosen = rng.sample(customers, k=target_links)

        # Cap edge first-seen at the recipient's first-seen (an edge can't
        # be older than the recipient itself).
        recipient_first_seen = recipient["first_seen_days_ago"]

        for customer in chosen:
            next_index += 1
            edge_first_seen = rng.randint(1, max(1, recipient_first_seen))
            # Edge event_count: bounded by the customer's transfer activity.
            # A zero-transfer customer still gets event_count = 1 because
            # the edge represents at least one synthetic transfer attempt.
            tx_freq = customer["normal_transfer_frequency_30d"]
            edge_event_count = rng.randint(1, max(1, tx_freq // 2 + 1))
            edge_record: GraphEdge = {
                "edge_id": make_edge_id(next_index),
                "source_node_id": customer["customer_id"],
                "source_node_type": "customer",
                "target_node_id": recipient["recipient_id"],
                "target_node_type": "recipient",
                "relationship_type": "attempted_transfer_to",
                "first_seen_days_ago": edge_first_seen,
                "event_count": edge_event_count,
            }
            _assert_graph_edge_shape(edge_record)
            edges.append(edge_record)

    return edges
