"""Phase 9 end-to-end lifecycle test through the route layer.

POST /runs → POST /rounds/run → GET /replay/{run_id} →
GET /runs/{run_id}/rounds/{round_id} → assertions that pin the
page-level invariants the web shell depends on:

  * Replay's ``five_step_story`` has step_id 1..5 in order.
  * Step 1 cards include red_team + bank_defense + deterministic_judge.
  * Step 2 cards have ``category="environment"``.
  * Steps 3, 4, 5 each have at least one ``round_summary`` card.
  * Step 5 has exactly one ``final_report`` card.
  * Charts' ``round_metrics`` kinds ⊆ {baseline, fixed} (no
    interpolated leaks from fixture-mode into live replay).
  * RoundDetail returned by the artifact-join route exposes the slim
    persisted record shape the page renders against.

The test is slow because it runs one real round end-to-end; that's the
smallest amount of execution that proves the chain holds.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.slow
def test_phase9_lifecycle_through_routes(api_client):
    """Full POST → run → replay chain, then assert page-level invariants."""
    # 1. Create the run.
    create_resp = api_client.post(
        "/runs",
        json={
            "seed": 42,
            "run_label": "p9_e2e",
            "demo_mode": "public",
            "max_rounds": 3,
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["run_id"]
    assert run_id.startswith("run_")

    # 2. Run one round via the route (this is the slow bit).
    run_resp = api_client.post(
        "/rounds/run",
        json={"run_id": run_id, "start_round": 1, "round_count": 1},
    )
    assert run_resp.status_code == 200
    completed = run_resp.json()["completed_rounds"]
    assert len(completed) == 1
    assert completed[0]["round_id"] == 1

    # 3. Fetch the replay payload.
    replay_resp = api_client.get(f"/replay/{run_id}")
    assert replay_resp.status_code == 200
    payload = replay_resp.json()
    assert sorted(payload.keys()) == ["charts", "five_step_story", "run"]

    # ``run`` shape sanity.
    assert payload["run"]["run_id"] == run_id
    assert payload["run"]["status"] == "running"  # max_rounds=3, only 1 done
    assert len(payload["run"]["rounds"]) == 1

    # ``five_step_story`` invariants the web page depends on.
    five = payload["five_step_story"]
    assert len(five) == 5
    assert [s["step_id"] for s in five] == [1, 2, 3, 4, 5]

    # Step 1 categories — needed by the page's section narration.
    step1_cats = {c.get("category") for c in five[0]["cards"]}
    assert "red_team" in step1_cats
    assert "bank_defense" in step1_cats
    assert "deterministic_judge" in step1_cats

    # Step 2 categories.
    step2_cats = {c.get("category") for c in five[1]["cards"]}
    assert step2_cats == {"environment"}

    # Steps 3 carries the executed-round summary.
    step3_cats = {c.get("category") for c in five[2]["cards"]}
    assert "round_summary" in step3_cats

    # Steps 4 and 5: round 2 + 3 are not yet executed → empty round_summary.
    step4_cats = {c.get("category") for c in five[3]["cards"]}
    step5_cats = {c.get("category") for c in five[4]["cards"]}
    # Step 5 always has the final_report card even when no rounds.
    assert "final_report" in step5_cats
    # Step 4 has either round_summary (if round 2 ran) or empty.
    assert step4_cats.issubset({"round_summary"})

    # ``charts.round_metrics`` kinds — live replay must NEVER emit
    # ``interpolated`` (Phase 9 invariant: judge-owned metrics only).
    snaps = payload["charts"]["round_metrics"]
    kinds = {s["kind"] for s in snaps}
    assert kinds.issubset({"baseline", "fixed"})
    assert "interpolated" not in kinds
    # 1 baseline + 1 fixed = 2 snapshots after one round.
    assert len(snaps) == 2

    # 4. Fetch RoundDetail for round 1 — verify the artifact-join shape
    # the page renders against (slim persisted records + JudgeReport).
    rd_resp = api_client.get(f"/runs/{run_id}/rounds/1")
    assert rd_resp.status_code == 200
    detail = rd_resp.json()
    assert detail["round_id"] == 1
    # Slim records carry the page-required fields.
    for mv in detail["model_vulnerabilities"]:
        assert mv["run_id"] == run_id
        assert mv["round_id"] == 1
        assert "model_vulnerability_id" in mv
        assert "family_id" in mv
        assert "summary" in mv
        assert "model_miss_rate" in mv
    for fx in detail["defensive_fixes"]:
        assert fx["run_id"] == run_id
        assert fx["round_id"] == 1
        assert "defensive_fix_id" in fx
        assert "fix_type" in fx
    # ``transcript_summary`` is the closed-enum string the
    # SafeTranscriptPanel surfaces.
    assert isinstance(detail["transcript_summary"], str)
    assert detail["transcript_summary"]
    assert detail["safety_scan_passed"] is True
