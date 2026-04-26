"""Synthetic recipient and external-account generators (Phase 2).

Per architecture-doc §1.5, this module owns BOTH ``Recipient`` records
(shared pool, no customer binding) and ``ExternalAccount`` records
(customer-bound). The two record types are intentionally co-located: both
participate in the relationship graph that component 4 (graph.py) builds,
and they share the "linked-to-the-customer-population" generation pattern.

Recipients are a SHARED pool. Each recipient has a ``recipient_reuse_degree``
that targets the number of distinct customers that will eventually link to
it via graph edges (component 4). The risk bucket is derived from the
combination of degree and recency:

    high_synthetic_graph_risk : reuse_degree >= 7
                              OR (reuse_degree >= 4 AND first_seen <= 10 days)
    medium                    : reuse_degree >= 4
                              OR (reuse_degree >= 2 AND first_seen <= 30 days)
    low                       : everything else

This produces a distribution where a small minority of "hot" recipients
carry elevated graph risk — the seed pattern Phase 6's
``low_velocity_high_graph_risk`` model-vulnerability family searches against.

External accounts are customer-bound (0–2 per customer). Their risk bucket
is independent of recipients but uses the same three-bucket allow-list to
keep downstream label / feature logic uniform.

Determinism: both generators consume only from the supplied RNG.
"""

from __future__ import annotations

import random
from typing import Final, TypedDict

from atlas.synthetic.customers import Customer

# ---------------------------------------------------------------------------
# Record shapes
# ---------------------------------------------------------------------------


class Recipient(TypedDict):
    """Synthetic transfer recipient. Shared across customers via graph edges."""

    recipient_id: str
    first_seen_days_ago: int
    recipient_reuse_degree: int
    recipient_risk_bucket: str


class ExternalAccount(TypedDict):
    """Synthetic external account linked to a customer profile."""

    external_account_id: str
    customer_id: str
    linked_days_ago: int
    verification_method: str
    external_account_risk_bucket: str


# ---------------------------------------------------------------------------
# Bucketed enums
# ---------------------------------------------------------------------------

RECIPIENT_ID_PREFIX: Final[str] = "recip_"
EXTERNAL_ACCOUNT_ID_PREFIX: Final[str] = "extacct_"

RECIPIENT_RISK_BUCKETS: Final[tuple[str, ...]] = (
    "low",
    "medium",
    "high_synthetic_graph_risk",
)

EXTERNAL_ACCOUNT_RISK_BUCKETS: Final[tuple[str, ...]] = (
    "low",
    "medium",
    "high_synthetic_graph_risk",
)

VERIFICATION_METHODS: Final[tuple[str, ...]] = (
    "synthetic_verified",
    "synthetic_pending_review",
    "synthetic_microdeposit",
)
_VERIFICATION_WEIGHTS: Final[tuple[float, ...]] = (0.70, 0.20, 0.10)

# Per-customer external-account count distribution.
_EXT_ACCT_COUNT_CHOICES: Final[tuple[int, ...]] = (0, 1, 2)
_EXT_ACCT_COUNT_WEIGHTS: Final[tuple[float, ...]] = (0.30, 0.60, 0.10)

# External-account risk weights — most are low, few medium, very few high.
_EXT_ACCT_RISK_WEIGHTS: Final[tuple[float, ...]] = (0.78, 0.18, 0.04)

# Recipient reuse-degree distribution (target customer-link count).
#  bucket 1: degree = 1                       (single-customer recipient)
#  bucket 2: degree = 2..3                    (small share)
#  bucket 3: degree = 4..6                    (multi-customer recipient)
#  bucket 4: degree = 7..15                   (hot recipient, often risky)
_RECIPIENT_DEGREE_BUCKET_WEIGHTS: Final[tuple[float, ...]] = (
    0.70,
    0.20,
    0.08,
    0.02,
)

_RECIPIENT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "recipient_id",
        "first_seen_days_ago",
        "recipient_reuse_degree",
        "recipient_risk_bucket",
    }
)

_EXTERNAL_ACCOUNT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "external_account_id",
        "customer_id",
        "linked_days_ago",
        "verification_method",
        "external_account_risk_bucket",
    }
)


# ---------------------------------------------------------------------------
# Public ID helpers
# ---------------------------------------------------------------------------


def make_recipient_id(index: int) -> str:
    if index < 1:
        raise ValueError("recipient index must be >= 1")
    return f"{RECIPIENT_ID_PREFIX}{index:06d}"


def make_external_account_id(index: int) -> str:
    if index < 1:
        raise ValueError("external_account index must be >= 1")
    return f"{EXTERNAL_ACCOUNT_ID_PREFIX}{index:06d}"


# ---------------------------------------------------------------------------
# Recipient sampling
# ---------------------------------------------------------------------------


def _draw_recipient_reuse_degree(rng: random.Random) -> int:
    bucket = rng.choices(
        (1, 2, 3, 4), weights=_RECIPIENT_DEGREE_BUCKET_WEIGHTS, k=1
    )[0]
    if bucket == 1:
        return 1
    if bucket == 2:
        return rng.randint(2, 3)
    if bucket == 3:
        return rng.randint(4, 6)
    return rng.randint(7, 15)


def _draw_recipient_first_seen(rng: random.Random, reuse_degree: int) -> int:
    # Hot recipients (degree >= 7) skew recent — that's the synthetic risk
    # pattern. Cooler recipients are sampled across the full plausible
    # tenure range.
    if reuse_degree >= 7:
        return rng.randint(1, 60)
    return rng.randint(1, 1500)


def _classify_recipient_risk(reuse_degree: int, first_seen_days_ago: int) -> str:
    if reuse_degree >= 7 or (reuse_degree >= 4 and first_seen_days_ago <= 10):
        return "high_synthetic_graph_risk"
    if reuse_degree >= 4 or (reuse_degree >= 2 and first_seen_days_ago <= 30):
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# External-account sampling
# ---------------------------------------------------------------------------


