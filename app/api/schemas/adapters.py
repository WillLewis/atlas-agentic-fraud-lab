"""Adapters between persisted Phase 2/3 records and API schemas.

Phase 4 invariant: the persisted dataset is NOT renamed. These adapters
translate at the API boundary so the OpenAPI public contract stays
satisfied without rewriting Phase 2/3 storage.
"""

from __future__ import annotations

from typing import Any


_CUSTOMER_API_KEYS = (
    "customer_id",
    "customer_segment",
    "home_region_bucket",
    "account_age_days",
    "normal_login_frequency_30d",
    "normal_transfer_frequency_30d",
    "synthetic_base_risk",
)


def customer_to_api_view(customer: dict[str, Any]) -> dict[str, Any]:
    """Persisted ``Customer`` → API ``Customer`` shape.

    Drops persistence-only fields (e.g. ``created_from_seed``) that aren't
    in the OpenAPI public contract.
    """
    return {k: customer[k] for k in _CUSTOMER_API_KEYS if k in customer}


def transfer_event_to_event_record(transfer: dict[str, Any]) -> dict[str, Any]:
    """Persisted ``TransferEvent`` → API ``EventRecord``.

    Renames ``transfer_event_id`` to ``event_id``; preserves the rest.
    Keeps ``synthetic_truth_label`` because OpenAPI marks it required;
    the scorer never reads it.
    """
    return {
        "event_id": transfer["transfer_event_id"],
        "customer_id": transfer["customer_id"],
        "event_type": transfer["event_type"],
        "event_time_utc": transfer["event_time_utc"],
        "device_id": None,
        "account_id": transfer.get("account_id"),
        "recipient_id": transfer.get("recipient_id"),
        "channel": transfer.get("channel"),
        "amount_bucket": transfer.get("amount_bucket"),
        "synthetic_truth_label": transfer["synthetic_truth_label"],
    }
