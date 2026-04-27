"""Phase 10 public-mode smoke test.

Bible §18 Phase 10 acceptance: a reviewer can run the demo without API
keys. This test pins the public-mode invariants the reviewer flow
relies on, exercised end-to-end through the FastAPI surface:

  * ``/config/demo`` reports synthetic generic labels — no real
    institution, no real model name.
  * ``/safety/scan`` with clean public-safe text passes.
  * ``/safety/scan`` over banned-institution text fails with a
    structured ``real_institution_names`` finding.
  * ``/safety/scan`` over secret-token text fails AND redacts the raw
    secret in the surfaced ``message`` field.
  * ``/model-quality-matrix`` exposes only public tier ids, never
    concrete model identifiers (``expose_concrete_model_names`` is
    ``false`` in the public-mode config).
  * ``config/demo.yaml`` and ``.mcp.json`` pass their respective
    Phase 10 validators.
  * The current ``outputs/demo_replays/`` curated replay file (if
    present) has its synthetic round_summary text pass the in-process
    safety scan.

The test is hermetic — uses the ``api_client`` fixture which
monkey-patches all OUTPUTS_ROOT paths into a tmp dir. No API keys, no
external services.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from atlas.safety.config_validator import (
    validate_demo_config,
    validate_mcp_config,
    validate_model_quality_matrix,
    validate_safety_config,
)
from atlas.safety.scanner import scan_text


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Public-safe label invariants from /config/demo
# ---------------------------------------------------------------------------


def test_config_demo_generic_institution_label(api_client):
    body = api_client.get("/config/demo").json()
    assert body["demo_mode"] == "public"
    # Generic synthetic label, not a real bank or payment network.
    assert body["institution_label"] == "RetailBank-X"


def test_config_demo_generic_model_label(api_client):
    body = api_client.get("/config/demo").json()
    # Public-safe placeholder name — does NOT mention any concrete
    # model identifier.
    assert body["model_label"] == "Mock Account-Takeover Risk Scorer"
    assert "claude" not in body["model_label"].lower()
    assert "gpt" not in body["model_label"].lower()
    assert "llama" not in body["model_label"].lower()


def test_config_demo_disclaimer_present(api_client):
    body = api_client.get("/config/demo").json()
    assert body.get("disclaimer")
    assert "synthetic" in body["disclaimer"].lower()


# ---------------------------------------------------------------------------
# /safety/scan public-mode behavior
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "clean_text",
    [
        "this is a synthetic test",
        "RetailBank-X uses public-safe terminology",
        "model_vulnerability identified, defensive_fix proposed",
        "the under_ranked_cohort had a high model_miss_rate",
    ],
)
def test_safety_scan_public_mode_clean_passes(api_client, clean_text):
    resp = api_client.post(
        "/safety/scan", json={"demo_mode": "public", "text": clean_text},
    )
    body = resp.json()
    assert body["passed"] is True
    assert body["findings"] == []


def test_safety_scan_public_mode_banned_institution_fails(api_client):
    resp = api_client.post(
        "/safety/scan",
        json={
            "demo_mode": "public",
            "text": "this configuration mentions jpmorgan internal",
        },
    )
    body = resp.json()
    assert body["passed"] is False
    cats = {f["category"] for f in body["findings"]}
    assert "real_institution_names" in cats
    # Recommended rewrites surface the public-safe label.
    assert any("RetailBank-X" in r for r in body["recommended_rewrites"])


def test_safety_scan_public_mode_secret_redacted(api_client):
    resp = api_client.post(
        "/safety/scan",
        json={
            "demo_mode": "public",
            "text": "we keep AKIA1234567890ABCDEF in the env",
        },
    )
    body = resp.json()
    assert body["passed"] is False
    # Raw secret must NOT appear in the surfaced messages.
    msgs = " ".join(f["message"] for f in body["findings"])
    assert "AKIA1234567890ABCDEF" not in msgs
    assert "<REDACTED-TOKEN>" in msgs


def test_safety_scan_public_mode_production_url_fails(api_client):
    resp = api_client.post(
        "/safety/scan",
        json={
            "demo_mode": "public",
            "text": "see https://api.bank.prod/v1/score for details",
        },
    )
    body = resp.json()
    assert body["passed"] is False
    cats = {f["category"] for f in body["findings"]}
    assert "production_endpoints" in cats
    assert any("127.0.0.1" in r for r in body["recommended_rewrites"])


# ---------------------------------------------------------------------------
# /model-quality-matrix public-mode behavior
# ---------------------------------------------------------------------------


def test_model_quality_matrix_no_concrete_model_names(api_client):
    """Public mode must not surface concrete model identifiers in the
    response — only tier ids. Even if the YAML has ``tier_models``,
    the route projection only reads the tier ids.
    """
    body = api_client.get("/model-quality-matrix").json()
    payload = json.dumps(body)
    # Concrete identifiers from config/model_quality_matrix.yaml's
    # ``tier_models`` block must NOT appear in the public response.
    forbidden = ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"]
    for name in forbidden:
        assert name not in payload, (
            f"public-mode /model-quality-matrix leaked {name!r}"
        )


def test_model_quality_matrix_tier_values_are_public_labels(api_client):
    body = api_client.get("/model-quality-matrix").json()
    for c in body["cells"]:
        assert c["red_team_model_tier"] in ("frontier", "compact")
        assert c["blue_team_model_tier"] in ("frontier", "compact")


# ---------------------------------------------------------------------------
# Static config validation in public mode
# ---------------------------------------------------------------------------


def test_demo_yaml_passes_validator():
    cfg = yaml.safe_load((REPO_ROOT / "config" / "demo.yaml").read_text())
    assert validate_demo_config(cfg) == []


def test_mcp_json_passes_validator():
    cfg = json.loads((REPO_ROOT / ".mcp.json").read_text())
    assert validate_mcp_config(cfg) == []


def test_safety_yaml_passes_validator():
    cfg = yaml.safe_load((REPO_ROOT / "config" / "safety.yaml").read_text())
    assert validate_safety_config(cfg) == []


def test_model_quality_matrix_yaml_passes_validator():
    cfg = yaml.safe_load(
        (REPO_ROOT / "config" / "model_quality_matrix.yaml").read_text()
    )
    assert validate_model_quality_matrix(cfg) == []


# ---------------------------------------------------------------------------
# Curated replay public-safety (when present)
# ---------------------------------------------------------------------------


def _curated_replay_path() -> Path | None:
    """Return the path to a curated replay file, if any. The Phase 10
    plan packages exactly one named replay; treat its absence as
    "skip" rather than fail since the test runs in fresh checkouts.
    """
    candidates = list((REPO_ROOT / "outputs" / "demo_replays").glob("run_*.json"))
    return candidates[0] if candidates else None


def test_curated_replay_text_passes_safety_scan():
    """Every transcript_summary + final_report.summary in the curated
    replay (if any) passes the in-process safety scan. The Phase 8
    closed-enum templates are designed to pass; this test pins that
    invariant for the file packaged for reviewers.
    """
    replay_path = _curated_replay_path()
    if replay_path is None:
        pytest.skip("no curated replay packaged yet (Phase 10 component 7)")
    payload = json.loads(replay_path.read_text())
    texts: list[str] = []
    for step in payload.get("five_step_story", []):
        for card in step.get("cards", []):
            for key in ("transcript_summary", "summary"):
                v = card.get(key)
                if isinstance(v, str) and v:
                    texts.append(v)
    assert texts, "curated replay had no transcript / summary text to check"
    for t in texts:
        rep = scan_text(t)
        assert rep.errors == [], (
            f"curated replay text failed safety scan: "
            f"{[(f.rule_id, f.snippet[:80]) for f in rep.errors]}"
        )
