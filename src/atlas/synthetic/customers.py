"""Synthetic customer generator (Phase 2).

Emits ``Customer`` records that match the fixture/architecture-doc shape:

    {customer_id, customer_segment, home_region_bucket, account_age_days,
     normal_login_frequency_30d, normal_transfer_frequency_30d,
     synthetic_base_risk, created_from_seed}

Determinism: ``generate_customers`` consumes only from the supplied
``random.Random`` instance and the seed integer. No global state, no
``datetime.now()``, no environment reads.

Synthetic-only: every value is either an integer count, a float in [0, 1],
or one of the bucketed enums declared at module level. There is no free-form
string anywhere; the safety scanner's PII regexes cannot match output of
this module.
"""

from __future__ import annotations

import random
from typing import Final, TypedDict

# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------


class Customer(TypedDict):
    """Synthetic customer profile. JSON-serializable as-is."""

    customer_id: str
    customer_segment: str
    home_region_bucket: str
    account_age_days: int
    normal_login_frequency_30d: int
    normal_transfer_frequency_30d: int
    synthetic_base_risk: float
    created_from_seed: int


# ---------------------------------------------------------------------------
# Bucketed enums (no free-form strings emitted)
# ---------------------------------------------------------------------------

CUSTOMER_ID_PREFIX: Final[str] = "cust_"

CUSTOMER_SEGMENTS: Final[tuple[str, ...]] = (
    "digital_primary",
    "low_digital_activity",
    "mixed_channel",
    "new_customer",
    "high_value",
)

# Twelve safe region buckets. Bucketed labels — never a real city / country.
HOME_REGION_BUCKETS: Final[tuple[str, ...]] = tuple(
    f"region_{i:02d}" for i in range(1, 13)
)

