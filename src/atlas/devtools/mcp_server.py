"""Local MCP wrapper over the Phase 4 + Phase 6 + Phase 7 + Phase 9 +
Phase 10 FastAPI service.

Thin local wrapper that exposes the implemented routes as callable
functions over ``ATLAS_API_BASE_URL`` (set in ``.mcp.json``).

Surface:
  * Phase 4 — ``get_decision_thresholds``, ``get_synthetic_sample``,
              ``score_event``, ``batch_score_events``.
  * Phase 6 — ``run_red_team_search``.
  * Phase 7 — ``propose_defensive_fixes``, ``apply_defensive_fix``.
  * Phase 9 — ``create_run``, ``list_runs``, ``get_run_detail``,
              ``run_rounds``, ``get_replay_payload``.
  * Phase 10 — ``run_safety_scan``, ``get_model_quality_matrix``.

A proper MCP-protocol server can wrap these functions in a future phase
without changing the underlying calls.

The wrapper does NOT add any new business logic — it forwards to the
local FastAPI service, which is the only authoritative path for scoring,
metadata, red-team search, defensive-fix proposal/apply, the Phase 9
run/round/replay surface, and the Phase 10 safety + model-quality
surfaces.
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


def propose_defensive_fixes(
    run_id: str,
    round_id: int,
    model_vulnerability_ids: list[str],
    allowed_fix_types: list[str],
) -> dict[str, Any]:
    """Propose deterministic defensive-fix candidates for one or more
    model vulnerabilities.

    Returns the ``DefensiveFixProposalResponse`` shape — one
    ``DefensiveFixCandidate`` per (vulnerability_id, fix_type) pair
    that survives the three-way intersection (request ∩ round_config ∩
    card recommendation).
    """
    payload: dict[str, Any] = {
        "run_id": run_id,
        "round_id": round_id,
        "model_vulnerability_ids": model_vulnerability_ids,
        "allowed_fix_types": allowed_fix_types,
    }
    with _client() as client:
        r = client.post("/defensive-fixes/propose", json=payload)
        r.raise_for_status()
        return r.json()


def apply_defensive_fix(
    run_id: str,
    round_id: int,
    defensive_fix_id: str,
) -> dict[str, Any]:
    """Materialize the candidate, run the judge in-process, and return
    the ``DefensiveFixApplyResponse`` (``applied`` flag +
    ``governance_rationale`` from the closed-enum formatter).

    ``applied=true`` ⇔ judge accepted the candidate.
    ``applied=false`` ⇔ judge rejected; artifacts still on disk under
    ``outputs/`` for traceability.
    """
    payload: dict[str, Any] = {
        "run_id": run_id,
        "round_id": round_id,
        "defensive_fix_id": defensive_fix_id,
    }
    with _client() as client:
        r = client.post("/defensive-fixes/apply", json=payload)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Phase 9 — runs / rounds / replay
# ---------------------------------------------------------------------------


def create_run(
    seed: int,
    run_label: str | None = None,
    demo_mode: str = "public",
    max_rounds: int = 3,
) -> dict[str, Any]:
    """Seed an initial ``RunState`` (status=``created``,
    current_round=0). Does NOT execute rounds — call ``run_rounds`` next.

    ``run_id`` is deterministic from ``(seed, run_label, demo_mode)``.
    """
    payload: dict[str, Any] = {
        "seed": seed,
        "demo_mode": demo_mode,
        "max_rounds": max_rounds,
    }
    if run_label is not None:
        payload["run_label"] = run_label
    with _client() as client:
        r = client.post("/runs", json=payload)
        r.raise_for_status()
        return r.json()


def list_runs() -> dict[str, Any]:
    """List all persisted ``RunState`` snapshots from ``outputs/runs/``.

    Returns ``{"runs": []}`` when no runs exist yet.
    """
    with _client() as client:
        r = client.get("/runs")
        r.raise_for_status()
        return r.json()


def get_run_detail(run_id: str) -> dict[str, Any]:
    """Fetch ``RunDetail`` — RunSummary + persisted RoundSummaries +
    ``latest_metrics`` derived from the latest round's judge report.
    """
    with _client() as client:
        r = client.get(f"/runs/{run_id}")
        r.raise_for_status()
        return r.json()


def run_rounds(
    run_id: str,
    start_round: int = 1,
    round_count: int = 1,
) -> dict[str, Any]:
    """Execute one or more rounds against an existing run. Calls
    ``execute_one_round`` per round and threads carry-forward versions.
    Returns ``RoundRunResponse`` with the completed RoundSummaries.

    422 when ``start_round + round_count - 1 > run.max_rounds``.
    """
    payload: dict[str, Any] = {
        "run_id": run_id,
        "start_round": start_round,
        "round_count": round_count,
    }
    with _client() as client:
        r = client.post("/rounds/run", json=payload)
        r.raise_for_status()
        return r.json()


def get_replay_payload(run_id: str) -> dict[str, Any]:
    """Fetch the public-safe ``ReplayPayload`` envelope (run +
    five_step_story + charts.round_metrics) for a run. 404 if missing.
    """
    with _client() as client:
        r = client.get(f"/replay/{run_id}")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Phase 10 — safety + model-quality
# ---------------------------------------------------------------------------


def run_safety_scan(
    demo_mode: str = "public",
    text: str | None = None,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Scan ``text`` or ``file_paths`` (or ``default_paths`` when both
    are omitted) against the public-mode rules in
    ``config/safety.yaml``. Returns ``{passed, findings,
    recommended_rewrites}``.

    Deterministic: same input → same response. Rewrite suggestions
    come from a closed-enum template registry keyed on rule_id; no
    LLM rewriting path exists.
    """
    payload: dict[str, Any] = {"demo_mode": demo_mode}
    if text is not None:
        payload["text"] = text
    if file_paths is not None:
        payload["file_paths"] = file_paths
    with _client() as client:
        r = client.post("/safety/scan", json=payload)
        r.raise_for_status()
        return r.json()


