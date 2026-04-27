"""Phase 10 integration tests — POST /safety/scan.

  * Request schema rejects unknown fields (extra=forbid).
  * Clean text → ``passed=true``, empty findings + rewrites.
  * Dirty text → ``passed=false``, structured findings, deterministic
    rewrites (closed-enum from ``suggest_rewrites`` keyed by rule_id).
  * ``file_paths`` mode scans tmp files.
  * Empty body falls back to ``default_paths`` walk.
  * Findings carry redacted snippets (no raw secrets/tokens).
"""
from __future__ import annotations


def test_safety_scan_clean_text(api_client):
    resp = api_client.post(
        "/safety/scan",
        json={"demo_mode": "public", "text": "this is just synthetic"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passed"] is True
    assert body["findings"] == []
    assert body["recommended_rewrites"] == []


def test_safety_scan_dirty_real_institution(api_client):
    resp = api_client.post(
        "/safety/scan",
        json={"demo_mode": "public", "text": "we found jpmorgan internal data"},
    )
    body = resp.json()
    assert body["passed"] is False
    assert len(body["findings"]) >= 1
    # Categories use rule_ids.
    cats = {f["category"] for f in body["findings"]}
    assert "real_institution_names" in cats
    # Recommended rewrites are populated and deterministic.
    assert len(body["recommended_rewrites"]) >= 1
    assert any("RetailBank-X" in r for r in body["recommended_rewrites"])


def test_safety_scan_finding_shape(api_client):
    resp = api_client.post(
        "/safety/scan",
        json={"demo_mode": "public", "text": "we found jpmorgan internal data"},
    )
    body = resp.json()
    f = body["findings"][0]
    assert set(f.keys()) >= {"severity", "category", "message", "location"}
    assert f["location"] == "text:1"


def test_safety_scan_redacts_secret_in_message(api_client):
    """The snippet surfaced as ``message`` should NOT carry the raw
    token; ``redact`` runs first.
    """
    resp = api_client.post(
        "/safety/scan",
        json={"demo_mode": "public", "text": "key sk-abcdef0123456789abcdef0123 here"},
    )
    body = resp.json()
    msgs = " ".join(f["message"] for f in body["findings"])
    assert "<REDACTED-TOKEN>" in msgs
    # Raw token must NOT appear.
    assert "sk-abcdef0123456789abcdef0123" not in msgs


def test_safety_scan_file_paths_mode(api_client, tmp_path):
    p = tmp_path / "x.md"
    p.write_text("we found jpmorgan internal data\n")
    resp = api_client.post(
        "/safety/scan",
        json={"demo_mode": "public", "file_paths": [str(p)]},
    )
    body = resp.json()
    assert body["passed"] is False
    assert {f["category"] for f in body["findings"]} >= {"real_institution_names"}


def test_safety_scan_empty_body_walks_default_paths(api_client):
    """Empty body (no text, no file_paths) → scans configured
    default_paths. Real repo has clean defaults so this should pass.
    """
    resp = api_client.post(
        "/safety/scan", json={"demo_mode": "public"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Real repo passes; we just confirm the route ran.
    assert "passed" in body


def test_safety_scan_extra_field_rejected(api_client):
    """``SafetyScanRequest`` uses extra='forbid'."""
    resp = api_client.post(
        "/safety/scan",
        json={"demo_mode": "public", "text": "x", "secret_override": "y"},
    )
    assert resp.status_code == 422


def test_safety_scan_invalid_demo_mode_rejected(api_client):
    resp = api_client.post(
        "/safety/scan",
        json={"demo_mode": "production", "text": "x"},
    )
    assert resp.status_code == 422


def test_safety_scan_rewrites_deterministic_across_calls(api_client):
    """Two identical requests produce identical responses."""
    payload = {"demo_mode": "public", "text": "we found jpmorgan inside"}
    a = api_client.post("/safety/scan", json=payload).json()
    b = api_client.post("/safety/scan", json=payload).json()
    assert a == b