# Required keys for runtime shape validation. Mirrors Customer's TypedDict
# fields one-for-one. Any drift here that is not also reflected in the
# TypedDict above will fail the validator.
_CUSTOMER_KEYS: Final[frozenset[str]] = frozenset(
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

# Plausibility bounds. Used both for sampling and for runtime assertions.
_ACCOUNT_AGE_MIN_DAYS: Final[int] = 7
_ACCOUNT_AGE_MAX_DAYS: Final[int] = 4500
_RISK_MIN: Final[float] = 0.01
_RISK_MAX: Final[float] = 0.95

# ---------------------------------------------------------------------------
# Public ID helpers
# ---------------------------------------------------------------------------


def make_customer_id(index: int) -> str:
    """Render a synthetic customer ID for ``index`` (1-based)."""
    if index < 1:
        raise ValueError("customer index must be >= 1")
    return f"{CUSTOMER_ID_PREFIX}{index:06d}"


# ---------------------------------------------------------------------------
# Per-segment sampling
# ---------------------------------------------------------------------------


def _draw_account_age_days(rng: random.Random, segment: str) -> int:
    if segment == "new_customer":
        return rng.randint(_ACCOUNT_AGE_MIN_DAYS, 180)
    if segment == "low_digital_activity":
        return rng.randint(90, 2500)
    return rng.randint(180, 3000)


def _draw_login_freq_30d(rng: random.Random, segment: str) -> int:
    if segment == "digital_primary":
        return rng.randint(12, 30)
    if segment == "low_digital_activity":
        return rng.randint(1, 6)
    if segment == "mixed_channel":
        return rng.randint(6, 15)
    if segment == "new_customer":
        return rng.randint(4, 15)
    if segment == "high_value":
        return rng.randint(8, 25)
    raise ValueError(f"unknown segment: {segment!r}")


def _draw_transfer_freq_30d(rng: random.Random, segment: str) -> int:
    if segment == "digital_primary":
        return rng.randint(1, 6)
    if segment == "low_digital_activity":
        return rng.randint(0, 2)
    if segment == "mixed_channel":
        return rng.randint(1, 4)
    if segment == "new_customer":
        return rng.randint(0, 3)
    if segment == "high_value":
        return rng.randint(2, 8)
    raise ValueError(f"unknown segment: {segment!r}")


def _draw_base_risk(rng: random.Random, segment: str) -> float:
    # Per-segment risk band, then small jitter, then clamp to [_RISK_MIN, _RISK_MAX].
    if segment == "digital_primary":
        center, half = 0.16, 0.06
    elif segment == "low_digital_activity":
        center, half = 0.31, 0.09
    elif segment == "mixed_channel":
        center, half = 0.22, 0.07
    elif segment == "new_customer":
        center, half = 0.31, 0.11
    elif segment == "high_value":
        center, half = 0.12, 0.06
    else:
        raise ValueError(f"unknown segment: {segment!r}")
    raw = center + rng.uniform(-half, half)
    clamped = max(_RISK_MIN, min(_RISK_MAX, raw))
    # Round to 4 decimals so JSON output is stable for hash comparison.
    return round(clamped, 4)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _assert_customer_shape(record: Customer) -> None:
    """Runtime shape + domain check. Raises ValueError on any mismatch."""
    keys = set(record.keys())
    if keys != _CUSTOMER_KEYS:
        missing = _CUSTOMER_KEYS - keys
        extra = keys - _CUSTOMER_KEYS
        raise ValueError(
            f"customer record shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    cid = record["customer_id"]
    if not cid.startswith(CUSTOMER_ID_PREFIX):
        raise ValueError(f"customer_id missing synthetic prefix: {cid!r}")
    seg = record["customer_segment"]
    if seg not in CUSTOMER_SEGMENTS:
        raise ValueError(f"customer_segment not in allow-list: {seg!r}")
    region = record["home_region_bucket"]
    if region not in HOME_REGION_BUCKETS:
        raise ValueError(f"home_region_bucket not in allow-list: {region!r}")
    age = record["account_age_days"]
    if not (_ACCOUNT_AGE_MIN_DAYS <= age <= _ACCOUNT_AGE_MAX_DAYS):
        raise ValueError(
            f"account_age_days out of bounds [{_ACCOUNT_AGE_MIN_DAYS}, {_ACCOUNT_AGE_MAX_DAYS}]: {age}"
        )
    if record["normal_login_frequency_30d"] < 0:
        raise ValueError(f"normal_login_frequency_30d must be >= 0: {record['normal_login_frequency_30d']}")
    if record["normal_transfer_frequency_30d"] < 0:
        raise ValueError(f"normal_transfer_frequency_30d must be >= 0: {record['normal_transfer_frequency_30d']}")
    risk = record["synthetic_base_risk"]
    if not (_RISK_MIN <= risk <= _RISK_MAX):
        raise ValueError(f"synthetic_base_risk out of bounds [{_RISK_MIN}, {_RISK_MAX}]: {risk}")


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------


def generate_customers(rng: random.Random, count: int, seed: int) -> list[Customer]:
    """Generate ``count`` synthetic customers using ``rng``.

    Args:
        rng: Seeded ``random.Random`` instance. The caller owns seeding;
            this function does not reseed and consumes from ``rng`` only.
        count: Number of customers to emit. Must be >= 1.
        seed: The integer seed value, written into each record's
            ``created_from_seed`` field for traceability across runs.

    Returns:
        A list of ``Customer`` TypedDicts. Same ``rng`` state and same
        ``count`` produces a byte-identical list.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")

    customers: list[Customer] = []
    for idx in range(1, count + 1):
        segment = rng.choice(CUSTOMER_SEGMENTS)
        region = rng.choice(HOME_REGION_BUCKETS)
        record: Customer = {
            "customer_id": make_customer_id(idx),
            "customer_segment": segment,
            "home_region_bucket": region,
            "account_age_days": _draw_account_age_days(rng, segment),
            "normal_login_frequency_30d": _draw_login_freq_30d(rng, segment),
            "normal_transfer_frequency_30d": _draw_transfer_freq_30d(rng, segment),
            "synthetic_base_risk": _draw_base_risk(rng, segment),
            "created_from_seed": seed,
        }
        _assert_customer_shape(record)
        customers.append(record)

    return customers
