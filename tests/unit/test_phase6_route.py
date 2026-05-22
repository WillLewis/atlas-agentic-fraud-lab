"""Phase 6 ``POST /red-team/search`` route tests via TestClient.

Uses the ``api_client`` fixture which monkey-patches the trained
baseline path + Phase 6 caches.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(**overrides):
    base = {
        "run_id": "run_local_test",
        "round_id": 1,
        "search_methods": ["random", "evolutionary", "graph_probe"],
        "max_score_queries": 100,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path + shape
# ---------------------------------------------------------------------------


def test_route_returns_200_on_happy_path(api_client):
    r = api_client.post("/red-team/search", json=_payload())
    assert r.status_code == 200, r.text


def test_route_response_shape(api_client):
    r = api_client.post("/red-team/search", json=_payload())
    body = r.json()
    required = {
        "run_id", "round_id",
        "valid_high_risk_events_tested", "accepted_high_risk_events",
        "model_miss_rate",
    }
    assert required.issubset(body)
    # Optional
    if "found_adaptive_set_event_ids" in body:
        assert isinstance(body["found_adaptive_set_event_ids"], list)
    if "model_vulnerability_cards" in body:
        assert isinstance(body["model_vulnerability_cards"], list)


def test_route_metric_types(api_client):
    body = api_client.post("/red-team/search", json=_payload()).json()
    assert isinstance(body["valid_high_risk_events_tested"], int)
    assert isinstance(body["accepted_high_risk_events"], int)
    assert isinstance(body["model_miss_rate"], (int, float))


# ---------------------------------------------------------------------------
# Determinism (Bible §18 Phase 6)
# ---------------------------------------------------------------------------


def test_route_byte_identical_under_repeat(api_client):
    r1 = api_client.post("/red-team/search", json=_payload())
    r2 = api_client.post("/red-team/search", json=_payload())
    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content


# ---------------------------------------------------------------------------
# found_adaptive_set deterministic + sourced from readable global artifact
# ---------------------------------------------------------------------------


def test_found_adaptive_set_event_ids_sorted_and_unique(api_client):
    body = api_client.post("/red-team/search", json=_payload()).json()
    ids = body.get("found_adaptive_set_event_ids", [])
    assert list(ids) == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_found_adaptive_set_ids_are_valid_global_event_ids(api_client):
    """Every found_adaptive_set event_id must exist in the readable
    global feature artifact (train + validation + clean_holdout)."""
    body = api_client.post("/red-team/search", json=_payload()).json()
    ids = set(body.get("found_adaptive_set_event_ids", []))
    if not ids:
        pytest.skip("no found_adaptive_set_event_ids returned to validate")
    # Load the readable global features
    global_ids: set[str] = set()
    for partition in ("train", "validation", "clean_holdout"):
        path = REPO_ROOT / "data" / "synthetic" / "features" / f"{partition}.json"
        if path.exists():
            with path.open() as fh:
                for f in json.load(fh):
                    global_ids.add(f["event_id"])
    assert ids.issubset(global_ids), (
        f"found_adaptive_set has ids not in readable global artifact: "
        f"{sorted(ids - global_ids)[:5]}"
    )


# ---------------------------------------------------------------------------
# ModelVulnerabilityCard structure
# ---------------------------------------------------------------------------


def test_model_vulnerability_cards_have_required_fields(api_client):
    body = api_client.post("/red-team/search", json=_payload()).json()
    cards = body.get("model_vulnerability_cards", [])
    if not cards:
        pytest.skip("no cards returned to validate")
    required = {
        "model_vulnerability_id", "round_id", "family_id",
        "summary", "model_miss_rate",
    }
    for card in cards:
        assert required.issubset(card)
        assert card["model_vulnerability_id"].startswith("mv_round")


def test_card_recommended_fix_types_from_canonical_map(api_client):
    from atlas.red_team.model_vulnerability_packager import RECOMMENDED_FIX_TYPES_BY_FAMILY

    body = api_client.post("/red-team/search", json=_payload()).json()
    cards = body.get("model_vulnerability_cards", [])
    if not cards:
        pytest.skip("no cards returned to validate")
    for card in cards:
        if card.get("recommended_defensive_fix_types") is not None:
            assert (
                tuple(card["recommended_defensive_fix_types"])
                == RECOMMENDED_FIX_TYPES_BY_FAMILY[card["family_id"]]
            )


# ---------------------------------------------------------------------------
# Error mapping (mirrors Phase 5 pattern)
# ---------------------------------------------------------------------------


def test_route_unknown_round_id_returns_422(api_client):
    r = api_client.post("/red-team/search", json=_payload(round_id=999))
    assert r.status_code == 422
    assert "unknown round_id" in r.json()["detail"]


def test_route_empty_family_intersection_returns_422(api_client):
    r = api_client.post("/red-team/search", json=_payload(
        allowed_family_ids=["activity_channel_shift"],  # not in round 1
    ))
    assert r.status_code == 422
    assert "empty family intersection" in r.json()["detail"]


def test_route_empty_method_intersection_returns_422(api_client):
    r = api_client.post("/red-team/search", json=_payload(
        round_id=2, search_methods=["random"],  # round 2 doesn't enable random
    ))
    assert r.status_code == 422


def test_route_negative_budget_returns_422(api_client):
    r = api_client.post("/red-team/search", json=_payload(max_score_queries=-1))
    assert r.status_code == 422


def test_route_missing_required_field_returns_422(api_client):
    r = api_client.post("/red-team/search", json={"run_id": "x"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# extra="forbid" — no client-supplied output overrides
# ---------------------------------------------------------------------------


def test_route_rejects_card_override(api_client):
    """A client-supplied model_vulnerability_cards in the request body
    must be rejected (extra="forbid"). Bible §18 Phase 6: search output
    is code-derived; agent text cannot drive it."""
    r = api_client.post("/red-team/search", json=_payload(
        model_vulnerability_cards=[{"model_vulnerability_id": "fake"}],
    ))
    assert r.status_code == 422


def test_route_rejects_arbitrary_field(api_client):
    r = api_client.post("/red-team/search", json=_payload(arbitrary_field="x"))
    assert r.status_code == 422


def test_route_rejects_found_adaptive_set_override(api_client):
    """The route's REQUEST schema doesn't expose found_adaptive_set; if
    the client tries to inject one, it must 422."""
    r = api_client.post("/red-team/search", json=_payload(
        found_adaptive_set_event_ids=["tx_999999"],
    ))
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Budget honored — search never EXCEEDS max_score_queries
# ---------------------------------------------------------------------------


def test_search_never_exceeds_score_query_budget(api_client):
    """The internal queries_used (sum across methods) must be <= the
    requested max_score_queries. Less is OK (graph_probe may skip some
    families)."""
    # We can verify this by inspecting the orchestrator's
    # RedTeamSearchResult. Run via the route then re-derive using the
    # in-process orchestrator with the same args.
    from atlas.red_team.fraud_scenario_agent import run_search, reset_caches
    import app.api.routes.red_team as route_mod
    reset_caches()
    result = run_search(
        run_id="r", round_id=1,
        search_methods=["random", "evolutionary", "graph_probe"],
        max_score_queries=200,
        outputs_root=route_mod.OUTPUTS_ROOT,
    )
    assert result.queries_used <= 200, (
        f"queries_used={result.queries_used} exceeded budget=200"
    )


# ---------------------------------------------------------------------------
# Round 2 — different family/method allow-lists
# ---------------------------------------------------------------------------


def test_route_round_2_works(api_client):
    """Round 2 enables only evolutionary + graph_probe; only allows
    different families. Verify the route handles it without error."""
    r = api_client.post("/red-team/search", json={
        "run_id": "r", "round_id": 2,
        "search_methods": ["evolutionary", "graph_probe"],
        "max_score_queries": 90,
    })
    assert r.status_code == 200
    body = r.json()
    # round 2 has no graph-relevant families → graph_probe contributes 0
    # but evolutionary still finds candidates
    assert body["round_id"] == 2
