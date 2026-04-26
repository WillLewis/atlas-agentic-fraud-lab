"""Synthetic device generator (Phase 2).

Each customer is assigned 1–3 synthetic devices. The customer's
``normal_login_frequency_30d`` is split across those devices, with the
highest-traffic device flagged ``is_current_event_device=True``. Channel
mix is weighted toward mobile to match the fixture's distribution.

Determinism: ``generate_devices`` consumes only from the supplied RNG and
the customer list. Channel choices, device counts, login splits, and
``first_seen_days_ago`` are all RNG-derived. No global state, no time reads.
"""

from __future__ import annotations

import random
from typing import Final, TypedDict

from atlas.synthetic.customers import Customer

# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------


class Device(TypedDict):
    """Synthetic device or browser/app identifier attached to a customer."""

    device_id: str
    customer_id: str
    device_channel: str
    first_seen_days_ago: int
    login_count_30d: int
    is_current_event_device: bool


# ---------------------------------------------------------------------------
# Bucketed enums
# ---------------------------------------------------------------------------

DEVICE_ID_PREFIX: Final[str] = "dev_"

DEVICE_CHANNELS: Final[tuple[str, ...]] = ("mobile_app", "web", "tablet_app")
_DEVICE_CHANNEL_WEIGHTS: Final[tuple[float, ...]] = (0.65, 0.30, 0.05)

# Per-customer device count: most customers have 1 device, some have 2 or 3.
_DEVICE_COUNT_CHOICES: Final[tuple[int, ...]] = (1, 2, 3)
_DEVICE_COUNT_WEIGHTS: Final[tuple[float, ...]] = (0.60, 0.30, 0.10)

_DEVICE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "device_id",
        "customer_id",
        "device_channel",
        "first_seen_days_ago",
        "login_count_30d",
        "is_current_event_device",
    }
)


# ---------------------------------------------------------------------------
# Public ID helpers
# ---------------------------------------------------------------------------


def make_device_id(index: int) -> str:
    """Render a synthetic device ID for ``index`` (1-based)."""
    if index < 1:
        raise ValueError("device index must be >= 1")
    return f"{DEVICE_ID_PREFIX}{index:06d}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _draw_device_count(rng: random.Random) -> int:
    return rng.choices(_DEVICE_COUNT_CHOICES, weights=_DEVICE_COUNT_WEIGHTS, k=1)[0]


def _draw_channel(rng: random.Random) -> str:
    return rng.choices(DEVICE_CHANNELS, weights=_DEVICE_CHANNEL_WEIGHTS, k=1)[0]


def _split_login_count(rng: random.Random, total: int, parts: int) -> list[int]:
    """Split ``total`` logins across ``parts`` devices.

    The primary device receives 55–90% of the logins (weighted by RNG).
    Any remainder is distributed across the other devices uniformly. When
    ``total`` is 0, every device gets 0 logins.
    """
    if parts < 1:
        raise ValueError("parts must be >= 1")
    if total < 0:
        raise ValueError("total must be >= 0")
    if parts == 1:
        return [total]
    if total == 0:
        return [0] * parts

    # Primary device share, biased toward concentration on one device.
    share = rng.uniform(0.55, 0.90)
    primary = max(1, min(total, int(round(total * share))))
    remaining = total - primary
    splits = [primary] + [0] * (parts - 1)
    for _ in range(remaining):
        i = rng.randrange(1, parts)
        splits[i] += 1
    return splits


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _assert_device_shape(record: Device) -> None:
    keys = set(record.keys())
    if keys != _DEVICE_KEYS:
        missing = _DEVICE_KEYS - keys
        extra = keys - _DEVICE_KEYS
        raise ValueError(
            f"device record shape mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )
    if not record["device_id"].startswith(DEVICE_ID_PREFIX):
        raise ValueError(f"device_id missing synthetic prefix: {record['device_id']!r}")
    if not record["customer_id"].startswith("cust_"):
        raise ValueError(f"customer_id missing synthetic prefix: {record['customer_id']!r}")
    if record["device_channel"] not in DEVICE_CHANNELS:
        raise ValueError(f"device_channel not in allow-list: {record['device_channel']!r}")
    if record["first_seen_days_ago"] < 0:
        raise ValueError(f"first_seen_days_ago must be >= 0: {record['first_seen_days_ago']}")
    if record["login_count_30d"] < 0:
        raise ValueError(f"login_count_30d must be >= 0: {record['login_count_30d']}")
    if not isinstance(record["is_current_event_device"], bool):
        raise ValueError("is_current_event_device must be bool")


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------


def generate_devices(rng: random.Random, customers: list[Customer]) -> list[Device]:
    """Generate 1–3 synthetic devices per customer.

    Per-customer invariants:
      - At most one device is flagged ``is_current_event_device=True``
        (always the device with the most logins; ties broken by index).
      - Sum of ``login_count_30d`` across the customer's devices equals
        the customer's ``normal_login_frequency_30d``.
      - Every device's ``first_seen_days_ago`` is within the customer's
        account history (``<= account_age_days``); a value of 0 is allowed
        and represents a brand-new device.

    Args:
        rng: Seeded ``random.Random``. Caller owns seeding.
        customers: Customer list (unmodified).

    Returns:
        Flat list of ``Device`` TypedDicts. Device IDs are 1-based and
        global (not per-customer).
    """
    devices: list[Device] = []
    next_index = 0

    for customer in customers:
        device_count = _draw_device_count(rng)
        max_first_seen = max(0, customer["account_age_days"])
        login_splits = _split_login_count(
            rng, customer["normal_login_frequency_30d"], device_count
        )
        # Current-event device is whichever device has the most logins. Ties
        # resolve to the lowest index (the primary, which already received
        # the largest share by construction).
        current_idx = max(range(device_count), key=lambda i: login_splits[i])

        for j in range(device_count):
            next_index += 1
            channel = _draw_channel(rng)
            first_seen = rng.randint(0, max_first_seen)
            record: Device = {
                "device_id": make_device_id(next_index),
                "customer_id": customer["customer_id"],
                "device_channel": channel,
                "first_seen_days_ago": first_seen,
                "login_count_30d": login_splits[j],
                "is_current_event_device": (j == current_idx),
            }
            _assert_device_shape(record)
            devices.append(record)

    return devices
