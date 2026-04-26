"""Local MCP wrapper over the Phase 4 + Phase 6 FastAPI service.

Thin local wrapper that exposes the implemented routes as callable
functions over ``ATLAS_API_BASE_URL`` (set in ``.mcp.json``).

Surface:
  * Phase 4 — ``get_decision_thresholds``, ``get_synthetic_sample``,
              ``score_event``, ``batch_score_events``.
  * Phase 6 — ``run_red_team_search``.

A proper MCP-protocol server can wrap these functions in a future phase
without changing the underlying calls.

The wrapper does NOT add any new business logic — it forwards to the
local FastAPI service, which is the only authoritative path for scoring,
metadata, and red-team search.
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


def run_red_team_search(
    run_id: str,
    round_id: int,
    search_methods: list[str],
    max_score_queries: int,
    allowed_family_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run a deterministic Phase 6 red-team search and return the
    ``RedTeamSearchResponse`` (headline metrics, found_adaptive_set
    event-ids, model-vulnerability cards).
    """
    payload: dict[str, Any] = {
        "run_id": run_id,
        "round_id": round_id,
        "search_methods": search_methods,
        "max_score_queries": max_score_queries,
    }
    if allowed_family_ids is not None:
        payload["allowed_family_ids"] = allowed_family_ids
    with _client() as client:
        r = client.post("/red-team/search", json=payload)
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
    "run_red_team_search": {
        "description": (
            "Run a deterministic Phase 6 red-team search across the "
            "configured methods + families and return public-safe "
            "model-vulnerability cards plus found_adaptive_set event-ids."
        ),
        "method": "POST /red-team/search",
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