def _draw_external_account_count(rng: random.Random) -> int:
    return rng.choices(
        _EXT_ACCT_COUNT_CHOICES, weights=_EXT_ACCT_COUNT_WEIGHTS, k=1
    )[0]


def _draw_verification_method(rng: random.Random) -> str:
    return rng.choices(VERIFICATION_METHODS, weights=_VERIFICATION_WEIGHTS, k=1)[0]


def _draw_external_account_risk(rng: random.Random) -> str:
    return rng.choices(
        EXTERNAL_ACCOUNT_RISK_BUCKETS, weights=_EXT_ACCT_RISK_WEIGHTS, k=1
    )[0]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _assert_recipient_shape(record: Recipient) -> None:
    keys = set(record.keys())
    if keys != _RECIPIENT_KEYS:
        missing = _RECIPIENT_KEYS - keys
        extra = keys - _RECIPIENT_KEYS
        raise ValueError(
            f"recipient record shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["recipient_id"].startswith(RECIPIENT_ID_PREFIX):
        raise ValueError(f"recipient_id missing synthetic prefix: {record['recipient_id']!r}")
    if record["first_seen_days_ago"] < 1:
        raise ValueError(f"first_seen_days_ago must be >= 1: {record['first_seen_days_ago']}")
    if record["recipient_reuse_degree"] < 1:
        raise ValueError(f"recipient_reuse_degree must be >= 1: {record['recipient_reuse_degree']}")
    if record["recipient_risk_bucket"] not in RECIPIENT_RISK_BUCKETS:
        raise ValueError(
            f"recipient_risk_bucket not in allow-list: {record['recipient_risk_bucket']!r}"
        )


def _assert_external_account_shape(record: ExternalAccount) -> None:
    keys = set(record.keys())
    if keys != _EXTERNAL_ACCOUNT_KEYS:
        missing = _EXTERNAL_ACCOUNT_KEYS - keys
        extra = keys - _EXTERNAL_ACCOUNT_KEYS
        raise ValueError(
            f"external_account record shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["external_account_id"].startswith(EXTERNAL_ACCOUNT_ID_PREFIX):
        raise ValueError(
            f"external_account_id missing synthetic prefix: {record['external_account_id']!r}"
        )
    if not record["customer_id"].startswith("cust_"):
        raise ValueError(f"customer_id missing synthetic prefix: {record['customer_id']!r}")
    if record["linked_days_ago"] < 0:
        raise ValueError(f"linked_days_ago must be >= 0: {record['linked_days_ago']}")
    if record["verification_method"] not in VERIFICATION_METHODS:
        raise ValueError(f"verification_method not in allow-list: {record['verification_method']!r}")
    if record["external_account_risk_bucket"] not in EXTERNAL_ACCOUNT_RISK_BUCKETS:
        raise ValueError(
            f"external_account_risk_bucket not in allow-list: {record['external_account_risk_bucket']!r}"
        )


# ---------------------------------------------------------------------------
# Public generators
# ---------------------------------------------------------------------------


def generate_recipients(rng: random.Random, customer_count: int) -> list[Recipient]:
    """Generate a shared recipient pool sized to the customer population.

    Pool size equals ``customer_count``, which combined with the reuse-degree
    distribution yields ~1.5 customer→recipient edges per customer on
    average. Component 4 (graph.py) honors each recipient's
    ``recipient_reuse_degree`` when wiring graph edges.

    Args:
        rng: Seeded ``random.Random``. Caller owns seeding.
        customer_count: Number of customers in the population. Pool size
            equals this value (>= 1).

    Returns:
        List of ``Recipient`` TypedDicts with global 1-based IDs.
    """
    if customer_count < 1:
        raise ValueError(f"customer_count must be >= 1, got {customer_count}")

    pool: list[Recipient] = []
    for idx in range(1, customer_count + 1):
        reuse_degree = _draw_recipient_reuse_degree(rng)
        first_seen = _draw_recipient_first_seen(rng, reuse_degree)
        risk = _classify_recipient_risk(reuse_degree, first_seen)
        record: Recipient = {
            "recipient_id": make_recipient_id(idx),
            "first_seen_days_ago": first_seen,
            "recipient_reuse_degree": reuse_degree,
            "recipient_risk_bucket": risk,
        }
        _assert_recipient_shape(record)
        pool.append(record)
    return pool


def generate_external_accounts(
    rng: random.Random, customers: list[Customer]
) -> list[ExternalAccount]:
    """Generate 0–2 external accounts per customer.

    ``linked_days_ago`` is bounded by the customer's account age — an
    external account cannot have been linked before the customer's account
    existed.

    Args:
        rng: Seeded ``random.Random``. Caller owns seeding.
        customers: Customer list (unmodified).

    Returns:
        Flat list of ``ExternalAccount`` TypedDicts with global 1-based IDs.
        Length is data-dependent (some customers contribute 0).
    """
    accounts: list[ExternalAccount] = []
    next_index = 0

    for customer in customers:
        count = _draw_external_account_count(rng)
        max_linked = max(1, customer["account_age_days"])
        for _ in range(count):
            next_index += 1
            verification = _draw_verification_method(rng)
            risk = _draw_external_account_risk(rng)
            linked_days = rng.randint(1, max_linked)
            record: ExternalAccount = {
                "external_account_id": make_external_account_id(next_index),
                "customer_id": customer["customer_id"],
                "linked_days_ago": linked_days,
                "verification_method": verification,
                "external_account_risk_bucket": risk,
            }
            _assert_external_account_shape(record)
            accounts.append(record)
    return accounts
