"""Synthetic account generator (Phase 2).

Emits ``Account`` records 1:1 with ``Customer`` records. Account age tracks
customer age (``opened_days_ago == customer.account_age_days``) so that
later transfer-event timestamps remain consistent with the customer's
synthetic history.

Determinism: ``generate_accounts`` consumes only from the supplied
``random.Random`` and the customer list. No global state, no time reads.
"""

from __future__ import annotations

import random
from typing import Final, TypedDict

from atlas.synthetic.customers import Customer

# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------


class Account(TypedDict):
    """Synthetic bank account attached to a customer."""

    account_id: str
    customer_id: str
    account_type: str
    opened_days_ago: int
    available_balance_bucket: str
    account_status: str


# ---------------------------------------------------------------------------
# Bucketed enums
# ---------------------------------------------------------------------------

ACCOUNT_ID_PREFIX: Final[str] = "acct_"

ACCOUNT_TYPES: Final[tuple[str, ...]] = ("checking", "savings")
_ACCOUNT_TYPE_WEIGHTS: Final[tuple[float, ...]] = (0.7, 0.3)

# Ten safe balance buckets. Never a real currency amount.
BALANCE_BUCKETS: Final[tuple[str, ...]] = tuple(
    f"balance_bucket_{i:02d}" for i in range(1, 11)
)

ACCOUNT_STATUSES: Final[tuple[str, ...]] = ("active", "limited", "closed")
_ACCOUNT_STATUS_WEIGHTS: Final[tuple[float, ...]] = (0.92, 0.06, 0.02)

_ACCOUNT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "account_id",
        "customer_id",
        "account_type",
        "opened_days_ago",
        "available_balance_bucket",
        "account_status",
    }
)

# ---------------------------------------------------------------------------
# Public ID helpers
# ---------------------------------------------------------------------------


def make_account_id(index: int) -> str:
    """Render a synthetic account ID for ``index`` (1-based)."""
    if index < 1:
        raise ValueError("account index must be >= 1")
    return f"{ACCOUNT_ID_PREFIX}{index:06d}"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _assert_account_shape(record: Account) -> None:
    keys = set(record.keys())
    if keys != _ACCOUNT_KEYS:
        missing = _ACCOUNT_KEYS - keys
        extra = keys - _ACCOUNT_KEYS
        raise ValueError(
            f"account record shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    aid = record["account_id"]
    if not aid.startswith(ACCOUNT_ID_PREFIX):
        raise ValueError(f"account_id missing synthetic prefix: {aid!r}")
    if not record["customer_id"].startswith("cust_"):
        raise ValueError(f"customer_id missing synthetic prefix: {record['customer_id']!r}")
    if record["account_type"] not in ACCOUNT_TYPES:
        raise ValueError(f"account_type not in allow-list: {record['account_type']!r}")
    if record["available_balance_bucket"] not in BALANCE_BUCKETS:
        raise ValueError(
            f"available_balance_bucket not in allow-list: {record['available_balance_bucket']!r}"
        )
    if record["account_status"] not in ACCOUNT_STATUSES:
        raise ValueError(f"account_status not in allow-list: {record['account_status']!r}")
    if record["opened_days_ago"] < 0:
        raise ValueError(f"opened_days_ago must be >= 0: {record['opened_days_ago']}")


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------


def generate_accounts(rng: random.Random, customers: list[Customer]) -> list[Account]:
    """Generate one ``Account`` per customer, in input order.

    Account ID is the customer's 1-based position in the input list. Account
    age tracks the customer's age so later transfer events cannot reference
    a transfer older than the account itself.

    Args:
        rng: Seeded ``random.Random``. Caller owns seeding.
        customers: Customer list (unmodified). Order is preserved in output.

    Returns:
        Length-equal list of ``Account`` TypedDicts. Determinism follows
        from the RNG and customer order.
    """
    accounts: list[Account] = []
    seen_customer_ids: set[str] = set()

    for idx, customer in enumerate(customers, start=1):
        cid = customer["customer_id"]
        if cid in seen_customer_ids:
            raise ValueError(f"duplicate customer_id in input: {cid!r}")
        seen_customer_ids.add(cid)

        account_type = rng.choices(
            ACCOUNT_TYPES, weights=_ACCOUNT_TYPE_WEIGHTS, k=1
        )[0]
        balance_bucket = rng.choice(BALANCE_BUCKETS)
        status = rng.choices(
            ACCOUNT_STATUSES, weights=_ACCOUNT_STATUS_WEIGHTS, k=1
        )[0]

        record: Account = {
            "account_id": make_account_id(idx),
            "customer_id": cid,
            "account_type": account_type,
            "opened_days_ago": customer["account_age_days"],
            "available_balance_bucket": balance_bucket,
            "account_status": status,
        }
        _assert_account_shape(record)
        accounts.append(record)

    return accounts
