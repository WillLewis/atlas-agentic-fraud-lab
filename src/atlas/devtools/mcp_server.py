"""Local MCP wrapper over the Phase 4 FastAPI service.

Thin local wrapper that exposes the implemented Phase 4 routes as
callable functions over ``ATLAS_API_BASE_URL`` (set in ``.mcp.json``).

Phase 4 deliberately keeps this surface small: four tool functions
(``get_decision_thresholds``, ``get_synthetic_sample``, ``score_event``,
``batch_score_events``) and a ``main()`` that prints the tool list. A
proper MCP-protocol server can wrap these functions in a future phase
without changing the underlying calls.

The wrapper does NOT add any new business logic — it forwards to the
local FastAPI service, which is the only authoritative path for scoring
and metadata.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
_TIMEOUT_SECONDS = 30.0


def _base_url() -> str:
    return os.environ.get("ATLAS_API_BASE_URL", DEFAULT_API_BASE_URL)


def _client() -> httpx.Client:
    return httpx.Client(base_url=_base_url(), timeout=_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# Tool functions — one per Phase 4 route exposed via MCP
# ---------------------------------------------------------------------------


def get_decision_thresholds() -> dict[str, Any]:
    """Get current decision thresholds and action-rate limits."""
    with _client() as client:
        r = client.get("/decision-thresholds")
        r.raise_for_status()
        return r.json()


def get_synthetic_sample(limit: int = 10) -> dict[str, Any]:
    """Get a small public-safe synthetic sample (customers, events, features)."""
    with _client() as client:
        r = client.get("/synthetic/sample", params={"limit": limit})
        r.raise_for_status()
        return r.json()


def score_event(event: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    """Score one synthetic event."""
    payload = {"event": event, "features": features}
    with _client() as client:
        r = client.post("/score", json=payload)
        r.raise_for_status()
        return r.json()


def batch_score_events(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Score many synthetic events. Each record is {event, features}."""
    payload = {"records": records}
    with _client() as client:
        r = client.post("/batch-score", json=payload)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Tool registry — printed by main() so callers can introspect the surface
# ---------------------------------------------------------------------------

TOOLS: dict[str, dict[str, str]] = {
    "get_decision_thresholds": {
        "description": "Get current decision thresholds and action-rate limits.",
        "method": "GET /decision-thresholds",
    },
    "get_synthetic_sample": {
        "description": "Get a small public-safe synthetic sample (customers, events, features).",
        "method": "GET /synthetic/sample?limit=N",
    },
    "score_event": {
        "description": "Score one synthetic event.",
        "method": "POST /score",
    },
    "batch_score_events": {
        "description": "Score many synthetic events in one request (max 5000).",
        "method": "POST /batch-score",
    },
}


def main(argv: list[str] | None = None) -> int:
    """Print the tool registry. Used as a manual sanity check."""
    info = {
        "atlas_api_base_url": _base_url(),
        "tools": TOOLS,
    }
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
