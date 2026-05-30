"""Integration tests — GET /model-quality-matrix.

Validates the YAML → OpenAPI projection:

  * Top-level keys: ``matrix_version`` / ``cells`` / ``caveat``.
  * ``matrix_version`` sourced from
    ``model_quality_matrix_version`` in YAML.
  * ``cells`` count matches the YAML ``runs[]`` count (4 runs → 4 cells).
  * Each cell carries ``red_team_model_tier`` + ``blue_team_model_tier``
    (renamed from YAML ``red_team_tier`` / ``bank_defense_tier``).
  * Cells with ``source_run_id`` carry judge-derived replay metrics.
  * Cells without a curated source expose explicit null metrics.
  * ``caveat`` is a non-empty closed-enum string.
"""
from __future__ import annotations

import pytest


def test_model_quality_matrix_top_level_shape(api_client):
    resp = api_client.get("/model-quality-matrix")
    assert resp.status_code == 200
    body = resp.json()
    assert sorted(body.keys()) == ["caveat", "cells", "matrix_version"]


def test_model_quality_matrix_version_from_yaml(api_client):
    body = api_client.get("/model-quality-matrix").json()
    assert body["matrix_version"] == "matrix_v1"


def test_model_quality_matrix_cells_match_runs_count(api_client):
    """The current YAML has 4 runs (A/B/C/D)."""
    body = api_client.get("/model-quality-matrix").json()
    cells = body["cells"]
    assert len(cells) == 4
    assert {c["cell_id"] for c in cells} == {"A", "B", "C", "D"}


def test_model_quality_matrix_cell_field_set(api_client):
    body = api_client.get("/model-quality-matrix").json()
    expected = {
        "cell_id",
        "red_team_model_tier",
        "blue_team_model_tier",
        "source_run_id",
        "metrics_source",
        "metrics_status",
        "average_model_miss_rate",
        "average_recall_recovery_points",
        "fixed_action_rate_pass",
    }
    for c in body["cells"]:
        assert set(c.keys()) >= expected


def test_model_quality_matrix_tier_values(api_client):
    """Each cell's tier values are in {frontier, compact}."""
    body = api_client.get("/model-quality-matrix").json()
    for c in body["cells"]:
        assert c["red_team_model_tier"] in ("frontier", "compact")
        assert c["blue_team_model_tier"] in ("frontier", "compact")


def test_model_quality_matrix_cell_a_uses_curated_replay_metrics(api_client):
    body = api_client.get("/model-quality-matrix").json()
    cell_a = next(c for c in body["cells"] if c["cell_id"] == "A")
    assert cell_a["source_run_id"] == "run_4548ebb8"
    assert cell_a["metrics_source"] == "judge_derived_replay"
    assert cell_a["metrics_status"] == "loaded"
    assert cell_a["average_model_miss_rate"] == pytest.approx(0.3177)
    assert cell_a["average_recall_recovery_points"] == pytest.approx(70.32)
    assert cell_a["fixed_action_rate_pass"] is True


def test_model_quality_matrix_unavailable_cells_are_null(api_client):
    body = api_client.get("/model-quality-matrix").json()
    unavailable = [c for c in body["cells"] if c["metrics_source"] == "unavailable"]
    assert {c["cell_id"] for c in unavailable} == {"B", "C", "D"}
    for c in unavailable:
        assert c["source_run_id"] is None
        assert c["metrics_status"] == "no_source_run"
        assert c["average_model_miss_rate"] is None
        assert c["average_recall_recovery_points"] is None
        assert c["fixed_action_rate_pass"] is None


def test_model_quality_matrix_caveat_non_empty(api_client):
    body = api_client.get("/model-quality-matrix").json()
    assert isinstance(body["caveat"], str)
    assert len(body["caveat"]) > 0
    assert "Phase 13" not in body["caveat"]
    assert "placeholder" not in body["caveat"].lower()
    assert "source_run_id" in body["caveat"]


def test_model_quality_matrix_cell_a_is_frontier_frontier(api_client):
    """Sanity-check the projection against the YAML run table."""
    body = api_client.get("/model-quality-matrix").json()
    cell_a = next(c for c in body["cells"] if c["cell_id"] == "A")
    assert cell_a["red_team_model_tier"] == "frontier"
    assert cell_a["blue_team_model_tier"] == "frontier"