def get_model_quality_matrix() -> dict[str, Any]:
    """Fetch the public-safe model-tier comparison matrix projected
    from ``config/model_quality_matrix.yaml``. Per-cell metric values
    are placeholders (Phase 13 fills measured values).
    """
    with _client() as client:
        r = client.get("/model-quality-matrix")
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
    "propose_defensive_fixes": {
        "description": (
            "Propose deterministic Phase 7 bank-defense fix candidates "
            "for the given model_vulnerability_ids. Three-way intersects "
            "request fix types ∩ round_config ∩ card recommendations."
        ),
        "method": "POST /defensive-fixes/propose",
    },
    "apply_defensive_fix": {
        "description": (
            "Apply a Phase 7 defensive-fix candidate: materialize "
            "candidate threshold or model artifacts, evaluate via the "
            "judge in-process, return applied=true (judge-accepted) or "
            "applied=false (judge-rejected) with a governance rationale."
        ),
        "method": "POST /defensive-fixes/apply",
    },
    "create_run": {
        "description": (
            "Seed an initial RunState (status=created, current_round=0). "
            "Does NOT execute rounds — call run_rounds next. run_id is "
            "deterministic from (seed, run_label, demo_mode)."
        ),
        "method": "POST /runs",
    },
    "list_runs": {
        "description": (
            "List all persisted RunState snapshots from outputs/runs/."
        ),
        "method": "GET /runs",
    },
    "get_run_detail": {
        "description": (
            "Fetch RunDetail — RunSummary + persisted RoundSummaries + "
            "latest_metrics derived from the latest round's judge report."
        ),
        "method": "GET /runs/{run_id}",
    },
    "run_rounds": {
        "description": (
            "Execute one or more rounds against an existing run. Calls "
            "execute_one_round per round and threads carry-forward "
            "versions. Returns RoundRunResponse."
        ),
        "method": "POST /rounds/run",
    },
    "get_replay_payload": {
        "description": (
            "Fetch the public-safe ReplayPayload envelope (run + "
            "five_step_story + charts.round_metrics) for a run."
        ),
        "method": "GET /replay/{run_id}",
    },
    "run_safety_scan": {
        "description": (
            "Scan text or file_paths against the public-mode rules in "
            "config/safety.yaml. Returns passed + findings + "
            "deterministic recommended_rewrites."
        ),
        "method": "POST /safety/scan",
    },
    "get_model_quality_matrix": {
        "description": (
            "Fetch the public-safe model-tier comparison matrix. "
            "Per-cell metric values are placeholders; Phase 13 fills "
            "measured values from live comparison runs."
        ),
        "method": "GET /model-quality-matrix",
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
