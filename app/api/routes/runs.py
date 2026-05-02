"""Phase 9 run-state routes — thin wrappers over ``atlas.ledger`` reads.

Routes (matches OpenAPI lines 146–239):

  POST /runs                              → RunSummary
  GET  /runs                              → { runs: RunSummary[] }
  GET  /runs/{run_id}                     → RunDetail
  GET  /runs/{run_id}/rounds              → { rounds: RoundSummary[] }
  GET  /runs/{run_id}/rounds/{round_id}   → RoundDetail

Phase 9 invariants honored:

  * ``POST /runs`` only builds an initial ``RunState`` (status=``created``,
    current_round=0). It does NOT execute rounds — the caller follows up
    with ``POST /rounds/run`` (or runs ``make run-rounds``).
  * Every read route uses ``atlas.ledger`` helpers added in component 2;
    no business logic in route handlers.
  * ``RoundDetail`` joins persisted vulnerability + fix + judge artifacts
    by ``run_id`` / ``round_id``. The closed-enum
    ``transcript_summary`` is surfaced verbatim from the persisted
    ``RoundState`` (Bible §18 Phase 9 transcript wording — without
    inventing a separate transcripts route family).
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.api.schemas.run import (  # noqa: E402
    MetricSnapshot,
    RoundDetail,
    RoundSummary,
    RunCreateRequest,
    RunDetail,
    RunSummary,
)
from atlas.ledger.ledger import (  # noqa: E402
    DEFAULT_BASELINE_MODEL_VERSION,
    DEFAULT_BASELINE_THRESHOLD_VERSION,
    MissingJudgeReportError,
    MissingRunError,
    RoundState,
    RunState,
    list_run_states,
    load_judge_report,
    load_round_state,
    load_round_states,
    load_run_defensive_fix_manifests,
    load_run_model_vulnerability_records,
    load_run_state,
    make_run_id,
    persist_run_state,
    read_dataset_reference_now_utc,
)
from atlas.model.loader import DEFAULT_DATA_DIR, MissingDatasetError  # noqa: E402

router = APIRouter()


# Module-level paths — tests monkeypatch to point at hermetic tmp dirs
# (mirrors Phase 7 ``OUTPUTS_ROOT`` pattern).
OUTPUTS_ROOT: Path = REPO_ROOT / "outputs"
DATA_DIR: Path = DEFAULT_DATA_DIR


# ---------------------------------------------------------------------------
# Internal projection helpers
# ---------------------------------------------------------------------------


def _run_state_to_summary(rs: RunState) -> dict[str, Any]:
    """``RunState`` → ``RunSummary`` shape (OpenAPI lines 779–796)."""
    return {
        "run_id": rs.run_id,
        "seed": rs.seed,
        "demo_mode": rs.demo_mode,
        "status": rs.status,
        "current_round": rs.current_round,
        "created_at_utc": rs.created_at_utc,
    }


def _artifact_updated_at_utc(run_id: str) -> str | None:
    """Return local run-state file mtime as an ISO timestamp.

    ``RunState.created_at_utc`` intentionally uses the dataset reference
    time for replay stability, so all generated runs can tie there. The
    run-list route uses this local artifact timestamp to let the web app
    select the run the developer just generated.
    """
    path = OUTPUTS_ROOT / "runs" / f"{run_id}.json"
    if not path.exists():
        return None
    dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _round_state_to_summary(rs: RoundState) -> dict[str, Any]:
    """``RoundState`` → ``RoundSummary`` shape (OpenAPI lines 837–858)."""
    return {
        "run_id": rs.run_id,
        "round_id": rs.round_id,
        "status": rs.status,
        "model_version_before": rs.model_version_before,
        "model_version_after": rs.model_version_after,
        "model_miss_rate_before": rs.model_miss_rate_before,
        "model_miss_rate_after": rs.model_miss_rate_after,
        "recall_at_fixed_action_rate_before": rs.recall_at_fixed_action_rate_before,
        "recall_at_fixed_action_rate_after": rs.recall_at_fixed_action_rate_after,
    }


def _latest_metrics_snapshot(
    rounds: list[RoundState], outputs_root: Path,
) -> dict[str, Any] | None:
    """Build a ``MetricSnapshot`` dict for the most recent round's
    "after" state, sourcing the friction + loss fields from the linked
    judge report when available.

    Mirrors ``atlas.ledger.replay._build_round_metrics`` semantics:
    accepted-fix rounds use the report's ``fixed`` side; rejected /
    no-candidate rounds use the ``baseline`` side (which equals the
    carry-forward state). Returns ``None`` when there are no rounds yet
    OR the linked judge report is missing.
    """
    if not rounds:
        return None
    rs = rounds[-1]
    if not rs.judge_report_id:
        return None
    try:
        report = load_judge_report(rs.judge_report_id, outputs_root)
    except MissingJudgeReportError:
        return None
    side = "fixed" if rs.accepted_fix_id else "baseline"
    md = report.get(side, {}) or {}
    return {
        "round_id": rs.round_id,
        "round_label": f"Round {rs.round_id}",
        "kind": "fixed",
        "model_miss_rate": float(
            md.get("model_miss_rate", rs.model_miss_rate_after)
        ),
        "recall_at_fixed_action_rate": float(
            md.get(
                "recall_at_fixed_action_rate",
                rs.recall_at_fixed_action_rate_after,
            )
        ),
        "false_positive_rate_at_fixed_action_rate": float(
            md.get("false_positive_rate_at_fixed_action_rate", 0.0)
        ),
        "synthetic_loss_allowed": float(md.get("synthetic_loss_allowed", 0.0)),
        "challenge_rate": float(md.get("challenge_rate", 0.0)),
        "alert_rate": float(md.get("alert_rate", 0.0)),
        "decline_rate": float(md.get("decline_rate", 0.0)),
    }


# ---------------------------------------------------------------------------
# POST /runs
# ---------------------------------------------------------------------------


@router.post("/runs", response_model=RunSummary, response_model_exclude_none=True)
def post_runs(req: RunCreateRequest) -> dict:
    """Create a new run record.

    Phase 9 component 3 contract: this DOES NOT execute rounds. It only
    seeds the ``RunState`` (``status="created"``, ``current_round=0``)
    so a follow-up ``POST /rounds/run`` can drive execution. ``run_id``
    is deterministic — same ``(seed, run_label, demo_mode)`` → same id.
    """
    try:
        created_at_utc = read_dataset_reference_now_utc(DATA_DIR)
    except MissingDatasetError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{exc} Run `make seed` first.",
        ) from exc

    run_id = make_run_id(
        seed=req.seed,
        run_label=req.run_label or "",
        demo_mode=req.demo_mode,
    )

    run_state = RunState(
        run_id=run_id,
        seed=req.seed,
        demo_mode=req.demo_mode,
        status="created",
        created_at_utc=created_at_utc,
        current_round=0,
        current_model_version=DEFAULT_BASELINE_MODEL_VERSION,
        current_threshold_version=DEFAULT_BASELINE_THRESHOLD_VERSION,
        run_label=req.run_label or "",
        max_rounds=req.max_rounds,
    )
    persist_run_state(run_state, outputs_root=OUTPUTS_ROOT)
    return _run_state_to_summary(run_state)


# ---------------------------------------------------------------------------
# GET /runs
# ---------------------------------------------------------------------------


@router.get("/runs")
def get_runs() -> dict:
    """List all persisted ``RunState`` snapshots.

    Returns ``{"runs": []}`` when ``outputs/runs/`` is missing or empty
    — a fresh checkout before any ``make run-rounds`` invocation.
    """
    runs = list_run_states(OUTPUTS_ROOT)
    summaries: list[dict[str, Any]] = []
    for run in runs:
        summary = _run_state_to_summary(run)
        artifact_time = _artifact_updated_at_utc(run.run_id)
        if artifact_time is not None:
            summary["created_at_utc"] = artifact_time
        summaries.append(summary)
    return {"runs": summaries}


# ---------------------------------------------------------------------------
# GET /runs/{run_id}
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}",
    response_model=RunDetail,
    response_model_exclude_none=True,
)
def get_run(run_id: str) -> dict:
    try:
        rs = load_run_state(run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    rounds = load_round_states(run_id, outputs_root=OUTPUTS_ROOT)
    body = _run_state_to_summary(rs)
    body["rounds"] = [_round_state_to_summary(r) for r in rounds]
    body["latest_metrics"] = _latest_metrics_snapshot(rounds, OUTPUTS_ROOT)
    return body


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/rounds
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/rounds")
def get_run_rounds(run_id: str) -> dict:
    try:
        load_run_state(run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    rounds = load_round_states(run_id, outputs_root=OUTPUTS_ROOT)
    return {"rounds": [_round_state_to_summary(r) for r in rounds]}


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/rounds/{round_id}
# ---------------------------------------------------------------------------


@router.get(
    "/runs/{run_id}/rounds/{round_id}",
    response_model=RoundDetail,
    response_model_exclude_none=True,
)
def get_run_round(run_id: str, round_id: int) -> dict:
    """Join the persisted vulnerability + fix + judge artifacts for one
    round under one envelope. Closed-enum transcript surfaced verbatim.
    """
    try:
        load_run_state(run_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        rs = load_round_state(run_id, round_id, outputs_root=OUTPUTS_ROOT)
    except MissingRunError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Filter run-scoped vulnerability + fix artifacts down to this round.
    mvs = [
        r
        for r in load_run_model_vulnerability_records(
            run_id, outputs_root=OUTPUTS_ROOT,
        )
        if r.get("round_id") == round_id
    ]
    fixes = [
        r
        for r in load_run_defensive_fix_manifests(
            run_id, outputs_root=OUTPUTS_ROOT,
        )
        if r.get("round_id") == round_id
    ]
    judge_reports: list[dict[str, Any]] = []
    if rs.judge_report_id:
        try:
            judge_reports.append(
                load_judge_report(rs.judge_report_id, outputs_root=OUTPUTS_ROOT)
            )
        except MissingJudgeReportError:
            # The round_state references a judge_report that's gone — surface
            # the round detail without it rather than 404'ing the whole route.
            judge_reports = []

    body = _round_state_to_summary(rs)
    body["model_vulnerabilities"] = mvs
    body["defensive_fixes"] = fixes
    body["judge_reports"] = judge_reports
    body["transcript_summary"] = rs.transcript_summary or None
    body["safety_scan_passed"] = rs.safety_scan_passed
    return body
